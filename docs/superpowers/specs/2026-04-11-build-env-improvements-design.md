# Build Environment Improvements Design

**Date:** 2026-04-11
**Status:** Draft

## Purpose

The SONiC build environment for this fork hits repeated friction points that
cost hours per session. This spec catalogs the failure modes observed during
the 2026-04-09 and 2026-04-11 porting sessions and proposes targeted fixes.
The goal is a build environment that is **trustworthy** (no silent failures),
**inspectable** (cache decisions are visible), and **durable** across upstream
syncs (customizations don't silently drift).

## Non-goals

- Rewriting `slave.mk` or replacing the upstream SONiC build system
- Migrating away from Docker-based per-distribution builders
- Changing the topic branch or quilt submodule workflow (separate concerns)

## Observed failure modes

Each numbered item is a real issue hit this session, with time cost and root
cause.

### F1. Dead config vars
- **Symptom:** `BUILD_SKIP_TEST = y` in `rules/config.user` had no effect. A
  flaky upstream `sonic-host-services` wheel test (`test_execute_reboot_fail_halt_timeout`)
  killed a 1.5 hr build.
- **Root cause:** The var was declared in `rules/config.user` but never
  referenced in `slave.mk`. No validator caught this.
- **Fix applied this session:** Wired `BUILD_SKIP_TEST` into 5 sites in
  `slave.mk` (one `else ifeq` plus 4 `_TEST` guards).
- **Preventative:** Parse-time validator.

### F2. Silent loss of customizations on upstream rebase
- **Symptom:** After rebasing the fork on fresh upstream 202511, at least
  9 wedge100s customizations in `files/` were silently lost: `MGMT_PORT|eth0`
  init_cfg stanza (caused eth0 to not DHCP on first boot), chrony
  `After=interfaces-config`, chrony mgmt VRF bindacqdevice, `set-vrf-strict-mode`
  service, `bmc_config.json.j2` template, cipher-pass persistence hooks,
  `interfaces-config.sh` retry loop, and 4 flag path regressions in
  `rc.local`/`config-setup`.
- **Root cause:** No inventory of which files in this fork are upstream vs.
  customized. Rebase merge succeeded without flagging.
- **Time cost this session:** ~4 hours to rediscover and re-port.

### F3. Kernel module silently missing from `.deb`
- **Symptom:** `wedge100s_cpld.ko` built successfully but was not included in
  the platform `.deb`. Sysfs attributes never appeared on hardware after
  install. No error message anywhere.
- **Root cause:** `debian/rules` `modules_install` target had wrong `M=`
  (pointed at top-level Accton dir instead of `wedge100s-32x/modules`) and
  wrong `INSTALL_MOD_PATH` (wrote to a throwaway `debian/platform-modules-*`
  dir instead of the package staging dir).
- **Fix applied this session:** Corrected both paths in `debian/rules` to
  match the working `.claude` build env.
- **Preventative:** Post-build assertion that every `.ko` under the module
  source dir appears in `dpkg-deb -c` of the produced `.deb`.

### F4. Incremental build misses newly-created files
- **Symptom:** Created new files in `files/image_config/` (e.g.
  `set-vrf-strict-mode.service`, cipher hook scripts) but the squashfs did not
  regenerate because those files are not in the `.squashfs.dep` list.
- **Root cause:** The `.squashfs.dep` file is a static snapshot captured
  during the previous build, not a live glob. New files are invisible to
  incremental rebuild.
- **Workaround:** `rm target/sonic-broadcom.bin target/*.squashfs*` to force
  full regeneration.

### F5. dpkg-cache decisions are opaque
- **Symptom:** Can't tell whether a `.deb` came from cache or was freshly
  rebuilt, or why the cache decided one way or the other.
- **Root cause:** Cache logic is embedded in `scripts/dpkg_cache.sh` with
  no per-target diagnostic output.

### F6. Wheel test suites run by default
- **Symptom:** `bdist_wheel` runs `setup.py test` or `pytest` for every
  Python package SONiC builds (~15 wheels). Upstream test flakes are caught
  here and cost hours.
- **Root cause:** `slave.mk` runs tests for every wheel build unless
  per-wheel `_TEST = n` is set. Not easy to disable globally.
- **Fix applied this session:** `BUILD_SKIP_TEST=y` plumbing (F1).

### F7. BMC / platform env var propagation is error-prone
- **Symptom:** Adding `BMC_NOS_ACCOUNT_USERNAME` and
  `BMC_ROOT_ACCOUNT_DEFAULT_PASSWORD` required editing 3 separate
  `docker run ... \` invocations in `slave.mk` (lines 1419, 1686, 1713)
  because env vars are listed per-invocation.
- **Root cause:** No common helper / variable expansion for wedge100s-specific
  build env.

### F8. fsroot-* directories are root-owned and opaque
- **Symptom:** `du -sh fsroot-broadcom` fails with permission errors for
  `run/docker`, `run/containerd`, `run/sudo`. `ls fsroot-broadcom/etc/sonic/`
  requires sudo. Can't easily verify what ended up in the rootfs after a build.
- **Root cause:** `build_debian.sh` runs as root via `sudo`, leaving the
  rootfs with root ownership.
- **Workaround:** `sudo` every inspection command.

### F9. Build artifacts leak into `git status`
- **Symptom:** Development-tree `git status` shows dozens of `tests/*/__pycache__/`,
  `tests/reports/`, `tests/timing.log`, `tools/tasks/__pycache__/` entries,
  plus root-owned `fsroot-*` junk on the buildimage side. Actual changes are
  drowned out.
- **Root cause:** `.gitignore` doesn't cover these patterns in both repos.

### F10. Platform `.deb` doesn't auto-rebuild on source change
- **Symptom:** `make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb`
  reports "up to date" even when platform source files have changed. Requires
  manual `rm` of the target file to force rebuild.
- **Root cause:** Make dependency tracking for platform `.deb`s does not
  include the full `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
  source tree; it tracks only the explicit prerequisite list in the `.mk` file.

### F11. slave.mk modifications add upstream-sync friction
- **Symptom:** `BUILD_SKIP_TEST`, BMC env var propagation, and other fixes
  live inline in `slave.mk`. Every upstream sync risks conflict on these
  edits.
- **Root cause:** No extension mechanism for platform-specific slave.mk
  customizations.

## Proposed work

Organized by phase from "stop bleeding" to "long-term hygiene".

### Phase 1 — Stop the bleeding (trust the build)

**P1.1** — **Config var validator** (fixes F1)

Add `tools/validate-config-user.sh` that:
- Parses every `VAR = value` from `rules/config.user` and `rules/config`
- Greps for references in `slave.mk`, `Makefile.work`, `build_debian.sh`,
  `files/**/*.j2`, `files/**/*.sh`
- Prints a dead-var warning for any declared-but-unused var
- Runs automatically as the first step of every `make target/...` invocation
  (via a `.platform` prerequisite rule)

**P1.2** — **Kernel module presence assertion** (fixes F3)

Add to `platform/broadcom/sonic-platform-modules-accton/debian/rules`:
```make
override_dh_builddeb:
    dh_builddeb
    for mod in $(MODULE_DIRS); do \
        for ko in $$(find $$mod/modules -name '*.ko'); do \
            name=$$(basename $$ko); \
            if ! dpkg-deb -c debian/$(PACKAGE_PRE_NAME)-$$mod*.deb | grep -q "$$name"; then \
                echo "ERROR: $$name was built but is not in the .deb" >&2; \
                exit 1; \
            fi; \
        done; \
    done
```

**P1.3** — **Rootfs dep includes image_config tree** (fixes F4)

In `slave.mk`, amend the `SONIC_RFS_TARGETS` rule prerequisite list to
include a wildcard over `files/image_config/` and `files/build_templates/`:
```make
$(addprefix $(TARGET_PATH)/, $(SONIC_RFS_TARGETS)) : $(TARGET_PATH)/% : \
    .platform \
    build_debian.sh \
    $(shell find files/image_config files/build_templates -type f) \
    ...
```

This causes `build_debian.sh` to re-run whenever any file in the image
template tree changes, including new files.

**P1.4** — **Platform .deb source tree tracking** (fixes F10)

In `platform/broadcom/platform-modules-accton.mk`:
```make
$(ACCTON_WEDGE100S_32X_PLATFORM_MODULE)_DEPENDS += $(shell find \
    platform/broadcom/sonic-platform-modules-accton/wedge100s-32x -type f)
```

So any source edit under the platform tree invalidates the `.deb`.

### Phase 2 — Drift protection (rebasing is safe)

**P2.1** — **Customization manifest** (fixes F2)

Create `docs/wedge100s-customizations.md`, a living inventory of every file
in this fork that differs from pristine upstream 202511:

```markdown
# Wedge 100S Customization Inventory

## files/build_templates/init_cfg.json.j2
Reason: MGMT_PORT|eth0|admin_status=up default so eth0 brings up DHCP on
first boot with the t1 preset.
Diff scope: +6 lines
Upstream owner: none (wedge100s-specific)

## files/image_config/chrony/override.conf
Reason: Order chronyd After=interfaces-config so chrony doesn't start
before eth0 has DHCP.
Diff scope: +1 line
...
```

Every new customization lands with a manifest entry; upstream rebases must
walk the manifest and verify each entry still applies.

**P2.2** — **Drift detector** (fixes F2)

`tools/detect-upstream-drift.sh` that:
- Fetches `upstream/202511`
- For each file in the manifest, `git diff upstream/202511 -- <path>` and
  reports whether the customization is still present
- Flags entries where the diff is now empty (customization lost) or
  substantially different (upstream changed the surrounding code)

Run before and after every upstream rebase.

### Phase 3 — Ergonomics

**P3.1** — **Build diagnostic script** (fixes F5)

`tools/build-cache-diag.sh`:
- Reads the build log
- Prints table of every package: `HIT` / `MISS` / `BUILT` / `SKIPPED`
- For MISS entries, shows why (source hash diff, missing deps, etc.)
- Prints total cache efficiency percentage

**P3.2** — **Wedge100s env var helper** (fixes F7)

Define a single multi-line variable in `slave.mk`:
```make
WEDGE100S_BUILD_ENV = \
    BMC_NOS_ACCOUNT_USERNAME="$(BMC_NOS_ACCOUNT_USERNAME)" \
    BMC_ROOT_ACCOUNT_DEFAULT_PASSWORD="$(BMC_ROOT_ACCOUNT_DEFAULT_PASSWORD)" \
    WEDGE100S_BUILD_TAG="$(WEDGE100S_BUILD_TAG)"
```

and use `$(WEDGE100S_BUILD_ENV)` in each docker-run invocation instead of
copy-pasting each var.

**P3.3** — **Fresh rootfs target** (fixes F4, F8)

Add `make fresh-rfs`:
```make
fresh-rfs:
    sudo rm -rf fsroot-*
    rm -f target/sonic-broadcom.bin target/*.squashfs*
    @echo "Rootfs state cleared. Run 'make target/sonic-broadcom.bin' to rebuild."
```

**P3.4** — **.gitignore cleanup** (fixes F9)

Both `sonic-wedge100s-devel` and `sonic-buildimage`:
```
__pycache__/
*.pyc
tests/reports/
tests/timing.log
tests/**/__pycache__/
tools/**/__pycache__/
fsroot-*/
fsroot.docker.*/
```

### Phase 4 — Long-term hygiene

**P4.1** — **slave.mk extension point** (fixes F11)

At the end of upstream `slave.mk`:
```make
-include wedge100s.mk
```

Move all wedge100s customizations (`BUILD_SKIP_TEST` wiring, `WEDGE100S_BUILD_ENV`,
etc.) to `wedge100s.mk`. Upstream syncs never touch `slave.mk` edits
because there are none — everything wedge100s lives in the -include.

**P4.2** — **Config var isolation**

Same idea for config:
```
rules/
├── config             (upstream)
├── config.user        (user overrides)
└── wedge100s.config   (platform-specific)
```

`Makefile.work` already -includes `rules/config.user`; add `rules/wedge100s.config`
to the include chain.

**P4.3** — **Build progress summary**

At end of `make target/sonic-broadcom.bin`, print:
```
===== Build Summary =====
Elapsed: 47m12s
Packages cached: 183 / 207 (88%)
Packages rebuilt: 24
Wheel tests run: 0 (BUILD_SKIP_TEST=y)
Submodule patches applied: 4
.ko files in platform .deb: 1 (wedge100s_cpld.ko)
.bin size: 1003 MB
==========================
```

## Priority and sequencing

| Phase | Priority | Rationale |
|-------|----------|-----------|
| P1 — Trust | **Critical** | Silent failures are the highest-cost bugs. Must be fixed before any other work |
| P2 — Drift protection | **High** | Every rebase is a new chance to lose customizations. Manifest + detector stop the bleed |
| P3 — Ergonomics | **Medium** | Quality-of-life, reduces per-session friction |
| P4 — Long-term hygiene | **Low** | Clean but not blocking; do when rebuilding slave.mk patches |

## Success criteria

1. Running `make target/sonic-broadcom.bin` with `BUILD_SKIP_TEST=y` never
   invokes `pytest` or `setup.py test` for any wheel build
2. Adding a new file under `files/image_config/` reliably causes the next
   incremental build to regenerate the squashfs without manual artifact removal
3. Kernel modules in the platform tree are guaranteed to appear in the
   produced platform `.deb`, or the build fails loudly
4. After an upstream rebase, `tools/detect-upstream-drift.sh` surfaces every
   lost customization within a single run; zero customizations lost without
   flagging
5. `git status` in both repos shows only intentional changes — no
   `__pycache__/`, no test artifacts, no root-owned rootfs dirs
6. A new platform-specific build env var can be added by editing **one** line
   in `wedge100s.mk` (or equivalent) instead of 3+ sites in `slave.mk`

## What this spec does not address

- CI/CD pipeline integration (assumes local-only builds for now)
- Cross-compile support for non-x86 targets
- Upstream SONiC PR workflow (that belongs in the clean-fork spec)
- The actual Python test suite (`tests/stage_*`) — that's an unrelated
  concern; this spec is about the *build system*, not the *test system*

## Open questions

1. **P2 manifest granularity** — should `docs/wedge100s-customizations.md` be
   a hand-maintained file or generated from git blame / branch walking?
2. **P1.3 performance** — will `find files/image_config` on every build add
   noticeable overhead? Probably not, but worth measuring.
3. **P4.1 compatibility** — does `-include wedge100s.mk` at the bottom of
   slave.mk actually work across all upstream variants, or does slave.mk have
   early-bound variables that need wedge100s.mk to be included earlier?
4. **Kernel module installation** — should the `.ko` actually be packaged in
   the `.deb` as we do now, or should it live in the `.bin` rootfs overlay
   (the way AS7712 does)? Need to compare with working Accton platforms to
   pick the idiomatic approach.
