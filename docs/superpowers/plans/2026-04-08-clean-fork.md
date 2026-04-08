# Clean Fork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reset `FlaxAdvisors/sonic-buildimage` to upstream 202511, then reconstruct all wedge100s platform work as 10 clean topic branches with documentation.

**Architecture:** Fresh file-copy approach — each topic branch is created from `master` (which equals `upstream/202511`), relevant files are copied from the local `wedge100s` working tree, and clean atomic commits are written. Shared files like `debian/rules` and `postinst` are built up incrementally across topic branches. The `upstream` branch tracks `sonic-net/sonic-buildimage:202511` for future syncing.

**Tech Stack:** git, GitHub CLI (`gh`), Sphinx (documentation), Doxygen (C docs)

**Spec:** `docs/superpowers/specs/2026-04-08-clean-fork-design.md`

---

## Conventions

**Paths:**
- `W100S=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x`
- `DEVICE=device/accton/x86_64-accton_wedge100s_32x-r0`
- `HWSKU=$DEVICE/Accton-WEDGE100S-32X`
- Source working tree: the local `wedge100s` branch (current HEAD of this repo)

**Branch creation pattern:** Every topic branch follows the same workflow:
```bash
git checkout master                    # start from clean upstream base
git checkout -b wedge100s/<topic>      # create topic branch
# ... copy files, commit ...
git push origin wedge100s/<topic>      # push to remote
```

**Commit message style:** Conventional commits (`feat(scope): description`).

**Important — merge-clean file edits:** Files shared with upstream (`debian/rules`, `platform-modules-accton.mk`, `one-image.mk`) must be edited to **add** wedge100s entries alongside existing content, NOT replace or comment out other platforms. The current development branch commented out other platforms for build speed — this must not carry forward.

**Fast-build toggle:** For local development, `patches/wedge100s-only-build.sh apply` strips the build to wedge100s-only (reversible with `revert`). This script lives in the `-devel` repo and is never committed to the clean fork.

---

## Task 0: Prepare Local Environment

**Files:**
- No files created; local git operations only

- [ ] **Step 1: Verify upstream/202511 is fetched and current**

```bash
git fetch upstream 202511
git log --oneline upstream/202511 | head -3
```

Expected: Shows recent upstream 202511 commits.

- [ ] **Step 2: Create a local reference branch of the current wedge100s working tree**

This ensures we have a fixed reference point even if the wedge100s branch moves.

```bash
git branch wedge100s-source wedge100s
```

- [ ] **Step 3: Verify all source files are present locally**

```bash
# Spot-check key files exist
test -f platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-i2c-daemon.c && echo "OK: i2c-daemon"
test -f platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/sfp.py && echo "OK: sfp.py"
test -f device/accton/x86_64-accton_wedge100s_32x-r0/installer.conf && echo "OK: installer.conf"
test -d src/sonic-swss.patch && echo "OK: swss patches"
```

Expected: All four lines print "OK".

---

## Task 1: Phase 1 — Repo Reset

**Files:**
- No files created; git remote operations only

**CAUTION: This task contains destructive remote operations. Execute each step only after explicit user confirmation.**

- [ ] **Step 1: Tag current wedge100s branch as safety archive**

```bash
git tag archive/wedge100s-v1 origin/wedge100s
git push origin archive/wedge100s-v1
```

Expected: Tag `archive/wedge100s-v1` created on remote.

- [ ] **Step 2: Create upstream tracking branch**

```bash
git branch -f upstream upstream/202511
git push origin upstream
```

Expected: `upstream` branch appears on `FlaxAdvisors/sonic-buildimage`.

- [ ] **Step 3: Force-push master to match upstream/202511**

```bash
git push origin upstream/202511:master --force
```

Expected: `master` on remote now equals `upstream/202511`. The accidental wedge100s merge is gone.

- [ ] **Step 4: Delete old branches from remote**

```bash
git push origin --delete wedge100s
git push origin --delete revert-1-wedge100s
```

Expected: Only `master` and `upstream` branches remain (plus the `archive/wedge100s-v1` tag).

- [ ] **Step 5: Update repo description**

```bash
gh repo edit FlaxAdvisors/sonic-buildimage \
  --description "SONiC platform support for Accton Wedge 100S-32X (Broadcom Tomahawk)"
```

- [ ] **Step 6: Verify remote state**

```bash
git ls-remote --heads origin
git ls-remote --tags origin | grep archive
gh repo view FlaxAdvisors/sonic-buildimage --json description -q '.description'
```

Expected:
- Two branches: `master`, `upstream`
- Tag: `archive/wedge100s-v1`
- Description updated

- [ ] **Step 7: Reset local master to match**

```bash
git checkout wedge100s-source   # stay on our source branch
git branch -f master upstream/202511
```

---

## Task 2: Topic Branch — `wedge100s/build-infra`

**Files:**
- Modify: `platform/broadcom/platform-modules-accton.mk` (add wedge100s entries to existing file)
- Modify: `platform/broadcom/one-image.mk` (add one `LAZY_INSTALLS` line)
- Modify: `platform/broadcom/sonic-platform-modules-accton/debian/rules` (add `wedge100s-32x` to `MODULE_DIRS`)
- Create: `installer/platforms/x86_64-accton_wedge100s_32x-r0`

- [ ] **Step 1: Create branch from master**

```bash
git checkout master
git checkout -b wedge100s/build-infra
```

- [ ] **Step 2: Add wedge100s to platform-modules-accton.mk**

Copy `platform/broadcom/platform-modules-accton.mk` from `upstream/202511` as the base, then add the wedge100s block. The additions are:

