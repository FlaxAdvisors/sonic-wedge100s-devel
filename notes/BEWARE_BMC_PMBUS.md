# BEWARE: BMC PMBus Access on Accton Wedge 100S-32X

**Read this before probing or programming any PMBus device on the BMC I2C buses.**
Two P2 telemetry gaps (GAP-021, GAP-022) were investigated in April 2026 and both
surfaced hardware traps that can corrupt the BMC or return invalid data. Every
section below describes a trap that was already sprung.

---

## 1. Writing PMBus PAGE Register Crashes the BMC

**DO NOT** run `i2cset` (or `i2ctransfer w2`) against the PMBus PAGE register (0x00)
on any of these devices:

| Device | BMC Bus | Address | Role |
|---|---|---|---|
| IR3581 | `i2c-1` | `0x10` | Tomahawk 1.0V core VRM (6-phase) |
| IR3584 | `i2c-1` | `0x12` | 1.0V analog VRM (2-phase) |
| IR3584 | `i2c-1` | `0x14` | 3.3V main VRM (2-phase) |

**Observed behavior:** `i2cset -f -y 1 0x10 0x00 0x01` (or similar PAGE writes to the
other addresses) causes an immediate BMC reboot. Reproduced twice on 2026-04-09.
Full kernel boot sequence observed on the BMC serial console.

**Why:** Unknown. Possibly a vendor-specific telemetry-unlock protocol is required
before PAGE writes are safe, or the PAGE write triggers an internal state-machine
transition that these particular IR358x parts do not handle on this board.

**What to use instead:** The Linux kernel `pmbus` driver serializes PAGE writes
through the `hwmon` sysfs interface. If you need to read telemetry from the VRMs,
bind the generic `pmbus` driver to the i2c client (via `new_device` in sysfs) and
read `/sys/class/hwmon/hwmonN/in1_input`. Do **not** raw-write PAGE.

Even reading PAGE (`i2cget -f -y 1 0x10 0x00`) appears safe, but only reading —
never writing.

---

## 2. Silent Telemetry: Addresses ACK but Return Zeros or 0xFF

Two distinct devices on the BMC I2C tree respond to `i2cdetect` but return
garbage data on every PMBus telemetry register. Both gaps that planned to use
this telemetry (GAP-021 and GAP-022) are infeasible until a reference register
map surfaces.

### 2a. PWR1014A (UCD9090 family) at BMC `i2c-2 / 0x3A`

- ACKs on i2cdetect (shows as `UU` under the Facebook OOT `pwr1014a` driver; `3a`
  after unbinding).
- `VOUT_MODE (0x20)` = **0xFF**
- `NUM_PAGES (0xD0)` = **0xFF**
- `PMBUS_REVISION (0xFD)` = **0xFF**
- `IC_DEVICE_ID (0xFC)` = **0xFF**
- `READ_VOUT (0x8B)` = **0xFF / 0xFFFF**
- Even the driver's `mod_hard_powercycle` attribute (reads reg 0x12) returns 0xFF.

The Facebook Wedge100 design never used this chip for voltage monitoring —
only for `mod_hard_powercycle` via reg 0x12 as a board-reset lever. There is no
PMBus telemetry path on this part as shipped. No reference platform (ONL
`wedge100s-32x`, Accton AS7712) reads voltages from it.

**Bus numbering correction:** The OCP spec calls this bus "BMC_I2C_3" (1-indexed)
but the Linux kernel numbers it `i2c-2` (0-indexed). This off-by-one also
affects the plan that originally referenced it.

### 2b. IR3581 / IR3584 VRMs at BMC `i2c-1 / 0x10`, `0x12`, `0x14`

- All three addresses ACK on i2cdetect.
- `MFR_ID` = **0x20** (Infineon, correct).
- `VOUT_MODE (0x20)` = **0x22** (unusual — Linear mode with exponent `+2`).
- `READ_VOUT (0x8B)` = **0x0000** on every VRM.
- `READ_IOUT (0x8C)` = **0x0000** on every VRM.
- `READ_TEMPERATURE_1 (0x8D)` = **0x0000** on every VRM.
- `READ_VIN`, `READ_POUT`, `CAPABILITY`, `STATUS_WORD` return non-zero but
  identical/implausible values (suggestive of a register map mismatch, not real
  telemetry).

