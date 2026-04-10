# P2 Feature Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all P2 feature-completeness gaps from DESIGNGAPS.md Phase 4: power telemetry (GAP-021, GAP-022), QSFP hardware reset (GAP-026), CL73 autoneg (GAP-027), LED breakout-mode lane mapping (GAP-028), Eagle Core management port (GAP-024), TPM integration (GAP-023), and health config cleanup (GAP-045).

**Architecture:** Eight independent work items across five topic branches. Each task is self-contained and can be executed in any order. Power telemetry (GAP-021/022) and QSFP reset (GAP-026) extend the existing bmc-daemon + Python API pattern. BCM config changes (GAP-024/027) are chipset configuration. LED work (GAP-028) modifies the ledup linkstate daemon. TPM (GAP-023) is an investigation-first task.

**Tech Stack:** C (bmc-daemon), Python 3 (platform API, ledup daemon), BCM SDK SOC scripting, BCM diag shell, pytest (hardware tests over SSH)

**Platform fork:** `/export/sonic/sonic-buildimage/`
**Platform modules prefix:** `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
**Device config prefix:** `device/accton/x86_64-accton_wedge100s_32x-r0/`
**Devel repo:** `/export/sonic/sonic-wedge100s-devel/`

**Important:** Several tasks require datasheet research (PWR1014A, IR3581/IR3584, SLB9645) and hardware experimentation (autoneg interop, Eagle Core link). These tasks include research steps — do not skip them and guess register addresses.

---

## Workflow Compliance

Every task that modifies `sonic-buildimage` MUST follow `docs/workflow.md`:

1. **Invoke `wedge100s-topic-branches` skill** before touching any file in the platform fork.
2. **Work on the owning topic branch** — never commit directly to master. See the ownership table below.
3. **Sync with master first:** `git checkout wedge100s/<topic> && git merge origin/master --no-edit`
4. **Conventional commits:** `feat(<scope>): ...`, `fix(<scope>): ...`, `test(<scope>): ...`
5. **Invoke `wedge100s-doc-check` skill** before every commit touching `.py` or `.c` files. All new C functions need `@brief`/`@param`/`@return` Doxygen headers. All new Python methods need Google-style docstrings.
6. **Push, then merge to master:** `git push origin wedge100s/<topic>` → `git checkout master` → `git merge origin/wedge100s/<topic> --no-edit` → `git push origin master`
7. **Invoke `wedge100s-build-verify` skill** after merging to master: `BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb`

### Topic Branch Ownership (this plan)

| Task | Gap(s) | Topic Branch | Owns |
|------|--------|-------------|------|
| 1, 2, 8 | GAP-021, GAP-022, GAP-045 | `wedge100s/i2c-bmc-sysfs` | `utils/wedge100s-bmc-daemon.c`, `sonic_platform/{psu,thermal}.py` |
| 3 | GAP-026 | `wedge100s/sfp-optics` | `sonic_platform/sfp.py` |
| 4, 6 | GAP-027, GAP-024 | `wedge100s/chipset-config` | `*.config.bcm`, `led_proc_init.soc` |
| 5 | GAP-028 | `wedge100s/led-pipeline` | `utils/wedge100s-ledup-linkstate` |
| 7 | GAP-023 | `wedge100s/security` (new) | TPM module loading |

### Test Placement (this plan)

Tests live in `sonic-wedge100s-devel` (never in `sonic-buildimage` — workflow anti-pattern #4). New tests go into the **existing stage directory** that covers the subsystem. New test files use the existing `ssh` session fixture from `conftest.py`. Reporters in `tests/lib/report.py` are updated to display new data.

| Test File | Stage | Covers |
|-----------|-------|--------|
| `tests/stage_03_platform/test_power_telemetry.py` | stage_03_platform | GAP-021 (power sequencer), GAP-022 (VRM telemetry) |
| `tests/stage_07_qsfp/test_qsfp_reset.py` | stage_07_qsfp | GAP-026 (QSFP hardware reset) |
| `tests/stage_15_autoneg_fec/test_autoneg_cl73.py` | stage_15_autoneg_fec | GAP-027 (CL73 autoneg) |
| `tests/stage_08_led/test_led_breakout.py` | stage_08_led | GAP-028 (LED breakout-mode) |

No new stages are created — `run_tests.py` discovers stages via `stage_*` glob, so new test files in existing stage directories are picked up automatically.

---

### Task 1: Add PWR1014A power sequencer voltage telemetry to bmc-daemon

**Gap:** GAP-021
**Topic branch:** `wedge100s/i2c-bmc-sysfs`
**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c`

The PWR1014A (TI UCD9090 family) power sequencer on BMC_I2C_3 at address 0x3A monitors 10 voltage rails. It speaks PMBus — the same protocol the bmc-daemon already uses for PSU telemetry.

- [ ] **Step 1: Checkout topic branch and sync**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/i2c-bmc-sysfs
git merge origin/master --no-edit
```

- [ ] **Step 2: Research PWR1014A register map on hardware**

SSH to the switch and probe the device. **Stop daemons first** per CLAUDE.md I2C bus safety rules:

```bash
ssh admin@192.168.88.12
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

# Probe via BMC
sshpass -p '0penBmc' ssh -o StrictHostKeyChecking=no root@192.168.88.13 \
  'i2cdetect -y 3' 2>/dev/null
# Expect 0x3A to show as UU or device address

# Read PMBus DEVICE_ID (0xFD)
sshpass -p '0penBmc' ssh root@192.168.88.13 \
  'i2ctransfer -y 3 w1@0x3a 0xfd r32@0x3a' 2>/dev/null

# Read NUM_PAGES (0xD0) — one page per rail
sshpass -p '0penBmc' ssh root@192.168.88.13 \
  'i2cget -y 3 0x3a 0xd0' 2>/dev/null

# Read VOUT_MODE (0x20) to get exponent for voltage decoding
sshpass -p '0penBmc' ssh root@192.168.88.13 \
  'i2cget -y 3 0x3a 0x20' 2>/dev/null

# For each page (rail), select page and read READ_VOUT (0x8B)
for page in 0 1 2 3 4 5 6 7 8 9; do
  sshpass -p '0penBmc' ssh root@192.168.88.13 \
    "i2cset -y 3 0x3a 0x00 $page && i2cget -y 3 0x3a 0x8b w" 2>/dev/null
  echo "Page $page: $?"
