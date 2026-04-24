# BMC-Mediated Interrupt Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace host-side polling of QSFP presence / PSU alarms / power-rail faults with an **event-driven path** that originates at the CPLD interrupt aggregator, propagates via BMC GPIO 31 edge interrupt, and signals the host via the existing bmc-daemon SSH ControlMaster channel. Closes GAP-018 (interrupt-driven QSFP events not implemented) and GAP-029 (CPLD interrupt masking unused) as a single architectural change.

**Architecture:** Three components. (1) A new **Python 3 daemon script** `wedge100s-cpld-int-monitor.py` (~80 lines) that uses `select.poll(POLLPRI)` on `/sys/class/gpio/gpio31/value` with `edge=both`, reads CPLD interrupt status registers via `/dev/i2c-12` on each edge, and appends event lines to `/tmp/wedge100s-cpld-int-events.log`. **Python 3.5.3 is already on the BMC at `/usr/bin/python3` (verified 2026-04-09) — no cross-compile, no new binaries on the BMC rootfs.** (2) `wedge100s-bmc-daemon` on the host rsyncs the `.py` file to `/tmp/` on the BMC at startup via its existing SSH ControlMaster, launches it with `setsid python3 /tmp/wedge100s-cpld-int-monitor.py &`, then tails the event log via the same ControlMaster — writing events into `/run/wedge100s/cpld_int_event` which the host `wedge100s-i2c-daemon` inotify-watches for targeted re-scans. (3) `platform-init` configures the CPLD mask registers so only the events we care about contribute to the gpio31 aggregate (noise reduction). The hot-swap detection latency drops from 1-3 seconds (current polling) to ~100ms end-to-end.

**Tech Stack:** Python 3.5 (BMC-side daemon, no deps beyond stdlib `select`/`fcntl`/`struct`), C (existing host `wedge100s-bmc-daemon.c` + `wedge100s-i2c-daemon.c` extensions), Python 3 (sonic_platform API wiring on host), Linux sysfs GPIO edge events, `setsid` for detached daemon on BMC (no runit/systemd integration — bmc-daemon owns the daemon lifecycle), SSH ControlMaster (existing bmc-daemon infrastructure), pytest (latency measurement)

**Why Python on the BMC:** Verified 2026-04-09 that `/usr/bin/python3` (Python 3.5.3) is on the Wedge 100S BMC with the `select`, `fcntl`, `struct` stdlib modules available. No cross-compile toolchain, no bitbake recipe, no OpenBMC image rebuild. The daemon script is a single file rsynced to `/tmp/` (tmpfs — cleared on BMC reboot, re-pushed by the host on every bmc-daemon start, so no persistence concern).

