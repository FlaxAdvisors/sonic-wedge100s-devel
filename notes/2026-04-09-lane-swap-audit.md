# QSFP Lane-Swap and Polarity-Flip Audit (GAP-003)

**Date:** 2026-04-09
**Scope:** Static cross-reference of OCP Wedge100S spec v1.3 Table 10 against
`device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm`
(read from worktree `/export/sonic/worktrees/wedge100s-chipset-config`).

**Verification status:** Static audit only. **No PRBS verification has been
performed on hardware.** No BCM config changes should be applied based on
this audit alone — all mismatches must be confirmed with PRBS31 loopback
tests before the config is touched. See
`tests/stage_03_platform/test_lane_swap_audit.py` for the gated runtime
harness.

## 1. Sources

| Source | Path |
|---|---|
| OCP spec PDF | `misc/Wedge100S_OCP_Spec_v1_3.pdf` Table 10 (pages 25–38) |
| BCM config   | `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm` |
| SONiC port map | `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc` lines 12–44 |

## 2. Notation and conventions

### 2.1 OCP Table 10 — PCB routing

Table 10 lists, for each QSFP cage, which ASIC serdes (Tomahawk FCn block,
4 lanes per block) routes to which QSFP MSA channel (CH-1..CH-4). Where the
PCB routing is non-identity, the table annotates the affected RX or TX
block with **"QSFP CHANNELS SWAPPED WITH IN THE QUAD"**. The annotation is
applied independently per direction (some ports have RX only, TX only, or
both).

The observed phy→CH permutations in the spec fall into four categories:

| Pattern             | Phy lane 0..3 → CH | Interpretation                  |
|---------------------|--------------------|---------------------------------|
| Identity            | 1, 2, 3, 4         | No correction needed            |
| Upper/lower (A)     | 3, 4, 1, 2         | CH 1↔3, 2↔4 (common Accton fix) |
| Pair (B)            | 2, 1, 4, 3         | CH 1↔2, 3↔4                     |
| Full reverse (C)    | 4, 3, 2, 1         | CH 1↔4, 2↔3                     |
| Unusual 4-way (D)   | 4, 2, 3, 1         | CH 1↔4 only                     |

Categories B/C/D appear on only a handful of ports; A is the most common.

### 2.2 BCM `xgxs_{rx,tx}_lane_map` semantics

Each setting is a 4-nibble hex value applied at the master port (first
serdes lane of each QSFP). The Broadcom documentation and Accton reference
configs are ambiguous about whether each nibble is "source phy lane for MAC
lane i" or "destination MAC lane for phy lane i" — the two interpretations
are inverses and both appear in the wild. **For this audit we therefore
classify match/mismatch structurally** (identity vs. non-identity) rather
than trying to verify that a specific hex value exactly matches a specific
permutation.

- **Structural MATCH**: OCP annotation absent ⇔ BCM map is `0x3210`
- **Structural MATCH**: OCP annotation present ⇔ BCM map is non-`0x3210`
- **Structural MISMATCH**: the two directions disagree

This means:
- A port where OCP says "no swap" and BCM has `0x3210` is MATCH.
- A port where OCP says "swap" and BCM has e.g. `0x1032` or `0x2301` is
  **structural MATCH but hex-value UNVERIFIED** — the specific permutation
  needs PRBS confirmation.
- A port where OCP says "swap" and BCM has `0x3210` is a **HIGH-confidence
  MISMATCH** regardless of nibble interpretation.
- A port where OCP says "no swap" and BCM has a non-identity map is a
  **HIGH-confidence MISMATCH** regardless of nibble interpretation.

### 2.3 `phy_xaui_rx_polarity_flip` / `phy_xaui_tx_polarity_flip`

**Finding:** These keys do not appear anywhere in the current
`th-wedge100s-32x-flex.config.bcm`. The BCM SDK default is "no flip" on all
lanes. The OCP spec Table 10 does **not** document per-lane polarity
inversion either (it only marks whole-quad channel swaps; N/P ordering is
consistent within each row). Therefore there is no static-audit mismatch
to report for polarity flip — the BCM default and the OCP spec agree by
omission. PRBS will still catch any undocumented polarity issues at
runtime.