done

sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

Write findings to `notes/2026-04-09-pwr1014a-research.md` in the **devel repo**. Key data: number of pages, page-to-rail mapping, VOUT_MODE exponent.

- [ ] **Step 3: Add rail name constants and poll function**

After the existing PSU polling code in `wedge100s-bmc-daemon.c`, add (update page count, rail names, and exponent from Step 2):

```c
/* PWR1014A (UCD9090) power sequencer on BMC_I2C_3 at 0x3A.
 * PMBus page-per-rail architecture: select PAGE (0x00), read READ_VOUT (0x8B).
 * VOUT_MODE (0x20) determines scaling — typically LINEAR16 (exponent -12).
 *
 * Page-to-rail mapping (from hardware probe — update after Step 2):
 */
#define PWRSEQ_BUS    3
#define PWRSEQ_ADDR   0x3A
#define PWRSEQ_PAGES  10   /* update from NUM_PAGES read */

static const char *pwrseq_rail_names[PWRSEQ_PAGES] = {
    "3v3_stby",    /* page 0 — update from hardware probe */
    "3v3_main",    /* page 1 */
    "1v8",         /* page 2 */
    "1v25",        /* page 3 */
    "1v0_rov",     /* page 4 — Tomahawk core */
    "1v0_analog",  /* page 5 */
    "stby_1",      /* page 6 */
    "stby_2",      /* page 7 */
    "stby_3",      /* page 8 */
    "stby_4",      /* page 9 */
};

/**
 * @brief Read one voltage rail from PWR1014A via PMBus page select + READ_VOUT.
 * @param page  PMBus page number (0-based rail index).
 * @param mv    Output: voltage in millivolts.
 * @return 0 on success, -1 on failure.
 */
static int pwrseq_read_vout(int page, int *mv)
{
    char cmd[256];
    int raw;

    /* Select page. */
    snprintf(cmd, sizeof(cmd),
             "i2cset -y %d 0x%02x 0x00 0x%02x",
             PWRSEQ_BUS, PWRSEQ_ADDR, page);
    bmc_run(cmd);

    /* Read VOUT (LINEAR16, exponent -12 typical for UCD90xx).
     * Raw value × 2^exponent = volts. With exp=-12: mV = raw * 1000 >> 12.
     * Verify exponent from VOUT_MODE (0x20) on hardware.
     */
    snprintf(cmd, sizeof(cmd),
             "i2cget -y %d 0x%02x 0x8b w",
             PWRSEQ_BUS, PWRSEQ_ADDR);
    raw = bmc_read_int(cmd, 0);
    if (raw < 0) return -1;

    *mv = (raw * 1000) >> 12;
    return 0;
}
```

- [ ] **Step 4: Add power sequencer poll to main loop**

In the main poll loop, after the PSU polling block:

```c
    /* Power sequencer rail voltages (poll every cycle = 10s). */
    for (int p = 0; p < PWRSEQ_PAGES; p++) {
        int mv;
        if (pwrseq_read_vout(p, &mv) == 0) {
            char path[128];
            snprintf(path, sizeof(path),
                     RUN_DIR "/vrail_%s_mv", pwrseq_rail_names[p]);
            write_file(path, mv);
        }
    }
```

- [ ] **Step 5: Run wedge100s-doc-check — verify Doxygen headers**

Invoke the `wedge100s-doc-check` skill. Ensure every new function in `wedge100s-bmc-daemon.c` has a `@brief`, `@param`, and `@return` Doxygen header.

- [ ] **Step 6: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 7: Commit and push on topic branch**

```bash
cd /export/sonic/sonic-buildimage
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c
git commit -m "feat(bmc): add PWR1014A power sequencer voltage telemetry

Read 10-rail voltage from UCD9090 sequencer at BMC_I2C_3/0x3A via
PMBus page-select + READ_VOUT. Write per-rail millivolt values to
/run/wedge100s/vrail_<name>_mv.

Closes: GAP-021"
git push origin wedge100s/i2c-bmc-sysfs
```

**Do NOT merge to master yet** — Task 2 adds more code to the same file on the same branch. Merge after Task 2.

- [ ] **Step 8: Write test in devel repo — `tests/stage_03_platform/test_power_telemetry.py`**

This file covers both GAP-021 (power sequencer) and GAP-022 (VRM telemetry). Create it now with the power sequencer tests; VRM tests are added in Task 2.

```python
"""Stage 03 supplement — Power rail telemetry (power sequencer + VRMs).

GAP-021: PWR1014A voltage rails via /run/wedge100s/vrail_*_mv.
GAP-022: IR3581/IR3584 VRM telemetry via /run/wedge100s/vrm_*_{vout_mv,iout_ma,temp_mc}.

Both are read by wedge100s-bmc-daemon from BMC I2C buses 2 and 3.
"""

import pytest

RUN_DIR = "/run/wedge100s"

# ── GAP-021: PWR1014A power sequencer rails ────────────────────────────────
# Expected rails and nominal voltage range in mV (±20% tolerance).
EXPECTED_RAILS = {
    "3v3_stby":   (2640, 3960),
    "3v3_main":   (2640, 3960),
    "1v8":        (1440, 2160),
    "1v25":       (1000, 1500),
    "1v0_rov":    (750, 1200),   # ROV adjusts this
    "1v0_analog": (800, 1200),
}


def test_vrail_files_exist(ssh):
    """Core voltage rail files should be present in /run/wedge100s/."""
    missing = []
    for rail in EXPECTED_RAILS:
        path = f"{RUN_DIR}/vrail_{rail}_mv"
        out, _, rc = ssh.run(f"test -f {path} && echo YES || echo NO", timeout=10)
        if "YES" not in out:
            missing.append(rail)
    assert not missing, (
        f"Missing vrail files: {missing}. "
        "Is wedge100s-bmc-daemon running with power sequencer support?"
    )


def test_vrail_values_reasonable(ssh):
    """Each voltage rail should be within ±20% of nominal."""
    for rail, (lo, hi) in EXPECTED_RAILS.items():
        path = f"{RUN_DIR}/vrail_{rail}_mv"
        out, _, rc = ssh.run(f"cat {path} 2>/dev/null", timeout=10)
        if rc != 0:
            continue
        mv = int(out.strip())
        print(f"  {rail}: {mv} mV (expected {lo}-{hi})")
        assert lo <= mv <= hi, (
            f"{rail}: {mv} mV outside expected range {lo}-{hi} mV"
        )
```

