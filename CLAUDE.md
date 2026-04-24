# CLAUDE.md

Guidance for Claude Code working in the wedge100s devel workspace.

## Project

Porting the Accton Wedge 100S-32X (Facebook Wedge 100S, Broadcom Tomahawk) to SONiC.

This is the **development companion repo** (`FlaxAdvisors/sonic-wedge100s-devel`). Platform code lives in `FlaxAdvisors/sonic-buildimage`.

Act as the expert. Take direction for changes but compare proposed implementations to other Accton/Broadcom platforms and the ONL wedge100s implementation.

## Repository Layout

| Repo | Where It Lives | Purpose |
|---|---|---|
| `FlaxAdvisors/sonic-buildimage` | `play-sonic:/export/sonic/sonic-buildimage` (remote) | Platform fork (clean build, based on 202511). Build host only. |
| `FlaxAdvisors/sonic-wedge100s-devel` | `/home/flax/git/sonic-wedge100s-devel` (this host, foreman) | This repo: tests, tools, notes, docs, workflow |

## Build Host Access

The `sonic-buildimage` fork is **not cloned locally on this host** (foreman lacks build capacity). All work on the platform fork runs on `play-sonic` via SSH through the `bang-fiesta` ProxyCommand configured in `~/.ssh/config`.

```bash
# Git operations on the fork
ssh play-sonic 'cd /export/sonic/sonic-buildimage && git <...>'

# Builds
ssh play-sonic 'cd /export/sonic/sonic-buildimage && BLDENV=trixie make <target>'

# Pull a built artifact back to this host
scp play-sonic:/export/sonic/sonic-buildimage/target/sonic-broadcom.bin ~/Downloads/
```

Editing files inside the fork requires either an SSH heredoc write or committing through the remote working copy directly. The skills listed below assume this remote-over-SSH model.

## ⛔ Development Workflow — MANDATORY

**Read [`docs/workflow.md`](docs/workflow.md) before ANY platform fork work.** It is the authoritative reference covering:

1. **Topic branch discipline** — all changes go through `wedge100s/<topic>` branches (see `wedge100s-topic-branches` skill)
2. **Submodule patches** — changes in `src/<submodule>/` must be quilt patches (see `sonic-submodule-patches` skill)
3. **Documentation mandate** — docstrings/Doxygen live WITH the code, same branch, same commit (see `wedge100s-doc-check` skill)
4. **Build verification** — verify builds after merging (see `wedge100s-build-verify` skill)
5. **Branch audits** — periodic health checks (see `wedge100s-branch-audit` skill)

## ⛔ I2C Bus Safety on Target Hardware

**NEVER touch the I2C bus while wedge100s-i2c-daemon or pmon are running.**

The CP2112 USB-HID bridge is a single shared resource. Concurrent access corrupts transactions, mux states, and EEPROM cache files.

**Before ANY i2c bus access or /run/wedge100s/ file manipulation on the target:**
```bash
sudo systemctl stop wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```
**After:**
```bash
sudo systemctl start wedge100s-i2c-daemon wedge100s-bmc-daemon pmon
```

All i2c data and debugging should use the `/run/wedge100s/` sysfs interface. Exceptions only for new features.

## Scope and Retry

- Read only files explicitly named in the prompt unless you ask first
- Do not refactor, add comments, or clean up code outside the stated task
- Non-zero Bash exit codes are normal — try up to 3 different workarounds
- After 3 failed attempts, surface full error output and ask for guidance

## SSH Access to Hardware

Permissions: unfettered SSH access to all hardware targets via `~/.claude/settings.json` wildcard allow.

The home-lab switch (`lapin`) sits on the dedicated `enp2s0 ↔ wedge100s-mgmt` link, addressed `192.168.99.0/24` by foreman's dnsmasq (see "Home Lab Network" below). Both `lapin` and `lapin-bmc` have static DHCP reservations and `~/.ssh/config` aliases — `ssh lapin` and `ssh lapin-bmc` work directly.

| Target | Access | Notes |
|---|---|---|
| SONiC switch | `ssh admin@lapin` (192.168.99.20) | Kernel 6.12-sonic-amd64, use python3. Default password `YourPaSsWoRd` for first ssh-copy-id. |
| ONIE | `ssh root@lapin` (192.168.99.20) | When booted into ONIE rescue. No python. |
| OpenBMC | `ssh root@lapin-bmc` (192.168.99.21, pw `0penBmc`) | OpenBMC 4.1.51. No python; `authorized_keys` cleared on reboot. udhcpc only fires once at POST — see feedback memory. |
| BMC IPv6 LL fallback | `ssh root@fe80::82a2:35ff:fe71:2d09%enp2s0` | EUI-64 from BMC MAC `80:a2:35:71:2d:09`. Works even when BMC's DHCP didn't fire. |
| Host serial console (via BMC) | `ssh lapin-bmc /usr/local/bin/sol.sh` | Exit with `<Enter>~.` |

