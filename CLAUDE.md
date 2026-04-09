# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in the wedge100s devel workspace.

## Project

Porting the Accton Wedge 100S-32X (Facebook Wedge 100S, Broadcom Tomahawk) to SONiC.

This is the **development companion repo** (`FlaxAdvisors/sonic-wedge100s-devel`). The platform code lives in `FlaxAdvisors/sonic-buildimage`.

I need claude to act as the expert here. Take direction for changes but be sure to compare the proposed implementation changes to other platform accton broadcom platforms and especially the OpenNetworkLinux implementation for wedge100s.

## Repository Layout

| Repo | Local Path | Purpose |
|---|---|---|
| `FlaxAdvisors/sonic-buildimage` | `/export/sonic/sonic-buildimage` | "Platform fork" (clean build clone, based on 202511) |
| `FlaxAdvisors/sonic-wedge100s-devel` | `/export/sonic/sonic-wedge100s-devel` | "This repo": tests, tools, notes, docs |

### ⛔ MANDATORY — Read and follow `docs/workflow.md` before ANY platform fork work

**The authoritative development workflow is defined in [`docs/workflow.md`](docs/workflow.md).** It covers topic branch discipline, submodule patch management, and documentation requirements. Every rule in that document is enforced — no exceptions. Read it before making any change to `FlaxAdvisors/sonic-buildimage`.

Key rules (see workflow.md for full details):
1. **All changes go through topic branches** — never commit directly to master
2. **Submodule changes must be quilt patches** — see `sonic-submodule-patches` skill
3. **Documentation is mandatory** — docstrings/Doxygen live WITH the code on the same branch, updated in the same commit as code changes
4. **Branch ownership is strict** — each file is owned by exactly one topic branch (see ownership table in workflow.md)

### ⛔ HARD RULE — All "Platform fork" development must be done in wedge100s/<topic> branches - see `wedge100s-topic-branches` skill for workflow

**NOTE** ALL platform changes MUST go through topic branches (`wedge100s/<topic>`) that PR into `master` on the "Platform fork." Ancillary files supporting development, but not part of the target build (e.g. tests, notes, tools, guides), stay in "This repo" and are never committed to the "Platform fork."

### ⛔ HARD RULE — Submodule Changes MUST Be Captured in Quilt Patches - see `wedge100s-submodule-patches` skill for workflow

### ⛔ HARD RULE — Documentation Must Accompany Code Changes

**Every new or modified function/method must have a docstring (Python) or Doxygen header (C).** Documentation lives on the SAME topic branch as the code it describes — never on a separate branch. The `wedge100s/docs` branch owns ONLY Sphinx infrastructure (.rst files, conf.py), not in-code annotations. See `docs/workflow.md` Section 3 for format requirements.

**ANY change made inside a `src/<submodule>/` directory will be wiped by `make init` or `make distclean`.** This has caused repeated loss of work.

**Before finishing any session that touches a submodule:**
1. Export the change as a patch: `git format-patch HEAD~1 --output-directory ../src/<sub>.patch/`
2. Update the series file: `ls ../src/<sub>.patch/*.patch | sort | xargs -n1 basename > ../src/<sub>.patch/series`
3. Commit the `.patch/` directory to the main repo

This applies to **all** submodules: `sonic-utilities`, `sonic-swss`, `sonic-ztp`, etc.
If a fix is not in a `.patch/` file tracked by the main repo, it **does not exist**.

### ⛔ HARD STOP — I2C Bus Safety on Target Hardware

**NEVER touch the I2C bus while wedge100s-i2c-daemon or pmon are running.**

The CP2112 USB-HID bridge is a single shared resource. Concurrent access from any tool (i2cget, i2cset, i2cdetect, manual hidraw reads) while the daemon is running will corrupt in-flight transactions, leave muxes selected in wrong states, and — critically — **corrupt the /run/wedge100s/ EEPROM cache files** with partial or zero data. Corrupted upper-page data (byte 220, vendor info) is NOT recovered by the 20-second DOM TTL refresh, requiring physical EEPROM reprogram.

**Before ANY i2c bus access or /run/wedge100s/ file manipulation on the target:**
```bash
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```
**After:**
```bash
sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```
This applies to: i2cdetect, i2cget, i2cset, xxd/cat on hidraw0, rm of sfp_*_eeprom files, and any script that touches /dev/hidraw0 or /dev/i2c-1.

**More generally -- but still as important for workflow:** All i2c related data and debugging should happen through the safe /run/wedge100s sysfs interface we have constructed for this platform. The only exceptions allowed outside this sysfs path would be for new features.