- [ ] **Step 9: Write research notes and commit devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/stage_03_platform/test_power_telemetry.py \
        notes/2026-04-09-pwr1014a-research.md
git commit -m "test(platform): add power sequencer voltage telemetry tests

Cover GAP-021 (PWR1014A rail monitoring) in stage_03_platform.
Validates bmc-daemon cache files contain reasonable voltage values."
```

---

### Task 2: Add IR3581/IR3584 VRM telemetry to bmc-daemon

**Gap:** GAP-022
**Topic branch:** `wedge100s/i2c-bmc-sysfs` (same branch as Task 1, already checked out)
**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c`

The Infineon IR3581 (6-phase core VRM) and two IR3584 (2-phase analog + 3.3V VRMs) on BMC_I2C_2 support PMBus telemetry: output voltage, output current, and die temperature.

- [ ] **Step 1: Research VRM register map on hardware**

```bash
ssh admin@192.168.88.12
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

# Probe BMC I2C bus 2 for VRMs
sshpass -p '0penBmc' ssh root@192.168.88.13 'i2cdetect -y 2' 2>/dev/null
# Expect: 0x10 (IR3581 core), 0x12 (IR3584 analog), 0x14 (IR3584 3.3V)

# Read VOUT_MODE (0x20) from each VRM to determine exponent
for addr in 0x10 0x12 0x14; do
  echo "--- $addr ---"
  sshpass -p '0penBmc' ssh root@192.168.88.13 "i2cget -y 2 $addr 0x20" 2>/dev/null
done

# Read core VRM telemetry: READ_VOUT (0x8B), READ_IOUT (0x8C), READ_TEMPERATURE_1 (0x8D)
for reg in 0x8b 0x8c 0x8d; do
  sshpass -p '0penBmc' ssh root@192.168.88.13 "i2cget -y 2 0x10 $reg w" 2>/dev/null
done

sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

Write findings to `notes/2026-04-09-vrm-telemetry-research.md` in the devel repo.

- [ ] **Step 2: Add VRM device constants and LINEAR11 decoder**

After the power sequencer code in `wedge100s-bmc-daemon.c`:

```c
/* Infineon IR3581/IR3584 VRMs on BMC_I2C_2.
 * PMBus: READ_VOUT (0x8B), READ_IOUT (0x8C), READ_TEMPERATURE_1 (0x8D).
 * VOUT uses LINEAR16 (exponent from VOUT_MODE 0x20).
 * IOUT and TEMP use LINEAR11 (5-bit exponent + 11-bit mantissa).
 */
#define VRM_BUS  2

struct vrm_info {
    int addr;
    const char *name;
    int vout_exp;  /* VOUT_MODE exponent (set from hardware probe) */
};

static struct vrm_info vrms[] = {
    { 0x10, "core",   -12 },  /* IR3581: Tomahawk 1.0V core (6-phase) */
    { 0x12, "analog", -12 },  /* IR3584: 1.0V analog (2-phase) */
    { 0x14, "3v3",    -12 },  /* IR3584: 3.3V main (2-phase) */
};
#define NUM_VRMS (sizeof(vrms) / sizeof(vrms[0]))

/**
 * @brief Decode PMBus LINEAR11 value to milliunit.
 *
 * LINEAR11 format: bits[15:11] = signed 5-bit exponent,
 * bits[10:0] = signed 11-bit mantissa. Result = mantissa * 2^exponent.
 *
 * @param raw  16-bit LINEAR11 value.
 * @return Value in milliunit (milliamps for current, millidegrees for temp).
 */
static int linear11_to_milli(int raw)
{
    int exp = (raw >> 11) & 0x1f;
    int mantissa = raw & 0x7ff;

    if (exp > 15) exp -= 32;
    if (mantissa > 1023) mantissa -= 2048;

    if (exp >= 0)
        return mantissa * (1 << exp) * 1000;
    else
        return (mantissa * 1000) >> (-exp);
}
```

- [ ] **Step 3: Add VRM poll function and integrate into main loop**

```c
/**
 * @brief Poll all VRM telemetry and write cache files.
 *
 * For each VRM: read output voltage (mV), output current (mA),
 * and die temperature (millidegrees C). Write to /run/wedge100s/vrm_*.
 */
static void poll_vrm_telemetry(void)
{
    for (int i = 0; i < (int)NUM_VRMS; i++) {
        char cmd[256];
        int raw, val;

        /* READ_VOUT (0x8B): LINEAR16 */
        snprintf(cmd, sizeof(cmd),
                 "i2cget -y %d 0x%02x 0x8b w", VRM_BUS, vrms[i].addr);
        raw = bmc_read_int(cmd, 0);
        if (raw >= 0) {
            val = (raw * 1000) >> (-vrms[i].vout_exp);
            char path[128];
            snprintf(path, sizeof(path),
                     RUN_DIR "/vrm_%s_vout_mv", vrms[i].name);
            write_file(path, val);
        }

        /* READ_IOUT (0x8C): LINEAR11 → milliamps */
        snprintf(cmd, sizeof(cmd),
                 "i2cget -y %d 0x%02x 0x8c w", VRM_BUS, vrms[i].addr);
        raw = bmc_read_int(cmd, 0);
        if (raw >= 0) {
            val = linear11_to_milli(raw);
            char path[128];
            snprintf(path, sizeof(path),
                     RUN_DIR "/vrm_%s_iout_ma", vrms[i].name);
            write_file(path, val);
        }

        /* READ_TEMPERATURE_1 (0x8D): LINEAR11 → millidegrees C */
        snprintf(cmd, sizeof(cmd),
                 "i2cget -y %d 0x%02x 0x8d w", VRM_BUS, vrms[i].addr);
        raw = bmc_read_int(cmd, 0);
        if (raw >= 0) {
            val = linear11_to_milli(raw);
            char path[128];
            snprintf(path, sizeof(path),
                     RUN_DIR "/vrm_%s_temp_mc", vrms[i].name);
            write_file(path, val);
        }
    }
}
```

In the main poll loop: `poll_vrm_telemetry();`

- [ ] **Step 4: Run wedge100s-doc-check — verify Doxygen headers**

- [ ] **Step 5: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 6: Commit, push, merge to master**

```bash
cd /export/sonic/sonic-buildimage
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c
git commit -m "feat(bmc): add IR3581/IR3584 VRM telemetry

