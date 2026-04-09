# Wedge 100S-32X SONiC Port: OCP v1.3 Design Gaps Specification

Chip-by-chip, register-by-register audit of OCP spec v1.3 capabilities vs. the
current SONiC implementation, organized as a prioritized backlog.

**Document owner:** FlaxAdvisors/sonic-wedge100s-devel  
**Hardware:** Accton Wedge 100S-32X (Facebook Wedge 100S, Broadcom Tomahawk BCM56960)  
**OCP Spec:** Wedge 100S Hardware Specification v1.3  
**Date:** 2026-04-09  
**Status:** Working engineering spec

---

## Priority Definitions

| Priority | Meaning | Criteria |
|----------|---------|----------|
| P0 | Correctness | Wrong behavior, data corruption risk, incorrect documentation |
| P1 | Production-readiness | Missing for reliable 24/7 unattended operation |
| P2 | Feature-completeness | OCP spec capability not exposed in SONiC |
| P3 | Nice-to-have | Polish, optimization, OCP-rack-specific features |

---

## P0 -- Correctness

### GAP-001: CPU identity error in HARDWARE.md

| Field | Detail |
|-------|--------|
| **ID** | GAP-001 |
| **Title** | CPU identity error in HARDWARE.md |
| **Priority** | P0 |
| **OCP Spec Ref** | Section 4.1, 9.1 -- Intel Broadwell-DE D1508 |
| **Hardware** | Intel Pentium D1508 @ 2.20GHz (COM-e module) |
| **Current State** | HARDWARE.md states "Intel Atom C2538" -- this is the Wedge100 (non-S) CPU. Confirmed wrong via `lscpu` on target hardware. |
| **Gap** | Incorrect CPU identification |
| **Impact** | Misleading for contributors; wrong thermal envelope (15W TDP vs 20W), wrong core count assumptions (4C/4T Atom vs 2C/4T Broadwell-DE), wrong ISA generation (Silvermont vs Broadwell) |
| **Remediation** | Correct HARDWARE.md; superseded by new PLATFORM_GUIDE.md which has the correct identity |
| **Effort** | S |
| **Topic Branch** | `wedge100s/docs` |

### GAP-002: PSU CPLD register polarity verification

| Field | Detail |
|-------|--------|
| **ID** | GAP-002 |
| **Title** | PSU CPLD register polarity verification incomplete |
| **Priority** | P0 |
| **OCP Spec Ref** | Section 7.7.2, page 54 -- Register 0x10, PSU status bits |
| **Hardware** | SYSCPLD register 0x10 at I2C 1-0032 |
| **Current State** | `wedge100s_cpld.c` reads 0x10 and correctly handles: D[0] PSU-1 Present (active-low, inverted in `show_psu1_present`), D[1] PSU-1 Power Output OK (active-high, read directly in `show_psu1_pgood`), D[4] PSU-2 Present (active-low, inverted), D[5] PSU-2 Power Output OK (active-high). Bits D[2], D[3], D[6], D[7] are not read at all. |
| **Gap** | OCP spec defines 8 bits in 0x10: D[0] PSU-1 Present (0=present, 1=absent), D[1] PSU-1 Output OK (0=bad, 1=OK), D[2] PSU-1 Input OK (0=bad, 1=OK), D[3] PSU-1 Alarm (0=alarm, 1=normal), D[4-7] same for PSU-2. Only 4 of 8 bits verified against spec. The 4 implemented bits appear correct but the polarity of D[2]/D[3]/D[6]/D[7] has never been verified on hardware. |
| **Impact** | If alarm or input-power polarity is assumed wrong when these bits are eventually exposed, incorrect status will be reported. The existing presence/pgood bits are confirmed correct on hardware. |
| **Remediation** | (1) Read register 0x10 on live hardware with both PSUs in various states (present/absent, powered/unpowered, alarm condition if inducible). (2) Verify all 8 bits match OCP spec polarity. (3) Document verified polarities in `wedge100s_cpld.c` register map header. (4) Add test case to `tests/` that validates sysfs output against expected hardware state. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-003: QSFP lane-swap validation against OCP spec

| Field | Detail |
|-------|--------|
| **ID** | GAP-003 |
| **Title** | QSFP lane-swap / polarity-flip not validated against OCP Table 10 |
| **Priority** | P0 |
| **OCP Spec Ref** | Section 7.1, Table 10, pages 25-38 -- QSFP channel swap annotations |
| **Hardware** | BCM56960 (Tomahawk) SerDes, QSFP cage wiring |
| **Current State** | `th-wedge100s-32x-flex.config.bcm` has per-port `phy_xaui_rx_polarity_flip` and `phy_xaui_tx_polarity_flip` settings. These were derived from ONL reference and operational testing, but have not been systematically cross-checked against OCP spec Table 10 channel assignments. |
| **Gap** | OCP spec Table 10 shows channel swaps on connectors 2-7 (physical QSFP8 and above), annotated as "QSFP CHANNELS SWAPPED WITHIN THE QUAD" for both RX and TX. A full lane-by-lane audit of all 32 ports has not been performed. |
| **Impact** | Incorrect lane swap on a port causes CRC errors, link failure, or intermittent bit errors. May explain known issues with certain optics on specific ports (documented in BEWARE_OPTICS.md). |
| **Remediation** | (1) Extract all 32 port entries from OCP Table 10 into a spreadsheet: physical port, logical lane 0-3, RX/TX swap status. (2) Cross-reference each port's `phy_xaui_rx_polarity_flip` and `phy_xaui_tx_polarity_flip` bitmask in BCM config. (3) Identify mismatches. (4) Test corrected values on hardware with PRBS eye-diagram measurements. (5) Update `th-wedge100s-32x-flex.config.bcm`. |
| **Effort** | M |
| **Topic Branch** | `wedge100s/chipset-config` |

---

## P1 -- Production-Readiness

### GAP-010: Reset reason not reported

