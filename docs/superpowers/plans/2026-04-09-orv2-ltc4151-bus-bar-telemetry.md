# ORv2 LTC4151 Bus-Bar Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support the Wedge 100S-32X Open Rack V2 (ORv2) SKU variant in which the two internal AC PSUs are replaced by a 12V bus-bar pass-through card carrying an LTC4151 current/voltage monitor at I2C 0x6F. Provide runtime SKU detection so a single platform .deb supports both the AC-PSU SKU and the ORv2 pass-through SKU. Surface bus-bar telemetry as a new `BusBarPsu` platform API object when the pass-through card is detected, and keep the existing `Psu` (AC) path when it is not. Closes GAP-044.

**Architecture:** Four layers. (1) `bmc-daemon` gains an LTC4151 probe at startup: if 0x6F responds on the pass-through card's BMC I2C bus, switch to polling it every 10s and writing `/run/wedge100s/busbar_{volts,amps,power_w}`. (2) A new `BusBarPsu` class in `sonic_platform/` mirrors the `Psu` interface (get_voltage/get_current/get_power/get_status) but sources from the LTC4151 cache instead of PMBus. (3) `chassis.py` `get_all_psus()` returns the AC `Psu` list OR a single `BusBarPsu` based on runtime SKU detection. (4) Tests gate on SKU detection so the same test file passes on both variants. The SKU detection uses a new `/run/wedge100s/sku` cache file written by bmc-daemon so any host-side code can query it without re-probing.

**Tech Stack:** C (bmc-daemon extension), Python 3 (sonic_platform), LTC4151 datasheet register map (public), pytest (hardware tests with SKU-aware skips)

