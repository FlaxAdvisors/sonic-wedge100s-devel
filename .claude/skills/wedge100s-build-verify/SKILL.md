---
name: wedge100s-build-verify
description: Use after merging any wedge100s topic branch to master, or after modifying submodule source — verifies quilt patches, builds the correct target for the changed component, and reports pass or fail with error context
---

# Wedge 100S Build Verification

## Overview

After merging a topic branch to master or modifying submodule source, verify the affected build target produces a clean artifact. A merge without build verification is incomplete.

**Build host:** `play-sonic:/export/sonic/sonic-buildimage` — reached via the `bang-fiesta` ProxyCommand in `~/.ssh/config`. The local workspace on foreman has no build tree, so every command below runs on play-sonic (either wrap in `ssh play-sonic '…'` or open an interactive `ssh play-sonic` and cd there).

## When to Use

- After `git merge origin/wedge100s/<topic>` into master
- After updating submodule patches
- Before declaring any task complete that touched platform code
- Before deploying artifacts to the target hardware

## Critical: BLDENV and Artifact Type Mapping

**Submodule packages** (in Docker containers) build in **bookworm**.
**Platform packages** (on host filesystem) build in **trixie**.
**Python-only packages** produce `.whl` wheels, not `.deb` files.

| Component | BLDENV | Artifact Type | Make Target |
|-----------|--------|--------------|-------------|
| Platform .deb (modules, utils, services) | trixie | `.deb` | `target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb` |
| swss / orchagent | bookworm | `.deb` | `target/debs/bookworm/swss_1.0.0_amd64.deb` |
| syncd | bookworm | `.deb` | `target/debs/bookworm/syncd_1.0.0_amd64.deb` |
| libsairedis | bookworm | `.deb` | `target/debs/bookworm/libsairedis_1.0.0_amd64.deb` |
| libswsscommon | bookworm | `.deb` | `target/debs/bookworm/libswsscommon_1.0.0_amd64.deb` |
| sonic-utilities | bookworm | `.whl` | `target/python-wheels/bookworm/sonic_utilities-1.2-py3-none-any.whl` |
| xcvrd | bookworm | `.whl` | `target/python-wheels/bookworm/sonic_xcvrd-1.0-py3-none-any.whl` |
| psud | bookworm | `.whl` | `target/python-wheels/bookworm/sonic_psud-1.0-py3-none-any.whl` |
| thermalctld | bookworm | `.whl` | `target/python-wheels/bookworm/sonic_thermalctld-1.0-py3-none-any.whl` |
| Full image | (both) | `.bin` | `target/sonic-broadcom.bin` (no BLDENV prefix) |

## Verification Procedure

### Step 1: Verify Quilt Patches

```bash
ssh play-sonic 'cd /export/sonic/sonic-buildimage && \
for d in src/*.patch; do
  sub=$(basename "$d" .patch)
  [ -d "src/$sub" ] || continue
  echo "=== $sub ==="
  pushd "src/$sub" > /dev/null
  quilt pop -a -f 2>/dev/null || true
  [ -d .pc ] && rm -rf .pc
  QUILT_PATCHES="../${sub}.patch" quilt push -a 2>&1
  quilt pop -a -f 2>/dev/null || true
  [ -d .pc ] && rm -rf .pc
  popd > /dev/null
done'
```

**If any patch fails:** Stop. Fix on `wedge100s/submodule-patches` using `sonic-submodule-patches` skill. Do not proceed.

### Step 2: Identify What to Build

Match the changed files to the correct build target:

| Changed Files | Build Command |
|--------------|---------------|
| `platform/.../wedge100s-32x/**` | `BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb` |
| `src/sonic-swss/**` | `BLDENV=bookworm make target/debs/bookworm/swss_1.0.0_amd64.deb` then `make target/docker-orchagent.gz` |
| `src/sonic-utilities/**` | `BLDENV=bookworm make target/python-wheels/bookworm/sonic_utilities-1.2-py3-none-any.whl` |
| `src/sonic-platform-daemons/**` | `BLDENV=bookworm make target/python-wheels/bookworm/sonic_xcvrd-1.0-py3-none-any.whl` (etc.) then `make target/docker-platform-monitor.gz` |
| `src/sonic-sairedis/**` | `BLDENV=bookworm make target/debs/bookworm/syncd_1.0.0_amd64.deb` then `make target/docker-syncd-brcm.gz` |
| `src/*.patch/**` (patch files only) | Build whatever the patched submodule produces |
| Multiple components | Build each affected target separately |

### Step 3: Clean and Build

```bash
# Clean stale artifact (append -clean to any target path)
ssh play-sonic 'cd /export/sonic/sonic-buildimage && make <target-path>-clean'

# Build
ssh play-sonic 'cd /export/sonic/sonic-buildimage && [BLDENV=<env>] make <target-path>'
```

### Step 4: Interpret Results

**Success:** `[ finished ]` message and artifact file exists.

**Common failures:**

| Error | Cause | Fix |
|-------|-------|-----|
| `No rule to make target` | `.mk` not included in `rules.mk` | Check `wedge100s/dev-build-only` or `wedge100s/build-infra` |
| `unknown package` | Missing from `debian/control` | Add stanza on `wedge100s/build-infra` |
| `cannot stat .../udev/*` | Missing `udev/` directory | Add udev rules on `wedge100s/build-infra` |
| `Hunk FAILED` in quilt | Patch context stale | `quilt push -f && quilt refresh` on `wedge100s/submodule-patches` |
| `.whl missing` in `.install` | Wheel not built by `debian/rules` | Check `sonic_platform_setup.py` and `debian/rules` build section |
| `modules/Makefile: No such file` | Missing kernel module skeleton | Add on `wedge100s/build-infra` |
| Wrong BLDENV (target not found) | Used trixie for a bookworm package | Check the BLDENV mapping table above |

### Step 5: Report

- **PASS** or **FAIL**
- If FAIL: error from `[ FAIL LOG START ]` to `[ FAIL LOG END ]`
- If PASS: artifact path and size

## Quick Reference — Platform .deb Only

```bash
ssh play-sonic 'cd /export/sonic/sonic-buildimage && \
  git checkout master && git pull origin master && \
  rm -f target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb && \
  BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb && \
  ls -la target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb'
```

To pull an artifact back to this host after a successful build:

```bash
scp play-sonic:/export/sonic/sonic-buildimage/target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb ~/Downloads/
# or for a full image
scp play-sonic:/export/sonic/sonic-buildimage/target/sonic-broadcom.bin ~/Downloads/
```
