"""Stage 07 — QSFP28 transceiver presence and EEPROM (32 ports).

Phase 2 architecture:
  Presence and EEPROM data come from /run/wedge100s/ daemon cache files
  written by wedge100s-i2c-daemon.  The daemon reads via /dev/hidraw0
  (CP2112 USB-HID bridge); i2c_mux_pca954x, at24, and optoe are NOT loaded.

  sfp_N_present — 0/1 for QSFP port N (0-indexed)
  sfp_N_eeprom  — 256-byte page 0 EEPROM content (present ports only)
  eeprom_path() — Python API returns sysfs path for present ports

Port naming: Ethernet0..124 (step 4), corresponding to QSFP ports 0..31.

Populated slots are derived from tools/topology.json — any Ethernet port
referenced in breakout_ports, optical_ports, portchannels, or hosts implies
a QSFP slot with an optic or DAC installed.

Phase reference: Phase 6 (QSFP/SFP).
"""

import json
import os
import re
import pytest

NUM_PORTS = 32

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOPOLOGY_PATH = os.path.join(_REPO_ROOT, "tools", "topology.json")


def _load_topology():
    with open(_TOPOLOGY_PATH) as f:
        return json.load(f)


def _eth_to_qsfp_slot(eth_name):
    """Ethernet120 -> 30 (QSFP slot = Ethernet index / 4)."""
    m = re.match(r"Ethernet(\d+)", eth_name)
    return int(m.group(1)) // 4 if m else None


def _populated_slots():
    """Return set of 0-based QSFP slot indices that should have optics/DACs."""
    topo = _load_topology()
    ports = set()

    for bp in topo.get("breakout_ports", []):
        ports.add(bp["parent"])
    for op in topo.get("optical_ports", []):
        ports.add(op["port"])
    for pc in topo.get("portchannels", []):
        for m in pc.get("members", []):
            ports.add(m)
    for h in topo.get("hosts", []):
        ports.add(h["port"])

    slots = set()
    for p in ports:
        s = _eth_to_qsfp_slot(p)
        if s is not None:
            slots.add(s)
    return slots


QSFP_CAPTURE = """\
import json, sys
from sonic_platform.platform import Platform

def _vendor_string(path):
    \"\"\"Read bytes 148-163 from EEPROM and return printable chars (>=4 consecutive).\"\"\"
    try:
        with open(path, 'rb') as f:
            data = f.read(164)
        if len(data) < 164:
            return ''
        vendor_bytes = data[148:164]
        result, run = [], []
        for b in vendor_bytes:
            if 0x20 <= b <= 0x7e:
                run.append(chr(b))
            else:
                if len(run) >= 4:
                    result.append(''.join(run))
                run = []
        if len(run) >= 4:
            result.append(''.join(run))
        return ' '.join(result).strip()
    except OSError:
        return ''

chassis = Platform().get_chassis()
results = []
for idx in range(1, 33):
    sfp = chassis.get_sfp(idx)
    present = sfp.get_presence()
    eeprom_path = None
    error_desc = None
    vendor_name = None
    try:
        eeprom_path = sfp.get_eeprom_path() if present else None
        error_desc = sfp.get_error_description()
        if present and eeprom_path:
            vendor_name = _vendor_string(eeprom_path)
    except Exception as e:
        error_desc = f'EXCEPTION: {e}'
    results.append({
        'index': idx,
        'name': sfp.get_name(),
        'present': present,
        'eeprom_path': eeprom_path,
        'error_description': error_desc,
        'position': sfp.get_position_in_parent(),
        'vendor_name': vendor_name,
    })
print(json.dumps(results))
"""


def _get_qsfps(ssh):
    out, err, rc = ssh.run_python(QSFP_CAPTURE, timeout=90)
    assert rc == 0, f"QSFP capture script failed (rc={rc}): {err}"
    return json.loads(out.strip())


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def test_qsfp_cli_presence(ssh):
    """show interfaces transceiver presence exits 0 and lists all 32 ports."""
    out, err, rc = ssh.run("show interfaces transceiver presence")
    print(f"\nshow interfaces transceiver presence:\n{out}")
    assert rc == 0, f"Command failed: {err}"
    assert out.strip(), "transceiver presence returned empty output"

    # Count Ethernet data rows
    eth_rows = [l for l in out.splitlines() if re.match(r"\s*Ethernet\d+", l)]
    print(f"\nPort rows: {len(eth_rows)}")
    assert len(eth_rows) >= NUM_PORTS, (
        f"Expected ≥{NUM_PORTS} Ethernet port rows, found {len(eth_rows)}"
    )


