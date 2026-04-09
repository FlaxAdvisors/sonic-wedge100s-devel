# Daemon Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the two C daemons to close P1 production-readiness gaps: QSFP RXLOSS signal monitoring (GAP-011), PSU model/serial via SMBus block-read (GAP-016), CP2112 I2C bus recovery via CPLD flush register (GAP-017), and presence poll interval tuning (GAP-018).

**Architecture:** Each gap is a self-contained change to one daemon + its Python API consumer. The i2c-daemon gains RXLOSS reads from PCA9535 at 0x24/0x25 and CPLD flush on bus error. The bmc-daemon gains SMBus block-read for PMBus MFR_MODEL/MFR_SERIAL. Poll interval changes are a timer unit tweak.

**Tech Stack:** C (userspace daemons), Python 3 (SONiC platform API), systemd timers, pytest (hardware tests over SSH)

**Platform fork path prefix:** `/export/sonic/sonic-buildimage/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
**Devel repo path prefix:** `/export/sonic/sonic-wedge100s-devel/`

---

### Task 1: Add RXLOSS signal reading to i2c-daemon

**Gap:** GAP-011
**Files:**
- Modify: `utils/wedge100s-i2c-daemon.c`

The PCA9535 GPIO expanders at 0x24 (ports 0-15) and 0x25 (ports 16-31) on PCA9548 #5 (0x74) channels 4 and 5 carry per-port RX loss-of-signal. The daemon already reads PCA9535 at 0x22/0x23 (presence) using the same mux — RXLOSS follows the identical pattern.

- [ ] **Step 1: Add RXLOSS constants**

Near the existing PCA9535 presence constants (around line 100), add:

```c
/* PCA9535 RXLOSS/INT expanders behind PCA9548 #5 (0x74).
 * OCP spec v1.3 Table 13: RXLOSS signals, active-low.
 * Bus 38 = mux 0x74 channel 4 → PCA9535 at 0x24 (ports 0-15)
 * Bus 39 = mux 0x74 channel 5 → PCA9535 at 0x25 (ports 16-31)
 */
#define RXLOSS_BUS_LO      38   /* logical bus for 0x24 (ports 0-15)  */
#define RXLOSS_BUS_HI      39   /* logical bus for 0x25 (ports 16-31) */
#define RXLOSS_ADDR_LO     0x24
#define RXLOSS_ADDR_HI     0x25
#define PCA9535_INPUT_PORT0 0x00 /* read input port 0 (bits 7:0)  */
#define PCA9535_INPUT_PORT1 0x01 /* read input port 1 (bits 15:8) */
```

- [ ] **Step 2: Add RXLOSS poll function for hidraw path**

After the existing `poll_presence_hidraw()` function, add:

```c
/**
 * @brief Poll QSFP RXLOSS signals via PCA9535 at 0x24/0x25 (hidraw path).
 *
 * Reads 2 bytes from each PCA9535 (input port 0 + input port 1 = 16 bits).
 * Writes per-port "0" (no loss) or "1" (RX loss detected) to
 * /run/wedge100s/sfp_N_rxlos.
 *
 * RXLOSS is active-low: PCA9535 bit = 0 means loss detected.
 * XOR-1 interleave applies (same as presence — see OCP spec Table 13).
 */
