# FBOSS Wedge100 LED bytecode — semantics

Sources: facebook/fboss main branch, commit of 2026-04-21 fetch.

## 1. The asm source (complete)

```asm
; Wedge100 LED microprocessor assembly.
; See the Tomahawk Theory of Operations document.
ADDR_SW_PORTS equ 0xc0
START_PORT    equ 63

update:
    ld a, START_PORT
loop_start:
    ld b, ADDR_SW_PORTS
    add b, a
    ld b, (b)        ; b = DATA_RAM[0xc0 + port]
    call set_led
    dec a
    jnc loop_start
    send 192         ; 64 * 3 bits

set_led:
    push b           ; LSB (Red)    -> bitstream
    pack
    ror b
    push b           ; bit1 (Green)
    pack
    ror b
    push b           ; bit2 (Blue)
    pack
    ret
```

Only **bits 0..2** of DATA_RAM[0xc0+N] are ever read. Bits 3..7 are ignored.
LSB is Red, bit1 Green, bit2 Blue. The LEDUP streams exactly 3 bits per port × 64 ports.

## 2. Wedge100LedUtils color enum (from .h)

```
OFF     = 0b000   // 0x00
BLUE    = 0b001   // bit0 set, but maps to Red if low bit is red...
GREEN   = 0b010
CYAN    = 0b011
RED     = 0b100
MAGENTA = 0b101
YELLOW  = 0b110
WHITE   = 0b111
```

Note: the enum names don't match the "LSB=red" asm comment — FBOSS's enum
treats bit0 as **blue** in the enum names (so BLUE=0b001). On wedge100s the
CPLD's color-channel wiring ultimately determines what the human sees; the
asm just routes 3 bits to the shift register.

## 3. Observed-on-hardware vs. expected

Bytecode reads **only bits [2:0]**. Any high-nibble poke (0x0f, 0xf0, 0x88,
0xff) is masked off by the asm *for the purposes of what the code sends*.
So:
- `0x0f` single-port dark and `0xf0` single-port dark **is not explained by
  the asm** — the bytecode only cares about the low 3 bits. 0x0f → low 3
  bits = 0b111 = WHITE (all colors on). Dark observation means something
  else is happening (flooding 0x0f gave "dim pink" which matches WHITE
  fading into pink fallback).
- `0x00` → 0b000 → all three shift bits zero → LED should be fully off.
  Observed pink is **not** produced by the asm — the asm loads `(b)` from
  `DATA_RAM[0xc0+port]` directly, never ORing anything from `DATA_RAM[0..63]`.

So the "pink on 0x00" fallback is **NOT** from explicit bytecode logic. It
must be coming from one of:
1. A **default LEDUP hardware pattern** the BCM SDK loads when no override
   is active (the LEDUP has "HW link status" bits in `DATA_RAM[0..63]`
   *independent* of the bytecode — they're used by other default microcode
   variants, not this one, but the CMIC may feed them into the output
   multiplexer / CPLD panel when the bytecode isn't actively driving).
2. A **CPLD-level default** on wedge100s where the CPLD itself drives a
   fallback color when the LEDUP bitstream is idle/zero.
3. The FBOSS bytecode never runs `send` on startup until the first full
   loop, and the panel latches whatever the CPLD was doing before the
   override.

## 4. Init sequence — what FBOSS does around the bytecode

`Wedge100Platform::onHwInitialized()` calls `enableLedMode()` which calls
`Wedge100LedUtils::enableLedMode()` (body not in the file we inspected —
likely in a .cpp we didn't pull; from platform conventions it pokes CPLD
scratch registers to route LEDUP → panel).

The bytecode itself contains **no init** — no clearing of DATA_RAM before
the loop. So at first run, DATA_RAM[0xc0..0xff] contains whatever the BCM
SDK left after microcode load (typically zero-filled by `bcm_led_control_set`).

`defaultLedCode()` returns the same 22 bytes we have, padded to 256 bytes
of zeros. The 256-byte load writes the full LEDUP INSTR_RAM.

## 5. The actual "LED OFF" byte

**`0x00`** is the correct "LED OFF" byte per the bytecode semantics (all
three color bits = 0 → no color sent on the wire).

If `0x00` is producing pink on our wedge100s, the problem is **not** in the
byte value — it's that **the bytecode isn't driving the panel**, or is
being overridden by the CPLD/LEDUP-HW pattern. Confirmation path:

1. Verify the bytecode is actually loaded into INSTR_RAM and the LEDUP is
   enabled (`LEDUP_CTRL.LEDUP_EN = 1`).
2. Verify the BCM SDK isn't running its own default LED customer handler
   on top of our override.
3. Check the CPLD's LED mux — wedge100s CPLD has a "BMC owns LEDs" vs
   "CPU/LEDUP owns LEDs" bit that may not be flipped to LEDUP.

## 6. Broadcom LEDUP opcode reference — NOT publicly available

WebSearch confirms: no public Broadcom docs describe `pack`/`ror`/`send`/
`push`/`ld`/`jnc` mnemonics at the byte level. The ledasm tool is part of
Broadcom's restricted SDK. Best public reference is the asm file itself
plus inspection of the OpenNSL/BCM-SDK examples in the SAI vendor
attachments — which we don't have.

Decoding 22 bytes by hand from the mnemonics:
- `0x02 0x3F` → `ld a, 63`      (START_PORT)
- `0x12 0xC0` → `ld b, 0xc0`    (ADDR_SW_PORTS)
- `0xF8`      → `add b, a`
- `0x15 0x67` → `ld b, (b)`     (indirect)
- `0x0D`      → `call set_led`
- `0x90`      → `dec a`
- `0x75 0x02` → `jnc loop_start` (relative +02? unclear)
- `0x3A 0xC0` → `send 192`
- `0x21 0x87` → `push b; pack`  (pair appears 3×)
- `0x99`      → `ror b`
- `0x57`      → `ret`

(Byte-to-mnemonic mapping is my best reconstruction from count-matching;
not authoritative.)
