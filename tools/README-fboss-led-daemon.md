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
| admin down                    | dim pink    | `0x07` |
| admin up, link down (pending) | purple      | `0x05` |
| 10G link up                   | cyan        | `0x01` |
| 25G link up                   | magenta     | `0x04` |
| 40G link up                   | bright pink | `0x00` |
| 50G link up                   | yellow      | `0x02` |
| 100G link up                  | green       | `0x03` |
| *(unknown-speed error)*       | red         | `0x06` |

All 5 supported link speeds (10/25/40/50/100 G) get a distinct color —
see `TODO-FBOSS-COLORS-SUCK.md` for why the palette is this awkward shape
(no pure blue, no true OFF, `0x00` repurposed as 40G slot because it
isn't usable as OFF anyway on this board). Red is reserved for
error/unexpected-speed conditions so users have an unambiguous "something
is wrong" signal.

### Why no "OFF" for link-down?

Standard switch UX would have unlinked ports dark. On this board,
**no byte produces a reliably dark LED** under the FBOSS bytecode:
`0x00` shows bright pink, `0x0f` shows dim pink, every other byte shows
pink too. Only CPLD-level gating (clearing `0x3c bit 1`) blacks the
panel, and that's all-or-nothing, not per-port. Full analysis and the
real-fix plan (custom LEDUP microcode) live in
`../TODO-FBOSS-COLORS-SUCK.md`.

So "admin down" renders as dim-pink (our quietest available color) and
"pending link" renders as purple (distinct, unambiguously "configured
but not carrying traffic").

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

## Known limitations

- Polls STATE_DB at 1 Hz — STATE_DB subscription would be lower latency
  but adds swsscommon event-loop complexity.
- No activity (TX/RX) blink on right arrows.
- No dynamic port add/remove — relies on hardcoded `PORT_TO_CAGE` map.
  A hwsku change (not just breakout mode) requires a daemon restart.
- CTRL pulse every frame even when nothing changed — benign but wasteful.

### Breakout handling

`PORT_TO_CAGE` maps all 128 possible `Ethernet0..127` names to the 32 cages
(4 sub-port names per cage). At each poll the daemon collects sub-port
states per cage and aggregates them via `aggregate_cage_state()`:

- Any oper-up sub-port wins — the cage reports the **max speed** of linked
  lanes as its effective speed (so 3-of-4 linked at 10G still lights cyan).
- If no sub-port is oper-up but any sub-port is admin-up → `(up, down, 0)`
  → purple ("pending link").
- All sub-ports admin-down → `(down, down, 0)` → dim pink.

This covers 1x100G, 2x50G, 4x25G, and 4x10G breakouts transparently. A
physical port in 1x100G mode has a single sub-port (`Ethernet(N*4)`);
sub-ports `(N*4+1..3)` simply don't appear in STATE_DB and are skipped.

## References

- Address map and methodology:
  [`notes/2026-04-21-fboss-led-mapping.md`](../notes/2026-04-21-fboss-led-mapping.md)
- Test tool: [`tools/wedge100s-fboss-led-test.sh`](./wedge100s-fboss-led-test.sh)
- Existing daemon source (for reference, on `play-sonic`):
  `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-ledup-linkstate.c`
- LEDUP init script (Phase 3 touches this):
  `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc`
