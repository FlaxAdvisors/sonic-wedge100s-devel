---
name: wedge100s-branch-audit
description: Use periodically or before milestones to verify topic branch health — checks sync status, file ownership, documentation coverage, and completeness against the archive tag
---

# Wedge 100S Branch Audit

## Overview

Verifies all topic branches are healthy: synced with master, files on correct branches, documentation present, and no regressions from the archive source.

**Build host:** The fork lives on `play-sonic:/export/sonic/sonic-buildimage`. Run the shell blocks below from an interactive `ssh play-sonic` session, or wrap each block in `ssh play-sonic '…'`.

## When to Use

- Before building a full SONiC image (`sonic-broadcom.bin`)
- Before deploying to hardware
- After a batch of topic branch changes
- When starting a new development session (quick sanity check)
- On user request

## Audit Procedure

### Check 1: Branch Sync Status

Verify no topic branch is behind master (run from an interactive `ssh play-sonic` session):

```bash
cd /export/sonic/sonic-buildimage
git fetch origin
for b in build-infra device-identity chipset-config i2c-bmc-sysfs \
         sfp-optics led-pipeline flex-counters ztp l3-bgp \
         submodule-patches docs dev-build-only; do
  behind=$(git rev-list --count origin/wedge100s/$b..origin/master 2>/dev/null)
  if [ "$behind" -gt 0 ]; then
    echo "  STALE: wedge100s/$b is $behind commits behind master"
  else
    echo "  OK:    wedge100s/$b"
  fi
done
```

**Fix stale branches:**
```bash
git checkout wedge100s/<branch>
git merge origin/master --no-edit
git push origin wedge100s/<branch>
```

### Check 2: Archive Completeness

Verify merged master has all files from `archive/wedge100s-v1`:

```bash
cd /export/sonic/sonic-buildimage
missing=$(comm -23 \
  <(git ls-tree -r --name-only archive/wedge100s-v1 -- \
      platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/ \
      platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x* \
      device/accton/x86_64-accton_wedge100s_32x-r0/ \
      installer/platforms/x86_64-accton_wedge100s_32x-r0 \
    | grep -v __pycache__ | sort) \
  <(git ls-tree -r --name-only origin/master -- \
      platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/ \
      platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x* \
      device/accton/x86_64-accton_wedge100s_32x-r0/ \
      installer/platforms/x86_64-accton_wedge100s_32x-r0 \
    | grep -v __pycache__ | sort))

if [ -z "$missing" ]; then
  echo "  OK: All archive files present on master"
else
  echo "  MISSING from master:"
  echo "$missing" | sed 's/^/    /'
fi
```

### Check 3: Documentation Coverage

Verify Python and C files have documentation:

```bash
cd /export/sonic/sonic-buildimage
W=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x

echo "=== Python docstring coverage ==="
for f in $W/sonic_platform/*.py; do
  [ -f "$f" ] || continue
  name=$(basename "$f")
  args_count=$(grep -c 'Args:\|Returns:' "$f" 2>/dev/null || echo 0)
  def_count=$(grep -c '^\s*def ' "$f" 2>/dev/null || echo 0)
  printf "  %-25s defs=%s  Args/Returns=%s\n" "$name" "$def_count" "$args_count"
done

echo "=== C Doxygen coverage ==="
for f in $(find $W -name "*.c" -not -path "*/build/*"); do
  name=$(echo "$f" | sed "s|$W/||")
  brief_count=$(grep -c '@brief' "$f" 2>/dev/null || echo 0)
  func_count=$(grep -cE '^(static )?(int|void|ssize_t|struct|const|unsigned) ' "$f" 2>/dev/null || echo 0)
  printf "  %-40s funcs=%s  @brief=%s\n" "$name" "$func_count" "$brief_count"
done
```

**Flag files where `@brief` count < function count or `Args/Returns` is 0.**

### Check 4: File Ownership

Spot-check that files haven't drifted to wrong branches. For each topic branch, verify its owned files exist and no foreign files were added:

```bash
cd /export/sonic/sonic-buildimage

# Example: sfp-optics should own sfp.py and nothing else in sonic_platform/
sfp_files=$(git diff --name-only origin/wedge100s/sfp-optics...origin/wedge100s/i2c-bmc-sysfs -- \
  $W/sonic_platform/ 2>/dev/null)
echo "Files sfp-optics adds beyond i2c-bmc-sysfs:"
echo "$sfp_files" | sed 's/^/  /'
# Should only show sfp.py
```

### Check 5: Quilt Patch Health

```bash
cd /export/sonic/sonic-buildimage
for d in src/*.patch; do
  sub=$(basename "$d" .patch)
  [ -d "src/$sub" ] || continue
  pushd "src/$sub" > /dev/null
  quilt pop -a -f 2>/dev/null || true
  [ -d .pc ] && rm -rf .pc
  result=$(QUILT_PATCHES="../${sub}.patch" quilt push -a 2>&1)
  if echo "$result" | grep -q "FAILED"; then
    echo "  FAIL: $sub"
  else
    echo "  OK:   $sub"
  fi
  quilt pop -a -f 2>/dev/null || true
  [ -d .pc ] && rm -rf .pc
  popd > /dev/null
done
```

## Report Format

```
=== Wedge 100S Branch Audit ===
Date: YYYY-MM-DD

Branch Sync:     X/12 synced, Y stale
Archive Files:   N missing from master
Doc Coverage:    Python X/Y methods, C X/Y functions
Patch Health:    N/N submodules clean
Ownership:       [OK | issues found]

Action Items:
- (list any fixes needed)
```

## Quick Audit (30-second version)

For a fast sanity check, run just checks 1 and 2 (from an interactive `ssh play-sonic` session):

```bash
cd /export/sonic/sonic-buildimage && git fetch origin && \
for b in $(git branch -r | grep wedge100s | sed 's|origin/||'); do
  behind=$(git rev-list --count origin/$b..origin/master 2>/dev/null)
  [ "$behind" -gt 0 ] && echo "STALE: $b ($behind behind)"
done && \
comm -23 \
  <(git ls-tree -r --name-only archive/wedge100s-v1 -- \
      platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/ \
      device/accton/x86_64-accton_wedge100s_32x-r0/ \
    | grep -v __pycache__ | sort) \
  <(git ls-tree -r --name-only origin/master -- \
      platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/ \
      device/accton/x86_64-accton_wedge100s_32x-r0/ \
    | grep -v __pycache__ | sort) | \
  { read line && echo "MISSING FILES:" && echo "$line" && cat || echo "All files present"; }
```