After the last existing `ACCTON_*_PLATFORM_MODULE_VERSION` line, add:
```makefile
ACCTON_WEDGE100S_32X_PLATFORM_MODULE_VERSION = 1.1

export ACCTON_WEDGE100S_32X_PLATFORM_MODULE_VERSION
```

After the last existing `SONIC_PLATFORM_*` block, add:
```makefile
ACCTON_WEDGE100S_32X_PLATFORM_MODULE = sonic-platform-accton-wedge100s-32x_$(ACCTON_WEDGE100S_32X_PLATFORM_MODULE_VERSION)_amd64.deb
$(ACCTON_WEDGE100S_32X_PLATFORM_MODULE)_PLATFORM = x86_64-accton_wedge100s_32x-r0
$(eval $(call add_extra_package,$(ACCTON_AS7712_32X_PLATFORM_MODULE),$(ACCTON_WEDGE100S_32X_PLATFORM_MODULE)))
SONIC_PLATFORM += $(ACCTON_WEDGE100S_32X_PLATFORM_MODULE)
```

Verify: The file retains ALL existing platform entries unchanged, with wedge100s appended.

- [ ] **Step 3: Add wedge100s to one-image.mk LAZY_INSTALLS**

Edit `platform/broadcom/one-image.mk`. Add one line to the `_LAZY_INSTALLS` list, after the last existing `ACCTON_*` entry:

```makefile
                               $(ACCTON_WEDGE100S_32X_PLATFORM_MODULE) \
```

This is the ONLY change to this file. Do NOT add `broadcom-legacy-th`, Arista, Nokia, or Nexthop entries — those were development artifacts.

- [ ] **Step 4: Add wedge100s-32x to debian/rules MODULE_DIRS**

Edit `platform/broadcom/sonic-platform-modules-accton/debian/rules`. Add `wedge100s-32x` to the existing `MODULE_DIRS` lines:

```makefile
MODULE_DIRS += wedge100s-32x
```

Do NOT comment out other platforms. Do NOT add `MAKE_FLAGS` or change `DH_VERBOSE`. Keep all other content identical to upstream.

- [ ] **Step 5: Create installer platform file**

```bash
# Copy from wedge100s-source branch
git show wedge100s-source:installer/platforms/x86_64-accton_wedge100s_32x-r0 \
  > installer/platforms/x86_64-accton_wedge100s_32x-r0
```

- [ ] **Step 6: Create empty wedge100s-32x module skeleton**

The `debian/rules` Makefile iterates `MODULE_DIRS` and expects a directory structure. Create the minimum skeleton so the build doesn't fail:

```bash
mkdir -p platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/modules
mkdir -p platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils
mkdir -p platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service
mkdir -p platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform

# Create minimal __init__.py
git show wedge100s-source:platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/__init__.py \
  > platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/__init__.py

# Create sonic_platform_setup.py (required by debian/rules install target)
git show wedge100s-source:platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform_setup.py \
  > platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform_setup.py
```

- [ ] **Step 7: Commit**

```bash
git add platform/broadcom/platform-modules-accton.mk \
       platform/broadcom/one-image.mk \
       platform/broadcom/sonic-platform-modules-accton/debian/rules \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/ \
       installer/platforms/x86_64-accton_wedge100s_32x-r0
git commit -m "feat(build): add Accton Wedge 100S-32X platform to SONiC build

Add wedge100s-32x to platform-modules-accton.mk, one-image.mk lazy
installs, and debian/rules MODULE_DIRS. Create installer platform
config and empty module skeleton.

Platform: Accton Wedge 100S-32X (Facebook Wedge 100S)
ASIC: Broadcom Memory (BCM56960)"
```

- [ ] **Step 8: Push**

```bash
git push origin wedge100s/build-infra
```

---

## Task 3: Topic Branch — `wedge100s/device-identity`

**Files:**
- Create: `$DEVICE/default_sku`
- Create: `$DEVICE/installer.conf`
- Create: `$DEVICE/platform.json`
- Create: `$DEVICE/platform_asic`
- Create: `$DEVICE/pmon_daemon_control.json`
- Create: `$DEVICE/system_health_monitoring_config.json`
- Create: `$HWSKU/hwsku.json`
- Create: `$HWSKU/port_config.ini`
- Create: `$HWSKU/port_breakout_config_db.json`
- Create: `$HWSKU/sai.profile`
- Create: `$W100S/utils/accton_wedge100s_util.py`
- Create: `$W100S/utils/wedge100s-pre-shutdown.sh`
- Create: `$W100S/service/wedge100s-pre-shutdown.service`
- Create: `$W100S/debian/sonic-platform-accton-wedge100s-32x.postinst` (skeleton)
- Create: `$W100S/debian/sonic-platform-accton-wedge100s-32x.prerm`
- Create: `$W100S/sonic_platform/platform.py`
- Create: `$W100S/sonic_platform/chassis.py`
- Create: `$W100S/sonic_platform/eeprom.py`
- Create: `$W100S/sonic_platform/component.py`
- Create: `$W100S/sonic_platform/watchdog.py`
- Create: `$W100S/sonic_platform/platform_smbus.py`
- Modify: `files/image_config/platform/rc.local` (dhclient timeout + apt sources.list.d fix)

- [ ] **Step 1: Create branch from build-infra**

```bash
git checkout wedge100s/build-infra
git checkout -b wedge100s/device-identity
```

- [ ] **Step 2: Copy device tree files**

```bash
DEVICE=device/accton/x86_64-accton_wedge100s_32x-r0
HWSKU=$DEVICE/Accton-WEDGE100S-32X
mkdir -p $HWSKU

for f in default_sku installer.conf platform.json platform_asic \
         pmon_daemon_control.json system_health_monitoring_config.json; do
  git show wedge100s-source:$DEVICE/$f > $DEVICE/$f
done

for f in hwsku.json port_config.ini port_breakout_config_db.json sai.profile; do
  git show wedge100s-source:$HWSKU/$f > $HWSKU/$f
done
```