### 2.4 Physical-port → FC block → first-serdes-lane mapping

The Tomahawk "physical port" number (left column of every `portmap_N.0=`
line RHS) equals the first serdes lane of the port. FC blocks are
numbered 0..31 and own serdes lanes `4*FC+1 .. 4*FC+4`.

| Phys QSFP | FC block | First serdes | BCM port (master) | SONiC iface |
|-----------|----------|--------------|-------------------|-------------|
| QSFP0     | FC29     | 117          | 118               | Ethernet0   |
| QSFP1     | FC28     | 113          | 122               | Ethernet4   |
| QSFP2     | FC31     | 125          | 126               | Ethernet8   |
| QSFP3     | FC30     | 121          | 130               | Ethernet12  |
| QSFP4     | FC1      | 5            | 1                 | Ethernet16  |
| QSFP5     | FC0      | 1            | 5                 | Ethernet20  |
| QSFP6     | FC3      | 13           | 9                 | Ethernet24  |
| QSFP7     | FC2      | 9            | 13                | Ethernet28  |
| QSFP8     | FC5      | 21           | 17                | Ethernet32  |
| QSFP9     | FC4      | 17           | 21                | Ethernet36  |
| QSFP10    | FC7      | 29           | 25                | Ethernet40  |
| QSFP11    | FC6      | 25           | 29                | Ethernet44  |
| QSFP12    | FC9      | 37           | 34                | Ethernet48  |
| QSFP13    | FC8      | 33           | 38                | Ethernet52  |
| QSFP14    | FC11     | 45           | 42                | Ethernet56  |
| QSFP15    | FC10     | 41           | 46                | Ethernet60  |
| QSFP16    | FC13     | 53           | 50                | Ethernet64  |
| QSFP17    | FC12     | 49           | 54                | Ethernet68  |
| QSFP18    | FC15     | 61           | 58                | Ethernet72  |
| QSFP19    | FC14     | 57           | 62                | Ethernet76  |
| QSFP20    | FC17     | 69           | 68                | Ethernet80  |
| QSFP21    | FC16     | 65           | 72                | Ethernet84  |
| QSFP22    | FC19     | 77           | 76                | Ethernet88  |
| QSFP23    | FC18     | 73           | 80                | Ethernet92  |
| QSFP24    | FC21     | 85           | 84                | Ethernet96  |
| QSFP25    | FC20     | 81           | 88                | Ethernet100 |
| QSFP26    | FC23     | 93           | 92                | Ethernet104 |
| QSFP27    | FC22     | 89           | 96                | Ethernet108 |
| QSFP28    | FC25     | 101          | 102               | Ethernet112 |
| QSFP29    | FC24     | 97           | 106               | Ethernet116 |
| QSFP30    | FC27     | 109          | 110               | Ethernet120 |
| QSFP31    | FC26     | 105          | 114               | Ethernet124 |

(Derived from `portmap_*.0=<first_serdes>:100` lines and the
`led_proc_init.soc` comment block.)

## 3. Per-port audit table (32 rows)

OCP "swap?" columns are taken from the phy-lane → CH ordering in Table 10
data rows, not only the annotation text. `BCM RX/TX` columns show the
master-port `xgxs_{rx,tx}_lane_map_<first_serdes>.0` value.