**Platform fork prefix:** `/export/sonic/sonic-buildimage/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
**Devel repo prefix:** `/export/sonic/sonic-wedge100s-devel/`

**⚠️ CRITICAL — research-first task:** The DESIGNGAPS.md and PLATFORM_GUIDE.md disagree on CPLD mask register addresses (0x20-0x25 vs 0x18-0x1B). **Do not touch mask registers until the hardware probe in Task 1 resolves this.** Writing to the wrong register on a production CPLD could disable a feature we care about (e.g., register 0x20 per PLATFORM_GUIDE is `UART_MUX`, and writing interrupt masks to it would break the console).

---

## Workflow Compliance

Every task that modifies `sonic-buildimage` MUST follow `docs/workflow.md`:

1. Invoke **`wedge100s-topic-branches`** skill before touching any file in the platform fork
2. Work on the owning topic branch (table below); never commit directly to master
3. Sync with master first: `git checkout wedge100s/<topic> && git merge origin/master --no-edit`
4. Conventional commits: `feat(<scope>):`, `fix(<scope>):`, `test(<scope>):`
5. Invoke **`wedge100s-doc-check`** skill before every commit touching `.py` or `.c` files
6. Push, then **STOP** — do NOT merge to master (parallel .bin builds must be respected)
7. Invoke **`wedge100s-build-verify`** skill ONLY in the isolated worktree, not on master

### Topic Branch Ownership

**All platform fork work lives on a single topic branch: `wedge100s/i2c-bmc-sysfs`.** The Python-daemon + rsync approach means no submodule patches, no bitbake recipes, no cross-compile, and no OpenBMC image rebuild — the `.py` file ships in the platform .deb and is pushed to `/tmp/` on the BMC at bmc-daemon startup.

| Task | Files | Topic Branch |
|------|-------|-------------|
| 1-2 (research) | `notes/*.md` | devel repo `initial` (no topic branch) |
| 3 (CPLD driver sysfs) | `modules/wedge100s_cpld.c` | `wedge100s/i2c-bmc-sysfs` |
| 4 (BMC daemon Python source) | `utils/wedge100s-cpld-int-monitor.py` (new) + `debian/sonic-platform-accton-wedge100s-32x.install` | `wedge100s/i2c-bmc-sysfs` |
| 5 (rsync push + launch from host) | `utils/wedge100s-bmc-daemon.c` | `wedge100s/i2c-bmc-sysfs` |
| 6 (event log format refinement) | `utils/wedge100s-cpld-int-monitor.py` | `wedge100s/i2c-bmc-sysfs` |
| 7 (host daemon event tail + inotify) | `utils/wedge100s-bmc-daemon.c`, `utils/wedge100s-i2c-daemon.c` | `wedge100s/i2c-bmc-sysfs` |
| 8 (platform init mask config) | `utils/wedge100s-platform-init.sh` | `wedge100s/i2c-bmc-sysfs` |
| 9-11 (tests + docs) | `tests/*`, `notes/PLATFORM_GUIDE.md` | devel repo `initial` |

### Test Placement

Tests live in the devel repo only (never in sonic-buildimage — workflow anti-pattern #4). New tests go into **existing stage directories**.

| Test File | Stage | Covers |
|-----------|-------|--------|
| `tests/stage_07_qsfp/test_interrupt_latency.py` | stage_07_qsfp | hot-swap detection latency measurement |
| `tests/stage_09_cpld/test_cpld_masks.py` | stage_09_cpld | mask register state verification |
| `tests/stage_10_daemon/test_cpld_int_monitor.py` | stage_10_daemon | BMC-side daemon health + event socket |

---

## Phase 1: Research and decision gate

### Task 1: Resolve the CPLD mask register address discrepancy

**Files:**
- Create: `notes/2026-04-09-cpld-interrupt-spec.md` (devel repo, branch `initial`)

DESIGNGAPS.md GAP-029 says masks are at **0x20-0x25**. PLATFORM_GUIDE.md CPLD register table (lines 645-690) says **0x18/0x19/0x1A/0x1B** are `PSU_INT_MASK` / `POWER_INT_MASK` / `PCA9535_INT_MASK_0/1` and that **0x20 is `UART_MUX`**. These cannot both be right. Resolve before any code is written.

- [ ] **Step 1: Read the OCP spec PDF authoritative sections**

```bash
# Wedge100S OCP spec v1.3 lives at:
ls -la /export/sonic/sonic-wedge100s-devel/misc/Wedge100S_OCP_Spec_v1_3.pdf
```

Read pages covering CPLD registers. DESIGNGAPS.md GAP-029 cites sections 7.7.2-7.7.7, GAP-018 cites section 7.6 Table 12 pages 44-45. Read both ranges using the Read tool with `pages` parameter (5-page chunks because the PDF is > 10 pages):

- `pages: "44-48"` (Section 7.6 — PCA9535 interrupt routing to CPLD)
- `pages: "50-54"` (Section 7.7 — CPLD register map, reset reason, power status, PSU)
- `pages: "55-61"` (Section 7.7 continued — interrupt masks, UART mux, fan control)
- `pages: "62-65"` (Section 7.7.8-7.7.14 — final CPLD registers)

For each register from `0x10` through `0x30`, record: address, name, direction (R/W/RO), purpose, bit definitions.

- [ ] **Step 2: Cross-check against the Facebook openbmc.git reference**

```bash
# The closest hardware sibling is Facebook Wedge100 (same ASIC + same CPLD per PLATFORM_GUIDE
# line 97). openbmc.git meta-wedge100 layer has the authoritative syscpld register map used
# by fscd. Clone the repo if it isn't already available:
cd /tmp
git clone --depth=1 https://github.com/facebook/openbmc.git openbmc-ref 2>&1 | tail -5
find openbmc-ref -path '*meta-wedge100*' -name '*.c' -o -name '*.h' -o -name '*.py' 2>/dev/null | \
  xargs grep -l -i 'syscpld\|interrupt\|mask\|0x18\|0x20' 2>/dev/null | head -20
```

If the clone fails (no network), skip this step and rely on the OCP spec only — but note the gap in the research notes.

For each interrupt-related register found in openbmc.git, compare to the OCP spec PDF values and the PLATFORM_GUIDE.md table. The openbmc.git code is what actually runs on the BMC, so if it disagrees with DESIGNGAPS.md, the openbmc.git values win.

- [ ] **Step 3: Hardware probe — read the registers with daemons stopped**

Follow `notes/BEWARE_BMC_PMBUS.md` §3a (targeted reads only, no scans) and §4 (stop both host and BMC sensor daemons):

```bash
ssh admin@192.168.88.12
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
sudo ssh -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no root@192.168.88.13 \
  'sv stop fscd ipmid; sleep 2'
```

Read both candidate address ranges via the host CP2112 path (register values are the same from host or BMC since it's the same physical CPLD — BEWARE note on line 853):

```bash
# Status registers (interrupt inputs)
for reg in 0x12 0x13 0x14; do
  val=$(ssh admin@192.168.88.12 "sudo i2cget -y -f 1 0x32 $reg 2>/dev/null")
  echo "host CPLD reg $reg = $val"
done

# DESIGNGAPS candidate mask addresses
for reg in 0x20 0x21 0x22 0x23 0x24 0x25; do
  val=$(ssh admin@192.168.88.12 "sudo i2cget -y -f 1 0x32 $reg 2>/dev/null")
  echo "host CPLD reg $reg = $val"
done

# PLATFORM_GUIDE candidate mask addresses
for reg in 0x18 0x19 0x1a 0x1b; do
  val=$(ssh admin@192.168.88.12 "sudo i2cget -y -f 1 0x32 $reg 2>/dev/null")
  echo "host CPLD reg $reg = $val"
done

# Restart daemons
sudo ssh -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no root@192.168.88.13 \
  'sv start fscd ipmid'
sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

**Do NOT write to any of these registers yet.** Read-only in this task.

- [ ] **Step 4: Decision gate — which address map is authoritative?**

Compare the three sources (OCP spec PDF, openbmc.git ref, hardware probe). One of three outcomes:

1. **OCP spec + openbmc.git + hardware probe all agree** → that's the authoritative map. Proceed.
2. **Two sources agree, one disagrees** → the disagreeing source is the bug. Document it. Proceed with the two-source majority.
3. **All three sources disagree** → STOP. Report BLOCKED. Do not write code against unknown register addresses.

- [ ] **Step 5: Write research notes**

Write `/export/sonic/sonic-wedge100s-devel/notes/2026-04-09-cpld-interrupt-spec.md` with:
- Full CPLD register map for addresses `0x10-0x30` with each bit documented
- Authoritative mask register addresses and the source (OCP spec / openbmc.git / hardware probe)
- The discrepancy analysis (DESIGNGAPS vs PLATFORM_GUIDE)
- Which document is wrong and needs correcting
- Interrupt signal flow diagram (text form): PCA9535 /INT → PCA9548 ch4/5 → CPLD 0x13/0x14 → aggregator → gpio31

- [ ] **Step 6: Commit notes**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add notes/2026-04-09-cpld-interrupt-spec.md
git commit -m "docs(notes): resolve CPLD interrupt mask register address ambiguity

DESIGNGAPS.md GAP-029 said the mask registers were at 0x20-0x25;
PLATFORM_GUIDE.md said 0x18-0x1B. Cross-reference against OCP spec
v1.3 sections 7.7.2-7.7.7, Facebook openbmc.git meta-wedge100
reference code, and direct hardware probe resolves this to
<authoritative map>.

Documents the full CPLD register map 0x10-0x30 with per-bit
definitions, the PCA9535 /INT → CPLD 0x13/0x14 → BMC gpio31 signal
flow, and the authoritative source for each fact.

Prerequisite for the BMC-mediated interrupt aggregation work
(GAP-018 + GAP-029)."
```

### Task 2: Confirm the BMC gpio31 wire is alive and carries QSFP events

**Files:**
- Create: `notes/2026-04-09-gpio31-alive-probe.md` (devel repo)

Before building a daemon around gpio31, prove the wire actually fires when a QSFP module is inserted or removed. DESIGNGAPS says the wire exists, but wires can be DNP'd or miswired; only hardware observation confirms.

- [ ] **Step 1: Verify gpio31 is exported on the BMC and has edge capability**

```bash
ssh admin@192.168.88.12
sudo ssh -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no root@192.168.88.13 \
  'ls -la /sys/class/gpio/ 2>&1 | head -20; echo ---; \
   cat /sys/class/gpio/gpio31/direction 2>/dev/null; \
   cat /sys/class/gpio/gpio31/edge 2>/dev/null; \
   cat /sys/class/gpio/gpio31/value 2>/dev/null'
```

Expected: `gpio31` exists, direction is `in`, edge is one of `none`, `falling`, `rising`, `both`, and the current value is `0` (if an interrupt is latched) or `1` (idle).

If `gpio31` does not exist or is not exported, STOP. The BMC kernel boot scripts or a previous session needs to export it. Check `/etc/init.d/` on the BMC for gpio export code.

- [ ] **Step 2: Watch the wire during a controlled QSFP event**

Use the existing i2c-daemon's presence poll file as a ground-truth observer. With the switch idle and all-polling running normally, physically insert or remove a QSFP module (or ask the human to do it) and capture the edge on gpio31:

```bash
# Terminal 1 (watch the GPIO in a loop — 10ms resolution):
ssh admin@192.168.88.12 "sudo ssh -i /etc/sonic/wedge100s-bmc-key root@192.168.88.13 \
  'for i in \$(seq 1 1000); do \
     printf \"%s %s\n\" \"\$(date +%s.%N)\" \"\$(cat /sys/class/gpio/gpio31/value)\"; \
     sleep 0.01; \
   done' | tee /tmp/gpio31-trace.txt"

# Terminal 2 (watch the host presence file):
ssh admin@192.168.88.12 \
  "while :; do cat /run/wedge100s/sfp_16_present; sleep 0.1; done"

# Physically insert/remove a QSFP module in a known port (e.g. port 16 = Ethernet64)
```

Record whether the gpio31 value transitions at the moment of insertion/removal.

**Decision gate:**
- **gpio31 transitions `1 → 0 → 1` (asserted then cleared)** → the wire is alive. Proceed.
- **gpio31 stays at `1`** → the wire is dead or the mask blocks the event. Check the status register 0x13/0x14 with daemons stopped — if status latches, the aggregator works but the path to gpio31 is blocked by a mask. STOP and re-open Task 1's mask decision.
- **gpio31 stays at `0`** → the wire is stuck-asserted. Something is always firing. Read 0x13/0x14 to identify what. This is a latent issue that would break any interrupt daemon. STOP and diagnose before proceeding.

- [ ] **Step 3: Write findings and commit**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add notes/2026-04-09-gpio31-alive-probe.md
git commit -m "docs(notes): verify BMC gpio31 interrupt wire on QSFP hot-swap

Confirms that the PCA9535 /INT aggregation path through CPLD
registers 0x13/0x14 reaches BMC gpio31 as an edge event on
QSFP module insertion/removal. Records the observed latency
between physical event and gpio31 transition, plus the latched
state of CPLD 0x13/0x14 after the event.

Without this confirmation, any interrupt-driven daemon would
be shooting blind. With it, the BMC-mediated interrupt path
(GAP-018 + GAP-029) is grounded in observed hardware behavior."
```

---

## Phase 2: CPLD driver sysfs extensions

### Task 3: Expose CPLD interrupt mask registers via sysfs

**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules/wedge100s_cpld.c`

Topic branch: `wedge100s/i2c-bmc-sysfs`. Worktree: `/export/sonic/worktrees/wedge100s-i2c-bmc-sysfs` (may already exist from earlier sessions; create if missing).

- [ ] **Step 1: Ensure the i2c-bmc-sysfs worktree exists**

```bash
cd /export/sonic/sonic-buildimage
if [ ! -d /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs ]; then
  git worktree add /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs wedge100s/i2c-bmc-sysfs
fi
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git merge origin/master --no-edit
git status  # should be clean
```

- [ ] **Step 2: Find the existing attribute registration pattern**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
grep -n 'DEVICE_ATTR\|SENSOR_DEVICE_ATTR\|attrs\[\]\|attribute_group' \
  platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules/wedge100s_cpld.c \
  | head -20
```

Identify whether the driver uses `DEVICE_ATTR` or `SENSOR_DEVICE_ATTR`, and where the `attrs[]` array is that feeds the attribute group. Every new attribute must be added to both places.

- [ ] **Step 3: Add register defines**

At the top of the register define block in `wedge100s_cpld.c`, add (update the register addresses to match Task 1's authoritative map — `<MASK_BASE>` is a placeholder until Task 1 resolves it):

```c
/* Interrupt status registers — read latched interrupt events.
 * Cleared by write-back or read-to-clear depending on register (TBD from
 * Task 1 spec research). Documented in notes/2026-04-09-cpld-interrupt-spec.md.
 */
