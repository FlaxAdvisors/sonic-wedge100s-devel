# Clean Fork Design: FlaxAdvisors/sonic-buildimage Wedge 100S Platform Port

**Date:** 2026-04-08
**Status:** Approved

## Purpose

Reorganize the wedge100s porting work into a clean, merge-ready fork with
well-documented code, functional topic branches, and separated development
artifacts. The goal is a repository that:

1. Could theoretically merge upstream into `sonic-net/sonic-buildimage`
2. Is discoverable by others wanting wedge100s SONiC support
3. Has clean git history grouped by functionality
4. Has full API documentation (pydoc, Doxygen, Sphinx)

Development artifacts (tests, notes, tools, config automation) will move to a
separate `-devel` repo (designed separately in a future session).

## Repository

**Repo:** `FlaxAdvisors/sonic-buildimage` (existing GitHub fork, reset in place)

Preserves the GitHub fork relationship to `sonic-net/sonic-buildimage` for
discoverability (network graph) and cross-repo PR capability.

**Base:** `sonic-net/sonic-buildimage:202511` branch

## Branch Strategy

```
sonic-net/sonic-buildimage:202511
    ↓ (fetch + push)
upstream                    ← read-only mirror, updated periodically
    ↓ (initial copy)
master                      ← default branch; upstream + merged topic PRs = buildable image
    ↑
wedge100s/build-infra      ──┐
wedge100s/device-identity  ──┤
wedge100s/chipset-config   ──┤
wedge100s/i2c-bmc-sysfs    ──┤  PRs into master, merged in dependency order
wedge100s/sfp-optics       ──┤
wedge100s/led-pipeline     ──┤
wedge100s/flex-counters    ──┤
wedge100s/ztp              ──┤
wedge100s/l3-bgp           ──┤
wedge100s/submodule-patches──┘  (independent, merges at any point)
```

### Ongoing Development

After initial topic branches are merged into `master`, ongoing work follows
normal GitHub flow:

- **Fix within one topic's scope:** commit on the original topic branch, PR to master
- **Fix spanning topics or depending on later work:** branch off `master` with descriptive name (e.g., `wedge100s/fix-led-magenta-bug`), PR to master

The original topic branches serve as historical documentation of the port
structure and as a template for anyone porting a similar platform.

### Release Branch Migration

When a new upstream release branch appears (e.g., `202605`):

1. Update `upstream` branch to new release
2. Rebase topic branches onto new `upstream`
3. Re-merge into `master`

## Topic Branch Decomposition

### 1. `wedge100s/build-infra` (depends on: —)

Build system integration — the minimum to make
`make target/debs/.../sonic-platform-accton-wedge100s-32x*.deb` succeed.

**Files:**
- `platform/broadcom/platform-modules-accton.mk`
- `platform/broadcom/one-image.mk`
- `platform/broadcom/sonic-platform-modules-accton/debian/rules`
- `installer/platforms/x86_64-accton_wedge100s_32x-r0`
- `installer/platforms_asic` (mapping entry)

**Commits:**
- `feat(build): add wedge100s-32x platform module target to Accton makefile`
- `feat(build): add wedge100s-32x to one-image lazy installs`
- `feat(installer): add wedge100s-32x console and platform config`

### 2. `wedge100s/device-identity` (depends on: build-infra)

Device tree and platform identity — what SONiC sees.

**Files:**
- `device/accton/x86_64-accton_wedge100s_32x-r0/` (hwsku, port_config.ini,
  platform.json, default_sku)
- `platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.postinst` (skeleton)
- `platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.prerm`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/accton_wedge100s_util.py`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-pre-shutdown.service`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-pre-shutdown.sh`
- `files/image_config/platform/rc.local` (serial console fix)

**Commits:**
- `feat(device): add wedge100s-32x hwsku, port_config, and platform.json`
- `feat(platform): add wedge100s-32x postinst/prerm and platform init utility`
- `feat(platform): add pre-shutdown service for clean reboot`
- `fix(platform): force TERM=linux for serial-getty on ttyS0`

### 3. `wedge100s/chipset-config` (depends on: device-identity)

Memory SDK configuration — what the ASIC sees.

**Files:**
- `device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm`
- `device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc`

**Commits:**
- `feat(memory): add Memory flex port config for wedge100s-32x (4x25G breakout)`
- `feat(memory): add LEDUP0/1 init bytecodes for Memory port LED mapping`

### 4. `wedge100s/i2c-bmc-sysfs` (depends on: device-identity)

CP2112 USB-HID bridge + OpenBMC REST daemon — the hardware abstraction layer
that exposes environmentals via `/run/wedge100s/` sysfs-like interface.

**Files:**
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-i2c-daemon.c`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon.c`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-auth.c`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bus-reset.sh`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-i2c-daemon.service`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-bmc-daemon.service`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-bmc-poller.service`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-bmc-poller.timer`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-i2c-poller.service`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-i2c-poller.timer`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-bmc-daemon` (Python wrapper)

