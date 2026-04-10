"""Stage 08 supplement - pure-function tests for LED state aggregation.

GAP-028: Unit tests for _iface_to_led_port() and _aggregate_led_states()
from wedge100s-ledup-linkstate. These run without hardware and catch
regressions in the aggregation logic directly.

The daemon script lives in the platform fork, not on sys.path, so we
load it via importlib.
"""

import importlib.machinery
import importlib.util
import os
import pytest

# Path to the daemon script in the platform fork.
_DAEMON_PATH = (
    "/export/sonic/sonic-buildimage/platform/broadcom/"
    "sonic-platform-modules-accton/wedge100s-32x/utils/"
    "wedge100s-ledup-linkstate"
)


@pytest.fixture(scope="module")
def daemon():
    """Load the daemon script as a module without executing main().

    Skips the test if the daemon file is not present at the expected
    path, or if the expected helper functions are missing (e.g. when
    running against a sonic-buildimage checkout on a branch that
    predates Task 5).

    The daemon is an executable script with no .py extension, so
    importlib.util.spec_from_file_location() won't auto-detect a
    loader. We use SourceFileLoader explicitly.
    """
    if not os.path.exists(_DAEMON_PATH):
        pytest.skip(f"Daemon script not found at {_DAEMON_PATH}")

    loader = importlib.machinery.SourceFileLoader(
        "wedge100s_ledup_linkstate", _DAEMON_PATH
    )
    spec = importlib.util.spec_from_loader(
        "wedge100s_ledup_linkstate", loader
    )
    module = importlib.util.module_from_spec(spec)
    # The daemon uses `if __name__ == "__main__": main()` so importing
    # it does not execute main().
    spec.loader.exec_module(module)

    # Sanity-check that the functions under test are present. On a
    # platform fork branch that predates Task 5, these won't exist.
    if not hasattr(module, "_aggregate_led_states"):
        pytest.skip(
            "Daemon at %s predates GAP-028 "
            "(no _aggregate_led_states)" % _DAEMON_PATH
        )
    return module


def test_iface_to_led_port_native(daemon):
    """Native 100G port maps to its LED slot via _IFACE_TO_LED_PORT."""
    # From _IFACE_TO_LED_PORT: Ethernet16 -> 1, Ethernet0 -> 29, Ethernet8 -> 31
    assert daemon._iface_to_led_port('Ethernet16') == 1
    assert daemon._iface_to_led_port('Ethernet0') == 29
    assert daemon._iface_to_led_port('Ethernet8') == 31


def test_iface_to_led_port_breakout(daemon):
    """Breakout sub-ports map to the parent's LED slot."""
    # Ethernet16..19 (4x25G breakout of Ethernet16) -> LED slot 1
    for j in range(4):
        assert daemon._iface_to_led_port(f'Ethernet{16+j}') == 1, (
            f"Ethernet{16+j} should map to LED port 1 (parent Ethernet16)"
        )
    # Ethernet0..3 (4x25G breakout of Ethernet0) -> LED slot 29
    for j in range(4):
        assert daemon._iface_to_led_port(f'Ethernet{j}') == 29, (
            f"Ethernet{j} should map to LED port 29 (parent Ethernet0)"
        )


def test_iface_to_led_port_non_ethernet(daemon):
    """Non-Ethernet interfaces return None."""
    assert daemon._iface_to_led_port('PortChannel1') is None
    assert daemon._iface_to_led_port('Loopback0') is None
    assert daemon._iface_to_led_port('eth0') is None
    assert daemon._iface_to_led_port('Ethernet') is None      # no index
    assert daemon._iface_to_led_port('EthernetXYZ') is None   # non-numeric


def test_aggregate_all_up(daemon):
    """All sub-ports up -> 0x80."""
    states = {f'Ethernet{16+j}': True for j in range(4)}
    result = daemon._aggregate_led_states(states)
    assert result == {1: 0x80}, f"Expected {{1: 0x80}}, got {result}"


def test_aggregate_all_down(daemon):
    """All sub-ports down -> 0x00."""
    states = {f'Ethernet{16+j}': False for j in range(4)}
    result = daemon._aggregate_led_states(states)
    assert result == {1: 0x00}, f"Expected {{1: 0x00}}, got {result}"


def test_aggregate_partial(daemon):
    """Partial (some up, some down) -> 0x80 per current workaround.

    FIXME(GAP-028-followup): when LEDUP1 bytecode supports blink, this
    should become 0x81. See notes/2026-04-09-led-breakout-partial.md.
    """
    states = {
        'Ethernet16': True,
        'Ethernet17': False,
        'Ethernet18': True,
        'Ethernet19': False,
    }
    result = daemon._aggregate_led_states(states)
    assert result == {1: 0x80}, f"Expected {{1: 0x80}}, got {result}"


def test_aggregate_multiple_slots(daemon):
    """Multiple LED slots aggregate independently."""
    states = {
        # Slot 1 (Ethernet16..19): all up
        'Ethernet16': True, 'Ethernet17': True,
        'Ethernet18': True, 'Ethernet19': True,
        # Slot 0 (Ethernet20..23): all down
        'Ethernet20': False, 'Ethernet21': False,
        'Ethernet22': False, 'Ethernet23': False,
        # Slot 29 (Ethernet0..3): partial
        'Ethernet0': True, 'Ethernet1': False,
        'Ethernet2': True, 'Ethernet3': False,
    }
    result = daemon._aggregate_led_states(states)
    assert result[1] == 0x80
    assert result[0] == 0x00
    assert result[29] == 0x80  # partial currently -> 0x80


def test_aggregate_ignores_non_ethernet(daemon):
    """Non-Ethernet interfaces are silently ignored."""
    states = {
        'Ethernet16': True, 'Ethernet17': True,
        'Ethernet18': True, 'Ethernet19': True,
        'PortChannel1': True,
        'Loopback0': True,
    }
    result = daemon._aggregate_led_states(states)
    assert result == {1: 0x80}