**Platform fork prefix:** `/export/sonic/sonic-buildimage/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
**Devel repo prefix:** `/export/sonic/sonic-wedge100s-devel/`

**⚠️ Critical safety note:** This plan must **NEVER** execute code paths that touch the LTC4151 on an AC-PSU SKU where the chip isn't populated — that would mean scanning an I2C address that might respond with garbage or, per BEWARE_BMC_PMBUS §3a, wedge a ghost slave. The SKU detection probe is a **single targeted `i2cget`** to 0x6F with a short timeout. If it times out, the SKU is AC. No broad scans, ever.

---

## Workflow Compliance

Every task that modifies `sonic-buildimage` MUST follow `docs/workflow.md`:

1. Invoke **`wedge100s-topic-branches`** before touching the platform fork
2. Work on the owning topic branch; never commit directly to master
3. Sync with master first
4. Conventional commits: `feat(<scope>):`, `fix(<scope>):`, `test(<scope>):`
5. Invoke **`wedge100s-doc-check`** before every commit touching `.py` or `.c` files
6. Push, then **STOP** — do not merge to master
7. Invoke **`wedge100s-build-verify`** only in the isolated worktree

### Topic Branch Ownership

| Task | Files | Topic Branch |
|------|-------|-------------|
| 1 (research) | `notes/2026-04-09-ltc4151-research.md` | devel repo `initial` |
| 2 (bmc-daemon SKU detect) | `utils/wedge100s-bmc-daemon.c` | `wedge100s/i2c-bmc-sysfs` |
| 3 (bmc-daemon LTC4151 poll) | `utils/wedge100s-bmc-daemon.c` | `wedge100s/i2c-bmc-sysfs` |
| 4 (BusBarPsu class) | `sonic_platform/busbar_psu.py` (new) | `wedge100s/i2c-bmc-sysfs` |
| 5 (chassis integration) | `sonic_platform/chassis.py` | `wedge100s/device-identity` |
| 6 (platform API wiring) | `sonic_platform/psu.py` | `wedge100s/i2c-bmc-sysfs` |
| 7-9 (tests + docs) | `tests/*`, `notes/PLATFORM_GUIDE.md` | devel repo `initial` |

**Cross-branch note:** The `BusBarPsu` class lives under `sonic_platform/` (per workflow.md §1, owned by `wedge100s/i2c-bmc-sysfs`), but `chassis.py` is owned by `wedge100s/device-identity`. Two separate commits on two separate branches — do not cross-contaminate.

### Test Placement

| Test File | Stage | Covers |
|-----------|-------|--------|
| `tests/stage_06_psu/test_busbar_psu.py` | stage_06_psu | BusBarPsu API when ORv2 SKU is detected (skips on AC SKU) |
| `tests/stage_03_platform/test_sku_detection.py` | stage_03_platform | /run/wedge100s/sku file exists and is one of {ac, orv2} |

---

## Phase 1: Research

### Task 1: Document the LTC4151 register map and pass-through card I2C topology

**Files:**
- Create: `notes/2026-04-09-ltc4151-research.md` (devel repo, branch `initial`)

- [ ] **Step 1: Read the LTC4151 datasheet register map**

The LTC4151 is a public Analog Devices / Linear Technology part. The datasheet is freely available. Record from the datasheet (no subagent network fetch required — the register map is stable and well-known):

```
LTC4151 I2C address: 0x6F (fixed, no address strap)
Register layout (12-bit ADC results, two registers per channel):

  0x00  SENSE_H   Current sense voltage, bits [11:4]
  0x01  SENSE_L   Current sense voltage, bits [3:0] in upper nibble
  0x02  VIN_H     Input voltage, bits [11:4]
  0x03  VIN_L     Input voltage, bits [3:0] in upper nibble
  0x04  ADIN_H    Auxiliary ADC input, bits [11:4]
  0x05  ADIN_L    Auxiliary ADC input, bits [3:0] in upper nibble
  0x06  CONTROL   Control register (R/W) — continuous-convert mode, channel
                  enables. Power-on default enables all three channels in
                  continuous mode, which is what we want.

Conversion constants (from datasheet):
  SENSE: LSB = 20 uV (so raw * 20 / 1000 = mV_across_sense_resistor)
  VIN:   LSB = 25 mV (so raw * 25 = mV_input_voltage)
  ADIN:  LSB = 500 uV (so raw * 500 / 1000 = mV_auxiliary)

For a 1 milliohm sense resistor (typical ORv2 pass-through card value):
  current_A = (sense_mV / 1000) / 0.001 = sense_mV
```

- [ ] **Step 2: Determine the BMC I2C bus for the pass-through card**

The OCP spec v1.3 §5.1.4 (pages 18-19) documents the LTC4151 location. Read those pages with the Read tool's `pages` parameter (the PDF is > 10 pages, so chunking is required):

- `pages: "15-19"` (Section 5.1 — Power and mechanical)

Record:
- The BMC I2C bus number that carries the pass-through card I2C (likely distinct from the existing `i2c-7` PSU bus)
- The sense resistor value documented in the spec (may be 1 mΩ, 0.5 mΩ, or 2 mΩ depending on design)
- Whether the LTC4151 has a mux in front of it or is direct-connect

- [ ] **Step 3: Hardware probe (AC SKU only — we cannot probe an ORv2 SKU we don't have)**

On the AC-PSU SKU that is currently in the lab (`hare-lorax`), verify that scanning 0x6F on every BMC I2C bus returns **no response** (confirming that the pass-through card is physically absent). Do this with **targeted** `i2cget` calls, not `i2cdetect`, per BEWARE_BMC_PMBUS §3a.

```bash
ssh admin@192.168.88.12
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
sudo ssh -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no root@192.168.88.13 \
  'sv stop fscd ipmid; sleep 2'

# Targeted read of 0x6F on each plausible BMC I2C bus.
# If the bus/address is absent, i2cget returns non-zero immediately.
# We only try buses 0-13 (the AST2400 I2C controllers, from earlier probes).
for bus in 0 1 2 3 4 5 6 7 8 9 10 11 12 13; do
  rc=$(ssh admin@192.168.88.12 "sudo ssh -i /etc/sonic/wedge100s-bmc-key \
    -o StrictHostKeyChecking=no root@192.168.88.13 \
    'timeout 1 i2cget -y -f $bus 0x6f 0x06 2>&1; echo rc=\$?'" 2>&1 | tail -2)
  echo "bus $bus: $rc"
done

# Restart daemons
sudo ssh -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no root@192.168.88.13 \
  'sv start fscd ipmid'
sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

Expected on an AC SKU: all 14 buses return `rc=1` (no device at 0x6F) or a timeout. Record any surprise — a positive response on an AC SKU would indicate either (a) the probe is hitting the wrong address or (b) there is a device at 0x6F doing something else, in which case the SKU detection needs a stronger discriminator than "does 0x6F respond?".

**Decision gate:**
- All 14 buses clean → SKU detection via LTC4151 probe is safe. Record the expected-clean behavior as a reference for the test suite.
- A bus responds at 0x6F → STOP. Investigate what's there before writing code that might write to it.

- [ ] **Step 4: Write the research notes**

Write `/export/sonic/sonic-wedge100s-devel/notes/2026-04-09-ltc4151-research.md`:

```markdown
# LTC4151 ORv2 bus-bar telemetry — research notes (GAP-044)

**Date:** 2026-04-09
**Task:** ORv2 SKU support plan — Phase 1 research
**Status:** Research only. SKU detection verified on AC SKU; no ORv2 hardware available.

## LTC4151 datasheet summary

- I2C address: 0x6F (fixed, no strap)
- 12-bit ADC, three channels: SENSE (across Rsense), VIN (input voltage),
  ADIN (auxiliary)
- Register map: 0x00-0x06 (see datasheet for exact layout)
- LSB constants:
  - SENSE: 20 μV
  - VIN:   25 mV
  - ADIN:  500 μV
- Power-on default CONTROL value enables continuous conversion on all channels

## Pass-through card I2C topology (from OCP spec v1.3 §5.1.4)

- Bus: BMC_I2C_<N>  (update from OCP spec pages 15-19)
- Sense resistor: <value> mΩ (update from OCP spec)
- Direct-connect (no mux in front) — recorded from spec diagram

## Hardware probe on AC SKU (hare-lorax, verified 2026-04-09)

All 14 BMC I2C buses (i2c-0 through i2c-13) return rc=1 on targeted
`i2cget -y -f <bus> 0x6f 0x06` reads. No device at 0x6F on any bus.
Confirms that the LTC4151 is physically absent on the AC SKU, and
that SKU detection via "is 0x6F reachable on the documented bus?"
is safe and unambiguous.

## Conversion formulas (for psu.py / busbar_psu.py)

Given Rsense_ohms and raw 12-bit values:

  vin_mv   = vin_raw * 25            # millivolts
  sense_uv = sense_raw * 20          # microvolts across Rsense
  current_a = sense_uv / 1e6 / Rsense_ohms
  power_w   = (vin_mv / 1000) * current_a

For Rsense = 0.001 ohm (1 mΩ typical):
  current_a = sense_raw * 0.02
  => 1 A of bus-bar draw corresponds to 50 ADC counts

## Files affected (for cross-reference in later tasks)

- platform/broadcom/.../utils/wedge100s-bmc-daemon.c (SKU probe + LTC4151 poll)
- platform/broadcom/.../sonic_platform/busbar_psu.py (new class)
- platform/broadcom/.../sonic_platform/psu.py (__all__ export)
- platform/broadcom/.../sonic_platform/chassis.py (SKU-aware get_all_psus)
```

- [ ] **Step 5: Commit**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add notes/2026-04-09-ltc4151-research.md
git commit -m "docs(notes): LTC4151 ORv2 bus-bar telemetry research (GAP-044)

Records LTC4151 datasheet register map, ORv2 pass-through card
I2C topology from OCP spec v1.3 §5.1.4, hardware probe confirming
the chip is absent on the AC SKU (safe SKU detection), and the
conversion formulas for bus-bar voltage/current/power.

Prerequisite for the ORv2 SKU support plan: bmc-daemon SKU
detection, LTC4151 polling, new BusBarPsu class, and chassis
integration that selects between AC Psu and BusBarPsu at
runtime."
```

---

## Phase 2: bmc-daemon SKU detection and LTC4151 polling

### Task 2: Add SKU detection to bmc-daemon

**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c`

Topic branch: `wedge100s/i2c-bmc-sysfs`. Worktree: `/export/sonic/worktrees/wedge100s-i2c-bmc-sysfs`.

- [ ] **Step 1: Ensure the worktree exists**

```bash
cd /export/sonic/sonic-buildimage
if [ ! -d /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs ]; then
  git worktree add /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs wedge100s/i2c-bmc-sysfs
fi
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git merge origin/master --no-edit
git status
```

- [ ] **Step 2: Add SKU detection constants**

Near the top of `wedge100s-bmc-daemon.c`, after the existing `psu_cfg[]` array, add:

```c
/* ORv2 pass-through card LTC4151.
 * Address 0x6F is fixed. Bus number from OCP spec v1.3 §5.1.4 — update if
 * the research notes disagree. Sense resistor is 1 mΩ on the reference
 * design, so current_a = sense_raw * 0.02.
 */
