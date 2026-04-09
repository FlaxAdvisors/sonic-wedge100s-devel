"""Stage 06 supplement — Verify PSU CPLD register 0x10 bit polarity.

GAP-002: OCP spec v1.3 section 7.7.2 defines 8 bits in register 0x10.
This test reads all 8 bits and validates polarity against known PSU state.

Requires: Both PSUs physically installed and powered.
"""

import pytest

RUN_DIR = "/run/wedge100s"


def _read_int(ssh, attr):
    out, _, rc = ssh.run(f"cat {RUN_DIR}/{attr}", timeout=10)
    assert rc == 0, f"Could not read {RUN_DIR}/{attr}"
    return int(out.strip(), 0)


def test_register_0x10_all_bits(ssh):
    """Read all 8 PSU status bits and print comprehensive report."""
    bits = {}
    for attr in ('psu1_present', 'psu1_pgood', 'psu1_input_ok', 'psu1_alarm',
                 'psu2_present', 'psu2_pgood', 'psu2_input_ok', 'psu2_alarm'):
        bits[attr] = _read_int(ssh, attr)
        print(f"  {attr}: {bits[attr]}")

    for n in (1, 2):
        if bits[f'psu{n}_present'] == 1 and bits[f'psu{n}_pgood'] == 1:
            assert bits[f'psu{n}_input_ok'] == 1, (
                f"PSU{n}: present+pgood but input_ok=0 — "
                "polarity may be inverted (OCP spec: 0=bad, 1=OK)"
            )
            assert bits[f'psu{n}_alarm'] == 1, (
                f"PSU{n}: present+pgood but alarm=0 — "
                "polarity may be inverted (OCP spec: 0=alarm, 1=normal)"
            )
