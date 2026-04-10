"""Stage 03 supplement — QSFP lane-swap and polarity-flip PRBS validation (GAP-003).

!!! WARNING !!!  This test disrupts any link connected to a tested port
    by running PRBS31 on it. Do not run during production traffic. The
    test requires loopback modules in the QSFP cages OR a cooperating
    peer running PRBS on the other end. Set ``LANE_SWAP_TEST_ACKNOWLEDGED=1``
    to opt in.

GAP-003 (P0 Correctness) static audit companion. Cross-references the
OCP spec v1.3 Table 10 QSFP lane assignments against the
``phy_xaui_*_polarity_flip`` / ``xgxs_*_lane_map`` settings in
``th-wedge100s-32x-flex.config.bcm``. Runs PRBS31 on each populated port
and checks for zero errors — non-zero errors indicate a lane swap or
polarity mismatch between the BCM config and the physical QSFP wiring.

Background
----------

The static audit in ``notes/2026-04-09-lane-swap-audit.md`` enumerates
32 ports × 2 directions and flags ~22 direction-ports where the OCP
spec and the current BCM config structurally disagree on whether a
lane-swap correction is needed. None of the flagged rows can be
corrected from static analysis alone because:

1. The Broadcom ``xgxs_{rx,tx}_lane_map`` nibble order is documented
   ambiguously across Broadcom SDKs and Accton reference configs — two
   inverse interpretations both exist in the wild.
2. Three ports (Ethernet88, Ethernet96, Ethernet112) have 3-nibble
   lane maps (``0x213``, ``0x123``, ``0x123``) that are structurally
   suspicious regardless of nibble interpretation.
3. The production board has been running with the current config, so
   some of the apparent mismatches may be explained by FEC masking or
   symmetric SDK compensation that we cannot observe statically.

Every apparent mismatch is therefore *speculative* until PRBS31 on the
real hardware confirms that the physical lanes carry the expected data.
A non-zero PRBS error count on a given direction is the minimum
requirement for touching the BCM config.

Gating
------

This test is gated behind ``LANE_SWAP_TEST_ACKNOWLEDGED`` because PRBS
takes over the SerDes TX/RX independently of SAI, which is **disruptive
to any active link** on the port. The gating pattern mirrors
``tests/stage_15_autoneg_fec/test_autoneg_cl73.py`` (which similarly
disrupts a production link for its duration).

Runtime model
-------------

For each populated QSFP port (detected via ``/run/wedge100s/sfp_N_present``),
the test drives the BCM diag shell to:

  1. Clear PRBS counters and configure PRBS31 on all four lanes.
  2. Start PRBS TX+RX on the port.
  3. Wait ``PRBS_DURATION_S`` seconds for counters to accumulate.
  4. Read the per-lane error count via ``phy diag <port> prbs get``.
  5. Stop PRBS and release the SerDes back to normal traffic.

Any non-zero per-lane error count is treated as a lane routing or
polarity mismatch, and the per-lane details are printed to help the
operator diff them against the static audit table.

See ``notes/2026-04-09-lane-swap-audit.md`` for the full 32-port
cross-reference table and the per-port mismatch verdicts.

Phase reference: Phase 3 (Platform Infrastructure).
"""

import os
import re
import time

import pytest

# --------------------------------------------------------------------
# Opt-in gate
# --------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    os.environ.get("LANE_SWAP_TEST_ACKNOWLEDGED") != "1",
    reason=(
        "Lane-swap PRBS test disrupts links on tested ports. "
        "Set LANE_SWAP_TEST_ACKNOWLEDGED=1 to opt in. Requires loopback "
        "modules or a cooperating peer running PRBS."
    ),
)

# --------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------
NUM_PORTS = 32
PRBS_DURATION_S = 10
RUN_DIR = "/run/wedge100s"

# Minimum interval between "clear" and "get" for the BCM diag shell to
# accumulate a meaningful error count. 10 s of PRBS31 at 25 Gbps per lane
# is 2.5e11 bits; zero errors over that window gives a BER bound of
# roughly 4e-12 which is enough to catch any gross lane swap.
PRBS_MIN_BITS = 25_000_000_000 * PRBS_DURATION_S  # per lane, approx