| Phys | SONiC       | FC   | 1st ln | OCP RX  | OCP TX  | BCM RX | BCM TX | RX verdict | TX verdict |
|------|-------------|------|--------|---------|---------|--------|--------|------------|------------|
| 0    | Ethernet0   | FC29 | 117    | 2,1,4,3 | 1,2,3,4 | 0x3210 | 0x3210 | **MISMATCH (H)** | MATCH |
| 1    | Ethernet4   | FC28 | 113    | 1,2,3,4 | 3,4,1,2 | 0x1032 | 0x3210 | **MISMATCH (H)** | **MISMATCH (H)** |
| 2    | Ethernet8   | FC31 | 125    | 3,4,1,2 | 3,4,1,2 | 0x3210 | 0x1032 | **MISMATCH (H)** | match (struct) |
| 3    | Ethernet12  | FC30 | 121    | 1,2,3,4 | 1,2,3,4 | 0x3210 | 0x3210 | MATCH      | MATCH |
| 4    | Ethernet16  | FC1  | 5      | 1,2,3,4 | 1,2,3,4 | 0x3210 | 0x3210 | MATCH      | MATCH |
| 5    | Ethernet20  | FC0  | 1      | 1,2,3,4 | 1,2,3,4 | 0x3210 | 0x3210 | MATCH      | MATCH |
| 6    | Ethernet24  | FC3  | 13     | 1,2,3,4 | 1,2,3,4 | 0x3210 | 0x3210 | MATCH      | MATCH |
| 7    | Ethernet28  | FC2  | 9      | 1,2,3,4 | 1,2,3,4 | 0x3210 | 0x3210 | MATCH      | MATCH |
| 8    | Ethernet32  | FC5  | 21     | 2,1,4,3 | 3,4,1,2 | 0x1032 | 0x3210 | match (struct) | **MISMATCH (H)** |
| 9    | Ethernet36  | FC4  | 17     | 3,4,1,2 | 1,2,3,4 | 0x2301 | 0x1032 | match (struct) | **MISMATCH (H)** |
| 10   | Ethernet40  | FC7  | 29     | 1,2,3,4 | 3,4,1,2 | 0x1032 | 0x3210 | **MISMATCH (H)** | **MISMATCH (H)** |
| 11   | Ethernet44  | FC6  | 25     | 3,4,1,2 | 1,2,3,4 | 0x3210 | 0x1032 | **MISMATCH (H)** | **MISMATCH (H)** |
| 12   | Ethernet48  | FC9  | 37     | 2,1,4,3 | 3,4,1,2 | 0x1032 | 0x3210 | match (struct) | **MISMATCH (H)** |
| 13   | Ethernet52  | FC8  | 33     | 3,4,1,2 | 1,2,3,4 | 0x2301 | 0x1032 | match (struct) | **MISMATCH (H)** |
| 14   | Ethernet56  | FC11 | 45     | 1,2,3,4 | 3,4,1,2 | 0x3210 | 0x3210 | MATCH | **MISMATCH (H)** |
| 15   | Ethernet60  | FC10 | 41     | 3,4,1,2 | 1,2,3,4 | 0x1032 | 0x3210 | match (struct) | MATCH |
| 16   | Ethernet64  | FC13 | 53     | 3,4,1,2 | 3,4,1,2 | 0x1032 | 0x1032 | match (struct) | match (struct) |
| 17   | Ethernet68  | FC12 | 49     | 3,4,1,2 | 3,4,1,2 | 0x1032 | 0x3210 | match (struct) | **MISMATCH (H)** |
| 18   | Ethernet72  | FC15 | 61     | 3,4,1,2 | 3,4,1,2 | 0x1032 | 0x1032 | match (struct) | match (struct) |
| 19   | Ethernet76  | FC14 | 57     | 3,4,1,2 | 3,4,1,2 | 0x1032 | 0x1032 | match (struct) | match (struct) |
| 20   | Ethernet80  | FC17 | 69     | 3,4,1,2 | 3,4,1,2 | 0x1032 | 0x1032 | match (struct) | match (struct) |
| 21   | Ethernet84  | FC16 | 65     | 1,2,3,4 | 1,2,3,4 | 0x1032 | 0x1032 | **MISMATCH (H)** | **MISMATCH (H)** |
| 22   | Ethernet88  | FC19 | 77     | 4,2,3,1 | 1,2,3,4 | 0x213  | 0x3210 | match (struct, D) | MATCH |
| 23   | Ethernet92  | FC18 | 73     | 3,4,1,2 | 3,4,1,2 | 0x3210 | 0x3210 | **MISMATCH (H)** | **MISMATCH (H)** |
| 24   | Ethernet96  | FC21 | 85     | 4,3,2,1 | 1,2,3,4 | 0x123  | 0x3210 | match (struct, C) | MATCH |
| 25   | Ethernet100 | FC20 | 81     | 1,2,3,4 | 3,4,1,2 | 0x1032 | 0x1032 | **MISMATCH (H)** | match (struct) |
| 26   | Ethernet104 | FC23 | 93     | 3,4,1,2 | 1,2,3,4 | 0x1032 | 0x3210 | match (struct) | MATCH |
| 27   | Ethernet108 | FC22 | 89     | 1,2,3,4 | 3,4,1,2 | 0x3210 | 0x1032 | MATCH | match (struct) |
| 28   | Ethernet112 | FC25 | 101    | 4,3,2,1 | 1,2,3,4 | 0x123  | 0x3210 | match (struct, C) | MATCH |
| 29   | Ethernet116 | FC24 | 97     | 1,2,3,4 | 3,4,1,2 | 0x3210 | 0x1032 | MATCH | match (struct) |
| 30   | Ethernet120 | FC27 | 109    | 3,4,1,2 | 1,2,3,4 | 0x3210 | 0x1032 | **MISMATCH (H)** | **MISMATCH (H)** |
| 31   | Ethernet124 | FC26 | 105    | 1,2,3,4 | 3,4,1,2 | 0x3210 | 0x3210 | MATCH | **MISMATCH (H)** |