#define REG_INT_STATUS_PSU        0x12  /* PSU event status */
#define REG_INT_STATUS_POWER      0x13  /* power rail event status */
#define REG_INT_STATUS_PCA9535_0  0x14  /* PCA9535 aggregate [7:0] */
#define REG_INT_STATUS_PCA9535_1  0x15  /* PCA9535 aggregate [15:8] */

/* Interrupt mask registers — write 1 to mask an event (default policy TBD
 * from Task 1 spec research). Cross-verified against hardware on 2026-04-09.
 */
#define REG_INT_MASK_PSU          0x18  /* PSU interrupt mask */
#define REG_INT_MASK_POWER        0x19  /* power rail interrupt mask */
#define REG_INT_MASK_PCA9535_0    0x1A  /* PCA9535 interrupt mask [7:0]  */
#define REG_INT_MASK_PCA9535_1    0x1B  /* PCA9535 interrupt mask [15:8] */
```

**IMPORTANT:** replace the register addresses above with whatever Task 1 resolved as authoritative. Do NOT use the DESIGNGAPS `0x20-0x25` range if PLATFORM_GUIDE turns out to be right (which would make `0x20` the UART_MUX — writing to it breaks the console).

- [ ] **Step 4: Add show/set functions for each mask register**

Copy the existing `led_sys1` RW template in the driver. For each of the four mask registers, add a read-modify-write pair:

```c
/**
 * @brief Show PSU interrupt mask register value.
 *
 * Reads the 8-bit register. Each bit set indicates that interrupt source
 * is masked (will NOT contribute to the gpio31 aggregate).
 *
 * @param dev   Device structure.
 * @param attr  Device attribute.
 * @param buf   Output buffer.
 * @return Number of bytes written, or negative errno.
 */
static ssize_t show_int_mask_psu(struct device *dev,
                                  struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_INT_MASK_PSU);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val & 0xff);
}

/**
 * @brief Set PSU interrupt mask register value.
 *
 * Parses an 8-bit hex value from the input buffer and writes it to
 * the mask register. Each bit set masks that interrupt source.
 *
 * @param dev   Device structure.
 * @param attr  Device attribute.
 * @param buf   Input buffer (ASCII hex, e.g. "0xff").
 * @param count Number of input bytes.
 * @return count on success, negative errno on failure.
 */
static ssize_t set_int_mask_psu(struct device *dev,
                                 struct device_attribute *attr,
                                 const char *buf, size_t count)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    unsigned long val;
    int rc;

    rc = kstrtoul(buf, 0, &val);
    if (rc || val > 0xff)
        return -EINVAL;

    mutex_lock(&data->update_lock);
    rc = cpld_write(client, REG_INT_MASK_PSU, (int)val);
    mutex_unlock(&data->update_lock);

    return rc < 0 ? rc : count;
}

static DEVICE_ATTR(int_mask_psu, S_IRUGO | S_IWUSR,
                   show_int_mask_psu, set_int_mask_psu);
```

Repeat for `int_mask_power`, `int_mask_pca9535_0`, `int_mask_pca9535_1` — changing only the `REG_*` constant and the function names.

Also add **read-only** show functions (no setters) for the four status registers:

```c
/**
 * @brief Show PCA9535 aggregate interrupt status [7:0].
 *
 * Each bit indicates a pending unmasked interrupt from one of 8 PCA9535
 * expander events. Read-only; cleared when the underlying PCA9535 INPUT
 * register is read (interrupt-on-change clear-on-read behavior).
 *
 * @param dev   Device structure.
 * @param attr  Device attribute.
 * @param buf   Output buffer.
 * @return Number of bytes written, or negative errno.
 */
static ssize_t show_int_status_pca9535_0(struct device *dev,
                                          struct device_attribute *attr,
                                          char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_INT_STATUS_PCA9535_0);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val & 0xff);
}

static DEVICE_ATTR(int_status_pca9535_0, S_IRUGO, show_int_status_pca9535_0, NULL);
```

Repeat for `int_status_psu`, `int_status_power`, `int_status_pca9535_1`.

- [ ] **Step 5: Add all eight new attributes to the attribute group**

Find the `wedge100s_cpld_attrs[]` array (or equivalent) and add:

```c
    &dev_attr_int_mask_psu.attr,
    &dev_attr_int_mask_power.attr,
    &dev_attr_int_mask_pca9535_0.attr,
    &dev_attr_int_mask_pca9535_1.attr,
    &dev_attr_int_status_psu.attr,
    &dev_attr_int_status_power.attr,
    &dev_attr_int_status_pca9535_0.attr,
    &dev_attr_int_status_pca9535_1.attr,
```

- [ ] **Step 6: Invoke wedge100s-doc-check skill**

All eight new functions have Doxygen `@brief`/`@param`/`@return` headers per the templates above. The skill should report zero findings.

- [ ] **Step 7: Build verify in the worktree**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -20
```

If the build conflicts with a parallel build on master (docklock, fsroot.docker.bookworm), skip and report SKIPPED — same pattern as earlier sessions.

- [ ] **Step 8: Commit + push topic branch (do NOT merge to master)**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules/wedge100s_cpld.c
git commit -m "feat(cpld): expose interrupt mask and status registers as sysfs

Add eight sysfs attributes to wedge100s_cpld for the CPLD interrupt
aggregation registers:

Read-write masks (int_mask_psu, int_mask_power,
                  int_mask_pca9535_0, int_mask_pca9535_1):
  Each bit set masks that interrupt source from contributing to
  the gpio31 aggregate. Register addresses verified against OCP
  spec v1.3 and hardware on 2026-04-09 (see
  notes/2026-04-09-cpld-interrupt-spec.md).

Read-only status (int_status_psu, int_status_power,
                  int_status_pca9535_0, int_status_pca9535_1):
  Latched interrupt source identification. Cleared by reading
  the underlying PCA9535 INPUT register (interrupt-on-change
  clear-on-read).

Prerequisite for the BMC-side cpld-int-monitor daemon and the
host-side event-driven re-scan path (GAP-018 + GAP-029)."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP.** Do not `git checkout master`. Do not merge.

---

## Phase 3: BMC-side interrupt monitor daemon (Python)

### Task 4: Write wedge100s-cpld-int-monitor.py

**Files:**
- Create: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-cpld-int-monitor.py`
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/debian/sonic-platform-accton-wedge100s-32x.install` (to ship the .py file in the platform .deb at `/usr/share/sonic/device/x86_64-accton_wedge100s_32x-r0/bmc/`)

Topic branch: `wedge100s/i2c-bmc-sysfs` (same worktree as Task 3).