### Scope Control
- Read only the files explicitly named in the prompt unless you ask first
- Do not refactor, add comments, or clean up code outside the stated task
- Do not add error handling for impossible cases or features not requested

### Retry Behavior
- Non-zero Bash exit codes are normal — try up to 3 different workarounds
- After 3 failed attempts, surface the full error output and ask for guidance
- Do NOT retry the exact same failing command unchanged

## Key File Paths

### Platform Fork (`/export/sonic/sonic-buildimage`)

| Resource | Path |
|---|---|
| Device directory | `device/accton/x86_64-accton_wedge100s_32x-r0/` |
| Platform modules | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/` |
| Build rules | `platform/broadcom/platform-modules-accton.mk` |
| Image assembly | `platform/broadcom/one-image.mk` |
| Installer config | `installer/platforms/x86_64-accton_wedge100s_32x-r0` |
| Submodule patches | `src/*.patch/` |

### This Repo (`/export/sonic/sonic-wedge100s-devel`)

| Resource | Path |
|---|---|
| Test suite | `tests/` (pytest, 25+ staged phases) |
| Investigation notes | `notes/` |
| Design specs | `docs/superpowers/specs/` |
| Implementation plans | `docs/superpowers/plans/` |
| Setup guides | `guides/` |
| Deployment tools | `tools/` |
| Reference configs | `cfg/` |
| Build toggle | `patches/wedge100s-only-build.sh` |
| Auto-memory | `/export/sonic/sonic-wedge100s-devel/.claude/memory/` |

### Reference Platforms

| Resource | Path |
|---|---|
| ONL Wedge100S source | `/export/sonic/OpenNetworkLinux/packages/platforms/accton/x86-64/wedge100s-32x/` |
| Similar platform AS7712 | `/export/sonic/sonic-buildimage/device/accton/x86_64-accton_as7712_32x-r0/` |


## SSH access to Target and Peer

- Permissions: you have unfettered SSH command access to all the hardware targets for all proposed changes and modifications without requesting permissions via the ~/.claude/settings.json wildcard allow.

### SONiC Switch (primary target)
- Access: `ssh admin@192.168.88.12`
- Platform: Accton Wedge 100S-32X running SONiC (kernel 6.1.0-29-2-amd64, hare-lorax)
- Use: python3, not python, when scripting

### ONIE (alternate state of primary target)
- Access: `ssh root@192.168.88.12`
- Platform: Accton Wedge 100S-32X running ONIE (limited tooling meant for NOS deployment)
- Use: no python is available

### OpenBMC (environmental/control)
- Access: `ssh root@192.168.88.13` (password: `0penBmc`)
- Fallback ONE (on SONiC target):
  - **Transport:** SSH over USB-CDC-Ethernet (usb0 on both switch and BMC)
  - **Target:** `root@fe80::ff:fe00:1%usb0` — IPv6 link-local, auto-derived from fixed BMC usb0 MAC `02:00:00:00:00:01`. No IP address configuration needed; only `ip link set usb0 up` required.
  - **Key:** `/etc/sonic/wedge100s-bmc-key` (ed25519) — accessible 
- Fallback TWO (on SONiC target): `/dev/ttyACM0` at 57600 baud (blocking mode, login: root / 0penBmc)
- Use: no python is available on BMC

### Peer wedge100s running Arista EOS
- Access: `sshpass -p '0penSesame' ssh -tt admin@192.168.88.14 '<command>'`
- Alternative access: `sshpass -p '0penSesame' ssh -tt -o StrictHostKeyChecking=no -J admin@192.168.88.12 admin@192.168.88.14 '<command>'`
- Platform: Accton Wedge 100S-32X running Arista EOS
- Direct SSH from dev host works when EOS Po1 has no IP; see tests/notes/lacp-mgmt-reachability-root-cause.md

### Serial Console Log
- View via: `ssh bang-lorax tail -n 500 screenlog.ttyUSB2.0`

### Reachability Warning for SONiC and openBMC
**BEFORE attempting SSH to hardware targets check if they are ping-reachable but SSH-unreachable.
This happens after every BMC reboot because `authorized_keys` is cleared on reset.

If ping succeeds but SSH fails → **USE `sshpass` and do `ssh-copy-id` instead of prompting the user**:

for the BMC

```bash
ping -c1 -W2 192.168.88.13 && ssh -o ConnectTimeout=5 root@192.168.88.13 echo ok
```

```bash
sshpass -p '0penBmc' ssh-copy-id -o StrictHostKeyChecking=no admin@192.168.88.13 2>&1
```

or for the SONiC target

```bash
ping -c1 -W2 192.168.88.12 && ssh -o ConnectTimeout=5 admin@192.168.88.12 echo ok
```

```bash
sshpass -p 'YourPaSsWoRd' ssh-copy-id -o StrictHostKeyChecking=no admin@192.168.88.12 2>&1
```


## Build System Architecture

All build commands run from `/export/sonic/sonic-buildimage`.

### Three-Layer Pipeline

1. **`Makefile` (host)** — thin wrapper; delegates to `Makefile.work` with `BLDENV=trixie` (and bookworm for dependencies). 202511 builds both.

2. **`Makefile.work` (host, Docker orchestrator)** — builds/pulls a `sonic-slave-trixie-<user>:<hash>` Docker image from `sonic-slave-trixie/Dockerfile.j2`, then runs `docker run --privileged` with the repo bind-mounted at `/sonic`. All compilation happens inside this container.

3. **`slave.mk` (inside container)** — the actual GNU make build engine. Includes `rules/*.mk` and `platform/broadcom/rules.mk`. Produces .deb packages in `target/debs/trixie/` and Docker images in `target/`.

### Image Assembly

`sonic-broadcom.bin` is a self-extracting ONIE installer built by `build_image.sh`:
- `fs.squashfs` — SONiC root filesystem (Debian trixie base)
- `dockerfs.tar.gz` — all SONiC service containers
- `installer/install.sh` + `installer/platforms/x86_64-accton_wedge100s_32x-r0` (console: port 0x3f8, dev 0/ttyS0, speed 57600)

Platform `.deb` files are **lazy installed** — bundled in the image and extracted based on the ONIE platform string at install time.

### Platform Build Dependency Chain

```
sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
  ├─ linux-headers (kernel module build)
  ├─ linux-headers-common
  └─ pddf-platform-module (SONIC_USE_PDDF_FRAMEWORK=y in rules/config)
```

### Where the Wedge 100S Hooks Into the Build

| File | Role |
|---|---|
| `platform/broadcom/platform-modules-accton.mk` | Defines .deb target; version is **1.1** |
| `platform/broadcom/rules.mk` | Includes platform-modules-accton.mk |
| `platform/broadcom/one-image.mk` | Lists module in `_LAZY_INSTALLS` |
| `installer/platforms/x86_64-accton_wedge100s_32x-r0` | Console params for GRUB |
| `installer/platforms_asic` | Maps platform string to ASIC vendor |

## Build Commands

Run from `/export/sonic/sonic-buildimage`:

```bash
# One-time setup
make init                              # Clone all git submodules
make configure PLATFORM=broadcom       # Creates .platform, .arch files

# Build the platform package (.deb only)
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb

# Build the full ONIE image (takes hours)
make SONIC_BUILD_JOBS=40 BUILD_SKIP_TEST=y target/sonic-broadcom.bin

# Clean a specific target
make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb-clean

# Enter build slave container interactively (for debugging)
make sonic-slave-bash

# Debug a failed build (drops to shell in container after failure)
KEEP_SLAVE_ON=yes BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb

# Install on target
scp target/debs/trixie/sonic-platform-accton-wedge100s-32x*.deb admin@192.168.88.12:~
ssh admin@192.168.88.12 sudo systemctl stop pmon
ssh admin@192.168.88.12 sudo dpkg -i sonic-platform-accton-wedge100s-32x*.deb
ssh admin@192.168.88.12 sudo systemctl start pmon
```

### Build Gotchas

- `BUILD_SKIP_TEST=y` only skips `.deb` package tests, NOT Python wheel tests
- Python wheel tests are controlled by `$($*_TEST)` per-package in `slave.mk` line 1014
- The build runs bookworm first, then trixie — a bookworm failure blocks trixie
- Platform .deb depends on the full bookworm dependency chain (containers, wheels)

## Test Runner

```bash
# Run all stages against the hardware target
cd tests && python3 run_tests.py

# Run a single stage
cd tests && pytest stage_01_eeprom/ -v

# Target connection config
cat tests/target.cfg   # SSH host, user, key path
```

## Notes Generation Rule

On completion of any investigation, hardware verification, or implementation phase:
**Write findings to `notes/<topic>.md`** before summarizing inline.

Format preference:
- Bullet points for facts and commands that worked
- Code blocks for exact commands/output
- Mark hardware-verified items with `(verified on hardware YYYY-MM-DD)`
- These files persists across sessions; inline conversation summaries do not