| Field | Detail |
|-------|--------|
| **ID** | GAP-010 |
| **Title** | CPLD reset reason registers not read |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.7.7, page 52 -- Registers 0x0D (reset reason), 0x0E (reset source 1), 0x0F (reset source 2) |
| **Hardware** | SYSCPLD registers 0x0D, 0x0E, 0x0F at I2C 1-0032 |
| **Current State** | None of these registers are defined in `wedge100s_cpld.c`. SONiC `show platform reboot-cause` has no data source. `Component.get_reboot_cause()` in the platform API returns unknown. |
| **Gap** | Register 0x0D encodes: D[7:6] power-cycle vs standby reset vs main reset, D[5:0] source (front panel button, debug button, software hot/warm/cold/power reset, BMC request, BMC watchdog). Registers 0x0E and 0x0F provide per-source detail: 0x0E covers front panel, debug header, FB header, SW hot/warm/cold/power sources; 0x0F covers BMC all/TH/COM-e/main/watchdog sources. None are read. |
| **Impact** | Operators cannot distinguish planned restarts from watchdog reboots, power glitches, or BMC-initiated resets. Critical for root cause analysis in production. SONiC health monitoring expects this data. |
| **Remediation** | (1) Add `#define REG_RESET_REASON 0x0D`, `REG_RESET_SRC1 0x0E`, `REG_RESET_SRC2 0x0F` to `wedge100s_cpld.c`. (2) Add sysfs attributes `reset_reason`, `reset_source1`, `reset_source2`. (3) Map bit patterns to SONiC reboot cause enum in `component.py` `get_reboot_cause()`. (4) Write-clear the registers after reading (per OCP spec, these are sticky latched bits). (5) Save last-read value to `/run/wedge100s/reset_reason` for persistence across daemon restarts. |
| **Effort** | M |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-011: QSFP RXLOSS signals not monitored

| Field | Detail |
|-------|--------|
| **ID** | GAP-011 |
| **Title** | PCA9535 RXLOSS expanders not read |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.6, Table 13, pages 47-48 -- PCA9535 at 0x24 (ports 0-15) and 0x25 (ports 16-31), RXLOSS signals |
| **Hardware** | PCA9535 GPIO expanders at I2C addresses 0x24 and 0x25, behind PCA9548 mux 0x74 channels 4 and 5 |
| **Current State** | `wedge100s-i2c-daemon.c` reads PCA9535 at 0x22/0x23 (mux channels 2/3) for presence only. The RXLOSS expanders at 0x24/0x25 (mux channels 4/5) are never accessed. No reference to 0x24 or 0x25 exists in the daemon source. |
| **Gap** | Hardware-level RX loss-of-signal indicators from the QSFP cage are available but not read. These are independent of ASIC link state and detect physical-layer faults (dirty fiber, broken connector, failing optic) before the ASIC reports link-down. |
| **Impact** | Fiber faults and failing optics cannot be detected until the ASIC reports link-down, which is slower and less specific. No differentiation between fiber-side and electrical-side failures. |
| **Remediation** | (1) Add PCA9535 addresses 0x24/0x25 and mux channels 4/5 to the daemon's poll constants. (2) Read INPUT registers (0x00, 0x01) from each expander on each poll cycle, same XOR-1 interleave as presence. (3) Write per-port RXLOSS to `/run/wedge100s/sfp_N_rxloss` (0=OK, 1=loss). (4) Expose in `sfp.py` via `get_rx_los()` list. (5) Active-low: 0 = loss of signal, 1 = signal OK (verify on hardware). |
| **Effort** | M |
| **Topic Branch** | `wedge100s/sfp-optics` |

### GAP-012: On-board power rail health not monitored

| Field | Detail |
|-------|--------|
| **ID** | GAP-012 |
| **Title** | CPLD power status registers 0x11/0x12 not read |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.7.3, page 55 -- Register 0x11 (power status 1), 0x12 (power status 2) |
| **Hardware** | SYSCPLD registers 0x11, 0x12 at I2C 1-0032 |
| **Current State** | Neither register is defined in `wedge100s_cpld.c`. No sysfs attributes exist. |
| **Gap** | Register 0x11 contains PWR_STBY_OK (standby 3.3V power good). Register 0x12 contains: D[0] VCORE_VRDY1 (Tomahawk core VRM power ready), D[1] VCORE_HOT (core VRM over-temperature), D[2] VANLOG_VRDY1 (analog VRM ready), D[3] VANLOG_HOT (analog VRM over-temp), D[4] V3V3_VRDY1 (3.3V VRM ready), D[5] V3V3_HOT (3.3V VRM over-temp). None are read. |
| **Impact** | Tomahawk core voltage regulator thermal events (VCORE_HOT, VANLOG_HOT) are invisible. These indicate the ASIC is approaching thermal throttling or emergency shutdown. In a headless rack deployment, this is the difference between graceful mitigation and a surprise outage. |
| **Remediation** | (1) Add `#define REG_POWER_STATUS1 0x11`, `REG_POWER_STATUS2 0x12` to `wedge100s_cpld.c`. (2) Add sysfs attributes: `pwr_standby_ok`, `vcore_ready`, `vcore_hot`, `vanalog_ready`, `vanalog_hot`, `v3v3_ready`, `v3v3_hot`. (3) Surface `*_hot` bits as platform health events or thermal sensor alarms. (4) Verify bit polarity on hardware. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-013: PSU alarm bits not monitored

| Field | Detail |
|-------|--------|
| **ID** | GAP-013 |
| **Title** | PSU alarm bits (D[3]/D[7] of register 0x10) not read |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.7.2, page 54 -- Register 0x10 D[3] (PSU-1 Alarm) and D[7] (PSU-2 Alarm) |
| **Hardware** | SYSCPLD register 0x10 bits 3 and 7, I2C 1-0032 |
| **Current State** | `wedge100s_cpld.c` reads register 0x10 but only exposes D[0]/D[4] (presence) and D[1]/D[5] (power output OK). Bits D[3] and D[7] are read by the I2C transaction but discarded. |
| **Gap** | D[3] and D[7] carry PSU alarm status: 0=PSU has alarm (fan failure, over-temp, input brownout), 1=normal. These early-warning bits are not exposed. |
| **Impact** | PSU degradation events (internal fan failure, PSU over-temperature, input voltage brownout) go undetected until PSU output actually fails, losing the early warning window that allows scheduled maintenance. |
| **Remediation** | (1) Add `#define PSU1_ALARM_BIT 3` and `#define PSU2_ALARM_BIT 7` to `wedge100s_cpld.c`. (2) Add sysfs attributes `psu1_alarm` and `psu2_alarm` (1=alarm, 0=normal, inverting the active-low bit). (3) Add to `psu.py` `get_status_alert()`. (4) Verify polarity per GAP-002 audit. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-014: PSU input-OK not monitored

| Field | Detail |
|-------|--------|
| **ID** | GAP-014 |
| **Title** | PSU input power status bits (D[2]/D[6] of register 0x10) not read |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.7.2, page 54 -- Register 0x10 D[2] (PSU-1 Input OK) and D[6] (PSU-2 Input OK) |
| **Hardware** | SYSCPLD register 0x10 bits 2 and 6, I2C 1-0032 |
| **Current State** | Only D[1]/D[5] (output power OK) are read. D[2]/D[6] (input power OK) are discarded. |
| **Gap** | D[2] = 0 means PSU-1 input power is bad, D[2] = 1 means OK. Same for D[6]/PSU-2. These bits detect input-side problems (brownout, phase loss, bad AC feed) before output capacitors drain and output fails. |
| **Impact** | Input power problems not detected until output fails. Loses seconds to minutes of early warning on AC feed issues -- critical in dual-PSU redundancy monitoring. |
| **Remediation** | (1) Add `#define PSU1_INPUT_OK_BIT 2` and `#define PSU2_INPUT_OK_BIT 6`. (2) Add sysfs attributes `psu1_input_ok` and `psu2_input_ok`. (3) Surface in `psu.py` or existing power-good logic. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-015: Fan heartbeat / HEART_ATTACK coordination

