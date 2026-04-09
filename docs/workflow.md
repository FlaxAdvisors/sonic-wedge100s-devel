# Wedge 100S Development Workflow

**This document is the authoritative reference for all development on `FlaxAdvisors/sonic-buildimage`.** CLAUDE.md loads this file. Every contributor (human or AI) must follow these rules without exception.

### Skills That Enforce This Workflow

| Skill | When to Load | What It Enforces |
|-------|-------------|-----------------|
| `wedge100s-topic-branches` | Any change to `FlaxAdvisors/sonic-buildimage` | Branch ownership, merge workflow, commit conventions |
| `sonic-submodule-patches` | Any change inside `src/<submodule>/` | Quilt patch export, series management, conflict resolution |
| `wedge100s-doc-check` | Before committing `.py` or `.c` files | Verify docstrings/Doxygen present on modified functions |
| `wedge100s-build-verify` | After merging any topic branch to master | Run platform .deb build, verify patches, report pass/fail |
| `wedge100s-branch-audit` | Periodically or before milestones | Branch sync, file ownership, doc coverage, archive completeness |

---

## 1. Topic Branch Discipline

**All changes to `FlaxAdvisors/sonic-buildimage` go through topic branches.**

### Rules

1. **Never commit directly to master.** Master is the merge target, not a development branch.
2. **Every change goes to the topic branch that owns the affected files.** See the ownership table below.
3. **Commit, push, then merge to master.** The sequence is always: edit on topic branch, push to remote, merge into master (merge commit, not squash).
4. **Do not cross-contaminate branches.** If a change touches files owned by two branches, split it into separate commits on separate branches. Only use a cross-cutting branch (`wedge100s/fix-<description>`) when the change is genuinely atomic and inseparable.

### Topic Branch Ownership

| Branch | Owns These Files |
|--------|-----------------|
| `wedge100s/build-infra` | `platform-modules-accton.mk`, `one-image.mk`, `debian/rules`, `debian/control`, `debian/*.install`, `installer/platforms/`, `modules/`, `udev/`, `README` |
| `wedge100s/device-identity` | `device/accton/x86_64-accton_wedge100s_32x-r0/` (except chipset, LED, ZTP files), `sonic_platform/{platform,chassis,eeprom,component,watchdog,platform_smbus}.py`, `utils/accton_wedge100s_util.py`, `debian/postinst` (base sections), `debian/prerm`, `service/wedge100s-{pre-shutdown,platform-init}.service` |
| `wedge100s/chipset-config` | `*.config.bcm`, `led_proc_init.soc` |
| `wedge100s/i2c-bmc-sysfs` | `utils/wedge100s-{i2c-daemon,bmc-daemon,bmc-auth}.c`, `utils/wedge100s-bus-reset.sh`, `sonic_platform/{bmc,fan,psu,thermal}.py`, `service/wedge100s-{i2c-daemon,bmc-daemon}.service`, `debian/postinst` (daemon enable sections) |
| `wedge100s/sfp-optics` | `sonic_platform/sfp.py` |
| `wedge100s/led-pipeline` | `plugins/led_control.py`, `utils/wedge100s-{ledup-linkstate,led-diag,led-diag-bmc,_ledup}.py`, `utils/clear_led_diag.sh`, `service/wedge100s-ledup-linkstate.service`, `debian/postinst` (ledup enable section) |
| `wedge100s/flex-counters` | `flex-counter-daemon/*`, `service/wedge100s-flex-counter-daemon.service`, `debian/postinst` (flex-counter enable section) |
| `wedge100s/ztp` | `device/.../ztp/*` |
| `wedge100s/l3-bgp` | L3 config generators, BGP templates |
| `wedge100s/submodule-patches` | `src/*.patch/` directories (quilt patch series) |
| `wedge100s/docs` | `docs/` directory ONLY (Sphinx conf.py, .rst files, architecture docs, Makefile). Does NOT own in-code docstrings or Doxygen headers. |
| `wedge100s/dev-build-only` | `platform/broadcom/rules.mk` (commented-out platforms), `platform-modules-accton.mk` (wedge100s-only). NEVER merge upstream. |

### Workflow for a Change

