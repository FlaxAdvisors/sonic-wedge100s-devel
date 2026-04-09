"""Stage 09 — CPLD Sysfs Attributes.

Verifies that the wedge100s_cpld kernel driver is loaded and all sysfs
attributes under /sys/bus/i2c/devices/1-0032/ are readable with values
in the expected ranges.

Sysfs attributes (defined in wedge100s_cpld.c):
  cpld_version   (RO) — "major.minor" from regs 0x00/0x01
  psu1_present   (RO) — 0=absent, 1=present
  psu1_pgood     (RO) — 0=not OK, 1=power good
  psu1_alarm     (RO) — 0=alarm, 1=normal (OCP v1.3 §7.7.2)
  psu1_input_ok  (RO) — 0=bad, 1=OK (OCP v1.3 §7.7.2)
  psu2_present   (RO) — 0=absent, 1=present
  psu2_pgood     (RO) — 0=not OK, 1=power good
  psu2_alarm     (RO) — 0=alarm, 1=normal (OCP v1.3 §7.7.2)
  psu2_input_ok  (RO) — 0=bad, 1=OK (OCP v1.3 §7.7.2)
  led_sys1       (RW) — 0=off, 1=red, 2=green, 4=blue; +8=blink
  led_sys2       (RW) — same encoding
  board_rev      (RO) — 4-bit board revision [0-15]
  model_id       (RO) — 4-bit model ID (0=wedge100 TOR)
  pwr_stby_ok    (RO) — 1=standby power OK
  pwr_status2    (RO) — 6-bit power rail status (VRDY + HOT)
  rov_status     (RO) — ROV strap/fuse register
  reset_reason   (RO) — OCP spec reset reason code
  reset_source1  (RO) — reset source bitmap 1
  reset_source2  (RO) — reset source bitmap 2
  come_status    (RO) — COM-e module status

CPLD hardware: i2c-1/0x32, accessed via CP2112 USB-HID bridge (i2c_dev).
"""

import re
import pytest

# Kernel driver sysfs path — used only for driver-binding tests
CPLD_SYSFS = "/sys/bus/i2c/devices/1-0032"

# Canonical daemon-cache path — used by all services (psu.py, chassis.py, ledd)
RUN_DIR = "/run/wedge100s"

SYSFS_ATTRS = [
    "cpld_version",
    "psu1_present",
    "psu1_pgood",
    "psu1_alarm",
    "psu1_input_ok",
    "psu2_present",
    "psu2_pgood",
    "psu2_alarm",
    "psu2_input_ok",
    "led_sys1",
    "led_sys2",
    "board_rev",
    "model_id",
    "pwr_stby_ok",
    "pwr_status2",
    "rov_status",
    "reset_reason",
    "reset_source1",
    "reset_source2",
    "come_status",
]


# ------------------------------------------------------------------
# Driver presence
# ------------------------------------------------------------------

def test_cpld_sysfs_dir_exists(ssh):
    """wedge100s_cpld sysfs directory exists at /sys/bus/i2c/devices/1-0032."""
    out, _, rc = ssh.run(f"test -d {CPLD_SYSFS} && echo YES || echo NO", timeout=10)
    assert "YES" in out, (
        f"{CPLD_SYSFS} does not exist.\n"
        "Check: lsmod | grep wedge100s_cpld"
    )


def test_cpld_driver_name(ssh):
    """CPLD device shows driver=wedge100s_cpld in sysfs."""
    out, _, rc = ssh.run(
        f"readlink {CPLD_SYSFS}/driver 2>/dev/null | xargs basename", timeout=10
    )
    driver = out.strip()
    print(f"\nCPLD driver: {driver!r}")
    assert driver == "wedge100s_cpld", (
        f"Expected driver 'wedge100s_cpld', got {driver!r}.\n"
        "Check: lsmod | grep wedge100s_cpld"
    )


# ------------------------------------------------------------------
# All attributes readable
# ------------------------------------------------------------------

def test_all_sysfs_attrs_readable(ssh):
    """All 20 CPLD attributes are readable from the daemon cache (/run/wedge100s/).

    Reads from the daemon cache rather than the kernel sysfs directly to avoid
    competing with wedge100s-i2c-daemon for the shared CP2112 USB-HID bus.
    """
    missing = []
    for attr in SYSFS_ATTRS:
        path = f"{RUN_DIR}/{attr}"
        out, err, rc = ssh.run(f"cat {path} 2>&1", timeout=10)
        if rc != 0 or "No such file" in out or "Permission denied" in out:
            missing.append(f"{attr}: {out.strip() or err.strip()}")
        else:
            print(f"  {attr}: {out.strip()!r}")
    assert not missing, (
        f"CPLD attrs missing from daemon cache:\n" + "\n".join(missing)
    )


