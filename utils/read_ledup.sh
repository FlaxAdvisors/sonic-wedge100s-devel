#!/bin/bash
# read_ledup.sh — dump BCM LEDUP DATA_RAM per-port status bytes via bcmcmd
# Run on SONiC target.  Requires syncd container running.
#
# Usage:
#   read_ledup.sh              # summary: LEDUP0[0..31] + LEDUP1[64..95]
#   read_ledup.sh --data 0     # raw dump LEDUP0 DATA_RAM[0..31]
#   read_ledup.sh --data 1     # raw dump LEDUP1 DATA_RAM[0..31] (BCM SDK zone)
#   read_ledup.sh --safe       # dump LEDUP1 DATA_RAM[64..95] (daemon safe zone)
#   read_ledup.sh --patch      # check LEDUP1 bytecode patch status
#
# Bit layout per DATA_RAM entry:
#   7: Link Up    6: Flow Control   5: Full Duplex
#   4:3: Speed (00=10M, 01=100M, 10=1G, 11=10G+)
#   2: Collision  1: TX activity    0: RX activity

set -e

bcm() {
    docker exec syncd bcmcmd "$1" 2>/dev/null
}

decode_flags() {
    local dec=$1
    if [ "$dec" -eq 0 ]; then echo "(dark)"; return; fi
    local flags=""
    [ $((dec & 0x80)) -ne 0 ] && flags="${flags}Link "
    [ $((dec & 0x40)) -ne 0 ] && flags="${flags}FC "
    [ $((dec & 0x20)) -ne 0 ] && flags="${flags}FD "
    local spd=$(( (dec >> 3) & 3 ))
    case $spd in
        0) flags="${flags}10M " ;;
        1) flags="${flags}100M " ;;
        2) flags="${flags}1G " ;;
        3) flags="${flags}10G+ " ;;
    esac
    [ $((dec & 0x04)) -ne 0 ] && flags="${flags}Col "
    [ $((dec & 0x02)) -ne 0 ] && flags="${flags}TX "
    [ $((dec & 0x01)) -ne 0 ] && flags="${flags}RX "
    echo "$flags"
}

# LED_port → SONiC interface
iface_for() {
    case $1 in
        0) echo "Ethernet20" ;;  1) echo "Ethernet16" ;;
        2) echo "Ethernet28" ;;  3) echo "Ethernet24" ;;
        4) echo "Ethernet36" ;;  5) echo "Ethernet32" ;;
        6) echo "Ethernet44" ;;  7) echo "Ethernet40" ;;
        8) echo "Ethernet52" ;;  9) echo "Ethernet48" ;;
       10) echo "Ethernet60" ;; 11) echo "Ethernet56" ;;
       12) echo "Ethernet68" ;; 13) echo "Ethernet64" ;;
       14) echo "Ethernet76" ;; 15) echo "Ethernet72" ;;
       16) echo "Ethernet84" ;; 17) echo "Ethernet80" ;;
       18) echo "Ethernet92" ;; 19) echo "Ethernet88" ;;
       20) echo "Ethernet100";; 21) echo "Ethernet96" ;;
       22) echo "Ethernet108";; 23) echo "Ethernet104";;
       24) echo "Ethernet116";; 25) echo "Ethernet112";;
       26) echo "Ethernet124";; 27) echo "Ethernet120";;
       28) echo "Ethernet4"  ;; 29) echo "Ethernet0"  ;;
       30) echo "Ethernet12" ;; 31) echo "Ethernet8"  ;;
        *) echo "" ;;
    esac
}

