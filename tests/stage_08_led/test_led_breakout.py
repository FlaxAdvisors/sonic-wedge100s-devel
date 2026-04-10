"""Stage 08 supplement - LED breakout-mode lane mapping.

GAP-028: Verify that LEDs correctly reflect per-lane link state in
breakout modes. Requires at least one port configured for breakout.
"""

import pytest

RUN_DIR = "/run/wedge100s"


def _find_breakout_parent(ssh):
    """Find a 4x25G breakout parent port. Return parent Ethernet index or None.

    Args:
        ssh: SSH fixture connected to the SONiC target.

    Returns:
        int or None: Parent Ethernet index (multiple of 4) if a group of 4
        consecutive sub-ports is present, else None.
    """
    out, _, _ = ssh.run(
        "show interfaces status | grep -oP 'Ethernet\\d+' | sort -t n -k 2n",
        timeout=10)
    ifaces = set(out.strip().split('\n'))
    for idx in range(0, 128, 4):
        expected = [f'Ethernet{idx+j}' for j in range(4)]
        if all(e in ifaces for e in expected):
            return idx
    return None


def test_led_breakout_port_detected(ssh):
    """At least one 4x25G breakout port should be configured."""
    parent = _find_breakout_parent(ssh)
    if parent is None:
        pytest.skip("No 4x25G breakout port found - configure one to test GAP-028")
    print(f"  Breakout parent: Ethernet{parent}")


def test_led_breakout_all_up_solid(ssh):
    """In breakout mode with all lanes up, LEDUP1 should show link-up state."""
    parent = _find_breakout_parent(ssh)
    if parent is None:
        pytest.skip("No 4x25G breakout port found")

    # Check link status of all 4 sub-ports
    all_up = True
    for j in range(4):
        out, _, _ = ssh.run(
            f"show interfaces status Ethernet{parent+j} | tail -1", timeout=10)
        if "up" not in out.lower():
            all_up = False
            break

    if not all_up:
        pytest.skip(f"Not all sub-ports of Ethernet{parent} are link-up")

    # Read LEDUP1 state file for this LED port
    led_port = parent // 4  # approximate mapping
    out, _, rc = ssh.run(
        f"cat {RUN_DIR}/ledup1_port_{led_port} 2>/dev/null", timeout=10)
    if rc != 0:
        pytest.skip(f"ledup1_port_{led_port} not found")
    val = out.strip()
    print(f"  Ethernet{parent} (LED port {led_port}): ledup1={val}")
    assert val == '1', (
        f"All 4 sub-ports UP but LEDUP1 not showing link-up state"
    )