- [ ] **Step 3: Copy platform init utility**

```bash
git show wedge100s-source:platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/accton_wedge100s_util.py \
  > platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/accton_wedge100s_util.py
chmod +x platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/accton_wedge100s_util.py
```

- [ ] **Step 4: Copy base sonic_platform API files**

```bash
W100S=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x
for f in platform.py chassis.py eeprom.py component.py watchdog.py platform_smbus.py; do
  git show wedge100s-source:$W100S/sonic_platform/$f > $W100S/sonic_platform/$f
done
```

- [ ] **Step 5: Copy pre-shutdown service**

```bash
git show wedge100s-source:$W100S/service/wedge100s-pre-shutdown.service \
  > platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-pre-shutdown.service
git show wedge100s-source:$W100S/utils/wedge100s-pre-shutdown.sh \
  > platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-pre-shutdown.sh
chmod +x platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-pre-shutdown.sh
```

- [ ] **Step 6: Create postinst skeleton**

Create `platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.postinst` with ONLY the base platform sections from the full postinst (lines covering platform-init, mgmt VRF cleanup, sysstat disable, pmon drop-in, system-health drop-in, var-log drop-in, pre-shutdown enable, serial console TERM fix). Exclude sections for bmc-daemon, i2c-daemon, ledup, flex-counter-daemon — those get added by later topic branches.

Extract the relevant sections from:
```bash
git show wedge100s-source:platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.postinst
```

- [ ] **Step 7: Copy prerm**

```bash
git show wedge100s-source:platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.prerm \
  > platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.prerm
chmod +x platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.prerm
```

- [ ] **Step 8: Apply rc.local fix**

Edit `files/image_config/platform/rc.local` to add:
1. The `timeout 5s` wrapper around dhclient calls
2. The `sources.list.d` move-aside during first-boot platform install

These are platform-independent bug fixes that prevent boot hangs.

- [ ] **Step 9: Commit device tree**

```bash
git add device/accton/x86_64-accton_wedge100s_32x-r0/
git commit -m "feat(device): add Wedge 100S-32X device tree and hwsku

Add platform.json (32x100G QSFP28 ports), port_config.ini,
hwsku.json with breakout support (4x25G), sai.profile, and
installer.conf for GRUB serial console (ttyS0 @ 57600)."
```

- [ ] **Step 10: Commit platform init and base API**

```bash
git add platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/accton_wedge100s_util.py \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/platform.py \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/chassis.py \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/eeprom.py \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/component.py \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/watchdog.py \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/sonic_platform/platform_smbus.py
git commit -m "feat(platform): add Wedge 100S platform init and base sonic_platform API

Add accton_wedge100s_util.py for CP2112 USB-HID mux initialization
and platform reset. Add sonic_platform chassis, eeprom, component,
and watchdog implementations backed by /run/wedge100s/ sysfs."
```

- [ ] **Step 11: Commit packaging and services**

```bash
git add platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.postinst \
       platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.prerm \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/service/wedge100s-pre-shutdown.service \
       platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/utils/wedge100s-pre-shutdown.sh
git commit -m "feat(platform): add postinst, prerm, and pre-shutdown service

postinst enables platform-init, installs pmon and system-health
drop-ins, disables mgmt VRF, and enables pre-shutdown for clean
reboot (fixes 2-3 minute reboot delay)."
```

- [ ] **Step 12: Commit rc.local fixes**

```bash
git add files/image_config/platform/rc.local
git commit -m "fix(rc.local): add dhclient timeout and apt sources.list.d isolation

Wrap first-boot dhclient in 'timeout 5s' to prevent hang when no
DHCP server is present. Move aside sources.list.d during platform
package install to prevent DNS-dependent apt queries before
networking is up."
```

- [ ] **Step 13: Push**

```bash
git push origin wedge100s/device-identity
```

---

## Task 4: Topic Branch — `wedge100s/chipset-config`

**Files:**
- Create: `$HWSKU/th-wedge100s-32x-flex.config.bcm`
- Create: `$DEVICE/led_proc_init.soc`

- [ ] **Step 1: Create branch**

```bash
git checkout wedge100s/device-identity
git checkout -b wedge100s/chipset-config
```

- [ ] **Step 2: Copy BCM config**

```bash
git show wedge100s-source:device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm \
  > device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm
```

- [ ] **Step 3: Commit BCM config**

```bash
git add device/accton/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/th-wedge100s-32x-flex.config.bcm
git commit -m "feat(memory): add Memory flex port config for Wedge 100S-32X

32x100G QSFP28 port mapping to Memory BCM56960 with 4x25G breakout
support. SerDes tuning, lane mapping, and port-to-physical mappings
derived from ONL and Memory SDK reference for this board."
```

- [ ] **Step 4: Copy LEDUP init SOC**

```bash
git show wedge100s-source:device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc \
  > device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc
```

- [ ] **Step 5: Commit LEDUP SOC**

```bash
git add device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc
git commit -m "feat(memory): add LEDUP0/1 init bytecodes for port LED mapping

Custom LEDUP microcontroller programs for the Wedge 100S LED chain.
LEDUP0 handles ports 1-16, LEDUP1 handles ports 17-32. Includes
LEDUP1 bytecode fix for all-magenta LED bug (BAR2 register offset
correction from iProc to CMIC address space)."
```

- [ ] **Step 6: Push**