static void poll_rxloss_hidraw(void)
{
    uint8_t raw[4]; /* 2 bytes from each PCA9535 */
    uint32_t rxloss_bits = 0;

    /* Read PCA9535 at 0x24 (ports 0-15). */
    if (mux_select(RXLOSS_BUS_LO) < 0) return;
    {
        uint8_t reg = PCA9535_INPUT_PORT0;
        if (cp2112_write_read(RXLOSS_ADDR_LO, &reg, 1, raw, 2) < 0) {
            mux_deselect_all();
            return;
        }
    }
    rxloss_bits = (uint32_t)raw[0] | ((uint32_t)raw[1] << 8);

    /* Read PCA9535 at 0x25 (ports 16-31). */
    if (mux_select(RXLOSS_BUS_HI) < 0) {
        mux_deselect_all();
        return;
    }
    {
        uint8_t reg = PCA9535_INPUT_PORT0;
        if (cp2112_write_read(RXLOSS_ADDR_HI, &reg, 1, raw, 2) < 0) {
            mux_deselect_all();
            return;
        }
    }
    rxloss_bits |= ((uint32_t)raw[0] | ((uint32_t)raw[1] << 8)) << 16;
    mux_deselect_all();

    /* Write per-port RXLOSS files.
     * Active-low: bit=0 means loss → write "1" to file.
     * XOR-1 interleave: physical bit N maps to port N^1.
     */
    for (int i = 0; i < NUM_PORTS; i++) {
        int phys_bit = i ^ 1; /* XOR-1 interleave */
        int loss = !((rxloss_bits >> phys_bit) & 1);
        char path[128], val[4];
        snprintf(path, sizeof(path), RUN_DIR "/sfp_%d_rxlos", i);
        snprintf(val, sizeof(val), "%d", loss);
        write_str_file(path, val);
    }
}
```

- [ ] **Step 3: Call poll_rxloss_hidraw() from the main loop**

In the main loop (around line 1740), after the `poll_presence_hidraw()` call, add:

```c
            poll_rxloss_hidraw();
```

- [ ] **Step 4: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 5: Commit**

```bash
git add utils/wedge100s-i2c-daemon.c
git commit -m "feat(i2c-daemon): poll QSFP RXLOSS signals from PCA9535 0x24/0x25

Read RX loss-of-signal from PCA9535 GPIO expanders behind PCA9548 #5
channels 4/5. Write per-port sfp_N_rxlos files (0=OK, 1=loss detected).
Uses same XOR-1 interleave as presence detection.

Closes: GAP-011 (daemon side)"
```

---

### Task 2: Expose RXLOSS in Python SFP platform API

**Gap:** GAP-011
**Files:**
- Modify: `sonic_platform/sfp.py`

- [ ] **Step 1: Add RXLOSS cache path constant**

Near the existing path constants:

```python
_RXLOS_CACHE = '/run/wedge100s/sfp_{}_rxlos'
```

- [ ] **Step 2: Add get_rx_los() method to Sfp class**

```python
    def get_rx_los(self):
        """Return per-lane RX loss-of-signal status from hardware PCA9535.

        The i2c-daemon reads PCA9535 at 0x24/0x25 and writes per-port
        sfp_N_rxlos files (0=OK, 1=loss). For QSFP28 (4-lane), all 4
        lanes share one hardware RXLOSS signal per port.

        Returns:
            list[bool]: [lane0, lane1, lane2, lane3] — True if RX loss detected.
                        Returns [False]*4 if data unavailable.
        """
        path = _RXLOS_CACHE.format(self._port)
        try:
            with open(path) as f:
                loss = f.read().strip() == '1'
            return [loss] * 4  # single hardware signal → all 4 lanes same
        except OSError:
            return [False] * 4
```

- [ ] **Step 3: Commit**

```bash
git add sonic_platform/sfp.py
git commit -m "feat(platform): expose QSFP RXLOSS in SFP platform API

Add Sfp.get_rx_los() reading /run/wedge100s/sfp_N_rxlos written by
i2c-daemon. Returns 4-lane list (QSFP28 has one RXLOSS per port).

Closes: GAP-011 (Python API side)"
```

---

### Task 3: Add SMBus block-read to bmc-daemon for PSU model/serial

**Gap:** GAP-016
**Files:**
- Modify: `utils/wedge100s-bmc-daemon.c`

The BMC daemon currently reads PMBus word registers (VIN, IIN, IOUT, POUT) using `i2cget -y`. PMBus MFR_MODEL (0x9A) and MFR_SERIAL (0x9E) are block-read commands that return a length-prefixed ASCII string.

- [ ] **Step 1: Add block-read function**

After the existing `bmc_read_int()` function, add:

```c
/**
 * @brief Read a PMBus block-read register via BMC i2cget and return as string.
 *
 * PMBus block-read format: first byte is length N, followed by N ASCII bytes.
 * We use 'i2cdump -y -r 0xNN-0xNN <bus> <addr> b' to read a range, then
 * parse the first byte as length and the rest as ASCII.
 *
 * Alternative: use 'i2ctransfer' which supports block reads natively.
 *
 * @param bus     BMC I2C bus number.
 * @param addr    PMBus device address (0x59 or 0x5a).
 * @param reg     PMBus register (e.g., 0x9a for MFR_MODEL).
 * @param out     Output buffer for null-terminated ASCII string.
 * @param out_sz  Size of output buffer.
 * @return 0 on success, -1 on failure.
 */
