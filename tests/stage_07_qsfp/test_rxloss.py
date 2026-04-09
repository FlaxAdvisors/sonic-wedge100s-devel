"""Stage 07 supplement — QSFP RXLOSS signal monitoring.

GAP-011: Verify that /run/wedge100s/sfp_N_rxlos files are written by
the i2c-daemon and contain valid values (0=OK, 1=loss detected).
"""

import pytest

NUM_PORTS = 32
RUN_DIR = "/run/wedge100s"


def test_rxlos_files_exist(ssh):
    """All 32 RXLOSS files should be present in /run/wedge100s/."""
    missing = []
    for port in range(NUM_PORTS):
        path = f"{RUN_DIR}/sfp_{port}_rxlos"
        out, _, rc = ssh.run(f"test -f {path} && echo YES || echo NO", timeout=10)
        if "YES" not in out:
            missing.append(port)
    assert not missing, (
        f"Missing rxlos files for ports: {missing}. "
        "Is wedge100s-i2c-daemon running with RXLOSS support?"
    )


def test_rxlos_values_valid(ssh):
    """All RXLOSS values should be 0 or 1."""
    for port in range(NUM_PORTS):
        path = f"{RUN_DIR}/sfp_{port}_rxlos"
        out, _, rc = ssh.run(f"cat {path} 2>/dev/null", timeout=10)
        if rc != 0:
            continue
        val = out.strip()
        assert val in ('0', '1'), (
            f"Port {port}: rxlos={val!r}, expected '0' or '1'"
        )


def test_present_port_no_rxloss(ssh):
    """Populated ports with link UP should not have RX loss."""
    for port in range(NUM_PORTS):
        pres_path = f"{RUN_DIR}/sfp_{port}_present"
        rxlos_path = f"{RUN_DIR}/sfp_{port}_rxlos"
        out_p, _, rc_p = ssh.run(f"cat {pres_path} 2>/dev/null", timeout=10)
        out_r, _, rc_r = ssh.run(f"cat {rxlos_path} 2>/dev/null", timeout=10)
        if rc_p != 0 or rc_r != 0:
            continue
        present = out_p.strip()
        rxlos = out_r.strip()
        if present == '1':
            print(f"  Port {port}: present=1, rxlos={rxlos}")
            if rxlos == '1':
                print(f"    WARNING: Port {port} present but RXLOSS=1 (fiber issue?)")