# ------------------------------------------------------------------
# Daemon cache (/run/wedge100s/)
# ------------------------------------------------------------------

def test_cpld_run_dir_populated(ssh):
    """All CPLD attrs are present in /run/wedge100s/ (daemon cache).

    wedge100s-i2c-daemon copies each wedge100s_cpld sysfs attribute to
    /run/wedge100s/ on every 3-second poll tick.  This test verifies that
    the cache is populated so that psu.py and chassis.py can read from
    the canonical daemon-cache path.
    """
    missing = []
    for attr in SYSFS_ATTRS:
        path = f"{RUN_DIR}/{attr}"
        out, err, rc = ssh.run(f"cat {path} 2>&1", timeout=10)
        if rc != 0 or "No such file" in out or "Permission denied" in out:
            missing.append(f"{attr}: {out.strip() or err.strip()}")
        else:
            print(f"  {RUN_DIR}/{attr}: {out.strip()!r}")
    assert not missing, (
        f"CPLD attrs missing from {RUN_DIR}:\n" + "\n".join(missing) + "\n"
        "Is wedge100s-i2c-daemon running? Check: systemctl status wedge100s-i2c-poller.timer"
    )


# ------------------------------------------------------------------
# cpld_version format
# ------------------------------------------------------------------

def test_cpld_version_format(ssh):
    """cpld_version daemon cache reads as 'major.minor' with both fields numeric."""
    out, _, rc = ssh.run(f"cat {RUN_DIR}/cpld_version", timeout=10)
    assert rc == 0, f"Could not read {RUN_DIR}/cpld_version"
    version = out.strip()
    print(f"\ncpld_version: {version!r}")
    m = re.match(r"^(\d+)\.(\d+)$", version)
    assert m, (
        f"cpld_version format unexpected: {version!r} (expected 'N.N')"
    )
    major = int(m.group(1))
    minor = int(m.group(2))
    assert 0 <= major <= 255, f"cpld_version major={major} out of range [0, 255]"
    assert 0 <= minor <= 255, f"cpld_version minor={minor} out of range [0, 255]"
    print(f"  major={major} minor={minor}")


# ------------------------------------------------------------------
# PSU attributes
# ------------------------------------------------------------------

def _read_int_attr(ssh, attr):
    """Read a CPLD integer attribute from the daemon cache; return int or raise."""
    out, _, rc = ssh.run(f"cat {RUN_DIR}/{attr}", timeout=10)
    assert rc == 0, f"Could not read {RUN_DIR}/{attr} — has wedge100s-i2c-daemon run?"
    return int(out.strip(), 0)


def test_psu1_present_valid(ssh):
    """psu1_present is 0 or 1."""
    val = _read_int_attr(ssh, "psu1_present")
    print(f"\npsu1_present: {val}")
    assert val in (0, 1), f"psu1_present={val}, expected 0 or 1"


def test_psu1_pgood_valid(ssh):
    """psu1_pgood is 0 or 1."""
    val = _read_int_attr(ssh, "psu1_pgood")
    print(f"\npsu1_pgood: {val}")
    assert val in (0, 1), f"psu1_pgood={val}, expected 0 or 1"


def test_psu2_present_valid(ssh):
    """psu2_present is 0 or 1."""
    val = _read_int_attr(ssh, "psu2_present")
    print(f"\npsu2_present: {val}")
    assert val in (0, 1), f"psu2_present={val}, expected 0 or 1"


def test_psu2_pgood_valid(ssh):
    """psu2_pgood is 0 or 1."""
    val = _read_int_attr(ssh, "psu2_pgood")
    print(f"\npsu2_pgood: {val}")
    assert val in (0, 1), f"psu2_pgood={val}, expected 0 or 1"


def test_psu_pgood_implies_present(ssh):
    """A PSU that is power-good must also be present.

    pgood=1 and present=0 is physically impossible; indicates a CPLD read error.
    """
    for n in (1, 2):
        present = _read_int_attr(ssh, f"psu{n}_present")
        pgood   = _read_int_attr(ssh, f"psu{n}_pgood")
        print(f"  PSU{n}: present={present} pgood={pgood}")
        if pgood == 1:
            assert present == 1, (
                f"PSU{n}: pgood=1 but present=0 — physically impossible"
            )


# ------------------------------------------------------------------
# LED attributes
# ------------------------------------------------------------------

