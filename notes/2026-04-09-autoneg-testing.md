# CL73 Autonegotiation Research & Testing (GAP-027)

**Date:** 2026-04-09
**Topic branch:** `wedge100s/chipset-config`
**Outcome:** **Deferred — cannot validate CL73 without a rebuild+reload cycle.
BCM config file NOT changed.**

## Goal

Task 4 of the P2 feature plan asked us to test CL73 autoneg against the
Arista EOS peer on a production port and, **if stable**, flip
`phy_an_c73=0x0` → `phy_an_c73=0x1` in
`th-wedge100s-32x-flex.config.bcm` so that per-port CL73 can be enabled
at runtime via `config interface autoneg EthernetN enabled`.

## Test Setup

### SONiC Port Selection

| Property | Value |
|---|---|
| SONiC interface | `Ethernet48` |
| SONiC alias | `Ethernet13/1` |
| SONiC lanes | 37, 38, 39, 40 |
| BCM port number | 34 |
| BCM diag shell port name | `ce7` |
| Baseline speed | 100G full-duplex |
| Baseline FEC | RS-FEC (CL91) |
| Baseline autoneg | off (forced) |
| Baseline admin/oper state | up/up |
| Platform interface type | KR4 |
| Routed vs LAG | standalone, routed mode — **not** a PortChannel1 member |

`Ethernet48` was chosen because it is the only production link to the
Arista peer that is **not** a PortChannel1 member. Ethernet16 and
Ethernet32 (PortChannel1 members) and Ethernet84/108/112 (also
rabbit-lorax neighbours per LLDP) were excluded — some are LAG
members, others were not needed for a single-port test.

### Peer (rabbit-lorax)

(verified on hardware 2026-04-09)

- **Platform:** Facebook WEDGE100S12V (sibling Tomahawk switch running EOS)
- **EOS version:** 4.27.0F, build 24305004.4270F
- **Peer port:** `Ethernet15/1` (confirmed via SONiC `show lldp table`)
- **Peer transceiver:** 100GBASE-CR4 (DAC), SN F2032955503-2
- **Peer PHY:** BCM56960-TSCF (identical to Wedge100S — same silicon)
- **Peer Oper speed:** 100 Gbps, Reed-Solomon FEC, PMA/PMD link up all 4 lanes
- **Peer running-config:**

  ```text
  interface Ethernet15/1
     switchport access vlan 2
  ```

  No `speed forced`, no `speed auto`. Port is at EOS default (fixed 100G,
  no AN).

- **Peer hardware capability:**

  ```text
  Speed/duplex: 10G/full,25G/full,40G/full,50G/full,100G/full(default),auto
  Error correction: reed-solomon(100G(default)), fire-code(25G(default),50G(default)),
                    disabled(10G(default),25G,40G(default),50G,100G)
  ```

  The peer **is capable** of autoneg but is not currently configured for it.

## What I Tested and What Happened

### Baseline Capture

```text
drivshell> ps ce7
           port  link  Lns   speed/duplex  auto   inter   max   ...
       ce7( 34)  up     4   100G  FD       No     KR4     9122
```

SONiC side:

```text
Ethernet48  37,38,39,40  100G  9100  rs  Ethernet13/1  routed  up  up
```

### Enable Autoneg from Diag Shell

```text
drivshell> port ce7 autoneg=on
drivshell> ps ce7
       ce7( 34)  down   4   25G  FD       Yes    KR2     9122
```

The BCM SDK accepted `autoneg=on`, marked the port as autoneg=Yes, and
**dropped the interface to 25G KR2** — i.e. CL37/CL73 base-page
negotiation converged on the slowest common mode, or fell through to
the CL37 path only, because `phy_an_c73=0x0` disables CL73 entirely at
SDK init.

Link stayed **down** for the full 10-second observation window. Because
the peer (rabbit-lorax Et15/1) is running fixed 100G with no AN, there
is no reachable negotiation result here — the BCM side is attempting
(CL37-only) AN and the peer is silent on AN PDUs.

### Restore

```text
drivshell> port ce7 autoneg=off speed=100000
drivshell> ps ce7
       ce7( 34)  up     4   100G  FD       No     KR4     9122
```

Link came back within <2 seconds. SONiC-side:

```text
Ethernet48  37,38,39,40  100G  9100  rs  Ethernet13/1  routed  up  up
```

Counters continued incrementing (traffic resumed). No residual state
damage, no BCM SDK error logs. Clean restore.

### Runtime Config Ground Truth

```text
drivshell> config show phy_an_c73
phy_an_c73=0x0
```

Confirmed the live SDK has `phy_an_c73=0x0`, i.e. the file under test
on `wedge100s/chipset-config` matches deployed behaviour.

## Why We Cannot Decide from This Test Alone

