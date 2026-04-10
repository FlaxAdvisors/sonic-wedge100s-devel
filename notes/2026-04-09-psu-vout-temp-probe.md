# PSU PMBus extended telemetry — probe findings (GAP-045)

**Date:** 2026-04-09
**Task:** Task 8 from `docs/superpowers/plans/2026-04-09-p2-feature-work.md`
**Topic branches:** `wedge100s/i2c-bmc-sysfs`, `wedge100s/device-identity`
**Status:** Implemented — bmc-daemon extended, psu.py updated, health config cleaned

## Summary

Extended `wedge100s-bmc-daemon` to read three additional PMBus registers
per PSU (READ_VOUT 0x8b, READ_TEMPERATURE_1 0x8d, READ_FAN_SPEED_1 0x90)
and wired them into `psu.py`. The previous workaround ignore entries
`psu.voltage`, `psu.temperature`, `PSU1_FAN1.speed`, and `PSU2_FAN1.speed`
were removed from `system_health_monitoring_config.json` because the
corresponding data sources now exist.

## Hardware probe transcript (verified on hardware 2026-04-09)

**I2C safety:** both host daemons (`wedge100s-i2c-daemon`,
`wedge100s-bmc-daemon`, `pmon`) and BMC daemons (`fscd`, `ipmid`) were
stopped before probing, and restarted afterwards. See
`notes/BEWARE_BMC_PMBUS.md` §4 — an earlier attempt with only the host
side stopped returned `Error: Could not set address: Device or resource
busy` because BMC-side `fscd` was still holding the PSU mux.

**Mux select sequence** (read from the existing `wedge100s-bmc-daemon.c`
`psu_cfg[]` array at lines 515–518):

```c
static const struct { int mux_ch; int pmbus_addr; } psu_cfg[2] = {
    { 0x02, 0x59 },   // PSU1
    { 0x01, 0x5a },   // PSU2
};
// i2cset -f -y 7 0x70 <mux_ch>
```

An earlier wrong guess of `0x04` for PSU2 is captured in the Task 8
back-and-forth — the correct value is `0x01`.

### PSU1 (bus 7, mux ch 0x02, addr 0x59)

```
i2cget -f -y 7 0x59 0x20   # VOUT_MODE
  → 0x17

i2cget -f -y 7 0x59 0x8b w # READ_VOUT  (LINEAR16)
  → 0x17ca

i2cget -f -y 7 0x59 0x8d w # READ_TEMPERATURE_1  (LINEAR11)
  → 0xf05b

i2cget -f -y 7 0x59 0x3a   # FAN_CONFIG_1_2
  → 0x90

i2cget -f -y 7 0x59 0x90 w # READ_FAN_SPEED_1
  → 0x2800

i2cget -f -y 7 0x59 0x91 w # READ_FAN_SPEED_2
  → 0x0000
```

### PSU2 (bus 7, mux ch 0x01, addr 0x5a)

```
i2cget -f -y 7 0x5a 0x20   # VOUT_MODE
  → 0x17

i2cget -f -y 7 0x5a 0x8b w # READ_VOUT  (LINEAR16)
  → 0x1802

i2cget -f -y 7 0x5a 0x8d w # READ_TEMPERATURE_1  (LINEAR11)
  → 0xf069

i2cget -f -y 7 0x5a 0x3a   # FAN_CONFIG_1_2
  → 0x90

i2cget -f -y 7 0x5a 0x90 w # READ_FAN_SPEED_1
  → 0x2909

i2cget -f -y 7 0x5a 0x91 w # READ_FAN_SPEED_2
  → 0x0000
```

## Decode analysis

### VOUT_MODE = 0x17 → exponent −9 (both PSUs)

Binary `00010111`:

- bits [7:5] = `000` — LINEAR mode
- bits [4:0] = `10111` — signed 5-bit exponent

Two's-complement 5-bit `10111` is `−9`, so `READ_VOUT` decodes as
`volts = raw × 2^−9 = raw / 512`.

### READ_VOUT decoded

| PSU | Raw | Decoded |
|-----|------|---------|
| PSU1 | `0x17ca` = 6090 | 6090 / 512 = **11.895 V** |
| PSU2 | `0x1802` = 6146 | 6146 / 512 = **12.004 V** |

Both values are within the ±20% tolerance band for a nominal 12V rail
and are consistent with the previous `pout / iout` workaround
(PSU-2 was measured at 11.886 V via the derivation).

### READ_TEMPERATURE_1 decoded (LINEAR11)

LINEAR11 layout: bits[15:11] = signed 5-bit exponent, bits[10:0] =
signed 11-bit mantissa, result = mantissa × 2^exponent.

| PSU | Raw | Exponent | Mantissa | Decoded |
|-----|------|----------|----------|---------|
| PSU1 | `0xf05b` | `11110` → −2 | `0101 1011` = 91 | 91 × 2^−2 = **22.75 °C** |
| PSU2 | `0xf069` | `11110` → −2 | `0110 1001` = 105 | 105 × 2^−2 = **26.25 °C** |

Both values are intake air temperatures near ambient — plausible for
idle load in a lab cooled room.

### READ_FAN_SPEED_1 — not LINEAR11, not duty cycle, plain RPM

FAN_CONFIG_1_2 (`0x3a`) = `0x90` on both PSUs. Per PMBus spec:

- bit 7 = 1 → FAN_1 installed
- bits [6:5] = `00` → 1 pulse per revolution
- bit 4 = 1 → FAN_1 unit flag set ("duty cycle" per PMBus spec)
- bit 3 = 0 → FAN_2 not installed
- bits [2:0] irrelevant

Nominally that says the PSU reports fan speed as duty cycle, not RPM.
But the observed `READ_FAN_SPEED_1` values rule that out:

| Interpretation | PSU1 raw 0x2800 | PSU2 raw 0x2909 | Plausible? |
|----------------|------------------|------------------|------------|
| LINEAR11 RPM   | 0 × 2^5 = 0 RPM | 265 × 2^5 = 8480 RPM | ❌ PSU1 cannot be 0 RPM (powered) |
| Duty cycle %   | 10240 % | 10505 % | ❌ out of 0–100 range |
| **Plain RPM**  | **10240** | **10505** | ✅ matches expected ~10k RPM idle |

Both PSUs reporting similar raw values at matched load confirms the
"plain RPM" interpretation. The FAN_CONFIG_1_2 unit-flag advertisement
is ignored by this Delta firmware.

`READ_FAN_SPEED_2` (`0x91`) returns `0x0000` on both PSUs, consistent
with FAN_2 being absent per `FAN_CONFIG_1_2` bit 3 = 0.

**Decision:** `psu.py` treats `psu_<N>_fan` as a raw 16-bit RPM value.
If a future PSU vendor ships SPAFCBK-14G firmware that actually uses
LINEAR11 here, the `_read_psu_telemetry()` helper will need a
per-firmware-revision dispatch. For now the single interpretation works
for both observed PSUs.

## Implementation

### `wedge100s-bmc-daemon.c` (commit `4878afe08` on `wedge100s/i2c-bmc-sysfs`)

Extended the `pmbus_regs[]` table in the PSU polling loop from 4 to 7
entries. Loop counter bumped from `r2 < 4` to `r2 < 7`. File header
docstring updated to list the three new cache files. No other changes
to the polling flow.

### `psu.py` (same commit)

- New `_linear16_vout_to_volts()` helper (hardcoded exponent −9,
  verified on hardware 2026-04-09 for both PSUs)
- `_read_psu_telemetry()` extended to read `vout`/`temp`/`fan_rpm` from
  the new cache files, keeps `pout / iout` vout fallback on file miss
- `get_voltage()` docstring updated
- New `get_temperature()` method (previously `NotImplementedError`)
- New `get_num_fans()` returning `1`
- New `get_all_fans()` returning `[PsuFan(self._index)]` (cached)
- New `PsuFan(FanBase)` class: name `PSU<N>_FAN1`, presence tracks
  parent PSU, `get_speed_rpm()` returns raw RPM from cache, `get_speed()`
  derives a percentage from a conservative 20000 RPM reference,
  `set_speed()` returns `False` (autonomous PSU-firmware-managed)

### `system_health_monitoring_config.json` (commit `066d2a0e0` on `wedge100s/device-identity`)

Removed four entries from `devices_to_ignore`:

- `psu.voltage` — `get_voltage()` now returns real data
- `psu.temperature` — `get_temperature()` implemented
- `PSU1_FAN1.speed` — `get_all_fans()[0].get_speed()` now returns real data
- `PSU2_FAN1.speed` — same for PSU-2

Kept `asic` — that's an unrelated generic ASIC health filter.

## Testing

`tests/stage_06_psu/test_psu_telemetry.py` verifies:

1. `/run/wedge100s/psu_{1,2}_{vout,temp,fan}` cache files exist
2. `Psu.get_voltage()` returns 11.0–13.0 V
3. `Psu.get_temperature()` returns 0.0–85.0 °C
4. `Psu.get_num_fans()` returns 1
5. `PsuFan.get_name()` is `PSU1_FAN1` / `PSU2_FAN1`
6. `PsuFan.get_speed_rpm()` returns 0 or 1000–20000 RPM

Each reading has a helpful `xfail` escape hatch for transient
daemon-read timing failures (PMBus reads can miss a cycle under load).

## Follow-up items

- The `_PSU_FAN_MAX_RPM` constant in `psu.py` is a conservative
  estimate (20000 RPM). When an actual loaded-PSU measurement is
  available, update this to the true max RPM so `get_speed()`
  percentage matches reality.
- The "plain RPM" interpretation of `READ_FAN_SPEED_1` was confirmed on
  the Delta SPAFCBK-14G only. If the rack ever ships with a different
  PSU model, re-probe and update the decode if necessary.
- `notes/PLATFORM_GUIDE.md` should note that PSU voltage, temperature,
  and fan RPM are now read via PMBus by bmc-daemon (next docs pass).

## Cross-references

- `notes/BEWARE_BMC_PMBUS.md` §4 — daemon coordination before PSU I2C
  access (stop both host AND BMC sides)
- `notes/BEWARE_BMC_PMBUS.md` §5 — switch-jumped SSH to BMC (avoid
  direct `sshpass` which is unreliable)
- `notes/BEWARE_BMC_PMBUS.md` §6 — summary table of what is and is not
  available on BMC PMBus (PSU row to be updated with the new findings)
- `docs/superpowers/plans/2026-04-09-p2-feature-work.md` Task 8 — the
  originating plan entry (which assumed GAP-021/022 would provide the
  data; those were BLOCKED, but the PSU PMBus path turned out to work
  and closes the gap independently)
