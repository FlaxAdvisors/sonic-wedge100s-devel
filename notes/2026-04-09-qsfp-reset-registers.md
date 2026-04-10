# QSFP per-port hardware reset — hardware probe findings (GAP-026)

Date: 2026-04-09
Target: hare-lorax (192.168.88.12), BMC 192.168.88.13
Status: **BLOCKED** — no per-port QSFP reset path found on Wedge 100S-32X

## Task

The P2 plan (Task 3) proposed that QSFP_RST_N[1:32] lines could be driven
via the BMC-side SYSCPLD at CPLD register 0x34-0x37 (4 bytes x 8 bits = 32
ports), bus "BMC_I2C_12" at CPLD address 0x31, assuming 1-indexed bus
naming. This file captures the probe results that invalidate that
hypothesis.

## Hardware probe (daemons stopped on both sides)

### BMC i2c bus listing

```
i2c-0 .. i2c-13   AST I2C adapters
i2c-14 .. i2c-21  i2c-7-mux (PSU PMBus mux)
```

Linux bus numbering is 0-indexed; the OCP spec name "BMC_I2C_12" maps to
Linux `i2c-12` on this platform (no +/-1 offset — both are 0-indexed when
you read `i2cdetect -l`).

### CPLD address scan

```
i2c-11: nothing at 0x30-0x32
i2c-12: UU at 0x31  <-- SYSCPLD, owned by wedge100s_cpld driver
i2c-13: killed by timeout after previous scan
```

CPLD responds on **BMC i2c-12 at 0x31** (same chip, different address, also
accessible from host CPU via CP2112 i2c-1 at 0x32 — the SYSCPLD sits on
both sides of the USB-HID bridge).

### i2cdump of bus 12 / addr 0x31 (verified on hardware 2026-04-09)

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00: 02 06 65 10 00 00 00 00 f4 00 00 5a 00 00 00 00
10: e8 01 3f ff 1e 00 00 00 f3 00 00 01 bf df 00 c3
20: 00 00 00 00 00 00 00 00 ef 00 00 00 00 c0 98 f2
30: ff ff 0f 0e ff ff ff ff ff ff 22 0f 02 40 02 00
40: 00 00 00 00 88 8c 88 8c 00 01 00 00 00 00 00 00
```

At first glance registers 0x34-0x37 are all 0xff (matches "32 QSFP resets
all deasserted"), so the plan's hypothesis looks plausible. But further
investigation shows this is coincidence.

### SYSCPLD kernel sysfs attributes (ground truth)

`ls /sys/class/i2c-adapter/i2c-12/12-0031/` (reset-related attrs only):

```
com-e_phy_rst_n
fan_rackmon_rst_n
fp_phy_rst_n
i2c_mux0_rst_n
i2c_mux1_rst_n
i2c_mux2_rst_n
i2c_mux3_rst_n
i2c_mux_psu_rst_n
lpc_rst_n
ob_phy_rst_n
oob_bcm5387_rst_n
reset_reason
th_pcie_rst_n
th_sys_rst_n
tpm_lpc_rst_n
tpm_spi_rst_n
usb2cp2112_rst_n
usb_hub_rst_n
usrv_rst_n
```

**There is no `qsfp_rst_n`, `qsfp_reset`, or `port_N_rst` attribute.** The
SYSCPLD exposes system-level resets (PHY, mux, CPU, TPM, USB hub, front-panel
PHY, OOB switch BCM5387) — but not per-port QSFP reset. Registers 0x34-0x37
are NOT the QSFP reset lines. Their being 0xff is coincidence.

### Our own wedge100s_cpld.c driver sysfs

`platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules/wedge100s_cpld.c`
loads at host-side i2c-1 0x32 and only defines:

- `reset_reason`   (reg 0x0D, 8-bit)
- `reset_source1`  (reg 0x0E)
- `reset_source2`  (reg 0x0F)

…plus board-rev and power-rail attrs added in later commits. No QSFP reset.

### PCA9535 topology (host side via CP2112)

From `architecture.rst` and `wedge100s-i2c-daemon.c` mux tables:

```
CP2112 i2c-1
  └─ PCA9548 0x74
       ├─ ch0 (bus 34) → PCA9535 0x20  LP_MODE ports 0-15  (all 16 pins used)
       ├─ ch1 (bus 35) → PCA9535 0x21  LP_MODE ports 16-31 (all 16 pins used)
       ├─ ch2 (bus 36) → PCA9535 0x22  presence ports 0-15
       ├─ ch3 (bus 37) → PCA9535 0x23  presence ports 16-31
       ├─ ch4 (bus 38) → PCA9535 0x24  RXLOSS ports 0-15
       ├─ ch5 (bus 39) → PCA9535 0x25  RXLOSS ports 16-31
       └─ ch6 (bus 40) → AT24C64 0x50  system EEPROM