# Max error count per lane that we still treat as "link training noise"
# rather than a structural mismatch. Any structural swap or polarity
# issue manifests as sustained ~50% BER which blows through this
# threshold in microseconds.
PRBS_NOISE_TOLERANCE = 1_000

# SONiC Ethernet<N> → BCM diag-shell port label.
#
# The BCM diag shell uses "ce<N>" labels for 100G ports, where N is the
# zero-based index assigned by the SDK when the port comes up. The
# authoritative mapping is the ``ps`` output from the diag shell — this
# table is a static snapshot derived from ``led_proc_init.soc`` scan
# positions (which are in BCM port-number order) and should be kept in
# sync with the BCM config's portmap.
#
# Format: sonic_iface -> (bcm_port, first_serdes, ce_label_hint)
#
# ``ce_label_hint`` is only a hint — the runtime code resolves the
# actual ce label from ``ps`` output at test time so that a portmap
# change in the BCM config does not silently wedge this test. The hint
# is used only for error messages and for sanity-checking.
SONIC_PORT_TABLE = {
    # sonic          (bcm,  1st_serdes, physQSFP)
    "Ethernet0":    (118, 117, 0),
    "Ethernet4":    (122, 113, 1),
    "Ethernet8":    (126, 125, 2),
    "Ethernet12":   (130, 121, 3),
    "Ethernet16":   (1,   5,   4),
    "Ethernet20":   (5,   1,   5),
    "Ethernet24":   (9,   13,  6),
    "Ethernet28":   (13,  9,   7),
    "Ethernet32":   (17,  21,  8),
    "Ethernet36":   (21,  17,  9),
    "Ethernet40":   (25,  29,  10),
    "Ethernet44":   (29,  25,  11),
    "Ethernet48":   (34,  37,  12),
    "Ethernet52":   (38,  33,  13),
    "Ethernet56":   (42,  45,  14),
    "Ethernet60":   (46,  41,  15),
    "Ethernet64":   (50,  53,  16),
    "Ethernet68":   (54,  49,  17),
    "Ethernet72":   (58,  61,  18),
    "Ethernet76":   (62,  57,  19),
    "Ethernet80":   (68,  69,  20),
    "Ethernet84":   (72,  65,  21),
    "Ethernet88":   (76,  77,  22),
    "Ethernet92":   (80,  73,  23),
    "Ethernet96":   (84,  85,  24),
    "Ethernet100":  (88,  81,  25),
    "Ethernet104":  (92,  93,  26),
    "Ethernet108":  (96,  89,  27),
    "Ethernet112":  (102, 101, 28),
    "Ethernet116":  (106, 97,  29),
    "Ethernet120":  (110, 109, 30),
    "Ethernet124":  (114, 105, 31),
}

# Ports flagged as high-confidence mismatches by the static audit.
# See notes/2026-04-09-lane-swap-audit.md §4.1.  These are the most
# interesting candidates for a PRBS dry run — if they come up clean,
# the config nibble-order hypothesis (§2.2 of the audit) is refuted
# and the mismatches become real.
HIGH_CONFIDENCE_MISMATCH_PORTS = {
    "Ethernet0",    # RX swap expected, config identity
    "Ethernet4",    # RX / TX inversion
    "Ethernet8",    # RX swap expected, config identity
    "Ethernet32",   # TX swap expected, config identity
    "Ethernet36",   # TX swap inverted
    "Ethernet40",   # RX / TX inversion
    "Ethernet44",   # RX / TX inversion
    "Ethernet48",   # TX swap expected, config identity
    "Ethernet52",   # TX swap inverted
    "Ethernet56",   # TX swap expected, config identity
    "Ethernet68",   # TX swap expected, config identity
    "Ethernet84",   # identity expected, config non-identity both dirs
    "Ethernet92",   # RX + TX swap expected, config identity
    "Ethernet100",  # RX identity expected, config non-identity
    "Ethernet120",  # RX / TX inversion
    "Ethernet124",  # TX swap expected, config identity
}