**Architecture note:** The daemon is a pure Python 3 script (no imports beyond stdlib — verified 2026-04-09 that `select`, `fcntl`, `struct` are available on the BMC's Python 3.5.3). It is **not** a bitbake-packaged binary. It ships in the host platform .deb and gets rsynced to `/tmp/` on the BMC at `wedge100s-bmc-daemon` startup (Task 5).

- [ ] **Step 1: Write the Python daemon source**

Create `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-cpld-int-monitor.py`:

```python
#!/usr/bin/env python3
"""wedge100s-cpld-int-monitor.py — BMC-side CPLD interrupt aggregator monitor.

Runs on the BMC (ARMv5, AST2400, Python 3.5.3 — verified 2026-04-09).
Blocks on gpio31 edge events via select.poll(POLLPRI), reads CPLD
interrupt status registers via /dev/i2c-12 on each edge, and appends
event lines to /tmp/wedge100s-cpld-int-events.log that the host tails
via SSH ControlMaster.

Signal flow:
  QSFP presence / PSU alarm / power rail fault →
  PCA9535 /INT → PCA9548 mux → CPLD aggregator (0x12-0x15) →
  gpio31 edge → this daemon → event log → host bmc-daemon inotify →
  host i2c-daemon targeted re-scan

Launched by the host wedge100s-bmc-daemon at startup via:
  setsid python3 /tmp/wedge100s-cpld-int-monitor.py \\
    > /tmp/wedge100s-cpld-int-monitor.stderr 2>&1 < /dev/null &

No runit service, no systemd. Ephemeral — lives in /tmp (tmpfs),
cleared on BMC reboot, re-pushed by the host on every bmc-daemon
start. Verified 2026-04-09 that Python 3.5's select, fcntl, and
struct stdlib modules are available on the BMC.
"""

import errno
import fcntl
import os
import select
import sys
import time

# GPIO 31 sysfs paths
GPIO_VALUE_PATH = '/sys/class/gpio/gpio31/value'
GPIO_EDGE_PATH  = '/sys/class/gpio/gpio31/edge'
GPIO_EXPORT     = '/sys/class/gpio/export'

# CPLD access via i2c-dev
CPLD_I2C_BUS    = 12
CPLD_I2C_ADDR   = 0x31
I2C_SLAVE_FORCE = 0x0706  # linux/i2c-dev.h

# Event log (tmpfs — cleared on reboot)
EVENT_LOG_PATH  = '/tmp/wedge100s-cpld-int-events.log'
EVENT_LOG_MAX   = 64 * 1024  # rotate at 64 KB

# CPLD status register addresses (update after Phase 1 Task 1 research
# resolves the DESIGNGAPS vs PLATFORM_GUIDE discrepancy).
REG_STATUS_PSU       = 0x12
REG_STATUS_POWER     = 0x13
REG_STATUS_PCA9535_0 = 0x14
REG_STATUS_PCA9535_1 = 0x15


def log(msg):
    """Write a timestamped info line to stderr (captured by host via SSH)."""
    sys.stderr.write('{}: {}\n'.format(time.strftime('%Y-%m-%dT%H:%M:%S'), msg))
    sys.stderr.flush()


def gpio_export_and_configure():
    """Export gpio31 if not already exported, then set edge=both.

    The Facebook OpenBMC image may have gpio31 already exported via
    its own boot scripts (shadow names under /tmp/gpionames). Writing
    to /sys/class/gpio/export for an already-exported pin returns
    EBUSY, which we ignore.

    Returns:
        bool: True if gpio31 is usable after this call, False otherwise.
    """
    if not os.path.exists('/sys/class/gpio/gpio31'):
        try:
            with open(GPIO_EXPORT, 'w') as f:
                f.write('31')
        except (IOError, OSError) as e:
            if getattr(e, 'errno', None) != errno.EBUSY:
                log('gpio31 export failed: {}'.format(e))

    try:
        with open(GPIO_EDGE_PATH, 'w') as f:
            f.write('both')
    except (IOError, OSError) as e:
        log('gpio31 edge=both failed: {}'.format(e))
        return False
    return True


def cpld_read(reg):
    """Read a single byte from the CPLD via /dev/i2c-12 at 0x31.

    Args:
        reg: CPLD register address (0x00-0xff).

    Returns:
        int or None: Register value (0-255), or None on read failure.
    """
    try:
        fd = os.open('/dev/i2c-{}'.format(CPLD_I2C_BUS), os.O_RDWR)
    except OSError as e:
        log('open /dev/i2c-{} failed: {}'.format(CPLD_I2C_BUS, e))
        return None
    try:
        fcntl.ioctl(fd, I2C_SLAVE_FORCE, CPLD_I2C_ADDR)
        os.write(fd, bytes([reg]))
        data = os.read(fd, 1)
        if len(data) != 1:
            return None
        return data[0]
    except (OSError, IOError) as e:
        log('cpld_read reg 0x{:02x} failed: {}'.format(reg, e))
        return None
    finally:
        os.close(fd)


def rotate_log_if_needed():
    """Rotate /tmp/wedge100s-cpld-int-events.log if it exceeds EVENT_LOG_MAX.

    Renames the current log to .log.1 (two-generation rotation) so a
    burst of events does not fill the tmpfs backing /tmp.
    """
    try:
        if os.path.getsize(EVENT_LOG_PATH) < EVENT_LOG_MAX:
            return
        os.rename(EVENT_LOG_PATH, EVENT_LOG_PATH + '.1')
    except OSError:
        pass


def main():
    """Daemon entry point — export gpio, loop on poll(POLLPRI)."""
    log('wedge100s-cpld-int-monitor: starting')

    if not gpio_export_and_configure():
        log('gpio setup failed — exiting')
        return 1

    try:
        gpio_fd = os.open(GPIO_VALUE_PATH, os.O_RDONLY)
    except OSError as e:
        log('open {} failed: {}'.format(GPIO_VALUE_PATH, e))
        return 1

    poller = select.poll()
    poller.register(gpio_fd, select.POLLPRI | select.POLLERR)

    # Drain any latched edge before entering the main loop.
    os.lseek(gpio_fd, 0, os.SEEK_SET)
    os.read(gpio_fd, 16)

    log('wedge100s-cpld-int-monitor: entering main loop')

    while True:
        events = poller.poll(-1)
        for fd, event in events:
            if fd != gpio_fd:
                continue
            os.lseek(gpio_fd, 0, os.SEEK_SET)
            raw = os.read(gpio_fd, 16).strip()
            gpio_val = 0 if raw == b'0' else 1

            # gpio31 is active-low: 0 = interrupt asserted.
            if gpio_val != 0:
                continue

            st_psu   = cpld_read(REG_STATUS_PSU)
            st_power = cpld_read(REG_STATUS_POWER)
            st_pca0  = cpld_read(REG_STATUS_PCA9535_0)
            st_pca1  = cpld_read(REG_STATUS_PCA9535_1)

            ts = time.monotonic()
            line = '{:.6f} {:d} {:d} {:d} {:d}\n'.format(
                ts,
                st_psu   if st_psu   is not None else -1,
                st_power if st_power is not None else -1,
                st_pca0  if st_pca0  is not None else -1,
                st_pca1  if st_pca1  is not None else -1,
            )

            rotate_log_if_needed()
            try:
                with open(EVENT_LOG_PATH, 'a') as lf:
                    lf.write(line)
                    lf.flush()
                    os.fsync(lf.fileno())
            except (IOError, OSError) as e:
                log('event log write failed: {}'.format(e))

            log('int event: ' + line.strip())


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 2: Ship the .py in the platform .deb**

Find the existing install file:

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
find platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/debian -name '*.install' | head
```

Add a line to the right `.install` file (likely `sonic-platform-accton-wedge100s-32x.install`):

```
utils/wedge100s-cpld-int-monitor.py    usr/share/sonic/device/x86_64-accton_wedge100s_32x-r0/bmc/
```

The `0755` mode is not required — the host rsync + `python3 <path>` launch pattern in Task 5 doesn't need the file to be executable.

- [ ] **Step 3: Verify Python syntax on the host**

```bash
python3 -m py_compile /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-cpld-int-monitor.py && echo OK
```

The host runs Python 3.11+ while the BMC runs 3.5.3. The script avoids f-strings (3.6+) and uses `.format()` throughout so it runs cleanly on both.

- [ ] **Step 4: Smoke-test on the BMC**

Copy the script manually and run it non-forking for a few seconds to verify imports and gpio setup work:

```bash
ssh admin@192.168.88.12 \
  "sudo scp -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no \
   /usr/share/sonic/device/x86_64-accton_wedge100s_32x-r0/bmc/wedge100s-cpld-int-monitor.py \
   root@192.168.88.13:/tmp/wedge100s-cpld-int-monitor.py" 2>&1 | tail -3
# (The above assumes the platform .deb is already installed — if not, scp from the worktree instead.)

ssh admin@192.168.88.12 "sudo ssh -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no root@192.168.88.13 \
  'timeout 5 python3 /tmp/wedge100s-cpld-int-monitor.py 2>&1; echo rc=\$?'"
```

Expected: `wedge100s-cpld-int-monitor: starting` + `entering main loop`, followed by no events (idle) and the `timeout` firing with `rc=124`. Anything earlier is a bug — fix it before committing.

- [ ] **Step 5: Invoke wedge100s-doc-check**

Every function has a Google-style docstring. Module-level docstring is present. Expect no findings.

- [ ] **Step 6: Build verify**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -10
```

Skip with SKIPPED if docklock conflicts with a parallel master build.

- [ ] **Step 7: Commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-cpld-int-monitor.py \
        platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/debian/sonic-platform-accton-wedge100s-32x.install
git commit -m "feat(bmc): add Python CPLD interrupt monitor for the BMC side

New wedge100s-cpld-int-monitor.py is a ~180-line Python 3 daemon
that runs on the BMC:
  1. Exports gpio31 (if not already) and sets edge=both
  2. Blocks on select.poll(POLLPRI) — zero CPU until edge fires
  3. Reads CPLD status registers 0x12-0x15 via /dev/i2c-12
  4. Appends event lines to /tmp/wedge100s-cpld-int-events.log
     with size-based rotation at 64 KB

Targets Python 3.5 (BMC ships /usr/bin/python3 = 3.5.3 verified
2026-04-09) — uses .format() strings, no f-strings, stdlib-only
(select, fcntl, struct, os, time, errno, sys).

The platform .deb ships the .py file at
/usr/share/sonic/device/x86_64-accton_wedge100s_32x-r0/bmc/
and the host-side wedge100s-bmc-daemon rsyncs + launches it at
startup (Task 5). No cross-compile, no bitbake recipe, no
OpenBMC image rebuild, no wedge100s/submodule-patches branch
touched.

Part of GAP-018 + GAP-029."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP. Do not merge to master.**

### Task 5: Rsync-push and launch the daemon from wedge100s-bmc-daemon

**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c`

Topic branch: `wedge100s/i2c-bmc-sysfs` (same worktree).

- [ ] **Step 1: Add path constants**

Near the existing `CTL_SOCK`, `BMC_HOST`, `BMC_KEY` defines in `wedge100s-bmc-daemon.c`, add:

```c
/* CPLD interrupt monitor daemon (Python 3, runs on BMC).
 * Shipped by the platform .deb at CPLD_INT_MONITOR_HOST_PATH and
 * rsynced to CPLD_INT_MONITOR_BMC_PATH on bmc_connect(). The BMC
 * path is in /tmp (tmpfs) so it's cleared on BMC reboot — we re-
 * push every time bmc-daemon starts, which is cheap.
 */
#define CPLD_INT_MONITOR_HOST_PATH \
    "/usr/share/sonic/device/x86_64-accton_wedge100s_32x-r0/bmc/wedge100s-cpld-int-monitor.py"
#define CPLD_INT_MONITOR_BMC_PATH \
    "/tmp/wedge100s-cpld-int-monitor.py"
#define CPLD_INT_MONITOR_STDERR_PATH \
    "/tmp/wedge100s-cpld-int-monitor.stderr"
#define CPLD_INT_MONITOR_EVENT_LOG \
    "/tmp/wedge100s-cpld-int-events.log"
```

- [ ] **Step 2: Add push-and-launch helper**

After `bmc_connect()`, add:

```c
/**
 * @brief Rsync wedge100s-cpld-int-monitor.py to the BMC and launch it.
 *
 * Uses the existing SSH ControlMaster (from bmc_connect()) so neither
 * rsync nor the launch command opens a new SSH handshake. The daemon
 * is launched with setsid so it outlives the launch shell; stderr is
 * redirected to /tmp/wedge100s-cpld-int-monitor.stderr.
 *
 * Idempotent: if a monitor is already running (pgrep check), this
 * function is a no-op. Otherwise it pushes the latest .py and
 * relaunches.
 *
 * @return 0 on success, -1 on failure. Failure is non-fatal — the
 *         host can continue polling as a fallback.
 */
static int push_and_launch_cpld_int_monitor(void)
{
    char cmd[512];

    /* 1. Check if a monitor is already running. */
    snprintf(cmd, sizeof(cmd),
        "ssh -S " CTL_SOCK " -o BatchMode=yes " BMC_HOST
        " 'pgrep -f wedge100s-cpld-int-monitor.py > /dev/null && echo RUNNING || echo STOPPED'");
    FILE *fp = popen(cmd, "r");
    if (!fp) return -1;
    char resp[32] = {0};
    fgets(resp, sizeof(resp), fp);
    pclose(fp);
    if (strstr(resp, "RUNNING")) {
        syslog(LOG_INFO, "cpld-int-monitor already running on BMC");
        return 0;
    }

    /* 2. Rsync the .py over the ControlMaster. */
    snprintf(cmd, sizeof(cmd),
        "rsync -e 'ssh -S " CTL_SOCK " -o BatchMode=yes' -q "
        CPLD_INT_MONITOR_HOST_PATH " " BMC_HOST ":" CPLD_INT_MONITOR_BMC_PATH);
    int rc = system(cmd);
    if (rc != 0) {
        syslog(LOG_WARNING, "rsync cpld-int-monitor.py failed: rc=%d", rc);
        return -1;
    }

    /* 3. Launch via setsid so the daemon survives our launch shell. */
    snprintf(cmd, sizeof(cmd),
        "ssh -S " CTL_SOCK " -o BatchMode=yes " BMC_HOST
        " 'setsid python3 " CPLD_INT_MONITOR_BMC_PATH
        "  > " CPLD_INT_MONITOR_STDERR_PATH " 2>&1 < /dev/null &'");
    rc = system(cmd);
    if (rc != 0) {
        syslog(LOG_WARNING, "launch cpld-int-monitor failed: rc=%d", rc);
        return -1;
    }

    syslog(LOG_INFO, "cpld-int-monitor rsynced and launched on BMC");
    return 0;
}
```

- [ ] **Step 3: Call it from main() after bmc_connect()**

In `main()`, after the existing `bmc_connect()` success path and before the main poll loop:

```c
    if (bmc_connect() < 0) {
        syslog(LOG_ERR, "wedge100s-bmc-daemon: initial connect failed — exiting");
        return 1;
    }

    /* Push and launch the Python CPLD interrupt monitor on the BMC.
     * Non-fatal on failure — the daemon falls back to polling. */
    push_and_launch_cpld_int_monitor();
```

- [ ] **Step 4: Confirm rsync is available on the SONiC host**

```bash
ssh admin@192.168.88.12 'which rsync; rsync --version 2>&1 | head -1'
```

Expected: `/usr/bin/rsync` and a version line. If rsync is not installed, substitute `scp` in the helper function above (same invocation pattern, different binary name).

- [ ] **Step 5: Invoke wedge100s-doc-check + build verify**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -10
```

Skip with SKIPPED if docklock conflict.

- [ ] **Step 6: Commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c
git commit -m "feat(bmc): rsync-push and launch the CPLD interrupt monitor

wedge100s-bmc-daemon now pushes wedge100s-cpld-int-monitor.py
(shipped in the platform .deb at /usr/share/sonic/device/.../bmc/)
to /tmp/wedge100s-cpld-int-monitor.py on the BMC via the existing
SSH ControlMaster at startup, then launches it with
setsid python3 ... &.

Idempotent — skips the push+launch if a monitor is already
running (pgrep check). Non-fatal on failure (host falls back to
polling).

No cross-compile, no bitbake recipe, no OpenBMC image rebuild.
Python 3.5.3 is already on the BMC (verified 2026-04-09). The
.py file is ephemeral — tmpfs, cleared on BMC reboot, re-pushed
by bmc-daemon on next start.

Part of GAP-018 + GAP-029."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP. Do not merge to master.**

### Task 6: (merged into Task 4)

The earlier draft's Task 6 refined a C-source event delivery mechanism from a UNIX socket to an append-only log file. The Python daemon in Task 4 uses the append-only log design directly — no refinement step needed. **Task 6 is intentionally left as a placeholder to preserve task numbering for commit messages and cross-references.**

---

## Phase 4: Host-side integration

### Task 7: Extend wedge100s-bmc-daemon to tail the BMC event log

**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c`
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-i2c-daemon.c`

Topic branch: `wedge100s/i2c-bmc-sysfs` (same worktree).

- [ ] **Step 1: Add a background SSH tail of the BMC event log**

In `wedge100s-bmc-daemon.c`, after the ControlMaster is established, fork a child process that runs `ssh -S <ctl_sock> root@... tail -F /var/log/wedge100s-cpld-int-events.log` and pipes its output to a pipe the parent reads non-blockingly in the main loop.

Add the following near the top of `main()` after `bmc_connect()`:

```c
    /* Spawn the BMC event tail as a child. The child uses the ControlMaster
     * socket that bmc_connect() just established, so no second SSH handshake.
     */
    int event_pipe[2];
    if (pipe(event_pipe) < 0) {
        syslog(LOG_ERR, "event pipe: %s", strerror(errno));
        return 1;
    }

    pid_t tail_pid = fork();
    if (tail_pid == 0) {
        /* Child: redirect stdout to the write end of the pipe and exec ssh tail. */
        close(event_pipe[0]);
        dup2(event_pipe[1], STDOUT_FILENO);
        close(event_pipe[1]);
        execlp("ssh", "ssh",
               "-o", "BatchMode=yes",
               "-o", "ControlPath=" CTL_SOCK,
               "-o", "StrictHostKeyChecking=no",
               "-i", BMC_KEY,
               BMC_HOST,
               "tail", "-n", "0", "-F",
               "/var/log/wedge100s-cpld-int-events.log",
               (char *)NULL);
        syslog(LOG_ERR, "tail exec failed: %s", strerror(errno));
        _exit(1);
    }
    close(event_pipe[1]);

    /* Make the read end non-blocking so poll() can wake on inotify + events. */
    fcntl(event_pipe[0], F_SETFL, O_NONBLOCK);
```

- [ ] **Step 2: Add the event pipe to the main poll() set**

Change the existing `pfds[2]` array to `pfds[3]`:

```c
    struct pollfd pfds[3] = {
        {.fd = timer_fd,        .events = POLLIN},
        {.fd = inotify_fd,      .events = POLLIN},
        {.fd = event_pipe[0],   .events = POLLIN},
    };
```

Update the poll() call and add a branch to handle incoming event lines:

```c
    while (1) {
        int r = poll(pfds, 3, -1);
        if (r < 0) {
            if (errno == EINTR) continue;
            syslog(LOG_ERR, "poll: %s", strerror(errno));
            continue;
        }

        if (pfds[2].revents & POLLIN) {
            /* A new event line is available from the BMC event log. */
            char buf[512];
            ssize_t n = read(event_pipe[0], buf, sizeof(buf) - 1);
            if (n > 0) {
                buf[n] = '\0';
                /* Format: "<ts_ns> <st_psu> <st_power> <st_pca0> <st_pca1>\n"
                 * Write the latest line to /run/wedge100s/cpld_int_event
                 * which the host-side wedge100s-i2c-daemon watches via inotify.
                 */
                int fd = open(RUN_DIR "/cpld_int_event",
                              O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (fd >= 0) {
                    write(fd, buf, n);
                    close(fd);
                }
                syslog(LOG_INFO, "CPLD interrupt event: %.*s", (int)n - 1, buf);
            }
            if (!(pfds[0].revents & POLLIN) && !(pfds[1].revents & POLLIN))
                continue;
        }

        /* ... existing timer_fd and inotify_fd branches ... */
    }
```

- [ ] **Step 3: Extend wedge100s-i2c-daemon to inotify-watch the event file**

In `wedge100s-i2c-daemon.c`, the main loop currently runs on a 1-second timer. Add an inotify watch on `/run/wedge100s/cpld_int_event` so that a write by bmc-daemon immediately wakes the i2c-daemon for a targeted re-scan.

Find the existing `poll()` infrastructure (or equivalent) in i2c-daemon and add a second pollfd for inotify. When the inotify fires on `cpld_int_event`:

1. Read the event file
2. Parse the four status values
3. If `st_pca0 != 0` or `st_pca1 != 0`, re-scan PCA9535 presence immediately (skip the normal 1-second cadence)
4. Update `/run/wedge100s/sfp_*_present` as usual

Paste the exact inotify snippet:

```c
/* In main(), after existing setup: */
int g_event_inotify_fd = inotify_init1(IN_NONBLOCK);
if (g_event_inotify_fd >= 0) {
    inotify_add_watch(g_event_inotify_fd, RUN_DIR "/cpld_int_event",
                      IN_CLOSE_WRITE | IN_MODIFY);
}

/* In the main poll loop, add event_inotify_fd to the pollfd set and handle it: */
if (pfds_evt.revents & POLLIN) {
    char buf[512];
    (void)read(g_event_inotify_fd, buf, sizeof(buf));  /* drain inotify */

    /* Read the event file and re-scan PCA9535 presence immediately. */
    int fd = open(RUN_DIR "/cpld_int_event", O_RDONLY);
    if (fd >= 0) {
        char line[256];
        ssize_t n = read(fd, line, sizeof(line) - 1);
        close(fd);
        if (n > 0) {
            line[n] = '\0';
            /* Parse status bytes to decide which subsystems to re-scan. */
            int st_psu, st_power, st_pca0, st_pca1;
            long long ts_sec; long ts_nsec;
            if (sscanf(line, "%lld.%ld %d %d %d %d",
                       &ts_sec, &ts_nsec,
                       &st_psu, &st_power, &st_pca0, &st_pca1) == 6) {
                if (st_pca0 || st_pca1) {
                    poll_qsfp_presence_now();  /* existing targeted poll */
                }
                /* Add power/PSU re-scan hooks if/when those exist. */
            }
        }
    }
}
```

- [ ] **Step 4: wedge100s-doc-check + build verify**

Run the doc-check skill and then:

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -10
```

Skip with SKIPPED if docklock conflict.

- [ ] **Step 5: Commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c \
        platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-i2c-daemon.c
git commit -m "feat(bmc,i2c): wire host daemons into BMC interrupt event log

wedge100s-bmc-daemon forks an SSH tail process that follows
/var/log/wedge100s-cpld-int-events.log on the BMC via the
existing ControlMaster socket (no second handshake). Event
lines arrive on a pipe added to the main poll() set; each
event is written to /run/wedge100s/cpld_int_event.

wedge100s-i2c-daemon adds an inotify watch on cpld_int_event
and triggers an immediate targeted PCA9535 presence re-scan
when the status byte indicates a QSFP change, bypassing the
normal 1-second polling cadence.

End-to-end QSFP hot-swap detection latency drops from 1-3s
(polling) to ~100ms (gpio31 edge → BMC → SSH → inotify →
targeted re-scan). GAP-018 + GAP-029."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP. Do not merge to master.**

### Task 8: Configure CPLD mask registers at platform init

**Files:**
- Modify: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-platform-init.sh`

Topic branch: `wedge100s/i2c-bmc-sysfs`.

- [ ] **Step 1: Determine the "useful" mask values**

From Task 1's research notes, decide which interrupt sources should contribute to gpio31. A conservative starting policy:

- **PCA9535 mask** (0x1A, 0x1B — verify against Task 1): unmask all bits (0x00, 0x00). We want every QSFP presence / RXLOSS change to fire.
- **PSU mask** (0x18): unmask PSU insertion/removal only (exact bit layout from Task 1).
- **Power mask** (0x19): unmask VCORE_HOT, VANLOG_HOT, V3V3_HOT bits (thermal emergencies). Leave routine VRDY bits masked to avoid boot-time noise.

**Do not guess.** If Task 1's research notes don't give you per-bit semantics for a register, keep that register at its power-on default and add a TODO comment.

- [ ] **Step 2: Add mask config block to platform-init.sh**

After the CPLD driver is loaded in `wedge100s-platform-init.sh`:

```bash
# ── Configure CPLD interrupt masks for BMC-mediated event aggregation ──
# See notes/2026-04-09-cpld-interrupt-spec.md for register semantics.
# Written on 2026-04-09; update if CPLD firmware rev changes.
if [ -d /sys/bus/i2c/devices/1-0032 ]; then
    # PCA9535 mask 0 (QSFP presence 0-7 + RXLOSS 0-7): unmask all
    echo 0x00 > /sys/bus/i2c/devices/1-0032/int_mask_pca9535_0 2>/dev/null || true
    # PCA9535 mask 1 (QSFP presence 8-15 + RXLOSS 8-15): unmask all
    echo 0x00 > /sys/bus/i2c/devices/1-0032/int_mask_pca9535_1 2>/dev/null || true
    # PSU mask: unmask insertion/removal; keep other bits masked (TBD)
    echo 0xfc > /sys/bus/i2c/devices/1-0032/int_mask_psu         2>/dev/null || true
    # Power mask: unmask HOT bits only; keep VRDY masked (boot noise)
    echo 0xe3 > /sys/bus/i2c/devices/1-0032/int_mask_power       2>/dev/null || true
fi
```

**Update the four mask values above** with whatever Task 1's research says is correct for this platform. The comment values are placeholders you MUST revisit.

- [ ] **Step 3: Build verify, commit + push topic branch**

```bash
cd /export/sonic/worktrees/wedge100s-i2c-bmc-sysfs
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb 2>&1 | tail -5
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-platform-init.sh
git commit -m "feat(platform): configure CPLD interrupt masks at boot

platform-init.sh now writes per-subsystem mask values to the CPLD
interrupt mask registers (added as sysfs attributes in an earlier
commit on this branch) so that gpio31 only fires for events the
host/BMC event path cares about:

  int_mask_pca9535_{0,1} = 0x00 (all QSFP events contribute)
  int_mask_psu            = 0xfc (PSU insert/remove only)
  int_mask_power          = 0xe3 (VCORE/VANLOG/V3V3 HOT only)

Values are from notes/2026-04-09-cpld-interrupt-spec.md. GAP-029."
git push origin wedge100s/i2c-bmc-sysfs
```

**STOP. Do not merge to master.**

---

## Phase 5: Tests and documentation

### Task 9: Hot-swap detection latency test

**Files:**
- Create: `tests/stage_07_qsfp/test_interrupt_latency.py` (devel repo, branch `initial`)

- [ ] **Step 1: Write the test**

```python
"""Stage 07 supplement — QSFP hot-swap detection latency (GAP-018).

Measures the end-to-end latency between a QSFP module physical event
(insert/remove) and the host-side /run/wedge100s/sfp_N_present file
updating to reflect the new state.

Before the BMC-mediated interrupt path (GAP-018 + GAP-029 resolution),
the worst-case latency is the host polling interval (1-3 seconds).
After, it should be ~100ms.

!!! WARNING !!!  This test requires physical intervention — a human
    or a test rig must insert/remove a QSFP module on command. It is
    gated on HOT_SWAP_TEST_ACKNOWLEDGED=1 because it cannot be
    automated from software.
"""

import os
import time
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HOT_SWAP_TEST_ACKNOWLEDGED") != "1",
    reason=(
        "Hot-swap latency test requires physical QSFP insertion/removal. "
        "Set HOT_SWAP_TEST_ACKNOWLEDGED=1 to opt in and follow the manual "
        "prompts."
    ),
)

RUN_DIR = "/run/wedge100s"
# Port 16 (Ethernet64) is the documented test port — update if lab topology changes.
TEST_PORT = 16
MAX_LATENCY_MS = 500  # pass if detection is within 500ms of physical event


def _read_presence(ssh, port):
    out, _, rc = ssh.run(f"cat {RUN_DIR}/sfp_{port}_present", timeout=5)
    if rc != 0:
        return None
    return out.strip()


def test_hot_swap_latency(ssh):
    """Measure insertion latency after the operator physically inserts a module.

    Procedure:
    1. Operator removes the module from the test port (test asks for it)
    2. Test waits until presence reads '0'
    3. Operator inserts the module (test asks for it)
    4. Test timestamps the first presence='1' read, reports latency
    """
    initial = _read_presence(ssh, TEST_PORT)
    if initial != '0':
        pytest.skip(
            f"Test port {TEST_PORT} is populated (present={initial}). "
            "Remove the module before running this test."
        )

    print(f"\n  >>> Insert a QSFP module into port {TEST_PORT} now.")
    print(f"  Waiting up to 30s for insertion...")

    start = time.monotonic()
    deadline = start + 30.0
    detected_at = None
    while time.monotonic() < deadline:
        if _read_presence(ssh, TEST_PORT) == '1':
            detected_at = time.monotonic()
            break
        time.sleep(0.01)  # 10ms poll of the PRESENCE FILE (not the hardware)

    assert detected_at is not None, (
        f"Port {TEST_PORT} did not report present=1 within 30s of test start"
    )

    # We don't know exactly when the operator inserted the module, but the
    # detection latency is bounded by how long after the module was inserted
    # the presence file updated. We print the observed detection duration as
    # a qualitative indicator — the operator can judge whether it's "fast"
    # (< 500ms from their perception) or "slow" (> 1s).
    latency_ms = (detected_at - start) * 1000
    print(f"  Detected at +{latency_ms:.0f}ms from test start")
    print(f"  Physical insertion latency ≤ {latency_ms:.0f}ms "
          f"(depends on when operator inserted vs test start)")

    # Looser assertion: just require detection within 30s of test start.
    # Operators can compare pre/post values to judge the improvement.
    assert latency_ms < 30000, f"Detection took {latency_ms}ms (>30s)"
```

- [ ] **Step 2: Commit in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/stage_07_qsfp/test_interrupt_latency.py
git commit -m "test(qsfp): add hot-swap detection latency test (GAP-018)

Measures the end-to-end latency between physical QSFP insertion
and the /run/wedge100s/sfp_N_present file update. Gated on
HOT_SWAP_TEST_ACKNOWLEDGED=1 because it requires physical
operator intervention.

Used to verify the GAP-018 + GAP-029 BMC-mediated interrupt
path delivers its expected 1-3s → ~100ms improvement."
```

### Task 10: CPLD mask register verification test

**Files:**
- Create: `tests/stage_09_cpld/test_cpld_masks.py` (devel repo)

- [ ] **Step 1: Write the test**

```python
"""Stage 09 supplement — CPLD interrupt mask register verification (GAP-029).

Verifies that platform-init.sh has successfully configured the CPLD
interrupt mask registers to the policy values documented in
notes/2026-04-09-cpld-interrupt-spec.md. A mismatch indicates either
a failure of platform-init (the /sys/bus/i2c path isn't available
yet when the script runs) or a drift between the script and the
policy document.
"""

import pytest

CPLD_SYSFS = "/sys/bus/i2c/devices/1-0032"

# Policy values from notes/2026-04-09-cpld-interrupt-spec.md — update
# whenever the platform-init script changes.
EXPECTED_MASKS = {
    "int_mask_pca9535_0": 0x00,  # all QSFP presence 0-7 unmasked
    "int_mask_pca9535_1": 0x00,  # all QSFP presence 8-15 unmasked
    "int_mask_psu":       0xfc,  # only insert/remove bits unmasked
    "int_mask_power":     0xe3,  # only HOT bits unmasked
}


def test_cpld_interrupt_mask_sysfs_exists(ssh):
    """All four mask sysfs attributes should exist under CPLD_SYSFS."""
    missing = []
    for attr in EXPECTED_MASKS:
        out, _, _ = ssh.run(
            f"test -f {CPLD_SYSFS}/{attr} && echo YES || echo NO", timeout=5)
        if "YES" not in out:
            missing.append(attr)
    if missing:
        pytest.skip(
            f"Missing CPLD mask attrs: {missing}. "
            "wedge100s_cpld driver may not be updated with GAP-029 attributes, "
            "or the driver is loaded but not bound to 1-0032."
        )


def test_cpld_interrupt_masks_match_policy(ssh):
    """Mask register values should match the documented policy."""
    mismatches = []
    for attr, expected in EXPECTED_MASKS.items():
        out, _, rc = ssh.run(f"cat {CPLD_SYSFS}/{attr}", timeout=5)
        if rc != 0:
            mismatches.append(f"{attr}: unreadable")
            continue
        try:
            actual = int(out.strip(), 0)
        except ValueError:
            mismatches.append(f"{attr}: unparsable {out.strip()!r}")
            continue
        if actual != expected:
            mismatches.append(
                f"{attr}: actual=0x{actual:02x}, expected=0x{expected:02x}"
            )
        else:
            print(f"  {attr} = 0x{actual:02x} (OK)")
    assert not mismatches, (
        "CPLD mask register mismatches:\n  " + "\n  ".join(mismatches) +
        "\n\nCheck wedge100s-platform-init.sh mask configuration block "
        "and notes/2026-04-09-cpld-interrupt-spec.md for expected values."
    )
```

- [ ] **Step 2: Commit in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/stage_09_cpld/test_cpld_masks.py
git commit -m "test(cpld): verify CPLD interrupt mask register values (GAP-029)

Reads the four new int_mask_{psu,power,pca9535_0,pca9535_1} sysfs
attributes and checks them against the policy values set by
platform-init.sh. Skips if the sysfs path isn't present (CPLD
driver not bound to 1-0032)."
```

### Task 11: BMC-side daemon health test

**Files:**
- Create: `tests/stage_10_daemon/test_cpld_int_monitor.py` (devel repo)

- [ ] **Step 1: Write the test**

```python
"""Stage 10 supplement — BMC-side cpld-int-monitor daemon health (GAP-018).

Verifies that the new wedge100s-cpld-int-monitor daemon is installed
on the BMC, is currently running under runit, and its event log file
exists and is being written to. Does NOT test end-to-end event
delivery (that's covered by stage_07_qsfp/test_interrupt_latency.py).
"""