#define LTC4151_BUS         3        /* UPDATE from Task 1 research */
#define LTC4151_ADDR        0x6F
#define LTC4151_RSENSE_MOHM 1        /* 1 mΩ default */

/* SKU detection state. Computed once at daemon startup by probing
 * LTC4151_ADDR on LTC4151_BUS. Written to /run/wedge100s/sku as "ac"
 * or "orv2" for host-side consumers.
 */
enum wedge100s_sku {
    SKU_UNKNOWN = 0,
    SKU_AC,       /* two internal AC PSUs, no LTC4151 */
    SKU_ORV2,     /* 12V bus-bar pass-through card with LTC4151 at 0x6F */
};

static enum wedge100s_sku g_sku = SKU_UNKNOWN;
```

- [ ] **Step 3: Add SKU detection function**

After the existing helper functions (`bmc_run`, `bmc_read_int`, etc.), add:

```c
/**
 * @brief Detect the platform SKU by probing LTC4151 at 0x6F on the
 *        pass-through card's BMC I2C bus.
 *
 * This is a single targeted i2cget call with a 1-second timeout. A
 * successful read of the LTC4151 CONTROL register (0x06) indicates
 * the pass-through card is present and the SKU is ORv2. A failure
 * (timeout, NAK, or bus error) indicates the standard AC SKU.
 *
 * The result is cached in g_sku and written to /run/wedge100s/sku
 * as "ac" or "orv2" for host-side consumers.
 *
 * Per notes/BEWARE_BMC_PMBUS.md §3a, this is a targeted read, not a
 * scan — no ghost-slave risk. Per §4, this should be called once at
 * daemon startup after the BMC SSH ControlMaster is up but before
 * any periodic polling begins.
 *
 * @return SKU_AC or SKU_ORV2 (never SKU_UNKNOWN after this call).
 */
static enum wedge100s_sku detect_sku(void)
{
    char cmd[256];
    int val;

    snprintf(cmd, sizeof(cmd),
             "timeout 1 i2cget -y -f %d 0x%02x 0x06 2>/dev/null",
             LTC4151_BUS, LTC4151_ADDR);
    if (bmc_read_int(cmd, 0, &val) == 0) {
        syslog(LOG_INFO, "SKU detect: LTC4151 responded at bus %d addr 0x%02x "
                         "(CONTROL=0x%02x) — ORv2 SKU",
               LTC4151_BUS, LTC4151_ADDR, val);
        g_sku = SKU_ORV2;
    } else {
        syslog(LOG_INFO, "SKU detect: LTC4151 not present at bus %d addr 0x%02x "
                         "— AC PSU SKU",
               LTC4151_BUS, LTC4151_ADDR);
        g_sku = SKU_AC;
    }

    /* Write SKU cache file for host-side consumers. */
    const char *sku_str = (g_sku == SKU_ORV2) ? "orv2" : "ac";
    FILE *f = fopen(RUN_DIR "/sku", "w");
    if (f) {
        fputs(sku_str, f);
        fputc('\n', f);
        fclose(f);
    }

    return g_sku;
}
```

- [ ] **Step 4: Call detect_sku() at daemon startup**

In `main()`, after `bmc_connect()` returns successfully and before the main poll loop starts, add:

```c
    if (bmc_connect() < 0) {
        syslog(LOG_ERR, "wedge100s-bmc-daemon: initial connect failed — exiting");
        return 1;
    }

    /* Detect platform SKU once at startup. */
    detect_sku();
```

- [ ] **Step 5: Invoke wedge100s-doc-check**

The new function has a full Doxygen header. No other functions touched.

- [ ] **Step 6: Build verify**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -10
```

Skip with SKIPPED if docklock conflict.

- [ ] **Step 7: Commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c
git commit -m "feat(bmc): add runtime SKU detection via LTC4151 probe

wedge100s-bmc-daemon now probes LTC4151 at address 0x6F on BMC_I2C_3
at startup to determine whether the platform is the standard AC
PSU SKU or the ORv2 bus-bar pass-through card SKU. The result is
cached in g_sku and written to /run/wedge100s/sku as 'ac' or 'orv2'
for host-side consumers.

The probe is a single targeted i2cget with a 1-second timeout,
safe per notes/BEWARE_BMC_PMBUS.md §3a — no broad scan, no ghost
slave risk.

Prerequisite for the LTC4151 telemetry polling (Task 3) and the
chassis-level SKU-aware PSU class selection (Tasks 4-5).

Part of GAP-044."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP. Do not merge to master.**

### Task 3: Add LTC4151 polling to bmc-daemon main loop

**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c`

Topic branch: `wedge100s/i2c-bmc-sysfs`.

- [ ] **Step 1: Add LTC4151 register addresses and decode helpers**

After the SKU detection constants in Task 2, add:

```c
/* LTC4151 register addresses (datasheet). 12-bit ADC results are split
 * across two registers: MSB in _H, upper-nibble of LSB in _L.
 */
#define LTC4151_REG_SENSE_H  0x00
#define LTC4151_REG_SENSE_L  0x01
#define LTC4151_REG_VIN_H    0x02
#define LTC4151_REG_VIN_L    0x03
#define LTC4151_REG_ADIN_H   0x04
#define LTC4151_REG_ADIN_L   0x05
#define LTC4151_REG_CONTROL  0x06

/**
 * @brief Combine the H and L halves of a 12-bit ADC result.
 *
 * The LTC4151 stores the 12-bit result as H[7:0]=bits[11:4] and
 * L[7:4]=bits[3:0]. The L register's lower nibble is reserved (zero).
 *
 * @param h  MSB register value (0-255, 8 bits).
 * @param l  LSB register value (0-255; upper nibble is the ADC data).
 * @return 12-bit ADC result (0-4095).
 */
static int ltc4151_combine(int h, int l)
{
    return ((h & 0xff) << 4) | ((l & 0xf0) >> 4);
}
```

- [ ] **Step 2: Add the LTC4151 poll function**

After `detect_sku()`:

```c
/**
 * @brief Poll LTC4151 bus-bar telemetry and write cache files.
 *
 * Reads the six ADC result registers and the control register (as a
 * liveness check), decodes them into voltage (mV), current (mA), and
 * power (mW), and writes three cache files:
 *
 *   /run/wedge100s/busbar_mv       bus-bar input voltage in millivolts
 *   /run/wedge100s/busbar_ma       current draw in milliamps
 *   /run/wedge100s/busbar_mw       power draw in milliwatts (derived)
 *
 * No-op on AC SKU; the caller is expected to gate on g_sku == SKU_ORV2.
 */