| Field | Detail |
|-------|--------|
| **ID** | GAP-015 |
| **Title** | CPLD fan heartbeat / HEART_ATTACK_EN interaction undocumented and untested |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.9, page 87 (fan heartbeat); Section 7.7.13, page 64 -- Register 0x2E[7] HEART_ATTACK_EN |
| **Hardware** | SYSCPLD register 0x2E bit 7; fan CPLD heartbeat signal |
| **Current State** | SONiC thermalctld implements its own fan-failure policy (ramp to 100%, shutdown after timeout). The CPLD has an independent hardware protection mechanism: if all 5 fan trays fail or are removed, the fan CPLD heartbeat to SYSCPLD stops, and if 0x2E[7] HEART_ATTACK_EN is set, SYSCPLD shuts down main power. The interaction between these two systems is undocumented and untested. |
| **Gap** | Unknown default state of 0x2E[7] on boot. Unknown behavior when thermalctld and CPLD protection disagree (e.g., thermalctld wants to keep running at 100% while CPLD wants to shut down). Unknown restart behavior after HEART_ATTACK power-off. |
| **Impact** | Potential conflict between software and hardware thermal protection. Worst case: CPLD kills power while thermalctld still has headroom, or thermalctld keeps system running past CPLD's intended shutdown threshold. |
| **Remediation** | (1) Read 0x2E[7] on live hardware to determine boot default. (2) Test with all fans removed: does power shut off? How quickly? (3) Document the interaction in platform guide. (4) Decide policy: disable CPLD shutdown (rely on thermalctld, set 0x2E[7]=0) or leave both active with documented precedence. (5) If leaving active, ensure thermalctld shutdown timeout is shorter than CPLD timeout. |
| **Effort** | M |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-016: PSU model and serial unreadable

| Field | Detail |
|-------|--------|
| **ID** | GAP-016 |
| **Title** | PSU PMBus block-read not implemented; model and serial return "N/A" |
| **Priority** | P1 |
| **OCP Spec Ref** | PMBus standard -- MFR_MODEL (cmd 0x9A), MFR_SERIAL (cmd 0x9E), MFR_ID (cmd 0x99) |
| **Hardware** | PSU PMBus MCU at addresses 0x59 (PSU1) and 0x5A (PSU2) behind BMC I2C bus |
| **Current State** | `wedge100s-bmc-daemon.c` implements byte and word I2C reads via BMC REST API. PMBus block-read (variable-length string) is not implemented. `psu.py` `get_model()` returns `"N/A"` with comment: "PMBus block-read not implemented." `get_serial()` same. |
| **Gap** | PMBus MFR_MODEL (0x9A) and MFR_SERIAL (0x9E) are block-read commands returning a length byte followed by an ASCII string. The BMC I2C interface supports this but the daemon doesn't implement the protocol. |
| **Impact** | `show platform psustatus` shows incomplete data. Asset management, inventory tracking, RMA workflows, and spare matching all require PSU model and serial. |
| **Remediation** | (1) Add SMBus block-read support to bmc-daemon: send PMBus command byte, read length+data response. (2) Handle variable-length response (typically 10-20 bytes). (3) Write parsed ASCII to `/run/wedge100s/psu_N_model` and `/run/wedge100s/psu_N_serial`. (4) Update `psu.py` to read these files. (5) Test with actual PSU hardware -- response format is vendor-specific. |
| **Effort** | M |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-017: CP2112 I2C bus recovery incomplete

| Field | Detail |
|-------|--------|
| **ID** | GAP-017 |
| **Title** | Bus recovery uses USB reset instead of CPLD flush mechanism |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.6.2, pages 48-49 -- (1) CPLD register 0x38[7] I2C flush (sends 9 SCL clocks), (2) Registers 0x2C/0x2D bit-bang (BMC takes over SCL/SDA lines) |
| **Hardware** | SYSCPLD register 0x38 bit 7 (SCL flush); registers 0x2C/0x2D (bit-bang control) |
| **Current State** | `wedge100s-bus-reset.sh` exists and performs a USB device reset of the CP2112, which is effective but maximally disruptive -- it resets the entire USB-HID bridge, requiring re-enumeration and daemon restart. |
| **Gap** | The OCP spec provides two less-disruptive recovery mechanisms: (1) Writing 0x38[7]=1 causes the CPLD to send 9 SCL clock pulses, which releases any slave holding SDA low (standard I2C bus recovery). (2) Registers 0x2C/0x2D allow the BMC to bit-bang SCL/SDA directly for fine-grained control. Neither is implemented. |
| **Impact** | Bus lockups from stuck QSFP modules (common with certain optics) require a full USB reset, which is more disruptive than a targeted SCL flush. The 9-clock recovery would take milliseconds vs seconds for USB re-enumeration. |
| **Remediation** | (1) Add CPLD 0x38[7] flush as first-try recovery in i2c-daemon error path. (2) Implement via bmc-daemon (0x38 is on BMC I2C path, not host path). (3) Sequence: detect stuck bus -> request CPLD flush via bmc-daemon -> retry transaction -> if still stuck, fall back to USB reset. (4) Log recovery attempts for diagnostics. |
| **Effort** | M |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-018: Interrupt-driven QSFP events not implemented