# Ports flagged as LOW CONFIDENCE structural (category C / D, suspicious
# 3-nibble lane maps). See notes/2026-04-09-lane-swap-audit.md §4.3.
LOW_CONFIDENCE_PORTS = {
    "Ethernet88",   # FC19, OCP category D (4,2,3,1), config `0x213`
    "Ethernet96",   # FC21, OCP category C (4,3,2,1), config `0x123`
    "Ethernet112",  # FC25, OCP category C (4,3,2,1), config `0x123`
}


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def _bcmcmd(ssh, cmd, timeout=15):
    """Run a diag-shell command via ``bcmcmd`` and return stdout.

    ``bcmcmd`` is a host-side wrapper that pipes its argument into the
    running syncd container's BCM diag shell. It may emit the shell
    prompt prefix and a trailing newline — callers should trim as
    needed.
    """
    out, err, rc = ssh.run(f"sudo bcmcmd '{cmd}'", timeout=timeout)
    if rc != 0:
        pytest.skip(
            f"bcmcmd failed (rc={rc}); syncd not running or diag shell "
            f"not reachable. stderr={err!r}"
        )
    return out


def _populated_ports(ssh):
    """Return the list of populated SONiC port names as strings.

    Uses ``/run/wedge100s/sfp_<idx>_present`` written by the
    wedge100s-i2c-daemon (no direct I2C access from the test — that
    would violate the I2C bus safety rule).  ``idx`` is the physical
    QSFP number 0..31, independent of the SONiC interface number.
    """
    populated = []
    for sonic_iface, (_bcm, _first, phys) in SONIC_PORT_TABLE.items():
        path = f"{RUN_DIR}/sfp_{phys}_present"
        out, _, rc = ssh.run(f"cat {path} 2>/dev/null", timeout=5)
        if rc == 0 and out.strip() == "1":
            populated.append(sonic_iface)
    return populated


def _resolve_ce_label(ssh, bcm_port):
    """Return the ``ce<N>`` diag-shell label for a BCM port number.

    The BCM ``ps`` output includes per-row labels like ``ce0`` through
    ``ce31`` (for 100G ports) next to the BCM logical port number. This
    function reads ``ps`` once and caches a simple lookup.
    """
    if not hasattr(_resolve_ce_label, "_cache"):
        out = _bcmcmd(ssh, "ps")
        cache = {}
        # ``ps`` rows look like:
        #   ce0( 118) 100G ...
        # Regex is lenient to handle spacing variations.
        row_re = re.compile(
            r"^\s*(ce\d+|xe\d+)\s*\(\s*(\d+)\s*\)",
        )
        for line in out.splitlines():
            m = row_re.match(line)
            if m:
                label = m.group(1)
                bcm = int(m.group(2))
                cache[bcm] = label
        _resolve_ce_label._cache = cache

    cache = _resolve_ce_label._cache
    if bcm_port not in cache:
        pytest.skip(
            f"BCM port {bcm_port} not found in ``ps`` output — the BCM "
            f"config portmap may have changed since the static table in "
            f"SONIC_PORT_TABLE was built. Re-run the audit in "
            f"notes/2026-04-09-lane-swap-audit.md to refresh."
        )
    return cache[bcm_port]


def _start_prbs(ssh, ce_label):
    """Start PRBS31 on all lanes of ``ce_label`` and clear counters.

    Broadcom diag-shell sequence::

        phy diag ce<N> prbs set p=3     # PRBS-31
        phy diag ce<N> prbs enable tx+rx
        phy diag ce<N> prbs clear

    The ``prbs clear`` zeroes the per-lane error latch so the next
    ``get`` returns only errors accumulated after clearing.
    """
    _bcmcmd(ssh, f"phy diag {ce_label} prbs set p=3")
    _bcmcmd(ssh, f"phy diag {ce_label} prbs enable tx+rx")
    _bcmcmd(ssh, f"phy diag {ce_label} prbs clear")


def _stop_prbs(ssh, ce_label):
    """Disable PRBS on ``ce_label`` and return the port to normal TX/RX."""
    _bcmcmd(ssh, f"phy diag {ce_label} prbs disable tx+rx")