**Commits:**
- `feat(i2c): add CP2112 USB-HID userspace I2C daemon`
- `feat(bmc): add OpenBMC REST daemon with SSH-key auth`
- `feat(sysfs): add /run/wedge100s/ virtual sysfs for environmentals`
- `feat(service): add systemd units for i2c-daemon, bmc-daemon, bmc-poller`

### 5. `wedge100s/sfp-optics` (depends on: i2c-bmc-sysfs)

SFP platform API implementation with multi-family optics support.

**Files:**
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/sfp.py`
- i2c-poller additions for SFP EEPROM caching

**Commits:**
- `feat(sfp): add SFP platform API with CMIS/SFF-8636/SFF-8472 support`
- `feat(sfp): add EEPROM caching via i2c-poller with TTL refresh`
- `feat(sfp): add presence detection and DOM monitoring`

### 6. `wedge100s/led-pipeline` (depends on: chipset-config, i2c-bmc-sysfs)

LED control covering presence, speed indication, and link activity.

**Files:**
- `device/accton/x86_64-accton_wedge100s_32x-r0/plugins/led_control.py`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-ledup-linkstate.service`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-ledup-linkstate`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-led-diag.py`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-led-diag-bmc.py`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/clear_led_diag.sh`
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s_ledup.py`

**Commits:**
- `feat(led): add led_control.py for presence/speed/activity states`
- `feat(led): add ledup-linkstate service for real-time link tracking`
- `fix(led): LEDUP1 bytecode patch for all-magenta LED bug`
- `feat(led-diag): add LED diagnostic tools (CLI, BMC CPLD access, BAR2 mmap)`

### 7. `wedge100s/flex-counters` (depends on: chipset-config)

Hardware counter path via bcmcmd socket, bypassing orchagent.

**Files:**
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/flex-counter-daemon/` (all C sources + Makefile)
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-flex-counter-daemon.service`

**Commits:**
- `feat(counters): add bcmcmd socket client for hardware counter reads`
- `feat(counters): add flex-counter-daemon with Redis I/O and lane-count detection`
- `fix(counters): Redis reconnect, I/O timeout, uint64 underflow protection`

### 8. `wedge100s/ztp` (depends on: device-identity)

L2 zero-touch provisioning baseline.

**Files:**
- `device/accton/x86_64-accton_wedge100s_32x-r0/ztp/l2-config_db.json`
- `device/accton/x86_64-accton_wedge100s_32x-r0/ztp/ztp-l2-sample.json`

**Commits:**
- `feat(ztp): add L2 config_db.json and ZTP sample configuration`

### 9. `wedge100s/l3-bgp` (depends on: ztp)

L3 config generator and BGP-ready templates.

**Files:**
- `device/accton/x86_64-accton_wedge100s_32x-r0/ztp/gen-l3-config.py`
- `device/accton/x86_64-accton_wedge100s_32x-r0/ztp/gen_l3_config.py`
- `device/accton/x86_64-accton_wedge100s_32x-r0/ztp/l3-config_db.json`
- `device/accton/x86_64-accton_wedge100s_32x-r0/ztp/ztp-l3-sample.json`

**Commits:**
- `feat(l3): add L3 config_db generator with breakout-aware port mapping`
- `feat(l3): add L3 ZTP sample with BGP-ready templates`

### 10. `wedge100s/submodule-patches` (depends on: —)

Quilt patch series for upstream submodule fixes.

**Files:**
- `src/sonic-swss.patch/`
- `src/sonic-utilities.patch/`
- `src/sonic-ztp.patch/`
- `src/ptf.patch/`
- `src/ptf-py3.patch/`
- `src/redis-dump-load.patch/`
- `src/scapy.patch/`
- `src/sonic-dash-ha.patch/`
- `src/supervisor.patch/`

**Commits:**
- `fix(patches): add quilt series for sonic-swss, sonic-utilities, sonic-ztp, ptf, scapy, and others`

## Documentation Infrastructure

Located at `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/docs/`:

```
docs/
├── conf.py              # Sphinx config — project name, extensions, paths
├── Makefile             # make html, make clean
├── index.rst            # Landing page with toctree
├── architecture.rst     # Platform overview, I2C topology, sysfs design
├── api/
│   ├── sfp.rst          # Auto-generated from sfp.py docstrings (autodoc)
│   ├── led_control.rst  # Auto-generated from led_control.py
│   └── ...              # One .rst per Python module
├── daemons/
│   ├── i2c-daemon.rst   # Architecture + Doxygen-extracted C docs
│   ├── bmc-daemon.rst
│   └── flex-counter.rst
└── guides/
    └── porting.rst      # "How we ported this" — template for others