Confirmed on a **completely quiet bus** with host-side
(`wedge100s-i2c-daemon`, `wedge100s-bmc-daemon`, `pmon`) **and** BMC-side
(`fscd`, `ipmid` via `sv stop`) daemons all stopped. Binding the Linux kernel
generic `pmbus` driver to each address reports the same hard zeros on
`vout1_input`, `iout1_input`, `temp1_input`, which rules out an
i2c-tools protocol mismatch.

`PLATFORM_GUIDE.md` line 1686 already documented: *"IR3581/IR3584 voltage
readback: No; not read by bmc-daemon."* The 2026-04-09 investigation confirms
the reason — the hardware does not expose telemetry via standard PMBus
registers without an unknown enable sequence.

---

## 3. BMC I2C Bus Numbering — Off-by-One vs OCP Spec

The OCP spec uses 1-indexed bus names (`BMC_I2C_1`, `BMC_I2C_2`, `BMC_I2C_3`, ...)
while the Linux kernel on the BMC uses 0-indexed adapter numbers
(`i2c-0`, `i2c-1`, `i2c-2`, ...). Translation table as of 2026-04-09:

| OCP spec name | Linux bus | Verified devices |
|---|---|---|
| BMC_I2C_1 | `i2c-0` | (COM-e EC path — unverified) |
| BMC_I2C_2 | `i2c-1` | IR3581 0x10, IR3584 0x12, IR3584 0x14 (verified on hardware 2026-04-09) |
| BMC_I2C_3 | `i2c-2` | PWR1014A 0x3A (verified on hardware 2026-04-09) |
| BMC_I2C_10 (per PLATFORM_GUIDE §15) | actually `i2c-9` | TPM SLB96xx 0x20 (verified on hardware 2026-04-09, see notes/2026-04-09-tpm-investigation.md) |
| BMC_I2C_12 | `i2c-12` | SYSCPLD 0x31 (no +/-1 offset here — 0-indexed both sides) |
| BMC_I2C_13 | `i2c-13` | **DANGER**: no instantiated devices, but scanning it wedged a ghost slave on 2026-04-09. Do not touch. |

**`PLATFORM_GUIDE.md` bus-number entries for the TPM (§15 line 852, 1701, 1705)
and for the VRMs / power sequencer (§14) all use the OCP spec names, which
differ from kernel bus numbers.** When writing daemon code or `i2cset` commands,
translate by subtracting 1 — **except** for buses 12 and 13, where the OCP
spec and the kernel bus numbers happen to agree. Always verify with
`i2cdetect -l` on the BMC before writing any code that hardcodes a bus number.

---

## 3a. NEVER Broad-Scan an Unknown BMC Bus

**DO NOT** run `i2cdetect -y <bus>` or `i2cdump -y <bus> <addr>` on a BMC bus
unless you already know the bus contains the device you are looking for.
Broad scans can wedge ghost slaves that do not appear in `ls /sys/bus/i2c/devices/`
and that no boot-time driver touches. A wedged bus cannot be recovered by the
Linux kernel's soft recovery (`ast-i2c.N: bus hanged, try to recovery it!`
followed by `recovery timed out` loops forever), only by a chassis power cycle
or — sometimes — a BMC reboot.

**Observed incident 2026-04-09 (GAP-026 Task 3 probe):**

```bash
# DANGEROUS — DO NOT DO THIS
for bus in 10 11 12 13; do
    i2cdetect -y $bus 0x30 0x32
done
```

That loop hung `ast-i2c.13` on a slave that `ls /sys/bus/i2c/devices/` shows
no client for. The controller entered an infinite recovery loop:

```
ast-i2c ast-i2c.13: I2C(13) ast_i2c_wait_bus_not_busy slave_op=0
ast-i2c ast-i2c.13: ERROR!! I2C(13) bus hanged, try to recovery it!
ast-i2c ast-i2c.13: I2C's master is locking the bus, try to stop it.
ast-i2c ast-i2c.13: recovery timed out
```

The BMC rebooted as collateral damage (watchdog or fscd sensor timeout), and
after recovery the i2c-13 storm **persisted** in dmesg. Fan/thermal/PSU reads
on other buses continued to work after the recovery sequence in section 3b.

**Safe alternatives:**

1. **Check ground truth first.** Before any probe, list the instantiated
   clients on the target bus:
   ```bash
   ls /sys/class/i2c-adapter/i2c-<bus>/
   ```
   If nothing matches your expected device name, the slave isn't there — do
   not scan for it.