| Field | Detail |
|-------|--------|
| **ID** | GAP-018 |
| **Title** | PCA9535 interrupt lines unused; presence detection is poll-only |
| **Priority** | P1 |
| **OCP Spec Ref** | Section 7.6, Table 12, pages 44-45 -- PCA9535 INT lines through PCA9548 #5 channels 4-5 to CPLD interrupt registers 0x13/0x14 |
| **Hardware** | PCA9535 /INT outputs -> PCA9548 mux -> CPLD registers 0x13 (per-expander INT) and 0x14 (global INT, D[3] PCA9535_ALL_INT_N) |
| **Current State** | `wedge100s-i2c-daemon.c` polls presence every 3 seconds via timer. No interrupt handling. The daemon header comment documents this as the design choice. |
| **Gap** | The hardware provides interrupt aggregation through the CPLD, but the CP2112 USB-HID bridge cannot deliver interrupts to the host -- it has no GPIO or interrupt pin connected to the host. This is an architectural limitation of the CP2112, not a software oversight. |
| **Impact** | 3-second worst-case detection latency for hot-swap events. In a production fabric, this means up to 3 seconds of traffic blackholing to a newly-inserted or removed port before xcvrd notices the change. |
| **Remediation** | (1) Document this as an architectural limitation in the platform guide. (2) Reduce poll interval to 1 second for presence-only reads -- these are lightweight 4-byte PCA9535 reads, well within the CP2112 bandwidth budget. (3) The CPLD interrupt registers (0x13/0x14) could theoretically be polled via BMC as a secondary check, but this adds complexity for marginal gain. |
| **Effort** | S (documentation + poll interval tuning) |
| **Topic Branch** | `wedge100s/sfp-optics` |

---

## P2 -- Feature-Completeness

### GAP-020: ROV (Regulator Output Voltage) not exposed

| Field | Detail |
|-------|--------|
| **ID** | GAP-020 |
| **Title** | Tomahawk ROV / core voltage register not read |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 7.7.6, page 52 -- Register 0x0B |
| **Hardware** | SYSCPLD register 0x0B at I2C 1-0032 |
| **Current State** | Not defined in `wedge100s_cpld.c`. Not read. |
| **Gap** | Register 0x0B contains: D[3:0] TH_ROV (Tomahawk requested operating voltage, 0.825V to 1.200V in 25mV steps) and D[6:4] VCORE_IDSEL (IR3581 voltage regulator VID setting). This reveals what voltage the Tomahawk silicon has requested based on its process corner (speed binning). |
| **Impact** | No visibility into Tomahawk core voltage. Useful for power profiling, thermal correlation, and diagnosing silicon that runs hotter due to higher voltage bin. |
| **Remediation** | (1) Add `#define REG_ROV 0x0B` to `wedge100s_cpld.c`. (2) Add sysfs attributes `th_rov` (raw 4-bit value) and `vcore_voltage_mv` (decoded millivolts). (3) Optionally expose as a SONiC Thermal or Component attribute. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-021: Power sequencer telemetry absent

| Field | Detail |
|-------|--------|
| **ID** | GAP-021 |
| **Title** | PWR1014A power sequencer not accessed |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 7.14, page 95 -- PWR1014A at BMC_I2C_3, address 0x3A |
| **Hardware** | PWR1014A power sequencer on BMC I2C bus 3 |
| **Current State** | Not accessed by bmc-daemon. No code references this device. |
| **Gap** | The PWR1014A monitors 10 voltage rails and performs voltage measurement via I2C. It can report actual measured voltage on: 3.3V standby, 3.3V main, 1.8V, 1.25V, 1.0V_ROV (Tomahawk core), 1.0V_A (analog), and other standby rails. |
| **Impact** | No per-rail voltage health monitoring. Cannot detect voltage droop, regulator degradation, or marginal power delivery issues. |
| **Remediation** | (1) Research PWR1014A I2C register map (TI datasheet). (2) Add voltage read commands to bmc-daemon. (3) Write per-rail voltage to `/run/wedge100s/vrail_<name>_mv`. (4) Surface as platform sensor or Component attributes. |
| **Effort** | L |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-022: Voltage regulator telemetry absent

| Field | Detail |
|-------|--------|
| **ID** | GAP-022 |
| **Title** | IR3581/IR3584 VRM telemetry not accessed |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 7.12, page 94 -- IR3581 at 0x10, IR3584 at 0x12 and 0x14, all on BMC_I2C_2 |
| **Hardware** | IR3581 (Tomahawk core VRM), two IR3584 (analog and 3.3V VRMs) on BMC I2C bus 2 |
| **Current State** | Not accessed by bmc-daemon. No code references these devices. |
| **Gap** | These VRMs support PMBus-compatible telemetry: per-phase output current, output voltage, input voltage, and die temperature. The IR3581 drives the Tomahawk core (highest power rail, ~100A). |
| **Impact** | Cannot measure Tomahawk power consumption (voltage x current). Cannot detect per-phase current imbalance indicating VRM degradation. No VRM temperature monitoring independent of CPLD HOT bits. |
| **Remediation** | (1) Obtain IR3581/IR3584 PMBus register maps from Infineon datasheets. (2) Add PMBus read commands to bmc-daemon for: READ_VOUT (0x8B), READ_IOUT (0x8C), READ_TEMPERATURE_1 (0x8D). (3) Write to `/run/wedge100s/vrm_<name>_*`. (4) Surface as platform sensors. |
| **Effort** | L |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-023: TPM not utilized

| Field | Detail |
|-------|--------|
| **ID** | GAP-023 |
| **Title** | SLB9645 TPM unused |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 9.2, Table 11 -- SLB9645 on BMC_I2C_10 |
| **Hardware** | Infineon SLB9645 TPM 1.2, BMC I2C bus 10 |
| **Current State** | Completely unused. No kernel driver loaded on COM-e side. No SONiC integration. |
| **Gap** | TPM provides hardware secure boot, remote attestation, and key storage capabilities. SONiC 202511 has optional TPM support in the security framework. |
| **Impact** | No hardware root of trust. Boot integrity is software-only. Remote attestation not possible. |
| **Remediation** | (1) Verify TPM is accessible from COM-e (may be BMC-only path). (2) Load `tpm_i2c_infineon` kernel module. (3) Test with `tpm2-tools`. (4) Integrate with SONiC secure boot chain if applicable. Note: TPM 1.2 (SLB9645) is legacy; SONiC may require TPM 2.0 for full integration. |
| **Effort** | L |
| **Topic Branch** | `wedge100s/security` (new branch) |

### GAP-024: Tomahawk Eagle Core 10G port unused

| Field | Detail |
|-------|--------|
| **ID** | GAP-024 |
| **Title** | BCM5387 management switch / Eagle Core SGMII port not configured |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 7.5, page 40 -- BCM5387 P1 connected to Tomahawk via SGMII, "wired and reserved for future" |
| **Hardware** | BCM5387 Memory Management Unit port 1, SGMII to Tomahawk Eagle Core 10G management port |
| **Current State** | Not configured in BCM config file. Not visible as a Linux network interface. |
| **Gap** | The Eagle Core port could provide an in-band management path or direct BMC-to-ASIC communication channel, separate from the front-panel data ports. |
| **Impact** | Missed opportunity for in-band management redundancy. All management traffic must use the dedicated 1GbE management port or front-panel ports. |
| **Remediation** | (1) Add Eagle Core port configuration to BCM config (management port entry). (2) Verify SGMII link with BCM diag shell. (3) Add Linux network interface for management routing. (4) Significant testing required -- this port has never been validated on wedge100s. |
| **Effort** | L |
| **Topic Branch** | `wedge100s/chipset-config` |

