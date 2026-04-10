"""Stage 05 supplement — CPLD HEART_ATTACK_EN register state (GAP-015).

Non-destructive static checks that run unconditionally:

- ``heart_attack_en`` sysfs attribute exists and is readable (skips
  cleanly until the ``wedge100s_cpld`` driver is bound to ``1-0032`` in
  a future commit; see notes/2026-04-09-fan-heartbeat.md §8)
- the attribute's value is a valid boolean ("0" or "1")
- all 5 fan trays are currently present (prerequisite for any future
  destructive variant of this test)

Destructive variant (future, gated on ``FAN_HEARTBEAT_TEST_ACKNOWLEDGED=1``):
removing all fans to observe CPLD hardware-shutdown behaviour. Cannot
be automated — it needs a human to physically pull trays and a serial
console to capture the time-to-shutdown — so the placeholder test
always skips with a pointer to the manual procedure documented in
notes/2026-04-09-fan-heartbeat.md §5.

See also:
    notes/2026-04-09-fan-heartbeat.md — full decision framework,
    observed boot-default register value, and manual destructive
    test procedure for a maintenance window.
"""

import os
import pytest

RUN_DIR = "/run/wedge100s"
CPLD_SYSFS = "/sys/bus/i2c/devices/1-0032"


def test_heart_attack_en_sysfs_exists(ssh):
    """``heart_attack_en`` sysfs attribute is present on the CPLD device.

    The attribute is exposed by the ``wedge100s_cpld`` kernel driver.
    Skips (does not fail) until the driver is bound to ``1-0032`` —
    see notes/2026-04-09-fan-heartbeat.md §8 for why the live switch
    does not currently have a bound CPLD device.
    """
    out, _, _ = ssh.run(
        f"test -f {CPLD_SYSFS}/heart_attack_en && echo YES || echo NO",
        timeout=10,
    )
    if "YES" not in out:
        pytest.skip(
            "heart_attack_en sysfs attribute not yet present — "
            "wedge100s_cpld driver is not bound to 1-0032 on this "
            "system. See notes/2026-04-09-fan-heartbeat.md §8."
        )


def test_heart_attack_en_value_valid(ssh):
    """``heart_attack_en`` reads as the string "0" or "1".

    The value reflects bit 7 of CPLD register 0x2E. A value of 1
    means the CPLD hardware fan-failure shutdown is enabled; 0 means
    SONiC ``thermalctld`` is solely responsible for fan-failure
    response. Skips if the attribute does not yet exist.
    """
    out, _, rc = ssh.run(
        f"cat {CPLD_SYSFS}/heart_attack_en 2>/dev/null", timeout=10,
    )
    if rc != 0:
        pytest.skip(
            "heart_attack_en attribute not readable — driver not yet "
            "bound to 1-0032"
        )
    val = out.strip()
    assert val in ("0", "1"), (
        f"heart_attack_en={val!r}, expected '0' or '1'"
    )
    meaning = (
        "enabled - CPLD hw shutdown on all-fans-removed"
        if val == "1" else "disabled - thermalctld only"
    )
    print(f"  heart_attack_en = {val} ({meaning})")


def test_fan_present_all_five(ssh):
    """All 5 fan trays are present.

    This is a prerequisite for any heartbeat-related test: if trays
    are already missing, the system state is already degraded and
    the heartbeat mechanism cannot be meaningfully tested. The
    ``/run/wedge100s/fan_present`` file should contain a bitmask
    ``0x1f`` (bits 0-4 set = trays 1-5 present).

    Note: on the current daemon this file reads ``"0"`` (ASCII zero)
    rather than ``"0x1f"`` — see notes/2026-04-09-fan-heartbeat.md §2
    for the separately-tracked daemon bug. This test will serve as
    the tripwire for that bug until it is fixed.
    """
    out, _, rc = ssh.run(f"cat {RUN_DIR}/fan_present", timeout=10)
    assert rc == 0, "Cannot read /run/wedge100s/fan_present"
    raw = out.strip()
    try:
        present = int(raw, 0)
    except ValueError:
        pytest.fail(
            f"fan_present = {raw!r}, expected a hex/decimal bitmask "
            "(e.g. 0x1f or 31). Daemon bug — see "
            "notes/2026-04-09-fan-heartbeat.md §2."
        )
    assert present == 0x1F, (
        f"fan_present = 0x{present:02x}, expected 0x1f "
        "(all 5 trays). Missing trays affect the heartbeat mechanism, "
        "or daemon is computing the bitmask incorrectly — see "
        "notes/2026-04-09-fan-heartbeat.md §2."
    )


@pytest.mark.skipif(
    os.environ.get("FAN_HEARTBEAT_TEST_ACKNOWLEDGED") != "1",
    reason=(
        "Destructive fan-heartbeat test requires physical fan removal "
        "and serial-console capture. Set "
        "FAN_HEARTBEAT_TEST_ACKNOWLEDGED=1 to acknowledge. NOTE: the "
        "destructive path is not automated — see "
        "notes/2026-04-09-fan-heartbeat.md §5 for the manual procedure."
    ),
)
def test_destructive_all_fans_removed_placeholder(ssh):
    """Placeholder for the manual destructive fan-heartbeat test.

    This test intentionally does not attempt to automate fan removal.
    A future implementation could pair with a physical test rig that
    pulls trays on command, but today the destructive path is a pure
    tripwire: if an operator sets the env var and runs the test, they
    get an explicit message pointing to the manual procedure in
    notes/2026-04-09-fan-heartbeat.md §5.
    """
    pytest.skip(
        "Destructive fan-heartbeat test is not automated. Follow the "
        "manual procedure in notes/2026-04-09-fan-heartbeat.md §5:\n"
        "  1. Start serial console capture: "
        "ssh bang-lorax tail -f screenlog.ttyUSB2.0\n"
        "  2. Stop wedge100s daemons "
        "(wedge100s-i2c-daemon, wedge100s-bmc-daemon, pmon)\n"
        "  3. Remove fan trays one by one, recording reg 0x2e state\n"
        "  4. For the all-fans-removed case, record time-to-shutdown "
        "from serial console\n"
        "  5. Reinsert all trays and verify recovery / register "
        "restore"
    )
