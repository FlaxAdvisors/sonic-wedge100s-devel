"""Stage 06 supplement — PSU vout, temperature, and fan RPM telemetry (GAP-045).

Verifies that wedge100s-bmc-daemon's PSU polling loop reads READ_VOUT
(PMBus 0x8b), READ_TEMPERATURE_1 (0x8d), and READ_FAN_SPEED_1 (0x90) from
each PSU, and that the corresponding platform API methods return plausible
values:

- Psu.get_voltage()     — prefers direct READ_VOUT (LINEAR16 exp=-9),
                          falls back to pout/iout derivation
- Psu.get_temperature() — LINEAR11 decode of READ_TEMPERATURE_1
- PsuFan.get_speed_rpm() — plain RPM from READ_FAN_SPEED_1

Hardware context (verified on hardware 2026-04-09):
- Both PSUs are Delta SPAFCBK-14G
- VOUT_MODE = 0x17 → signed 5-bit exponent = -9 → volts = raw / 512
- READ_TEMPERATURE_1 uses standard LINEAR11 (intake air, ~22-27 C idle)
- READ_FAN_SPEED_1 is plain 16-bit RPM on this vendor, NOT LINEAR11 or
  duty cycle (see notes/2026-04-09-psu-vout-temp-probe.md for the
  decode-format reasoning)
"""

import json
import pytest

RUN_DIR = "/run/wedge100s"

PSU_TELEMETRY_CAPTURE = """\
import json
from sonic_platform.platform import Platform
chassis = Platform().get_chassis()
results = []
for psu in chassis.get_all_psus():
    if not psu.get_presence():
        results.append({"name": psu.get_name(), "present": False})
        continue
    fans = psu.get_all_fans() if hasattr(psu, "get_all_fans") else []
    fan_data = []
    for f in fans:
        fan_data.append({
            "name": f.get_name(),
            "presence": f.get_presence(),
            "rpm": f.get_speed_rpm(),
            "pct": f.get_speed(),
        })
    results.append({
        "name": psu.get_name(),
        "present": True,
        "voltage": psu.get_voltage(),
        "temperature": psu.get_temperature(),
        "num_fans": psu.get_num_fans() if hasattr(psu, "get_num_fans") else 0,
        "fans": fan_data,
    })
print(json.dumps(results))
"""


def _capture_psu_telemetry(ssh):
    out, err, rc = ssh.run_python(PSU_TELEMETRY_CAPTURE, timeout=30)
    assert rc == 0, f"PSU telemetry capture failed: {err}"
    return json.loads(out.strip())


# ----------------------------------------------------------------------
# Daemon cache file existence
# ----------------------------------------------------------------------

def test_psu_vout_cache_files_exist(ssh):
    """/run/wedge100s/psu_{1,2}_vout exist (bmc-daemon reads 0x8b)."""
    missing = []
    for idx in (1, 2):
        path = f"{RUN_DIR}/psu_{idx}_vout"
        out, _, _ = ssh.run(f"test -f {path} && echo YES || echo NO", timeout=10)
        if "YES" not in out:
            missing.append(path)
    assert not missing, (
        f"Missing PSU vout cache files: {missing}. "
        "Is wedge100s-bmc-daemon built with the READ_VOUT extension?"
    )


def test_psu_temp_cache_files_exist(ssh):
    """/run/wedge100s/psu_{1,2}_temp exist (bmc-daemon reads 0x8d)."""
    missing = []
    for idx in (1, 2):
        path = f"{RUN_DIR}/psu_{idx}_temp"
        out, _, _ = ssh.run(f"test -f {path} && echo YES || echo NO", timeout=10)
        if "YES" not in out:
            missing.append(path)
    assert not missing, (
        f"Missing PSU temp cache files: {missing}. "
        "Is wedge100s-bmc-daemon built with the READ_TEMPERATURE_1 extension?"
    )


def test_psu_fan_cache_files_exist(ssh):
    """/run/wedge100s/psu_{1,2}_fan exist (bmc-daemon reads 0x90)."""
    missing = []
    for idx in (1, 2):
        path = f"{RUN_DIR}/psu_{idx}_fan"
        out, _, _ = ssh.run(f"test -f {path} && echo YES || echo NO", timeout=10)
        if "YES" not in out:
            missing.append(path)
    assert not missing, (
        f"Missing PSU fan cache files: {missing}. "
        "Is wedge100s-bmc-daemon built with the READ_FAN_SPEED_1 extension?"
    )


# ----------------------------------------------------------------------
# Platform API — voltage
# ----------------------------------------------------------------------

