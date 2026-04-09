# Wedge 100S-32X Platform Hardware and Architecture Guide

**Single-source-of-truth reference for the Accton Wedge 100S-32X SONiC port.**

| Field | Value |
|---|---|
| Platform | Accton Wedge 100S-32X (Facebook Wedge 100S) |
| OEM | Joytech |
| OCP Spec | OCP Accepted, Wedge 100S v1.3 |
| SONiC Branch | 202511 |
| Kernel | 6.1.0-29-2-amd64 (Debian trixie) |
| Verified on hardware | 2026-03-15 (architecture), 2026-02-25 (CPLD/PSU) |

**Companion documents** (not replaced by this guide):

| Document | Scope |
|---|---|
| [BEWARE_EEPROM.md](BEWARE_EEPROM.md) | EEPROM corruption incidents and probe-write analysis |
| [BEWARE_IRQ.md](BEWARE_IRQ.md) | IRQ 18 overload, BCM IRQ storms, TCP black hole |
| [BEWARE_OPTICS.md](BEWARE_OPTICS.md) | CWDM4 physical blocker, autoneg, FEC, serdes tuning |
| [HARDWARE_I2C.md](HARDWARE_I2C.md) | Detailed I2C bus topology and access patterns |
| SUBSYSTEMS_*.md (8 files) | Per-subsystem deep-dives with Python API details |

---

## Table of Contents

