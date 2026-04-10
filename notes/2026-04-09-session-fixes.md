# 2026-04-09 Session Fixes

## Fixes Landed (all topic-branch workflow, merged to master)

### wedge100s/build-infra
- **modules_install path**: `debian/rules` had wrong `M=` and `INSTALL_MOD_PATH` — `.ko` was built but never included in `.deb`. Fixed to match working `.claude` build env.
- **Clean targets**: Restored guards and `rm -f` for compiled C binaries, flex-counter-daemon clean.

### wedge100s/device-identity
- **initialize_system_led()**: Added method + compat alias for upstream SONiC typo `initizalize_system_led`. System-health was crashing with AttributeError on startup, preventing SYSTEM_READY=UP.
- **Postinst fixes relocated**: Cherry-picked 2 stray master commits (Docker timeouts, pmon-fixup oneshot) back onto topic branch to restore discipline.

### wedge100s/i2c-bmc-sysfs
- **i2cdump for PSU model/serial**: BMC lacks `i2ctransfer`. Switched `bmc_read_pmbus_string()` to `i2cdump -f -y <bus> <addr> s <reg>`, parse ASCII column. (verified on hardware: PSU model=SPAFCBK-14G)
- **Fan target speed**: `get_target_speed()` raised `NotImplementedError` when BMC manages speed autonomously. Now returns actual speed as target, so system-health fan checks pass.
- **pwr_status2 HOT polarity**: Register 0x12 HOT bits are active-low (1=OK, 0=hot). Corrected CPLD driver comment.

### wedge100s/flex-counters
- **Restart=always**: `wedge100s-flex-counter-daemon.service` had `Restart=on-failure` — clean stop during dpkg deploy left it dead, blocking SYSTEM_READY.

### wedge100s/submodule-patches
- **Patch 0004**: Fix `initizalize_system_led` → `initialize_system_led` in `sonic-utilities` `show/system_health.py` and test mock.

## Findings

- **CPLD kernel module packaging**: The `.ko` goes in the platform `.deb`, not the `.bin` exclusively. The `.claude` build env had this right; our fork had regressed. (verified on hardware 2026-04-09)
- **CPLD device instantiation**: Module loads but needs `echo wedge100s_cpld 0x32 > /sys/bus/i2c/devices/i2c-1/new_device` to probe. Platform-init or postinst should handle this.
- **SYSTEM_READY race**: After `system-health.service` restart, sysmonitor deletes SYSTEM_READY key. If all services are already UP, `publish_system_status` compares DOWN==DOWN (no change) and never re-posts. Workaround: restart a service to trigger a state change event.
- **BMC tool availability**: OpenBMC image has i2cget/i2cset/i2cdump/i2cdetect but NOT i2ctransfer.
- **PSU-1 "out of power"**: Real hardware state (present but unplugged). Does not block SYSTEM_READY — only services do.

## Test Fixes (sonic-wedge100s-devel)

- `tests/stage_09_cpld/test_cpld.py`: Fixed pwr_status2 bit layout (interleaved per CPLD driver) and polarity (active-low HOT).
- `tests/stage_07_qsfp/test_qsfp.py`: EEPROM tests now derive populated slots from `tools/topology.json` instead of trusting live API presence for all 32 ports.
- `tools/deploy.py`: Added `_restart_platform_services()` — restarts all wedge100s services before system-ready gate to prevent stale-stop SYSTEM_READY=DOWN.
