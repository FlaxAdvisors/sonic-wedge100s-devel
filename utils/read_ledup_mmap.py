#!/usr/bin/env python3
"""Read BCM56960 LEDUP DATA_RAM and PROGRAM_RAM via PCIe BAR2 /dev/mem.

Bypasses bcmcmd/dsserve — reads CMIC registers directly.  Must run as root.

CMIC LEDUP register offsets within BAR2 (Tomahawk BCM56960):
  CMIC_LEDUP0_DATA_RAM:    0x21000 + 4*index  (index 0..255)
  CMIC_LEDUP0_PROGRAM_RAM: 0x21400 + 4*index
  CMIC_LEDUP1_DATA_RAM:    0x21400 + 4*index
  CMIC_LEDUP1_PROGRAM_RAM: 0x21800 + 4*index

Verified against bcmcmd getreg on live BCM56960 hardware (2026-04-07).

Bit layout per DATA_RAM entry (lower 8 bits):
  7: Link Up    6: Flow Control   5: Full Duplex
  4:3: Speed (00=10M, 01=100M, 10=1G, 11=10G+)
  2: Collision  1: TX activity    0: RX activity
"""

import mmap
import os
import struct
import sys

BCM_VID = "0x14e4"
BCM_DID = "0xb960"

LEDUP_DATA_BASES = {0: 0x20400, 1: 0x21400}
LEDUP_PROG_BASES = {0: 0x20800, 1: 0x21800}
SPEED_NAMES = ["10M", "100M", "1G", "10G+"]

# Interface mapping for display (LED_port → SONiC interface)
LED_PORT_TO_IFACE = {
    0: "Ethernet20",  1: "Ethernet16",  2: "Ethernet28",  3: "Ethernet24",
    4: "Ethernet36",  5: "Ethernet32",  6: "Ethernet44",  7: "Ethernet40",
    8: "Ethernet52",  9: "Ethernet48", 10: "Ethernet60", 11: "Ethernet56",
   12: "Ethernet68", 13: "Ethernet64", 14: "Ethernet76", 15: "Ethernet72",
   16: "Ethernet84", 17: "Ethernet80", 18: "Ethernet92", 19: "Ethernet88",
   20: "Ethernet100",21: "Ethernet96", 22: "Ethernet108",23: "Ethernet104",
   24: "Ethernet116",25: "Ethernet112",26: "Ethernet124",27: "Ethernet120",
   28: "Ethernet4",  29: "Ethernet0",  30: "Ethernet12", 31: "Ethernet8",
}


def find_bcm_bar2():
    for dev in os.listdir("/sys/bus/pci/devices"):
        devpath = "/sys/bus/pci/devices/" + dev
        try:
            vid = open(devpath + "/vendor").read().strip()
            did = open(devpath + "/device").read().strip()
        except OSError:
            continue
        if vid == BCM_VID and did == BCM_DID:
            lines = open(devpath + "/resource").read().strip().split("\n")
            parts = lines[2].split()
            start = int(parts[0], 16)
            end = int(parts[1], 16)
            if start == 0:
                continue
            return start, end - start + 1
    return None, None


def decode_flags(val):
    if val == 0:
        return "(dark)"
    parts = []
    if val & 0x80:
        parts.append("Link")
    if val & 0x40:
        parts.append("FC")
    if val & 0x20:
        parts.append("FD")
    parts.append(SPEED_NAMES[(val >> 3) & 3])
    if val & 0x04:
        parts.append("Col")
    if val & 0x02:
        parts.append("TX")
    if val & 0x01:
        parts.append("RX")
    return " ".join(parts)


def read_reg(mm, offset):
    mm.seek(offset)
    return struct.unpack("<I", mm.read(4))[0] & 0xFF


def dump_data_ram(mm, proc, start=0, end=32):
    base = LEDUP_DATA_BASES[proc]
    zone = ""
    if proc == 1 and start >= 64:
        zone = " (daemon safe zone)"
    print("\n=== LEDUP%d DATA_RAM[%d..%d]%s ===" % (proc, start, end - 1, zone))
    print("%-6s %-14s %-6s %s" % ("Entry", "Interface", "Hex", "Flags"))
    for i in range(start, end):
        val = read_reg(mm, base + 4 * i)
        led_port = i if i < 32 else i - 64
        iface = LED_PORT_TO_IFACE.get(led_port, "")
        print("[%-3d]  %-14s 0x%02x   %s" % (i, iface, val, decode_flags(val)))


