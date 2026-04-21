#!/bin/bash
# wedge100s-fboss-led-test.sh
#
# Front-panel LED test for Wedge 100S running SONiC with the FBOSS LED
# microcode. Runs a cascading color wave that starts at cages 1 and 32
# and propagates inward, meeting at cages 16-17 and continuing through
# the palette indefinitely.
#
# Ctrl-C halts the animation and resets DATA_RAM to 0x00 on both LEDUP
# engines. With DATA_RAM=0, the HW-populated link-status bytes at
# DATA_RAM[0..63] drive the default "link-up pink" display — the
# authoritative link-state daemon (TODO) will override this with real
# per-port colors.
#
# Requires:
#   - SONiC running, syncd container up
#   - FBOSS 22-byte bytecode loaded on CMIC_LEDUP0 and CMIC_LEDUP1
#     (script auto-loads if PROGRAM_RAM[0] != 0x02)
#
# Address map verified against physical panel 2026-04-21 via
# cage-by-cage red-on-green + 4-color pattern walks.

set -u

BCMCMD="sudo docker exec syncd bcmcmd"

# 22-byte FBOSS bytecode (from fboss/agent/platforms/common/utils/Wedge100LedUtils.cpp).
# Reads per-LED color bytes from DATA_RAM[192..223] (ADDR_SW_PORTS=0xc0).
FBOSS_BYTECODE="023F12C0F815670D9075023AC021879921879921 8757"

# Per-cage DATA_RAM address map (1-indexed by cage number).
# LEDUP0 drives cages 1-12 + 29-32; LEDUP1 drives cages 13-28.
# L = left arrow (LU for upper cages, LD for lower); R = right arrow.
# Cage number:          1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20  21  22  23  24  25  26  27  28  29  30  31  32
L_ENG=(  ""             0   0   0   0   0   0   0   0   0   0   0   0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0   0   0   0 )
R_ENG=(  ""             0   0   0   0   0   0   0   0   0   0   0   0   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   1   0   0   0   0 )
L_ADDR=( ""           216 217 221 220 192 193 197 196 200 201 205 204 192 193 197 196 200 201 205 204 208 209 213 212 216 217 221 220 208 209 213 212 )
R_ADDR=( ""           218 219 222 223 194 195 198 199 202 203 206 207 194 195 198 199 202 203 206 207 210 211 215 214 218 219 222 223 210 211 215 214 )

# 7-color palette (values → colors; 0x00 = OFF; see memory palette notes).
PALETTE=( 0x01 0x02 0x03 0x04 0x05 0x06 0x07 )
P_LEN=${#PALETTE[@]}

HOLD_SEC="${HOLD_SEC:-0.3}"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

ensure_fboss_bytecode() {
  local first
  first=$($BCMCMD "getreg CMIC_LEDUP0_PROGRAM_RAM[0]" 2>&1 | grep -oE 'DATA=0x?[0-9a-fA-F]+' | head -1)
  if [ "$first" != "DATA=2" ] && [ "$first" != "DATA=0x2" ]; then
    log "FBOSS bytecode not loaded (LEDUP0_PROGRAM_RAM[0]=$first); loading..."
    for n in 0 1; do
      $BCMCMD "led $n stop"   >/dev/null 2>&1
      $BCMCMD "led $n prog $FBOSS_BYTECODE" >/dev/null 2>&1
      $BCMCMD "led $n start"  >/dev/null 2>&1
    done
  fi
}

# Batch a frame's worth of setreg commands through one bcmcmd invocation
# via rcload (avoids 60+ docker exec calls per frame).
apply_frame() {
  local commands="$1"
  # Write commands into the syncd container's /tmp, then rcload.
  sudo docker exec -i syncd sh -c 'cat > /tmp/wedge_led_frame.rc && bcmcmd "rcload /tmp/wedge_led_frame.rc" >/dev/null 2>&1' <<EOF
$commands
EOF
}

reset_panel() {
  echo ""
  log "Ctrl-C — resetting LEDs to default state (DATA_RAM=0x00)..."
  local cmds=""
  for a in $(seq 192 223); do
    cmds+="setreg CMIC_LEDUP0_DATA_RAM[$a] 0x00"$'\n'
    cmds+="setreg CMIC_LEDUP1_DATA_RAM[$a] 0x00"$'\n'
  done
  cmds+="setreg CMIC_LEDUP0_CTRL 0x2a8"$'\n'
  cmds+="setreg CMIC_LEDUP0_CTRL 0x2a9"$'\n'
  cmds+="setreg CMIC_LEDUP1_CTRL 0x1e8"$'\n'
  cmds+="setreg CMIC_LEDUP1_CTRL 0x1e9"$'\n'
  apply_frame "$cmds"
  log "LEDs reset. (Link-state daemon TODO will own the functional color mapping.)"
  exit 0
}
trap reset_panel INT TERM

ensure_fboss_bytecode

log "Cascading color wave (cages 1 and 32 inward). Ctrl-C to halt."

t=0
while true; do
  frame=""
  for cage in $(seq 1 32); do
    if [ "$cage" -le 16 ]; then
      dist=$(( cage - 1 ))
    else
      dist=$(( 32 - cage ))
    fi
    idx=$(( (t + dist) % P_LEN ))
    color=${PALETTE[$idx]}
    leng=${L_ENG[$cage]}
    reng=${R_ENG[$cage]}
    laddr=${L_ADDR[$cage]}
    raddr=${R_ADDR[$cage]}
    frame+="setreg CMIC_LEDUP${leng}_DATA_RAM[$laddr] $color"$'\n'
    frame+="setreg CMIC_LEDUP${reng}_DATA_RAM[$raddr] $color"$'\n'
  done
  frame+="setreg CMIC_LEDUP0_CTRL 0x2a8"$'\n'
  frame+="setreg CMIC_LEDUP0_CTRL 0x2a9"$'\n'
  frame+="setreg CMIC_LEDUP1_CTRL 0x1e8"$'\n'
  frame+="setreg CMIC_LEDUP1_CTRL 0x1e9"$'\n'
  apply_frame "$frame"
  sleep "$HOLD_SEC"
  t=$(( t + 1 ))
done