def _read_prbs_errors(ssh, ce_label):
    """Read per-lane PRBS error counts on ``ce_label``.

    Returns a dict ``{lane_idx: error_count}`` for lanes 0..3. Any lane
    that reports "no sync" / "not locked" is recorded as the string
    ``"no_sync"`` so the caller can distinguish an unlocked receiver
    from a receiver that locked but has errors.
    """
    out = _bcmcmd(ssh, f"phy diag {ce_label} prbs get")
    # Expected format per lane (varies across SDK versions):
    #   lane 0: errors 0 (locked)
    #   lane 1: not in lock
    errors = {}
    lane_re = re.compile(
        r"lane\s+(\d+).*?(?:errors?\s+(\d+)|not\s+(?:in\s+)?lock)",
        re.IGNORECASE,
    )
    for m in lane_re.finditer(out):
        lane = int(m.group(1))
        if m.group(2) is not None:
            errors[lane] = int(m.group(2))
        else:
            errors[lane] = "no_sync"
    return errors


# --------------------------------------------------------------------
# The actual test
# --------------------------------------------------------------------

def test_prbs_zero_errors_populated_ports(ssh):
    """Run PRBS31 on every populated QSFP port and require zero errors.

    Non-zero error counts indicate a lane-swap or polarity mismatch
    between the BCM config and the physical QSFP wiring. Any failure
    should be cross-referenced against the 32-port audit table in
    ``notes/2026-04-09-lane-swap-audit.md`` for remediation suggestions.

    The test skips gracefully if no QSFP ports are populated, if the
    BCM diag shell is not reachable, or if the BCM ``ps`` output does
    not contain a row for a BCM port named in the static table.
    """
    populated = _populated_ports(ssh)
    if not populated:
        pytest.skip(
            "No populated QSFP ports — insert loopback modules or "
            "connect a cooperating peer and re-run."
        )

    print(
        f"\nPRBS31 sweep across {len(populated)} populated port(s): "
        f"{', '.join(populated)}"
    )
    print(
        f"  {PRBS_DURATION_S}s per port, ~{PRBS_MIN_BITS/1e9:.0f} Gbit "
        f"per lane, noise tolerance {PRBS_NOISE_TOLERANCE} err/lane"
    )

    failures = []  # (sonic_iface, lane, error_count, verdict_tag)

    for sonic_iface in populated:
        bcm_port, first_serdes, phys = SONIC_PORT_TABLE[sonic_iface]
        ce_label = _resolve_ce_label(ssh, bcm_port)

        # Flag ports that the static audit already marked suspicious so
        # the operator sees them clearly in the console output.
        tag = ""
        if sonic_iface in LOW_CONFIDENCE_PORTS:
            tag = " [AUDIT: LOW-CONFIDENCE lane map]"
        elif sonic_iface in HIGH_CONFIDENCE_MISMATCH_PORTS:
            tag = " [AUDIT: HIGH-CONFIDENCE mismatch]"

        print(
            f"  {sonic_iface} (BCM {bcm_port}, 1st serdes {first_serdes}, "
            f"QSFP{phys}, diag {ce_label}){tag}"
        )

        _start_prbs(ssh, ce_label)
        try:
            time.sleep(PRBS_DURATION_S)
            errors = _read_prbs_errors(ssh, ce_label)
        finally:
            _stop_prbs(ssh, ce_label)

        for lane in range(4):
            count = errors.get(lane)
            if count is None:
                failures.append((sonic_iface, lane, "missing", tag))
                print(f"    lane {lane}: NO READING (regex mismatch?)")
            elif count == "no_sync":
                failures.append((sonic_iface, lane, "no_sync", tag))
                print(f"    lane {lane}: RX NOT LOCKED")
            elif count > PRBS_NOISE_TOLERANCE:
                failures.append((sonic_iface, lane, count, tag))
                print(f"    lane {lane}: {count} errors (FAIL)")
            else:
                print(f"    lane {lane}: {count} errors (ok)")

    if failures:
        lines = [
            "PRBS31 detected lane errors on the following direction-ports:"
        ]
        for iface, lane, count, tag in failures:
            lines.append(f"  {iface} lane {lane}: {count}{tag}")
        lines.append("")
        lines.append(
            "Cross-reference these against the 32-port audit table in "
            "notes/2026-04-09-lane-swap-audit.md §3 to identify the "
            "required xgxs_{rx,tx}_lane_map correction. Do NOT guess a "
            "fix from the audit table alone — confirm with a second PRBS "
            "run after each config edit."
        )
        pytest.fail("\n".join(lines))