```bash
# 1. Identify the owning branch
#    (check the table above)

# 2. Check out the branch and sync with master
git checkout wedge100s/<topic>
git merge origin/master --no-edit

# 3. Make changes, including documentation (see Section 3)
#    ...edit files...

# 4. Commit with conventional-commit style
git add <files>
git commit -m "fix(<scope>): description"

# 5. Push
git push origin wedge100s/<topic>

# 6. Merge to master
git checkout master
git merge origin/wedge100s/<topic> --no-edit
git push origin master
```

---

## 2. Submodule Patch Workflow

**Any change inside `src/<submodule>/` will be destroyed by `make init`.** Changes must be captured as quilt patches in `src/<submodule>.patch/`.

### Rules

1. **Never leave uncommitted submodule edits.** If you edited a file under `src/`, export it as a patch before ending the session.
2. **Use quilt for conflict resolution.** When a patch fails to apply, use `quilt push -f` then `quilt refresh` — do not hand-edit patch files.
3. **All submodule patch work goes on `wedge100s/submodule-patches`.** Not on master, not on other topic branches.
4. **Test patches apply cleanly** before committing:
   ```bash
   cd src/<submodule>
   quilt pop -a -f 2>/dev/null || true
   [ -d .pc ] && rm -rf .pc
   QUILT_PATCHES=../<submodule>.patch quilt push -a
   ```

### Creating a New Patch

```bash
cd src/<submodule>

# Apply existing patches first
quilt pop -a -f 2>/dev/null || true
QUILT_PATCHES=../<submodule>.patch quilt push -a

# Make edits, then commit in the submodule
git add <files>
git commit -m "describe change"

# Export as patch
git format-patch HEAD~1 --output-directory ../<submodule>.patch/

# Update series
ls ../<submodule>.patch/*.patch | sort | xargs -n1 basename > ../<submodule>.patch/series

# Return to main repo, commit on the right branch
cd ../..
git checkout wedge100s/submodule-patches
git add src/<submodule>.patch/
git commit -m "fix(patches): description"
git push origin wedge100s/submodule-patches
```

### When a Patch Fails to Apply

```bash
cd src/<submodule>
quilt push -f          # force-apply, saves rejects
# Fix the conflict in the file (not the .rej)
quilt refresh          # regenerates the patch with correct context
quilt push -a          # continue with remaining patches
```

---

## 3. Documentation Rules

**Documentation is not optional. It is part of every code change.**

### Rule: Docstrings and Doxygen Live With the Code

In-code documentation (Python docstrings, C Doxygen headers) is owned by the **same topic branch** that owns the code. When you modify a function, you update its docstring on the same branch, in the same commit.

The `wedge100s/docs` branch owns ONLY:
- Sphinx infrastructure (`docs/conf.py`, `docs/Makefile`, `docs/.gitignore`)
- `.rst` documentation files (`docs/index.rst`, `docs/architecture.rst`, `docs/api/*.rst`, `docs/daemons/*.rst`, `docs/guides/*.rst`)
- It does NOT own any `.py` or `.c` file content

### Python Files

Every public class and method must have a Google-style docstring:

```python
def get_temperature(self):
    """Return current temperature in Celsius.

    Reads from the daemon cache file. Updates min/max recorded values
    as a side effect.

    Args:
        (none beyond self for this example)

    Returns:
        float: Temperature in degrees Celsius, or None on read failure.
    """
```

Required sections:
- **One-line summary** (always)
- **Args** (when method takes parameters beyond `self`)
- **Returns** (when method returns a value)
- **Raises** (only when method explicitly raises exceptions)

### C Files

Every function must have a Doxygen header:

```c
/**
 * @brief Read a single byte from a CPLD register via I2C with retry.
 * @param client I2C client handle for the CPLD device.
 * @param reg Register address to read.
 * @return Register value (0-255) on success, negative errno on failure.
 */
static int cpld_read(struct i2c_client *client, u8 reg)
```

Required markers:
- `@brief` (always)
- `@param` (for each parameter)
- `@return` (for non-void functions)

### File Headers