### GAP-025: COM-e status register not read

| Field | Detail |
|-------|--------|
| **ID** | GAP-025 |
| **Title** | CPLD COM-e status register 0x18 not read |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 7.7.4, page 57 -- Register 0x18 |
| **Hardware** | SYSCPLD register 0x18 at I2C 1-0032 |
| **Current State** | Not defined in `wedge100s_cpld.c`. Not read. |
| **Gap** | Register 0x18 contains: D[2:0] B_COM_TYPE (board type: 00=wedge100, 01=6-pack line card, 10=6-pack fabric card), D[3] COM_GBE0_LINK1000_N (1GbE management link status), D[4] COM_SUS_STAT_N, D[5] COM_SUS_S3_N, D[6] COM_SUS_S4_N, D[7] COM_SUS_S5_N (ACPI suspend states). |
| **Impact** | Cannot programmatically confirm board type (wedge100 TOR vs 6-pack cards). Cannot monitor management link status via CPLD. Suspend state bits are informational for debug. |
| **Remediation** | (1) Add `#define REG_COM_STATUS 0x18` to `wedge100s_cpld.c`. (2) Add sysfs attributes `board_type`, `mgmt_link`. (3) Use `board_type` in `Component.get_description()` for hardware identification. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-026: QSFP per-port hardware reset not accessible

| Field | Detail |
|-------|--------|
| **ID** | GAP-026 |
| **Title** | QSFP hardware reset lines not controllable from SONiC |
| **Priority** | P2 |
| **OCP Spec Ref** | Figure 33, page 97 -- SYSCPLD controls QSFP_RST_N[1:32] |
| **Hardware** | SYSCPLD QSFP reset register(s), accessible via BMC I2C path |
| **Current State** | `sfp.py` `reset()` returns `False`. Only LP_MODE is controllable from the host side (via PCA9535 at 0x20/0x21). The QSFP_RST_N lines are driven by the CPLD and are only accessible from the BMC I2C bus. |
| **Gap** | Cannot hardware-reset a misbehaving optics module without a full I2C bus reset. Module-level reset is a standard SONiC platform API expectation. |
| **Impact** | Misbehaving optics (stuck in boot, I2C lockup, firmware hang) require full bus reset affecting all 32 ports, instead of targeted single-port reset. |
| **Remediation** | (1) Identify the CPLD register(s) controlling QSFP_RST_N[1:32] (likely 4 bytes for 32 ports). (2) Add reset command to bmc-daemon protocol. (3) i2c-daemon submits reset request via `/run/wedge100s/` command interface. (4) bmc-daemon writes CPLD reset register via BMC I2C, waits for de-assert, re-reads presence. (5) `sfp.py` `reset()` writes command file and polls for completion. |
| **Effort** | M |
| **Topic Branch** | `wedge100s/sfp-optics` |

### GAP-027: Autoneg (CL73) disabled at ASIC level

| Field | Detail |
|-------|--------|
| **ID** | GAP-027 |
| **Title** | CL73 autonegotiation globally disabled |
| **Priority** | P2 |
| **OCP Spec Ref** | IEEE 802.3 Clause 73; BCM SDK configuration |
| **Hardware** | BCM56960 (Tomahawk) SerDes, all 32 QSFP ports |
| **Current State** | `th-wedge100s-32x-flex.config.bcm` contains `phy_an_c73=0x0`, globally disabling CL73 autonegotiation. All ports operate at fixed speed only. |
| **Gap** | Some peer devices (certain Arista, Cisco, Juniper configurations) require or strongly prefer CL73 negotiation. No per-port override mechanism exists. |
| **Impact** | Link failures with autoneg-requiring peers. Documented as a known limitation in BEWARE_OPTICS.md. Workaround: configure peer to disable autoneg. |
| **Remediation** | (1) Test per-port CL73 enable via BCM diag shell on lab hardware. (2) Verify stability with common optics (CWDM4, SR4, LR4, DAC). (3) If stable, add per-port autoneg enable/disable support via BCM config or runtime SAI attribute. (4) Significant interop testing matrix required. |
| **Effort** | L |
| **Topic Branch** | `wedge100s/chipset-config` |

### GAP-028: Port LED pipeline incomplete for breakout modes

| Field | Detail |
|-------|--------|
| **ID** | GAP-028 |
| **Title** | LED breakout-mode lane-level status not fully working |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 7.11, pages 87-93 -- 12-bit per-port LED stream format |
| **Hardware** | BCM56960 LED microcontroller, CPLD LED shift register chain |
| **Current State** | `led_proc_init.soc` programs the Tomahawk LED microcontroller. `wedge100s-ledup-linkstate` updates per-port link status. Native 100G and 4x25G breakout modes work. 2x50G and mixed breakout modes do not correctly show per-lane color differentiation. |
| **Gap** | The OCP spec defines a 12-bit per-port LED data format that encodes per-lane link state for breakout-aware display. The current LED processor code does not fully implement lane-level encoding for all breakout combinations. |
| **Impact** | LEDs do not accurately reflect per-lane status in 2x50G breakout mode. Operators cannot visually identify which lanes are up/down in a breakout group. |
| **Remediation** | (1) Complete `led_proc_init.soc` to emit correct 12-bit stream for each breakout mode (1x100G, 2x50G, 4x25G, 4x10G). (2) Update ledup daemon to track per-lane link state from SAI port status. (3) Test each breakout mode on hardware with partial link-up scenarios. |
| **Effort** | L |
| **Topic Branch** | `wedge100s/led-pipeline` |

### GAP-029: CPLD interrupt masking unused

| Field | Detail |
|-------|--------|
| **ID** | GAP-029 |
| **Title** | CPLD interrupt mask registers at defaults |
| **Priority** | P2 |
| **OCP Spec Ref** | Sections 7.7.2-7.7.7 -- Registers 0x20-0x25 (interrupt masks) |
| **Hardware** | SYSCPLD registers 0x20-0x25 at I2C 1-0032 |
| **Current State** | All interrupt mask registers are at their power-on default values. No interrupt handler is registered. The masks are irrelevant because GAP-018 documents that the CP2112 cannot deliver interrupts to the host. |
| **Gap** | The full interrupt masking infrastructure (per-event masks for PSU, power, PCA9535, and global interrupts) is unused. These could be useful if a future board revision adds an interrupt path from CPLD to COM-e. |
| **Impact** | No functional impact. This is unused hardware capability. |
| **Remediation** | Document available masking registers for future reference. No code changes needed unless interrupt delivery path is added. |
| **Effort** | S (documentation only) |
| **Topic Branch** | `wedge100s/docs` |

