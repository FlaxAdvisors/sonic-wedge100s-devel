# Hardware Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two remaining validation gaps that require hands-on hardware testing: QSFP lane-swap audit against OCP spec Table 10 (GAP-003, P0 correctness) and CPLD fan heartbeat / HEART_ATTACK_EN interaction (GAP-015, P1 production-readiness).

**Architecture:** Both tasks are primarily investigation + documentation + test, with potential BCM config or CPLD register changes depending on findings. GAP-003 cross-references the OCP spec's 32-port lane assignment table against the current BCM config polarity-flip settings. GAP-015 probes CPLD register 0x2E[7] and tests the hardware fan-failure shutdown mechanism. Both require SSH access to live hardware and careful sequencing (stop daemons before direct I2C access per CLAUDE.md I2C bus safety rules).

**Tech Stack:** BCM diag shell (PRBS testing), SSH to SONiC switch (192.168.88.12), SSH to BMC (192.168.88.13), pytest (hardware tests), OCP spec v1.3 PDF (`misc/Wedge100S_OCP_Spec_v1_3.pdf`)

**Platform fork:** `/export/sonic/sonic-buildimage/`
**Device config prefix:** `device/accton/x86_64-accton_wedge100s_32x-r0/`
**Devel repo:** `/export/sonic/sonic-wedge100s-devel/`

**SAFETY WARNING:** Task 2 (fan heartbeat) may cause unexpected power shutdown if HEART_ATTACK_EN is active and fans are removed. Only perform during a maintenance window with physical access to the switch.

---

## Workflow Compliance

Every task that modifies `sonic-buildimage` MUST follow `docs/workflow.md`:

1. **Invoke `wedge100s-topic-branches` skill** before touching any file in the platform fork.
2. **Work on the owning topic branch.** See ownership table below.
3. **Sync with master first:** `git checkout wedge100s/<topic> && git merge origin/master --no-edit`
4. **Conventional commits:** `fix(<scope>): ...`, `feat(<scope>): ...`
5. **Invoke `wedge100s-doc-check` skill** before every commit touching `.py` or `.c` files.
6. **Push, then merge:** `git push origin wedge100s/<topic>` → `git checkout master` → `git merge origin/wedge100s/<topic> --no-edit` → `git push origin master`
7. **Invoke `wedge100s-build-verify` skill** after merging to master.

### Topic Branch Ownership (this plan)

| Task | Gap | Topic Branch | Owns |
|------|-----|-------------|------|
| 1 | GAP-003 | `wedge100s/chipset-config` | `*.config.bcm`, `led_proc_init.soc` |
| 2 | GAP-015 | `wedge100s/i2c-bmc-sysfs` | `modules/wedge100s_cpld.c`, `utils/wedge100s-platform-init.sh` |

### Test Placement (this plan)