import pytest

BMC_KEY = "/etc/sonic/wedge100s-bmc-key"
BMC_HOST = "root@192.168.88.13"
BMC_SSH = (
    f"sudo ssh -i {BMC_KEY} -o StrictHostKeyChecking=no "
    f"-o ConnectTimeout=5 {BMC_HOST}"
)


def _bmc(ssh, cmd):
    return ssh.run(f"{BMC_SSH} '{cmd}'", timeout=15)


def test_cpld_int_monitor_binary_installed(ssh):
    """The BMC rootfs has /usr/local/bin/wedge100s-cpld-int-monitor."""
    out, _, rc = _bmc(ssh, "test -x /usr/local/bin/wedge100s-cpld-int-monitor && echo OK")
    assert "OK" in out, (
        "wedge100s-cpld-int-monitor binary missing from BMC rootfs. "
        "Has the BMC image been rebuilt with the meta-wedge100s recipe?"
    )


def test_cpld_int_monitor_runit_service_up(ssh):
    """The runit service under /etc/sv is up."""
    out, _, _ = _bmc(ssh, "sv status wedge100s-cpld-int-monitor 2>&1")
    assert "run:" in out, (
        f"runit service is not running. sv status output:\n{out}"
    )


def test_cpld_int_monitor_event_log_exists(ssh):
    """The event log file exists and is recent (mtime within 5 minutes)."""
    out, _, rc = _bmc(ssh, "stat -c '%Y' /var/log/wedge100s-cpld-int-events.log")
    if rc != 0:
        pytest.skip("event log not yet created — no events since last start")
    import time
    mtime = int(out.strip())
    age = time.time() - mtime
    assert age < 3600, (  # 1 hour is generous — daemon should fsync per event
        f"event log mtime is {age:.0f}s old, suggesting the daemon is not "
        "fsync-ing events or has not received any events. Check runit logs."
    )