Read output voltage (mV), output current (mA), and die temperature
(millidegrees C) from three VRMs on BMC_I2C_2: IR3581 core (0x10),
IR3584 analog (0x12), IR3584 3.3V (0x14). Write to /run/wedge100s/vrm_*.

Closes: GAP-022"
git push origin wedge100s/i2c-bmc-sysfs

# Merge Tasks 1+2 to master together
git checkout master
git merge origin/wedge100s/i2c-bmc-sysfs --no-edit
git push origin master
```

Invoke `wedge100s-build-verify` skill to confirm clean build on master.

- [ ] **Step 7: Append VRM tests to `tests/stage_03_platform/test_power_telemetry.py`**

Add to the bottom of the file created in Task 1 Step 8:

```python
# ── GAP-022: IR3581/IR3584 VRM telemetry ──────────────────────────────────

VRMS = {
    "core":   {"vout": (750, 1200),  "iout_max": 170000, "temp_max": 125000},
    "analog": {"vout": (800, 1200),  "iout_max": 60000,  "temp_max": 125000},
    "3v3":    {"vout": (2640, 3960), "iout_max": 60000,  "temp_max": 125000},
}


def test_vrm_vout_files_exist(ssh):
    """VRM output voltage files should be present."""
    missing = []
    for name in VRMS:
        path = f"{RUN_DIR}/vrm_{name}_vout_mv"
        out, _, _ = ssh.run(f"test -f {path} && echo YES || echo NO", timeout=10)
        if "YES" not in out:
            missing.append(name)
    assert not missing, f"Missing VRM vout files: {missing}"


def test_vrm_vout_reasonable(ssh):
    """VRM output voltages should be within expected range."""
    for name, spec in VRMS.items():
        path = f"{RUN_DIR}/vrm_{name}_vout_mv"
        out, _, rc = ssh.run(f"cat {path} 2>/dev/null", timeout=10)
        if rc != 0:
            continue
        mv = int(out.strip())
        lo, hi = spec["vout"]
        print(f"  {name}: {mv} mV (expected {lo}-{hi})")
        assert lo <= mv <= hi, f"{name}: {mv} mV outside {lo}-{hi}"


def test_vrm_iout_reasonable(ssh):
    """VRM output current should be non-negative and below max."""
    for name, spec in VRMS.items():
        path = f"{RUN_DIR}/vrm_{name}_iout_ma"
        out, _, rc = ssh.run(f"cat {path} 2>/dev/null", timeout=10)
        if rc != 0:
            continue
        ma = int(out.strip())
        print(f"  {name}: {ma} mA (max {spec['iout_max']})")
        assert 0 <= ma <= spec["iout_max"], (
            f"{name}: {ma} mA outside range 0-{spec['iout_max']}"
        )


def test_vrm_temp_reasonable(ssh):
    """VRM die temperature should be 0-125 C (reported in millidegrees)."""
    for name, spec in VRMS.items():
        path = f"{RUN_DIR}/vrm_{name}_temp_mc"
        out, _, rc = ssh.run(f"cat {path} 2>/dev/null", timeout=10)
        if rc != 0:
            continue
        mc = int(out.strip())
        print(f"  {name}: {mc/1000:.1f} C (max {spec['temp_max']/1000:.0f})")
        assert 0 <= mc <= spec["temp_max"], (
            f"{name}: {mc} mc outside range 0-{spec['temp_max']}"
        )
```

- [ ] **Step 8: Update `tests/lib/report.py` — add power telemetry to `report_platform()`**

Locate the `report_platform()` function and append a power telemetry section. Add a helper that reads all `vrail_*_mv` and `vrm_*_*` files from `/run/wedge100s/` and prints them in a table:

```python
    # ── Power telemetry (GAP-021, GAP-022) ──────────────────────────────
    # Read vrail_*_mv files
    out, _, rc = ssh.run(
        "for f in /run/wedge100s/vrail_*_mv; do "
        "echo \"$(basename $f .mv | sed 's/^vrail_//')=$(cat $f)\"; "
        "done 2>/dev/null", timeout=10)
    if rc == 0 and out.strip():
        rail_rows = []
        for line in out.strip().split('\n'):
            if '=' in line:
                name, val = line.split('=', 1)
                rail_rows.append((name.replace('_mv', ''), f"{val} mV"))
        if rail_rows:
            _table(["Rail", "Voltage"], rail_rows,
                   title="Power Sequencer Rails (PWR1014A)")

    # Read vrm_*_vout_mv files
    out, _, rc = ssh.run(
        "for f in /run/wedge100s/vrm_*_vout_mv; do "
        "n=$(basename $f _vout_mv | sed 's/^vrm_//'); "
        "v=$(cat $f); i=$(cat /run/wedge100s/vrm_${n}_iout_ma 2>/dev/null || echo -); "
        "t=$(cat /run/wedge100s/vrm_${n}_temp_mc 2>/dev/null || echo -); "
        "echo \"$n=$v=$i=$t\"; done 2>/dev/null", timeout=10)
    if rc == 0 and out.strip():
        vrm_rows = []
        for line in out.strip().split('\n'):
            parts = line.split('=')
            if len(parts) == 4:
                name, mv, ma, mc = parts
                vrm_rows.append((name, f"{mv} mV", f"{ma} mA",
                                 f"{int(mc)//1000} C" if mc != '-' else '-'))
        if vrm_rows:
            _table(["VRM", "Voltage", "Current", "Temp"], vrm_rows,
                   title="VRM Telemetry (IR3581/IR3584)")
```

- [ ] **Step 9: Run tests on hardware and commit devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_03_platform/test_power_telemetry.py -v
./run_tests.py --report stage_03_platform

git add tests/stage_03_platform/test_power_telemetry.py \
        tests/lib/report.py \
        notes/2026-04-09-vrm-telemetry-research.md
git commit -m "test(platform): add VRM telemetry tests and power reporter

Cover GAP-022 (IR3581/IR3584 VRM monitoring) in stage_03_platform.
Update report_platform() to display power sequencer and VRM data."
```