def dump_prog_ram(mm, proc, offsets=None):
    base = LEDUP_PROG_BASES[proc]
    if offsets is None:
        offsets = list(range(256))
    print("\n=== LEDUP%d PROGRAM_RAM ===" % proc)
    line = []
    for i in offsets:
        val = read_reg(mm, base + 4 * i)
        line.append("%02x" % val)
        if len(line) == 16 or i == offsets[-1]:
            addr = i - len(line) + 1
            print("  0x%02x: %s" % (addr, " ".join(line)))
            line = []


def check_patch(mm):
    """Verify the LEDUP1 bytecode patch is in place."""
    base = LEDUP_PROG_BASES[1]
    b14 = read_reg(mm, base + 4 * 0x14)
    b15 = read_reg(mm, base + 4 * 0x15)
    patch = [read_reg(mm, base + 4 * (0xF0 + i)) for i in range(10)]

    print("\n=== LEDUP1 Bytecode Patch Status ===")
    print("  PROG[0x14] = 0x%02x  (expect 0x77 = JMP)" % b14)
    print("  PROG[0x15] = 0x%02x  (expect 0xF0 = target addr)" % b15)
    print("  PROG[0xF0..0xF9] = %s" % " ".join("%02x" % x for x in patch))
    print("  Expected:          02 f9 0a 40 12 fc 06 fc 77 16")

    ok = (b14 == 0x77 and b15 == 0xF0 and
          patch == [0x02, 0xF9, 0x0A, 0x40, 0x12, 0xFC, 0x06, 0xFC, 0x77, 0x16])
    print("  Status: %s" % ("PATCHED (correct)" if ok else "NOT PATCHED or CORRUPTED"))
    return ok


def print_summary(mm):
    """Print a quick summary: which ports are up/down on each chain."""
    print("\n=== LED State Summary ===")
    print("%-14s  %-10s  %-10s  %s" % ("Interface", "LEDUP0", "LEDUP1[+64]", "Expected LED"))

    for led_port in range(32):
        iface = LED_PORT_TO_IFACE.get(led_port, "?")
        v0 = read_reg(mm, LEDUP_DATA_BASES[0] + 4 * led_port)
        v1 = read_reg(mm, LEDUP_DATA_BASES[1] + 4 * (led_port + 64))
        blue = bool(v0 & 0x80)
        orange = bool(v1 & 0x80)
        if blue and orange:
            color = "MAGENTA (up)"
        elif blue:
            color = "BLUE (down)"
        elif orange:
            color = "ORANGE (anomaly!)"
        else:
            color = "OFF"
        print("%-14s  0x%02x %-5s  0x%02x %-5s  %s" % (
            iface, v0, "blue" if blue else "-",
            v1, "orng" if orange else "-", color))


def usage():
    print("Usage: %s [options]" % sys.argv[0])
    print("  (no args)     Show summary of all 32 ports (both chains)")
    print("  --data N      Dump LEDUP<N> DATA_RAM[0..31]")
    print("  --safe        Dump LEDUP1 DATA_RAM[64..95] (daemon safe zone)")
    print("  --patch       Check LEDUP1 bytecode patch status")
    print("  --prog N      Dump full LEDUP<N> PROGRAM_RAM (256 bytes)")
    print("  --all         Show everything")
    sys.exit(0)


def main():
    bar_addr, bar_size = find_bcm_bar2()
    if bar_addr is None:
        print("ERROR: BCM56960 BAR2 not found")
        sys.exit(1)

    print("BCM56960 BAR2: 0x%x  size=0x%x" % (bar_addr, bar_size))

    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    mm = mmap.mmap(fd, bar_size, mmap.MAP_SHARED, mmap.PROT_READ,
                   offset=bar_addr)

    args = sys.argv[1:]

    if not args or args == ["--help"] or args == ["-h"]:
        if not args:
            check_patch(mm)
            print_summary(mm)
        else:
            usage()
    elif "--all" in args:
        check_patch(mm)
        dump_data_ram(mm, 0, 0, 32)
        dump_data_ram(mm, 1, 0, 32)
        dump_data_ram(mm, 1, 64, 96)
        dump_prog_ram(mm, 0)
        dump_prog_ram(mm, 1)
        print_summary(mm)
    else:
        for i, arg in enumerate(args):
            if arg == "--data" and i + 1 < len(args):
                proc = int(args[i + 1])
                dump_data_ram(mm, proc, 0, 32)
            elif arg == "--safe":
                dump_data_ram(mm, 1, 64, 96)
            elif arg == "--patch":
                check_patch(mm)
            elif arg == "--prog" and i + 1 < len(args):
                proc = int(args[i + 1])
                dump_prog_ram(mm, proc)

    mm.close()
    os.close(fd)


if __name__ == "__main__":
    main()