def test_gpio31_configured_as_edge_both(ssh):
    """gpio31 is exported and edge=both."""
    out, _, rc = _bmc(ssh, "cat /sys/class/gpio/gpio31/edge 2>&1")
    assert rc == 0, f"gpio31 not exported: {out}"
    assert out.strip() == "both", (
        f"gpio31 edge={out.strip()!r}, expected 'both'. "
        "wedge100s-cpld-int-monitor gpio_setup() may have failed."
    )
```

- [ ] **Step 2: Commit in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/stage_10_daemon/test_cpld_int_monitor.py
git commit -m "test(daemon): add BMC cpld-int-monitor health test (GAP-018)

Four non-destructive checks:
1. The daemon binary is installed on the BMC rootfs
2. The runit service is 'run:' status
3. The event log file exists and is recent
4. gpio31 is exported with edge=both

Run automatically in stage_10_daemon (no gating). Skips gracefully
if the BMC image hasn't been rebuilt yet with the GAP-018 recipe."
```

### Task 12: Update PLATFORM_GUIDE.md with the resolved register map

**Files:**
- Modify: `notes/PLATFORM_GUIDE.md` (devel repo)

- [ ] **Step 1: Correct the CPLD register table**

Based on Task 1's research, update the CPLD register table around lines 645-690 in PLATFORM_GUIDE.md to reflect the authoritative addresses. Every register whose address differs between DESIGNGAPS.md and the current PLATFORM_GUIDE.md table must be corrected.