### GAP-030: Board revision not read

| Field | Detail |
|-------|--------|
| **ID** | GAP-030 |
| **Title** | CPLD board revision / model ID register 0x00 not fully parsed |
| **Priority** | P2 |
| **OCP Spec Ref** | Section 7.7.1, page 50 -- Register 0x00 |
| **Hardware** | SYSCPLD register 0x00 at I2C 1-0032 |
| **Current State** | `wedge100s_cpld.c` reads register 0x00 as `REG_VERSION_MAJOR` and displays it as the CPLD version major number. However, per the OCP spec, 0x00 contains: D[3:0] BRD_REV (board hardware revision) and D[5:4] MODEL_ID (00=wedge100, 01=6-pack LC, 10=6-pack FC). The CPLD version is actually at 0x01 only (minor), with 0x00 serving double duty. |
| **Gap** | The current code treats 0x00 as "version major" but it actually contains board revision and model ID. The `show_cpld_version` function displays `0x00.0x01` as "major.minor" which is misleading if 0x00 upper bits carry MODEL_ID. |
| **Impact** | Cannot distinguish hardware revisions. Cannot programmatically confirm MODEL_ID=00 (wedge100 TOR mode). CPLD version display may be incorrect if MODEL_ID bits are non-zero. |
| **Remediation** | (1) Verify on hardware: read 0x00, check if upper bits match MODEL_ID encoding. (2) If confirmed, split: `board_rev` = 0x00[3:0], `model_id` = 0x00[5:4], `cpld_version` = 0x01 only. (3) Add sysfs attributes `board_rev` and `model_id`. (4) Fix `cpld_version` display. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

---

## P3 -- Nice-to-Have

### GAP-040: RackMon interface not integrated

| Field | Detail |
|-------|--------|
| **ID** | GAP-040 |
| **Title** | RS-485 RackMon / Open Rack V2 monitoring not implemented |
| **Priority** | P3 |
| **OCP Spec Ref** | Section 8, pages 98-100 -- 3x RS-485 RJ45 for Open Rack V2, JayBox GPIO, fan LEDs |
| **Hardware** | RS-485 transceivers, RJ45 connectors, JayBox GPIO on BMC |
| **Current State** | Not used. This is an OCP rack-specific feature for Open Rack V2 deployments with rack-level PSU and fan monitoring via RS-485 bus. |
| **Gap** | No rack-level PSU/fan status aggregation. |
| **Impact** | Only relevant in Open Rack V2 deployments. No impact for standalone or standard-rack installations. |
| **Remediation** | Only implement if deploying in OCP Open Rack V2 with centralized rack management. Requires RS-485 driver, RackMon protocol implementation, and integration with rack controller. |
| **Effort** | L |
| **Topic Branch** | N/A (only if OCP rack deployment needed) |

### GAP-041: UART MUX control not exposed

| Field | Detail |
|-------|--------|
| **ID** | GAP-041 |
| **Title** | Console UART routing not software-controllable |
| **Priority** | P3 |
| **OCP Spec Ref** | Section 7.7.8, page 61 -- Register 0x26 |
| **Hardware** | SYSCPLD register 0x26 at I2C 1-0032 |
| **Current State** | Not controllable from SONiC. UART routing is set by BMC GPIO at boot time. Default routes COM-e console to rear RJ45. |
| **Gap** | Register 0x26 allows software selection of console routing: COM-e to BMC UART-1, COM-e to FB Debug header, rear debug to Tomahawk UART 0/1/2/3. The Tomahawk UART channels are useful for BCM diag shell access. |
| **Impact** | Cannot redirect console to Tomahawk debug UART from software. Field debugging requires physical access to change UART routing. |
| **Remediation** | (1) Add `#define REG_UART_MUX 0x26` to `wedge100s_cpld.c`. (2) Add sysfs attribute `uart_mux` (R/W). (3) Document available routing options. Useful for field debugging only. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-042: Dual-boot and flash write-protect not managed

| Field | Detail |
|-------|--------|
| **ID** | GAP-042 |
| **Title** | BIOS dual-boot and flash write-protect not managed |
| **Priority** | P3 |
| **OCP Spec Ref** | Section 7.7.14, page 64 -- Register 0x2F |
| **Hardware** | SYSCPLD register 0x2F at I2C 1-0032 |
| **Current State** | Not managed. BIOS flash protection left at power-on defaults. |
| **Gap** | Register 0x2F provides: D[0] DUAL_BOOT_EN (enable dual BIOS boot), D[1] EN_2ND_Flash_WP (write-protect secondary BIOS flash), D[2] Force_2nd_WR (force write to secondary flash). These enable BIOS recovery and corruption protection. |
| **Impact** | No software-controlled BIOS recovery mechanism. No write protection for backup BIOS image. Low risk in practice -- BIOS corruption is rare. |
| **Remediation** | (1) Document available controls in platform guide. (2) Implement if BIOS corruption becomes a concern in the field. (3) If implementing: add sysfs attributes, verify dual-boot behavior on hardware before enabling. |
| **Effort** | S |
| **Topic Branch** | `wedge100s/docs` |

### GAP-043: PSU EEPROM inventory not read

| Field | Detail |
|-------|--------|
| **ID** | GAP-043 |
| **Title** | PSU AT24C02 EEPROM not read |
| **Priority** | P3 |
| **OCP Spec Ref** | Table 11, pages 43-44 -- AT24C02 at 0x51 (PSU1) and 0x52 (PSU2) behind PCA9548 on BMC_I2C_8 |
| **Hardware** | AT24C02 EEPROM on PSU modules, BMC I2C bus 8 |
| **Current State** | Not read. bmc-daemon only accesses PSU PMBus MCU addresses (0x59/0x5A). |
| **Gap** | PSU EEPROMs may contain manufacturing data, lot codes, or calibration information separate from the PMBus MCU. Content format is vendor-specific. |
| **Impact** | Missing PSU manufacturing data for inventory. Partially overlaps with GAP-016 (PMBus model/serial). If GAP-016 is implemented, the PMBus data may be sufficient and EEPROM reads unnecessary. |
| **Remediation** | (1) Read EEPROM contents on hardware to determine if useful data exists. (2) If vendor-specific format is documented, parse and expose. (3) Lower priority if GAP-016 provides sufficient PSU identification. |
| **Effort** | M |
| **Topic Branch** | `wedge100s/i2c-bmc-sysfs` |

### GAP-044: LTC4151 current sense on Open Rack pass-through card

