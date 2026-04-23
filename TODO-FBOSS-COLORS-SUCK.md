# TODO: FBOSS 22-byte bytecode palette is impoverished

## The problem

The 22-byte FBOSS LED microcode we ship on the wedge100s LEDUP engines
encodes only 3 bits per port (RGB, one bit per channel). Across 8 possible
values we see 7 *visibly distinct* colors on this panel — and crucially,
**none of the 8 are a usable "pure blue" or "pure white" or "truly OFF".**

Empirical palette (DATA_RAM byte → visible color on wedge100s):

| byte | visible color | notes |
|---:|---|---|
| `0x00` | bright pink | NOT off — some CPLD wiring interaction injects red+blue |
| `0x01` | cyan | G+B channels on |
| `0x02` | yellow | R+G channels on |
| `0x03` | green | — |
| `0x04` | magenta | R+B — similar shade to 0x00 bright pink |
| `0x05` | purple | darker R+B; daemon uses this for admin-up/link-down |
| `0x06` | red | — |
| `0x07` | dim pink | daemon uses this for admin-down |

Notably **missing**: pure blue, pure white, and any "truly OFF" byte
(a bit pattern that produces no LED output for a port).

## Why this is a problem

1. **Can't represent all 5 link-up speeds distinctly**: 10G/25G/40G/50G/100G
   want 5 distinct colors. Excluding reserved slots (purple for pending
   link, dim-pink for admin-down) and our policy of not using red-for-valid
   ("red means error"), we only have 4 non-reserved colors. Two speeds
   have to share one color. See `tools/wedge100s-fboss-ledup-linkstate.py`
   `port_color()` — currently 40G and 50G share yellow.
2. **No true OFF**: unplugged / admin-down ports can't actually be dark.
   `0x00` shows bright pink (CPLD-wiring quirk) and every other byte
   produces some visible output. We use `0x07` dim-pink as the quietest
   visible proxy for "admin-down", but it's not off.
3. **Can't show pure blue**: the BMC's own CPLD rainbow proves the LEDs
   are physically *capable* of blue (`wedge100s-led-diag-bmc.py` cycles
   through yellow/blue/cyan/green/magenta/red via CPLD test-pattern mode,
   which bypasses our scan chain). Our FBOSS-driven palette can't reach it.

## Proof that the hardware can do more

CPLD register 0x3c + `test_mode_en=1` with 4 different `th_led_steam`
values produces 4 distinct solid panel colors. `test_mode_en + blink`
cycles 6 colors including **pure blue**. Those colors don't go through
our LEDUP bytecode at all — they come from the CPLD's built-in test
generator. So the panel LEDs are full-RGB capable; the limitation is
purely in how our bytecode encodes bytes into scan-chain bits.

## What a real fix looks like

Write new Broadcom LEDASM microcode that encodes more bits per port (or
uses a different wire encoding) to unlock the remaining colors. The
hard part:

- Broadcom LEDASM opcode reference is **not publicly documented**. Only
  two example programs exist to reverse-engineer from:
  - FBOSS's 22-byte `02 3F 12 C0 F8 15 67 0D 90 75 02 3A C0 21 87 99 21 87 99 21 87 57`
    (`fboss/agent/platforms/wedge/wedge100/wedge100_led.asm` — source form
    commented but not opcode-level)
  - The stock BCM-SDK program plus patched LEDUP1 variant in
    `led_proc_init.soc` (pre-cutover — in git history)
- AS7712 uses the same engine with a different bytecode — could diff to
  isolate opcodes.
- The scan-chain wire order on wedge100s (3 bits per port × 64 ports =
  192 bits) is fixed by the 74LV164 chain routing; any new encoding has
  to respect that physical layout.

## Candidate approaches

1. **Per-port 4-or-more-bit encoding** — use DATA_RAM bits 3..7 to
   select from a larger color table at the scan-chain assembly stage.
   Needs new bytecode that reads the extra bits and maps to a 4-channel
   (RGB + enable) or similar output. Ideal.
2. **Dual-byte per port** — write 2 bytes per LED instead of 1, use
   more bits. Requires re-wiring the scan chain offsets.
3. **CPLD-side pre-programmed palette** — if we can program the CPLD
   test color table we might be able to encode richer colors via the
   existing 3-bit path. Requires CPLD documentation.
4. **Pragmatic expansion** — stop fighting the 3-bit limit. Use two
   arrows per port differently (L = speed bucket, R = fine-grained
   distinction). E.g. L-cyan + R-cyan = 10G, L-cyan + R-magenta = 25G,
   etc. Fits within current bytecode, abandons the one-color-per-cage
   simplification. Doable today but ugly.

## Priority

**Not urgent.** The current Phase-3 daemon handles all five operational
states (admin-down / pending / <40G / 40-100G / 100G) with readable,
distinct colors. This TODO is about fidelity and UX polish, not
correctness.

Revisit when:
- Somebody finds/reverses a Broadcom LEDASM opcode reference, or
- Phase-4 budget is available for multi-day bytecode work, or
- A real user complaint surfaces about 10G-vs-25G ambiguity (currently
  theoretical).

## Related code

- Daemon + color policy: `tools/wedge100s-fboss-ledup-linkstate.py`
  (devel) and `platform/.../utils/wedge100s-ledup-linkstate` (platform
  fork; both kept in lockstep).
- Bytecode load: `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc`
  (on the platform fork).
- Mapping + observations: `notes/2026-04-21-fboss-led-mapping.md`.
