# Fan Heartbeat / HEART_ATTACK_EN Investigation (GAP-015)

**Date:** 2026-04-09
**Task:** Hardware Validation Plan Task 2 — static portion only
**Scope:** Read CPLD register `0x2E[7]` on live hardware, document the CPLD
hardware fan-failure shutdown mechanism and its interaction with SONiC
`thermalctld`, add a `heart_attack_en` sysfs attribute to the `wedge100s_cpld`
driver. **NOT** included: physical fan removal, policy change in
`platform-init.sh`, merge to master.

## 1. Boot-default register value (verified on hardware 2026-04-09)

Target: `hare-lorax` (192.168.88.12), CPLD at CP2112 `i2c-1` / `0x32`.
Read procedure (daemons briefly stopped, single targeted `i2cget` — no bus
scan, complies with BEWARE_BMC_PMBUS §3a):

```bash
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
sudo i2cget -y -f 1 0x32 0x2e   # -> 0x98
sudo i2cget -y -f 1 0x32 0x2d   # -> 0xc0  (context: neighbour)
sudo i2cget -y -f 1 0x32 0x2f   # -> 0xf2  (context: neighbour)
sudo i2cget -y -f 1 0x32 0x00   # -> 0x02  (sanity: CPLD ver major)
sudo i2cget -y -f 1 0x32 0x10   # -> 0xe8  (sanity: PSU status)
sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

Result: `reg 0x2E = 0x98 = 0b10011000` (verified on hardware 2026-04-09).

| Bit | Value | Meaning |
|-----|-------|---------|
| 7   | 1     | **HEART_ATTACK_EN = enabled** — CPLD hw shutdown on fan-CPLD heartbeat loss |
| 6   | 0     | unknown |
| 5   | 0     | unknown |
| 4   | 1     | unknown (set by firmware) |
| 3   | 1     | unknown (set by firmware) |
| 2   | 0     | unknown |
| 1   | 0     | unknown |
| 0   | 0     | unknown |

Bits `[6:0] = 0x18` — other fan-CPLD control state, semantics TBD. The new
`heart_attack_en` store handler does a read-modify-write so these bits are
preserved when toggling bit 7.

**Boot default on this unit: HEART_ATTACK is ENABLED.** SONiC does not
appear to clear it during platform init — there is no write to `0x2E` in
`wedge100s-platform-init.sh` or in any systemd unit we ship.

## 2. Current fan state (verified on hardware 2026-04-09)

```
fan_present = "0\n"   (via /run/wedge100s/fan_present)
fan_1_front=7350  fan_1_rear=4950
fan_2_front=7350  fan_2_rear=4950
fan_3_front=7500  fan_3_rear=4800
fan_4_front=7500  fan_4_rear=4950
fan_5_front=7350  fan_5_rear=4800
```

All 5 fan trays spinning healthy front/rear RPMs. **However `/run/wedge100s/fan_present`
reads as `"0"`, not `"0x1f"`** — this looks like a separate daemon/cache bug
(the file contains the ASCII string `"0\n"`, 2 bytes). Noted but not fixed
here — it's not in scope for GAP-015 and is almost certainly cosmetic
(e.g., the daemon never populates the bitmask because ONL parsed tray
presence differently). **Follow-up:** file a separate ticket to audit
`wedge100s-i2c-daemon.c`'s fan_present computation. The non-destructive
test in this task asserts `fan_present == 0x1f` and will (correctly) fail
today as a tripwire for that bug until it is fixed.

## 3. Interaction model: CPLD hw heartbeat vs SONiC `thermalctld`

### Hardware path
- The Wedge 100S fan module has its own small CPLD ("fan CPLD") that
  monitors tray presence and fan tachometers.
- The fan CPLD drives a dedicated heartbeat signal into the system
  SYSCPLD (the chip at `1-0032` we just probed).
- When `SYSCPLD reg 0x2E bit 7 = 1`, if the heartbeat stops (e.g. all
  fan trays are physically removed or the fan CPLD itself dies), the
  SYSCPLD will **automatically cut main power** after some timeout.
- The timeout duration is **unknown on this platform** and is not
  documented in ONL's `wedge100s-32x` or in Accton's datasheet excerpt we
  have — it needs a destructive test to measure.

### Software path (SONiC)
- `thermalctld` runs in the `pmon` container, polls every `thermal_info`
  / `fan_info` and runs a state machine.
- Default SONiC policy on fan failure: ramp all remaining fans to 100%,
  log an alarm, and after a configurable timeout (default `thermal_info
  fan_shutdown_timeout` ≈ 60 s depending on 2018 defaults) invoke a
  graceful system shutdown.
- `thermalctld` has **visibility into sensor data and operators** — it
  can log context-rich events, notify via SNMP/syslog, and shut down
  gracefully (flushing filesystems, notifying peers, etc.).
- `thermalctld` cannot stop SYSCPLD from cutting power — the CPLD
  shutdown is a pure hardware response.

### The two systems are independent and potentially conflicting
- **Double policy:** both the CPLD and `thermalctld` are allowed to
  shut down the box, using different policies and timelines.
- **Race condition risk:** if the CPLD timeout is shorter than
  `thermalctld`'s reaction time, the box dies ungracefully — no log
  flush, no peer notification, no syslog of the final event.
- **Unknown behaviour on brief maintenance removal:** if an operator
  pulls a tray for 10 seconds to reseat, does the CPLD timeout fire?
  Is there a debounce?
- **No soft-override:** once HEART_ATTACK is enabled and the heartbeat
  stops, software cannot veto the shutdown. The only escape is to
  clear bit 7 before the event.

## 4. Policy decision framework (decision deferred)

### Option A — Disable HEART_ATTACK at boot (`platform-init.sh` writes `0x2E` = `0x18`)

Pros:
- `thermalctld` is the single source of truth for fan failure response.
- Operators get graceful shutdown with full logging.
- No hidden hardware timeout to measure and engineer around.
- Matches the behaviour of most other SONiC platforms where the CPLD
  fan-shutdown is either absent or disabled.

Cons:
- If `thermalctld` is hung, crashed, or the pmon container is wedged,
  the box has no hardware backstop for fan failure. A prolonged
  `thermalctld` outage during a summer thermal event could damage the
  switch. (Mitigation: `thermalctld` watchdog + `systemd` restart
  policy in pmon.)

### Option B — Leave HEART_ATTACK enabled (boot default as observed today)

Pros:
- Defense in depth — hardware backstop if software fails.
- No change to the platform-init path, reduces commit surface.
- This is what the factory firmware chose, presumably for a reason.

Cons:
- Unknown CPLD shutdown timeout. Could be seconds, could be minutes.
  If it's shorter than `thermalctld`'s 60 s graceful window, the box
  dies before the log flushes. We don't know.
- Brief maintenance removal (single tray out for 10 s to reseat) may
  or may not trigger the shutdown. We don't know.
- `thermalctld` and the CPLD policy run independently — they will
  race on any real fan failure, and the outcome depends on whichever
  timer fires first.

### Option C — Hybrid: enable with a documented acceptance test

Leave HEART_ATTACK enabled but add a scheduled maintenance task:
1. Measure the CPLD shutdown timeout once (destructive test below).
2. Tune `thermalctld fan_shutdown_timeout` to be strictly less than the
   measured CPLD timeout, so SONiC's graceful path always wins.
3. Document the measured timeout in `docs/PLATFORM_GUIDE.md`.

### Recommendation criteria

**Cannot recommend without data.** Need:
1. CPLD shutdown timeout (seconds, measured).
2. Behaviour on brief single-tray removal (shutdown or no shutdown,
   measured).
3. Behaviour with N-1 trays removed for M minutes (shutdown or no
   shutdown, measured).

Until we have that data, **recommend Option C as the target state**
once the destructive test has been performed, and keep the current
boot default (enabled) in the meantime because it is what has been
running successfully.

## 5. Destructive test procedure (manual, future maintenance window)

**Prerequisites:**
- Physical access to all 5 fan trays
- Serial console capture active: `ssh bang-lorax tail -f screenlog.ttyUSB2.0`
- An unlimited-power-cycle budget (operator may need to reseat PSUs
  to recover from the shutdown)
- Stop the polling daemons so they don't mask sysfs/cache state:
  ```bash
  sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
  ```

**Procedure:**

1. Record starting state:
   ```bash
   sudo i2cget -y -f 1 0x32 0x2e        # expect 0x98
   # Visually confirm all 5 trays seated and spinning
   ```
2. Open serial console capture and mark a timestamp.
3. Remove fan tray 1. Record:
   - Time of removal (serial console timestamp)
   - `sudo i2cget -y -f 1 0x32 0x2e` (should be unchanged)
   - Any SYSCPLD alerts / register changes
   - Any system reaction
4. Wait 60 seconds. Observe.
5. Reinsert tray 1, verify recovery, wait 30 seconds.
6. Repeat for trays 2, 3, 4 individually.
7. Final test: remove trays 1–4 simultaneously, leaving only tray 5.
   Observe for 60 seconds.
8. **Final destructive step:** remove tray 5 (now 0 fans). Start a
   stopwatch. Record time-to-shutdown from serial console.
9. **Expected outcome:** SYSCPLD kills main power after some T seconds.
   Serial console shows the last kernel message before power is cut.
   Record T.
10. Reseat all trays, power-cycle, boot, verify the system comes back
    with register `0x2E = 0x98` (boot default restored).

**Abort conditions:** any step that produces unexpected peripheral
damage (PSU alarms, melting, smoke, noise), stop and document.

**Follow-up test with HEART_ATTACK disabled:**
After the above run, clear bit 7:
```bash
# With new sysfs attribute (requires topic branch merged + new_device bind):
echo 0 | sudo tee /sys/bus/i2c/devices/1-0032/heart_attack_en
# Verify:
cat /sys/bus/i2c/devices/1-0032/heart_attack_en   # 0
sudo i2cget -y -f 1 0x32 0x2e                     # 0x18
```
Then repeat steps 7–9 and confirm **no** hardware shutdown occurs —
only `thermalctld`'s graceful shutdown path fires.

## 6. Why physical testing was NOT done in this session

- No operator on-site to pull trays.
- The task is explicitly scoped to "static portion only" — static =
  register read + documentation + test skeleton; destructive portion
  defers to a maintenance window.
- A subagent has no physical actuators. The destructive path requires
  human intervention that cannot be automated from software.

## 7. Driver change committed on topic branch

- **File:** `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules/wedge100s_cpld.c`
- **Branch:** `wedge100s/i2c-bmc-sysfs`
- **Commit:** `e940b911e` (pushed to origin)
- **What it adds:** a new `DEVICE_ATTR(heart_attack_en, S_IRUGO | S_IWUSR, ...)`
  exposing reg `0x2E[7]` as read/write sysfs under the existing CPLD
  device. Store handler uses read-modify-write so bits `[6:0]` are
  preserved. Both functions have `@brief`/`@param`/`@return` Doxygen
  headers.
- **What it does NOT do:** change the boot default, wire up a new
  `new_device` binding for the CPLD, or mirror the attribute to
  `/run/wedge100s/`. The driver is loaded on the live switch but not
  currently bound to a device (see §8), so the attribute will only
  appear after a future commit that wires CPLD binding into
  `platform-init.sh`.

## 8. Current state of the CPLD driver binding on hare-lorax

`lsmod` shows `wedge100s_cpld` loaded, but `/sys/bus/i2c/drivers/wedge100s_cpld/`
has no bound devices. There is no `1-0032` subdirectory under
`/sys/bus/i2c/devices/`. Current ALL CPLD reads in production go through
`wedge100s-i2c-daemon` talking to CP2112 from userspace, which populates
`/run/wedge100s/` files.

This is consistent with the project history: the `wedge100s_cpld` kernel
driver is the long-term target, but the daemon-driven approach is what
ships today while the driver is being brought up. The `heart_attack_en`
sysfs attribute becomes visible the day the CPLD device is wired into
platform init (future work, not in scope here).

**Implication for the test file:** the `test_heart_attack_en_sysfs_exists`
check must `pytest.skip` rather than fail when the sysfs path doesn't
exist, because the attribute is not yet exposed on production systems.
The test is forward-compatible — once the driver is bound, the skip
goes away automatically.

## 9. Summary

- reg `0x2E = 0x98` → HEART_ATTACK_EN = 1 (enabled) on hare-lorax (verified on hardware 2026-04-09)
- All 5 fans healthy (front 7.3–7.5k RPM, rear 4.8–5.0k RPM) (verified on hardware 2026-04-09)
- `fan_present` reads `"0\n"` — separate daemon bug, logged as follow-up
- Driver loaded but unbound; sysfs access is deferred until CPLD is
  probed via `new_device` in a future commit
- Driver commit `e940b911e` adds `heart_attack_en` RW sysfs attribute
  with full doxygen, preserving other bits of reg `0x2E`
- Policy decision (keep enabled vs disable in `platform-init.sh`) is
  **deferred to a maintenance window** where the destructive test in §5
  can run and measure the CPLD shutdown timeout.