| Field | Detail |
|-------|--------|
| **ID** | GAP-044 |
| **Title** | System-level power measurement via LTC4151 not available |
| **Priority** | P3 |
| **OCP Spec Ref** | Section 5.1.4, pages 18-19 -- LTC4151 at 0x6F on pass-through card I2C |
| **Hardware** | LTC4151 current sense amplifier on Open Rack pass-through card |
| **Current State** | Not accessed. Only relevant for Open Rack V2 SKU with pass-through card (12V bus-bar power). |
| **Gap** | LTC4151 provides total system power consumption measurement for rack-level metering. Only available on the pass-through card variant, not the standard PSU variant. |
| **Impact** | No total system power measurement at the bus-bar level. Per-PSU output wattage is available via PMBus (once GAP-016 is resolved). |
| **Remediation** | Only implement if deploying Open Rack SKU. Standard I2C current/voltage read from LTC4151 registers. |
| **Effort** | S |
| **Topic Branch** | N/A (only if Open Rack deployment) |

### GAP-045: System health monitoring config too permissive

| Field | Detail |
|-------|--------|
| **ID** | GAP-045 |
| **Title** | system_health_monitoring_config.json ignores PSU sensors that should exist |
| **Priority** | P3 |
| **OCP Spec Ref** | N/A -- SONiC platform configuration |
| **Hardware** | N/A -- software configuration |
| **Current State** | `device/accton/x86_64-accton_wedge100s_32x-r0/system_health_monitoring_config.json` ignores PSU voltage, PSU temperature, and PSU fan speed monitoring. These are ignored because the data sources do not yet exist (blocked by GAP-016, GAP-021). |
| **Gap** | The ignore list is a workaround for missing telemetry, not a permanent configuration. When PSU telemetry gaps are closed, these entries should be removed. |
| **Impact** | Health dashboard shows incomplete picture. Suppresses legitimate monitoring that should exist once data sources are available. |
| **Remediation** | After GAP-016 (PSU model/serial) and GAP-021 (power sequencer) are implemented, remove the corresponding ignore entries from the config file and verify health monitoring reports PSU data correctly. |
| **Effort** | S (after prerequisite gaps resolved) |
| **Topic Branch** | `wedge100s/device-identity` |

---

## CPLD Register Cross-Reference Matrix

SYSCPLD at I2C address 0x32 on host bus 1. Register map from OCP spec sections
7.7.1 through 7.7.14 plus LED control registers.

| Addr | Register Name (OCP Spec) | R/W | Read by SONiC? | Written by SONiC? | Owning Module | Gap ID |
|------|--------------------------|-----|-----------------|---------------------|---------------|--------|
| 0x00 | Board Revision / Model ID | R | Yes (as version major) | No | wedge100s_cpld.ko | GAP-030 |
| 0x01 | CPLD Version (minor) | R | Yes | No | wedge100s_cpld.ko | -- |
| 0x02 | Reserved | -- | No | No | none | -- |
| 0x03 | Reserved | -- | No | No | none | -- |
| 0x04 | Reserved | -- | No | No | none | -- |
| 0x05 | Reserved | -- | No | No | none | -- |
| 0x06 | Reserved | -- | No | No | none | -- |
| 0x07 | Reserved | -- | No | No | none | -- |
| 0x08 | Reserved | -- | No | No | none | -- |
| 0x09 | Reserved | -- | No | No | none | -- |
| 0x0A | Reserved | -- | No | No | none | -- |
| 0x0B | ROV / VCORE_IDSEL | R | No | No | none | GAP-020 |
| 0x0C | Reserved | -- | No | No | none | -- |
| 0x0D | Reset Reason | R/C | No | No | none | GAP-010 |
| 0x0E | Reset Source 1 | R/C | No | No | none | GAP-010 |
| 0x0F | Reset Source 2 | R/C | No | No | none | GAP-010 |
| 0x10 | PSU Status | R | Partial (4/8 bits) | No | wedge100s_cpld.ko | GAP-002, GAP-013, GAP-014 |
| 0x11 | Power Status 1 (Standby) | R | No | No | none | GAP-012 |
| 0x12 | Power Status 2 (VRM) | R | No | No | none | GAP-012 |
| 0x13 | PCA9535 Interrupt Status | R | No | No | none | GAP-018 |
| 0x14 | Global Interrupt Status | R | No | No | none | GAP-018 |
| 0x15 | Reserved | -- | No | No | none | -- |
| 0x16 | Reserved | -- | No | No | none | -- |
| 0x17 | Reserved | -- | No | No | none | -- |
| 0x18 | COM-e Status | R | No | No | none | GAP-025 |
| 0x19 | Reserved | -- | No | No | none | -- |
| 0x1A | Reserved | -- | No | No | none | -- |
| 0x1B | Reserved | -- | No | No | none | -- |
| 0x1C | Reserved | -- | No | No | none | -- |
| 0x1D | Reserved | -- | No | No | none | -- |
| 0x1E | Reserved | -- | No | No | none | -- |
| 0x1F | Reserved | -- | No | No | none | -- |
| 0x20 | PSU Interrupt Mask | R/W | No | No | none | GAP-029 |
| 0x21 | Power Interrupt Mask | R/W | No | No | none | GAP-029 |
| 0x22 | PCA9535 Interrupt Mask 1 | R/W | No | No | none | GAP-029 |
| 0x23 | PCA9535 Interrupt Mask 2 | R/W | No | No | none | GAP-029 |
| 0x24 | Global Interrupt Mask | R/W | No | No | none | GAP-029 |
| 0x25 | Interrupt Mask 5 | R/W | No | No | none | GAP-029 |
| 0x26 | UART MUX Control | R/W | No | No | none | GAP-041 |
| 0x27 | Reserved | -- | No | No | none | -- |
| 0x28 | Reserved | -- | No | No | none | -- |
| 0x29 | Reserved | -- | No | No | none | -- |
| 0x2A | Reserved | -- | No | No | none | -- |
| 0x2B | Reserved | -- | No | No | none | -- |
| 0x2C | I2C Bit-Bang Control 1 | R/W | No | No | none | GAP-017 |
| 0x2D | I2C Bit-Bang Control 2 | R/W | No | No | none | GAP-017 |
| 0x2E | Fan/Thermal Control | R/W | No | No | none | GAP-015 |
| 0x2F | Dual-Boot / Flash WP | R/W | No | No | none | GAP-042 |
| 0x30 | Reserved | -- | No | No | none | -- |
| 0x31 | Reserved | -- | No | No | none | -- |
| 0x32 | Reserved | -- | No | No | none | -- |
| 0x33 | Reserved | -- | No | No | none | -- |
| 0x34 | Reserved | -- | No | No | none | -- |
| 0x35 | Reserved | -- | No | No | none | -- |
| 0x36 | Reserved | -- | No | No | none | -- |
| 0x37 | Reserved | -- | No | No | none | -- |
| 0x38 | I2C Bus Recovery | R/W | No | No | none | GAP-017 |
| 0x39 | Reserved | -- | No | No | none | -- |
| 0x3A | Reserved | -- | No | No | none | -- |
| 0x3B | Reserved | -- | No | No | none | -- |
| 0x3C | Port LED Control 1 | R/W | No | No | none | GAP-028 |
| 0x3D | Port LED Control 2 | R/W | No | No | none | GAP-028 |
| 0x3E | System LED 1 | R/W | Yes | Yes | wedge100s_cpld.ko | -- |
| 0x3F | System LED 2 | R/W | Yes | Yes | wedge100s_cpld.ko | -- |

