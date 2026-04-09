# Platform Guide and Design Gaps Specification

**Date:** 2026-04-09
**Author:** Claude Code + db-at-work
**Status:** Approved

## Objective

Produce two authoritative documents for the Wedge 100S-32X SONiC port:

1. **`notes/PLATFORM_GUIDE.md`** — Single-source-of-truth hardware and architecture reference, replacing the combination of HARDWARE.md and ARCHITECTURE.md. Consolidates OCP spec v1.3 ground truth with implementation reality.

2. **`notes/DESIGNGAPS.md`** — Chip-by-chip, register-by-register audit of OCP spec capabilities vs. current SONiC implementation, prioritized as a future work backlog.

## Audience

Contributors working on the `FlaxAdvisors/sonic-buildimage` platform fork. Assumes familiarity with SONiC, Linux I2C, and network switch hardware.

## Approach

- OCP spec v1.3 (`misc/Wedge100S_OCP_Spec_v1_3.pdf`) as hardware ground truth
- SFF-8636 Rev 2.11 (`misc/PUBLISHED SFF-8636.pdf`) for QSFP management interface
- Current platform code in `sonic-buildimage` as implementation truth
- Hardware-verified facts from existing notes marked with verification dates
- Existing BEWARE docs and SUBSYSTEMS docs remain as companion references (not replaced)
- HARDWARE.md and ARCHITECTURE.md remain as historical artifacts (not deleted)

## Deliverable 1: PLATFORM_GUIDE.md

### Structure (15 sections)

1. **Platform Identity** — OCP spec version, SKU, HW revision, comparison to Wedge100/AS7712
2. **System Architecture** — Block diagram, dual-domain model, daemon-mediated cache
3. **Processor and Memory** — Intel Pentium D1508, COM-e module, DDR4, storage
4. **Switching ASIC** — BCM56960 Tomahawk, port mapping, lane swaps, BCM config, breakout, FEC
5. **I2C Topology** — CP2112, PCA9548 mux tree, PCA9535 GPIO expanders, bus map
6. **System CPLD** — MAX-V 5M2210ZF256, full register map with implementation status
7. **BMC Subsystem** — AST2400 OpenBMC, I2C buses, owned hardware, SSH protocol
8. **Thermal Management** — 8 sensors, threshold policy, ROV implications
9. **Fan System** — 5 trays, fan CPLD, heartbeat, speed control
10. **Power Supply** — PSU models, PMBus registers, CPLD status bits
11. **QSFP Optics** — Presence, EEPROM, LP_MODE, RESET, DOM, RXLOSS
12. **LED Subsystem** — System LEDs, port LEDs (shift register chain), Tomahawk LED uC, modes
13. **OOB Ethernet** — BCM5387, PHY allocation, Eagle Core port
14. **Power Distribution** — PWR1014A sequencer, IR3581/3584 regulators, monitored rails
15. **Security** — TPM, Intel TXT, dual BIOS, write protection

### Conventions

- Each section leads with OCP spec truth, then describes SONiC implementation
- Tables preferred over prose for register maps and device inventories
- Cross-references to SUBSYSTEMS/BEWARE docs where deeper detail exists
- Hardware-verified facts carry `(verified YYYY-MM-DD)` tags from existing notes

## Deliverable 2: DESIGNGAPS.md

### Priority Definitions

| Priority | Meaning | Criteria |
|----------|---------|----------|
| P0 | Correctness | Wrong behavior, data corruption risk, incorrect documentation |
| P1 | Production-readiness | Missing for reliable 24/7 unattended operation |
| P2 | Feature-completeness | OCP spec capability not exposed in SONiC |
| P3 | Nice-to-have | Polish, optimization, OCP-rack-specific features |

### Gap Entry Format

Each gap has: ID, title, priority, OCP spec reference, hardware involved, current state, gap description, impact, remediation path, effort estimate (S/M/L), owning topic branch.

### Preliminary Gap Inventory

**P0 (3 gaps):** CPU identity doc error, PSU register polarity verification, QSFP lane-swap validation.

**P1 (9 gaps):** Reset-reason reporting, RXLOSS monitoring, power rail health, PSU alarm/input bits, fan heartbeat coordination, PSU model/serial block-read, CP2112 bus recovery, interrupt-driven QSFP events, system health config.

**P2 (11 gaps):** ROV exposure, power sequencer telemetry, voltage regulator telemetry, TPM utilization, Eagle Core port, COM-e status, QSFP hardware reset, autoneg enablement, LED pipeline completion, interrupt masking, board revision reading.

**P3 (5 gaps):** RackMon, UART MUX, dual-boot/flash-WP, PSU EEPROM inventory, LTC4151 current sense.

### Cross-Reference Matrix

CPLD register map (0x00-0x3F) with columns: register, OCP spec section, read/written by port, owning daemon/module, gap ID.

### Implementation Roadmap

Suggested ordering by priority band, with natural groupings (e.g., CPLD register expansion as a single wedge100s_cpld.c change covering multiple P1 gaps).

## Non-Goals

- Not replacing BEWARE docs (those document specific incidents and pitfalls)
- Not replacing SUBSYSTEMS docs (those provide per-subsystem deep-dives)
- Not documenting the build system or workflow (covered by Developer's Guide and workflow.md)
- Not an operational runbook (that would be a separate deliverable)

## Execution

Write both documents directly into `notes/`. No topic branch needed — these are documentation in the devel repo, not platform fork code.