2. **Targeted `i2cget` against a known address.** Never broad-scan a range.
3. **Verify via kernel driver sysfs, not raw i2cget.** The `wedge100s_cpld`
   driver's sysfs attributes are the ground truth for CPLD registers. If a
   sysfs attribute doesn't exist, the register is not what you think it is
   — do not guess.

---

## 3b. Recovery Procedure After Accidental BMC Reboot

If the BMC reboots mid-investigation (watchdog, panic, hung bus), the
switch-side `wedge100s-bmc-daemon` will enter a restart loop with one of
these errors:

- `wedge100s-bmc-auth: command timed out` → key push via IPMI/TTY failed
- `SSH ControlMaster failed` → the IPv6 link-local `usb0` path is down

The daemon uses `root@fe80::ff:fe00:1%usb0` (IPv6 link-local via CDC-ECM
USB gadget) as `BMC_HOST`, not the 192.168.88.13 IPv4 management address.
Do not be misled by ping/ssh to .13 working — that's a different path.

**Recovery steps (verified 2026-04-09):**

```bash
# 1. Re-install the switch's public key on the rebooted BMC via the
#    still-working switch-jumped SSH path. ssh-copy-id requires sshpass
#    which SONiC does not ship — use the direct append pattern instead:
ssh admin@192.168.88.12 "cat /etc/sonic/wedge100s-bmc-key.pub | \
  sudo ssh -i /etc/sonic/wedge100s-bmc-key -o StrictHostKeyChecking=no \
    root@192.168.88.13 \
    'mkdir -p /root/.ssh && cat >> /root/.ssh/authorized_keys && \
     sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys && \
     chmod 600 /root/.ssh/authorized_keys'"

# 2. Bring usb0 back up on the switch. The BMC presents its gadget side
#    immediately on reboot (`g_cdc gadget: g_cdc ready` in BMC dmesg) but
#    the switch-side interface may be left DOWN:
ssh admin@192.168.88.12 "sudo ip link set usb0 up"

# Wait a couple of seconds, then verify:
ssh admin@192.168.88.12 "ip -br addr show usb0"
# Expect: usb0  UNKNOWN  fe80::ff:fe00:2/64
ssh admin@192.168.88.12 "ping6 -c 2 'fe80::ff:fe00:1%usb0'"

# 3. Restart the daemon (reset-failed first to clear the rate limit):
ssh admin@192.168.88.12 "sudo systemctl reset-failed wedge100s-bmc-daemon && \
                          sudo systemctl restart wedge100s-bmc-daemon"

# 4. Verify fresh reads:
ssh admin@192.168.88.12 "stat -c '%y %n' /run/wedge100s/thermal_1 \
                                          /run/wedge100s/fan_1_front"
# Expect: timestamps within the last 15 seconds
```

