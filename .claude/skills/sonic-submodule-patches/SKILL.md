---
name: sonic-submodule-patches
description: Use when modifying sonic-buildimage submodules and needing changes to survive make distclean, make init, or git submodule reset — managing the quilt patch workflow to capture local edits as versioned patch files
---

# SONiC Submodule Patch Workflow

## Overview

SONiC submodules live under `src/` and are reset by `make init` and `make distclean`. To preserve changes, store them as quilt-format patch files in `src/{submodule}.patch/`. The build system (`slave.mk`) auto-detects and applies these patches before each build using quilt.

**Build host:** All quilt work runs on `play-sonic:/export/sonic/sonic-buildimage` (reached via the `bang-fiesta` ProxyCommand). The foreman workspace has no submodule trees — `ssh play-sonic` in first, or wrap commands in `ssh play-sonic '…'`.

## Directory Layout

```
src/
  sonic-utilities/             ← git submodule (ephemeral, wiped by make init)
  sonic-utilities.patch/       ← patch dir (tracked in main repo, survives reset)
    series                     ← ordered list of patch filenames
    0001-my-feature.patch      ← unified diff patches
    0002-another-fix.patch
```

**Key rule:** The `.patch/` directory is a sibling of the submodule, named `{submodule-dir}.patch/`.

## Creating a Patch from Submodule Changes

When you've edited files inside a submodule and want to preserve them:

```bash
# 1. Go to the submodule
cd src/sonic-utilities

# 2. Commit your changes inside the submodule (creates a git commit)
git add -p                    # or git add <files>
git commit -m "describe change"

# 3. Export as a patch file
git format-patch HEAD~1 --output-directory ../sonic-utilities.patch/

# 4. Create or update the series file
ls ../sonic-utilities.patch/*.patch | xargs -n1 basename > ../sonic-utilities.patch/series

# 5. Return to main repo and commit the .patch/ directory
cd ../..
git add src/sonic-utilities.patch/
git commit -m "sonic-utilities: add patch for <feature>"
```

The `series` file must list patch filenames (not full paths), one per line, in apply order.

## After make init or make distclean (Re-applying Patches Manually)

The build system applies patches automatically. For manual verification:

```bash
cd src/sonic-utilities
# Remove any previously applied patches first (safe, idempotent)
quilt pop -a -f 2>/dev/null || true
# Apply all patches from series
QUILT_PATCHES=../sonic-utilities.patch quilt push -a
```

To remove patches and restore clean submodule state:

```bash
cd src/sonic-utilities
quilt pop -a -f
[ -d .pc ] && rm -rf .pc
```

## How slave.mk Applies Patches (Auto, No Manual Step)

`slave.mk` applies patches before every build and removes them after:

```make
# Apply (before build)
if [ -f $($*_SRC_PATH).patch/series ]; then
    pushd $($*_SRC_PATH) && \
    ( quilt pop -a -f 1>/dev/null 2>&1 || true ) && \
    QUILT_PATCHES=../$(notdir $($*_SRC_PATH)).patch quilt push -a; \
    popd; fi

# Remove (after build)
if [ -f $($*_SRC_PATH).patch/series ]; then
    pushd $($*_SRC_PATH) && quilt pop -a -f; \
    [ -d .pc ] && rm -rf .pc; popd; fi
```

The `_SRC_PATH` for a package is defined in `rules/{package}.mk`, e.g.:
```make
$(SONIC_UTILITIES_PY3)_SRC_PATH = $(SRC_PATH)/sonic-utilities
```

## Adding a New Patch to an Existing Series

```bash
cd src/sonic-utilities

# Apply existing patches first so you're editing on top of them
quilt pop -a -f 2>/dev/null || true
QUILT_PATCHES=../sonic-utilities.patch quilt push -a

# Make your edits, then commit in the submodule
git add <files>
git commit -m "my new change"

# Export only the new commit
git format-patch HEAD~1 --output-directory ../sonic-utilities.patch/

# Append to series file
ls ../sonic-utilities.patch/*.patch | sort | xargs -n1 basename > ../sonic-utilities.patch/series

cd ../..
git add src/sonic-utilities.patch/
git commit -m "sonic-utilities: add patch for <new change>"
```

## Checking What Patches Exist

```bash
# List all submodules with patch directories
ls -d src/*.patch/ 2>/dev/null

# Show series for a given submodule
cat src/sonic-utilities.patch/series

# Verify quilt can apply all patches cleanly
cd src/sonic-utilities && quilt pop -a -f 2>/dev/null || true
QUILT_PATCHES=../sonic-utilities.patch quilt push -a && echo "ALL PATCHES APPLY OK"
```

## When a Patch Fails to Apply

If `quilt push -a` fails (submodule was updated upstream):

```bash
cd src/sonic-utilities
quilt push                  # applies next failing patch, leaves conflict markers
# Edit the conflict, then:
quilt refresh               # updates the patch with your resolution
quilt push -a               # continue applying remaining patches
```

Then re-export the updated patch:
```bash
git diff > ../sonic-utilities.patch/000N-updated-patch.patch
# Update series file accordingly
```

## What Survives make distclean / make init

| Item | Survives? |
|------|-----------|
| `src/{submodule}/` edits | **NO** — wiped by `git submodule update --init` |
| `src/{submodule}.patch/` | **YES** — tracked in main repo, not in submodule |
| `.pc/` quilt state dirs | **NO** — ephemeral, inside submodule dir |
| Built `.deb` in `target/` | **NO** — wiped by distclean |

**Rule:** Never store changes only inside a submodule. Always export to the `.patch/` directory before running `make init`.

## Quick Reference

| Task | Command |
|------|---------|
| Export submodule commit as patch | `git format-patch HEAD~1 --output-directory ../{sub}.patch/` |
| Update series file | `ls ../{sub}.patch/*.patch \| sort \| xargs -n1 basename > ../{sub}.patch/series` |
| Apply patches manually | `QUILT_PATCHES=../{sub}.patch quilt push -a` |
| Remove patches manually | `quilt pop -a -f && rm -rf .pc` |
| Test patch applies cleanly | `quilt pop -a -f 2>/dev/null; QUILT_PATCHES=../{sub}.patch quilt push -a` |
| List patched submodules | `ls -d src/*.patch/` |