```

All 32 LP_MODE pins are consumed by LP_MODE on the 0x20/0x21 PCA9535s.
There is no PCA9535 at 0x26 or 0x27 for QSFP reset. Channel 7 (bus 41) is
unoccupied.

### BMC-side QSFP hardware access

BMC `find / -iname '*qsfp*'` returns only:

```
/usr/local/bin/reset_qsfp_mux.sh
/usr/local/packages/utils/reset_qsfp_mux.sh
```

That script toggles `i2c_mux{0-3}_rst_n` — the mux reset lines, not the
per-port QSFP module resets. There is no per-port QSFP reset path on the
BMC either.

### ONL upstream reference

`/export/sonic/OpenNetworkLinux/packages/platforms/accton/x86-64/wedge100s-32x/`
does NOT implement `onlp_sfpi_reset()`. No reset register references. ONL
upstream leaves reset unimplemented on this platform.

### Existing sfp.py comment

```python
# RESET is not accessible from host CPU on Wedge 100S-32X.
# LP_MODE is managed by wedge100s-i2c-daemon via request/state files.

def reset(self):
    """Reset not supported from host CPU on this platform."""
    return False
```

This is load-bearing — it's based on the same evidence captured here.

## Conclusion

**QSFP_RST_N[1:32] is not wired to any software-accessible register on the
Wedge 100S-32X.** Neither the SYSCPLD (reg 0x30-0x3F), the COM-e PCA9535s,
nor the BMC i2c tree expose a per-port reset path. The Task 3 hypothesis
(`CPLD reg 0x34-0x37` on BMC bus 12) is false: those registers belong to
the SYSCPLD but do not drive QSFP reset lines.

**GAP-026 cannot be closed without one of:**

1. Hardware schematic review to find the actual QSFP_RST_N destination
   (which COM-e GPIO pin, CPLD pin, or FPGA signal). If they are hard-tied
   high on-board (PCB pull-up with no software driver), GAP-026 is
   **unimplementable** and `sfp.py reset()` should be documented as
   permanently unsupported.
2. A replacement soft-reset path via SFF-8636 page 00h byte 93 bit 7
   ("soft reset via I2C"), which writes to the module EEPROM to trigger
   a module-initiated reset. This path is **host-accessible** via the
   existing daemon EEPROM write mechanism (`sfp_N_write_req`) and would
   close GAP-026 without new hardware paths. It is NOT a hard reset but
   is sufficient for recovery from a stuck module.
3. Repurposing `reset_qsfp_mux.sh` to reset all ports on a quadrant
   (ports 0-7, 8-15, etc.) at mux granularity. This is a much coarser
   workaround — it affects all 8 ports on a mux branch and would drop
   traffic on unrelated ports.

## Recommendation

Defer GAP-026 and update `sfp.py reset()` docstring to explain WHY reset is
unsupported (cite this note). If a soft-reset path via SFF-8636 byte 93.7
is acceptable, file a new task to implement it — this does not need any
bmc-daemon changes, only sfp.py + the existing write_req mechanism.

## Probe coordination

All probes ran with:

- Host: `sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon`
- BMC:  `sv stop fscd ipmid`
- All i2cget/i2cdump used `timeout -t N` (busybox syntax) on the BMC
- CPLD scan used the `-f` flag to bypass the kernel driver claim (`UU`)
- Restarted both sides after probe completion

No writes were attempted on any register. Read-only verification.