**BMC reachability after reboot:** `authorized_keys` is cleared. If ping works but SSH fails, run:
```bash
sshpass -p '0penBmc' ssh-copy-id -o StrictHostKeyChecking=no root@lapin-bmc
```

## Home Lab Network

Foreman serves DHCP, HTTP (for ONIE network installs), and NAT to the wedge100s on the dedicated wired link.

| Component | Where | Notes |
|---|---|---|
| `enp2s0` (wired) | `192.168.99.1/24` static via `/etc/netplan/02-enp2s0.yaml` (renderer: networkd) | NM unmanages it via `/etc/NetworkManager/conf.d/99-unmanaged-enp2s0.conf` |
| `wlp3s0` (wifi) | NetworkManager-managed, home LAN | Untouched — losing it would lose the headless box |
| dnsmasq (DHCP) | `/etc/dnsmasq.d/switch-mgmt.conf` | DHCP-only (`port=0`, no DNS), `bind-dynamic`, range `.10-.50`, reservations for lapin/lapin-bmc |
| Apache (HTTP) | `/etc/apache2/sites-available/srv-htdocs.conf` → `/srv/www/htdocs` | Serves NOS installers for `onie-nos-install`. Foreman vhosts disabled. |
| NAT | `iptables-persistent` MASQUERADE on `wlp3s0` for `192.168.99.0/24` | Lets switch reach internet via wifi |
| Foreman / Puppet stack | Stopped + disabled | Was hijacking port 80; replaced by simple apache vhost |

## Key Paths

### Platform Fork (`play-sonic:/export/sonic/sonic-buildimage`)

All paths below are relative to the build host — prefix with `ssh play-sonic 'cd /export/sonic/sonic-buildimage && …'` to access.

| Resource | Path (on play-sonic) |
|---|---|
| Device directory | `device/accton/x86_64-accton_wedge100s_32x-r0/` |
| Platform modules | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/` |
| Submodule patches | `src/*.patch/` |

### This Repo (`/home/flax/git/sonic-wedge100s-devel`)

| Resource | Path |
|---|---|
| Workflow bible | `docs/workflow.md` |
| Developer's guide | `guides/SONiC-wedge100s-Developers-Guide.md` |
| Test suite | `tests/` |
| Notes | `notes/` |
| Skills | `.claude/skills/` |

### Reference Platforms (on play-sonic)

| Resource | Path |
|---|---|
| ONL Wedge100S | `play-sonic:/export/sonic/OpenNetworkLinux/packages/platforms/accton/x86-64/wedge100s-32x/` |
| Facebook Wedge100 | `device/facebook/x86_64-facebook_wedge100-r0/` (inside the fork, closest HW sibling) |
| AS7712 | `device/accton/x86_64-accton_as7712_32x-r0/` (inside the fork, same Accton SW stack) |

## Build Quick Reference

Builds run on **play-sonic** — foreman does not have build capacity. See `wedge100s-build-verify` skill and `guides/SONiC-wedge100s-Developers-Guide.md` Section 3 for full details.

```bash
# Platform .deb (trixie — host filesystem)
ssh play-sonic 'cd /export/sonic/sonic-buildimage && BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb'

# Submodule packages (bookworm — Docker containers)
ssh play-sonic 'cd /export/sonic/sonic-buildimage && BLDENV=bookworm make target/debs/bookworm/swss_1.0.0_amd64.deb'

# Full ONIE image (no BLDENV prefix — runs both passes)
ssh play-sonic 'cd /export/sonic/sonic-buildimage && make target/sonic-broadcom.bin'

# Pull a finished image back to this host for deploy to the home-lab switch
scp play-sonic:/export/sonic/sonic-buildimage/target/sonic-broadcom.bin ~/Downloads/
```

## Test Runner

```bash
cd tests && python3 run_tests.py       # All stages
cd tests && pytest stage_01_eeprom/ -v  # Single stage
```

## Notes Rule

On completion of any investigation or implementation phase, write findings to `notes/<topic>.md` before summarizing inline. Use bullet points, code blocks, and mark hardware-verified items with `(verified on hardware YYYY-MM-DD)`.