---

### Task 3: Add QSFP per-port hardware reset via bmc-daemon

**Gap:** GAP-026
**Topic branch:** `wedge100s/sfp-optics` (owns `sfp.py`), plus `wedge100s/i2c-bmc-sysfs` (owns `bmc-daemon.c`)
**Files:**
- Modify: `platform/.../utils/wedge100s-bmc-daemon.c` (on `wedge100s/i2c-bmc-sysfs`)
- Modify: `platform/.../sonic_platform/sfp.py` (on `wedge100s/sfp-optics`)

Since this change touches files owned by two branches, it requires two separate commits on two branches per workflow rule #4 (do not cross-contaminate).

- [ ] **Step 1: Identify CPLD QSFP reset registers on hardware**

```bash
ssh admin@192.168.88.12
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

# Read candidate CPLD registers 0x34-0x37 via BMC (CPLD at 0x31 on BMC_I2C_12)
for reg in 0x34 0x35 0x36 0x37; do
  val=$(sshpass -p '0penBmc' ssh root@192.168.88.13 \
    "i2cget -y 12 0x31 $reg" 2>/dev/null)
  echo "Register $reg: $val"
done
# All bits should be 0xFF (active-low reset, deasserted = 1).

sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

Write findings to `notes/2026-04-09-qsfp-reset-registers.md` in the devel repo.

- [ ] **Step 2: Add QSFP reset to bmc-daemon (on wedge100s/i2c-bmc-sysfs)**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/i2c-bmc-sysfs
git merge origin/master --no-edit
```

Add the reset handler to `wedge100s-bmc-daemon.c`:

```c
/* QSFP reset registers in CPLD (BMC_I2C_12, CPLD at 0x31).
 * 4 registers × 8 bits = 32 ports.
 * Bit = 0: reset asserted (active-low). Bit = 1: normal.
 * (update QSFP_RST_REG_BASE from Step 1 hardware probe)
 */
#define QSFP_RST_BMC_BUS   12
#define QSFP_RST_CPLD_ADDR 0x31
#define QSFP_RST_REG_BASE  0x34  /* update from Step 1 */

/**
 * @brief Assert and deassert hardware reset on one QSFP port.
 *
 * Active-low: write 0 to assert, wait 100ms, write 1 to deassert.
 * The 100ms hold time exceeds the SFF-8636 minimum of 2ms.
 *
 * @param port  0-based port number (0-31).
 * @return 0 on success, -1 on failure.
 */
static int qsfp_hw_reset(int port)
{
    if (port < 0 || port >= 32) return -1;

    int reg = QSFP_RST_REG_BASE + (port / 8);
    int bit = port % 8;
    char cmd[256];

    snprintf(cmd, sizeof(cmd),
             "i2cget -y %d 0x%02x 0x%02x",
             QSFP_RST_BMC_BUS, QSFP_RST_CPLD_ADDR, reg);
    int cur = bmc_read_int(cmd, 0);
    if (cur < 0) return -1;

    int asserted = cur & ~(1 << bit);
    snprintf(cmd, sizeof(cmd),
             "i2cset -y %d 0x%02x 0x%02x 0x%02x",
             QSFP_RST_BMC_BUS, QSFP_RST_CPLD_ADDR, reg, asserted);
    bmc_run(cmd);

    usleep(100000); /* 100ms reset hold */

    int deasserted = cur | (1 << bit);
    snprintf(cmd, sizeof(cmd),
             "i2cset -y %d 0x%02x 0x%02x 0x%02x",
             QSFP_RST_BMC_BUS, QSFP_RST_CPLD_ADDR, reg, deasserted);
    bmc_run(cmd);

    return 0;
}
```

Add inotify handler for `sfp_N_reset_req` files (same pattern as existing lpmode request handling — writes `done`/`fail` to `sfp_N_reset_ack`).

Run `wedge100s-doc-check`, build, commit, push:

```bash
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c
git commit -m "feat(bmc): add QSFP per-port hardware reset via CPLD

Handle sfp_N_reset_req inotify events by asserting/deasserting CPLD
QSFP_RST_N[N] for 100ms via BMC I2C. Write result to sfp_N_reset_ack.

Closes: GAP-026 (daemon side)"
git push origin wedge100s/i2c-bmc-sysfs
git checkout master && git merge origin/wedge100s/i2c-bmc-sysfs --no-edit && git push origin master
```

Invoke `wedge100s-build-verify` skill to confirm daemon build on i2c-bmc-sysfs changes before switching branches.

- [ ] **Step 3: Update sfp.py reset() (on wedge100s/sfp-optics)**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/sfp-optics
git merge origin/master --no-edit
```

Replace the `reset()` method in `sonic_platform/sfp.py`:

```python
    _RESET_REQ_PATH = '/run/wedge100s/sfp_{}_reset_req'
    _RESET_ACK_PATH = '/run/wedge100s/sfp_{}_reset_ack'
    _RESET_TIMEOUT_S = 5

    def reset(self):
        """Hardware reset this QSFP module via CPLD QSFP_RST_N line.

        Writes a request file that the bmc-daemon picks up via inotify,
        which asserts/deasserts the CPLD reset line for 100ms. Waits
        up to 5 seconds for acknowledgment.

        Returns:
            bool: True if reset completed, False on timeout or error.
        """
        import time

        req_path = self._RESET_REQ_PATH.format(self._port)
        ack_path = self._RESET_ACK_PATH.format(self._port)

        try:
            os.remove(ack_path)
        except OSError:
            pass

        try:
            with open(req_path, 'w') as f:
                f.write('1')
        except OSError:
            return False

        deadline = time.monotonic() + self._RESET_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                with open(ack_path) as f:
                    result = f.read().strip()
                if result == 'done':
                    return True
                if result == 'fail':
                    return False
            except OSError:
                pass
            time.sleep(0.1)

        return False
```

Run `wedge100s-doc-check`, commit, push, merge:

```bash
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/sfp.py
git commit -m "feat(sfp): implement QSFP hardware reset via daemon request

Sfp.reset() writes /run/wedge100s/sfp_N_reset_req and polls for ack.
Replaces the previous stub that returned False.

