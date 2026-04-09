---
name: wedge100s-topic-branches
description: Use when making any change to the FlaxAdvisors/sonic-buildimage fork — guides the topic branch workflow for maintaining merge-ready platform code on the wedge100s port
---

# Wedge 100S Topic Branch Workflow

## Overview

All changes to `FlaxAdvisors/sonic-buildimage` go through topic branches that PR into `master`. Master is the integrated, merge-ready state. This keeps the git history clean, grouped by functionality, and theoretically mergeable upstream.

## Branch Structure

```
upstream                        ← read-only mirror of sonic-net/sonic-buildimage:202511
master                          ← upstream + merged topic PRs = buildable image
wedge100s/<topic>               ← feature/fix branches, PR into master
archive/wedge100s-v1            ← tag: safety snapshot of original work
```

## The 10 Topic Branches

| Branch | Scope | Depends On |
|---|---|---|
| `wedge100s/build-infra` | Build system (mk files, installer, skeleton) | — |
| `wedge100s/device-identity` | Device tree, hwsku, platform init, base API | build-infra |
| `wedge100s/chipset-config` | BCM config.bcm, LEDUP SOC bytecodes | device-identity |
| `wedge100s/i2c-bmc-sysfs` | I2C/BMC daemons, environmentals API | device-identity |
| `wedge100s/sfp-optics` | SFP platform API, EEPROM caching | i2c-bmc-sysfs |
| `wedge100s/led-pipeline` | LED control, ledup-linkstate, diagnostics | chipset-config + i2c-bmc-sysfs |
| `wedge100s/flex-counters` | Hardware counter daemon | chipset-config |
| `wedge100s/ztp` | L2 ZTP configuration | device-identity |
| `wedge100s/l3-bgp` | L3 config generator, BGP templates | ztp |
| `wedge100s/submodule-patches` | Quilt series for upstream submodule fixes | — (independent) |

## Making a Change

### Step 1: Determine which topic branch owns the files

Match the files you're changing to a topic branch from the table above. If unsure:
- `device/accton/x86_64-accton_wedge100s_32x-r0/` → device-identity, chipset-config, ztp, or l3-bgp (by file)
- `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/` → device-identity (base), i2c-bmc-sysfs (fan/psu/thermal/bmc), sfp-optics (sfp.py)
- `platform/.../wedge100s-32x/flex-counter-daemon/` → flex-counters
- `platform/.../wedge100s-32x/utils/wedge100s-led-*` → led-pipeline
- `platform/.../wedge100s-32x/utils/wedge100s-i2c-*` or `wedge100s-bmc-*` → i2c-bmc-sysfs
- `src/*.patch/` → submodule-patches
- Build files (`platform-modules-accton.mk`, `one-image.mk`, `debian/rules`) → build-infra

### Step 2: Update the topic branch

```bash
# Fetch latest master
git fetch origin master

# Check out the topic branch
git checkout wedge100s/<topic>

# Merge master into it (to pick up any changes from other merged topics)
git merge origin/master --no-edit

# Make your changes, commit with conventional-commit style
git add <files>
git commit -m "fix(<scope>): description of what and why"

# Push
git push origin wedge100s/<topic>
```

### Step 3: PR into master

```bash
gh pr create --base master --head wedge100s/<topic> \
  --title "wedge100s: short description" \
  --body "What changed and why."
```

Then merge the PR (merge commit, not squash — preserves individual commits).

### Step 4: Update the clean build clone

If you maintain a clean build at `/export/sonic/sonic-buildimage`:
```bash
cd /export/sonic/sonic-buildimage
git pull origin master
```

## Fix Spanning Multiple Topic Branches

If a fix touches files owned by different topics, either:

1. **Split into separate commits on separate branches** — preferred if the changes are independent
2. **Branch off master** with a descriptive name like `wedge100s/fix-boot-hang` and PR directly — use when the fix genuinely spans concerns

## Submodule Patch Changes

Submodule patches follow the same topic branch flow but also require the quilt workflow. See the `sonic-submodule-patches` skill for the quilt mechanics. The git flow is:

```bash
git checkout wedge100s/submodule-patches
git merge origin/master --no-edit

# Apply quilt patches, make changes, export new patch
# (see sonic-submodule-patches skill)

git add src/<submodule>.patch/
git commit -m "fix(patches): description"
git push origin wedge100s/submodule-patches

# PR into master
gh pr create --base master --head wedge100s/submodule-patches \
  --title "wedge100s: update <submodule> patches" \
  --body "Description."
```

## Syncing with Upstream

When `sonic-net/sonic-buildimage:202511` gets updates:

```bash
# Update the upstream tracking branch
git fetch upstream 202511
git push origin upstream/202511:upstream

# Merge upstream into master
git checkout master
git merge upstream --no-edit
git push origin master

# Then update each topic branch as needed
git checkout wedge100s/<topic>
git merge origin/master --no-edit
# Resolve any conflicts
git push origin wedge100s/<topic>
```

## Commit Message Convention

```
feat(<scope>): add new capability
fix(<scope>): correct broken behavior
docs(<scope>): documentation only
refactor(<scope>): no behavior change
test(<scope>): test additions or fixes
```

Scopes: `build`, `device`, `platform`, `memory`, `i2c`, `bmc`, `sysfs`, `sfp`, `led`, `led-diag`, `counters`, `ztp`, `l3`, `patches`, `postinst`, `service`, `rc.local`

## Build Verification

After merging a PR, verify the platform .deb still builds:

```bash
cd /export/sonic/sonic-buildimage
git pull origin master
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

## What NOT to Do

- **Do not commit directly to master** — always go through a topic branch + PR
- **Do not force-push topic branches** — other branches may have merged from them
- **Do not add devel artifacts** (tests, notes, tools) — those go in `FlaxAdvisors/sonic-wedge100s-devel`
- **Do not comment out other platforms** in shared build files — use `patches/wedge100s-only-build.sh` locally instead