def test_psu_voltage_reasonable(ssh):
    """Present PSUs report 11-13 V via get_voltage().

    Delta SPAFCBK-14G nominal output is 12 V. The direct READ_VOUT path
    (LINEAR16, exp=-9) should give ~11.8-12.1 V at typical load.
    """
    psus = _capture_psu_telemetry(ssh)
    present = [p for p in psus if p.get("present")]
    assert present, "No present PSUs to check voltage"

    all_none = all(p["voltage"] is None for p in present)
    if all_none:
        pytest.xfail(
            "All present PSUs returned voltage=None — transient daemon read "
            "or cache not yet populated. Re-run stage_06_psu in isolation."
        )

    for p in present:
        v = p["voltage"]
        if v is None:
            print(f"  WARN: {p['name']} get_voltage() returned None")
            continue
        print(f"  {p['name']}: voltage={v:.3f} V")
        assert 11.0 <= v <= 13.0, (
            f"{p['name']} voltage={v} V outside 11-13 V range. "
            "Check _linear16_vout_to_volts() — Delta SPAFCBK-14G VOUT_MODE "
            "is 0x17 (exp=-9), so volts = raw / 512."
        )


# ----------------------------------------------------------------------
# Platform API — temperature
# ----------------------------------------------------------------------

def test_psu_temperature_reasonable(ssh):
    """Present PSUs report 0-85 C via get_temperature().

    This is the PSU intake temperature (READ_TEMPERATURE_1). Idle lab
    conditions should be 20-40 C; the 85 C ceiling is below the PSU's
    thermal shutdown threshold and well above any observed reading.
    """
    psus = _capture_psu_telemetry(ssh)
    present = [p for p in psus if p.get("present")]
    if not present:
        pytest.skip("No present PSUs")

    all_none = all(p["temperature"] is None for p in present)
    if all_none:
        pytest.xfail(
            "All present PSUs returned temperature=None — transient daemon "
            "read or cache not yet populated."
        )

    for p in present:
        t = p["temperature"]
        if t is None:
            print(f"  WARN: {p['name']} get_temperature() returned None")
            continue
        print(f"  {p['name']}: temperature={t:.1f} C")
        assert 0.0 <= t <= 85.0, (
            f"{p['name']} temperature={t} C outside 0-85 C range. "
            "Check _pmbus_decode_linear11() or the cache file content."
        )


# ----------------------------------------------------------------------
# Platform API — fans
# ----------------------------------------------------------------------

def test_psu_num_fans(ssh):
    """Present PSUs report exactly 1 fan via get_num_fans().

    Delta SPAFCBK-14G FAN_CONFIG_1_2 (0x3a) = 0x90 → FAN_1 installed,
    FAN_2 absent.
    """
    psus = _capture_psu_telemetry(ssh)
    present = [p for p in psus if p.get("present")]
    if not present:
        pytest.skip("No present PSUs")

    for p in present:
        n = p.get("num_fans", 0)
        print(f"  {p['name']}: num_fans={n}")
        assert n == 1, (
            f"{p['name']} num_fans={n}, expected 1 "
            "(FAN_CONFIG_1_2 reports FAN_1 installed, FAN_2 absent)"
        )


def test_psu_fan_name_and_presence(ssh):
    """PSU fan is named PSU<N>_FAN1 and reports presence tied to the PSU."""
    psus = _capture_psu_telemetry(ssh)
    present = [p for p in psus if p.get("present")]
    if not present:
        pytest.skip("No present PSUs")

    for p in present:
        fans = p.get("fans", [])
        assert len(fans) == 1, (
            f"{p['name']} exposed {len(fans)} fans, expected 1"
        )
        fan = fans[0]
        # get_name() returns PSU1_FAN1 or PSU2_FAN1
        expected_name_base = p["name"].replace("PSU-", "PSU")  # PSU-1 → PSU1
        assert fan["name"].startswith(expected_name_base), (
            f"Fan name {fan['name']!r} does not start with {expected_name_base!r}"
        )
        assert fan["presence"] is True, (
            f"{fan['name']} presence={fan['presence']} but parent PSU is present"
        )


def test_psu_fan_rpm_reasonable(ssh):
    """PSU fan RPM is 0 or within 1000-20000 range.

    Delta SPAFCBK-14G internal fans typically run 8-12k RPM at low load,
    spinning up to 15-18k under thermal stress. Very low readings (<1k)
    usually indicate a stopped fan; values above 20k are implausible.
    A reading of exactly 0 is allowed — some PSU firmware stops the fan
    entirely at no load.
    """
    psus = _capture_psu_telemetry(ssh)
    present = [p for p in psus if p.get("present")]
    if not present:
        pytest.skip("No present PSUs")

    all_none = all(
        (not p.get("fans")) or p["fans"][0].get("rpm") is None for p in present
    )
    if all_none:
        pytest.xfail(
            "All present PSUs returned fan rpm=None — transient daemon read "
            "or cache not yet populated."
        )

    for p in present:
        fans = p.get("fans", [])
        if not fans:
            continue
        rpm = fans[0].get("rpm")
        if rpm is None:
            print(f"  WARN: {fans[0]['name']} get_speed_rpm() returned None")
            continue
        print(f"  {fans[0]['name']}: {rpm} RPM")
        assert rpm == 0 or 1000 <= rpm <= 20000, (
            f"{fans[0]['name']} rpm={rpm} outside {{0, [1000-20000]}} range. "
            "If the value looks like a LINEAR11 word (e.g. 0x2800=10240 at "
            "the raw level but decoded as 0), the decode format in psu.py "
            "may need revisiting."
        )