### Legend

- **MATCH**: OCP says identity, BCM map is `0x3210`.
- **match (struct)**: OCP says non-identity, BCM map is non-`0x3210` but the
  specific nibble layout cannot be verified statically (see §2.2).
  Requires PRBS to confirm the exact permutation.
- **MISMATCH (H)**: OCP and BCM disagree on the presence/absence of a swap.
  High confidence that the config is wrong regardless of nibble semantics.
- Categories C (full reverse) and D (4-way 4,2,3,1) are flagged in the RX
  verdict column because they are unusual permutations that `0x123` /
  `0x213` may or may not faithfully encode — these definitely need PRBS
  validation.

## 4. Mismatch summary

### 4.1 High-confidence mismatches (19 direction-ports)

These ports have a clear disagreement between OCP Table 10 and the BCM
config — the two sources disagree on whether **any** swap correction is
needed. **Do NOT apply any change without PRBS verification.**

| Phys | SONiC       | Direction | OCP says          | BCM has |
|------|-------------|-----------|-------------------|---------|
| 0    | Ethernet0   | RX        | swap (2,1,4,3)    | `0x3210` (identity) |
| 1    | Ethernet4   | RX        | identity          | `0x1032` (non-identity) |
| 1    | Ethernet4   | TX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 2    | Ethernet8   | RX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 8    | Ethernet32  | TX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 9    | Ethernet36  | TX        | identity          | `0x1032` (non-identity) |
| 10   | Ethernet40  | RX        | identity          | `0x1032` (non-identity) |
| 10   | Ethernet40  | TX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 11   | Ethernet44  | RX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 11   | Ethernet44  | TX        | identity          | `0x1032` (non-identity) |
| 12   | Ethernet48  | TX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 13   | Ethernet52  | TX        | identity          | `0x1032` (non-identity) |
| 14   | Ethernet56  | TX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 17   | Ethernet68  | TX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 21   | Ethernet84  | RX        | identity          | `0x1032` (non-identity) |
| 21   | Ethernet84  | TX        | identity          | `0x1032` (non-identity) |
| 23   | Ethernet92  | RX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 23   | Ethernet92  | TX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 25   | Ethernet100 | RX        | identity          | `0x1032` (non-identity) |
| 30   | Ethernet120 | RX        | swap (3,4,1,2)    | `0x3210` (identity) |
| 30   | Ethernet120 | TX        | identity          | `0x1032` (non-identity) |
| 31   | Ethernet124 | TX        | swap (3,4,1,2)    | `0x3210` (identity) |

**Pattern observation:** Eight of the mismatches form an RX/TX inversion
pattern (e.g. Ethernet4, 10/40, 11/44, 30/120) where OCP says "RX only" or
"TX only" and BCM has the OPPOSITE direction non-identity. This strongly
suggests **the original config author swapped the meaning of
`xgxs_rx_lane_map` and `xgxs_tx_lane_map`**, or there is a systematic
understanding difference about which end the lane map applies to. Either
way, these ports have been working in production (the hardware is shipping
software) which means one of the following must be true:

1. The Broadcom SDK silently compensates by symmetry (e.g. applies the
   same map to both directions) — unlikely.
2. The OCP spec Table 10 is wrong for these ports — possible but the
   spec is the authoritative PCB reference.
3. The nibble convention used in the config is the inverse of what we
   assumed, and `xgxs_rx_lane_map_N=0x1032` in this config actually
   means "TX side needs a 0x1032 swap" (see §2.2).
4. The ports are running with CH crosstalk and RS-FEC is papering over
   per-lane mis-routing — possible on optics, dangerous on DAC.

None of these can be resolved from the static audit alone. **PRBS
verification is required.**

### 4.2 Medium-confidence items (0)

None — the permutation ambiguity in §2.2 means anything that is not a
clear high-confidence mismatch is classed as a structural match pending
PRBS.

### 4.3 Low-confidence / unknown

- **Ports with category C (full reverse 4,3,2,1) or D (4,2,3,1) permutations:**
  Ethernet88 (QSFP22, FC19), Ethernet96 (QSFP24, FC21), Ethernet112
  (QSFP28, FC25). The BCM config has three-digit lane maps (`0x213`,
  `0x123`, `0x123`) at master ports 77, 85, 101 respectively. A 4×4
  permutation cannot be encoded in 3 nibbles, so either (a) these values
  are implicitly zero-padded to `0x0213`/`0x0123`, (b) the Broadcom
  parser has a special meaning for short values, or (c) they are typos
  that truncated a nibble. Any of the three would need PRBS to determine
  whether the effective map matches the documented C/D permutation.
  Flagged as **LOW CONFIDENCE** — suggest a PRBS dry run AND a read-back
  of the programmed lane map from the device via `bshell` after boot.

- **All `match (struct)` verdict rows:** the nibble layout is unverified
  and only PRBS can confirm. Structural matching guarantees only that the
  config author knew a correction was needed, not that the correction is
  the right one.

## 5. Recommendations

1. **No config changes should be made** before running PRBS on the
   mismatched ports (and ideally all 32 for regression coverage). Any
   correction derived from this audit alone is speculative.
2. The **pattern of apparent RX/TX inversions** (§4.1) is worth
   investigating further by cross-referencing a different Broadcom
   platform (e.g. the Accton AS7712-32X) that uses the same nibble
   convention and a known-good reference BSP to settle the nibble-order
   ambiguity. If the AS7712 config shows the same `0x1032`/`0x2301`
   usage where the schematic shows matched swap patterns, then the
   Wedge100S config convention is fine and the OCP Table 10 annotations
   are misread.
3. The **category C / D** ports (Ethernet88, Ethernet96, Ethernet112)
   should be the first PRBS targets because the 3-nibble values are
   structurally suspicious regardless of the underlying convention.
4. PRBS runs should use the gated test in
   `tests/stage_03_platform/test_lane_swap_audit.py` — do not invent a
   parallel runner.

## 6. Counts

- 32 ports total × 2 directions = **64 direction-ports**
- **MATCH**: 17
- **match (struct, needs PRBS)**: 24 (including 3 category-C/D)
- **MISMATCH (HIGH confidence)**: 22 (across 16 unique ports)
- **LOW CONFIDENCE** (category C/D sub-set): 3 of the match-struct rows
- **UNKNOWN**: 0 (PDF fully legible for all 32 ports on pages 25–38)

Polarity-flip cross-reference: no `phy_xaui_*_polarity_flip` lines in
the BCM config, no per-lane polarity annotations in OCP Table 10 — no
mismatch to report.

## 7. Deferred work

- PRBS verification of every row classed as `match (struct)` or
  `MISMATCH (H)` — requires loopback modules OR cooperating peer PRBS.
  See `tests/stage_03_platform/test_lane_swap_audit.py`.
- Resolve nibble-order ambiguity (§2.2) by reference to AS7712 or
  Facebook Wedge100 config and Broadcom SDK source.
- BSP-side inspection of `bshell`-dumped effective lane map
  (`phy diag <port> rx_lane_map`) on a running switch to compare against
  the config hex.