Every source file must have a header:
- **Python**: Module-level docstring (`"""..."""`) explaining purpose, hardware context, and data flow
- **C**: `/** @file ... @brief ... */` Doxygen file header

### When Documentation Must Be Updated

| Change Type | Documentation Required |
|-------------|----------------------|
| New function/method | Full docstring/Doxygen header |
| Changed function signature | Update Args/params |
| Changed return value | Update Returns/@return |
| Changed behavior | Update description |
| Bug fix with non-obvious cause | Add comment explaining the fix |
| New file | Module-level docstring + all function docs |

### Enforcement

Before committing, verify:
```bash
# Python: check for missing docstrings
grep -n 'def ' <file>.py | while read line; do
  # Every def should have a docstring on the next non-blank line
done

# C: check for Doxygen coverage
grep -c '@brief' <file>.c   # should match function count
```

---

## 4. Commit Message Convention

```
feat(<scope>): add new capability
fix(<scope>): correct broken behavior  
docs(<scope>): documentation changes (in-code or .rst)
refactor(<scope>): no behavior change
test(<scope>): test additions or fixes
```

Scopes: `build`, `device`, `platform`, `memory`, `i2c`, `bmc`, `sysfs`, `sfp`, `led`, `led-diag`, `counters`, `ztp`, `l3`, `patches`, `postinst`, `service`, `rc.local`

---

## 5. Build Verification

After merging any topic branch to master:

```bash
cd /export/sonic/sonic-buildimage
git pull origin master
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

The platform .deb must build cleanly before the merge is considered complete.

---

## 6. What Goes Where

| Artifact | Repository | Branch |
|----------|-----------|--------|
| Platform code (C, Python, services) | `sonic-buildimage` | `wedge100s/<topic>` |
| Build system changes | `sonic-buildimage` | `wedge100s/build-infra` |
| Submodule patches | `sonic-buildimage` | `wedge100s/submodule-patches` |
| Sphinx docs infrastructure | `sonic-buildimage` | `wedge100s/docs` |
| Tests, tools, notes, guides | `sonic-wedge100s-devel` | `initial` branch |
| This workflow document | `sonic-wedge100s-devel` | `initial` branch |

---

## 7. Anti-Patterns (Do NOT Do These)

1. **Do not commit docs annotations on `wedge100s/docs` for code owned by other branches.** Docstrings go with the code.
2. **Do not edit submodule files without exporting a quilt patch.** If it's not in a `.patch/` file, it does not exist.
3. **Do not comment out other platforms in shared build files on merge-ready branches.** Use `wedge100s/dev-build-only` for that (local-only, never upstream).
4. **Do not commit tests, notes, or tools to `sonic-buildimage`.** Those go in `sonic-wedge100s-devel`.
5. **Do not force-push topic branches.** Other branches may have merged from them.
6. **Do not add features without docstrings.** Undocumented code is incomplete code.
7. **Do not hand-edit patch files.** Use `quilt refresh` after resolving conflicts.

---

## 8. Skills Reference

### Existing Skills

**`wedge100s-topic-branches`** — Loaded automatically when any change targets `FlaxAdvisors/sonic-buildimage`. Contains:
- Branch structure and dependency graph
- File-to-branch ownership mapping
- Step-by-step workflow for making changes
- Merge and upstream sync procedures
- Commit message convention

**`sonic-submodule-patches`** — Loaded when any change touches `src/<submodule>/`. Contains:
- Quilt patch creation, application, and refresh procedures
- `slave.mk` integration details (how the build system applies patches)
- Conflict resolution workflow
- What survives `make distclean` / `make init`

**`wedge100s-doc-check`** — Loaded before committing code to a topic branch. Scans modified `.py` files for public methods missing docstrings and `.c` files for functions missing `@brief` Doxygen headers. Blocks the commit until gaps are fixed.

**`wedge100s-build-verify`** — Loaded after merging a topic branch to master. Verifies quilt patches apply cleanly, runs the platform .deb build, and reports pass/fail with specific error context. Includes a failure-mode lookup table for common build errors.

**`wedge100s-branch-audit`** — Loaded periodically or before milestones. Checks branch sync status, archive completeness, documentation coverage, file ownership, and quilt patch health. Produces a structured report with action items.
