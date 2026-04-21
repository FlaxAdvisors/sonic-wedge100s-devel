# Wedge 100S Front-Panel LED — FBOSS bytecode mapping (2026-04-21)

Verified end-to-end address map from DATA_RAM bytes to physical front-panel
LEDs under the **FBOSS 22-byte LED bytecode**. This is the per-LED 8-color
mapping that the next-generation link-state daemon will use.

**Hardware verified on lapin 2026-04-21** via three complementary tests:
palette-cycling walk → red-on-green cage-by-cage walk → 4-color-per-cage
pattern walk (LU/LD/RU/RD distinguished).

## Scope

This document captures the **FBOSS-bytecode** mapping only. The current
production config (`led_proc_init.soc` on the platform fork) loads the stock
BCM SDK bytecode on LEDUP0 and a patched version on LEDUP1, implementing a
"two parallel color channels, OR'd per port" model (see
`notes/front-panel-leds-still-boinked.md`). That model is **not** what this
document describes. The FBOSS bytecode replaces both engines' programs with
a 22-byte program that reads per-LED color bytes from `DATA_RAM[192..223]`
and drives each physical LED with one of 8 colors independently.

Use `tools/wedge100s-fboss-led-test.sh` to load the FBOSS bytecode at
runtime and exercise all 64 LEDs.

## Architecture (under FBOSS bytecode)

- **Two LEDUP engines drive the 64 LEDs**, bank-split:
  - LEDUP0 owns cages 1-12 + 29-32 (32 LEDs)
  - LEDUP1 owns cages 13-28 (32 LEDs)
  - LEDUP2 exists in silicon but is physically unwired on this board.
- **Each LED gets one byte** in its engine's `DATA_RAM[192..223]`.
- **8 colors per LED** (`0x00..0x07`):
  - `0x00` = OFF (intent; HW link-status bytes at `DATA_RAM[0..63]` may bleed through producing pink — see "quirks" below)
  - `0x01` = cyan
  - `0x02` = yellow/orange
  - `0x03` = green
  - `0x04` = magenta
  - `0x05` = purple
  - `0x06` = red
  - `0x07` = dim pink (renders OFF on some edge LEDs)
- **Port cage has 2 LEDs**: L (left arrow) and R (right arrow). For the
  upper cage of a pair these are LU/RU; for the lower cage they are LD/RD.
  All four LEDs of a cage-pair sit at the same physical vertical level,
  arrayed L,L,R,R left-to-right.

## Canonical 64-LED address map

Engine 0 = LEDUP0, engine 1 = LEDUP1. Addresses are DATA_RAM byte indices.

| cage | engine | L addr | R addr | cage | engine | L addr | R addr |
|---:|:-:|---:|---:|---:|:-:|---:|---:|
|  1 | 0 | 216 | 218 | 17 | 1 | 200 | 202 |
|  2 | 0 | 217 | 219 | 18 | 1 | 201 | 203 |
|  3 | 0 | 221 | 222 | 19 | 1 | 205 | 206 |
|  4 | 0 | 220 | 223 | 20 | 1 | 204 | 207 |
|  5 | 0 | 192 | 194 | 21 | 1 | 208 | 210 |
|  6 | 0 | 193 | 195 | 22 | 1 | 209 | 211 |
|  7 | 0 | 197 | 198 | 23 | 1 | 213 | 215 |
|  8 | 0 | 196 | 199 | 24 | 1 | 212 | 214 |
|  9 | 0 | 200 | 202 | 25 | 1 | 216 | 218 |
| 10 | 0 | 201 | 203 | 26 | 1 | 217 | 219 |
| 11 | 0 | 205 | 206 | 27 | 1 | 221 | 222 |
| 12 | 0 | 204 | 207 | 28 | 1 | 220 | 223 |
| 13 | 1 | 192 | 194 | 29 | 0 | 208 | 210 |
| 14 | 1 | 193 | 195 | 30 | 0 | 209 | 211 |
| 15 | 1 | 197 | 198 | 31 | 0 | 213 | 215 |
| 16 | 1 | 196 | 199 | 32 | 0 | 212 | 214 |

## Within-block offset patterns

Each cage-pair occupies a 4-byte block in DATA_RAM. Within each block, the
offsets for (LU, LD, RU, RD) depend on the block's DATA_RAM index (0-7
where block N starts at addr 192 + 4*N):

| block | addrs        | (LU,LD,RU,RD) offsets | LEDUP0 cage-pair | LEDUP1 cage-pair |
|:-:|:------------:|:-:|:-:|:-:|
| 0 | [192..195]   | (0,1,2,3)           | 5-6   | 13-14 |
| 1 | [196..199]   | (1,0,2,3)           | 7-8   | 15-16 |
| 2 | [200..203]   | (0,1,2,3)           | 9-10  | 17-18 |
| 3 | [204..207]   | (1,0,2,3)           | 11-12 | 19-20 |
| 4 | [208..211]   | (0,1,2,3)           | 29-30 | 21-22 |
| 5 | [212..215]   | **(1,0,3,2)**       | 31-32 | 23-24 |
| 6 | [216..219]   | (0,1,2,3)           | 1-2   | 25-26 |
| 7 | [220..223]   | (1,0,2,3)           | 3-4   | 27-28 |

**Clean rule**: even blocks get `(0,1,2,3)`, odd blocks get `(1,0,2,3)`,
except **block 5 gets `(1,0,3,2)`** — an RU/RD swap visible on both engines.
That anomaly is a property of the 5th 24-bit shift-register segment on the
CPLD, not of any specific cage.

## Block-to-cage-pair assignment