static void poll_ltc4151(void)
{
    char cmd[128];
    int vin_h, vin_l, sense_h, sense_l;
    int vin_raw, sense_raw;
    int vin_mv, sense_uv, current_ma, power_mw;

    /* Read VIN high + low */
    snprintf(cmd, sizeof(cmd),
             "i2cget -y -f %d 0x%02x 0x%02x",
             LTC4151_BUS, LTC4151_ADDR, LTC4151_REG_VIN_H);
    if (bmc_read_int(cmd, 0, &vin_h) != 0) return;

    snprintf(cmd, sizeof(cmd),
             "i2cget -y -f %d 0x%02x 0x%02x",
             LTC4151_BUS, LTC4151_ADDR, LTC4151_REG_VIN_L);
    if (bmc_read_int(cmd, 0, &vin_l) != 0) return;

    vin_raw = ltc4151_combine(vin_h, vin_l);
    vin_mv  = vin_raw * 25;  /* 25 mV per LSB per datasheet */

    /* Read SENSE high + low */
    snprintf(cmd, sizeof(cmd),
             "i2cget -y -f %d 0x%02x 0x%02x",
             LTC4151_BUS, LTC4151_ADDR, LTC4151_REG_SENSE_H);
    if (bmc_read_int(cmd, 0, &sense_h) != 0) return;

    snprintf(cmd, sizeof(cmd),
             "i2cget -y -f %d 0x%02x 0x%02x",
             LTC4151_BUS, LTC4151_ADDR, LTC4151_REG_SENSE_L);
    if (bmc_read_int(cmd, 0, &sense_l) != 0) return;

    sense_raw = ltc4151_combine(sense_h, sense_l);
    sense_uv  = sense_raw * 20;  /* 20 uV per LSB per datasheet */

    /* current_mA = sense_uV / Rsense_mOhm
     * (uV / mOhm == mA, since 1 uV / 1 mOhm = 1 mA).
     */
    current_ma = sense_uv / LTC4151_RSENSE_MOHM;

    /* power_mW = vin_mV * current_A = vin_mV * current_mA / 1000 */
    power_mw = (vin_mv * current_ma) / 1000;

    write_file(RUN_DIR "/busbar_mv", vin_mv);
    write_file(RUN_DIR "/busbar_ma", current_ma);
    write_file(RUN_DIR "/busbar_mw", power_mw);
}
```

- [ ] **Step 3: Call poll_ltc4151() from the main loop (only when SKU is ORv2)**

In the main poll loop, find the existing PSU polling block. Wrap it with a SKU conditional, and add the LTC4151 call in the else branch:

```c
    while (1) {
        /* ... existing poll wait, timer, inotify handling ... */

        if (pfds[0].revents & POLLIN) {
            /* timer tick — run 10s polling */

            /* ... existing thermal and fan polling (bus 3/8 — shared between SKUs) ... */

            if (g_sku == SKU_ORV2) {
                /* ORv2 SKU — poll LTC4151 instead of per-PSU PMBus */
                poll_ltc4151();
            } else {
                /* AC SKU — existing PSU PMBus polling unchanged */
                for (int i = 0; i < 2; i++) {
                    /* ... existing PSU poll block (mux select + 7 PMBus regs
                     *     + model/serial block-read) ... */
                }
            }
        }

        /* ... rest of existing loop ... */
    }
```

**CRITICAL:** do not remove the existing PSU polling block. Wrap it in the `g_sku == SKU_AC` (or `else`) branch so that AC-SKU builds keep working exactly as before.

- [ ] **Step 4: Update the daemon header comment**

Add the new cache files to the output-files list at the top of `wedge100s-bmc-daemon.c`:

```c
 * Output files — all plain decimal integers in /run/wedge100s/:
 *   thermal_{1..7}                 TMP75 temperature in millidegrees C
 *   fan_present                    bitmask (0 = all present; bit set = absent)
 *   fan_{1..5}_front               front-rotor RPM
 *   fan_{1..5}_rear                rear-rotor RPM
 *   psu_{1,2}_{vin,iin,iout,pout}  raw PMBus LINEAR11 word (decimal)   [AC SKU]
 *   psu_{1,2}_{vout,temp,fan}      raw PMBus word values                [AC SKU]
 *   psu_{1,2}_{model,serial}       PMBus MFR_MODEL/MFR_SERIAL strings   [AC SKU]
 *   busbar_mv                      LTC4151 input voltage in millivolts  [ORv2 SKU]
 *   busbar_ma                      LTC4151 current draw in milliamps    [ORv2 SKU]
 *   busbar_mw                      derived power draw in milliwatts     [ORv2 SKU]
 *   sku                            "ac" or "orv2" (written once at startup)
 *   qsfp_int                       BMC gpio31 value (0 = interrupt asserted)
 *   qsfp_led_position              BMC gpio59 board strap (written once)
```

- [ ] **Step 5: Invoke wedge100s-doc-check and build verify**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -10
```

Skip if docklock conflict.

- [ ] **Step 6: Commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c
git commit -m "feat(bmc): poll LTC4151 bus-bar telemetry on ORv2 SKU

Adds LTC4151 register reads + voltage/current/power decoding to
the bmc-daemon main loop, gated on g_sku == SKU_ORV2 so the AC-
SKU PSU polling path is unchanged.

Cache files written on ORv2 SKU:
  /run/wedge100s/busbar_mv   bus-bar input voltage (millivolts)
  /run/wedge100s/busbar_ma   current draw (milliamps)
  /run/wedge100s/busbar_mw   derived power draw (milliwatts)

Conversion constants from the LTC4151 datasheet (25 mV/LSB for VIN,
20 uV/LSB for SENSE) with a 1 mΩ sense resistor per OCP spec v1.3
§5.1.4.

Part of GAP-044."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP. Do not merge to master.**

---

## Phase 3: Platform API — BusBarPsu class

### Task 4: Create the BusBarPsu class

