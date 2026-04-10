"""Stage 15 supplement — CL73 autonegotiation interop test (GAP-027).

Verify that CL73 autoneg can be enabled per-port via the SONiC CLI
(``config interface autoneg``) and that the port successfully
negotiates a 100G link with the Arista EOS peer ``rabbit-lorax``.

This test is **not** part of the default stage_15 run because it
reconfigures a production link (Ethernet48 is routed and carries
traffic in the lab). It is a standalone verification script that must
be invoked explicitly::

    cd tests && pytest stage_15_autoneg_fec/test_autoneg_cl73.py -v

**Prerequisite (GAP-027 config fix):**

The BCM SDK globally gates Clause 73 autoneg via
``phy_an_c73`` in ``th-wedge100s-32x-flex.config.bcm``. With
``phy_an_c73=0x0`` (the current setting as of 2026-04-09), the SDK
will not arm CL73 state machines for any port, and an attempt to
enable autoneg from SONiC drops the port to a CL37 fallback
(25G KR2) that cannot negotiate with a 100G peer. This test will fail
with a "link did not come up" assertion in that state.

To run this test successfully:

1. Build the platform .deb with ``phy_an_c73=0x1``::

       device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm

2. Deploy the .deb and restart syncd::

       sudo dpkg -i sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
       sudo systemctl restart swss

3. Configure the Arista peer Ethernet15/1 for autoneg::

       rabbit-lorax# configure
       rabbit-lorax(config)# interface Ethernet15/1
       rabbit-lorax(config-if-Et15/1)# speed auto 100gfull

4. Run this test.

**Topology (verified 2026-04-09):**

- Ethernet48 (SONiC) ↔ Ethernet15/1 (Arista rabbit-lorax)
- Ethernet48 is a standalone routed port, NOT a PortChannel1 member
- 100GBASE-CR4 DAC, both ends are Tomahawk (BCM56960-TSCF)
- Ethernet48 maps to BCM port 34 / diag shell ``ce7``

See ``notes/2026-04-09-autoneg-testing.md`` for the research record
and deferral rationale.

Phase reference: Phase 15 (Auto-Negotiation & FEC Configuration).
"""

import time
import pytest

# SONiC interface connected to rabbit-lorax Ethernet15/1.
# Update if lab topology changes.
AUTONEG_PORT = "Ethernet48"
AUTONEG_PEER_PORT = "Ethernet15/1"  # rabbit-lorax

# Link wait budget — CL73 negotiation typically completes in
# 100-500 ms, but orchagent/syncd programming adds latency and
# CR4 DAC link-training takes a few seconds on top.
LINK_WAIT_S = 30

# Stability observation window once link is up — flapping shorter
# than this would indicate unstable CL73 behaviour with this peer.
STABILITY_WINDOW_S = 10


def _port_oper_state(ssh, port):
    """Return the oper state string for ``port`` from APPL_DB.

    Reads ``PORT_TABLE:<port>`` ``oper_status`` which is written by
    portsyncd when the kernel netdev transitions up/down.
    """
    out, _, _ = ssh.run(
        f"redis-cli -n 0 hget 'PORT_TABLE:{port}' oper_status", timeout=10
    )
    return out.strip().lower()


def _wait_link_up(ssh, port, timeout):
    """Poll oper_status until it is 'up' or timeout expires.

    Returns the elapsed time in seconds, or ``None`` if the link never
    came up within ``timeout``.
    """
    start = time.time()
    deadline = start + timeout
    while time.time() < deadline:
        if _port_oper_state(ssh, port) == "up":
            return time.time() - start
        time.sleep(1)
    return None


