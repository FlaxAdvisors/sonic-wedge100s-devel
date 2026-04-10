# Eagle Core / TSC-E Management Port Research (GAP-024)

**Date:** 2026-04-09
**Task:** P2 Task 6 — Tomahawk Eagle Core management port
**Decision:** **DEFER as "requires hardware schematic + loopback validation"**
**Branch:** `wedge100s/chipset-config` (no config change applied)

## Background

Per OCP Wedge 100S v1.3 spec Section 7.5 and `PLATFORM_GUIDE.md` Section 13,
the BCM5387 OOB management switch port P1 is documented as connected to a
Tomahawk "Eagle Core" 10G management port via SGMII and labeled
"wired and reserved for future." This task investigates whether the port
is usable today.

The Tomahawk BCM56960 includes **TSC-E** (Eagle) PHY blocks intended for
low-speed chip-management Ethernet (typically 1G/10G SGMII) separate from
the primary Tomahawk front-panel TSCF (Falcon) ports. In SDK configuration
files these appear as `portmap_66` / `portmap_100` or similar, sourcing
SerDes physical lanes 129–134.

## Evidence gathered

### 1. Live BCM diag shell on target (verified on hardware 2026-04-09)

Accessed via `ssh admin@192.168.88.12` → `docker exec syncd bcmcmd '<cmd>'`.
No changes made — read-only introspection only.

- `bcmcmd 'ps all'` lists **132 ports**: `ce0..ce31` (front panel 100G) plus
  `xe0..xe99` subports + CPU, logical port numbers 1–133 with gaps at
  **66, 67, 100, 101** (and 33). No port named `mng`, `mgmt`, `mgmt0`,
  `xe100`, or anything Eagle-Core related.
- `bcmcmd 'port mng status'`, `'port mgmt status'`, `'port mgmt0 status'`,
  `'port 66'` all return `unrecognized port bitmap`.
- `bcmcmd 'config show' | grep portmap` emits exactly the portmap entries
  from `th-wedge100s-32x-flex.config.bcm` — no additional management
  portmap lines injected by the SDK.
- Gaps in live portmap series:
  ```
  portmap_65.0=60:25:i
  (no portmap_66 or portmap_67)
  portmap_68.0=69:100
  ...
  portmap_99.0=96:25:i
  (no portmap_100 or portmap_101)
  portmap_102.0=101:100
  ```
- `bcmcmd 'phy info'` shows entries for physical SerDes 65, 87, 111, 112,
  113, 129. SerDes 129 appears in the phy table even though it is not
  mapped to any logical port. No phy entry for SerDes 130/133/134 (the
  other candidate TSC-E lanes in the AS7712 reference).

### 2. Linux-side OOB path

- `eth0` on the SONiC host binds to `igb` (Intel I210, PCI 8086:1533 at
  `0000:02:00.0`). This is the COM-e NIC connecting directly to the
  BCM5387 P0 front-panel RJ45. **It is not the Eagle Core path.**
- No orphaned `mgmt`/`eth1`/`ma1` interface is missing on the host — any
  future Eagle Core interface would be a brand-new netdev requiring a new
  portmap + saiplayer + hostif lane mapping.

### 3. Reference platform cross-reference

**Accton AS7712-32X** — same Tomahawk BCM56960, same Accton SDK lineage:

```
# th-as7712-32x100G.config.bcm
#TSC-E Management port 1
#portmap_66=129:10
#portmap_67=133:10
...
#TSC-E Management port 2
#portmap_100=131:10
#portmap_101=134:10
```

Accton explicitly **defines then comments out** both TSC-E management
ports. The naming ("TSC-E") is the confirming evidence of what logical
slots 66/67 and 100/101 are reserved for in this BCM configuration
lineage, and the fact that Accton ships AS7712 with them disabled on a
production platform with the same SoC is strong evidence that the Eagle
Core path is not needed for a working SONiC system.

**Facebook Wedge100 (non-S)** — closest HW sibling:

`th-wedge100-32x100G.config.bcm` has **no** `mng`, `mgmt`, `eagle`,
`TSC-E`, `portmap_66`, or `portmap_100` references at all. Facebook's
reference SONiC config for the Wedge100 family does not configure an
Eagle Core management port.

### 4. Current wedge100s config state