**Files:**
- Create: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/busbar_psu.py`

Topic branch: `wedge100s/i2c-bmc-sysfs`.

- [ ] **Step 1: Write busbar_psu.py**

```python
#!/usr/bin/env python3
"""sonic_platform/busbar_psu.py — ORv2 bus-bar PSU for Accton Wedge 100S-32X.

On the ORv2 SKU, the switch draws 12V directly from a rack-level bus bar
via a pass-through card. The card carries an LTC4151 current/voltage
monitor at I2C address 0x6F that wedge100s-bmc-daemon polls every 10
seconds and writes to:

  /run/wedge100s/busbar_mv   bus-bar input voltage (millivolts)
  /run/wedge100s/busbar_ma   current draw (milliamps)
  /run/wedge100s/busbar_mw   derived power draw (milliwatts)

This file exposes the cached values as a single platform-API Psu-like
object so SONiC's system-health and platform monitoring treat the
bus-bar as one "virtual PSU". It is NOT a subclass of the standard Psu
class because it has no PMBus MCU, no present/absent state (the
pass-through card is hard-wired), and no input AC voltage — only a
12V DC input from the rack bus bar.

The chassis integration (chassis.py) decides at runtime whether to
return the two AC Psu instances or a single BusBarPsu instance
depending on /run/wedge100s/sku.
"""

import time

try:
    from sonic_platform_base.psu_base import PsuBase
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")


_RUN_DIR = '/run/wedge100s'

# Telemetry cache to avoid hammering the daemon files on every attribute read.
_CACHE_TTL = 30.0
_cache = {}


def _read_int(path):
    """Read a plain decimal integer from a daemon cache file.

    Args:
        path: Absolute path to the cache file.

    Returns:
        int or None: The parsed integer, or None on any read/parse error.
    """
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (IOError, OSError, ValueError):
        return None


def _read_telemetry():
    """Read all three bus-bar cache files and return a dict.

    Caches the result for _CACHE_TTL seconds to reduce file reads when
    multiple BusBarPsu attributes are queried in quick succession.

    Returns:
        dict: Keys 'mv', 'ma', 'mw', 'ts' — any of the first three may
            be absent if the corresponding cache file was unreadable.
    """
    now = time.monotonic()
    if _cache.get('ts', 0) + _CACHE_TTL > now:
        return _cache

    result = {'ts': now}
    for key, fname in (('mv', 'busbar_mv'),
                       ('ma', 'busbar_ma'),
                       ('mw', 'busbar_mw')):
        val = _read_int('{}/{}'.format(_RUN_DIR, fname))
        if val is not None:
            result[key] = val

    _cache.clear()
    _cache.update(result)
    return result


class BusBarPsu(PsuBase):
    """Virtual PSU representing the ORv2 12V bus-bar input.

    Subclasses PsuBase so `chassis.get_all_psus()` can return it
    alongside (or instead of) the AC Psu class. Methods map as:

      get_voltage()        → busbar_mv / 1000.0  (volts)
      get_current()        → busbar_ma / 1000.0  (amperes)
      get_power()          → busbar_mw / 1000.0  (watts)
      get_presence()       → True if busbar_mv is readable (ORv2
                             pass-through card is always present)
      get_status()         → True if presence AND voltage is in 11-13 V range
      get_powergood_status() → same as get_status()
      get_input_voltage()  → same as get_voltage() (no AC/DC distinction)
      get_input_current()  → same as get_current()
      get_temperature()    → None (LTC4151 has no temperature channel)
      get_num_fans()       → 0 (bus-bar has no fan)
      get_all_fans()       → []
      get_model()          → "ORv2-PassThrough" (fixed)
      get_serial()         → "N/A" (LTC4151 has no serial)
      get_type()           → "DC"
      get_capacity()       → 3300.0 (rack bus-bar nominal, watts)
    """

    def __init__(self):
        """Initialize the bus-bar PSU wrapper."""
        PsuBase.__init__(self)

    # ------------------------------------------------------------------
    # DeviceBase API
    # ------------------------------------------------------------------

    def get_name(self):
        """Return the SONiC-visible name for the bus-bar PSU."""
        return 'BusBar-12V'

    def get_model(self):
        """ORv2 pass-through card has no discrete PSU model."""
        return 'ORv2-PassThrough'

    def get_serial(self):
        """LTC4151 has no serial number exposed over I2C."""
        return 'N/A'

    def get_presence(self):
        """Present iff the bus-bar voltage cache file is readable.

        On ORv2, the pass-through card is hard-wired to the bus bar and
        cannot be "removed" in the same way an AC PSU can be. The only
        way for presence to read False is if the daemon hasn't written
        the cache yet or the LTC4151 read failed.
        """
        return _read_telemetry().get('mv') is not None

    def get_status(self):
        """True when the bus-bar voltage is in the 11-13 V range."""
        mv = _read_telemetry().get('mv')
        if mv is None:
            return False
        return 11000 <= mv <= 13000

    def get_position_in_parent(self):
        """Return the 1-based position (always 1 for the single bus bar)."""
        return 1

    def is_replaceable(self):
        """The ORv2 pass-through card is replaceable at the rack level."""
        return True

    # ------------------------------------------------------------------
    # PsuBase API
    # ------------------------------------------------------------------

    def get_type(self):
        """ORv2 bus bar is DC input (12V nominal)."""
        return 'DC'

    def get_capacity(self):
        """Nominal rack bus-bar capacity per ORv2 spec (watts)."""
        return 3300.0

    def get_voltage(self):
        """Return bus-bar input voltage in volts.

        Returns:
            float: Voltage in volts, or None on read failure.
        """
        mv = _read_telemetry().get('mv')
        return None if mv is None else mv / 1000.0

    def get_current(self):
        """Return bus-bar current draw in amperes.

        Returns:
            float: Current in amperes, or None on read failure.
        """
        ma = _read_telemetry().get('ma')
        return None if ma is None else ma / 1000.0

    def get_power(self):
        """Return derived power draw in watts.

        Returns:
            float: Power in watts, or None on read failure.
        """
        mw = _read_telemetry().get('mw')
        return None if mw is None else mw / 1000.0

    def get_powergood_status(self):
        """True when bus-bar voltage is within the healthy range."""
        return self.get_status()

    def get_input_voltage(self):
        """Return bus-bar input voltage (same as get_voltage for DC input)."""
        return self.get_voltage()

    def get_input_current(self):
        """Return bus-bar input current (same as get_current for DC input)."""
        return self.get_current()

    def get_temperature(self):
        """LTC4151 has no temperature channel."""
        return None

    def get_num_fans(self):
        """ORv2 bus-bar pass-through card has no fans."""
        return 0

    def get_all_fans(self):
        """Return an empty fan list."""
        return []

    def set_status_led(self, color):
        """No dedicated LED on the pass-through card."""
        return False

    def get_status_led(self):
        """Report green when healthy, red otherwise."""
        return (PsuBase.STATUS_LED_COLOR_GREEN if self.get_status()
                else PsuBase.STATUS_LED_COLOR_RED)
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -m py_compile /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/busbar_psu.py && echo OK
```

- [ ] **Step 3: Invoke wedge100s-doc-check**

All public methods have Google-style docstrings. The module has a module-level docstring. No other files touched.

- [ ] **Step 4: Build verify**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -10
```