1. [Platform Identity](#1-platform-identity)
2. [System Architecture](#2-system-architecture)
3. [Processor and Memory](#3-processor-and-memory)
4. [Switching ASIC](#4-switching-asic)
5. [I2C Topology](#5-i2c-topology)
6. [System CPLD](#6-system-cpld)
7. [BMC Subsystem](#7-bmc-subsystem)
8. [Thermal Management](#8-thermal-management)
9. [Fan System](#9-fan-system)
10. [Power Supply](#10-power-supply)
11. [QSFP Optics](#11-qsfp-optics)
12. [LED Subsystem](#12-led-subsystem)
13. [OOB Ethernet](#13-oob-ethernet)
14. [Power Distribution](#14-power-distribution)
15. [Security](#15-security)

---

## 1. Platform Identity

### OCP Specification

The Wedge 100S-32X is an OCP-accepted open switch platform designed by Facebook
(now Meta) and manufactured by Accton Technology (OEM: Joytech). The "S"
designation distinguishes this platform from the original Wedge 100 in two
critical ways:

| Attribute | Wedge 100 (non-S) | Wedge 100S |
|---|---|---|
| CPU | Intel Atom C2538, 4-core, 2.4 GHz | Intel Pentium D1508, 2-core/4-thread, 2.2/2.6 GHz |
| CPU architecture | Silvermont (22nm) | Broadwell-DE (14nm) |
| CPU TDP | 15W | 25W |
| Memory | DDR3 | DDR4 ECC |
| COM Express | Type-6 | Type-6 |
| ASIC | BCM56960 (Tomahawk) | BCM56960 (Tomahawk) |
| Port count | 32 x QSFP28 | 32 x QSFP28 |

The ASIC, port layout, BMC, CPLD, and mechanical design are identical between
the two platforms. Only the CPU module differs.

### SONiC Platform Identifiers

| Identifier | Value |
|---|---|
| `platform` | `x86_64-accton_wedge100s_32x-r0` |
| `hwsku` | `Accton-WEDGE100S-32X` |
| ONIE Machine | `accton_wedge100s_32x` |
| Device directory | `device/accton/x86_64-accton_wedge100s_32x-r0/` |
| Platform modules | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/` |

### System EEPROM Identity (verified on hardware 2026-03-14)

| TLV Field | Code | Value |
|---|---|---|
| Product Name | 0x21 | WEDGE100S12V |
| Part Number | 0x22 | 20-001688 |
| Serial Number | 0x23 | AI09019591 |
| Base MAC Address | 0x24 | 00:90:fb:61:da:a1 |
| Vendor Name | 0x2D | Accton |
| Manufacturer | 0x2B | Joytech |

The system EEPROM is a 24C64 (8 KiB) in ONIE TlvInfo format, located behind
PCA9548 mux 0x74, channel 6, at I2C address 0x50.

### Reference Platforms

| Platform | Local Path | Relationship |
|---|---|---|
| ONL Wedge100S | `/export/sonic/OpenNetworkLinux/packages/platforms/accton/x86-64/wedge100s-32x/` | ONL reference implementation |
| Facebook Wedge100 | `device/facebook/x86_64-facebook_wedge100-r0/` | Closest HW sibling (same ASIC/BMC/CPLD) |
| Accton AS7712-32X | `device/accton/x86_64-accton_as7712_32x-r0/` | Same Accton SW stack, same Tomahawk |

---

## 2. System Architecture

### Design Principle: Daemon-Mediated I2C

The Wedge 100S uses a Silicon Labs CP2112 USB-to-HID-to-I2C bridge as the sole
host-side path to the QSFP mux tree, system EEPROM, and CPLD. This bridge is a
single shared resource. The kernel's standard I2C mux subsystem
(`i2c_mux_pca954x`) creates virtual buses and issues mux-select writes that
compete with any userspace I2C access, leading to mux-channel corruption and
EEPROM data loss.

The SONiC port deliberately bypasses the kernel I2C mux stack. A single
compiled C daemon (`wedge100s-i2c-daemon`) owns `/dev/hidraw0` exclusively and
serializes all mux-tree transactions. Python platform API code reads daemon
cache files from `/run/wedge100s/` and never initiates I2C transactions in
steady-state operation.

This architecture mirrors Arista EOS on the same hardware, where a single
privileged process owns the CP2112 and all others read cached state. See
[BEWARE_EEPROM.md](BEWARE_EEPROM.md) for the full incident record that
motivated this design.

### Kernel Modules

**Loaded at platform init** (via `accton_wedge100s_util.py install`):

| Module | Purpose |
|---|---|
| `i2c_dev` | Exposes `/dev/i2c-N` character devices (used by i2c-daemon Phase 1 fallback when hidraw unavailable) |
| `i2c_i801` | Intel PCH SMBus controller, creates `/dev/i2c-0` |
| `hid_cp2112` | CP2112 USB-HID bridge, creates `/dev/i2c-1` and `/dev/hidraw0` |
| `wedge100s_cpld` | Custom CPLD driver, bound to `1-0032` via `new_device` |

**Intentionally NOT loaded:**

| Module | Reason |
|---|---|
| `i2c_mux_pca954x` | Would create buses i2c-2..41 and compete with daemon for mux state |
| `optoe` | No virtual QSFP buses exist; EEPROM served from daemon cache |
| `at24` | System EEPROM served from daemon cache |
| `lm75` | TMP75 sensors are on BMC I2C bus, not host; accessed via TTY |
| `gpio_pca953x` | PCA9535 presence chips owned by daemon via hidraw |
| `i2c_ismt` | Not present on this platform |

### I2C Bus Map (Runtime)

```
/dev/i2c-0   -- Intel i801 SMBus (LPC-attached)
/dev/i2c-1   -- CP2112 USB-HID bridge (CPLD at 1-0032 only)
/dev/hidraw0 -- CP2112 raw HID (daemon owns entire mux tree)
```

Buses `i2c-2` through `i2c-41` do **not** exist. `i2c_mux_pca954x` is not loaded.

### Boot Sequence

```
systemd
  |-- wedge100s-platform-init.service  (Before=pmon.service, oneshot)
  |     accton_wedge100s_util.py install
  |       modprobe i2c_dev
  |       modprobe i2c_i801
  |       modprobe hid_cp2112
  |       modprobe wedge100s_cpld
  |       echo wedge100s_cpld 0x32 > .../i2c-1/new_device
  |       mkdir /run/wedge100s
  |     completes ~3 s after boot
  |
  |-- wedge100s-i2c-poller.timer  (OnBootSec=5s, OnUnitActiveSec=3s)
  |     t=5s: wedge100s-i2c-daemon poll-presence
  |       -> /run/wedge100s/syseeprom       (written once)
  |       -> /run/wedge100s/sfp_N_present   (all 32 ports)
  |       -> /run/wedge100s/sfp_N_eeprom    (inserted ports only)
  |     repeats every 3 s
  |
  |-- wedge100s-bmc-poller.timer  (OnBootSec=15s, OnUnitActiveSec=10s)
  |     t=15s: wedge100s-bmc-daemon
  |       -> /run/wedge100s/thermal_{1..7}
  |       -> /run/wedge100s/fan_present, fan_{1-5}_{front,rear}
  |       -> /run/wedge100s/psu_{1,2}_{vin,iin,iout,pout}
  |     repeats every 10 s
  |
  |-- pmon.service  (starts after platform-init, after multi-user.target)
        loads sonic_platform package
          Chassis.__init__() builds all subsystem objects
        launches pmon daemons (xcvrd, thermalctld, psud, ledd, healthd)
```

There is a brief window (~1-2 s) where pmon is running but the i2c cache has
not yet been written. Python platform API methods return safe defaults during
this window (`False` for presence, `None` for EEPROM reads). There are no
Python-side I2C fallback paths — all hardware access is daemon-mediated.

### systemd Timer Units

| Unit | OnBootSec | OnUnitActiveSec | AccuracySec | What it runs |
|---|---|---|---|---|
| `wedge100s-i2c-poller.timer` | 5 s | 3 s | 1 s | `wedge100s-i2c-daemon poll-presence` |
| `wedge100s-bmc-poller.timer` | 15 s | 10 s | 1 s | `wedge100s-bmc-daemon` |

Both one-shot service units have `LogLevelMax=notice` to suppress high-volume
Start/Finish journal entries (the i2c timer fires ~28,800 times/day; the bmc
timer ~8,640 times/day).

### /run/wedge100s/ File Summary

| File Pattern | Writer | Interval | Consumer |
|---|---|---|---|
| `syseeprom` | i2c-daemon | Once at boot | `eeprom.py` |
| `sfp_N_present` (N=0..31) | i2c-daemon | 3 s | `sfp.py`, `chassis.py` |
| `sfp_N_eeprom` (N=0..31) | i2c-daemon | On insertion | `sfp.py` |
| `fan_present` | bmc-daemon | 10 s | `fan.py` |
| `fan_N_front`, `fan_N_rear` (N=1..5) | bmc-daemon | 10 s | `fan.py` |
| `thermal_1` through `thermal_7` | bmc-daemon | 10 s | `thermal.py` |
| `psu_N_vin`, `psu_N_iin`, `psu_N_iout`, `psu_N_pout` (N=1,2) | bmc-daemon | 10 s | `psu.py` |
| `led_sys1`, `led_sys2` | i2c-daemon | 3 s | informational |
| `qsfp_led_position` | bmc-daemon | Once at boot | LED remap |

### pmon Daemon Interactions

| pmon Daemon | Python API Calls | Data Source |
|---|---|---|
| `xcvrd` | `chassis.get_change_event()`, `sfp.get_presence()`, `sfp.read_eeprom()` | `/run/wedge100s/sfp_N_*` |
| `thermalctld` | `thermal.get_temperature()`, `fan.get_speed()`, `fan.set_speed()` | `/run/wedge100s/thermal_N`, `fan_*`, BMC SSH |
| `psud` | `psu.get_presence()`, `psu.get_voltage()`, `psu.get_power()` | CPLD sysfs, `/run/wedge100s/psu_*` |
| `ledd` / `healthd` | `chassis.set_status_led()` | CPLD sysfs `1-0032/led_sys1` |

### Python Platform API Object Count

| Object Type | Count | Notes |
|---|---|---|
| Thermal | 8 | Index 0 = CPU coretemp, 1-7 = TMP75 |
| FanDrawer | 5 | Each contains 1 Fan (2 rotors) |
| Fan | 10 | 5 front + 5 rear (logical), exposed as 5 trays |
| PSU | 2 | PSU1 and PSU2 |
| SFP | 32 | QSFP28 ports, 0-based internally |
| SysEeprom | 1 | ONIE TlvInfo |
| Component | 2 | CPLD, BIOS |
| Watchdog | 1 | BMC watchdog |

---

## 3. Processor and Memory

### CPU

| Attribute | Value |
|---|---|
| Part | Intel Pentium D1508 |
| Microarchitecture | Broadwell-DE |
| Process | 14nm |
| Cores / Threads | 2 / 4 |
| Base / Turbo clock | 2.2 GHz / 2.6 GHz |
| TDP | 25W |
| Cache | 3 MB L2 (shared) |
| ISA | x86-64, SSE4.2, AES-NI, VT-x, VT-d |
| Intel TXT | Supported |
| Platform | COM Express Type-6 module (Portwell PCOM-B634VG) |

The D1508 is a server-class SoC with integrated PCH. It supports ECC memory,
Intel TXT (Trusted Execution Technology), and VT-d (I/O virtualization).

**Important:** The original Wedge 100 (non-S) uses the Intel Atom C2538, which
is a different microarchitecture (Silvermont vs Broadwell-DE), different core
count (4 vs 2), and does not support ECC memory. Do not confuse the two.

### Memory

| Attribute | Value |
|---|---|
| Type | DDR4 ECC SODIMM |
| Capacity | 8 GB |
| Speed | 2133 MT/s |
| ECC | Supported and enabled |

### Storage

| Attribute | Value |
|---|---|
| Type | M.2 SATA SSD |
| Capacity | 128 GB |
| Interface | SATA III (6 Gbps) |
| Filesystem | SONiC 32 GB root partition |

### BIOS

| Attribute | Value |
|---|---|
| Vendor | AMI (American Megatrends) |
| Type | UEFI with Legacy CSM |
| Flash | Dual SPI flash (primary + backup) |
| Write protection | CPLD register 0x2F controls SPI flash write protect |

### Console

| Attribute | Value |
|---|---|
| Device | `ttyS0` (on-board UART at I/O 0x3f8) |
| Baud rate | 57600 |
| Format | 8N1 |
| GRUB kernel args | `console=ttyS0,57600n8 nopat intel_iommu=off noapic` |

The `noapic` kernel argument is critical on this platform. It matches the ONL
`platform-config.yml` setting and affects IRQ routing. Without it, the BCM ASIC
uses IO-APIC IRQ 16 instead of XT-PIC IRQ 11, changing IRQ affinity behavior.
See [BEWARE_IRQ.md](BEWARE_IRQ.md) for details.

---

## 4. Switching ASIC

### Hardware

| Attribute | Value |
|---|---|
| Part | Broadcom BCM56960 |
| Family | Memory Marvell StrataXGS Tomahawk |
| Switching capacity | 3.2 Tbps |
| SerDes blocks | 32 Falcon cores (128 x 25G SerDes lanes) |
| Host interface | PCIe Gen2 x4 |
| Supported configurations | 32x100G, 64x50G, 128x25G, 32x40G, 128x10G |
| LED microcontroller | 2 LEDUP scan chains (LEDUP0 green, LEDUP1 amber) |
| Memory | On-chip packet buffer, external TCAM not present |

### Port Configuration

All 32 front-panel ports are QSFP28 (100G). Each port uses 4 BCM SerDes lanes.
The default configuration runs all ports at 100G with RS-FEC (CL91).

SONiC interface names use `EthernetN` where N = (panel_port - 1) * 4.

### Port-to-Lane Assignment

| Panel Port | SONiC Interface | BCM Lanes | Alias | BCM Port |
|---|---|---|---|---|
| 1 | Ethernet0 | 117,118,119,120 | Ethernet1/1 | ce29 |
| 2 | Ethernet4 | 113,114,115,116 | Ethernet2/1 | ce28 |
| 3 | Ethernet8 | 125,126,127,128 | Ethernet3/1 | ce31 |
| 4 | Ethernet12 | 121,122,123,124 | Ethernet4/1 | ce30 |
| 5 | Ethernet16 | 5,6,7,8 | Ethernet5/1 | ce1 |
| 6 | Ethernet20 | 1,2,3,4 | Ethernet6/1 | ce0 |
| 7 | Ethernet24 | 13,14,15,16 | Ethernet7/1 | ce3 |
| 8 | Ethernet28 | 9,10,11,12 | Ethernet8/1 | ce2 |
| 9 | Ethernet32 | 21,22,23,24 | Ethernet9/1 | ce5 |
| 10 | Ethernet36 | 17,18,19,20 | Ethernet10/1 | ce4 |
| 11 | Ethernet40 | 29,30,31,32 | Ethernet11/1 | ce7 |
| 12 | Ethernet44 | 25,26,27,28 | Ethernet12/1 | ce6 |
| 13 | Ethernet48 | 37,38,39,40 | Ethernet13/1 | ce9 |
| 14 | Ethernet52 | 33,34,35,36 | Ethernet14/1 | ce8 |
| 15 | Ethernet56 | 45,46,47,48 | Ethernet15/1 | ce11 |
| 16 | Ethernet60 | 41,42,43,44 | Ethernet16/1 | ce10 |
| 17 | Ethernet64 | 53,54,55,56 | Ethernet17/1 | ce13 |
| 18 | Ethernet68 | 49,50,51,52 | Ethernet18/1 | ce12 |
| 19 | Ethernet72 | 61,62,63,64 | Ethernet19/1 | ce15 |
| 20 | Ethernet76 | 57,58,59,60 | Ethernet20/1 | ce14 |
| 21 | Ethernet80 | 69,70,71,72 | Ethernet21/1 | ce17 |
| 22 | Ethernet84 | 65,66,67,68 | Ethernet22/1 | ce16 |
| 23 | Ethernet88 | 77,78,79,80 | Ethernet23/1 | ce19 |
| 24 | Ethernet92 | 73,74,75,76 | Ethernet24/1 | ce18 |
| 25 | Ethernet96 | 85,86,87,88 | Ethernet25/1 | ce21 |
| 26 | Ethernet100 | 81,82,83,84 | Ethernet26/1 | ce20 |
| 27 | Ethernet104 | 93,94,95,96 | Ethernet27/1 | ce23 |
| 28 | Ethernet108 | 89,90,91,92 | Ethernet28/1 | ce22 |
| 29 | Ethernet112 | 101,102,103,104 | Ethernet29/1 | ce25 |
| 30 | Ethernet116 | 97,98,99,100 | Ethernet30/1 | ce24 |
| 31 | Ethernet120 | 109,110,111,112 | Ethernet31/1 | ce27 |
| 32 | Ethernet124 | 105,106,107,108 | Ethernet32/1 | ce26 |

Lane pairs are interleaved within each group of 8 (odd/even pairs swap). This
is the ASIC's internal pipe arrangement, not a wiring anomaly.

### FEC Configuration

| FEC Mode | BCM Name | Status on this platform |
|---|---|---|
| RS-FEC (CL91) | `SAI_PORT_FEC_MODE_RS` | Required for 100GBASE-CR4; works (verified 2026-03-02) |
| FC-FEC (CL74) | `SAI_PORT_FEC_MODE_FC` | Rejected by CLI for 100G ports; not supported on Tomahawk 100G |
| None | `SAI_PORT_FEC_MODE_NONE` | Works; use only for loopback or when peer disables FEC |

RS-FEC must be set explicitly on every 100G port because Clause 73
auto-negotiation is disabled in the BCM config (`phy_an_c73=0x0`). See
[BEWARE_OPTICS.md](BEWARE_OPTICS.md) for details.

### Auto-Negotiation Status

Auto-negotiation is **non-functional at the ASIC level** on this platform
(verified 2026-03-02). The SONiC CLI accepts `config interface autoneg`
commands, and CONFIG_DB/APP_DB propagate the setting, but
`SAI_PORT_ATTR_AUTO_NEG_MODE` remains `false` in ASIC_DB. The BCM config
explicitly disables Clause 73 AN:

```
phy_an_c73=0x0   # Clause 73 (IEEE 802.3ap) -- DISABLED
phy_an_c37=0x3   # Clause 37 (1G Ethernet) -- enabled but irrelevant for QSFP28
```

### BCM Config Files

| File | Purpose |
|---|---|
| `Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm` | DPB-capable flex config (production) |
| `Accton-WEDGE100S-32X/led_proc_init.soc` | LED microcontroller bytecode (Wedge 100S remap) |

### SerDes Channel Swap

Per the OCP spec SerDes mapping table, many ports have "QSFP CHANNELS SWAPPED
WITHIN THE QUAD." This means the physical lanes on the QSFP connector do not
map 1:1 to the Tomahawk SerDes lanes. The BCM config file must include
`phy_lane_swap` entries to compensate.

Ports on connectors 2-7 (approximately QSFP8-31) have channel swaps. The exact
swap pattern varies per connector and must be derived from the OCP spec's SerDes
mapping table (Section 6.2).

The current BCM config (`th-wedge100s-32x-flex.config.bcm`) includes the
correct `phy_xaui_rx_polarity_flip` and `phy_xaui_tx_polarity_flip` settings
for all 32 ports, derived from the OCP spec and verified with live link-up
testing on the Arista EOS peer.

### SerDes Preemphasis

The BCM config sets `serdes_preemphasis` per port. The default tuning is
optimized for copper DAC cables:

```
serdes_preemphasis=0x284800   # post=0x28(40), main=0x48(72), pre=0x00
```

For optical modules (SR4, LR4, CWDM4), the host-side preemphasis should be
reduced since optical modules handle equalization internally. Recommended
optical settings: `pre=0, main=max(60-80), post=0`.

Live tuning (does not survive reboot):
```bash
sudo bcmcmd "phy diag ce26 txeq n1=0 m=80 p1=0"
```

For persistent optical tuning, create a `media_settings.json` in the device
directory. See [BEWARE_OPTICS.md](BEWARE_OPTICS.md) for details.

### Memory and Forwarding

| Attribute | Value |
|---|---|
| Packet buffer | On-chip (no external memory) |
| L2 table entries | 32K (shared) |
| L3 host table entries | 8K IPv4 / 4K IPv6 |
| LPM entries | 16K IPv4 / 8K IPv6 (default MEMORY profile) |
| ACL entries | Varies by profile |
| Forwarding model | Cut-through (default) |

### IRQ Behavior

The BCM ASIC generates significant interrupt load during initialization and
periodic SDK operations:

| State | IRQ Rate | Duration |
|---|---|---|
| Steady-state | ~104-148 /s | Continuous |
| Cold-start (syncd init) | ~2,556 /s | ~136 s |
| xcvrd DOM batch (60 s cycle) | ~4,000-4,400 /s | ~3-5 s |
| BGP ARP storm (if misconfigured) | ~1,878-4,342 /s | Continuous |

These IRQ storms can cause TCP black holes (new SSH connections fail). See
[BEWARE_IRQ.md](BEWARE_IRQ.md) for mitigations including `tcp_syn_retries=2`.

---

## 5. I2C Topology

### Overview

The Wedge 100S has two I2C domains with no electrical connection between them:

1. **Host-side:** Intel I801 SMBus (i2c-0) and CP2112 USB-HID bridge (i2c-1)
2. **BMC-side:** ASPEED AST2400 I2C controllers (BMC_I2C_1 through BMC_I2C_13)

The host cannot directly access BMC I2C devices and vice versa, except through
the shared physical I2C segment between host i2c-1 and BMC i2c-7 (which
carries the risk of bus contention).

### Host I2C: i2c-0 (Intel I801 SMBus)

| Address | Device | Notes |
|---|---|---|
| 0x08 | RTC / Clock | -- |
| 0x44 | Voltage monitor | -- |
| 0x48 | ADS1015 12-bit ADC | 4-channel, 3.3V reference |

### Host I2C: i2c-1 (CP2112 USB-HID Bridge)

CP2112 USB VID:PID `10c4:ea90`. In Phase 2, only the CPLD is registered as a
kernel device on this bus:

| Address | Device | Driver | Kernel-managed |
|---|---|---|---|
| 0x32 | System CPLD (Altera MAX-V 5M2210ZF256) | `wedge100s_cpld` | Yes |
| 0x70 | PCA9548 mux-A | -- | No (daemon-owned) |
| 0x71 | PCA9548 mux-B | -- | No (daemon-owned) |
| 0x72 | PCA9548 mux-C | -- | No (daemon-owned) |
| 0x73 | PCA9548 mux-D | -- | No (daemon-owned) |
| 0x74 | PCA9548 mux-E | -- | No (daemon-owned) |
| 0x50 | COM-e EC chip | -- | No (do not use -- see BEWARE_EEPROM.md) |
| 0x51 | COM-e internal EEPROM (AT24C02) | -- | No (do not write -- see BEWARE_EEPROM.md) |

### CP2112 Mux Tree (Daemon-Managed)

The daemon navigates this tree via raw HID reports (AN495 protocol). Bus
numbers shown are the logical numbers that would be assigned if
`i2c_mux_pca954x` were loaded.

```
i2c-1 (CP2112)
|
+-- PCA9548 @ 0x70 (mux-A) --> logical buses 2-9
|     ch0 -> bus  2  (QSFP port  1 EEPROM @ 0x50)
|     ch1 -> bus  3  (QSFP port  0 EEPROM @ 0x50)
|     ch2 -> bus  4  (QSFP port  3 EEPROM @ 0x50)
|     ch3 -> bus  5  (QSFP port  2 EEPROM @ 0x50)
|     ch4 -> bus  6  (QSFP port  5 EEPROM @ 0x50)
|     ch5 -> bus  7  (QSFP port  4 EEPROM @ 0x50)
|     ch6 -> bus  8  (QSFP port  7 EEPROM @ 0x50)
|     ch7 -> bus  9  (QSFP port  6 EEPROM @ 0x50)
|
+-- PCA9548 @ 0x71 (mux-B) --> logical buses 10-17
|     ch0 -> bus 10  (QSFP port  9 EEPROM @ 0x50)
|     ch1 -> bus 11  (QSFP port  8 EEPROM @ 0x50)
|     ch2 -> bus 12  (QSFP port 11 EEPROM @ 0x50)
|     ch3 -> bus 13  (QSFP port 10 EEPROM @ 0x50)
|     ch4 -> bus 14  (QSFP port 13 EEPROM @ 0x50)
|     ch5 -> bus 15  (QSFP port 12 EEPROM @ 0x50)
|     ch6 -> bus 16  (QSFP port 15 EEPROM @ 0x50)
|     ch7 -> bus 17  (QSFP port 14 EEPROM @ 0x50)
|
+-- PCA9548 @ 0x72 (mux-C) --> logical buses 18-25
|     ch0 -> bus 18  (QSFP port 17 EEPROM @ 0x50)
|     ch1 -> bus 19  (QSFP port 16 EEPROM @ 0x50)
|     ch2 -> bus 20  (QSFP port 19 EEPROM @ 0x50)
|     ch3 -> bus 21  (QSFP port 18 EEPROM @ 0x50)
|     ch4 -> bus 22  (QSFP port 21 EEPROM @ 0x50)
|     ch5 -> bus 23  (QSFP port 20 EEPROM @ 0x50)
|     ch6 -> bus 24  (QSFP port 23 EEPROM @ 0x50)
|     ch7 -> bus 25  (QSFP port 22 EEPROM @ 0x50)
|
+-- PCA9548 @ 0x73 (mux-D) --> logical buses 26-33
|     ch0 -> bus 26  (QSFP port 25 EEPROM @ 0x50)
|     ch1 -> bus 27  (QSFP port 24 EEPROM @ 0x50)
|     ch2 -> bus 28  (QSFP port 27 EEPROM @ 0x50)
|     ch3 -> bus 29  (QSFP port 26 EEPROM @ 0x50)
|     ch4 -> bus 30  (QSFP port 29 EEPROM @ 0x50)
|     ch5 -> bus 31  (QSFP port 28 EEPROM @ 0x50)
|     ch6 -> bus 32  (QSFP port 31 EEPROM @ 0x50)
|     ch7 -> bus 33  (QSFP port 30 EEPROM @ 0x50)
|
+-- PCA9548 @ 0x74 (mux-E) --> logical buses 34-41
      ch0 -> bus 34  (PCA9535 #1 @ 0x20, LPMODE ports 0-15)
      ch1 -> bus 35  (PCA9535 #2 @ 0x21, LPMODE ports 16-31)
      ch2 -> bus 36  (PCA9535 #3 @ 0x22, PRESENCE ports 0-15)
      ch3 -> bus 37  (PCA9535 #4 @ 0x23, PRESENCE ports 16-31)
      ch4 -> bus 38  (PCA9535 #5 @ 0x24, RXLOSS/INT ports 0-15)
      ch5 -> bus 39  (PCA9535 #6 @ 0x25, RXLOSS/INT ports 16-31)
      ch6 -> bus 40  (24C64 system EEPROM @ 0x50, 8 KiB)
      ch7 -> bus 41  (unused)
```

**Note on PCA9535 #5/#6 (0x24/0x25):** Per the OCP spec low-speed signal tables
(Table 13), these carry RXLOSS signals, not just generic interrupt. The current
SONiC implementation does not read these devices.

### Port-to-Bus Map

The daemon uses this mapping to select the correct PCA9548 mux and channel for
each QSFP port's EEPROM:

| Port | Bus | Port | Bus | Port | Bus | Port | Bus |
|---|---|---|---|---|---|---|---|
| 0 | 3 | 8 | 11 | 16 | 19 | 24 | 27 |
| 1 | 2 | 9 | 10 | 17 | 18 | 25 | 26 |
| 2 | 5 | 10 | 13 | 18 | 21 | 26 | 29 |
| 3 | 4 | 11 | 12 | 19 | 20 | 27 | 28 |
| 4 | 7 | 12 | 15 | 20 | 23 | 28 | 31 |
| 5 | 6 | 13 | 14 | 21 | 22 | 29 | 30 |
| 6 | 9 | 14 | 17 | 22 | 25 | 30 | 33 |
| 7 | 8 | 15 | 16 | 23 | 24 | 31 | 32 |

Pattern: pairs of front-panel ports are interleaved (XOR-1 pattern within each
group of 8). This matches the PCA9548 channel wiring on the mux board and is
verified on hardware (2026-03-11).

### Address 0x50 Disambiguation

Three distinct devices respond to address 0x50 depending on which I2C segment
is selected:

| Path | Address | Device | Danger |
|---|---|---|---|
| i2c-1 direct | 0x50 | COM-e EC chip | ACKs writes but silently discards them |
| i2c-1 direct | 0x51 | COM-e internal EEPROM (AT24C02) | Writing TlvInfo here was a bug in early development |
| Via mux 0x74 ch6 (bus 40) | 0x50 | True system EEPROM (24C64, 8 KiB) | Authoritative platform EEPROM |

See [BEWARE_EEPROM.md](BEWARE_EEPROM.md) for the full incident record.

### I2C Bus Safety

**NEVER touch the I2C bus while `wedge100s-i2c-daemon` or `pmon` are running.**
The CP2112 bridge is a single shared resource. Concurrent access corrupts mux
state.

```bash
# Before any manual I2C access:
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

# After:
sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

---

## 6. System CPLD

### Hardware

| Attribute | Value |
|---|---|
| Part | Altera MAX-V 5M2210ZF256 |
| Type | Non-volatile CPLD, instant-on |
| Power domain | Standby (always powered when PSU present) |
| Host I2C address | 0x32 (via CP2112, i2c-1) |
| BMC I2C address | 0x31 (via BMC_I2C_13) |
| Kernel driver | `wedge100s_cpld` |
| sysfs root | `/sys/bus/i2c/devices/1-0032/` |
| CPLD version observed | Major 0x02, Minor 0x06 (verified 2026-02-25) |
| Board ID | 0x65 |

### Full Register Map (0x00 - 0x3F)

| Reg | Name | Access | Description | Implemented in SONiC |
|---|---|---|---|---|
| 0x00 | VERSION_MAJOR | RO | CPLD major version | Yes (`cpld_version`) |
| 0x01 | VERSION_MINOR | RO | CPLD minor version | Yes (`cpld_version`) |
| 0x02 | BOARD_ID | RO | Board identification (0x65) | No |
| 0x03 | BOARD_REV | RO | Board revision | No |
| 0x04 | MODULE_PRESENCE_0 | RO | QSFP module presence bits [7:0] | No (daemon uses PCA9535) |
| 0x05 | MODULE_PRESENCE_1 | RO | QSFP module presence bits [15:8] | No |
| 0x06 | MODULE_PRESENCE_2 | RO | QSFP module presence bits [23:16] | No |
| 0x07 | MODULE_PRESENCE_3 | RO | QSFP module presence bits [31:24] | No |
| 0x08 | ROV_STATUS | RO | Regulator output voltage status | No |
| 0x09 | RESET_REASON | RO | Last reset cause (power-on, watchdog, etc.) | No |
| 0x0A | RESERVED_0A | -- | Reserved | -- |
| 0x0B | RESERVED_0B | -- | Reserved | -- |
| 0x0C | RESERVED_0C | -- | Reserved | -- |
| 0x0D | RESERVED_0D | -- | Reserved | -- |
| 0x0E | RESERVED_0E | -- | Reserved | -- |
| 0x0F | RESERVED_0F | -- | Reserved | -- |
| 0x10 | PSU_STATUS | RO | PSU presence and power-good | Yes (`psu{1,2}_{present,pgood}`) |
| 0x11 | POWER_STATUS | RO | Main power rail status | No |
| 0x12 | PCA9535_INT_0 | RO | PCA9535 interrupt status [7:0] | No |
| 0x13 | PCA9535_INT_1 | RO | PCA9535 interrupt status [15:8] | No |
| 0x14 | COME_STATUS_0 | RO | COM-e status register 0 | No |
| 0x15 | COME_STATUS_1 | RO | COM-e status register 1 | No |
| 0x16 | LED_BUTTON | RO | Front-panel LED button state | No |
| 0x17 | CP2112_GPIO | RO | CP2112 GPIO pin state | No |
| 0x18 | PSU_INT_MASK | RW | PSU interrupt mask | No |
| 0x19 | POWER_INT_MASK | RW | Power interrupt mask | No |
| 0x1A | PCA9535_INT_MASK_0 | RW | PCA9535 interrupt mask [7:0] | No |
| 0x1B | PCA9535_INT_MASK_1 | RW | PCA9535 interrupt mask [15:8] | No |
| 0x1C | RESERVED_1C | -- | Reserved | -- |
| 0x1D | RESERVED_1D | -- | Reserved | -- |
| 0x1E | RESERVED_1E | -- | Reserved | -- |
| 0x1F | RESERVED_1F | -- | Reserved | -- |
| 0x20 | UART_MUX | RW | UART multiplexer control | No |
| 0x21 | COME_CONTROL_0 | RW | COM-e control register 0 | No |
| 0x22 | COME_CONTROL_1 | RW | COM-e control register 1 | No |
| 0x23 | CP2112_GPIO_OE | RW | CP2112 GPIO output enable | No |
| 0x24 | CP2112_GPIO_OUT | RW | CP2112 GPIO output value | No |
| 0x25 | RESERVED_25 | -- | Reserved | -- |
| 0x26 | RESERVED_26 | -- | Reserved | -- |
| 0x27 | RESERVED_27 | -- | Reserved | -- |
| 0x28 | RESERVED_28 | -- | Reserved | -- |
| 0x29 | RESERVED_29 | -- | Reserved | -- |
| 0x2A | RESERVED_2A | -- | Reserved | -- |
| 0x2B | RESERVED_2B | -- | Reserved | -- |
| 0x2C | RESERVED_2C | -- | Reserved | -- |
| 0x2D | RESERVED_2D | -- | Reserved | -- |
| 0x2E | DEBUG_CONTROL | RW | Debug control; bit 7 = HEART_ATTACK_EN | No |
| 0x2F | DUAL_BOOT_CTRL | RW | DUAL_BOOT_EN, EN_2ND_Flash_WP, Force_2nd_WR | No |
| 0x30 | RESERVED_30 | -- | Reserved | -- |
| 0x31 | RESERVED_31 | -- | Reserved | -- |
| 0x32 | RESERVED_32 | -- | Reserved | -- |
| 0x33 | RESERVED_33 | -- | Reserved | -- |
| 0x34 | RESERVED_34 | -- | Reserved | -- |
| 0x35 | RESERVED_35 | -- | Reserved | -- |
| 0x36 | RESERVED_36 | -- | Reserved | -- |
| 0x37 | RESERVED_37 | -- | Reserved | -- |
| 0x38 | RESERVED_38 | -- | Reserved | -- |
| 0x39 | RESERVED_39 | -- | Reserved | -- |
| 0x3A | RESERVED_3A | -- | Reserved | -- |
| 0x3B | RESERVED_3B | -- | Reserved | -- |
| 0x3C | TH_LED_CONTROL | RW | Tomahawk LED control (th_led_en, test modes) | No (BMC-side only, via 0x31) |
| 0x3D | RESERVED_3D | -- | Reserved | -- |
| 0x3E | LED_SYS1 | RW | SYS1 LED control | Yes (`led_sys1`) |
| 0x3F | LED_SYS2 | RW | SYS2 LED control | Yes (`led_sys2`) |

### PSU Status Register (0x10) Bit Map

Active-low polarity: `0` = present/good, `1` = absent/failed.

| Bit | Signal | Sysfs Attribute | Polarity |
|---|---|---|---|
| 0 | PSU1_PRESENT | `psu1_present` | Active-low (driver inverts: 1 = present) |
| 1 | PSU1_PGOOD | `psu1_pgood` | Active-high (1 = good) |
| 2-3 | Reserved | -- | -- |
| 4 | PSU2_PRESENT | `psu2_present` | Active-low (driver inverts: 1 = present) |
| 5 | PSU2_PGOOD | `psu2_pgood` | Active-high (1 = good) |
| 6-7 | Reserved | -- | Read as 1 (observed 0xe0 with both PSUs) |

Live observed value: `0xe0` (bits 7:6 set, all PSU status bits clear when both
PSUs present and powered). (verified 2026-02-25)

### LED Encoding (Registers 0x3E, 0x3F)

| Value | Color | Blink Variant |
|---|---|---|
| 0x00 | Off | 0x08 = off (blink) |
| 0x01 | Red | 0x09 = red blinking |
| 0x02 | Green | 0x0A = green blinking |
| 0x04 | Blue | 0x0C = blue blinking |

The `+0x08` modifier enables blinking for any base color. The hardware has no
amber LED; `chassis.py` maps `'amber'` to `0x01` (red).

### CPLD sysfs Interface

Path: `/sys/bus/i2c/devices/1-0032/`

| Attribute | Access | Format | Register |
|---|---|---|---|
| `cpld_version` | RO | `"major.minor\n"` (e.g., `"2.6\n"`) | 0x00, 0x01 |
| `psu1_present` | RO | `"0\n"` or `"1\n"` | 0x10 bit 0 (inverted) |
| `psu1_pgood` | RO | `"0\n"` or `"1\n"` | 0x10 bit 1 |
| `psu2_present` | RO | `"0\n"` or `"1\n"` | 0x10 bit 4 (inverted) |
| `psu2_pgood` | RO | `"0\n"` or `"1\n"` | 0x10 bit 5 |
| `led_sys1` | RW | `"0x02\n"` on read; decimal or hex on write | 0x3E |
| `led_sys2` | RW | Same encoding | 0x3F |

The driver uses `i2c_smbus_read_byte_data` / `i2c_smbus_write_byte_data` with
up to 10 retries at 60 ms intervals. All register accesses are serialized under
a per-device `struct mutex update_lock`.

### Debug Control Register (0x2E)

| Bit | Name | Function |
|---|---|---|
| 0 | DEBUG_0 | Reserved debug control |
| 1 | DEBUG_1 | Reserved debug control |
| 2 | DEBUG_2 | Reserved debug control |
| 3 | DEBUG_3 | Reserved debug control |
| 4 | DEBUG_4 | Reserved debug control |
| 5 | DEBUG_5 | Reserved debug control |
| 6 | DEBUG_6 | Reserved debug control |
| 7 | HEART_ATTACK_EN | Fan heartbeat failure triggers power shutdown |

### HEART_ATTACK_EN (Register 0x2E, Bit 7)

The CPLD includes a fan heartbeat watchdog. If all 5 fan trays report failure
(heartbeat signal lost), and `HEART_ATTACK_EN` (register 0x2E bit 7) is set,
the CPLD triggers a main power shutdown to protect the ASIC from thermal
damage. This is a hardware-level safety mechanism independent of software.

### Tomahawk LED Control Register (0x3C)

This register is accessible from the BMC side (CPLD address 0x31 on
BMC_I2C_13). It controls the port LED scan chain:

| Bit | Name | Function | Default |
|---|---|---|---|
| 0 | LED_MODE_0 | LED mode select bit 0 | 0 |
| 1 | TH_LED_EN | Enable Tomahawk LEDUP output to front panel | 0 (gated) |
| 2 | LED_MODE_2 | LED mode select bit 2 | 0 |
| 3 | WALK_TEST_EN | Enable walking LED test pattern | 0 |
| 4 | Reserved | -- | 0 |
| 5 | Reserved | -- | 1 |
| 6 | LED_TEST_BLINK_EN | Enable LED blink test mode | 1 |
| 7 | LED_TEST_MODE_EN | Enable global LED test mode | 1 |

Factory default: `0xE0` (test modes active, LEDUP gated). After platform-init:
`clear_led_diag.sh` sets to `0x02` (th_led_en=1, all test modes off).
(verified 2026-03-26)

### Dual BIOS Control (Register 0x2F)

| Bit | Name | Function |
|---|---|---|
| 0 | DUAL_BOOT_EN | Enable dual-BIOS boot support |
| 1 | EN_2ND_Flash_WP | Write-protect secondary BIOS SPI flash |
| 2 | Force_2nd_WR | Force write to secondary flash |

**Not implemented in SONiC.** These registers are available for firmware
update tooling but are not currently exposed via sysfs or any platform API.

---

## 7. BMC Subsystem

### Hardware

| Attribute | Value |
|---|---|
| Part | ASPEED AST2400 (some units AST1250/AST2520 per OCP spec) |
| Architecture | ARM926EJ-S |
| Firmware | Facebook OpenBMC |
| Host connectivity | USB-CDC-ECM (fe80::ff:fe00:1%usb0), USB-CDC-ACM (/dev/ttyACM0 @ 57600) |
| Network | 192.168.88.13 (management), fe80::ff:fe00:1%usb0 (link-local) |
| Login | root / 0penBmc |

### Host-BMC Communication Channels

| Channel | Path | Used By | Notes |
|---|---|---|---|
| USB-CDC-ACM | `/dev/ttyACM0` @ 57600 8N1 | `wedge100s-bmc-daemon` | Primary data channel |
| USB-CDC-ECM | `fe80::ff:fe00:1%usb0` | SSH (fallback) | For interactive debug |
| Ethernet | `192.168.88.13` | SSH | Via management network |
| Serial | `/dev/ttyACM0` or JTAG | Console | Emergency access |

The `wedge100s-bmc-daemon` opens `/dev/ttyACM0` and keeps the session open for
all commands in one invocation, avoiding the ~65 s per-cycle overhead of
re-opening and re-logging in per command. Prompt pattern: `:~# ` (matches any
OpenBMC root shell hostname).

### BMC Reachability After Reboot

After BMC reboot, `authorized_keys` is cleared. If ping works but SSH fails:

```bash
sshpass -p '0penBmc' ssh-copy-id -o StrictHostKeyChecking=no root@192.168.88.13
```

### BMC I2C Bus Map

| BMC Bus | Devices | Notes |
|---|---|---|
| BMC_I2C_1 | COM-e SMBus | Shared physical segment with host i2c-1 |
| BMC_I2C_2 | IR3581 @ 0x10, IR3584 @ 0x12, IR3584 @ 0x14 | DC-DC converters (Tomahawk power) |
| BMC_I2C_3 | PWR1014A @ 0x3A | Power sequencer (Lattice) |
| BMC_I2C_4 | TMP75 #1-5 @ 0x48-0x4C | Mainboard thermal sensors |
| BMC_I2C_5 | COM-e EC I2C, PCA9534 @ 0x20 | IO expander |
| BMC_I2C_6 | USB hub SMBus @ 0x2C | -- |
| BMC_I2C_7 | PCF8574 @ 0x3F, 24C64 EEPROM @ 0x50 | BMC-side EEPROM |
| BMC_I2C_8 | PCA9548 @ 0x70 (see below) | PSU mux |
| BMC_I2C_9 | Fan CPLD @ 0x33, TMP75 #6 @ 0x48, TMP75 #7 @ 0x49 | Fan board |
| BMC_I2C_10 | SLB9645 TPM | Infineon Trusted Platform Module |
| BMC_I2C_13 | SYSCPLD @ 0x31 | Same physical CPLD as host 0x32 |

### BMC_I2C_8 PCA9548 Mux Channels

| Channel | Device(s) | Notes |
|---|---|---|
| CH0 | PSU2 MCU @ 0x5A, PSU2 EEPROM @ 0x52 | Mux select value 0x01 |
| CH1 | PSU1 MCU @ 0x59, PSU1 EEPROM @ 0x51 | Mux select value 0x02 |
| CH2 | BMC PHY EEPROM @ 0x50 | BCM54616S |
| CH3 | Front-panel PHY EEPROM @ 0x50 | BCM54616S |
| CH4-7 | Unused | -- |

### BMC Daemon Commands

The `wedge100s-bmc-daemon` issues these commands to the BMC per invocation
(every 10 s):

| Category | BMC Command | Output File |
|---|---|---|
| Thermal | `cat /sys/bus/i2c/devices/3-0048/hwmon/*/temp1_input` | `thermal_1` |
| Thermal | `cat /sys/bus/i2c/devices/3-0049/hwmon/*/temp1_input` | `thermal_2` |
| Thermal | `cat /sys/bus/i2c/devices/3-004a/hwmon/*/temp1_input` | `thermal_3` |
| Thermal | `cat /sys/bus/i2c/devices/3-004b/hwmon/*/temp1_input` | `thermal_4` |
| Thermal | `cat /sys/bus/i2c/devices/3-004c/hwmon/*/temp1_input` | `thermal_5` |
| Thermal | `cat /sys/bus/i2c/devices/8-0048/hwmon/*/temp1_input` | `thermal_6` |
| Thermal | `cat /sys/bus/i2c/devices/8-0049/hwmon/*/temp1_input` | `thermal_7` |
| Fan | `cat .../8-0033/fantray_present` | `fan_present` |
| Fan | `cat .../8-0033/fan{1,3,5,7,9}_input` | `fan_{1-5}_front` |
| Fan | `cat .../8-0033/fan{2,4,6,8,10}_input` | `fan_{1-5}_rear` |
| PSU | `i2cset -f -y 7 0x70 0x02` (select PSU1) | -- |
| PSU | `i2cget -f -y 7 0x59 0x88 w` (READ_VIN) | `psu_1_vin` |
| PSU | `i2cget -f -y 7 0x59 0x89 w` (READ_IIN) | `psu_1_iin` |
| PSU | `i2cget -f -y 7 0x59 0x8c w` (READ_IOUT) | `psu_1_iout` |
| PSU | `i2cget -f -y 7 0x59 0x96 w` (READ_POUT) | `psu_1_pout` |
| PSU | `i2cset -f -y 7 0x70 0x01` (select PSU2) | -- |
| PSU | `i2cget -f -y 7 0x5a 0x88 w` (etc.) | `psu_2_{vin,iin,iout,pout}` |

All thermal values are millidegrees C. PSU PMBus values are raw LINEAR11 16-bit
words; Python decodes them to SI units.

### IPMI and REST API

**IPMI is completely absent** on this platform. `modprobe ipmi_si` returns
`No such device`; the BMC does not listen on UDP 623. This is a Facebook-OpenBMC
build that predates IPMI support.

The **Facebook REST API** (port 8080 over IPv6 link-local on `usb0`) works but
adds 1.0-1.4 s latency per call. Fan speed writes are not available via REST
(`writable = false` in `/etc/rest.cfg`). The TTY-based daemon remains the
correct approach.

---

## 8. Thermal Management

### Sensor Inventory

8 thermal sensors total. Index 0 is host-side; indices 1-7 are BMC-side.

| Index | Name | Device | Location | Bus/Addr | Threshold (High) | Threshold (Critical) |
|---|---|---|---|---|---|---|
| 0 | CPU Core | Intel coretemp | Host CPU (D1508) | Host sysfs | 95.0 C | 102.0 C |
| 1 | TMP75-1 | TI TMP75 | Mainboard | BMC i2c-3 / 0x48 | 70.0 C | 80.0 C |
| 2 | TMP75-2 | TI TMP75 | Mainboard | BMC i2c-3 / 0x49 | 70.0 C | 80.0 C |
| 3 | TMP75-3 | TI TMP75 | Mainboard | BMC i2c-3 / 0x4A | 70.0 C | 80.0 C |
| 4 | TMP75-4 | TI TMP75 | Mainboard | BMC i2c-3 / 0x4B | 70.0 C | 80.0 C |
| 5 | TMP75-5 | TI TMP75 | Mainboard | BMC i2c-3 / 0x4C | 70.0 C | 80.0 C |
| 6 | TMP75-6 | TI TMP75 | Fan board | BMC i2c-8 / 0x48 | 70.0 C | 80.0 C |
| 7 | TMP75-7 | TI TMP75 | Fan board | BMC i2c-8 / 0x49 | 70.0 C | 80.0 C |

All 7 TMP75 sensors are wired to the BMC I2C bus, not the host. No host kernel
`lm75` driver is loaded for these.

Verified live readings (hardware, 2026-02-25): TMP75-1: 23.75 C, TMP75-2:
22.9 C, TMP75-3: 23.1 C, TMP75-4: 33.3 C, TMP75-5: 21.1 C, TMP75-6:
20.6 C, TMP75-7: 23.0 C.

### Host-Side Thermal Reading (Index 0)

The CPU core temperature is read directly by Python via the host `coretemp`
kernel module:

```
/sys/devices/platform/coretemp.0/hwmon/hwmon*/temp*_input
```

Values are in millidegrees C. The `max()` across all matched files is returned
(mirrors ONL `onlp_file_read_int_max()`). The hwmon index is not stable across
reboots; the code uses a glob.

### BMC-Side Thermal Reading (Indices 1-7)

The `wedge100s-bmc-daemon` polls all 7 TMP75 sensors via `/dev/ttyACM0` and
writes millidegrees C as plain decimal integers to:

```
/run/wedge100s/thermal_1 through /run/wedge100s/thermal_7
```

### Python API

Class `Thermal` in `sonic_platform/thermal.py`, inherits `ThermalBase`.
0-based index 0-7, instantiated by `Chassis.__init__()`.

| Method | Source |
|---|---|
| `get_temperature()` | Host coretemp (index 0) or `/run/wedge100s/thermal_N` (indices 1-7) |
| `get_high_threshold()` | 95.0 C (CPU) or 70.0 C (TMP75), from `_SENSORS` table |
| `get_high_critical_threshold()` | 102.0 C (CPU) or 80.0 C (TMP75) |
| `get_presence()` | Always `True` (board-mounted) |
| `get_status()` | `True` if temperature reading succeeds |

### Thermal Sensor Physical Placement

The OCP spec and board schematics place the TMP75 sensors at specific
measurement points. The exact placement mapping requires correlation with the
hardware schematic, but the general arrangement is:

| Index | Estimated Location | Typical Reading | Notes |
|---|---|---|---|
| 1 (0x48 bus 3) | Near Tomahawk ASIC (inlet side) | 23-35 C | Highest mainboard reading |
| 2 (0x49 bus 3) | Mainboard center | 22-30 C | -- |
| 3 (0x4A bus 3) | Mainboard rear | 22-30 C | -- |
| 4 (0x4B bus 3) | Near power regulators | 30-40 C | Often warmest TMP75 |
| 5 (0x4C bus 3) | Near COM-e module | 20-28 C | -- |
| 6 (0x48 bus 8) | Fan board inlet | 20-25 C | Ambient intake temperature |
| 7 (0x49 bus 8) | Fan board exhaust side | 22-28 C | -- |

These placements are estimated from observed thermal gradients. Verified
readings listed are from a lab environment at ~22 C ambient (2026-02-25).

### Thermal Shutdown Mechanism

The Wedge 100S has a hardware-level thermal protection mechanism independent
of software:

1. **Fan heartbeat failure:** If all 5 fan trays stop sending heartbeat signals
   to the SYSCPLD, and `HEART_ATTACK_EN` (CPLD 0x2E bit 7) is set, the CPLD
   cuts main power to protect the ASIC.

2. **Tomahawk internal thermal shutdown:** The BCM56960 has an internal thermal
   sensor that triggers ASIC shutdown if the junction temperature exceeds its
   rated maximum (~110 C). This is independent of the TMP75 board sensors.

3. **CPU thermal throttling:** The D1508 supports PROCHOT# thermal throttling.
   The CPU reduces clock speed before reaching T-junction maximum (105 C).

### Known Limitations

- Thresholds are compile-time constants; lost on pmon restart.
- No low-temperature thresholds defined.
- TMP75 sensor names do not indicate physical board location; correlate against
  ONL `thermali.c` or hardware schematic for exact placement.
- Min/max recorded values are in-process state only; no STATE_DB persistence.
- No Tomahawk die temperature sensor accessible from SONiC (would require
  BCM SDK call via syncd).

---

## 9. Fan System

### Hardware

| Attribute | Value |
|---|---|
| Fan trays | 5 |
| Rotors per tray | 2 (counter-rotating: front + rear) |
| Fan model | Delta GFB0412EHS-DA06 |
| Voltage | 12 VDC |
| Current (max) | 1.40A / 1.68A |
| Front RPM (max) | 16,000 +/- 10% |
| Rear RPM (max) | 15,400 +/- 10% |
| Noise | 64.5 dB-A |
| Airflow | Front-to-back (intake at front, exhaust at rear), fixed |
| Controller | Fan CPLD at 0x33 on BMC_I2C_9 |
| BMC sysfs | `/sys/bus/i2c/devices/8-0033/` |

### Fan Board sysfs (BMC Filesystem)

| sysfs File | Description | Example |
|---|---|---|
| `fan1_input` | Front rotor RPM, tray 1 | ~7500 |
| `fan2_input` | Rear rotor RPM, tray 1 | ~4950 |
| `fan3_input` | Front rotor RPM, tray 2 | -- |
| `fan4_input` | Rear rotor RPM, tray 2 | -- |
| ... | ... | ... |
| `fan9_input` | Front rotor RPM, tray 5 | -- |
| `fan10_input` | Rear rotor RPM, tray 5 | -- |
| `fantray_present` | Presence bitmask (bit N set = tray N+1 absent) | 0x00 = all present |

Fan number formula: tray N -> front = `fan(2N-1)_input`, rear = `fan(2N)_input`.

### Speed Control

```bash
set_fan_speed.sh <percent>   # Global, applies to all trays equally
```

No per-tray speed control is available. The command is sent to the BMC via
`/dev/ttyACM0`.

### Heartbeat Watchdog

The fan CPLD sends a heartbeat signal to the SYSCPLD. If all 5 fan trays fail
(heartbeat lost), and `HEART_ATTACK_EN` (CPLD register 0x2E bit 7) is set, the
SYSCPLD triggers main power shutdown to protect the ASIC.

### Daemon Cache

`wedge100s-bmc-daemon` writes to `/run/wedge100s/`:

| File | Content |
|---|---|
| `fan_present` | Decimal integer bitmask (bit N set = tray N+1 absent; 0x00 = all present) |
| `fan_N_front` (N=1-5) | Front rotor RPM |
| `fan_N_rear` (N=1-5) | Rear rotor RPM |

### Python API

Class `Fan` in `sonic_platform/fan.py` (1-based index 1-5). Class `FanDrawer`
contains one `Fan` each. Both instantiated by `Chassis.__init__()`.

| Method | Returns |
|---|---|
| `get_presence()` | `bool` from `/run/wedge100s/fan_present` bitmask (cached 2 s) |
| `get_speed_rpm()` | `min(front_rpm, rear_rpm)` per ONL `fani.c` policy |
| `get_speed()` | Percentage (0-100) derived from RPM / 15,400 |
| `set_speed(pct)` | Sends `set_fan_speed.sh <pct>` to BMC; all trays simultaneously |
| `get_direction()` | `FAN_DIRECTION_INTAKE` (hardcoded, front-to-back) |
| `get_speed_tolerance()` | 20% (hardcoded) |

### Fan Speed vs Temperature Policy

The SONiC `thermalctld` daemon implements a thermal control algorithm that reads
all 8 thermal sensors and adjusts fan speed accordingly. The algorithm uses the
following thresholds:

| Temperature Range | Fan Speed | Action |
|---|---|---|
| All sensors < 60 C | thermalctld algorithm | Normal proportional control |
| Any TMP75 >= 70 C | 100% | High threshold exceeded |
| Any TMP75 >= 80 C | 100% + alarm | Critical threshold exceeded |
| CPU Core >= 95 C | 100% + alarm | CPU high threshold |
| CPU Core >= 102 C | 100% + shutdown warning | CPU critical |

Fan speed changes are sent to the BMC via `set_fan_speed.sh <pct>`. The BMC's
internal `fand` process also has its own thermal control algorithm that may
conflict with SONiC's `thermalctld`. The interaction between these two control
loops is a known source of fan speed oscillation.

### Fan Tray Numbering

| Tray | Front sysfs | Rear sysfs | Typical Front RPM | Typical Rear RPM |
|---|---|---|---|---|
| 1 | fan1_input | fan2_input | ~7500 | ~4950 |
| 2 | fan3_input | fan4_input | ~7500 | ~4950 |
| 3 | fan5_input | fan6_input | ~7500 | ~4950 |
| 4 | fan7_input | fan8_input | ~7500 | ~4950 |
| 5 | fan9_input | fan10_input | ~7500 | ~4950 |

Typical values at default BMC fan speed (~50% duty cycle). Front rotors
consistently run faster than rear rotors due to airflow path differences.

### Known Limitations

- Fan tray LEDs are not individually addressable from the host.
- `get_model()` and `get_serial()` return `'N/A'`.
- Speed control applies to all 5 trays simultaneously.
- `get_target_speed()` raises `NotImplementedError` before first `set_speed()`.
- BMC `fand` and SONiC `thermalctld` may both attempt to control fan speed
  simultaneously, causing oscillation.
- No per-tray speed feedback; `get_speed()` returns the same target for all.

---

## 10. Power Supply

### Hardware

| Attribute | Value |
|---|---|
| Slots | 2 (PSU-1 and PSU-2) |
| Models | Bel Power Solutions SPDFCBK-14G (AC), -15G (DC 40-72V), -16G (DC 40-72V 400W) |
| AC input | 120/240V |
| DC output (main) | 12V, 62A max |
| DC output (standby) | 3.3V, 3A |
| Rated capacity | 750W (AC); 750W / 400W (DC variants) |

### PSU I2C Addressing

PSU I2C addresses are set by PS_A0 (pull-up) and PS_A1 (pull-down):

| PSU | MCU Address | EEPROM Address | BMC Mux Channel | Mux Select Value |
|---|---|---|---|---|
| PSU1 | 0x59 | 0x51 | BMC_I2C_8 PCA9548 CH1 | 0x02 |
| PSU2 | 0x5A | 0x52 | BMC_I2C_8 PCA9548 CH0 | 0x01 |

### Host-Side Access (Fast Path)

Presence and power-good status are available via the CPLD at `i2c-1/0x32`,
register 0x10:

| Signal | Register Bit | sysfs Attribute | Polarity |
|---|---|---|---|
| PSU1 present | 0x10 bit 0 | `psu1_present` | Active-low (driver inverts) |
| PSU1 power good | 0x10 bit 1 | `psu1_pgood` | Active-high |
| PSU2 present | 0x10 bit 4 | `psu2_present` | Active-low (driver inverts) |
| PSU2 power good | 0x10 bit 5 | `psu2_pgood` | Active-high |

### BMC-Side Access (Slow Path -- PMBus Telemetry)

The `wedge100s-bmc-daemon` reads PMBus registers via the BMC:

| PMBus Register | Code | Quantity | Format |
|---|---|---|---|
| READ_VIN | 0x88 | AC input voltage | LINEAR11 |
| READ_IIN | 0x89 | AC input current | LINEAR11 |
| READ_IOUT | 0x8C | DC output current | LINEAR11 |
| READ_POUT | 0x96 | DC output power | LINEAR11 |
| MFR_MODEL | 0x9A | Model string | ASCII (not implemented -- requires block read) |

### LINEAR11 Decoding

All PMBus values are stored as raw LINEAR11 16-bit words in the daemon cache.
Python decodes them:

```
Bits [15:11]: 5-bit two's-complement exponent N
Bits [10:0]:  11-bit two's-complement mantissa Y
Value = Y * 2^N  (returns float in base SI units: V, A, W)
```

DC output voltage is computed as `POUT / IOUT` to avoid LINEAR16 `VOUT_MODE`
complexity (mirrors ONL `psui.c`). Returns `None` when `IOUT` is zero (no-load).

### Python API

Class `Psu` in `sonic_platform/psu.py`, 1-based index 1-2.

| Method | Source |
|---|---|
| `get_presence()` | CPLD sysfs `psu{N}_present` |
| `get_powergood_status()` | CPLD sysfs `psu{N}_pgood` |
| `get_voltage()` | `POUT / IOUT` from daemon cache |
| `get_current()` | `IOUT` from daemon cache (LINEAR11) |
| `get_power()` | `POUT` from daemon cache (LINEAR11) |
| `get_input_voltage()` | `VIN` from daemon cache (LINEAR11) |
| `get_input_current()` | `IIN` from daemon cache (LINEAR11) |
| `get_type()` | `'AC'` (hardcoded) |
| `get_capacity()` | `650.0` W (hardcoded) |

Telemetry cache TTL: 30 s.

### Known Limitations

- `get_model()` and `get_serial()` return `'N/A'`. PMBus MFR_MODEL (0x9A)
  requires an SMBus block-read transaction not implemented in the bmc-daemon.
- `set_status_led()` returns `False`; PSU LED control is not exposed via CPLD.
- PSU1 was unpowered in the lab during development; PSU1 PMBus telemetry is
  unverified on hardware.
- DC output voltage returns `None` at no-load (IOUT = 0).

---

## 11. QSFP Optics

### Hardware

32 QSFP28 cages (100G each). All presence detection and EEPROM access in Phase
2 is via `wedge100s-i2c-daemon` writing to `/run/wedge100s/`.

RESET and LP_MODE pins are on the mux board and are **not accessible from the
host CPU**. `set_lpmode()` and `reset()` return `False` on all ports.

### QSFP Port Numbering (OCP Spec Figure 19)

8 physical connectors, each with 4 QSFP cages:

| Connector | Designator | QSFP Ports (left to right) |
|---|---|---|
| 0 | J3300 | QSFP0, QSFP2, QSFP1, QSFP3 |
| 1 | J2600 | QSFP4, QSFP6, QSFP5, QSFP7 |
| 2 | J2700 | QSFP8, QSFP10, QSFP9, QSFP11 |
| 3 | J2800 | QSFP12, QSFP14, QSFP13, QSFP15 |
| 4 | J2900 | QSFP16, QSFP18, QSFP17, QSFP19 |
| 5 | J3000 | QSFP20, QSFP22, QSFP21, QSFP23 |
| 6 | J3100 | QSFP24, QSFP26, QSFP25, QSFP27 |
| 7 | J3200 | QSFP28, QSFP30, QSFP29, QSFP31 |

Many ports have "QSFP CHANNELS SWAPPED WITHIN THE QUAD" per the OCP spec SerDes
mapping table. Ports on connectors 2-7 (roughly QSFP8-31) have channel swaps
that must be handled by `phy_lane_swap` or equivalent in the BCM config.

### Presence Detection

Two PCA9535 16-bit I/O expanders provide insertion status:

| Logical Bus | I2C Address | Ports Covered | Mux Path |
|---|---|---|---|
| 36 | 0x22 | 0-15 | i2c-1 -> mux 0x74 ch2 |
| 37 | 0x23 | 16-31 | i2c-1 -> mux 0x74 ch3 |

Each PCA9535 has two 8-bit input registers (offset 0x00 = bits 0-7, offset
0x01 = bits 8-15 within the group). Bits are active-low: `0` = module present,
`1` = absent.

**XOR-1 interleave:** The bit position for port `N` within its group of 16 is
`(N % 16) ^ 1`. This even/odd swap matches physical cage order. Documented in
ONL `sfpi.c` as `onlp_sfpi_reg_val_to_port_sequence()` and verified on
hardware (2026-03-11).

Example: port 0 -> line `(0 % 16) ^ 1 = 1`, register 0x00 of 0x22, bit 1.

### EEPROM Access

Each QSFP cage's EEPROM (SFF-8636, address 0x50) is reached by:
1. Selecting the appropriate PCA9548 channel on mux 0x70-0x73
2. Reading from address 0x50

The daemon caches page 0 (256 bytes) on insertion to
`/run/wedge100s/sfp_N_eeprom`. Only page 0 is cached. Pages 1-3 (DOM data
beyond byte 128) are not accessible without the optoe kernel driver.

### EEPROM Safety

Budget DAC cable transceivers (FS Q28-PC02/Q28-PC01) have WP permanently
unasserted (tied to GND or unconnected). Any write reaching 0x50 on a selected
mux channel overwrites physical non-volatile EEPROM cells. Loading
`i2c_mux_pca954x` is an immediate EEPROM corruption event if any QSFP modules
are inserted. See [BEWARE_EEPROM.md](BEWARE_EEPROM.md) for full details.

### Python API

Class `Sfp` in `sonic_platform/sfp.py`, inherits `SfpOptoeBase`. 0-based
index 0-31.

| Method | Returns | Source |
|---|---|---|
| `get_presence()` | `bool` | `/run/wedge100s/sfp_N_present` (returns `False` if file missing or unreadable) |
| `read_eeprom(offset, num_bytes)` | `bytearray` or `None` | `/run/wedge100s/sfp_N_eeprom` |
| `get_eeprom_path()` | `str` | `/run/wedge100s/sfp_N_eeprom` (always returns daemon cache path) |
| `get_reset_status()` | `False` (always) | Not wired to host CPU |
| `get_lpmode()` | `False` (always) | Not wired to host CPU |
| `reset()` | `False` | Not supported |
| `set_lpmode(lpmode)` | `False` | Not supported |

### LP_MODE and RESET via PCA9535

The OCP spec defines LP_MODE and RESET as active-low signals on the QSFP
connectors. On the Wedge 100S, these signals are wired to PCA9535 I/O
expanders on the mux board:

| Logical Bus | I2C Address | Function | Ports |
|---|---|---|---|
| 34 | 0x20 | LP_MODE control | 0-15 |
| 35 | 0x21 | LP_MODE control | 16-31 |

However, these PCA9535 devices are behind PCA9548 mux 0x74 channels 0 and 1,
accessible only via the CP2112 mux tree. The daemon does not currently read or
write these registers. The Python API returns `False` for all LP_MODE and RESET
operations.

To implement LP_MODE or RESET in the future, the daemon would need to:
1. Select mux 0x74 channel 0 or 1
2. Write the appropriate bit in the PCA9535 output register
3. Ensure the write does not conflict with ongoing EEPROM or presence reads

### RXLOSS via PCA9535

| Logical Bus | I2C Address | Function | Ports |
|---|---|---|---|
| 38 | 0x24 | RXLOSS / Interrupt | 0-15 |
| 39 | 0x25 | RXLOSS / Interrupt | 16-31 |

Per OCP spec Table 13, these carry per-lane RXLOSS signals. Not read by the
current implementation.

### PCA9535 INT# Not Wired

Neither PCA9535 INT# pin (for the presence expanders at 0x22/0x23) is connected
to any host CPU GPIO. There is no interrupt-driven presence detection path.
Polling at 3 s intervals is the only mechanism.

`dmesg | grep pca953x` shows `pca953x 36-0022: using no AI` and
`pca953x 37-0023: using no AI`, confirming no auto-increment and no interrupt
wiring.

### i2c-Daemon QSFP Operations

The `wedge100s-i2c-daemon` performs these operations per invocation (every 3 s):

1. **System EEPROM** (once at first boot, skipped if cache exists):
   - Selects PCA9548 0x74 ch6
   - Reads 24C64 @ 0x50 in 512-byte chunks (2-byte 16-bit addressing)
   - Validates `TlvInfo\x00` magic header
   - Writes `/run/wedge100s/syseeprom` (8192 bytes binary)

2. **QSFP presence scan:**
   - Reads PCA9535 @ 0x22 (INPUT0+INPUT1) via mux 0x74 ch2 (ports 0-15)
   - Reads PCA9535 @ 0x23 via mux 0x74 ch3 (ports 16-31)
   - Decodes XOR-1 interleave and active-low polarity
   - Produces 32 binary presence bits

3. **Per-port logic:**
   - **Absent:** Deletes `sfp_N_eeprom`, writes `sfp_N_present="0"`
   - **Stable present** (cache exists, SFF-8024 identifier byte valid):
     Rewrites `sfp_N_present="1"`, skips EEPROM I2C
   - **Insertion or invalid cache:** Selects per-port mux channel, reads
     128 bytes (lower page 0x00) + 128 bytes (upper page 0x80) from 0x50;
     writes `sfp_N_eeprom` only if identifier byte is valid (0x01-0x7F)
   - **Removal:** `sfp_N_eeprom` deleted immediately (stale data not served)

**Runtime path selection:**
- **Phase 2 (normal):** Opens `/dev/hidraw0`; all mux-tree I2C via raw CP2112
  HID reports (AN495 protocol)
- **Phase 1 (fallback):** `/dev/hidraw0` unavailable; uses `i2c-dev` ioctl on
  buses 36/37 for PCA9535 and sysfs for EEPROM

### Test Bench Module Inventory (verified 2026-03-27)

14 of 32 ports populated:

| SONiC Port | 0-based | Vendor | Part Number | Type | DOM |
|---|---|---|---|---|---|
| Ethernet0 | 0 | Mellanox | MCP7F00-A002R | Passive DAC 2m | None |
| Ethernet8 | 2 | Mellanox | MCP1600-C01A | Passive DAC | None |
| Ethernet12 | 3 | FS | Q28-PC03 | Passive DAC 3m | None |
| Ethernet16 | 4 | FS | Q28-PC02 | Passive DAC 2m | None |
| Ethernet32 | 8 | FS | Q28-PC02 | Passive DAC 2m | None |
| Ethernet48 | 12 | FS | Q28-PC02 | Passive DAC 2m | None |
| Ethernet64 | 16 | Mellanox | MCP7904-X002A | Passive DAC | None |
| Ethernet76 | 19 | AOI | AQPLBCQ4EDMA1105 | Active optical | byte220=0x0c |
| Ethernet80 | 20 | Amphenol | NDAQGF-F305 | Passive DAC | None |
| Ethernet84 | 21 | Arista Networks | QSFP28-SR4-100G | Optical SR4 | byte220=0x0c |
| Ethernet100 | 25 | Arista Networks | QSFP28-SR4-100G | Optical SR4 | byte220=0x0c |
| Ethernet104 | 26 | Arista Networks | QSFP28-LR4-100G | Optical LR4 | byte220=0x0c |
| Ethernet108 | 27 | Arista Networks | QSFP28-SR4-100G | Optical SR4 | byte220=0x0c |
| Ethernet112 | 28 | FS | Q28-PC01 | Passive DAC 1m | None |

Passive copper DAC cables have no DOM (byte 220 = 0x00, `temp_support=False`,
`temp=N/A` is correct behavior). Arista SR4 modules report byte 220 = 0x0c
(bits 3+2 = bias/power monitoring; voltage N/A is correct per module spec).

### Known Limitations

- LP_MODE and RESET pins not accessible from host CPU.
- Only page 0 (256 bytes) cached; no DOM data beyond byte 128.
- No interrupt-driven presence notification.
- EEPROM cache written only on insertion events.
- Budget DAC cables have WP unasserted; any write to 0x50 corrupts EEPROM.
- `get_model()` and `get_serial()` resolved from EEPROM by parent class
  `SfpOptoeBase` via `read_eeprom()`.

---

## 12. LED Subsystem

### System LEDs

Two system LEDs controlled via CPLD registers:

| LED | CPLD Register | Owner | Function |
|---|---|---|---|
| SYS1 | 0x3E | `chassis.py` / `healthd` | System-status indicator |
| SYS2 | 0x3F | `led_control.py` / `ledd` | Port-activity indicator |

### System LED Encoding

| Value | Color | Blink | Notes |
|---|---|---|---|
| 0x00 | Off | No | -- |
| 0x01 | Red | No | `'amber'` maps here (no amber hardware) |
| 0x02 | Green | No | Normal operation |
| 0x04 | Blue | No | -- |
| 0x08 | Off | Yes | -- |
| 0x09 | Red | Yes | -- |
| 0x0A | Green | Yes | -- |
| 0x0C | Blue | Yes | -- |

**SYS2 logic:** Binary -- green when at least one port has
`netdev_oper_status == 'up'`, off otherwise. No per-port system LED hardware
exists for SYS2.

### Port LEDs (Tomahawk LEDUP)

32 QSFP28 cages x 4 LEDs per cage = 128 physical LEDs arranged in 2 rows
(TOP and BOT). Each port uses a 12-bit stream: 4 lanes x 3 bits (B-G-R per
lane).

### Port LED Signal Chain

```
BCM56960 LEDUP0/LEDUP1 scan chains
  -> CPLD register 0x3C (mode select + enable)
    -> 24x 74LV164 shift registers (192 bits total)
      -> Front-panel LED cages
```

Three serial LED streams: LED_CLK0/DATA0, LED_CLK1/DATA1, LED_CLK2/DATA2.

### CPLD LED Mode Control (Register 0x3C)

Accessible from BMC only (CPLD address 0x31 on BMC_I2C_13):

| Bits [2:0] | Mode | Description |
|---|---|---|
| 010 | Tomahawk direct | BCM LEDUP drives LEDs directly |
| 110 | FB 12-bit format | Facebook-specific LED encoding |
| 000 | CPLD test logic | Test pattern mode |

| Bit | Name | Function |
|---|---|---|
| 1 | `th_led_en` | Enable Tomahawk LEDUP output |
| 3 | `walk_test_en` | Walking LED test pattern |
| 6 | `led_test_blink_en` | Blink test mode |
| 7 | `led_test_mode_en` | Global test mode |

**Factory default at power-on:** `0xE0` (all test bits set, LEDUP gated).
After platform-init: `clear_led_diag.sh` sets register to `0x02`
(`th_led_en=1`, all test modes off). (verified 2026-03-26)

### LED Button

`LED_Button_Select` (physical front-panel button) toggles between TOP and BOT
row display. This is a hardware-only feature; no software control exists.

### BCM LED Program

The LED bytecode loaded via `led_proc_init.soc` is the same bytecode as
AS7712-32X (same Tomahawk chip). However, the PORT ORDER REMAP tables differ
because the Wedge 100S has different PCB routing of the LEDUP scan chain. The
remap derives LED physical port index as `(first_serdes_lane - 1) / 4` from
the BCM config file.

### Port LED Color Decode (BCM Bytecode)

| Port State | LEDUP0 (Green) | LEDUP1 (Amber) | Visual Color |
|---|---|---|---|
| No module / link down | Off | Off | Dark |
| Link up, 100G | On | Off | Green |
| Link up, 10G/25G | On | On or blink | Amber or yellow |
| Activity (TX/RX) | Blink | -- | Green blink |

### LED qsfp_led_position Strap

BMC GPIO59 value determines QSFP LED scan chain direction:
- `gpio59=1`: Standard direction (port 0 at left/low end of front panel)
- Written to `/run/wedge100s/qsfp_led_position` by bmc-daemon at startup

(verified 2026-03-26: gpio59=1)

### Known Limitations

- No amber LED hardware; `'amber'` silently maps to red.
- Fan tray and PSU LEDs are not individually addressable from the host.
- Blue LED and blink variants are supported by hardware but not used by any
  current Python code.
- No interrupt-driven LED change; all updates are explicit writes.

---

## 13. OOB Ethernet

### Hardware

| Attribute | Value |
|---|---|
| Switch IC | BCM5387 5-port SGMII switch |
| PHY (x3) | BCM54616S |
| Topology | 5-port switch fabric connecting COM-e, BMC, front panel, and Tomahawk |

### BCM5387 Port Assignment

| Port | Connection | Interface | PHY | Status |
|---|---|---|---|---|
| P0 | COM-e (host CPU) | SGMII | BCM54616S | Active (management eth0) |
| P1 | Tomahawk Eagle Core 10G | SGMII | Direct wired | Reserved / unused |
| P2 | BMC (RGMII B2B) | RGMII | BCM54616S (reserved) | Reserved |
| P3 | Front-panel RJ45 OOB | SGMII | BCM54616S | Active (front-panel management) |
| P4 | BMC | SGMII | BCM54616S | Active (BMC management) |

The front-panel RJ45 and the host CPU share the same L2 broadcast domain via
the BCM5387 switch. The Tomahawk Eagle Core connection (P1) is wired but
reserved/unused in the current configuration.

### BCM54616S PHY Details

Three BCM54616S PHYs are used on the OOB switch fabric:

| PHY | Connection | Speed | Interface to BCM5387 |
|---|---|---|---|
| PHY-1 | COM-e (host CPU NIC) | 1G | SGMII |
| PHY-2 | Front-panel RJ45 | 10/100/1000 | SGMII |
| PHY-3 | BMC (P4) | 1G | SGMII |

Each PHY has an EEPROM accessible via the BMC_I2C_8 PCA9548 mux:
- CH2: BMC PHY EEPROM @ 0x50
- CH3: Front-panel PHY EEPROM @ 0x50

### Eagle Core (Unused)

The Tomahawk BCM56960 has an internal "Eagle Core" 10G SGMII MAC that is wired
to BCM5387 port P1. This provides a potential in-band management path through
the switching ASIC, but it is reserved and unused in the current configuration.
Enabling it would require BCM config changes and additional SONiC integration.

### Management Access

| Target | Address | Method |
|---|---|---|
| SONiC host | 192.168.88.12 | SSH via front-panel RJ45 or OOB network |
| OpenBMC | 192.168.88.13 | SSH (root/0penBmc) |
| BMC fallback | fe80::ff:fe00:1%usb0 | USB-CDC-ECM IPv6 link-local |
| BMC serial | /dev/ttyACM0 @ 57600 | USB-CDC-ACM |
| Peer (Arista EOS) | 192.168.88.14 | SSH (admin/0penSesame) |

---

## 14. Power Distribution

### Power Architecture Overview

The Wedge 100S uses a two-domain power architecture:

1. **Standby domain:** Always powered when at least one PSU is present.
   Supplies BMC, CPLD, and low-power rails.
2. **Main domain:** Powered on by the PWR1014A power sequencer. Supplies
   Tomahawk ASIC, COM-e CPU, and all high-power components.

### Power Sequencer

| Attribute | Value |
|---|---|
| Part | Lattice PWR1014A |
| Bus/Address | BMC_I2C_3 / 0x3A |
| Function | Sequences 12 rails, monitors 10 voltage rails |
| Control | BMC-managed; no host access |

### Tomahawk Core Power (Main Domain)

| Rail | Regulator | Topology | Max Current | Notes |
|---|---|---|---|---|
| 1.0V Core (ROV) | IR3581 + 6x IR3556 | 6-phase | 160A | Tomahawk VDD core; voltage set by ROV pins |
| 1.0V Analog | IR3584 + 2x IR3556 | 2-phase | 50A | Tomahawk analog supply |
| 3.3V Main | IR3584 + 2x IR3556 | 2-phase | 50A | I/O supply |

The IR3581 and IR3584 voltage regulators are accessible via BMC_I2C_2:

| Address | Device | Rail |
|---|---|---|
| 0x10 | IR3581 | 1.0V Core (6-phase master) |
| 0x12 | IR3584 | 1.0V Analog (2-phase) |
| 0x14 | IR3584 | 3.3V Main (2-phase) |

### Small Power Rails (Main Domain)

| Rail | Regulator | Max Current |
|---|---|---|
| 1.8V | TPS54329 | 3A |
| 1.25V | TPS53318 | 6A |

Additional small rails use TPS54339 (3A) and TPS53318 (6A) regulators.

### Standby Domain Rails

All standby rails use TPS62130 (1.5A) regulators:

| Rail | Notes |
|---|---|
| 3.3V_STBY | Standby power for CPLD, BMC, PHY |
| 2.5V_STBY | -- |
| 1.8V_STBY | -- |
| 1.5V_STBY | -- |
| 1.2V_STBY | -- |

### ROV (Regulator Output Voltage)

The Tomahawk core voltage is set by ROV status pins read by the IR3581. The
CPLD register 0x08 exposes the ROV status. The voltage is typically 1.0V but
may be adjusted by the ASIC's ROV pins for process-voltage-temperature
optimization. This is a hardware-only mechanism; no software intervention is
required.

### Power Sequencing Order

The PWR1014A sequences power-up in a defined order (typical sequence):

1. Standby rails (3.3V_STBY, 2.5V_STBY, 1.8V_STBY, 1.5V_STBY, 1.2V_STBY)
2. 3.3V Main
3. 1.8V, 1.25V
4. 1.0V Analog
5. 1.0V Core (ROV)

Power-down is the reverse sequence. The sequencer monitors all 10 voltage rails
and asserts a power-good signal only when all rails are within tolerance.

### Power Rail Monitoring Points

The PWR1014A monitors these voltage rails and reports power-good to the CPLD:

| Rail | Nominal | Tolerance | Domain | Monitor |
|---|---|---|---|---|
| 12V PSU | 12.0V | +/- 5% | Input | PWR1014A |
| 3.3V_STBY | 3.3V | +/- 5% | Standby | PWR1014A |
| 2.5V_STBY | 2.5V | +/- 5% | Standby | PWR1014A |
| 1.8V_STBY | 1.8V | +/- 5% | Standby | PWR1014A |
| 1.5V_STBY | 1.5V | +/- 5% | Standby | PWR1014A |
| 1.2V_STBY | 1.2V | +/- 5% | Standby | PWR1014A |
| 3.3V Main | 3.3V | +/- 5% | Main | PWR1014A + IR3584 |
| 1.8V Main | 1.8V | +/- 5% | Main | PWR1014A |
| 1.25V Main | 1.25V | +/- 5% | Main | PWR1014A |
| 1.0V Analog | 1.0V | +/- 3% | Main | IR3584 |
| 1.0V Core | ROV-set | +/- 1% | Main | IR3581 |

### Power Consumption Budget (Estimated)

| Component | Typical Power | Notes |
|---|---|---|
| Tomahawk BCM56960 | ~200-300W | Varies with traffic pattern and port config |
| CPU (D1508) | ~15-25W | Depends on utilization |
| QSFP28 modules (32x) | ~32-96W | 1-3W per module depending on type |
| Fans (5x) | ~30-60W | Varies with speed setting |
| BMC + standby | ~5-10W | Always-on |
| Other (PHYs, switch, etc.) | ~10-20W | Misc components |
| **Total estimated** | **~300-500W** | Within 750W PSU budget |

### SONiC Implementation Status

| Component | Implemented | Notes |
|---|---|---|
| PSU presence/pgood | Yes | CPLD sysfs via `wedge100s_cpld` driver |
| PSU PMBus telemetry | Yes | Via bmc-daemon (VIN, IIN, IOUT, POUT) |
| PWR1014A monitoring | No | BMC-side only; not exposed to host |
| IR3581/IR3584 voltage readback | No | BMC_I2C_2; not read by bmc-daemon |
| Power sequencer status | No | BMC_I2C_3; not exposed |
| ROV status | No | CPLD register 0x08 not in sysfs |
| Power rail monitoring | No | Available via PWR1014A but not implemented |
| Voltage margin tuning | No | IR3581/IR3584 support VID but not used |

---

## 15. Security

### TPM (Trusted Platform Module)

| Attribute | Value |
|---|---|
| Part | Infineon SLB9645 (or SLB9660 on some units) |
| Interface | I2C (BMC_I2C_10) |
| TPM spec | 1.2 (SLB9645) or 2.0 (SLB9660) |
| Access | BMC-side only; not directly accessible from host |

The TPM is connected to the BMC I2C bus 10 and is not accessible from the host
CPU's I2C bus. Using the TPM for measured boot or secure key storage requires
BMC firmware support.

### Intel TXT

The Intel Pentium D1508 supports Trusted Execution Technology (TXT). This
provides a hardware root of trust for measured launch of the boot environment.
TXT is not currently configured or used in the SONiC build.

### Dual BIOS SPI Flash

The CPLD provides dual-BIOS support via register 0x2F:

| Feature | CPLD Register | Status |
|---|---|---|
| Dual boot enable | 0x2F bit 0 (DUAL_BOOT_EN) | Available, not used by SONiC |
| Secondary flash write protect | 0x2F bit 1 (EN_2ND_Flash_WP) | Available, not used by SONiC |
| Force secondary write | 0x2F bit 2 (Force_2nd_WR) | Available, not used by SONiC |

This provides a recovery mechanism: if the primary BIOS is corrupted, the CPLD
can boot from the secondary SPI flash. Write protection prevents accidental
overwrite of the backup BIOS.

### CPLD Firmware Update

The BMC manages CPLD firmware updates via JTAG-over-GPIO. No host-side CPLD
update mechanism exists. The CPLD is non-volatile (Altera MAX-V) and retains
its configuration without external power.

### Physical Security Features

| Feature | Mechanism | Status |
|---|---|---|
| Chassis intrusion detection | Not present | No tamper switch on this platform |
| PSU lock | Physical latch | Hardware only |
| Fan tray lock | Physical latch | Hardware only |
| Front panel | Physical button for LED row toggle | No software lockout |

### I2C Bus Security Considerations

The CP2112 USB-HID bridge is the primary attack surface for I2C-based attacks
on this platform. Any process with access to `/dev/hidraw0` or `/dev/i2c-1`
can read/write any device on the mux tree, including QSFP EEPROMs, system
EEPROM, and CPLD registers.

Mitigations in the current design:
- `/dev/hidraw0` is opened exclusively by `wedge100s-i2c-daemon`
- `i2c_mux_pca954x` not loaded (no kernel virtual buses to attack)
- `at24` and `optoe` not loaded (no sysfs write paths to EEPROM)
- CPLD driver uses `I2C_FUNC_SMBUS_BYTE_DATA` only (no block write)
- Python platform code reads cache files, never initiates I2C

See [BEWARE_EEPROM.md](BEWARE_EEPROM.md) for the EEPROM corruption incident
that motivated this security posture.

### OpenBMC Security Considerations

The OpenBMC firmware on this platform is a legacy Facebook build with known
limitations:
- Default root password (`0penBmc`) cannot be changed persistently
- `authorized_keys` is cleared on every BMC reboot
- No IPMI authentication (IPMI not present)
- REST API (port 8080) has no authentication
- BMC-to-host USB-CDC-ECM provides network access with root credentials

### SONiC Security Implementation Status

| Feature | Status | Notes |
|---|---|---|
| TPM | Not used | BMC-side only; requires firmware support |
| Intel TXT | Not configured | D1508 supports it |
| Dual BIOS | Not configured | CPLD registers available |
| Secure boot | Not implemented | UEFI secure boot not enabled |
| CPLD write protect | Not configured | Register 0x2F available |
| I2C bus isolation | Implemented | Daemon-mediated, no kernel mux drivers |
| EEPROM write protection | Partial | Daemon is read-only; budget DACs have no hardware WP |

---

## Appendix A: Console and SSH Access

| Target | Access Method | Notes |
|---|---|---|
| SONiC switch | `ssh admin@192.168.88.12` | Kernel 6.1.0-29-2-amd64, use python3 |
| ONIE | `ssh root@192.168.88.12` | No python available |
| OpenBMC | `ssh root@192.168.88.13` (pw: `0penBmc`) | `authorized_keys` cleared on reboot |
| BMC fallback | `root@fe80::ff:fe00:1%usb0` or `/dev/ttyACM0` @ 57600 | Key: `/etc/sonic/wedge100s-bmc-key` |
| Peer (Arista EOS) | `sshpass -p '0penSesame' ssh -tt admin@192.168.88.14` | -- |
| Serial console | `ssh bang-lorax tail -n 500 screenlog.ttyUSB2.0` | Host ttyS0 @ 57600 |

## Appendix B: Build Quick Reference

```bash
# Platform .deb (trixie -- host filesystem)
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb

# Submodule packages (bookworm -- Docker containers)
BLDENV=bookworm make target/debs/bookworm/swss_1.0.0_amd64.deb

# Full ONIE image (no BLDENV prefix -- runs both passes)
make target/sonic-broadcom.bin
```

## Appendix C: Key File Paths

### Platform Fork (`/export/sonic/sonic-buildimage`)

| Resource | Path |
|---|---|
| Device directory | `device/accton/x86_64-accton_wedge100s_32x-r0/` |
| Platform modules | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/` |
| CPLD driver source | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules/wedge100s_cpld.c` |
| i2c-daemon source | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-i2c-daemon.c` |
| bmc-daemon source | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c` |
| Python platform API | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/` |
| BCM config | `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm` |
| LED program | `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/led_proc_init.soc` |
| Port config | `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/port_config.ini` |

### Development Repo (`/export/sonic/sonic-wedge100s-devel`)

| Resource | Path |
|---|---|
| This guide | `notes/PLATFORM_GUIDE.md` |
| Workflow bible | `docs/workflow.md` |
| Developer's guide | `guides/SONiC-wedge100s-Developers-Guide.md` |
| Test suite | `tests/` |
| Notes | `notes/` |

### Target System (`/run/wedge100s/`)

| File | Content |
|---|---|
| `syseeprom` | 8192 bytes binary, ONIE TlvInfo format |
| `sfp_N_present` (N=0..31) | ASCII "0" or "1" |
| `sfp_N_eeprom` (N=0..31) | 256 bytes binary, SFF-8636 page 0 |
| `thermal_N` (N=1..7) | Decimal millidegrees C |
| `fan_present` | Decimal bitmask |
| `fan_N_front` (N=1..5) | Decimal RPM |
| `fan_N_rear` (N=1..5) | Decimal RPM |
| `psu_N_vin` (N=1,2) | Decimal LINEAR11 raw word |
| `psu_N_iin` (N=1,2) | Decimal LINEAR11 raw word |
| `psu_N_iout` (N=1,2) | Decimal LINEAR11 raw word |
| `psu_N_pout` (N=1,2) | Decimal LINEAR11 raw word |
| `led_sys1` | Hex LED value |
| `led_sys2` | Hex LED value |
| `qsfp_led_position` | "0" or "1" |

## Appendix D: Known Platform Issues

### EEPROM Corruption from Kernel I2C Drivers

Loading `i2c_mux_pca954x`, `optoe`, or `at24` while QSFP modules are inserted
causes EEPROM corruption. The kernel driver's probe writes reach physical EEPROM
cells because budget DAC cables (FS Q28-PC02/Q28-PC01) have write-protect pins
unasserted. Six transceivers were corrupted during development before the
daemon-mediated architecture was adopted. Full details in
[BEWARE_EEPROM.md](BEWARE_EEPROM.md).

### SSH Black Holes During BCM IRQ Storms

The BCM56960 generates interrupt storms (2,500-4,400 IRQ/s) during cold-start,
xcvrd DOM batch processing, and BGP ARP retry cycles. These storms starve
NET_TX/NET_RX softirqs, causing new TCP connections to fail for 3-5 second
windows. Mitigation: `tcp_syn_retries=2` reduces the observable gap from ~33 s
to <=7 s. See [BEWARE_IRQ.md](BEWARE_IRQ.md).

### Ethernet104/108 Permanently Down

Two CWDM4 optical links (Ethernet104 and Ethernet108) have been down since
install (~52 days at time of documentation). Confirmed physical issue: SONiC
serdes generates TX signal (PRBS test passes), but zero photons reach the EOS
peer. Not a software problem. See [BEWARE_OPTICS.md](BEWARE_OPTICS.md).

### Auto-Negotiation Silent No-Op

The SONiC CLI accepts `config interface autoneg enabled` but the SAI does not
program the ASIC. `SAI_PORT_ATTR_AUTO_NEG_MODE` remains `false` because the BCM
config has `phy_an_c73=0x0`. No error is logged. RS-FEC must be set explicitly.

### onie-syseeprom Reports False Success

`onie-syseeprom -s` reports "Programming passed" even when it wrote nothing. The
tool writes to the COM-e EC chip (i2c-1/0x50), which ACKs all writes but
discards them. The verification step reads from an in-memory buffer, not
hardware. Do not trust `onie-syseeprom` output on this platform.

### BMC authorized_keys Cleared on Reboot

The OpenBMC firmware clears `/root/.ssh/authorized_keys` on every reboot. Any
SSH key-based access to the BMC must be re-established after a BMC power cycle.
The `wedge100s-bmc-daemon` uses password-based access via `/dev/ttyACM0` and is
not affected.

### CP2112 Mux Channel Corruption Under Concurrent Access

If two processes (e.g., daemon and kernel driver) access the CP2112 bridge
simultaneously, the PCA9548 mux-select state becomes corrupted. This causes
EEPROM reads to return garbage data from the wrong mux channel. The
daemon-mediated architecture prevents this, but any manual `i2cget`/`i2cset`
while the daemon is running will trigger corruption.

### IRQ Number Instability

The BCM ASIC IRQ number changes between kernel configurations:
- Without `noapic`: IRQ 16 (IO-APIC, movable)
- With `noapic` (current): IRQ 11 (XT-PIC, pinned to CPU0)

Never hardcode IRQ numbers in platform code. Always parse `/proc/interrupts`
for the `linux-kernel-bde` label.

### PCA9535 INT# Not Connected

Neither PCA9535 INT# pin (presence detection) is connected to the host CPU.
There is no interrupt-driven QSFP hotplug notification. Presence must be polled.
The minimum practical polling interval is ~1 s (limited by CP2112 USB HID
latency and IRQ budget).

---

*This document was written 2026-04-09 as the consolidated platform hardware and
architecture reference for the Accton Wedge 100S-32X SONiC port. It replaces
the combination of HARDWARE.md and ARCHITECTURE.md as single-source-of-truth.
Companion documents (BEWARE_*.md, SUBSYSTEMS_*.md, HARDWARE_I2C.md) remain
authoritative for their specific deep-dive topics.*