The task's decision gate ("if CL73 link is stable for 10 s → flip the
config; if not → defer") assumes the test exercises the intended code
path. On this platform, the observed test **does not**:

1. `phy_an_c73=0x0` is a **boot-time SDK global** that gates whether
   the TSCF firmware arms CL73 state machines at all. It is **not**
   runtime-toggleable from `bcmcmd`. With it set to `0x0`, `port ce7
   autoneg=on` takes the CL37-only code path, which on a 100G KR4
   serdes group lands on 25G KR2 and (with no AN peer) does not link.
2. To actually observe CL73 negotiate, we would need to:
   a. Rebuild the platform .deb with `phy_an_c73=0x1`, deploy it, and
      restart `syncd` (or reboot the switch); **and**
   b. Configure the Arista peer with `speed forced 100gfull` → `speed
      auto` (or equivalent) so both ends are actually attempting CL73.
3. Neither of those is in scope for this task (the build is running on
   master; deployment to production peer is disruptive).

In other words, the runtime failure we observed is the expected
behaviour of the current configuration — it tells us **nothing** about
whether CL73 works with this peer once it is actually turned on. The
test was not able to answer the question the task wanted us to answer.

Given that uncertainty, flipping the global to `0x1` without a real
CL73 stability proof would be irresponsible: even if 31 of 32 front
ports are currently forced-speed (so CL73 arming is dormant until a
`config interface autoneg` call), enabling it creates a new
configuration surface for which we have **zero** on-hardware evidence
of stability.

## Decision

**Deferred.** Leave `phy_an_c73=0x0` in the BCM config on the
`wedge100s/chipset-config` branch. Do not commit a change to the
platform fork for GAP-027.

To unblock GAP-027, the following sequence is required:

1. Schedule a maintenance window with the rabbit-lorax owner (the
   link carries production traffic — `RX_OK` increments ~2k/second at
   test time).
2. Rebuild the wedge100s-32x platform .deb on a **separate** topic
   branch spike (not merged) with `phy_an_c73=0x1`.
3. Deploy to the Wedge 100S in a staging configuration (not during
   traffic hours).
4. On the Arista side, set `interface Ethernet15/1 ; speed auto
   100gfull` (Arista uses `speed auto <forced-list>` for CL73-like
   negotiation on CR4 links).
5. Run the `tests/stage_15_autoneg_fec/test_autoneg_cl73.py` test
   included in this commit against `Ethernet48`.
6. If the test passes and link is stable for 60+ seconds with zero
   flaps and zero FEC uncorrected codewords, repeat the config file
   change on `wedge100s/chipset-config`, push, merge, and rebuild.

## Files Included in This Change

**Platform fork (`/export/sonic/worktrees/wedge100s-chipset-config`):**

- No changes. Decision deferred.

**Devel repo (`/export/sonic/sonic-wedge100s-devel`):**

- `notes/2026-04-09-autoneg-testing.md` (this file)
- `tests/stage_15_autoneg_fec/test_autoneg_cl73.py` (standalone CL73
  interop test, documents `AUTONEG_PORT = "Ethernet48"` and
  `AUTONEG_PEER_PORT = "Ethernet15/1"`). Not included in the default
  stage_15 run — must be invoked explicitly because it reconfigures a
  production link.

## Cross-References

- `docs/superpowers/plans/2026-04-09-p2-feature-work.md` §Task 4
- `tests/stage_15_autoneg_fec/test_autoneg_fec.py` lines 7-18 (prior
  observation of "autoneg speed workaround failed / Feature not
  initialized", which is the orchagent-visible form of the same
  boot-time CL73 gating)
- `tests/stage_20_traffic/test_traffic.py` lines 7-27 (lab topology,
  confirming Ethernet48 is standalone and not a LAG member)
- `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm`
  line 14 (the `phy_an_c73=0x0` setting that gates this feature)
- `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc`
  lines 21, 41 (Ethernet48 ↔ BCM port 34 ↔ `ce7` mapping)

## Facts Verified on Hardware 2026-04-09

- `Ethernet48` ↔ BCM port 34 ↔ `ce7` (verified via `phy info` and
  `ps ce7`) (verified on hardware 2026-04-09)
- Peer `rabbit-lorax` is a Facebook WEDGE100S12V running EOS 4.27.0F
  (verified on hardware 2026-04-09)
- Peer `Ethernet15/1` is at fixed 100GBASE-CR4 with RS-FEC, no AN in
  running-config (verified on hardware 2026-04-09)
- `port ce7 autoneg=on` with `phy_an_c73=0x0` drops the port to 25G
  KR2 and the port does not relink (verified on hardware 2026-04-09)
- `port ce7 autoneg=off speed=100000` cleanly restores the original
  100G KR4 forced-speed state in <2 s (verified on hardware 2026-04-09)
- Runtime `config show phy_an_c73` reports `0x0` (verified on hardware
  2026-04-09)