```bash
git push origin wedge100s/chipset-config
```

---

## Task 5: Topic Branch — `wedge100s/i2c-bmc-sysfs`

**Files:**
- Create: `$W100S/utils/wedge100s-i2c-daemon.c`
- Create: `$W100S/utils/wedge100s-bmc-daemon.c`
- Create: `$W100S/utils/wedge100s-bmc-auth.c`
- Create: `$W100S/utils/wedge100s-bmc-daemon` (Python wrapper)
- Create: `$W100S/utils/wedge100s-bus-reset.sh`
- Create: `$W100S/service/wedge100s-i2c-daemon.service`
- Create: `$W100S/service/wedge100s-bmc-daemon.service`
- Create: `$W100S/service/wedge100s-bmc-poller.service`
- Create: `$W100S/service/wedge100s-bmc-poller.timer`
- Create: `$W100S/service/wedge100s-i2c-poller.service`
- Create: `$W100S/service/wedge100s-i2c-poller.timer`
- Create: `$W100S/sonic_platform/bmc.py`
- Create: `$W100S/sonic_platform/fan.py`
- Create: `$W100S/sonic_platform/psu.py`
- Create: `$W100S/sonic_platform/thermal.py`
- Modify: `$W100S/debian/sonic-platform-accton-wedge100s-32x.postinst` (add i2c-daemon + bmc-daemon enable)

- [ ] **Step 1: Create branch**

```bash
git checkout wedge100s/device-identity
git checkout -b wedge100s/i2c-bmc-sysfs
```

- [ ] **Step 2: Copy I2C daemon source**

```bash
W100S=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x
git show wedge100s-source:$W100S/utils/wedge100s-i2c-daemon.c > $W100S/utils/wedge100s-i2c-daemon.c
```

- [ ] **Step 3: Commit I2C daemon**

```bash
git add $W100S/utils/wedge100s-i2c-daemon.c
git commit -m "feat(i2c): add CP2112 USB-HID userspace I2C daemon

Userspace I2C master daemon that communicates with the CP2112
USB-to-SMBus bridge via /dev/hidraw0. Manages the PCA9548 mux
tree for SFP EEPROM reads and environmental monitoring. Writes
cached data to /run/wedge100s/ for consumption by sonic_platform
API classes.

Design choice: userspace daemon instead of kernel i2c-dev driver
because the CP2112 is a single shared resource requiring explicit
mux sequencing that kernel drivers cannot coordinate."
```

- [ ] **Step 4: Copy BMC daemon sources**

```bash
git show wedge100s-source:$W100S/utils/wedge100s-bmc-daemon.c > $W100S/utils/wedge100s-bmc-daemon.c
git show wedge100s-source:$W100S/utils/wedge100s-bmc-auth.c   > $W100S/utils/wedge100s-bmc-auth.c
git show wedge100s-source:$W100S/utils/wedge100s-bmc-daemon    > $W100S/utils/wedge100s-bmc-daemon
chmod +x $W100S/utils/wedge100s-bmc-daemon
git show wedge100s-source:$W100S/utils/wedge100s-bus-reset.sh  > $W100S/utils/wedge100s-bus-reset.sh
chmod +x $W100S/utils/wedge100s-bus-reset.sh
```

- [ ] **Step 5: Commit BMC daemon**

```bash
git add $W100S/utils/wedge100s-bmc-daemon.c \
       $W100S/utils/wedge100s-bmc-auth.c \
       $W100S/utils/wedge100s-bmc-daemon \
       $W100S/utils/wedge100s-bus-reset.sh
git commit -m "feat(bmc): add OpenBMC REST daemon with SSH-key auth

C daemon that queries the OpenBMC REST API over SSH tunnel for
fan speeds, PSU status, and thermal sensor data. SSH auth uses
a platform-provisioned ed25519 key. Includes bus-reset utility
for recovering from CP2112 hang states.

bmc-auth.c handles SSH key provisioning and known_hosts management.
Python wrapper (wedge100s-bmc-daemon) provides systemd integration."
```

- [ ] **Step 6: Copy systemd service files**

```bash
for f in wedge100s-i2c-daemon.service wedge100s-bmc-daemon.service \
         wedge100s-bmc-poller.service wedge100s-bmc-poller.timer \
         wedge100s-i2c-poller.service wedge100s-i2c-poller.timer; do
  git show wedge100s-source:$W100S/service/$f > $W100S/service/$f
done
```

- [ ] **Step 7: Copy environmentals platform API**

```bash
for f in bmc.py fan.py psu.py thermal.py; do
  git show wedge100s-source:$W100S/sonic_platform/$f > $W100S/sonic_platform/$f
done
```

- [ ] **Step 8: Commit services and platform API**

```bash
git add $W100S/service/wedge100s-i2c-daemon.service \
       $W100S/service/wedge100s-bmc-daemon.service \
       $W100S/service/wedge100s-bmc-poller.service \
       $W100S/service/wedge100s-bmc-poller.timer \
       $W100S/service/wedge100s-i2c-poller.service \
       $W100S/service/wedge100s-i2c-poller.timer \
       $W100S/sonic_platform/bmc.py \
       $W100S/sonic_platform/fan.py \
       $W100S/sonic_platform/psu.py \
       $W100S/sonic_platform/thermal.py
git commit -m "feat(sysfs): add /run/wedge100s/ platform API and systemd services

Add sonic_platform implementations for fan, PSU, and thermal
monitoring backed by /run/wedge100s/ cached data. Add systemd
units for i2c-daemon, bmc-daemon, and polling timers.

bmc.py provides the BmcApi class used by fan/psu/thermal to
read OpenBMC environmental data via the bmc-daemon cache."
```

