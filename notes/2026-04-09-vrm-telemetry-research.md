# IR3581/IR3584 VRM Telemetry Research (GAP-022)

**Date:** 2026-04-09
**Task:** P2 Feature Work — Task 2 (IR3581/IR3584 VRM telemetry)
**Status:** **BLOCKED** — hardware returns zero for all telemetry registers, and writing to PAGE crashes the BMC

## Summary

The three VRMs (IR3581 at 0x10, IR3584 at 0x12, IR3584 at 0x14) are present on
the BMC I2C bus and respond to basic PMBus commands (PAGE, OPERATION, VOUT_MODE,
CAPABILITY, MFR_ID, STATUS_BYTE/WORD, READ_VIN), but:

1. **Every output-telemetry register (READ_VOUT 0x8b, READ_IOUT 0x8c,
   READ_TEMPERATURE_1 0x8d) returns 0x0000 on all three VRMs**, confirmed on a
   completely quiet I2C bus (all host + BMC i2c consumers stopped).
2. **Writing to the PAGE register (0x00) on these VRMs causes the BMC to
   reboot**, observed twice. `i2cset -f -y 1 0x10 0x00 <val>` followed by any
   subsequent read locks up the bus and triggers the BMC watchdog.

The second finding is a hard stop: we cannot safely explore vendor-specific
telemetry-unlock sequences on production hardware without risking BMC resets.

Closing GAP-022 as originally scoped is **infeasible on this hardware**.

## Bus-numbering correction

Plan says "BMC_I2C_2". Actual Linux bus number on the OpenBMC is **`i2c-1`**
(`ast_i2c.1`), not `i2c-2`. Same off-by-one as Task 1. (verified on hardware 2026-04-09)

```
BMC# i2cdetect -y 1 0x10 0x14
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
10: 10 -- 12 -- 14
```

## Clean probe (contention eliminated)

Before probing I stopped **both** host-side and BMC-side i2c consumers:

```
# host (admin@192.168.88.12)
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

# BMC (switch-jumped SSH)
sv stop fscd         # Facebook fan-sensor control daemon (was probing i2c)
sv stop ipmid        # IPMI daemon (was probing i2c)
```

Failing to stop fscd/ipmid the first time produced `ast-i2c.10: I2C's slave is
dead, try to recover it` kernel messages (bus contention). With fscd/ipmid
stopped the bus is quiet and word reads are reliable.

### Register dump, all three VRMs (clean bus)

| Reg | Name             | Type | 0x10   | 0x12   | 0x14   |
|-----|------------------|------|--------|--------|--------|
| 0x19 | CAPABILITY      | byte | 0x32   | 0x0c   | 0x17   |
| 0x20 | VOUT_MODE       | byte | 0x22   | 0x22   | 0x22   |
| 0x78 | STATUS_BYTE     | byte | 0x22   | 0x20   | 0x00   |
| 0x79 | STATUS_WORD     | word | 0x005f | 0x0067 | 0x0067 |
| 0x88 | READ_VIN        | word | 0x6700 | 0x5f00 | 0x5f08 |
| **0x8b** | **READ_VOUT**       | **word** | **0x0000** | **0x0000** | **0x0000** |
| **0x8c** | **READ_IOUT**       | **word** | **0x0000** | **0x0000** | **0x0000** |
| **0x8d** | **READ_TEMPERATURE_1** | **word** | **0x0000** | **0x0000** | **0x0000** |
| 0x96 | READ_POUT       | word | 0xff06 | 0xff06 | 0xff06 |
| 0x99 | MFR_ID          | byte | 0x20   | 0x20   | 0x20   |

(verified on hardware 2026-04-09)

**Key observations:**

- CAPABILITY, STATUS_BYTE, STATUS_WORD differ per VRM — confirming word reads
  work on the bus and each device responds individually with distinct data.
- READ_VIN returns non-zero but implausible values (0x6700 = 26,368 decimal;
  LINEAR11 exponent=00000=0, mantissa would read as -3992 with sign extension
  since bit 15 is set — clearly not a 12 V reading).