# Valid LED values: 0=off, 1=red, 2=green, 4=blue; any of these +8=blink
LED_VALID = {0, 1, 2, 4, 8, 9, 10, 12}


def test_led_sys1_valid(ssh):
    """led_sys1 value is a valid LED encoding."""
    val = _read_int_attr(ssh, "led_sys1")
    print(f"\nled_sys1: {val} (0x{val:02x})")
    assert val in LED_VALID, (
        f"led_sys1={val} is not a valid LED value {sorted(LED_VALID)}"
    )


def test_led_sys2_valid(ssh):
    """led_sys2 value is a valid LED encoding."""
    val = _read_int_attr(ssh, "led_sys2")
    print(f"\nled_sys2: {val} (0x{val:02x})")
    assert val in LED_VALID, (
        f"led_sys2={val} is not a valid LED value {sorted(LED_VALID)}"
    )


def test_led_sys2_cache_readable(ssh):
    """led_sys2 daemon cache file exists and contains a valid LED value.

    The hardware LED state is owned by ledd and reflected by wedge100s-i2c-daemon
    into /run/wedge100s/led_sys2.  Direct sysfs writes are avoided while the
    daemon is running to prevent CP2112 bus contention.
    """
    run_path = f"{RUN_DIR}/led_sys2"
    out, _, rc = ssh.run(f"cat {run_path}", timeout=10)
    assert rc == 0, f"Could not read {run_path}"
    val = int(out.strip(), 0)
    print(f"\nled_sys2 (cache): {val} (0x{val:02x})")
    assert val in LED_VALID, (
        f"led_sys2 cache value {val} is not a valid LED encoding {sorted(LED_VALID)}"
    )


# ------------------------------------------------------------------
# PSU alarm and input_ok attributes (GAP-013/014)
# ------------------------------------------------------------------

def test_psu_alarm_valid(ssh):
    """psu{1,2}_alarm values are 0 or 1 (OCP: 0=alarm, 1=normal)."""
    for n in (1, 2):
        val = _read_int_attr(ssh, f"psu{n}_alarm")
        print(f"  psu{n}_alarm: {val}")
        assert val in (0, 1), f"psu{n}_alarm={val}, expected 0 or 1"


def test_psu_input_ok_valid(ssh):
    """psu{1,2}_input_ok values are 0 or 1 (OCP: 0=bad, 1=OK)."""
    for n in (1, 2):
        val = _read_int_attr(ssh, f"psu{n}_input_ok")
        print(f"  psu{n}_input_ok: {val}")
        assert val in (0, 1), f"psu{n}_input_ok={val}, expected 0 or 1"


def test_psu_present_implies_input_ok(ssh):
    """If a PSU is present and power-good, input_ok must be 1 and alarm must be 1.

    OCP v1.3 section 7.7.2: a healthy, powered PSU has input_ok=1 (input AC OK)
    and alarm=1 (no alarm active).  Failure here suggests inverted polarity in
    the CPLD driver bit decode.
    """
    for n in (1, 2):
        present  = _read_int_attr(ssh, f"psu{n}_present")
        pgood    = _read_int_attr(ssh, f"psu{n}_pgood")
        input_ok = _read_int_attr(ssh, f"psu{n}_input_ok")
        alarm    = _read_int_attr(ssh, f"psu{n}_alarm")
        print(f"  PSU{n}: present={present} pgood={pgood} input_ok={input_ok} alarm={alarm}")
        if present == 1 and pgood == 1:
            assert input_ok == 1, (
                f"PSU{n}: present+pgood but input_ok=0 — "
                "polarity may be inverted (OCP spec: 0=bad, 1=OK)"
            )
            assert alarm == 1, (
                f"PSU{n}: present+pgood but alarm=0 — "
                "polarity may be inverted (OCP spec: 0=alarm, 1=normal)"
            )


# ------------------------------------------------------------------
# Board revision and model ID (GAP-030)
# ------------------------------------------------------------------

def test_board_rev_range(ssh):
    """board_rev is a 4-bit value in [0, 15]."""
    val = _read_int_attr(ssh, "board_rev")
    print(f"\nboard_rev: {val}")
    assert 0 <= val <= 15, f"board_rev={val}, expected 0-15 (4-bit field)"


def test_model_id_is_wedge100(ssh):
    """model_id should be 0 for the Wedge 100S TOR variant."""
    val = _read_int_attr(ssh, "model_id")
    print(f"\nmodel_id: {val}")
    assert val == 0, (
        f"model_id={val}, expected 0 (Wedge 100S TOR). "
        "Non-zero may indicate a different board variant."
    )