**LEDUP1 is sequential** — cage-pairs 13-14, 15-16, ..., 27-28 map to blocks
0, 1, ..., 7 in order.

**LEDUP0 is scrambled** — because its 16 cages split between the panel's
left edge (1-12) and right edge (29-32), and the scan chain visits them in
PCB-routing order, not cage-number order:

| LEDUP0 scan block | cage-pair |
|:-:|:-:|
| 0 | 5-6   |
| 1 | 7-8   |
| 2 | 9-10  |
| 3 | 11-12 |
| 4 | 29-30 |
| 5 | 31-32 |
| 6 | 1-2   |
| 7 | 3-4   |

## Physical LED defects (cataloged)

Per-LED hardware issues on this specific lapin unit. Not to be treated as
bugs in the daemon — these are manufacturing variance:

| LED | defect | behavior |
|:-:|:-:|:-:|
| C4-R (RD) | **fully defective** | Red channel only. Byte `0x03` (green) shows dim red. All byte values appear red-ish or off. |
| C5-L (LU) | blue-weak | `0x01` cyan → green; `0x04` magenta → red. Non-blue bytes (2, 3, 6) render normally. |
| C23-R | blue-weak | same pattern. |
| C24-L | blue-weak | same pattern. |
| C29-L, C31-L | blue-weak | `0x01` → green. |
| C30-R, C32-R | blue-weak | `0x04` → red. |

The daemon should either (a) avoid byte values that require blue on these
specific LEDs, or (b) accept the discolored rendering and document.

## Other quirks

- **`DATA_RAM[0..63]` is hardware-populated** with link-status bytes by the
  BCM MAC/SERDES and can't be cleared via `setreg` (values snap back). FBOSS
  bytecode reads color bytes from `[192..255]` and is supposed to ignore
  `[0..63]`, but when color-byte is `0x00` the default link-up pink shows
  through — appears the bytecode falls back to link-status rendering on OFF.
  To force a LED off via the ASIC, write any non-zero "dim" value (0x07) or
  disable the engine entirely.
- **`LEDUP_RUNNING` bit in STATUS is a sticky latch** — never clears on
  `EN=0` or `led N stop`. Use `CTRL.LEDUP_EN` as source of truth.
- **`PORT_ORDER_REMAP` is identical on both engines** — simple pair-swap
  `[1,0,3,2,5,4,...,31,30]` for positions 0-31, positions 32-63 → index 63
  (unused). Programmed by `led_proc_init.soc` at syncd startup. FBOSS
  bytecode uses this REMAP as-is; no REMAP changes needed to transition.
- **LEDUP2 exists but is unwired** on this PCB. Don't try to use it.

## Methodology summary

1. **Cold-boot baseline observed** — panel lands in stock "all dim pink"
   (with per-LED defects visible).
2. **FBOSS 22-byte bytecode loaded** via `led N prog <hex>` — replaces the
   stock bytecode on both engines at runtime.
3. **Palette walk**: flood `DATA_RAM[192..223]` with cycling 1..7, user
   walks the panel, identifying the color at each physical LED in
   left-to-right order. Decoded 60% of the map; the other 40% was
   ambiguous due to two blocks holding the same byte-value set.
4. **Red-on-green cage walk**: turn all LEDs green, then for each cage N
   (1..32) overwrite its two expected addresses with red. User identifies
   which physical cage lit red. This disambiguated block-to-cage assignment
   but not within-pair L/R.
5. **4-color-per-pair walk**: light pair's LU=cyan, LD=yellow, RU=green,
   RD=red simultaneously. 4 distinct colors lets user identify each LED's
   physical position by color. This disambiguated within-pair L/R ordering.
6. **Full 16-pair loop with LU=yellow, LD=green, RU=purple, RD=magenta
   against cyan background** — visual confirmation of the entire map with
   no ambiguity.

Verification bytes and test scripts live in `tools/wedge100s-fboss-led-test.sh`.

## Staged migration to FBOSS daemon

This mapping is captured now but is **not yet wired into SONiC production**.
The migration plan:

1. ✅ **Phase 1 — test tool** (this commit): Ship
   `tools/wedge100s-fboss-led-test.sh` that auto-loads FBOSS bytecode and
   runs a cascading visual test. Doesn't touch production config.
2. **Phase 2 — new daemon**: Write `wedge100s-fboss-ledup-linkstate` (new
   name, runs alongside the current `wedge100s-ledup-linkstate` during
   transition) that writes to `DATA_RAM[192..223]` using the 64-entry map
   above. Daemon reads link-state from STATE_DB and writes per-LED colors.
3. **Phase 3 — cutover**: Update
   `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc` on the
   platform fork to load FBOSS bytecode instead of the stock/patched BCM
   bytecode. Same commit retires the old daemon + removes the
   `DATA_RAM[64..95]` safe-zone init. This is a wedge100s topic-branch
   change (`wedge100s/led-fboss-cutover`).

Do not do Phase 3 until Phase 2 is ready. Old daemon + new bytecode =
LEDs dark on link-up.

## References

- `tools/wedge100s-fboss-led-test.sh` — test tool that loads FBOSS bytecode
  at runtime and runs the cascading wave animation.
- `notes/front-panel-leds-still-boinked.md` — prior decode of the
  two-color-channel model (still authoritative for current production).
- FBOSS source: `fboss/agent/platforms/common/utils/Wedge100LedUtils.cpp`
  (22-byte bytecode) and `fboss/agent/platforms/wedge/wedge100/wedge100_led.asm`
  (asm source; `ADDR_SW_PORTS=0xc0`, `START_PORT=63`).
- Platform config: `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc`
  (on `play-sonic:/export/sonic/sonic-buildimage`).