- READ_POUT returns 0xff06 on all three — LINEAR11 with exp=11111=-1 and
  mantissa=006, i.e. 6 × 2^-1 = 3 W, same on every VRM. Not meaningful.
- **Output telemetry (VOUT/IOUT/TEMP1) is hard-zero on all three VRMs**, across
  multiple read attempts, with no contention. Not a transient.
- VOUT_MODE = 0x22: mode=001 (Linear), exponent = 0b00010 = +2. Positive
  exponent on a 1.0 V rail is unusual (expected −8 to −12).

### Linux generic pmbus driver confirms

From the first probe pass (before the BMC crashed), binding the Linux kernel
`pmbus` generic driver to each VRM produced matching results:

```
# echo pmbus 0x10 > /sys/bus/i2c/devices/i2c-1/new_device
# cat /sys/bus/i2c/devices/1-0010/hwmon/hwmon12/*_input
curr1_input (iin):    -156672000
curr2_input (iout1):  0             <-- expected ~100000
in1_input   (vin):    -1048576000   <-- clearly garbage
in2_input   (vcap):   87000
in3_input   (vout1):  0             <-- should be ~1000
power2_input (pout1): -125000000
temp1_input:          0
temp2_input:          0
temp3_input:          2000          <-- 0.002 C
```

All three VRMs bound successfully but returned the same pattern: hard zeros on
vout1/iout1/temp1, and garbage on vin/iin/pout. This rules out "it's just
i2c-tools doing the wrong protocol" — the kernel driver uses textbook PMBus
and gets the same result. (verified on hardware 2026-04-09)

## BMC crash on PAGE write

When I tried to send `i2cset -f -y 1 <addr> 0x00 <page>` (to test PAGE 0 vs 1
for multi-page decoding), the BMC dropped off the network within seconds and
rebooted. Reproduced twice:

1. First attempt: tried to write PAGE=0 then PAGE=1 then PAGE=0xff on 0x10.
   BMC hung, went through full reboot cycle, came back up with 2-min uptime.
2. Second attempt: after BMC came back and I ran the clean byte/word dump
   above, I then tried to add PAGE writes — BMC rebooted again during the
   PAGE write loop.

Root cause is unclear — it could be:
- The VRM asserting SMBALERT# during a page write, which in turn trips a BMC
  watchdog via a GPIO,
- The device clock-stretching indefinitely, hanging the ast_i2c controller and
  eventually tripping its watchdog,
- A bug in the BMC's `i2cset` handling of these devices.

**Operational conclusion:** Even if READ_VOUT returning 0 on PAGE 0 could
theoretically be fixed by reading PAGE 1 or some vendor register, the write
needed to get there crashes the BMC. This makes the exploration itself unsafe
on production hardware.

## Sanity check (fails)

| Metric | Expected | Got |
|--------|----------|-----|
| READ_VOUT on core rail | ~1000 mV | 0 |
| READ_IOUT on core rail | ~30-80 A | 0 |
| READ_TEMPERATURE_1 | ~40-70 C | 0 |
| READ_VIN | ~12 V | implausible (0x6700) |

## Hypotheses

1. **OTP-disabled telemetry.** IR3581/IR3584 have vendor-specific config OTP
   that can disable telemetry reporting. Accton may have shipped these parts
   with a minimal config that supports protection/VID but not telemetry.
   Confirming would require the IR3581/IR3584 register map (Infineon NDA doc).
2. **Different silicon than assumed.** Possible rebranded or revisioned variant
   that doesn't implement the standard PMBus telemetry command block.
3. **Telemetry requires an MFR_SPECIFIC unlock sequence.** Some Infineon VRMs
   need a write to a vendor register (e.g. 0xd0-0xef range) to enable
   telemetry. Without datasheet visibility and given that writes to the
   standard PAGE register crash the BMC, probing this is too risky.
4. **Firmware issue on the VRM itself.** The IR3581 might have been configured
   with telemetry_enable=0 at manufacture.

No IR358x reference code was found in:
- `/export/sonic/OpenNetworkLinux/packages/platforms/accton/x86-64/wedge100s-32x/`
- `/export/sonic/sonic-buildimage/device/facebook/x86_64-facebook_wedge100-r0/`
- `/export/sonic/sonic-buildimage/device/accton/`