**CLAUDE.md already documents the key-push fix** ("After BMC reboot,
`authorized_keys` is cleared. If ping works but SSH fails, use
`sshpass -p '0penBmc' ssh-copy-id`..."), but sshpass is not installed on
SONiC, so use the direct-append pattern above instead.

**The `usb0` step is the one nobody documented.** The bmc-daemon's
"SSH ControlMaster failed" error is silent about WHY — it doesn't tell
you the interface is down. Always check `ip -br addr show usb0` first
when debugging bmc-daemon connect failures after a BMC reboot.

---

## 4. Daemon Coordination Required Before Any Probe

The CP2112 USB-HID bridge on the host side is a single shared resource, and the
BMC has its own hwmon daemons (`fscd`, `ipmid`) that periodically poll sensors.
Concurrent access corrupts PMBus transactions and mux state on both sides.

**Before any I2C bus access** (even via BMC):

```bash
# Host side
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon

# BMC side (only when you need a completely quiet bus — e.g., telemetry investigation)
ssh admin@192.168.88.12 "sudo ssh -i /etc/sonic/wedge100s-bmc-key \
  -o StrictHostKeyChecking=no root@192.168.88.13 'sv stop fscd ipmid'"
```

**After:**

```bash
# BMC side
ssh admin@192.168.88.12 "sudo ssh -i /etc/sonic/wedge100s-bmc-key \
  -o StrictHostKeyChecking=no root@192.168.88.13 'sv start fscd ipmid'"

# Host side
sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

First-pass probing with only host daemons stopped produces `ast-i2c.N: I2C's
slave is dead` events in the BMC dmesg, because BMC-side fscd is still hammering
sensors on the same bus. Always stop both sides for telemetry investigation.

---

## 5. Preferred BMC SSH Path

Direct `sshpass -p '0penBmc' ssh root@192.168.88.13` from the devel host is
unreliable (connections stall mid-output — observed during Task 7 TPM
investigation). Use the switch-jumped path instead:

```bash
ssh admin@192.168.88.12 "sudo ssh -i /etc/sonic/wedge100s-bmc-key \
  -o StrictHostKeyChecking=no root@192.168.88.13 '<command>'"
```

This reuses the SONiC switch's established BMC key authentication and is the
pattern `wedge100s-bmc-daemon.c` itself uses via its SSH ControlMaster socket.

---

## 6. Summary: What Is and Isn't Available on BMC PMBus

| Device | Readable Telemetry? | Notes |
|---|---|---|
| PSU1 PMBus (0x59 on BMC i2c-7) | **Yes** | VIN/IIN/IOUT/POUT working. MFR_MODEL/MFR_SERIAL via block-read (GAP-016 — done, commit be10000). |
| PSU2 PMBus (0x5A on BMC i2c-7) | **Yes** | Same as PSU1. |
| IR3581 core VRM (0x10 on BMC i2c-1) | **No** — returns 0x0000 | GAP-022 BLOCKED. PAGE write crashes BMC. |
| IR3584 analog VRM (0x12 on BMC i2c-1) | **No** — returns 0x0000 | GAP-022 BLOCKED. PAGE write crashes BMC. |
| IR3584 3v3 VRM (0x14 on BMC i2c-1) | **No** — returns 0x0000 | GAP-022 BLOCKED. PAGE write crashes BMC. |
| PWR1014A sequencer (0x3A on BMC i2c-2) | **No** — returns 0xFF | GAP-021 BLOCKED. Only `mod_hard_powercycle` reg 0x12 was ever used by Facebook. |
| TPM SLB96xx (0x20 on BMC i2c-9) | N/A — not PMBus, TPM 1.2 | BMC-only, not host-accessible. GAP-023 deferred. See notes/2026-04-09-tpm-investigation.md. |
| Thermal TMP75 (BMC i2c-3, i2c-8) | **Yes** | Working via bmc-daemon, `/run/wedge100s/thermal_*`. |
| Fan controller (BMC i2c-8 0x33) | **Yes** | Working via bmc-daemon, `/run/wedge100s/fan_*`. |

---

## 7. Path Forward for Power Telemetry

Neither GAP-021 (PWR1014A) nor GAP-022 (IR3581/IR3584) is fixable in software
alone on this hardware. Possible future paths:

1. **Facebook `meta-wedge100` openbmc.git reference code** — may contain an
   IR358x enable sequence or a vendor-specific unlock. Not present in any
   workspace on this build host; would need to be fetched and audited.
2. **Infineon NDA register map** — requires customer support engagement. Would
   document the correct PAGE/unlock sequence (if any).
3. **Hardware mod: INA226 shunt monitors** — add external current/voltage
   monitors on the 12V input rails to IR358x. Bypasses the IR358x telemetry
   entirely. Requires board rework.
4. **COM-e hwmon rails** (GAP-050 candidate) — the existing `com_e_driver`
   already exposes CPU Vcore, +3V, +5V, +12V, VDIMM on `hwmon6/in[0-4]_input`.
   These could be surfaced through `bmc-daemon` into `/run/wedge100s/vrail_*_mv`
   as a narrower replacement for GAP-021. Real data, zero new I2C risk. Worth
   considering as a scope-reduction for GAP-021 rather than leaving it open.

Until one of the above lands, any `show platform` power-telemetry data will be
limited to the two PSUs and thermal/fan sensors.

---

## 8. Cross-References

- `/export/sonic/sonic-wedge100s-devel/notes/2026-04-09-pwr1014a-research.md` —
  full probe transcript for GAP-021
- `/export/sonic/sonic-wedge100s-devel/notes/2026-04-09-vrm-telemetry-research.md` —
  full probe transcript for GAP-022, including the BMC-crash reproduction
- `/export/sonic/sonic-wedge100s-devel/notes/2026-04-09-tpm-investigation.md` —
  TPM investigation (GAP-023), where the bus-number off-by-one pattern was
  first observed
- `/export/sonic/sonic-wedge100s-devel/notes/PLATFORM_GUIDE.md` §14 (Power
  Distribution), §15 (Security) — contains the OCP spec bus-number names that
  need translation before kernel-side use