Closes: GAP-026 (Python API side)"
git push origin wedge100s/sfp-optics
git checkout master && git merge origin/wedge100s/sfp-optics --no-edit && git push origin master
```

Invoke `wedge100s-build-verify` skill.

- [ ] **Step 4: Write test — `tests/stage_07_qsfp/test_qsfp_reset.py`**

```python
"""Stage 07 supplement — QSFP per-port hardware reset.

GAP-026: Verify that sfp.reset() triggers a CPLD reset cycle and the
optic re-initializes. Test on one populated port with no production traffic.
"""

import json
import time
import pytest

RESET_CAPTURE = """\
import json, time
from sonic_platform.platform import Platform
chassis = Platform().get_chassis()
sfps = chassis.get_all_sfps()
port = {port}
sfp = sfps[port]
print(json.dumps({{
    "present_before": sfp.get_presence(),
    "reset_result": sfp.reset(),
}}))
"""

RUN_DIR = "/run/wedge100s"
NUM_PORTS = 32


def _find_populated_port(ssh):
    """Return first populated port index, or None."""
    for port in range(NUM_PORTS):
        out, _, rc = ssh.run(
            f"cat {RUN_DIR}/sfp_{port}_present 2>/dev/null", timeout=5)
        if rc == 0 and out.strip() == '1':
            return port
    return None


def test_qsfp_reset_populated_port(ssh):
    """Reset a populated port and verify it comes back present."""
    port = _find_populated_port(ssh)
    if port is None:
        pytest.skip("No populated QSFP port found")

    script = RESET_CAPTURE.format(port=port)
    out, err, rc = ssh.run_python(script, timeout=30)
    assert rc == 0, f"Reset script failed (rc={rc}): {err}"
    result = json.loads(out)
    assert result["present_before"], f"Port {port} not present before reset"
    assert result["reset_result"], f"Port {port} reset returned False"

    # Wait for module to re-initialize (SFF-8636: 2s max).
    time.sleep(3)

    out2, _, _ = ssh.run(f"cat {RUN_DIR}/sfp_{port}_present", timeout=10)
    assert out2.strip() == '1', f"Port {port} not present after reset"
    print(f"  Port {port}: reset OK, re-initialized")
```

- [ ] **Step 5: Update reporter — add reset capability to `report_qsfp()`**

In `tests/lib/report.py`, find `report_qsfp()` and add a line reporting whether `sfp.reset()` is functional (check for `sfp_0_reset_ack` file existence as a proxy).

- [ ] **Step 6: Run test and commit devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_07_qsfp/test_qsfp_reset.py -v

git add tests/stage_07_qsfp/test_qsfp_reset.py \
        tests/lib/report.py \
        notes/2026-04-09-qsfp-reset-registers.md
git commit -m "test(qsfp): add QSFP hardware reset test

Cover GAP-026 (per-port reset via CPLD) in stage_07_qsfp.
Validates reset request/ack protocol and optic re-initialization."
```

---

### Task 4: Enable per-port CL73 autonegotiation

**Gap:** GAP-027
**Topic branch:** `wedge100s/chipset-config`
**Files:**
- Modify: `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm`

- [ ] **Step 1: Checkout topic branch and sync**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/chipset-config
git merge origin/master --no-edit
```

- [ ] **Step 2: Test CL73 autoneg via BCM diag shell**

Requires connection to Arista EOS peer (192.168.88.14). Identify a connected port pair.

```bash
ssh admin@192.168.88.12
docker exec -it syncd bash

# Test on a connected port (example: Ethernet16 = BCM port ce0)
bcmcmd 'port ce0 autoneg=on an=cl73'
sleep 10
bcmcmd 'port ce0 status'

# If link up, run PRBS error check
bcmcmd 'phy ce0 prbs set mode=phy polynomial=p31 invert=0'
sleep 5
bcmcmd 'phy ce0 prbs get'
bcmcmd 'phy ce0 prbs clear'

# Restore fixed mode
bcmcmd 'port ce0 autoneg=off speed=100000'
exit
```

Write findings to `notes/2026-04-09-autoneg-testing.md` in the devel repo.

- [ ] **Step 3: Update BCM config (only if Step 2 passes)**

Change in `th-wedge100s-32x-flex.config.bcm`:

```
phy_an_c73=0x0
```
to:
```
# CL73 autoneg: globally enabled but ports default to forced speed.
# Per-port AN enabled at runtime: config interface autoneg EthernetN enabled
# Tested on hardware: 2026-04-09 (update date after verification).
phy_an_c73=0x1
```

If Step 2 shows instability, do NOT change. Document failures in notes and close gap as "deferred."

- [ ] **Step 4: Build verify, commit, push, merge**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
git add device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm
git commit -m "feat(chipset): enable per-port CL73 autonegotiation

Change phy_an_c73 from 0x0 (globally disabled) to 0x1 (globally
enabled). Ports default to forced speed; per-port AN enabled via
'config interface autoneg' at runtime.

Closes: GAP-027"
git push origin wedge100s/chipset-config
git checkout master && git merge origin/wedge100s/chipset-config --no-edit && git push origin master
```

Invoke `wedge100s-build-verify` skill.

- [ ] **Step 5: Write test — `tests/stage_15_autoneg_fec/test_autoneg_cl73.py`**

This goes into the existing `stage_15_autoneg_fec` directory which already has `conftest.py` and `test_autoneg_fec.py`:

```python
"""Stage 15 supplement — CL73 autonegotiation interop test.

GAP-027: Verify CL73 autoneg can be enabled per-port and successfully
negotiates with the Arista EOS peer.
"""

import time
import pytest

# Port connected to Arista peer (update from lab topology).
AUTONEG_PORT = "Ethernet16"
LINK_WAIT_S = 30


def test_cl73_enable_negotiate(ssh):
    """Enable CL73 on a connected port and verify link comes up."""
    ssh.run(
        f"sudo config interface autoneg {AUTONEG_PORT} enabled", timeout=10)
    ssh.run(
        f"sudo config interface advertised-speeds {AUTONEG_PORT} 100000",
        timeout=10)

    deadline = time.time() + LINK_WAIT_S
    link_up = False
    while time.time() < deadline:
        out, _, _ = ssh.run(
            f"show interfaces status {AUTONEG_PORT} | tail -1", timeout=10)
        if "up" in out.lower():
            link_up = True
            break
        time.sleep(2)

    assert link_up, (
        f"{AUTONEG_PORT}: link did not come up with CL73 autoneg "
        f"within {LINK_WAIT_S}s"
    )
    print(f"  {AUTONEG_PORT}: link UP with CL73 autoneg")


def test_cl73_disable_restore(ssh):
    """Disable autoneg and verify fixed-speed link restores."""
    ssh.run(
        f"sudo config interface autoneg {AUTONEG_PORT} disabled", timeout=10)
    ssh.run(
        f"sudo config interface speed {AUTONEG_PORT} 100000", timeout=10)

    time.sleep(10)
    out, _, _ = ssh.run(
        f"show interfaces status {AUTONEG_PORT} | tail -1", timeout=10)
    assert "up" in out.lower(), (
        f"{AUTONEG_PORT}: fixed-speed link did not restore after "
        "disabling autoneg"
    )
```