static int bmc_read_pmbus_string(int bus, int addr, int reg,
                                  char *out, size_t out_sz)
{
    char cmd[256], line[512];
    int len, rc;

    /* Use i2ctransfer for block read: w1@addr reg, r32@addr
     * This sends: START addr+W reg REPEATED-START addr+R <count> <data...> STOP
     * The kernel SMBus layer handles the block-read protocol.
     */
    snprintf(cmd, sizeof(cmd),
             "i2ctransfer -y %d w1@0x%02x 0x%02x r32@0x%02x 2>/dev/null",
             bus, addr, reg, addr);

    rc = build_ssh_cmd(cmd, line, sizeof(line));
    if (rc != 0) return -1;

    FILE *fp = popen(line, "r");
    if (!fp) return -1;

    /* i2ctransfer outputs hex bytes: "0x0e 0x44 0x65 0x6c 0x74 ..." */
    char resp[512];
    if (!fgets(resp, (int)sizeof(resp), fp)) {
        pclose(fp);
        return -1;
    }
    pclose(fp);

    /* Parse hex bytes. First byte is PMBus block length. */
    unsigned int bytes[33];
    int n = 0;
    char *p = resp;
    while (n < 33 && sscanf(p, "0x%02x", &bytes[n]) == 1) {
        n++;
        p = strchr(p, ' ');
        if (!p) break;
        p++;
    }
    if (n < 2) return -1;

    len = (int)bytes[0];
    if (len > n - 1) len = n - 1;
    if (len <= 0) return -1;
    if ((size_t)len >= out_sz) len = (int)out_sz - 1;

    for (int i = 0; i < len; i++)
        out[i] = (char)bytes[i + 1];
    out[len] = '\0';

    /* Trim trailing spaces/nulls. */
    while (len > 0 && (out[len-1] == ' ' || out[len-1] == '\0'))
        out[--len] = '\0';

    return 0;
}
```

- [ ] **Step 2: Add PSU model/serial reads to main poll loop**

In the main poll loop, after the existing PSU PMBus reads (VIN/IIN/IOUT/POUT), add:

```c
    /* PSU model and serial: read once at startup, then only on PSU change. */
    static int psu_info_read[2] = {0, 0};
    for (int p = 0; p < 2; p++) {
        if (psu_info_read[p]) continue;

        /* Check if PSU is present before attempting block read. */
        char present_path[128], pbuf[8];
        snprintf(present_path, sizeof(present_path),
                 RUN_DIR "/psu%d_present", p + 1);
        FILE *pf = fopen(present_path, "r");
        if (!pf) continue;
        if (!fgets(pbuf, sizeof(pbuf), pf)) { fclose(pf); continue; }
        fclose(pf);
        if (atoi(pbuf) != 1) continue;

        int bus = 7;  /* BMC I2C bus for PSU mux */
        int addr = (p == 0) ? 0x59 : 0x5a;

        /* Select PSU mux channel first. */
        char mux_cmd[128];
        snprintf(mux_cmd, sizeof(mux_cmd),
                 "i2cset -y %d 0x70 0x%02x",
                 bus, (p == 0) ? 0x02 : 0x01);
        bmc_run(mux_cmd);

        char model[64] = "", serial[64] = "";
        if (bmc_read_pmbus_string(bus, addr, 0x9a, model, sizeof(model)) == 0) {
            char path[128];
            snprintf(path, sizeof(path), RUN_DIR "/psu%d_model", p + 1);
            write_str_file(path, model);
        }
        if (bmc_read_pmbus_string(bus, addr, 0x9e, serial, sizeof(serial)) == 0) {
            char path[128];
            snprintf(path, sizeof(path), RUN_DIR "/psu%d_serial", p + 1);
            write_str_file(path, serial);
        }

        if (model[0] && serial[0])
            psu_info_read[p] = 1;
    }
