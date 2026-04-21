# wedge100s-fboss-ledup-linkstate — FBOSS LED link-state daemon

Phase 2 of the FBOSS LED cutover. Reads SONiC `STATE_DB` for per-port
link state and writes per-LED color bytes to `CMIC_LEDUP{0,1}_DATA_RAM`
using the verified 64-entry map from
[`notes/2026-04-21-fboss-led-mapping.md`](../notes/2026-04-21-fboss-led-mapping.md).

## Files

| File | Role |
|---|---|
| `wedge100s-fboss-ledup-linkstate.py` | The daemon itself |
| `wedge100s-fboss-ledup-linkstate.service` | systemd unit |
| `wedge100s-fboss-led-test.sh` | Visual LED test / FBOSS bytecode loader |

## Color policy (v1)

| Port state | Color | Byte |
|---|---|---|
| admin down                              | dim pink               | `0x07` |
| admin up, link down                     | purple (AS7712-"blue") | `0x05` |
| admin up, link up, ≥ 100 Gbps           | green                  | `0x03` |
| admin up, link up, 40 Gbps              | yellow                 | `0x02` |
| admin up, link up, < 40 Gbps            | cyan                   | `0x01` |
| admin up, link up, unknown speed        | magenta                | `0x04` |

### Why not just "OFF for link-down"?

Standard switch UX would have unlinked ports dark. The FBOSS bytecode
on this board has **no reliable "truly OFF" byte**:
- `0x00` → bright pink (BCM HW auto-populates `DATA_RAM[0..31]` link
  bits that somehow inject pink into the scan chain)
- `0x0f` → dim pink when flooded, only appears dark as optical contrast
  against a bright-pink neighbor
- Every other byte 0x08..0xff → pink (same as 0x00)
- Only way to force the panel truly dark is clearing CPLD 0x3c bit 1
  (`th_led_en`), which gates all LEDs off globally — not per-port.

The palette choice above borrows from the AS7712's convention: admin-up
but unlinked gets a distinctive quiet color ("blue" on AS7712, our
palette's purple — the closest blue-ish we have). Admin-down goes dim
pink as a subtler "port is configured out" state.

A real per-port OFF capability needs custom LED microcode that checks a
daemon-controlled "suppress" flag per port. Broadcom LEDASM opcodes
aren't publicly documented — that's a reverse-engineering project for
Phase 3 or later.

Both arrows of a cage currently get the same color. Activity blink
(TX/RX on R-arrow) is not implemented in v1.

Defective/blue-weak LEDs (documented in the mapping notes) will render
the color palette imperfectly — this is hardware variance on this
specific unit and is not corrected in software. The daemon picks colors
that minimize visual confusion on the known-defective LEDs (e.g.
`0x03` green for link-up requires only the green channel, works fine
on all known blue-weak LEDs).

## Deployment (testing on lapin)

### One-shot sanity check (dev only)

On the foreman host, from this repo:
```sh
scp tools/wedge100s-fboss-ledup-linkstate.py lapin:/tmp/
ssh lapin 'sudo python3 /tmp/wedge100s-fboss-ledup-linkstate.py --oneshot --verbose'
```

This auto-loads FBOSS bytecode if needed, reads STATE_DB once, writes a
single frame, and exits. Useful for verifying the daemon + map work
end-to-end before enabling the long-running service.

### Full systemd deployment

```sh
scp tools/wedge100s-fboss-ledup-linkstate.py      lapin:/tmp/
scp tools/wedge100s-fboss-ledup-linkstate.service lapin:/tmp/

ssh lapin '
  sudo install -m 755 /tmp/wedge100s-fboss-ledup-linkstate.py      /usr/local/bin/ &&
  sudo install -m 644 /tmp/wedge100s-fboss-ledup-linkstate.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now wedge100s-fboss-ledup-linkstate
'

# Watch the log
ssh lapin 'sudo journalctl -u wedge100s-fboss-ledup-linkstate -f'
```

### Stop / remove

```sh
ssh lapin 'sudo systemctl disable --now wedge100s-fboss-ledup-linkstate'
```

Clean shutdown clears `DATA_RAM[192..223]` to `0x00` (LEDs revert to the
stock link-status pink baseline until the next daemon start).

## Coexistence with the existing daemon

`wedge100s-ledup-linkstate` (stock, Phase-1-era) writes to
`CMIC_LEDUP1_DATA_RAM[64..95]` per the patched LEDUP1 bytecode in
`led_proc_init.soc`. That's a disjoint address range from our
`[192..223]`, so **both daemons may run at once without corrupting each
other's state**.

Only the currently-loaded bytecode determines which writes actually
light LEDs:

- Stock bytecode loaded → old daemon drives LEDs; new daemon's writes
  have no visible effect.
- FBOSS bytecode loaded → new daemon drives LEDs; old daemon's writes
  have no visible effect.

Our daemon auto-loads FBOSS bytecode at startup (unless
`--no-bytecode-check` is passed), so running this daemon effectively
takes over the panel from the old one.

Phase 3 will retire the old daemon + stock bytecode entirely, in a
single topic-branch commit on the platform fork.

## Known limitations (v1)

- Polls STATE_DB at 1 Hz — STATE_DB subscription would be lower latency
  but adds swsscommon event-loop complexity.
- No activity (TX/RX) blink on right arrows.
- Breakout sub-ports (4×25G) not handled — reads only the parent
  `Ethernet(N*4)` of each cage. When a cage is in breakout mode, the
  parent port is typically down; the daemon will show that as "link
  down" even if the breakout lanes are up. Fix in v2.
- No dynamic port add/remove — relies on hardcoded `PORT_TO_CAGE` map.
  A breakout or hwsku change requires a daemon restart.
- CTRL pulse every frame even when nothing changed — benign but wasteful.

## References

- Address map and methodology:
  [`notes/2026-04-21-fboss-led-mapping.md`](../notes/2026-04-21-fboss-led-mapping.md)
- Test tool: [`tools/wedge100s-fboss-led-test.sh`](./wedge100s-fboss-led-test.sh)
- Existing daemon source (for reference, on `play-sonic`):
  `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-ledup-linkstate.c`
- LEDUP init script (Phase 3 touches this):
  `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc`
