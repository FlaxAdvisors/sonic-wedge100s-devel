# TODO — wedge100s platform pending work

Tracked items that are not yet in flight. The NTP items were opened 2026-04-21
during LED debugging and home-lab network bring-up; MERGE-202511 was opened
2026-06-12 after auditing our fork against upstream.

---

## MERGE-202511 · Catch the fork up to upstream `202511` tip

**Context (2026-06-12):** Our `sonic-buildimage` fork is based on upstream
`202511` at `1447149b8` (2026-04-08). Upstream `202511` has since advanced to
`97a82c196` (2026-06-11) — **239 commits ahead, and our base is a clean
ancestor** (no rebase tangle; a `merge upstream/202511` replays our
`wedge100s/*` work on top). Of the 239: **63 are automated submodule
HEAD-bumps**, leaving 176 real backports — and most of those are other-vendor
(Mellanox/Nvidia, Marvell, Nokia, Arista, Broadcom **DNX**/Jericho) and do NOT
affect our Broadcom **XGS/Tomahawk** port.

**Do NOT rebase onto `202605`** — the next release line exists upstream but as
of 2026-06-12 has *never had a successful build pipeline* (CI blocked on
p4lang/protobuf breakage, see upstream #27809/#27825); it is diverged from
202511 by ahead 1231 / behind 676. Revisit 202605 only once it produces green
builds (realistically late summer / fall 2026).

**What's actually relevant to us (~20-30 commits):**
- 🔴 **Broadcom XGS SAI** — four driver upgrades we lack:
  `14.3.0.0.0.0.9.0 → .10.0 → .14.0 → .16.0` (#26708, #27290, #27426, #27579).
  This is our ASIC driver (syncd-brcm); highest-impact item and the one most
  likely to need a rebuild + hardware re-test.
- 🟡 **pmon / platform / optics** (touch our `sonic_platform`):
  `Add cpld/fpga device mount for pmon container` (#27676 — intersects our
  CPLD-driven LED/i2c daemons); `Prevent spurious xcvr insertion events`
  (#27033) and `Q3D enable interrupt to detect packet corruption` (#27501 —
  relevant to `sfp.py`); **`Remove ifupdown hooks installed by Chrony`
  (#27679 — intersects NTP-1/NTP-2 below)**.
- 🟡 **kernel / build / security:** `linux-kbuild install dep for installer`
  (#26955), `crashkernel high-region reserve` (#27650), `resolve April 2026
  docker-ptf security vulnerabilities` (#26866 — only explicit CVE in the
  239), `upgrade p4lang package versions` (#26775), and the
  `[ci/build] Upgrade SONiC package versions` rollups (#26995, #27126, #27525).
- Skip the ~140 Mellanox/Marvell/Nokia/Arista/DNX commits — no wedge100s impact.

**Plan:**
1. Stage on a fresh topic branch `wedge100s/upstream-202511-catchup` off
   `master` (do NOT touch `master` until validated). `git merge upstream/202511`.
2. **Re-validate quilt patch series** against the 63 submodule bumps —
   `quilt push -a` each `src/*.patch` series; `quilt refresh` any that fuzz.
   The `src/sonic-utilities.patch` area is the likely refresh point (~30
   sonic-utilities commits landed upstream, incl. the `system_health` area our
   patch 0004 touches).
3. Rebuild platform `.deb` + full image; the Broadcom XGS SAI bump means
   syncd behavior can shift — **hardware re-test on lapin** before merging to
   `master` (run the `tests/` suite, focus on optics/xcvr + SAI counters).
4. Merge to `master` only after build + hardware validation pass.

**Verification of build currency that prompted this (2026-06-12):** the
existing `target/sonic-broadcom.bin` (built 2026-04-23 09:24 PDT) IS faithful
to our `master` HEAD `86aa3b9c0` — no unbuilt master commits, and the lone
unmerged topic commit (`dcb5186d7` on `wedge100s/i2c-bmc-sysfs`) is a content
duplicate of what reached master via PR #24. The image is stale only relative
to *upstream*, which is what this item closes.

---

## NTP-1 · Persist NTP defaults in fresh-install init template

**Context (2026-04-21):** After fresh ONIE + SONiC install of the current
master `.deb`, lapin's chrony runs but syncs nothing — `NTP_SERVER` in
config_db is empty and `/etc/chrony/chrony.conf` has no `server`/`pool` lines.
BMC's `/etc/ntp.conf` has placeholder server names `ntp1/2/3` that never
resolve. Both result in clocks stuck at POST defaults (SONiC at Sep 2025 on a
switch we booted in Apr 2026). Runtime workaround for this session: `sudo
config ntp add 162.159.200.1` (+ `.123`) on SONiC, manual `/etc/ntp.conf`
append on BMC.

**Scope for this task — SONiC side only** (BMC side is handled in NTP-2):
- Add a default `NTP_SERVER` block to the platform's init-config template.
  Likely location: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
  — check for `init_cfg.json.j2`, `ztp-*.json`, or similar. If platform has no
  such template, consider whether this belongs upstream (generic SONiC default)
  vs. in our `wedge100s/build-infra` branch.
- Use Cloudflare anycast IPs (stable, no GeoDNS-to-break-on-pinning issue):
  `162.159.200.1` and `162.159.200.123`.
- Topic branch: `wedge100s/build-infra` (owns init-config templates).

**Partial supersession:** The BMC side of this is folded into NTP-2 since
BMC's rootfs is non-persistent anyway; SONiC pushes fresh config on every
boot there.

**Ref:** see `~/.claude/projects/-home-flax-git-sonic-wedge100s-devel/memory/project_bmc_nonpersistent_rootfs.md`
for BMC rootfs context.

---

## NTP-2 · Feature: SONiC-side NTP config cascades to BMC (single source of truth)

**Context:** Today the two NTP configs are completely independent — SONiC
chrony sees its own `NTP_SERVER` config_db table; BMC `ntpd` reads
`/etc/ntp.conf` which ships with non-resolvable placeholder names. No
mechanism links them. An operator who fixes NTP on SONiC (via
`sudo config ntp add ...`) has no effect on BMC clock. And BMC rootfs is
wiped on every BMC reboot so any `/etc/ntp.conf` edit is ephemeral (see
`project_bmc_nonpersistent_rootfs.md`).

**Goal:** SONiC becomes the single source of truth. When `NTP_SERVER`
changes in SONiC's config_db (CLI or ZTP), the change propagates to BMC's
`/etc/ntp.conf` and ntpd is restarted there.

**Design sketch (refine during implementation):**
1. Watch SONiC's Redis config_db `NTP_SERVER` table — either via pub/sub
   subscription in an existing daemon, a hook in `sonic-utilities`' `config
   ntp` command, or periodic reconciliation from a wedge100s-side daemon.
2. Render the server list into BMC-compatible `ntp.conf` format (`server
   <ip> iburst` lines on top of the base BMC template that preserves
   `tinker panic 0`, `driftfile`, `restrict` defaults).
3. Push to BMC over SSH (same IPv6 LL + key path `_bmc_led_init()` uses).
   Deploy to `/etc/ntp.conf`; investigate if writing to `/mnt/data/etc/...`
   would persist across BMC reboot (we believe not on this image, but
   worth re-testing).
4. Restart `/etc/init.d/ntpd` on BMC after each push.
5. On every SONiC boot, re-apply unconditionally — BMC rootfs is ephemeral
   per project_bmc_nonpersistent_rootfs.md.

**Likely owning component:** `wedge100s-bmc-daemon` already has the SSH
ControlMaster to the BMC and inotify watch on `/run/wedge100s/`. Natural
extension: add a new dispatch filename `ntp_config.set` analogous to
`clear_led_diag.set`, rendered from config_db whenever NTP_SERVER changes,
plus a boot-time apply.

**Topic branches involved:**
- `wedge100s/i2c-bmc-sysfs` — daemon change (new inotify dispatch)
- `wedge100s/device-identity` — optional helper in `sonic_platform/bmc.py`
- `wedge100s/submodule-patches` — if we hook SONiC's `config ntp` CLI
  (sonic-utilities) for synchronous push on CLI add/del

**Supersedes:** NTP-1's BMC-side requirement.

---

## Notes for future you

- These are separate from the currently-in-flight LED FBOSS bytecode work —
  see `project_led_fboss_mapping.md` in memory for that thread.
- Both NTP items are **not urgent** — lapin's clocks are manually set in the
  current session. But the defect will recur on every fresh install until
  fixed.
- Before picking these up, confirm the workaround IPs (Cloudflare anycast
  `162.159.200.{1,123}`) are still appropriate; check for any organizational
  preference for a specific NTP source.
- **MERGE-202511 is the higher-value item** of the three and partially
  overlaps NTP — upstream #27679 (`Remove ifupdown hooks installed by Chrony`)
  lands in that merge and may change chrony behavior the NTP work depends on.
  Sequence the catch-up merge before (or alongside) the NTP tasks.