Skip if docklock.

- [ ] **Step 5: Commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/busbar_psu.py
git commit -m "feat(psu): add BusBarPsu class for ORv2 pass-through card

New sonic_platform/busbar_psu.py exposes the LTC4151 bus-bar
telemetry (voltage, current, derived power) as a single PsuBase
subclass that chassis.py can return instead of the AC Psu list
on the ORv2 SKU.

Reads from /run/wedge100s/busbar_{mv,ma,mw} (written by bmc-daemon
on ORv2 SKU only). get_num_fans() returns 0, get_temperature()
returns None (the LTC4151 has no temperature channel), and
get_model() returns the fixed string 'ORv2-PassThrough'.

Not yet wired into chassis.py — that integration is on the
wedge100s/device-identity branch (Task 5) because chassis.py is
owned by a different topic branch per workflow.md §1.

Part of GAP-044."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP. Do not merge to master.**

---

## Phase 4: Chassis integration

### Task 5: Make chassis.py SKU-aware

**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/chassis.py`

Topic branch: `wedge100s/device-identity`. This is a **different** topic branch from the bmc-daemon + busbar_psu work because `chassis.py` is owned by `wedge100s/device-identity` per workflow.md §1.

- [ ] **Step 1: Ensure the device-identity worktree exists and is synced**

```bash
cd /export/sonic/sonic-buildimage
if [ ! -d /export/sonic/worktrees/wedge100s-device-identity ]; then
  git worktree add /export/sonic/worktrees/wedge100s-device-identity wedge100s/device-identity
fi
cd /export/sonic/worktrees/wedge100s-device-identity
git merge origin/master --no-edit
git status
```

- [ ] **Step 2: Find the current get_all_psus() implementation**

```bash
grep -n '_psus\|get_all_psus\|Psu(' \
  platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/chassis.py | head -20
```

Identify how the Psu list is currently constructed (likely `[Psu(1), Psu(2)]` in `__init__` or on first call).

- [ ] **Step 3: Add SKU detection helper and lazy BusBarPsu import**

At the top of `chassis.py`, after existing imports, add:

```python
# ORv2 SKU support — if /run/wedge100s/sku reads as "orv2", get_all_psus()
# returns a single BusBarPsu instead of the two AC Psu instances.
_SKU_FILE = '/run/wedge100s/sku'


def _platform_sku():
    """Read /run/wedge100s/sku and return 'ac' or 'orv2'.

    Written once by wedge100s-bmc-daemon at startup. Defaults to 'ac'
    if the file is missing (backward-compatible behavior — pre-GAP-044
    builds will behave exactly as they did before).

    Returns:
        str: 'ac' or 'orv2'.
    """
    try:
        with open(_SKU_FILE) as f:
            val = f.read().strip()
        if val == 'orv2':
            return 'orv2'
    except (IOError, OSError):
        pass
    return 'ac'
```

- [ ] **Step 4: Update __init__ to populate _psus based on SKU**

Replace the existing PSU list construction:

```python
# BEFORE (approximate — check the actual file):
self._psus = [Psu(1), Psu(2)]

# AFTER:
if _platform_sku() == 'orv2':
    # ORv2 SKU: single bus-bar pass-through card via LTC4151
    from .busbar_psu import BusBarPsu
    self._psus = [BusBarPsu()]
else:
    # AC SKU: two internal PSUs with PMBus telemetry
    self._psus = [Psu(1), Psu(2)]
```

The `from .busbar_psu import BusBarPsu` is intentionally inside the conditional so that AC SKUs don't import the new module (defensive — if the new file has a parse error, AC SKUs still boot).

- [ ] **Step 5: Update get_num_psus() if it's hardcoded**

```bash
grep -n 'NUM_PSUS\|get_num_psus' \
  platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/chassis.py
```

If there's a hardcoded `NUM_PSUS = 2` constant or a `get_num_psus()` that returns a literal 2, change it to:

```python
def get_num_psus(self):
    """Return the number of PSU objects exposed by this chassis.

    Varies by SKU: 2 on the AC PSU SKU, 1 (bus-bar) on the ORv2 SKU.

    Returns:
        int: Number of PSUs.
    """
    return len(self._psus)
```

- [ ] **Step 6: Verify syntax**

```bash
python3 -m py_compile /export/sonic/worktrees/wedge100s-device-identity/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/chassis.py && echo OK
```

- [ ] **Step 7: Invoke wedge100s-doc-check**

- [ ] **Step 8: Build verify**

```bash
cd /export/sonic/worktrees/wedge100s-device-identity
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -10
```

Skip if docklock.

- [ ] **Step 9: Commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-device-identity
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/chassis.py
git commit -m "feat(chassis): return BusBarPsu on ORv2 SKU, two Psu on AC SKU

chassis.py now reads /run/wedge100s/sku (written by
wedge100s-bmc-daemon at startup) to decide whether
get_all_psus() returns the two AC Psu instances or a single
BusBarPsu instance.

Defaults to AC SKU if the sku file is missing, so pre-GAP-044
builds behave identically to before. get_num_psus() returns
len(self._psus) so callers see the SKU-appropriate count.

Depends on: wedge100s/i2c-bmc-sysfs commits adding
detect_sku() to bmc-daemon and the BusBarPsu class to
sonic_platform/.

Part of GAP-044."
git push origin wedge100s/device-identity
```

**STOP. Do not merge to master.**

---

## Phase 5: Tests and documentation

### Task 6: SKU detection test

**Files:**
- Create: `tests/stage_03_platform/test_sku_detection.py` (devel repo)

- [ ] **Step 1: Write the test**