Tests live in `sonic-wedge100s-devel` only (workflow anti-pattern #4). New tests go into **existing stage directories**. `run_tests.py` discovers them automatically via `stage_*` glob.

| Test File | Stage | Covers |
|-----------|-------|--------|
| `tests/stage_03_platform/test_lane_swap_audit.py` | stage_03_platform | GAP-003 (PRBS validation) |
| `tests/stage_05_fan/test_heart_attack.py` | stage_05_fan | GAP-015 (HEART_ATTACK_EN register state) |

Reporters in `tests/lib/report.py` are updated to display the new data.

---

### Task 1: Audit QSFP lane-swap and polarity-flip against OCP Table 10

**Gap:** GAP-003 (P0 — Correctness)
**Topic branch:** `wedge100s/chipset-config`
**Files:**
- Read: `misc/Wedge100S_OCP_Spec_v1_3.pdf` (pages 25-38, Table 10)
- Modify (if mismatches found): `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm`

OCP spec Table 10 documents the physical QSFP connector wiring for all 32 ports. Connectors 2-7 have "QSFP CHANNELS SWAPPED WITHIN THE QUAD" annotations. The BCM config has per-port `phy_xaui_rx_polarity_flip`, `phy_xaui_tx_polarity_flip`, `xgxs_rx_lane_map`, and `xgxs_tx_lane_map` — these must match the physical wiring.

- [ ] **Step 1: Checkout topic branch and sync**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/chipset-config
git merge origin/master --no-edit
```

- [ ] **Step 2: Extract OCP Table 10 lane assignments**

Read the OCP spec PDF (`misc/Wedge100S_OCP_Spec_v1_3.pdf`, pages 25-38). For each of the 32 physical QSFP connectors, record:

| Column | Data |
|--------|------|
| Physical connector # | 1-32 |
| SONiC interface name | Ethernet0..124 (×4) |
| BCM port number | From led_proc_init.soc mapping |
| First serdes lane | From portmap |
| RX lane swap? | yes/no, which lanes |
| TX lane swap? | yes/no, which lanes |
| RX polarity flip bitmask | per-lane |
| TX polarity flip bitmask | per-lane |

Write the full table to `notes/2026-04-09-lane-swap-audit.md` in the devel repo.

- [ ] **Step 3: Extract current BCM config settings**

```bash
cd /export/sonic/sonic-buildimage
grep -E 'polarity_flip|lane_map' \
  device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm \
  | sort > /tmp/bcm_lane_settings.txt
cat /tmp/bcm_lane_settings.txt
```

Build a per-port table from these settings:
- `phy_xaui_rx_polarity_flip_<port>.0` — 4-bit bitmask
- `phy_xaui_tx_polarity_flip_<port>.0` — same for TX
- `xgxs_rx_lane_map_<port>.0` — 4-digit hex (e.g., 0x3210 = identity, 0x1032 = swap pairs)
- `xgxs_tx_lane_map_<port>.0` — same for TX

- [ ] **Step 4: Cross-reference OCP spec vs BCM config**

For each of the 32 ports, compare lane map and polarity flip against OCP spec. Create comparison table in the notes file:

```markdown
| Phys | SONiC | BCM | OCP RX Swap | Config RX Map | Match? | OCP RX Pol | Config RX Pol | Match? |
|------|-------|-----|-------------|---------------|--------|------------|---------------|--------|
| 1    | Eth0  | 118 | No          | 0x2301        | ?      | 0x0        | 0x0           | ?      |
| ...  | ...   | ... | ...         | ...           | ...    | ...        | ...           | ...    |
```

List all mismatches with current value vs expected value.

- [ ] **Step 5: Verify with PRBS on suspect ports**

For mismatched ports (and controls), run PRBS via BCM diag shell:

```bash
ssh admin@192.168.88.12
docker exec -it syncd bash

# For each port under test:
bcmcmd 'phy ce0 prbs set mode=phy polynomial=p31 invert=0'
sleep 30
bcmcmd 'phy ce0 prbs get'
# Non-zero errors indicate lane swap or polarity mismatch.
bcmcmd 'phy ce0 prbs clear'
exit
```

**Prerequisite:** PRBS requires peer running PRBS or loopback modules.

Record PRBS results in `notes/2026-04-09-lane-swap-audit.md`.

- [ ] **Step 6: Apply corrections (if mismatches found)**

For each confirmed mismatch, update `th-wedge100s-32x-flex.config.bcm` with a comment referencing the OCP spec table and page number.

- [ ] **Step 7: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 8: Deploy and verify corrected ports**

Install updated platform .deb, reboot, and verify:
1. All 32 ports link up
2. PRBS on corrected ports shows zero errors
3. No regression on previously-working ports

Run existing tests:

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_13_link/ -v      # Link-up verification
pytest tests/stage_20_traffic/ -v   # Traffic forwarding
```

- [ ] **Step 9: Write test — `tests/stage_03_platform/test_lane_swap_audit.py`**

```python
"""Stage 03 supplement — QSFP lane-swap and polarity-flip validation.

GAP-003: Run PRBS31 on populated ports and check for zero errors,
validating that BCM config lane maps and polarity flips match the
physical QSFP connector wiring per OCP spec Table 10.

Requires loopback modules or a cooperating peer running PRBS.
"""

import time
import pytest

NUM_PORTS = 32
PRBS_DURATION_S = 10
RUN_DIR = "/run/wedge100s"

# BCM port numbers from led_proc_init.soc mapping.
# SONiC Ethernet(N*4) → BCM port.
SONIC_TO_BCM = {
    0: 118, 4: 122, 8: 126, 12: 130,
    16: 1,  20: 5,  24: 9,  28: 13,
    32: 17, 36: 21, 40: 25, 44: 29,
    48: 34, 52: 38, 56: 42, 60: 46,
    64: 50, 68: 54, 72: 58, 76: 62,
    80: 68, 84: 72, 88: 76, 92: 80,
    96: 84, 100: 88, 104: 92, 108: 96,
    112: 102, 116: 106, 120: 110, 124: 114,
}


def _populated_ports(ssh):
    """Return list of populated SONiC port indices (multiples of 4)."""
    ports = []
    for sonic_idx in range(0, 128, 4):
        sfp_idx = sonic_idx // 4
        out, _, rc = ssh.run(
            f"cat {RUN_DIR}/sfp_{sfp_idx}_present 2>/dev/null", timeout=5)
        if rc == 0 and out.strip() == '1':
            ports.append(sonic_idx)
    return ports


def test_prbs_zero_errors(ssh):
    """Run PRBS31 on all populated ports; expect zero errors.

    Non-zero errors indicate lane swap or polarity mismatch.
    Skip if no populated ports or if PRBS is not supported on the peer side.
    """
    populated = _populated_ports(ssh)
    if not populated:
        pytest.skip("No populated QSFP ports")

    print(f"  Testing {len(populated)} populated ports")

    # Start PRBS on all populated ports.
    for sonic_idx in populated:
        bcm_port = SONIC_TO_BCM.get(sonic_idx)
        if bcm_port is None:
            continue
        ssh.run(
            f"docker exec syncd bcmcmd 'phy ce{bcm_port} prbs set "
            f"mode=phy polynomial=p31 invert=0'",
            timeout=10)

    time.sleep(PRBS_DURATION_S)

    # Read error counts.
    errors = {}
    for sonic_idx in populated:
        bcm_port = SONIC_TO_BCM.get(sonic_idx)
        if bcm_port is None:
            continue
        out, _, _ = ssh.run(
            f"docker exec syncd bcmcmd 'phy ce{bcm_port} prbs get'",
            timeout=10)
        print(f"  Ethernet{sonic_idx} (ce{bcm_port}): {out.strip()}")
        # Parse for non-zero error counts.
        if "error" in out.lower():
            for token in out.split():
                if token.isdigit() and int(token) > 0:
                    errors[sonic_idx] = out.strip()
                    break

    # Clear PRBS on all ports.
    for sonic_idx in populated:
        bcm_port = SONIC_TO_BCM.get(sonic_idx)
        if bcm_port is None:
            continue
        ssh.run(
            f"docker exec syncd bcmcmd 'phy ce{bcm_port} prbs clear'",
            timeout=10)

    assert not errors, (
        f"PRBS errors on {len(errors)} ports — possible lane swap "
        f"or polarity mismatch:\n" +
        "\n".join(f"  Ethernet{k}: {v}" for k, v in errors.items())
    )
```

- [ ] **Step 10: Run wedge100s-doc-check on modified files**

Invoke `wedge100s-doc-check` skill to verify any added comments in the BCM config are well-formed and test file docstrings are present.

- [ ] **Step 11: Commit platform fork (only if changes made)**

```bash
cd /export/sonic/sonic-buildimage
git add device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm
git commit -m "fix(chipset): correct lane-swap/polarity-flip per OCP Table 10

Cross-referenced all 32 ports against OCP spec v1.3 Table 10.
Corrected [describe corrections]. Confirmed with PRBS31 zero-error
testing on hardware.

Closes: GAP-003"
git push origin wedge100s/chipset-config
git checkout master && git merge origin/wedge100s/chipset-config --no-edit && git push origin master
```

Invoke `wedge100s-build-verify` skill.

- [ ] **Step 12: Commit devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
git add tests/stage_03_platform/test_lane_swap_audit.py \
        notes/2026-04-09-lane-swap-audit.md
git commit -m "test(platform): add QSFP lane-swap/polarity-flip PRBS validation

Cover GAP-003 (P0 correctness) in stage_03_platform. PRBS31 on
populated ports verifies lane maps and polarity flips match OCP
spec Table 10. Includes full 32-port audit table in notes."
```

---

### Task 2: Test fan heartbeat / HEART_ATTACK_EN interaction

**Gap:** GAP-015 (P1 — Production-Readiness)
**Topic branch:** `wedge100s/i2c-bmc-sysfs`
**Files:**
- Modify (if sysfs attribute needed): `platform/.../modules/wedge100s_cpld.c`
- Modify (if policy change needed): `platform/.../utils/wedge100s-platform-init.sh`
- Update: `notes/PLATFORM_GUIDE.md` (Fan System section)

**SAFETY WARNING:** This task may cause the switch to lose power during testing. Only perform with physical access and serial console running (`ssh bang-lorax tail -f screenlog.ttyUSB2.0`).

- [ ] **Step 1: Checkout topic branch and sync**

```bash
cd /export/sonic/sonic-buildimage
git checkout wedge100s/i2c-bmc-sysfs
git merge origin/master --no-edit
```

- [ ] **Step 2: Read HEART_ATTACK_EN boot default**

```bash
ssh admin@192.168.88.12
# Try sysfs first, then fall back to direct i2c-dev
cat /sys/bus/i2c/devices/1-0032/heart_attack_en 2>/dev/null || \
  i2cget -y -f 1 0x32 0x2e
# Extract bit 7: (value >> 7) & 1
```

Record the boot-default value.

- [ ] **Step 3: Read fan heartbeat status**

```bash
ssh admin@192.168.88.12
# Verify all 5 fan trays present
cat /run/wedge100s/fan_present
# Expect 0x1F (all 5 present)

# Check fan controller on BMC
sshpass -p '0penBmc' ssh root@192.168.88.13 \
  'i2cget -y 8 0x33 0x00' 2>/dev/null
```

- [ ] **Step 4: Test with one fan tray removed (safe test)**

Start serial console monitoring:

```bash
# In another terminal:
ssh bang-lorax tail -f screenlog.ttyUSB2.0
```

On the switch:

```bash
watch -n 1 'cat /run/wedge100s/fan_present; echo "---"; \
  cat /run/wedge100s/fan_*_front 2>/dev/null'
```

Physically remove one fan tray. Observe:
1. Does `fan_present` bitmask update within 10s?
2. Does thermalctld ramp remaining fans?
3. Does CPLD shut down power? (Expected: no — only all-fans triggers HEART_ATTACK)

Reinsert fan tray.

- [ ] **Step 5: Test all-fans-removed scenario**

**Option A (safe): Disable HEART_ATTACK first, then remove all fans**

```bash
ssh admin@192.168.88.12
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

CURRENT=$(i2cget -y -f 1 0x32 0x2e)
echo "Current 0x2E: $CURRENT"
NEW=$(printf '0x%02x' $(( $(echo $CURRENT) & 0x7f )))
i2cset -y -f 1 0x32 0x2e $NEW

sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

Remove all 5 fans one by one. Record:
- Time from last-fan-removal to thermalctld alarm
- Thermalctld behavior (ramp to 100%, eventual shutdown?)
- CPLD behavior (no shutdown since disabled)
- Thermal sensor readings

**Option B (characterize shutdown): Test with HEART_ATTACK enabled**

Only if you want exact CPLD shutdown timing. Ensure serial console is capturing. Remove all fans rapidly. Record time-to-shutdown.

- [ ] **Step 6: Decide HEART_ATTACK policy**

| Finding | Recommended Policy |
|---------|-------------------|
| HEART_ATTACK_EN=0 at boot | Leave disabled, thermalctld handles fan failure |
| HEART_ATTACK_EN=1 + thermalctld shuts down faster | Leave enabled, both provide defense-in-depth |
| HEART_ATTACK_EN=1 + CPLD shuts down faster | Either disable in platform-init or ensure thermalctld timeout < CPLD timeout |

- [ ] **Step 7: Add sysfs attribute for HEART_ATTACK_EN (if not already exposed)**

Check if `heart_attack_en` already exists in the CPLD sysfs attribute list:

```bash
ssh admin@192.168.88.12
ls /sys/bus/i2c/devices/1-0032/heart_attack_en 2>/dev/null && echo EXISTS || echo MISSING
```

If MISSING, add to `modules/wedge100s_cpld.c`:

```c
#define REG_FAN_CTRL      0x2E
#define HEART_ATTACK_BIT   7

/**
 * @brief Show HEART_ATTACK_EN status (1=enabled, 0=disabled).
 * @param dev   Device structure.
 * @param attr  Device attribute.
 * @param buf   Output buffer.
 * @return Number of bytes written, or negative errno.
 */
static ssize_t show_heart_attack_en(struct device *dev,
                                     struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_FAN_CTRL);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n",
                     (val >> HEART_ATTACK_BIT) & 1);
}

/**
 * @brief Set HEART_ATTACK_EN (write 0 or 1).
 * @param dev   Device structure.
 * @param attr  Device attribute.
 * @param buf   Input buffer (ASCII "0" or "1").
 * @param count Number of input bytes.
 * @return count on success, negative errno on failure.
 */
static ssize_t set_heart_attack_en(struct device *dev,
                                    struct device_attribute *attr,
                                    const char *buf, size_t count)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    unsigned long val;
    int cur, rc;

    rc = kstrtoul(buf, 10, &val);
    if (rc || val > 1)
        return -EINVAL;

    mutex_lock(&data->update_lock);
    cur = cpld_read(client, REG_FAN_CTRL);
    if (cur < 0) {
        mutex_unlock(&data->update_lock);
        return cur;
    }
    if (val)
        cur |= (1 << HEART_ATTACK_BIT);
    else
        cur &= ~(1 << HEART_ATTACK_BIT);
    rc = cpld_write(client, REG_FAN_CTRL, cur);
    mutex_unlock(&data->update_lock);

    return rc < 0 ? rc : count;
}

static DEVICE_ATTR(heart_attack_en, S_IRUGO | S_IWUSR,
                   show_heart_attack_en, set_heart_attack_en);
```

Add `&dev_attr_heart_attack_en.attr` to the attribute group array.

- [ ] **Step 8: Implement chosen policy in platform-init (if needed)**

If policy decision is to disable HEART_ATTACK_EN at boot, add to `utils/wedge100s-platform-init.sh` (after CPLD driver loads):

```bash
# Disable CPLD hardware fan-failure power shutdown.
# thermalctld handles fan failure detection and shutdown.
# See notes/PLATFORM_GUIDE.md section 9 for rationale.
echo 0 > /sys/bus/i2c/devices/1-0032/heart_attack_en
```

- [ ] **Step 9: Run wedge100s-doc-check, build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 10: Commit, push, merge**

```bash
cd /export/sonic/sonic-buildimage
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules/wedge100s_cpld.c
# If platform-init was modified:
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-platform-init.sh
git commit -m "feat(cpld): expose HEART_ATTACK_EN sysfs + set production policy

Add read/write sysfs attribute for CPLD register 0x2E[7] controlling
hardware fan-failure power shutdown. Boot default: [0 or 1].
Production policy: [describe decision and rationale].

Closes: GAP-015"
git push origin wedge100s/i2c-bmc-sysfs
git checkout master && git merge origin/wedge100s/i2c-bmc-sysfs --no-edit && git push origin master
```

Invoke `wedge100s-build-verify` skill.

- [ ] **Step 11: Update PLATFORM_GUIDE.md Fan System section (in devel repo)**

In `notes/PLATFORM_GUIDE.md`, update the Fan System section (section 9) to document:
1. Boot default of register 0x2E[7]
2. CPLD HEART_ATTACK shutdown timing (from testing)
3. Interaction with SONiC thermalctld
4. Production policy decision and rationale

- [ ] **Step 12: Write test — `tests/stage_05_fan/test_heart_attack.py`**

```python
"""Stage 05 supplement — CPLD HEART_ATTACK_EN status and policy.

GAP-015: Verify that the HEART_ATTACK_EN register is in the expected
state per the production policy. This test does NOT remove fans —
it only checks the register value.
"""

import pytest

RUN_DIR = "/run/wedge100s"

# Expected policy value — update after Step 6 decision:
#   0 = disabled (thermalctld handles fan failure)
#   1 = enabled (CPLD and thermalctld both provide protection)
EXPECTED_VALUE = None  # SET THIS after policy decision


def test_heart_attack_en_readable(ssh):
    """HEART_ATTACK_EN should be readable from daemon cache or sysfs."""
    # Try daemon cache first, then sysfs
    out, _, rc = ssh.run(
        f"cat {RUN_DIR}/heart_attack_en 2>/dev/null || "
        f"cat /sys/bus/i2c/devices/1-0032/heart_attack_en 2>/dev/null",
        timeout=10)
    assert rc == 0, (
        "Cannot read heart_attack_en — is CPLD driver loaded "
        "with the attribute? Check: ls /sys/bus/i2c/devices/1-0032/"
    )
    val = out.strip()
    assert val in ('0', '1'), (
        f"HEART_ATTACK_EN = {val!r}, expected '0' or '1'"
    )
    print(f"  HEART_ATTACK_EN = {val}")


def test_heart_attack_en_policy(ssh):
    """HEART_ATTACK_EN should match production policy."""
    if EXPECTED_VALUE is None:
        pytest.skip(
            "EXPECTED_VALUE not set — update after policy decision "
            "(GAP-015 Task 2 Step 6)"
        )
    out, _, rc = ssh.run(
        f"cat {RUN_DIR}/heart_attack_en 2>/dev/null || "
        f"cat /sys/bus/i2c/devices/1-0032/heart_attack_en 2>/dev/null",
        timeout=10)
    if rc != 0:
        pytest.skip("heart_attack_en not available")
    val = int(out.strip())
    assert val == EXPECTED_VALUE, (
        f"HEART_ATTACK_EN = {val}, expected {EXPECTED_VALUE} per policy. "
        "Check platform-init script."
    )


def test_fan_present_all(ssh):
    """All 5 fan trays should be present (prerequisite for heartbeat)."""
    out, _, rc = ssh.run(f"cat {RUN_DIR}/fan_present", timeout=10)
    assert rc == 0, "Cannot read fan_present"
    present = int(out.strip(), 0)
    assert present == 0x1f, (
        f"fan_present = 0x{present:02x}, expected 0x1f (all 5 trays). "
        "Missing fan trays affect heartbeat behavior."
    )
```

- [ ] **Step 13: Update reporter — add HEART_ATTACK_EN to `report_fan()`**

In `tests/lib/report.py`, locate `report_fan()` and append:

```python
    # HEART_ATTACK_EN (GAP-015)
    out, _, rc = ssh.run(
        "cat /run/wedge100s/heart_attack_en 2>/dev/null || "
        "cat /sys/bus/i2c/devices/1-0032/heart_attack_en 2>/dev/null",
        timeout=10)
    if rc == 0:
        val = out.strip()
        status = "enabled (CPLD will shut down on all-fan failure)" if val == '1' \
            else "disabled (thermalctld handles fan failure)"
        print(f"\n  HEART_ATTACK_EN : {val} — {status}")
```

- [ ] **Step 14: Update CPLD sysfs attr list in `tests/stage_09_cpld/test_cpld.py`**

If the `heart_attack_en` attribute was added to the CPLD driver, add it to the `SYSFS_ATTRS` list in `test_cpld.py` (line 41) so the "all attributes readable" test covers it:

```python
SYSFS_ATTRS = [
    # ... existing attrs ...
    "heart_attack_en",
]
```

- [ ] **Step 15: Run tests and commit devel repo**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_05_fan/test_heart_attack.py -v
pytest tests/stage_09_cpld/test_cpld.py -v
./run_tests.py --report stage_05_fan

git add tests/stage_05_fan/test_heart_attack.py \
        tests/stage_09_cpld/test_cpld.py \
        tests/lib/report.py \
        notes/PLATFORM_GUIDE.md
git commit -m "test(fan): add HEART_ATTACK_EN validation and update reporters

Cover GAP-015 in stage_05_fan. Documents boot default, CPLD shutdown
timing, thermalctld interaction, and production policy. Updates
report_fan() and stage_09_cpld attribute list."
```