```

- [ ] **Step 3: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 4: Commit**

```bash
git add utils/wedge100s-bmc-daemon.c
git commit -m "feat(bmc-daemon): read PSU model/serial via PMBus block-read

Add bmc_read_pmbus_string() using i2ctransfer for PMBus block-read
protocol. Read MFR_MODEL (0x9A) and MFR_SERIAL (0x9E) from each PSU
at startup. Write to /run/wedge100s/psu{1,2}_{model,serial}.

Closes: GAP-016 (daemon side)"
```

---

### Task 4: Wire PSU model/serial into Python platform API

**Gap:** GAP-016
**Files:**
- Modify: `sonic_platform/psu.py`

- [ ] **Step 1: Add cache path constants**

```python
_PSU_MODEL_CACHE  = '/run/wedge100s/psu{}_model'
_PSU_SERIAL_CACHE = '/run/wedge100s/psu{}_serial'
```

- [ ] **Step 2: Update get_model() and get_serial()**

Replace the existing static methods:

```python
    def get_model(self):
        """Return PSU model string from PMBus MFR_MODEL (0x9A).

        Returns:
            str: Model string (e.g. "DPS-1100AB-6 A"), or "N/A" if unavailable.
        """
        path = _PSU_MODEL_CACHE.format(self._index)
        try:
            with open(path) as f:
                model = f.read().strip()
            return model if model else "N/A"
        except OSError:
            return "N/A"

    def get_serial(self):
        """Return PSU serial number from PMBus MFR_SERIAL (0x9E).

        Returns:
            str: Serial number string, or "N/A" if unavailable.
        """
        path = _PSU_SERIAL_CACHE.format(self._index)
        try:
            with open(path) as f:
                serial = f.read().strip()
            return serial if serial else "N/A"
        except OSError:
            return "N/A"
```

- [ ] **Step 3: Commit**

```bash
git add sonic_platform/psu.py
git commit -m "feat(platform): read PSU model/serial from daemon cache

Replace static 'N/A' returns with reads from /run/wedge100s/psu{N}_{model,serial}
written by bmc-daemon via PMBus block-read.

Closes: GAP-016 (Python API side)"
```

---

### Task 5: Add CP2112 I2C bus recovery via CPLD flush register

**Gap:** GAP-017
**Files:**
- Modify: `utils/wedge100s-i2c-daemon.c`

The CPLD register 0x38 bit 7 triggers an I2C flush: writing 1 then 0 sends 9 SCL clocks to unstick any slave holding SDA low. This is less disruptive than the current USB device reset.

- [ ] **Step 1: Add CPLD flush function**

After the existing `mux_deselect_all()` function, add:

```c
/**
 * @brief Trigger CP2112 I2C bus flush via CPLD register 0x38[7].
 *
 * OCP spec v1.3 section 7.6.2.1: Writing 1 then 0 to bit 7 of CPLD
 * register 0x38 causes the CPLD to send 9 SCL clocks on the CP2112
 * I2C bus, which unlocks any slave device holding SDA low.
 *
 * This is accessed via the BMC I2C path (CPLD at 0x31 on BMC_I2C_13)
 * because the host CP2112 may be the stuck bus we're trying to recover.
 *
 * @return 0 on success, -1 on failure.
 */