PLATFORM_GUIDE.md §14 (line 1686) already documents this gap:
`IR3581/IR3584 voltage readback: No. BMC_I2C_2; not read by bmc-daemon.`
and (line 1690): `Voltage margin tuning: No. IR3581/IR3584 support VID but not used.`
The fact that no one else reads these VRMs — neither Accton nor ONL nor
Facebook's OpenBMC fscd.py — reinforces the likelihood that telemetry was
never enabled on this board.

## Decision

Per the task's decision gate:

> **If any VRM does not respond (all 0xFF/0xFFFF for every register), STOP and
> report BLOCKED. Do not fabricate page mappings.**

The literal text ("all 0xFF/0xFFFF") doesn't fit this exact situation — the
VRMs respond at the I2C level and on several registers return distinct
non-0xFFFF data. But the **spirit** of the decision gate (don't ship fabricated
telemetry) applies: **every output-telemetry register returns 0 on every VRM**.

Additionally, **writing to the PAGE register crashes the BMC**, which means any
further exploration of page-based workarounds or vendor unlock sequences
requires mitigations we don't have (a way to reset the BMC cleanly if it hangs,
a Infineon register map under NDA, etc.).

**BLOCKED.**

Reporting `/run/wedge100s/vrm_core_vout_mv = 0` to the platform API would be
actively worse than the current state — thermal management, fan control, and
any future health-monitoring logic could misinterpret "core rail = 0 V" as a
hard fault and take destructive action (shut down, force fans full).

## What would unblock

- Infineon IR3581/IR3584 extended register map (vendor NDA doc) — lets us find
  the telemetry-enable path without blind probing.
- A reference implementation from Facebook's OpenBMC tree targeting wedge100s
  (search `meta-facebook/meta-wedge100` in openbmc.git for `sensor-util`,
  `fan-util`, `fscd` backend reads).
- Accton support request — they may have a VRM firmware update or config blob
  that re-enables telemetry.
- Alternative current/voltage measurement via an INA230/INA226 shunt monitor,
  if any are fitted on the board (check schematic section 14.7 — the PLATFORM
  guide mentions PWR1014A but not discrete INA parts).

## What was NOT changed

- **No edits to** `wedge100s-bmc-daemon.c`.
- **No new test file** committed on the devel repo.
- **No commits** on the `wedge100s/i2c-bmc-sysfs` topic branch (worktree at
  `/export/sonic/worktrees/wedge100s-i2c-bmc-sysfs/` left clean, same 27
  commits ahead of origin it had at start).
- **No changes** to `report.py`.

## Hardware safety notes

- Stopping only host-side daemons is **insufficient**. The BMC runs fscd (fan
  sensor control) and ipmid which actively probe i2c. Both must be stopped via
  `sv stop fscd; sv stop ipmid` on the BMC before any host-initiated i2c probe
  of BMC-side devices, otherwise you'll see `ast-i2c.N: I2C's slave is dead`
  events and possible bus deadlock. Restart with `sv start` after probing.
- **Do not write to PAGE (0x00) on these VRMs via i2cset.** Observed twice to
  crash the BMC. If a future investigation must touch these devices, do it via
  the Linux kernel pmbus driver (which serializes page switches correctly
  through hwmon sysfs) rather than via raw `i2cset`.
- The BMC has per-bus reset knobs at `/sys/devices/platform/ast-i2c.N/bus_master_reset`
  and `bus_slave_reset` — these are useful for clearing transient hangs but
  did not recover the BMC from the reboot caused by PAGE writes.

## Related

- Task 1 (PWR1014A, GAP-021): BLOCKED — `notes/2026-04-09-pwr1014a-research.md`
- PLATFORM_GUIDE §14 Power Distribution, lines 1580-1690.
- Two consecutive P2 tasks (Task 1 and Task 2) both BLOCKED with the same
  pattern: device responds at I2C level but telemetry returns garbage/zero.
  This suggests the hardware was never fully qualified for monitoring beyond
  what Facebook's ONL/OpenBMC originally supported, which per ONL source code
  was only presence/pgood/fan readings — never VRM or sequencer telemetry.