- [ ] **Step 9: Update postinst with daemon enable blocks**

Append to the existing postinst (from device-identity) the sections that enable and start `wedge100s-bmc-daemon.service` and `wedge100s-i2c-daemon.service`.

```bash
git add $W100S/../debian/sonic-platform-accton-wedge100s-32x.postinst
git commit -m "feat(postinst): enable i2c-daemon and bmc-daemon on install

Add systemctl enable/start blocks for wedge100s-i2c-daemon and
wedge100s-bmc-daemon to postinst. These daemons must start before
pmon to populate /run/wedge100s/ environmental data."
```

- [ ] **Step 10: Push**

```bash
git push origin wedge100s/i2c-bmc-sysfs
```

---

## Task 6: Topic Branch — `wedge100s/sfp-optics`

**Files:**
- Create: `$W100S/sonic_platform/sfp.py`
- Modify: postinst (no changes needed — SFP uses i2c-poller already added)

- [ ] **Step 1: Create branch**

```bash
git checkout wedge100s/i2c-bmc-sysfs
git checkout -b wedge100s/sfp-optics
```

- [ ] **Step 2: Copy sfp.py**

```bash
W100S=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x
git show wedge100s-source:$W100S/sonic_platform/sfp.py > $W100S/sonic_platform/sfp.py
```

- [ ] **Step 3: Commit**

```bash
git add $W100S/sonic_platform/sfp.py
git commit -m "feat(sfp): add SFP platform API with multi-family optics support

Implements SONiC SFP platform API for 32 QSFP28 ports. Supports
CMIS, SFF-8636, and SFF-8472 optics families with automatic
detection. Reads EEPROM data from /run/wedge100s/sfp_*_eeprom
cache files populated by the i2c-poller timer.

Features:
- Presence detection via CP2112 I2C mux tree
- DOM monitoring (temperature, voltage, TX/RX power, bias current)
- Transceiver info (vendor, PN, SN, type, media)
- 20-second TTL cache refresh for upper EEPROM pages"
```

- [ ] **Step 4: Push**

```bash
git push origin wedge100s/sfp-optics
```

---

## Task 7: Topic Branch — `wedge100s/led-pipeline`

**Files:**
- Create: `$DEVICE/plugins/led_control.py`
- Create: `$W100S/service/wedge100s-ledup-linkstate.service`
- Create: `$W100S/utils/wedge100s-ledup-linkstate`
- Create: `$W100S/utils/wedge100s-led-diag.py`
- Create: `$W100S/utils/wedge100s-led-diag-bmc.py`
- Create: `$W100S/utils/clear_led_diag.sh`
- Create: `$W100S/utils/wedge100s_ledup.py`
- Modify: postinst (add ledup-linkstate enable)

- [ ] **Step 1: Create branch**

This branch depends on BOTH chipset-config (LEDUP bytecodes) and i2c-bmc-sysfs (CPLD access via BMC). Branch from i2c-bmc-sysfs and merge chipset-config in.

```bash
git checkout wedge100s/i2c-bmc-sysfs
git checkout -b wedge100s/led-pipeline
git merge wedge100s/chipset-config --no-edit
```

- [ ] **Step 2: Copy led_control.py**

```bash
DEVICE=device/accton/x86_64-accton_wedge100s_32x-r0
mkdir -p $DEVICE/plugins
git show wedge100s-source:$DEVICE/plugins/led_control.py > $DEVICE/plugins/led_control.py
```

- [ ] **Step 3: Copy ledup-linkstate service and script**

```bash
W100S=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x
git show wedge100s-source:$W100S/service/wedge100s-ledup-linkstate.service \
  > $W100S/service/wedge100s-ledup-linkstate.service
git show wedge100s-source:$W100S/utils/wedge100s-ledup-linkstate \
  > $W100S/utils/wedge100s-ledup-linkstate
chmod +x $W100S/utils/wedge100s-ledup-linkstate
```

- [ ] **Step 4: Commit LED control and linkstate**

```bash
git add $DEVICE/plugins/led_control.py \
       $W100S/service/wedge100s-ledup-linkstate.service \
       $W100S/utils/wedge100s-ledup-linkstate
git commit -m "feat(led): add LED control and ledup-linkstate service

led_control.py maps port state (presence, speed, link) to LED
colors via the LEDUP microcontroller data RAM. The
ledup-linkstate service monitors netlink for link state changes
and updates LEDUP port status bytes in real-time.

LED states: off (absent), green (link up), amber (link down/admin
disabled), blinking green (activity via flex-counter-daemon)."
```

- [ ] **Step 5: Copy LED diagnostic tools**

```bash
git show wedge100s-source:$W100S/utils/wedge100s-led-diag.py     > $W100S/utils/wedge100s-led-diag.py
git show wedge100s-source:$W100S/utils/wedge100s-led-diag-bmc.py > $W100S/utils/wedge100s-led-diag-bmc.py
git show wedge100s-source:$W100S/utils/clear_led_diag.sh         > $W100S/utils/clear_led_diag.sh
git show wedge100s-source:$W100S/utils/wedge100s_ledup.py        > $W100S/utils/wedge100s_ledup.py
chmod +x $W100S/utils/wedge100s-led-diag.py $W100S/utils/wedge100s-led-diag-bmc.py \
         $W100S/utils/clear_led_diag.sh
```

- [ ] **Step 6: Commit LED diagnostics**