- [ ] **Step 6: Run test and commit devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_15_autoneg_fec/test_autoneg_cl73.py -v

git add tests/stage_15_autoneg_fec/test_autoneg_cl73.py \
        notes/2026-04-09-autoneg-testing.md
git commit -m "test(autoneg): add CL73 autoneg interop test

Cover GAP-027 (CL73 autoneg) in stage_15_autoneg_fec.
Tests enable/disable cycle with Arista EOS peer."
```

---

### Task 5: Complete LED breakout-mode lane mapping

**Gap:** GAP-028
**Topic branch:** `wedge100s/led-pipeline`
**Files:**
- Modify: `platform/.../utils/wedge100s-ledup-linkstate`

- [ ] **Step 1: Checkout topic branch and sync**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/led-pipeline
git merge origin/master --no-edit
```

- [ ] **Step 2: Understand current breakout handling**

Read the full `wedge100s-ledup-linkstate` daemon (380 lines) and check how it currently maps interfaces to LED ports. Key question: does `_IFACE_TO_LED_PORT` handle breakout sub-ports?

```bash
grep -n 'breakout\|sub.*port\|Ethernet[0-9]*[1-3]\b' \
  platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-ledup-linkstate
```

- [ ] **Step 3: Add lane-aware LED encoding**

Add breakout-aware mapping and state aggregation to the daemon:

```python
def _iface_to_led_port(iface):
    """Map any interface (native or breakout sub-port) to LED port.

    Native:  Ethernet16 → led_port 1
    Breakout: Ethernet16..19 → led_port 1

    LED port = (first_serdes_of_parent - 1) / 4.
    Parent = Ethernet number rounded down to nearest multiple of 4.

    Args:
        iface: SONiC interface name (e.g., 'Ethernet16', 'Ethernet17').

    Returns:
        int or None: LED port index (0-31), or None if not mappable.
    """
    if not iface.startswith('Ethernet'):
        return None
    try:
        idx = int(iface[8:])
    except ValueError:
        return None
    parent_idx = (idx // 4) * 4
    parent_iface = f'Ethernet{parent_idx}'
    return _IFACE_TO_LED_PORT.get(parent_iface)


def _aggregate_led_states(iface_states):
    """Aggregate per-interface oper_status into per-LED-port state byte.

    All lanes up → 0x80 (solid color).
    Partial (some up, some down) → 0x81 (link + blink flag).
    All lanes down → 0x00 (dark).

    Args:
        iface_states: dict mapping interface name to oper_status string.

    Returns:
        dict: {led_port: state_byte}
    """
    led_counts = {}  # {led_port: [total_sub, up_count]}

    for iface, oper in iface_states.items():
        led_port = _iface_to_led_port(iface)
        if led_port is None:
            continue
        if led_port not in led_counts:
            led_counts[led_port] = [0, 0]
        led_counts[led_port][0] += 1
        if oper == 'up':
            led_counts[led_port][1] += 1

    led_states = {}
    for led_port, (total, up) in led_counts.items():
        if up == 0:
            led_states[led_port] = 0x00
        elif up == total:
            led_states[led_port] = 0x80
        else:
            led_states[led_port] = 0x81  # partial: link + blink
    return led_states
```

Replace the per-interface state update in the main poll loop with `_aggregate_led_states()`.

- [ ] **Step 4: Run wedge100s-doc-check, build verify, commit, push, merge**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-ledup-linkstate
git commit -m "feat(led): add breakout-mode lane-aware LED encoding

Aggregate sub-port link states into per-LED-port state byte.
All lanes up → solid. Partial → blink. All down → dark.
Handles 1×100G, 2×50G, 4×25G, and 4×10G breakout modes.

Closes: GAP-028"
git push origin wedge100s/led-pipeline
git checkout master && git merge origin/wedge100s/led-pipeline --no-edit && git push origin master
```

Invoke `wedge100s-build-verify` skill.

- [ ] **Step 5: Write test — `tests/stage_08_led/test_led_breakout.py`**

```python
"""Stage 08 supplement — LED breakout-mode lane mapping.

GAP-028: Verify that LEDs correctly reflect per-lane link state in
breakout modes. Requires at least one port configured for breakout.
"""

import pytest

RUN_DIR = "/run/wedge100s"


def _find_breakout_parent(ssh):
    """Find a 4×25G breakout parent port. Return parent Ethernet index or None."""
    out, _, _ = ssh.run(
        "show interfaces status | grep -oP 'Ethernet\\d+' | sort -t n -k 2n",
        timeout=10)
    ifaces = set(out.strip().split('\n'))
    for idx in range(0, 128, 4):
        expected = [f'Ethernet{idx+j}' for j in range(4)]
        if all(e in ifaces for e in expected):
            return idx
    return None


def test_led_breakout_port_detected(ssh):
    """At least one 4×25G breakout port should be configured."""
    parent = _find_breakout_parent(ssh)
    if parent is None:
        pytest.skip("No 4×25G breakout port found — configure one to test GAP-028")
    print(f"  Breakout parent: Ethernet{parent}")


