# PSU Model/Serial Cache Integration

**Date:** 2026-04-09  
**Task:** P2-T4: Wire PSU model/serial into psu.py  
**Branch:** `wedge100s/i2c-bmc-sysfs`  
**Commit:** `1e29444858c12b002682c125ad972cc523556c61`

## Summary

Integrated PSU model and serial number reading into the SONiC platform API (`psu.py`). These values are now dynamically read from cache files written by the `wedge100s-bmc-daemon` via PMBus block-read operations.

## Implementation Details

### File Changed
- `/export/sonic/sonic-buildimage/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/psu.py`

### Cache Constants Added
```python
_PSU_MODEL_CACHE    = '/run/wedge100s/psu_{}_model'
_PSU_SERIAL_CACHE   = '/run/wedge100s/psu_{}_serial'
```

Naming verified against bmc-daemon source (`wedge100s-bmc-daemon.c`):
- Daemon writes to `RUN_DIR "/psu_%d_%s"` where `%d = psu_index + 1` (1-based) and `%s` is suffix from `pmbus_str_regs[]`
- Model register: `0x9a` → `"model"`
- Serial register: `0x9e` → `"serial"`
- Files: `psu_1_model`, `psu_2_model`, `psu_1_serial`, `psu_2_serial`

### Methods Updated

#### `get_model(self)` 
- **Before:** Returned static string `"Delta DPS-1100AB-6 A"`
- **After:** Reads from `/run/wedge100s/psu_{N}_model`, returns `"N/A"` if file unavailable or empty
- **Docstring:** Added, references PMBus MFR_MODEL register 0x9A

#### `get_serial(self)`
- **Before:** Returned static string `'N/A'`
- **After:** Reads from `/run/wedge100s/psu_{N}_serial`, returns `"N/A"` if file unavailable or empty
- **Docstring:** Added, references PMBus MFR_SERIAL register 0x9E

### Error Handling

Both methods:
1. Format cache path using `self._index` (1-based: 1 or 2)
2. Attempt to open and read the file
3. Return the trimmed content if non-empty
4. Return `"N/A"` on any `OSError` (file not found, permission denied, etc.)
5. Return `"N/A"` if file content is empty after strip

### Graceful Degradation

Returns `"N/A"` when:
- PSU not inserted (file not created by daemon)
- BMC unreachable (SSH connection timeout)
- Early boot (daemon hasn't run yet)
- No PMBus response from PSU

## Verification

- **Syntax:** `python3 -m py_compile` — passed
- **Code review:** Follows existing cache pattern (`_PSU_ALARM_CACHE`, `_PSU_INPUT_OK_CACHE`)
- **Cache path format:** Verified against bmc-daemon C source code
- **Index handling:** Uses `self._index` (1-based) correctly for path formatting

## Dependencies

- `wedge100s-bmc-daemon` (P2-T3, already completed) must write PSU model/serial files
- Tested alongside: no direct test changes required for this commit (tests in P2-T7)

## Notes

- Cache files are written once per PSU insertion (daemon sets `psu_info_read[]` flag)
- No telemetry caching needed; model/serial are static per PSU lifetime
- Consistent with existing PSU alarm/input-OK cache pattern