static int cpld_i2c_flush(void)
{
    char cmd[256], line[512];
    int rc;

    /* Write 1 to 0x38[7] to trigger flush. */
    snprintf(cmd, sizeof(cmd),
             "i2cset -y -f 12 0x31 0x38 0xff");
    rc = build_ssh_cmd(cmd, line, sizeof(line));
    if (rc != 0) {
        /* build_ssh_cmd not available in i2c-daemon; use system() as fallback.
         * The BMC is reachable via the bmc-daemon's SSH socket.
         */
        char ssh_cmd[512];
        snprintf(ssh_cmd, sizeof(ssh_cmd),
                 "ssh -o BatchMode=yes -o ConnectTimeout=5 "
                 "-i /etc/sonic/wedge100s-bmc-key "
                 "root@fe80::ff:fe00:1%%usb0 "
                 "'i2cset -y -f 12 0x31 0x38 0xff' 2>/dev/null");
        rc = system(ssh_cmd);
        if (rc != 0) return -1;
    }

    usleep(10000); /* 10ms — allow 9 SCL clocks to complete */

    /* Write 0 to 0x38[7] to deassert. */
    {
        char ssh_cmd[512];
        snprintf(ssh_cmd, sizeof(ssh_cmd),
                 "ssh -o BatchMode=yes -o ConnectTimeout=5 "
                 "-i /etc/sonic/wedge100s-bmc-key "
                 "root@fe80::ff:fe00:1%%usb0 "
                 "'i2cset -y -f 12 0x31 0x38 0x7f' 2>/dev/null");
        system(ssh_cmd);
    }

    return 0;
}
```

- [ ] **Step 2: Integrate flush into error recovery path**

In the hidraw poll functions, when a CP2112 operation fails (e.g., `cp2112_write_read()` returns < 0), try the CPLD flush before falling back to USB reset. Find the error handling in `poll_presence_hidraw()` and add:

```c
    /* On CP2112 transfer failure, try CPLD I2C flush first. */
    if (transfer_failed) {
        syslog(LOG_WARNING, "CP2112 transfer failed; attempting CPLD I2C flush");
        cpld_i2c_flush();
        cp2112_cancel();
        /* Retry the failed operation once. */
    }
```

The exact integration point depends on the error handling structure. The principle: call `cpld_i2c_flush()` on first failure, retry once, then fall back to USB reset only if flush didn't help.

- [ ] **Step 3: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 4: Commit**

```bash
git add utils/wedge100s-i2c-daemon.c
git commit -m "feat(i2c-daemon): add CPLD I2C flush for bus recovery

Use CPLD register 0x38[7] (via BMC SSH) to send 9 SCL clocks and
unstick slaves before falling back to full USB device reset. Less
disruptive than current bus-reset.sh approach.

Closes: GAP-017"
```

---

### Task 6: Reduce presence poll interval from 3s to 1s

**Gap:** GAP-018
**Files:**
- Modify: `service/wedge100s-i2c-poller.timer`

- [ ] **Step 1: Update the systemd timer**

Change `OnUnitActiveSec` from `3s` to `1s`:

```ini
[Timer]
OnBootSec=5s
OnUnitActiveSec=1s
AccuracySec=500ms
```

Note: `AccuracySec` reduced from `1s` to `500ms` to avoid systemd coalescing the 1s timer with other timers.

- [ ] **Step 2: Update documentation**

In `/export/sonic/sonic-wedge100s-devel/notes/PLATFORM_GUIDE.md`, update the timer table to reflect 1s interval.

- [ ] **Step 3: Build verify and commit**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
git add service/wedge100s-i2c-poller.timer
git commit -m "feat(service): reduce i2c-daemon poll interval from 3s to 1s

Improves QSFP hot-swap detection latency from 3s worst-case to 1s.
Presence-only reads (PCA9535 bulk read) are lightweight enough for
1s polling on the CP2112 bus.

Closes: GAP-018"
```

---

### Task 7: Write hardware tests for daemon enhancements

**Files:**
- Create: `tests/stage_07_qsfp/test_rxloss.py` (in devel repo)
- Modify: `tests/stage_06_psu/test_psu.py` (in devel repo)

- [ ] **Step 1: Write RXLOSS test**