**Summary:** Of 64 register addresses (0x00-0x3F), the current implementation accesses **5 registers** (0x00, 0x01, 0x10, 0x3E, 0x3F). Register 0x10 is only partially parsed (4 of 8 defined bits). Approximately 20 registers contain useful functionality that is not accessed.

---

## Implementation Roadmap

### Phase 1: Quick Wins (P0 + easy P1) -- Target: 1-2 days

| Gap | Work | Effort | Branch |
|-----|------|--------|--------|
| GAP-001 | Fix CPU identity in HARDWARE.md | S | `wedge100s/docs` |
| GAP-002 | Verify all 8 bits of register 0x10 on hardware | S | `wedge100s/i2c-bmc-sysfs` |
| GAP-013 | Add `psu1_alarm`, `psu2_alarm` sysfs (D[3]/D[7] of existing 0x10 read) | S | `wedge100s/i2c-bmc-sysfs` |
| GAP-014 | Add `psu1_input_ok`, `psu2_input_ok` sysfs (D[2]/D[6] of existing 0x10 read) | S | `wedge100s/i2c-bmc-sysfs` |
| GAP-012 | Add registers 0x11/0x12 reads, 7 new sysfs attributes | S | `wedge100s/i2c-bmc-sysfs` |
| GAP-030 | Add `board_rev`, `model_id` sysfs from register 0x00 | S | `wedge100s/i2c-bmc-sysfs` |

All Phase 1 CPLD work is additive to `wedge100s_cpld.c` -- new `#define`, new `show_*` functions, new `DEVICE_ATTR` entries. No existing behavior changes. Build verification: `BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb`.

### Phase 2: CPLD Register Expansion (remaining P1 CPLD) -- Target: 2-3 days

| Gap | Work | Effort | Branch |
|-----|------|--------|--------|
| GAP-010 | Reset reason registers 0x0D/0x0E/0x0F: sysfs + platform API `get_reboot_cause()` | M | `wedge100s/i2c-bmc-sysfs` |
| GAP-020 | ROV register 0x0B: sysfs + voltage decode table | S | `wedge100s/i2c-bmc-sysfs` |
| GAP-025 | COM-e status register 0x18: sysfs | S | `wedge100s/i2c-bmc-sysfs` |
| -- | Platform API integration: wire all new sysfs attributes into `component.py`, `psu.py`, `chassis.py` | M | `wedge100s/i2c-bmc-sysfs` |

### Phase 3: Daemon Enhancements (P1 daemon work) -- Target: 3-5 days

| Gap | Work | Effort | Branch |
|-----|------|--------|--------|
| GAP-011 | RXLOSS monitoring: add 0x24/0x25 to i2c-daemon, `/run/wedge100s/sfp_N_rxlos`, `sfp.py` | M | `wedge100s/sfp-optics` |
| GAP-016 | PSU block-read: add SMBus block-read to bmc-daemon, parse PMBus strings, `psu.py` | M | `wedge100s/i2c-bmc-sysfs` |
| GAP-017 | CPLD flush recovery: add 0x38[7] write to bmc-daemon, integrate into i2c-daemon error path | M | `wedge100s/i2c-bmc-sysfs` |
| GAP-018 | Reduce presence poll interval from 3s to 1s; document CP2112 interrupt limitation | S | `wedge100s/sfp-optics` |

### Phase 4: Feature Work (P2) -- Per-item, as prioritized

| Gap | Work | Effort | Branch |
|-----|------|--------|--------|
| GAP-021 | PWR1014A power sequencer telemetry | L | `wedge100s/i2c-bmc-sysfs` |
| GAP-022 | IR3581/IR3584 VRM telemetry | L | `wedge100s/i2c-bmc-sysfs` |
| GAP-026 | QSFP per-port hardware reset via bmc-daemon | M | `wedge100s/sfp-optics` |
| GAP-027 | CL73 autoneg testing and per-port config | L | `wedge100s/chipset-config` |
| GAP-028 | LED breakout-mode lane mapping | L | `wedge100s/led-pipeline` |
| GAP-024 | Eagle Core management port | L | `wedge100s/chipset-config` |
| GAP-023 | TPM integration | L | `wedge100s/security` |

### Phase 5: Validation -- Target: 1-2 days (hardware required)

| Gap | Work | Effort | Branch |
|-----|------|--------|--------|
| GAP-003 | Lane swap audit: cross-reference all 32 ports against OCP Table 10 | M | `wedge100s/chipset-config` |
| GAP-015 | Fan heartbeat testing: read 0x2E[7], test all-fans-removed scenario | M | `wedge100s/i2c-bmc-sysfs` |

---

## Appendix: Files Modified Per Gap

| Gap | Files |
|-----|-------|
| GAP-001 | `notes/HARDWARE.md`, superseded by `PLATFORM_GUIDE.md` |
| GAP-002, 012, 013, 014, 020, 025, 030 | `wedge100s_cpld.c`, `psu.py`, `component.py` |
| GAP-010 | `wedge100s_cpld.c`, `component.py` |
| GAP-011 | `wedge100s-i2c-daemon.c`, `sfp.py` |
| GAP-015 | `wedge100s_cpld.c`, docs |
| GAP-016 | `wedge100s-bmc-daemon.c`, `psu.py` |
| GAP-017 | `wedge100s-bmc-daemon.c`, `wedge100s-i2c-daemon.c` |
| GAP-018 | `wedge100s-i2c-daemon.c`, docs |
| GAP-026 | `wedge100s-bmc-daemon.c`, `wedge100s-i2c-daemon.c`, `sfp.py` |
| GAP-027 | `th-wedge100s-32x-flex.config.bcm` |
| GAP-028 | `led_proc_init.soc`, `wedge100s-ledup-linkstate` |
| GAP-045 | `system_health_monitoring_config.json` |

All source files are under `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/` in the `sonic-buildimage` fork. Device config files are under `device/accton/x86_64-accton_wedge100s_32x-r0/`.