@pytest.fixture(scope="module")
def cl73_port_restore(ssh):
    """Capture and restore the original forced-speed state.

    Records autoneg, speed and admin_status before the test and
    restores them afterwards so a failing test cannot leave the
    production link in a degraded state.
    """
    out, _, _ = ssh.run(
        f"redis-cli -n 4 hget 'PORT|{AUTONEG_PORT}' autoneg", timeout=10
    )
    original_autoneg = out.strip() or "off"

    out, _, _ = ssh.run(
        f"redis-cli -n 4 hget 'PORT|{AUTONEG_PORT}' speed", timeout=10
    )
    original_speed = out.strip() or "100000"

    out, _, _ = ssh.run(
        f"redis-cli -n 4 hget 'PORT|{AUTONEG_PORT}' admin_status", timeout=10
    )
    original_admin = out.strip() or "up"

    yield {
        "autoneg": original_autoneg,
        "speed": original_speed,
        "admin": original_admin,
    }

    # Restore forced-speed state. Run these even on test failure.
    ssh.run(
        f"sudo config interface autoneg {AUTONEG_PORT} disabled", timeout=15)
    ssh.run(
        f"sudo config interface speed {AUTONEG_PORT} {original_speed}",
        timeout=15,
    )
    if original_admin != "up":
        ssh.run(
            f"sudo config interface shutdown {AUTONEG_PORT}", timeout=15)
    # Give orchagent/syncd time to re-program the ASIC.
    time.sleep(5)


def test_cl73_enable_negotiate(ssh, cl73_port_restore):
    """Enable CL73 on Ethernet48 and verify link comes up within 30 s.

    Assumes the BCM SDK config has ``phy_an_c73=0x1`` and the peer
    (rabbit-lorax Et15/1) is configured for autoneg. See this module's
    docstring for prerequisites.
    """
    # Enable CL73 autoneg at the orchagent level. This writes
    # ``autoneg=on`` to CONFIG_DB which propagates through portsyncd,
    # orchagent and syncd to SAI_PORT_ATTR_AUTO_NEG_MODE.
    ssh.run(
        f"sudo config interface autoneg {AUTONEG_PORT} enabled", timeout=15)
    ssh.run(
        f"sudo config interface advertised-speeds {AUTONEG_PORT} 100000",
        timeout=15,
    )

    elapsed = _wait_link_up(ssh, AUTONEG_PORT, LINK_WAIT_S)
    assert elapsed is not None, (
        f"{AUTONEG_PORT}: link did not come up with CL73 autoneg "
        f"within {LINK_WAIT_S} s. Check that phy_an_c73=0x1 is in the "
        f"deployed BCM config and that peer {AUTONEG_PEER_PORT} is "
        f"configured for autoneg."
    )
    print(f"  {AUTONEG_PORT}: CL73 link up in {elapsed:.1f} s")

    # Observe stability — a flapping link would toggle oper_status
    # within this window.
    flaps = 0
    last = "up"
    end = time.time() + STABILITY_WINDOW_S
    while time.time() < end:
        state = _port_oper_state(ssh, AUTONEG_PORT)
        if state != last:
            flaps += 1
            last = state
        time.sleep(1)
    assert flaps == 0, (
        f"{AUTONEG_PORT}: CL73 link flapped {flaps} time(s) in the "
        f"{STABILITY_WINDOW_S} s stability window — unstable with "
        f"peer {AUTONEG_PEER_PORT}."
    )
    assert last == "up", (
        f"{AUTONEG_PORT}: CL73 link ended the stability window in "
        f"state '{last}'"
    )


def test_cl73_disable_restore(ssh, cl73_port_restore):
    """Disable autoneg and verify the forced-speed link restores.

    This test must run after :func:`test_cl73_enable_negotiate` and
    returns the port to its original forced-speed state so the lab
    topology is consistent for subsequent test modules.
    """
    original_speed = cl73_port_restore["speed"]
    ssh.run(
        f"sudo config interface autoneg {AUTONEG_PORT} disabled", timeout=15)
    ssh.run(
        f"sudo config interface speed {AUTONEG_PORT} {original_speed}",
        timeout=15,
    )

    elapsed = _wait_link_up(ssh, AUTONEG_PORT, LINK_WAIT_S)
    assert elapsed is not None, (
        f"{AUTONEG_PORT}: forced-speed link did not restore within "
        f"{LINK_WAIT_S} s after disabling autoneg."
    )
    print(
        f"  {AUTONEG_PORT}: forced-speed {original_speed} link restored "
        f"in {elapsed:.1f} s"
    )
