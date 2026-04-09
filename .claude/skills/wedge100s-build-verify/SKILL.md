---
name: wedge100s-build-verify
description: Use after merging any wedge100s topic branch to master — runs the platform .deb build, verifies quilt patches apply, and reports pass or fail with specific error context
---

# Wedge 100S Build Verification

## Overview

After merging a topic branch to master, verify the platform .deb builds cleanly. A merge without build verification is incomplete.

## When to Use

- After `git merge origin/wedge100s/<topic>` into master
- After updating submodule patches
- Before declaring any task complete that touched platform code
- Before deploying a `.deb` to the target hardware

## Verification Procedure

### Step 1: Verify Quilt Patches

Before building, confirm all submodule patches apply cleanly:

```bash
cd /export/sonic/sonic-buildimage
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
done
```

**If any patch fails:** Stop. Fix the patch on `wedge100s/submodule-patches` using the `sonic-submodule-patches` skill (quilt refresh workflow). Do not proceed to build.

### Step 2: Clean Stale Artifacts

```bash
cd /export/sonic/sonic-buildimage
rm -f target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

### Step 3: Build Platform .deb

```bash
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

This can take 5-15 minutes depending on cache state.

### Step 4: Interpret Results

**Success indicators:**
```
[ finished ] [ target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb ]
```
And the file exists:
```bash
ls -la target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

**Common failure modes and fixes:**

| Error | Cause | Fix |
|-------|-------|-----|
| `No rule to make target` | `platform-modules-accton.mk` not included in `rules.mk` | Uncomment include on `wedge100s/dev-build-only` |
| `unknown package sonic-platform-accton-wedge100s-32x` | Missing from `debian/control` | Add package stanza on `wedge100s/build-infra` |
| `cannot stat .../udev/*` | Missing `udev/` directory | Add udev rules on `wedge100s/build-infra` |
| `Hunk FAILED` in quilt patch | Submodule code changed, patch context stale | Use `quilt push -f && quilt refresh` on `wedge100s/submodule-patches` |
| `sonic_platform-1.0-py3-none-any.whl missing` | `.install` file references wheel not built | Verify `sonic_platform_setup.py` exists and `debian/rules` builds it |
| `modules/Makefile: No such file` | Missing kernel module skeleton | Add `modules/` dir on `wedge100s/build-infra` |

### Step 5: Report

After build completes, report:
- **PASS** or **FAIL**
- If FAIL: the specific error line from `[ FAIL LOG START ]` to `[ FAIL LOG END ]`
- If PASS: the .deb file size and path

## Quick Reference

```bash
# Full verify sequence (copy-paste ready)
cd /export/sonic/sonic-buildimage
git checkout master
git pull origin master
rm -f target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
ls -la target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```