dump_data() {
    local proc=$1 start=$2 end=$3 label=$4
    echo "=== LEDUP${proc} DATA_RAM[${start}..$(( end - 1 ))]${label} ==="
    printf "%-6s %-14s %-6s %s\n" "Entry" "Interface" "Value" "Flags"
    for (( i=start; i<end; i++ )); do
        local out
        out=$(bcm "getreg CMIC_LEDUP${proc}_DATA_RAM(${i})")
        local val
        val=$(echo "$out" | grep -oP 'DATA=0x[0-9a-fA-F]+' | head -1 | cut -d= -f2)
        [ -z "$val" ] && val="0x00"
        local dec=$((val))
        local led_port=$i
        [ $i -ge 64 ] && led_port=$((i - 64))
        local iface
        iface=$(iface_for $led_port)
        printf "[%-3d]  %-14s %-6s %s\n" "$i" "$iface" "$val" "$(decode_flags $dec)"
    done
    echo ""
}

check_patch() {
    echo "=== LEDUP1 Bytecode Patch Status ==="
    local b14 b15
    b14=$(bcm "getreg CMIC_LEDUP1_PROGRAM_RAM(20)" | grep -oP 'DATA=0x[0-9a-fA-F]+' | cut -d= -f2)
    b15=$(bcm "getreg CMIC_LEDUP1_PROGRAM_RAM(21)" | grep -oP 'DATA=0x[0-9a-fA-F]+' | cut -d= -f2)
    echo "  PROG[0x14] = ${b14:-??}  (expect 0x77 = JMP)"
    echo "  PROG[0x15] = ${b15:-??}  (expect 0xf0 = target)"

    local patch=""
    for (( i=240; i<250; i++ )); do
        local v
        v=$(bcm "getreg CMIC_LEDUP1_PROGRAM_RAM(${i})" | grep -oP 'DATA=0x[0-9a-fA-F]+' | cut -d= -f2)
        patch="${patch} ${v:-??}"
    done
    echo "  PROG[0xF0..0xF9] =${patch}"
    echo "  Expected:          0x02 0xf9 0x0a 0x40 0x12 0xfc 0x06 0xfc 0x77 0x16"
    echo ""
}

summary() {
    echo "=== LED State Summary ==="
    printf "%-14s  %-8s  %-8s  %s\n" "Interface" "LEDUP0" "LEDUP1+64" "LED Color"
    for (( lp=0; lp<32; lp++ )); do
        local iface v0_raw v1_raw v0 v1
        iface=$(iface_for $lp)
        v0_raw=$(bcm "getreg CMIC_LEDUP0_DATA_RAM(${lp})" | grep -oP 'DATA=0x[0-9a-fA-F]+' | cut -d= -f2)
        v1_raw=$(bcm "getreg CMIC_LEDUP1_DATA_RAM($((lp + 64)))" | grep -oP 'DATA=0x[0-9a-fA-F]+' | cut -d= -f2)
        v0=$(( ${v0_raw:-0} ))
        v1=$(( ${v1_raw:-0} ))
        local blue=$(( v0 & 0x80 )) orange=$(( v1 & 0x80 ))
        local color
        if [ $blue -ne 0 ] && [ $orange -ne 0 ]; then color="MAGENTA (up)"
        elif [ $blue -ne 0 ]; then color="BLUE (down)"
        elif [ $orange -ne 0 ]; then color="ORANGE (anomaly!)"
        else color="OFF"
        fi
        printf "%-14s  %-8s  %-8s  %s\n" "$iface" "${v0_raw:-??}" "${v1_raw:-??}" "$color"
    done
    echo ""
}

# --- main ---
case "${1:-}" in
    --data)
        dump_data "${2:-0}" 0 32 ""
        ;;
    --safe)
        dump_data 1 64 96 " (daemon safe zone)"
        ;;
    --patch)
        check_patch
        ;;
    --all)
        check_patch
        dump_data 0 0 32 ""
        dump_data 1 0 32 " (BCM SDK zone)"
        dump_data 1 64 96 " (daemon safe zone)"
        summary
        ;;
    "")
        summary
        ;;
    *)
        echo "Usage: $0 [--data N | --safe | --patch | --all]"
        exit 1
        ;;
esac