```bash
git add $W100S/utils/wedge100s-led-diag.py \
       $W100S/utils/wedge100s-led-diag-bmc.py \
       $W100S/utils/clear_led_diag.sh \
       $W100S/utils/wedge100s_ledup.py
git commit -m "feat(led-diag): add LED diagnostic and verification tools

CLI tools for LED pipeline debugging:
- wedge100s-led-diag.py: SOC-side LED control via /dev/mem BAR2 access
- wedge100s-led-diag-bmc.py: BMC-side CPLD LED register R/W
- wedge100s_ledup.py: LEDUP data RAM reader and bytecode loader
- clear_led_diag.sh: reset LEDs to normal operation after diagnostics"
```

- [ ] **Step 7: Update postinst**

Append `systemctl enable/start wedge100s-ledup-linkstate.service` block.

```bash
git add platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.postinst
git commit -m "feat(postinst): enable ledup-linkstate service on install"
```

- [ ] **Step 8: Push**

```bash
git push origin wedge100s/led-pipeline
```

---

## Task 8: Topic Branch — `wedge100s/flex-counters`

**Files:**
- Create: `$W100S/flex-counter-daemon/Makefile`
- Create: `$W100S/flex-counter-daemon/daemon.c`
- Create: `$W100S/flex-counter-daemon/bcmcmd_client.c`
- Create: `$W100S/flex-counter-daemon/bcmcmd_client.h`
- Create: `$W100S/flex-counter-daemon/stat_map.c`
- Create: `$W100S/flex-counter-daemon/stat_map.h`
- Create: `$W100S/flex-counter-daemon/compat.c`
- Create: `$W100S/service/wedge100s-flex-counter-daemon.service`
- Modify: postinst (add flex-counter-daemon enable)

- [ ] **Step 1: Create branch**

```bash
git checkout wedge100s/chipset-config
git checkout -b wedge100s/flex-counters
```

- [ ] **Step 2: Copy flex-counter-daemon sources**

```bash
W100S=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x
mkdir -p $W100S/flex-counter-daemon

for f in Makefile daemon.c bcmcmd_client.c bcmcmd_client.h stat_map.c stat_map.h compat.c; do
  git show wedge100s-source:$W100S/flex-counter-daemon/$f > $W100S/flex-counter-daemon/$f
done
```

- [ ] **Step 3: Commit daemon sources**

```bash
git add $W100S/flex-counter-daemon/
git commit -m "feat(counters): add flex-counter-daemon for hardware port counters

C daemon that reads BCM port statistics via bcmcmd Unix socket
and writes them to Redis COUNTERS_DB. Bypasses orchagent's
counter collection path which cannot handle dynamic port breakout.

Components:
- bcmcmd_client: Unix socket client for BCM diag shell commands
- stat_map: maps BCM counter names to SONiC COUNTERS_DB fields
- daemon: main loop with 1-second poll, Redis I/O, lane-count
  flex detection for breakout port support
- compat: hiredis static linking compatibility shim

Includes fixes for Redis auto-reconnect on broken connections,
I/O timeout to prevent hang during DPB, and uint64 underflow
protection on BCM counter reset."
```

- [ ] **Step 4: Copy and commit service file**

```bash
git show wedge100s-source:$W100S/service/wedge100s-flex-counter-daemon.service \
  > $W100S/service/wedge100s-flex-counter-daemon.service
git add $W100S/service/wedge100s-flex-counter-daemon.service
git commit -m "feat(service): add flex-counter-daemon systemd unit

Starts after syncd.service. Restarts on failure with 5s delay.
Shares bcmcmd socket with LED daemon via connect-on-demand."
```

- [ ] **Step 5: Update postinst**

Append `systemctl enable/start wedge100s-flex-counter-daemon.service` block to the postinst (branching from chipset-config, so this postinst has the base skeleton only — add the flex-counter block).

```bash
git add platform/broadcom/sonic-platform-modules-accton/debian/sonic-platform-accton-wedge100s-32x.postinst
git commit -m "feat(postinst): enable flex-counter-daemon on install"
```

- [ ] **Step 6: Push**

```bash
git push origin wedge100s/flex-counters
```

---

## Task 9: Topic Branch — `wedge100s/ztp`

**Files:**
- Create: `$DEVICE/ztp/l2-config_db.json`
- Create: `$DEVICE/ztp/ztp-l2-sample.json`

- [ ] **Step 1: Create branch**

```bash
git checkout wedge100s/device-identity
git checkout -b wedge100s/ztp
```

- [ ] **Step 2: Copy ZTP files**

```bash
DEVICE=device/accton/x86_64-accton_wedge100s_32x-r0
mkdir -p $DEVICE/ztp
git show wedge100s-source:$DEVICE/ztp/l2-config_db.json   > $DEVICE/ztp/l2-config_db.json
git show wedge100s-source:$DEVICE/ztp/ztp-l2-sample.json  > $DEVICE/ztp/ztp-l2-sample.json
```

- [ ] **Step 3: Commit**

```bash
git add $DEVICE/ztp/
git commit -m "feat(ztp): add L2 config_db.json and ZTP sample configuration

L2 baseline config_db.json for zero-touch provisioning:
- All 32 ports in VLAN 999 (default data VLAN)
- Management interface on eth0 with DHCP
- Loopback0 configured
- LLDP, SNMP, NTP enabled
- mgmt VRF disabled (causes SSH blackout on this platform)

ztp-l2-sample.json provides a working ZTP provisioning template."
```

- [ ] **Step 4: Push**

```bash
git push origin wedge100s/ztp
```

---

## Task 10: Topic Branch — `wedge100s/l3-bgp`

**Files:**
- Create: `$DEVICE/ztp/gen-l3-config.py`
- Create: `$DEVICE/ztp/gen_l3_config.py`
- Create: `$DEVICE/ztp/l3-config_db.json`
- Create: `$DEVICE/ztp/ztp-l3-sample.json`

- [ ] **Step 1: Create branch**