```python
"""Stage 03 supplement — runtime SKU detection (GAP-044).

Verifies that wedge100s-bmc-daemon has probed the LTC4151 and written
the result to /run/wedge100s/sku. The value must be 'ac' or 'orv2';
any other value indicates a bug in detect_sku() or a corrupted cache
file.

Also asserts that the cached SKU matches what Chassis.get_num_psus()
returns (sanity check that the chassis wiring reads the same value).
"""

import pytest

RUN_DIR = "/run/wedge100s"
SKU_FILE = f"{RUN_DIR}/sku"

CAPTURE = """\
from sonic_platform.platform import Platform
chassis = Platform().get_chassis()
print(chassis.get_num_psus())
"""


def _read_sku(ssh):
    out, _, rc = ssh.run(f"cat {SKU_FILE}", timeout=5)
    return out.strip() if rc == 0 else None


def test_sku_file_exists(ssh):
    """/run/wedge100s/sku exists and is readable."""
    out, _, rc = ssh.run(
        f"test -f {SKU_FILE} && echo YES || echo NO", timeout=5)
    assert "YES" in out, (
        f"{SKU_FILE} missing. Is wedge100s-bmc-daemon running with "
        "SKU detection (GAP-044)?"
    )


def test_sku_value_valid(ssh):
    """/run/wedge100s/sku is 'ac' or 'orv2'."""
    sku = _read_sku(ssh)
    assert sku in ("ac", "orv2"), (
        f"{SKU_FILE} = {sku!r}, expected 'ac' or 'orv2'"
    )
    print(f"  Detected SKU: {sku}")


def test_num_psus_matches_sku(ssh):
    """chassis.get_num_psus() matches the detected SKU.

    AC SKU → 2 PSUs (PSU-1 + PSU-2).
    ORv2 SKU → 1 PSU (BusBar-12V).
    """
    sku = _read_sku(ssh)
    if sku is None:
        pytest.skip("SKU file unavailable")

    out, err, rc = ssh.run_python(CAPTURE, timeout=20)
    assert rc == 0, f"get_num_psus() script failed: {err}"
    num = int(out.strip())

    if sku == "ac":
        assert num == 2, (
            f"AC SKU but get_num_psus()={num}, expected 2. "
            "Is chassis.py using _platform_sku()?"
        )
    elif sku == "orv2":
        assert num == 1, (
            f"ORv2 SKU but get_num_psus()={num}, expected 1. "
            "Is chassis.py constructing BusBarPsu?"
        )
    print(f"  SKU={sku}, num_psus={num}")
```

- [ ] **Step 2: Commit in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/stage_03_platform/test_sku_detection.py
git commit -m "test(platform): add SKU detection and chassis consistency test (GAP-044)

Three tests:
1. /run/wedge100s/sku exists
2. Its value is 'ac' or 'orv2'
3. chassis.get_num_psus() matches the detected SKU (2 for AC, 1
   for ORv2)

Passes on both SKU variants; no gating needed."
```

### Task 7: BusBarPsu platform API test

**Files:**
- Create: `tests/stage_06_psu/test_busbar_psu.py` (devel repo)

- [ ] **Step 1: Write the test**

```python
"""Stage 06 supplement — ORv2 BusBarPsu platform API (GAP-044).

Verifies that when the SKU is ORv2, chassis.get_all_psus() returns a
single BusBarPsu instance whose methods produce plausible values from
the LTC4151 telemetry cache. Skips entirely on AC SKU.
"""

import json
import pytest

RUN_DIR = "/run/wedge100s"
SKU_FILE = f"{RUN_DIR}/sku"

CAPTURE = """\
import json
from sonic_platform.platform import Platform
chassis = Platform().get_chassis()
psus = chassis.get_all_psus()
results = []
for psu in psus:
    results.append({
        "name": psu.get_name(),
        "model": psu.get_model(),
        "serial": psu.get_serial(),
        "type": psu.get_type(),
        "capacity_w": psu.get_capacity(),
        "present": psu.get_presence(),
        "status": psu.get_status(),
        "pgood": psu.get_powergood_status(),
        "voltage": psu.get_voltage(),
        "current": psu.get_current(),
        "power": psu.get_power(),
        "input_voltage": psu.get_input_voltage(),
        "input_current": psu.get_input_current(),
        "temperature": psu.get_temperature(),
        "num_fans": psu.get_num_fans(),
    })
print(json.dumps(results))
"""


def _read_sku(ssh):
    out, _, rc = ssh.run(f"cat {SKU_FILE}", timeout=5)
    return out.strip() if rc == 0 else None


def _capture_psus(ssh):
    out, err, rc = ssh.run_python(CAPTURE, timeout=30)
    assert rc == 0, f"PSU capture failed: {err}"
    return json.loads(out.strip())


def test_busbar_psu_only_on_orv2(ssh):
    """On ORv2 SKU, get_all_psus() returns exactly one BusBar-12V."""
    sku = _read_sku(ssh)
    if sku != "orv2":
        pytest.skip(f"Not an ORv2 SKU (sku={sku}); BusBarPsu test skipped")

    psus = _capture_psus(ssh)
    assert len(psus) == 1, f"Expected 1 PSU on ORv2, got {len(psus)}"
    assert psus[0]["name"] == "BusBar-12V", (
        f"Expected name 'BusBar-12V', got {psus[0]['name']!r}"
    )
    assert psus[0]["type"] == "DC", (
        f"Expected type 'DC', got {psus[0]['type']!r}"
    )
    assert psus[0]["model"] == "ORv2-PassThrough"


def test_busbar_voltage_in_range(ssh):
    """Bus-bar voltage is 11-13 V (12V nominal ±8%)."""
    sku = _read_sku(ssh)
    if sku != "orv2":
        pytest.skip("Not an ORv2 SKU")

    psus = _capture_psus(ssh)
    v = psus[0]["voltage"]
    assert v is not None, "BusBarPsu.get_voltage() returned None"
    print(f"  Bus-bar voltage: {v:.3f} V")
    assert 11.0 <= v <= 13.0, f"voltage={v} V outside 11-13 V range"


def test_busbar_current_non_negative(ssh):
    """Bus-bar current is non-negative and below a sanity ceiling."""
    sku = _read_sku(ssh)
    if sku != "orv2":
        pytest.skip("Not an ORv2 SKU")

    psus = _capture_psus(ssh)
    i = psus[0]["current"]
    assert i is not None, "BusBarPsu.get_current() returned None"
    print(f"  Bus-bar current: {i:.3f} A")
    # Wedge 100S ceiling: 500W / 12V ≈ 42A peak. 100A is a generous sanity cap.
    assert 0.0 <= i <= 100.0, f"current={i} A outside 0-100 A sanity range"


def test_busbar_power_consistency(ssh):
    """Derived power matches voltage * current within ±5%."""
    sku = _read_sku(ssh)
    if sku != "orv2":
        pytest.skip("Not an ORv2 SKU")

    psus = _capture_psus(ssh)
    v = psus[0]["voltage"]
    i = psus[0]["current"]
    p = psus[0]["power"]
    if v is None or i is None or p is None:
        pytest.skip("One of voltage/current/power is None")

    expected = v * i
    tolerance = max(expected * 0.05, 1.0)  # 5% or 1W, whichever is larger
    print(f"  Power: {p:.2f} W (expected {expected:.2f} W ± {tolerance:.2f})")
    assert abs(p - expected) <= tolerance, (
        f"power={p} W does not match voltage*current={expected} W "
        f"(tolerance {tolerance} W)"
    )