`th-wedge100s-32x-flex.config.bcm` (133 portmap entries):
- Has the same gaps at 66/67 and 100/101 as AS7712 — i.e., it was
  derived from the AS7712 config but never enabled TSC-E mgmt.
- Physical SerDes 129, 130, 131, 132, 133, 134 are **not** currently
  used as right-hand values in any `portmap_N.0=P:speed` line in
  wedge100s-32x, so the lanes themselves are available.

## Decision: DEFER

Classification: **"requires hardware schematic + loopback validation"**
(closable only with physical evidence we do not currently have).

### Why not proceed

1. **No runtime evidence the port exists on the board.** `bcmcmd 'ps all'`
   has zero management port slots. The SDK will not auto-instantiate an
   Eagle Core port just because the SerDes lanes exist — a portmap entry
   is required. But a portmap entry for a SerDes lane that is not
   physically wired to the BCM5387 would produce a dead port with
   permanently down link and no way to distinguish "cable unplugged"
   from "there is no cable."

2. **No reference platform gives us a known-good entry to copy.**
   - AS7712: entries exist but commented out in production. Accton
     clearly decided not to use them, which suggests either (a) the
     feature was problematic in their validation, or (b) the AS7712
     board does not actually route these lanes to a management PHY.
     Either way, copying `portmap_66=129:10` to wedge100s is
     speculative — the lane-to-physical wiring on wedge100s is almost
     certainly different from AS7712's layout anyway.
   - FB Wedge100: no entries at all. Facebook built their entire Wedge
     100 product line without needing an Eagle Core SONiC port.

3. **OCP spec says "reserved for future" — not "currently functional."**
   The phrase explicitly means the signal trace may exist on the PCB
   but there is no committed use today. Without a board schematic
   showing which BCM56960 SerDes pins route to the BCM5387 P1 SGMII
   balls, we cannot guess the correct lane number.

4. **Risk of breaking boot.** Adding a portmap entry to a running
   config forces a syncd restart on the next reload. A bad entry
   (wrong lane, lane conflict with an existing front-panel subport,
   unsupported speed) can brick syncd startup and require a rollback
   via u-boot, which is disproportionate risk for a feature with zero
   validated use case.

5. **Nothing is currently missing.** The existing eth0 management path
   (Intel I210 → BCM5387 P0 RJ45) works. No SONiC feature, daemon,
   or test is blocked by the absence of an Eagle Core interface.

### Conditions for closing the gap in the future

To move this from "deferred" to either "implemented" or "permanently
closed as unused," we need:

- **Wedge100s board schematic** showing the trace from BCM56960 TSC-E
  SerDes pins to BCM5387 P1 SGMII pins. Only then can we derive the
  correct `portmap_N=serdes:speed` entry.
- **Loopback / traffic test plan** — with the portmap entry added and
  a build deployed, run `bcmcmd 'port mng set enable'` + `ps mng` and
  confirm the link comes up, then send ARP from the BCM5387 side (via
  BMC or COM-e) and verify it arrives on the Tomahawk logical port.
- **Motivation.** A specific SONiC use case that justifies the
  validation effort (in-band chip management, for example, separated
  from the eth0 OOB path). Currently none exists.

Until all three exist, this gap stays deferred.

## Alternative: permanently close the gap

If a schematic review shows the BCM5387 P1 is actually **not wired**
to any BCM56960 SerDes pin on the wedge100s board (which would
contradict OCP Section 7.5 but is possible if Accton optimized the
layout), we should close this gap as "permanently unused on this
platform" and update `PLATFORM_GUIDE.md` Section 13 to remove the
"reserved for future" language and state "not present."

## Artifacts

- **No file changes** to `th-wedge100s-32x-flex.config.bcm`.
- Research logged here.

## References

- `/export/sonic/sonic-buildimage/device/accton/x86_64-accton_as7712_32x-r0/Accton-AS7712-32X/th-as7712-32x100G.config.bcm` lines 79–81, 108–110
- `/export/sonic/sonic-buildimage/device/facebook/x86_64-facebook_wedge100-r0/Facebook-W100-C32/th-wedge100-32x100G.config.bcm`
- `/export/sonic/worktrees/wedge100s-chipset-config/device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm`
- `PLATFORM_GUIDE.md` Section 13 (OOB Ethernet mapping)
- OCP Wedge 100S Spec v1.3 Section 7.5
- `docs/superpowers/plans/2026-04-09-p2-feature-work.md` Task 6