```

### Documentation Standards

**Python:** Google-style docstrings on every public class, method, and module.
Sphinx `autodoc` extension generates API reference pages.

**C:** Doxygen `/** @brief */` headers on all functions. Sphinx `breathe`
extension integrates Doxygen XML output. If breathe adds too much build
complexity, C docs will be hand-written `.rst` files referencing the Doxygen
comments as source of truth.

**Per-module documentation covers:**
- Purpose and design rationale
- Public API with parameter descriptions and return values
- Hardware dependencies and constraints
- Configuration and systemd service relationships

**Build:** `make -C docs html` produces `docs/_build/html/` (gitignored).

Each topic branch gets a final `docs(<topic>)` commit adding annotations and
sphinx pages for its components.

## Execution Plan

### Phase 1 — Repo Reset

**Context:** The existing `FlaxAdvisors/sonic-buildimage` fork was created with
"main only" (i.e., only the `master` branch was copied from upstream). The fork
has no `202511` branch. Since a GitHub fork is just a regular git repo with a
parent link, we can push any branch to it — we don't need to re-fork.

**Prerequisite:** `upstream` remote points to `sonic-net/sonic-buildimage` and
`upstream/202511` has been fetched locally (already done in this repo).

```bash
# 1. Safety — tag the old wedge100s branch before touching anything
git tag archive/wedge100s-v1 origin/wedge100s
git push origin archive/wedge100s-v1

# 2. Create the upstream tracking branch from sonic-net 202511
git branch upstream upstream/202511
git push origin upstream

# 3. Force-push master to match upstream/202511
#    (This overwrites the accidental wedge100s merge on master)
git push origin upstream/202511:master --force

# 4. Clean up old branches from the remote
git push origin --delete wedge100s
git push origin --delete revert-1-wedge100s

# 5. Update repo description (via GitHub API)
gh repo edit FlaxAdvisors/sonic-buildimage \
  --description "SONiC platform support for Accton Wedge 100S-32X (Broadcom Tomahawk)"
```

After this, `FlaxAdvisors/sonic-buildimage` has:
- `master` (default) = `sonic-net/sonic-buildimage:202511` content
- `upstream` = tracking branch for future syncs
- `archive/wedge100s-v1` tag = safety snapshot of old work
- GitHub fork relationship to `sonic-net/sonic-buildimage` preserved

**To sync upstream later:**
```bash
git fetch upstream 202511
git push origin upstream/202511:upstream
# Then merge or rebase upstream into master as needed
```

**Destructive operations — requires explicit user go-ahead before executing.**

### Phase 2 — Topic Branch Creation

For each of the 10 topic branches, in dependency order:

1. Create branch from `master`
2. Copy relevant files from local `wedge100s` working tree
3. Add pydoc/doxygen annotations to all public APIs
4. Write clean atomic commits with conventional-commit messages
5. Add `docs(<topic>)` commit with sphinx pages
6. Push branch to remote

### Phase 3 — Documentation Infrastructure

1. Set up sphinx config, Makefile, and index in `wedge100s-32x/docs/`
2. Write `architecture.rst` (platform overview, I2C topology, sysfs design)
3. Write `porting.rst` (how-we-ported-this guide)
4. Verify `make -C docs html` builds successfully

### Phase 4 — Integration

1. Open PRs in dependency order
2. Merge each PR into `master`
3. Merge `wedge100s/submodule-patches` at any point

### Phase 5 — Verification

1. Build `sonic-platform-accton-wedge100s-32x*.deb` from `master`
2. Install on hardware, verify platform services start correctly

## Devel Repo (Future)

A separate `FlaxAdvisors/wedge100s-devel` repo will contain:

- Test suite (pytest stages)
- Development notes and investigation findings
- Configuration automation (deploy.py, tools/)
- Developer onboarding documentation
- Hardware topology and reference materials

Design for this repo will be done in a subsequent session after the clean fork
is established.

## Decisions Log

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Upstream base | `sonic-net/sonic-buildimage:202511` | Stable release branch, avoids bookworm/trixie phase issues |
| 2 | Branch organization | Functional topic branches (10) | Reviewable per-feature, cherry-pickable |
| 3 | Topic decomposition | build→device→chipset→i2c→sfp→led→counters→ztp→l3→patches | Dependency-ordered, maps to platform bring-up sequence |
| 4 | Submodule patches | Single topic branch | Only 9 small series, splitting adds overhead |
| 5 | Documentation level | Full sphinx/doxygen generation | "Show upstream how it should be done" |
| 6 | Doc location | `wedge100s-32x/docs/` | Merge-friendly, self-contained within platform dir |
| 7 | Creation method | Fresh file copy from working tree | Interleaved commits make rebase impractical |
| 8 | Repo strategy | Reset existing fork (B2) | Preserves GitHub fork relationship for discoverability and upstream PRs |
| 9 | Branch strategy | `upstream` tracking + `master` integrated | Clean separation of upstream vs. our work, easier release migration |
| 10 | Ongoing development | GitHub flow off `master` | Topic branches become historical after initial merge |