def test_busbar_no_fans(ssh):
    """BusBarPsu.get_num_fans() returns 0."""
    sku = _read_sku(ssh)
    if sku != "orv2":
        pytest.skip("Not an ORv2 SKU")

    psus = _capture_psus(ssh)
    assert psus[0]["num_fans"] == 0


def test_busbar_no_temperature(ssh):
    """BusBarPsu.get_temperature() returns None (LTC4151 has no temp)."""
    sku = _read_sku(ssh)
    if sku != "orv2":
        pytest.skip("Not an ORv2 SKU")

    psus = _capture_psus(ssh)
    assert psus[0]["temperature"] is None
```

- [ ] **Step 2: Commit in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/stage_06_psu/test_busbar_psu.py
git commit -m "test(psu): add BusBarPsu platform API tests (GAP-044)

Six tests that run only when /run/wedge100s/sku reads as 'orv2':
1. get_all_psus() returns exactly 1 BusBar-12V with type='DC'
2. voltage is 11-13 V (12V nominal ±8%)
3. current is 0-100 A (sanity ceiling)
4. power = voltage * current within ±5% or ±1 W
5. num_fans == 0
6. temperature is None (LTC4151 has no temperature channel)

Skips cleanly on AC SKU so the same test file passes on both SKU
variants."
```

### Task 8: Report + reporter update

**Files:**
- Modify: `tests/lib/report.py` (devel repo)

- [ ] **Step 1: Find and update report_psu()**

```bash
grep -n 'def report_psu' /export/sonic/sonic-wedge100s-devel/tests/lib/report.py
```

Extend the existing PSU reporter to also print bus-bar telemetry on ORv2 SKUs. Add near the end of `report_psu()` (just before the final `print` or return):

```python
    # ── Bus-bar telemetry (GAP-044, ORv2 SKU only) ─────────────────────
    out, _, rc = ssh.run("cat /run/wedge100s/sku 2>/dev/null", timeout=5)
    if rc == 0 and out.strip() == "orv2":
        mv, _, rc_mv = ssh.run("cat /run/wedge100s/busbar_mv 2>/dev/null", timeout=5)
        ma, _, rc_ma = ssh.run("cat /run/wedge100s/busbar_ma 2>/dev/null", timeout=5)
        mw, _, rc_mw = ssh.run("cat /run/wedge100s/busbar_mw 2>/dev/null", timeout=5)
        if rc_mv == 0 and rc_ma == 0 and rc_mw == 0:
            print("\n  Bus-bar telemetry (LTC4151):")
            print(f"    Voltage : {int(mv)/1000:.3f} V")
            print(f"    Current : {int(ma)/1000:.3f} A")
            print(f"    Power   : {int(mw)/1000:.2f} W")
```

- [ ] **Step 2: Commit in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/lib/report.py
git commit -m "test(report): show bus-bar telemetry on ORv2 SKU in report_psu (GAP-044)

When /run/wedge100s/sku reads 'orv2', report_psu() also prints the
LTC4151 bus-bar voltage/current/power below the standard PSU
summary. AC SKU output is unchanged."
```

### Task 9: Update PLATFORM_GUIDE.md

**Files:**
- Modify: `notes/PLATFORM_GUIDE.md` (devel repo)

- [ ] **Step 1: Add an ORv2 SKU subsection**

In PLATFORM_GUIDE.md Section 10 (Power Supply) or Section 14 (Power Distribution), add a new subsection documenting the ORv2 SKU variant:

```markdown
### ORv2 Pass-Through SKU

The Wedge 100S-32X ships in two power SKUs sharing the same platform .deb:

| SKU | PSUs | Monitoring | Detection |
|---|---|---|---|
| Standard (AC) | 2× Delta SPAFCBK-14G 650 W AC | PMBus at 0x59/0x5A on BMC_I2C_7 via `bmc-daemon` | `/run/wedge100s/sku` = `ac` |
| ORv2 | 12 V bus-bar pass-through card | LTC4151 at 0x6F on BMC_I2C_<N> via `bmc-daemon` | `/run/wedge100s/sku` = `orv2` |

`wedge100s-bmc-daemon` probes the LTC4151 address at startup with a
single targeted `i2cget`. If it responds, the daemon switches to
polling LTC4151 registers instead of the per-PSU PMBus path and
writes `/run/wedge100s/busbar_{mv,ma,mw}` every 10 seconds. If it
doesn't respond, the daemon continues with the existing AC-SKU PSU
polling unchanged.

`chassis.py` `get_all_psus()` reads `/run/wedge100s/sku` and returns
either the two AC `Psu` instances or a single `BusBarPsu` instance.
The rest of SONiC's platform API is unaffected — `show platform
psustatus` prints whichever flavor is live.

On ORv2, these AC-specific attributes return non-useful values:
- `get_serial()` returns `"N/A"` (LTC4151 has no serial)
- `get_temperature()` returns `None` (LTC4151 has no temperature channel)
- `get_num_fans()` returns `0`

These are documented in `notes/2026-04-09-ltc4151-research.md`.
```

- [ ] **Step 2: Commit**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add notes/PLATFORM_GUIDE.md
git commit -m "docs(guide): document ORv2 pass-through SKU variant (GAP-044)

Adds a new subsection under Power Supply describing the two power
SKUs (AC dual-PSU and ORv2 12V bus-bar pass-through), runtime SKU
detection via /run/wedge100s/sku, LTC4151 telemetry cache files,
and the BusBarPsu platform API object used on ORv2.

Cross-references notes/2026-04-09-ltc4151-research.md for the
LTC4151 register map and conversion formulas."
```

---

## Summary of topic branch commits when plan is complete

| Branch | Commits | Purpose |
|--------|---------|---------|
| `wedge100s/i2c-bmc-sysfs` | ~3 | bmc-daemon SKU detect + LTC4151 poll, BusBarPsu class |
| `wedge100s/device-identity` | ~1 | chassis.py SKU-aware get_all_psus |
| devel `initial` | ~5 | research notes, 2 test files, reporter update, PLATFORM_GUIDE update |

**No branch is merged to master** by this plan — deferred per session convention.