```bash
git checkout wedge100s/ztp
git checkout -b wedge100s/l3-bgp
```

- [ ] **Step 2: Copy L3 config files**

```bash
DEVICE=device/accton/x86_64-accton_wedge100s_32x-r0
git show wedge100s-source:$DEVICE/ztp/gen-l3-config.py   > $DEVICE/ztp/gen-l3-config.py
git show wedge100s-source:$DEVICE/ztp/gen_l3_config.py   > $DEVICE/ztp/gen_l3_config.py
git show wedge100s-source:$DEVICE/ztp/l3-config_db.json   > $DEVICE/ztp/l3-config_db.json
git show wedge100s-source:$DEVICE/ztp/ztp-l3-sample.json  > $DEVICE/ztp/ztp-l3-sample.json
chmod +x $DEVICE/ztp/gen-l3-config.py
```

- [ ] **Step 3: Commit**

```bash
git add $DEVICE/ztp/gen-l3-config.py \
       $DEVICE/ztp/gen_l3_config.py \
       $DEVICE/ztp/l3-config_db.json \
       $DEVICE/ztp/ztp-l3-sample.json
git commit -m "feat(l3): add L3 config generator and BGP-ready templates

gen-l3-config.py generates a complete L3 config_db.json with:
- Breakout-aware port naming (4x25G[10G] mode support)
- Per-port /31 point-to-point addressing
- BGP neighbor configuration for dual-ToR k8s topology
- Route policy hardening (prefix limits, route maps)

l3-config_db.json is the pre-generated L3 template.
ztp-l3-sample.json adds breakout-apply as a ZTP step."
```

- [ ] **Step 4: Push**

```bash
git push origin wedge100s/l3-bgp
```

---

## Task 11: Topic Branch — `wedge100s/submodule-patches`

**Files:**
- Create/Modify: `src/sonic-swss.patch/` (series + patches)
- Create: `src/sonic-utilities.patch/` (series + patches)
- Create: `src/sonic-ztp.patch/` (series + patches)
- Modify: `src/ptf-py3.patch/` (series + patches, if different from upstream)
- Modify: `src/sonic-dash-ha.patch/` (new, not on upstream)

- [ ] **Step 1: Create branch (independent of other topics)**

```bash
git checkout master
git checkout -b wedge100s/submodule-patches
```

- [ ] **Step 2: Copy patch directories that are NEW (not on upstream)**

```bash
for d in sonic-swss.patch sonic-utilities.patch sonic-ztp.patch sonic-dash-ha.patch; do
  mkdir -p src/$d
  git show wedge100s-source:src/$d/series > src/$d/series
  for p in $(cat src/$d/series); do
    git show wedge100s-source:src/$d/$p > src/$d/$p
  done
done
```

- [ ] **Step 3: Handle ptf-py3.patch (exists on upstream but we have changes)**

```bash
# Check what's different
git diff upstream/202511...wedge100s-source -- src/ptf-py3.patch/

# If we added patches, copy only our additions to the series and patch files
# If we modified existing patches, copy the full directory
mkdir -p src/ptf-py3.patch
git show wedge100s-source:src/ptf-py3.patch/series > src/ptf-py3.patch/series
for p in $(cat src/ptf-py3.patch/series); do
  git show wedge100s-source:src/ptf-py3.patch/$p > src/ptf-py3.patch/$p
done
```

- [ ] **Step 4: Commit**

```bash
git add src/sonic-swss.patch/ src/sonic-utilities.patch/ src/sonic-ztp.patch/ \
       src/sonic-dash-ha.patch/ src/ptf-py3.patch/
git commit -m "fix(patches): add quilt series for submodule build fixes

Patches for upstream submodules required to build on 202511:

sonic-swss (2 patches):
- Fix vxlanorch doTask using-declaration for gcc13
- Fix orchagent inherited method name hiding for gcc13

sonic-utilities (3 patches):
- Fix sfpshow SFF-8636 PM fallback and threshold dict
- Fix generate-completions fallback template for import failures
- Fix sonic-package-manager Docker init deferral during migration

sonic-ztp (2 patches):
- Fix Doxygen backslash escape sequences (Python 3.12 SyntaxWarning)
- Fix configdb-json use shutil.move instead of os.rename (cross-device)

sonic-dash-ha (1 patch):
- Fix cargo relative path for build dependencies

ptf-py3 (updated series):
- Additional patches for test framework compatibility"
```

- [ ] **Step 5: Push**

```bash
git push origin wedge100s/submodule-patches
```

---

## Task 12: Documentation Infrastructure

**Files:**
- Create: `$W100S/docs/conf.py`
- Create: `$W100S/docs/Makefile`
- Create: `$W100S/docs/index.rst`
- Create: `$W100S/docs/architecture.rst`
- Create: `$W100S/docs/api/*.rst`
- Create: `$W100S/docs/daemons/*.rst`
- Create: `$W100S/docs/guides/porting.rst`
- Create: `$W100S/docs/.gitignore`

This task runs AFTER all topic branches are merged into `master`. It adds documentation as a single commit on `master` (or on a `wedge100s/docs` topic branch if preferred).

- [ ] **Step 1: Create docs branch from master (after all topic merges)**

```bash
git checkout master
git pull origin master
git checkout -b wedge100s/docs
```

- [ ] **Step 2: Create Sphinx infrastructure**

Create `$W100S/docs/conf.py`:
```python
"""Sphinx configuration for Wedge 100S-32X platform documentation."""

project = 'Wedge 100S-32X SONiC Platform'
copyright = '2026, FlaxAdvisors'
author = 'FlaxAdvisors'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
]

# Napoleon settings for Google-style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = False

templates_path = []
exclude_patterns = ['_build']

html_theme = 'alabaster'

# Path to sonic_platform module for autodoc
import os
import sys
sys.path.insert(0, os.path.abspath('../sonic_platform'))
```