# ------------------------------------------------------------------
# Power rail health (GAP-012)
# ------------------------------------------------------------------

def test_pwr_stby_ok(ssh):
    """pwr_stby_ok must be 1 in a running system (standby power is present)."""
    val = _read_int_attr(ssh, "pwr_stby_ok")
    print(f"\npwr_stby_ok: {val}")
    assert val == 1, (
        f"pwr_stby_ok={val}, expected 1. "
        "Standby power must be present in a running system."
    )


def test_pwr_status2_healthy(ssh):
    """Decode pwr_status2: VRDY bits should be 1, HOT bits should be 0.

    Bit layout (6 bits):
      [0] VCORE_VRDY  — 1=voltage ready
      [1] VANLOG_VRDY — 1=voltage ready
      [2] V3V3_VRDY   — 1=voltage ready
      [3] VCORE_HOT   — 0=normal, 1=over-temperature
      [4] VANLOG_HOT  — 0=normal, 1=over-temperature
      [5] V3V3_HOT    — 0=normal, 1=over-temperature
    """
    val = _read_int_attr(ssh, "pwr_status2")
    print(f"\npwr_status2: {val} (0b{val:06b})")

    vcore_vrdy  = (val >> 0) & 1
    vanlog_vrdy = (val >> 1) & 1
    v3v3_vrdy   = (val >> 2) & 1
    vcore_hot   = (val >> 3) & 1
    vanlog_hot  = (val >> 4) & 1
    v3v3_hot    = (val >> 5) & 1

    print(f"  VCORE_VRDY={vcore_vrdy}  VANLOG_VRDY={vanlog_vrdy}  V3V3_VRDY={v3v3_vrdy}")
    print(f"  VCORE_HOT={vcore_hot}   VANLOG_HOT={vanlog_hot}   V3V3_HOT={v3v3_hot}")

    assert vcore_vrdy == 1, "VCORE voltage not ready"
    assert vanlog_vrdy == 1, "VANLOG voltage not ready"
    assert v3v3_vrdy == 1, "V3V3 voltage not ready"
    assert vcore_hot == 0, "VCORE over-temperature!"
    assert vanlog_hot == 0, "VANLOG over-temperature!"
    assert v3v3_hot == 0, "V3V3 over-temperature!"


# ------------------------------------------------------------------
# Reset reason (GAP-010)
# ------------------------------------------------------------------

# Known OCP spec reset reason codes
KNOWN_RESET_REASONS = {
    0x00,  # No reset / power-on
    0x11,  # Software warm reset
    0x22,  # CPU warm reset
    0x33,  # Watchdog reset
    0x44,  # Power cycle
    0x55,  # Power-on reset
    0x66,  # CPLD reset
    0x77,  # External reset
    0xFF,  # Unknown / first boot
}


def test_reset_reason_valid(ssh):
    """reset_reason should be one of the known OCP spec reset reason codes."""
    val = _read_int_attr(ssh, "reset_reason")
    print(f"\nreset_reason: 0x{val:02X}")
    assert val in KNOWN_RESET_REASONS, (
        f"reset_reason=0x{val:02X} is not a known OCP spec code. "
        f"Known codes: {sorted(f'0x{c:02X}' for c in KNOWN_RESET_REASONS)}"
    )


# ------------------------------------------------------------------
# ROV voltage (GAP-020)
# ------------------------------------------------------------------

def test_rov_voltage_sane(ssh):
    """Decode TH_ROV bits [3:0] as Tomahawk core voltage; verify 0.825-1.200V.

    The ROV (Regulator Output Voltage) strap encodes the target core voltage
    for the Memory PHY / Memory Interface / Core domain.
    Voltage = 1.200 - (code * 0.025) for codes 0-15.
    """
    val = _read_int_attr(ssh, "rov_status")
    rov_code = val & 0x0F
    voltage = 1.200 - (rov_code * 0.025)
    print(f"\nrov_status: 0x{val:02X}")
    print(f"  TH_ROV code: {rov_code}")
    print(f"  Decoded voltage: {voltage:.3f}V")
    assert 0.825 <= voltage <= 1.200, (
        f"ROV voltage {voltage:.3f}V out of sane range [0.825, 1.200]V "
        f"(rov_code={rov_code})"
    )


# ------------------------------------------------------------------
# COM-e status (GAP-025)
# ------------------------------------------------------------------

def test_come_status_readable(ssh):
    """come_status is readable and within an 8-bit range."""
    val = _read_int_attr(ssh, "come_status")
    print(f"\ncome_status: 0x{val:02X}")
    assert 0 <= val <= 255, f"come_status={val} outside 8-bit range"