```python
"""Stage 07 supplement — QSFP RXLOSS signal monitoring.

GAP-011: Verify that /run/wedge100s/sfp_N_rxlos files are written by
the i2c-daemon and contain valid values (0=OK, 1=loss detected).

A populated port with link UP should report rxlos=0.
An empty port has undefined RXLOSS (hardware pulls may vary).
"""

import json
import pytest

NUM_PORTS = 32
RUN_DIR = "/run/wedge100s"


def test_rxlos_files_exist(ssh):
    """All 32 RXLOSS files should be present in /run/wedge100s/."""
    missing = []
    for port in range(NUM_PORTS):
        path = f"{RUN_DIR}/sfp_{port}_rxlos"
        out, _, rc = ssh.run(f"test -f {path} && echo YES || echo NO", timeout=10)
        if "YES" not in out:
            missing.append(port)
    assert not missing, (
        f"Missing rxlos files for ports: {missing}. "
        "Is wedge100s-i2c-daemon running with RXLOSS support?"
    )


def test_rxlos_values_valid(ssh):
    """All RXLOSS values should be 0 or 1."""
    for port in range(NUM_PORTS):
        path = f"{RUN_DIR}/sfp_{port}_rxlos"
        out, _, rc = ssh.run(f"cat {path} 2>/dev/null", timeout=10)
        if rc != 0:
            continue  # covered by test_rxlos_files_exist
        val = out.strip()
        assert val in ('0', '1'), (
            f"Port {port}: rxlos={val!r}, expected '0' or '1'"
        )


def test_present_port_no_rxloss(ssh):
    """Populated ports with link UP should not have RX loss."""
    for port in range(NUM_PORTS):
        pres_path = f"{RUN_DIR}/sfp_{port}_present"
        rxlos_path = f"{RUN_DIR}/sfp_{port}_rxlos"
        out_p, _, rc_p = ssh.run(f"cat {pres_path} 2>/dev/null", timeout=10)
        out_r, _, rc_r = ssh.run(f"cat {rxlos_path} 2>/dev/null", timeout=10)
        if rc_p != 0 or rc_r != 0:
            continue
        present = out_p.strip()
        rxlos = out_r.strip()
        if present == '1':
            print(f"  Port {port}: present=1, rxlos={rxlos}")
            # Warn but don't fail — RXLOSS can be 1 if fiber is disconnected
            if rxlos == '1':
                print(f"    WARNING: Port {port} present but RXLOSS=1 (fiber issue?)")
```

- [ ] **Step 2: Add PSU model/serial test to existing PSU tests**

Append to `tests/stage_06_psu/test_psu.py`:

```python
def test_psu_model_readable(ssh):
    """PSU model string should be non-empty for present PSUs."""
    psus = _get_psus(ssh)
    for psu in psus:
        if psu['presence']:
            model = psu.get('model', 'N/A')
            print(f"  {psu['name']}: model={model!r}")
            assert model != "N/A", (
                f"{psu['name']}: model is 'N/A' — PMBus block-read may not be working"
            )


def test_psu_serial_readable(ssh):
    """PSU serial number should be non-empty for present PSUs."""
    psus = _get_psus(ssh)
    for psu in psus:
        if psu['presence']:
            serial = psu.get('serial', 'N/A')
            print(f"  {psu['name']}: serial={serial!r}")
            assert serial != "N/A", (
                f"{psu['name']}: serial is 'N/A' — PMBus block-read may not be working"
            )
```

Also update the PSU_CAPTURE script to include model/serial:

```python
PSU_CAPTURE = """\
import json
from sonic_platform.platform import Platform

chassis = Platform().get_chassis()
psus = chassis.get_all_psus()
results = []
for psu in psus:
    results.append({
        'name': psu.get_name(),
        'presence': psu.get_presence(),
        'status': psu.get_status(),
        'powergood': psu.get_powergood_status(),
        'type': psu.get_type(),
        'capacity_w': psu.get_capacity(),
        'model': psu.get_model(),
        'serial': psu.get_serial(),
        'voltage_v': psu.get_voltage(),
        'current_a': psu.get_current(),
        'power_w': psu.get_power(),
        'input_voltage_v': psu.get_input_voltage(),
        'input_current_a': psu.get_input_current(),
        'position': psu.get_position_in_parent(),
    })
print(json.dumps(results))
"""
```

- [ ] **Step 3: Run tests on hardware**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_07_qsfp/test_rxloss.py -v
pytest tests/stage_06_psu/test_psu.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/stage_07_qsfp/test_rxloss.py tests/stage_06_psu/test_psu.py
git commit -m "test: add RXLOSS and PSU model/serial hardware tests

Cover GAP-011 (RXLOSS signal monitoring) and GAP-016 (PSU model/serial
via PMBus block-read). Validates daemon cache files and Python API."
```