Create `$W100S/docs/Makefile`:
```makefile
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

.PHONY: help Makefile

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)
```

Create `$W100S/docs/.gitignore`:
```
_build/
```

- [ ] **Step 3: Create index.rst**

```rst
Wedge 100S-32X SONiC Platform
==============================

Platform support for the Accton Wedge 100S-32X (Facebook Wedge 100S)
running SONiC. This platform uses a Broadcom Memory (BCM56960) ASIC
with 32x100G QSFP28 ports.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   architecture
   api/index
   daemons/index
   guides/porting
```

- [ ] **Step 4: Write architecture.rst**

Document the platform architecture covering:
- Hardware overview (CP2112 USB-HID bridge, PCA9548 mux tree, OpenBMC, CPLD)
- I2C topology and the /run/wedge100s/ sysfs design choice
- Daemon architecture (i2c-daemon → bmc-daemon → flex-counter-daemon → ledup)
- Service dependency graph
- Data flow from hardware sensors to SONiC platform API

- [ ] **Step 5: Create API autodoc stubs**

Create `$W100S/docs/api/index.rst` and individual `.rst` files for each sonic_platform module (sfp, chassis, fan, psu, thermal, bmc, eeprom, component, watchdog, platform_smbus).

Each file uses Sphinx autodoc:
```rst
SFP Module
==========

.. automodule:: sfp
   :members:
   :undoc-members:
   :show-inheritance:
```

- [ ] **Step 6: Create daemon documentation**

Create `$W100S/docs/daemons/index.rst` and pages for i2c-daemon, bmc-daemon, flex-counter-daemon with:
- Purpose and design rationale
- Build instructions
- Configuration
- Systemd service relationships
- Key data structures and algorithms

- [ ] **Step 7: Write porting guide**

Create `$W100S/docs/guides/porting.rst` documenting how this platform was ported — intended as a template for others porting Accton/Broadcom platforms to SONiC.

- [ ] **Step 8: Add pydoc annotations to all Python source files**

For each `.py` file in `sonic_platform/` and `utils/`, add Google-style docstrings to every public class, method, and function. Focus on:
- Module-level docstring explaining purpose
- Class docstrings explaining what the class represents
- Method docstrings with Args, Returns, Raises sections

- [ ] **Step 9: Add Doxygen headers to all C source files**

For each `.c` and `.h` file, add `/** @brief */` function headers covering:
- Brief description
- @param descriptions
- @return description
- Key assumptions or constraints

- [ ] **Step 10: Commit and push**

```bash
git add $W100S/docs/ $W100S/sonic_platform/ $W100S/utils/ $W100S/flex-counter-daemon/
git commit -m "docs: add Sphinx API documentation and source annotations

Add Sphinx documentation infrastructure with autodoc for Python
modules and hand-written documentation for C daemons. Add
Google-style pydoc to all sonic_platform classes and Doxygen
headers to all C functions.

Build docs: make -C $W100S/docs html"
git push origin wedge100s/docs
```

---

## Task 13: Integration — Merge Topic Branches via PRs

- [ ] **Step 1: Create PRs in dependency order**

```bash
# Independent (can be created first)
gh pr create --base master --head wedge100s/submodule-patches \
  --title "wedge100s: add submodule quilt patches for 202511 build fixes" \
  --body "Quilt patch series for sonic-swss, sonic-utilities, sonic-ztp, sonic-dash-ha, and ptf-py3."

# Dependency chain
gh pr create --base master --head wedge100s/build-infra \
  --title "wedge100s: add build infrastructure for Wedge 100S-32X" \
  --body "Minimum build system changes to compile the wedge100s-32x platform module."

# After build-infra merges:
gh pr create --base master --head wedge100s/device-identity \
  --title "wedge100s: add device tree and base platform API" \
  --body "Device tree, hwsku, platform init, base sonic_platform classes, and postinst."

# Continue in order: chipset-config, i2c-bmc-sysfs, sfp-optics,
# led-pipeline, flex-counters, ztp, l3-bgp, docs
```

- [ ] **Step 2: Merge each PR after review**

Merge in dependency order. Each PR should build on the previously merged work.

- [ ] **Step 3: Verify final state**

```bash
git checkout master
git pull origin master
# Verify all platform files are present
find device/accton/x86_64-accton_wedge100s_32x-r0/ -type f | wc -l
find platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/ -type f | wc -l
ls src/sonic-swss.patch/ src/sonic-utilities.patch/ src/sonic-ztp.patch/
```

---

## Task 14: Verification — Build and Hardware Test

- [ ] **Step 1: Build the platform .deb from clean master**

```bash
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

Expected: .deb builds successfully.

- [ ] **Step 2: Install on hardware**

```bash
scp target/debs/trixie/sonic-platform-accton-wedge100s-32x*.deb admin@192.168.88.12:~
ssh admin@192.168.88.12 sudo systemctl stop pmon
ssh admin@192.168.88.12 sudo dpkg -i sonic-platform-accton-wedge100s-32x*.deb
ssh admin@192.168.88.12 sudo systemctl start pmon
```

- [ ] **Step 3: Verify platform services**

```bash
ssh admin@192.168.88.12 "systemctl status wedge100s-i2c-daemon wedge100s-bmc-daemon wedge100s-flex-counter-daemon wedge100s-ledup-linkstate"
ssh admin@192.168.88.12 "show platform summary"
ssh admin@192.168.88.12 "show interfaces transceiver eeprom"
```

Expected: All services active, platform detected, optics visible.