# ------------------------------------------------------------------
# Python API — presence table
# ------------------------------------------------------------------

def test_qsfp_api_port_count(ssh):
    """Platform returns presence for all 32 QSFP ports."""
    data = _get_qsfps(ssh)

    present_ports = [p for p in data if p["present"]]
    absent_ports  = [p for p in data if not p["present"]]

    print(f"\nQSFP port summary: {len(present_ports)} present, {len(absent_ports)} absent")
    print("\nPresent ports:")
    for p in present_ports:
        print(f"  {p['name']:15s}  eeprom={p['eeprom_path']}")
    if absent_ports:
        absent_names = [p['name'] for p in absent_ports]
        print(f"\nAbsent ports ({len(absent_ports)}): {absent_names[:8]}{'...' if len(absent_names)>8 else ''}")

    assert len(data) == NUM_PORTS, (
        f"Expected {NUM_PORTS} port entries, got {len(data)}"
    )


def test_qsfp_api_names(ssh):
    """QSFP port names follow 'QSFP28 N' pattern."""
    data = _get_qsfps(ssh)
    for p in data:
        assert "QSFP" in p["name"] or "SFP" in p["name"], (
            f"Unexpected port name: {p['name']!r}"
        )


def test_qsfp_api_positions(ssh):
    """QSFP positions are 1-based sequential 1..32."""
    data = _get_qsfps(ssh)
    positions = sorted(p["position"] for p in data)
    assert positions == list(range(1, NUM_PORTS + 1)), (
        f"Non-sequential positions: {positions}"
    )


def test_qsfp_api_present_error_description(ssh):
    """Present ports report error_description indicating OK/present."""
    data = _get_qsfps(ssh)
    for p in data:
        if not p["present"]:
            continue
        desc = p["error_description"]
        assert "OK" in str(desc).upper() or "present" in str(desc).lower(), (
            f"Port {p['name']!r} is present but error_description={desc!r}"
        )
        assert "EXCEPTION" not in str(desc), (
            f"Port {p['name']!r} raised an exception: {desc}"
        )


def test_qsfp_api_absent_error_description(ssh):
    """Absent ports report error_description indicating unplugged/absent."""
    data = _get_qsfps(ssh)
    for p in data:
        if p["present"]:
            continue
        desc = p["error_description"]
        # Absent ports should say "unplugged" or similar — not an exception
        assert "EXCEPTION" not in str(desc), (
            f"Port {p['name']!r} (absent) raised an exception: {desc}"
        )


# ------------------------------------------------------------------
# Topology-aware presence check
# ------------------------------------------------------------------

def test_qsfp_topology_ports_present(ssh):
    """Ports referenced in topology.json should have optics/DACs present."""
    expected = _populated_slots()
    data = _get_qsfps(ssh)

    missing = []
    for p in data:
        slot = p["index"] - 1  # index is 1-based, slots are 0-based
        if slot in expected and not p["present"]:
            missing.append(f"QSFP slot {slot} (Ethernet{slot*4})")

    print(f"\nExpected populated slots: {sorted(expected)}")
    print(f"Missing: {missing or 'none'}")
    assert not missing, (
        f"Topology expects optics/DACs but ports report absent: {missing}"
    )


# ------------------------------------------------------------------
# EEPROM reads — only for topology-known populated ports
# ------------------------------------------------------------------

def _topology_present_ports(data):
    """Filter QSFP data to only ports expected by topology.json."""
    expected = _populated_slots()
    return [p for p in data
            if (p["index"] - 1) in expected and p["present"] and p["eeprom_path"]]


def test_qsfp_eeprom_path_exists(ssh):
    """For topology-populated ports, the EEPROM cache file exists on target."""
    data = _get_qsfps(ssh)
    present = _topology_present_ports(data)
    if not present:
        pytest.skip("No topology-populated QSFP ports present")

    for p in present:
        path = p["eeprom_path"]
        out, _, rc = ssh.run(f"test -f {path} && echo EXISTS || echo MISSING")
        assert "EXISTS" in out, (
            f"Port {p['name']!r}: EEPROM path {path!r} does not exist on target"
        )