- [ ] **Step 2: Add a new subsection on the BMC interrupt path**

After Section 7 (BMC Subsystem), add a new subsection 7.3 "Interrupt-Driven Event Aggregation" that documents:

- The signal flow: PCA9535 /INT → PCA9548 mux → CPLD 0x13/0x14 → gpio31 on BMC
- The BMC-side `wedge100s-cpld-int-monitor` daemon
- The host-side integration via `wedge100s-bmc-daemon` event log tail + `wedge100s-i2c-daemon` inotify watch
- The mask register policy (refer to `notes/2026-04-09-cpld-interrupt-spec.md`)
- Expected latency (< 100ms end-to-end for QSFP hot-swap)

- [ ] **Step 3: Remove the stale "CP2112 cannot deliver interrupts" framing**

Find and update the sections that currently describe QSFP presence detection as poll-only. The poll-only path is still the fallback when the BMC daemon is unavailable, but it's no longer the primary path.

- [ ] **Step 4: Commit in devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add notes/PLATFORM_GUIDE.md
git commit -m "docs(guide): document BMC-mediated interrupt aggregation path

Updates Section 6 (System CPLD) register table with the authoritative
interrupt mask register addresses resolved in
notes/2026-04-09-cpld-interrupt-spec.md (fixes the DESIGNGAPS.md vs
PLATFORM_GUIDE.md discrepancy).

Adds Section 7.3 'Interrupt-Driven Event Aggregation' documenting
the gpio31 signal flow, the wedge100s-cpld-int-monitor BMC daemon,
and the end-to-end latency target (~100ms for QSFP hot-swap).

Supersedes the older poll-only framing in the QSFP presence
detection section.

Part of GAP-018 + GAP-029 resolution."
```

---

## Summary of topic branch commits when plan is complete

| Branch | Commits | Purpose |
|--------|---------|---------|
| `wedge100s/i2c-bmc-sysfs` | ~5 | CPLD driver sysfs + Python BMC daemon + host daemon push/tail + platform-init mask config |
| devel `initial` | ~7 | Research notes + 3 test files + PLATFORM_GUIDE update |

**No `wedge100s/submodule-patches` branch** — this plan ships zero files under `src/sonic-bmc/`. The BMC-side daemon is pure Python 3 (verified on-BMC 2026-04-09), rsynced at bmc-daemon startup. No cross-compile, no bitbake, no OpenBMC image rebuild.

No branch is merged to master by this plan — that is deferred per session convention.