def test_led_breakout_all_up_solid(ssh):
    """In breakout mode with all lanes up, LEDUP1 should show 0x80 (solid)."""
    parent = _find_breakout_parent(ssh)
    if parent is None:
        pytest.skip("No 4×25G breakout port found")

    # Check link status of all 4 sub-ports
    all_up = True
    for j in range(4):
        out, _, _ = ssh.run(
            f"show interfaces status Ethernet{parent+j} | tail -1", timeout=10)
        if "up" not in out.lower():
            all_up = False
            break

    if not all_up:
        pytest.skip(f"Not all sub-ports of Ethernet{parent} are link-up")

    # Read LEDUP1 state file for this LED port
    led_port = parent // 4  # approximate mapping
    out, _, rc = ssh.run(
        f"cat {RUN_DIR}/ledup1_port_{led_port} 2>/dev/null", timeout=10)
    if rc != 0:
        pytest.skip(f"ledup1_port_{led_port} not found")
    val = out.strip()
    print(f"  Ethernet{parent} (LED port {led_port}): ledup1={val}")
    assert val == '1', (
        f"All 4 sub-ports UP but LEDUP1 not showing link-up state"
    )
```

- [ ] **Step 6: Run test and commit devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_08_led/test_led_breakout.py -v

git add tests/stage_08_led/test_led_breakout.py
git commit -m "test(led): add LED breakout-mode lane mapping test

Cover GAP-028 in stage_08_led. Validates LED state aggregation
for 4×25G breakout port groups."
```

---

### Task 6: Configure Tomahawk Eagle Core management port

**Gap:** GAP-024
**Topic branch:** `wedge100s/chipset-config`
**Files:**
- Modify: `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm`

- [ ] **Step 1: Checkout topic branch and sync**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/chipset-config
git merge origin/master --no-edit
```

- [ ] **Step 2: Research Eagle Core port via BCM diag shell**

```bash
ssh admin@192.168.88.12
docker exec -it syncd bash
bcmcmd 'port mng status'
bcmcmd 'ps all'
exit
```

Also check AS7712 BCM config for reference:

```bash
grep -i 'eagle\|mng\|management' \
  /export/sonic/sonic-buildimage/device/accton/x86_64-accton_as7712_32x-r0/*/th-*.config.bcm
```

Write findings to `notes/2026-04-09-eagle-core-research.md` in the devel repo.

- [ ] **Step 3: Add Eagle Core port to BCM config (only if research shows it's viable)**

Typical entry:

```
# Eagle Core 10G management port — BCM5387 P1 via SGMII.
# OCP spec v1.3 Section 7.5: "wired and reserved for future."
portmap_66.0=129:10
```

**Decision gate:** If BCM diag shows no management port or SGMII link fails to come up, close this gap as "deferred — requires BCM5387 configuration not exposed via SDK." Document in notes.

- [ ] **Step 4: Build, commit, push, merge (only if proceeding)**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
git add device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm
git commit -m "feat(chipset): configure Tomahawk Eagle Core management port

Add portmap entry for Eagle Core 10G SGMII port connecting to BCM5387
management switch P1.

Closes: GAP-024"
git push origin wedge100s/chipset-config
git checkout master && git merge origin/wedge100s/chipset-config --no-edit && git push origin master
```

- [ ] **Step 5: Commit research notes in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add notes/2026-04-09-eagle-core-research.md
git commit -m "docs: Eagle Core management port research notes (GAP-024)"
```

No new test file needed — if the port comes up, it will appear in existing `stage_03_platform` tests via `ip link show`.

---

### Task 7: Investigate TPM integration

**Gap:** GAP-023
**Topic branch:** `wedge100s/security` (new branch — create only if proceeding past research)
**Files:** None initially — this is an investigation-first task.

- [ ] **Step 1: Verify TPM accessibility from BMC and host**

```bash
ssh admin@192.168.88.12
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

# Probe BMC I2C bus 10
sshpass -p '0penBmc' ssh root@192.168.88.13 'i2cdetect -y 10' 2>/dev/null

# Check host-side TPM
ls -la /dev/tpm* 2>/dev/null
ls -la /sys/class/tpm/ 2>/dev/null
dmesg | grep -i tpm

sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

- [ ] **Step 2: Document findings**

Write to `notes/2026-04-09-tpm-investigation.md` in the devel repo:

1. Is TPM accessible from BMC? Which address?
2. Is it SLB9645 (TPM 1.2) or SLB9660 (TPM 2.0)?
3. Is it accessible from host? If BMC-only, note that.
4. SONiC 202511 requires TPM 2.0 — if 1.2, integration is limited.

**Decision gate:** If BMC-only and TPM 1.2, close gap as "deferred — hardware limitation." If TPM 2.0 and host-accessible, create `wedge100s/security` branch and proceed with kernel module loading.

- [ ] **Step 3: Create topic branch (only if proceeding)**

```bash
cd /export/sonic/sonic-buildimage
git checkout master
git checkout -b wedge100s/security
# Add module loading to platform-init if host-side TPM is available
git push -u origin wedge100s/security
```

- [ ] **Step 4: Commit research notes in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add notes/2026-04-09-tpm-investigation.md
git commit -m "docs: TPM integration investigation (GAP-023)"
```

---

### Task 8: Update system_health_monitoring_config.json

**Gap:** GAP-045
**Prerequisite:** Tasks 1 and 2 deployed and working.
**Topic branch:** `wedge100s/device-identity`
**Files:**
- Modify: `device/accton/x86_64-accton_wedge100s_32x-r0/system_health_monitoring_config.json`

- [ ] **Step 1: Checkout topic branch and sync**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/device-identity
git merge origin/master --no-edit
```

- [ ] **Step 2: Read current config and identify PSU ignore entries**

```bash
cat device/accton/x86_64-accton_wedge100s_32x-r0/system_health_monitoring_config.json
```

Remove entries that ignore PSU voltage, temperature, and fan speed monitoring — these were workarounds for missing telemetry.

- [ ] **Step 3: Build, test, commit, push, merge**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
git add device/accton/x86_64-accton_wedge100s_32x-r0/system_health_monitoring_config.json
git commit -m "fix(device): remove PSU sensor ignores from health monitoring

Now that PSU telemetry is available (GAP-016, GAP-021), remove the
workaround ignore entries so system-health reports PSU data.

Closes: GAP-045"
git push origin wedge100s/device-identity
git checkout master && git merge origin/wedge100s/device-identity --no-edit && git push origin master
```

Invoke `wedge100s-build-verify` skill. Then deploy and verify `show system-health summary` includes PSU sensor data.