def test_qsfp_eeprom_identifier_byte(ssh):
    """EEPROM byte 0 (identifier) is non-zero for topology-populated ports."""
    data = _get_qsfps(ssh)
    present = _topology_present_ports(data)
    if not present:
        pytest.skip("No topology-populated QSFP ports present")

    p = present[0]
    path = p["eeprom_path"]
    # Read first byte (identifier: 0x0D=QSFP+, 0x11=QSFP28, 0x18=QSFP-DD)
    out, err, rc = ssh.run(
        f"sudo hexdump -n 1 -e '1/1 \"0x%02x\"' {path} 2>/dev/null"
    )
    print(f"\n{p['name']} EEPROM identifier byte: {out.strip()}")
    assert rc == 0, f"Could not read EEPROM for {p['name']}: {err}"
    assert out.strip() and out.strip() != "0x00", (
        f"Port {p['name']!r} EEPROM identifier byte is 0x00 (unexpected)"
    )


def test_qsfp_eeprom_vendor_info(ssh):
    """At least one topology-populated port has readable vendor string."""
    data = _get_qsfps(ssh)
    present = _topology_present_ports(data)
    if not present:
        pytest.skip("No topology-populated QSFP ports present")

    readable = [(p["name"], p["vendor_name"]) for p in present if p.get("vendor_name")]

    print(f"\nVendor-readable ports ({len(readable)}/{len(present)}):")
    for name, vendor in readable:
        print(f"  {name}: {vendor!r}")
    if not readable:
        print(f"\nNo readable vendor from: {[p['name'] for p in present]}")

    assert readable, (
        f"No topology-populated port has ≥4 printable chars at EEPROM bytes 148–163 "
        f"(checked {len(present)} ports). "
        f"Possible cause: DAC cable quality (garbled vendor field is a known issue)."
    )


# ------------------------------------------------------------------
# PCA9535 GPIO expanders (raw presence check)
# ------------------------------------------------------------------

def _pca9535_check(ssh, bus, addr):
    """Return (raw_value_or_None, status_string) for a PCA9535 i2cget attempt."""
    out, err, rc = ssh.run(f"sudo i2cget -y {bus} 0x{addr:02x} 0x00 2>&1")
    combined = (out + err).strip()
    if rc == 0:
        return out.strip(), "ok"
    if "busy" in combined.lower():
        return None, "busy"   # kernel driver has it — expected
    return None, f"error: {combined}"


def test_pca9535_daemon_cache_ports_0_15(ssh):
    """PCA9535 presence data for ports 0-15 is in daemon cache files.

    Phase 2: i2c-36 does not exist (i2c_mux_pca954x not loaded).
    wedge100s-i2c-daemon reads PCA9535 at mux 0x74 ch2 via /dev/hidraw0
    and writes /run/wedge100s/sfp_{0..15}_present.
    """
    missing = []
    for port in range(16):
        out, _, rc = ssh.run(f"cat /run/wedge100s/sfp_{port}_present 2>/dev/null")
        if rc != 0 or out.strip() not in ("0", "1"):
            missing.append(port)
    assert not missing, (
        f"Ports {missing} have missing/invalid presence cache files.\n"
        "Fix: sudo systemctl start wedge100s-i2c-poller.service"
    )


def test_pca9535_daemon_cache_ports_16_31(ssh):
    """PCA9535 presence data for ports 16-31 is in daemon cache files.

    Phase 2: i2c-37 does not exist (i2c_mux_pca954x not loaded).
    wedge100s-i2c-daemon reads PCA9535 at mux 0x74 ch3 via /dev/hidraw0
    and writes /run/wedge100s/sfp_{16..31}_present.
    """
    missing = []
    for port in range(16, 32):
        out, _, rc = ssh.run(f"cat /run/wedge100s/sfp_{port}_present 2>/dev/null")
        if rc != 0 or out.strip() not in ("0", "1"):
            missing.append(port)
    assert not missing, (
        f"Ports {missing} have missing/invalid presence cache files.\n"
        "Fix: sudo systemctl start wedge100s-i2c-poller.service"
    )
