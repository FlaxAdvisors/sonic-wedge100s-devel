# CLAUDE.md

Guidance for Claude Code working in the wedge100s devel workspace.

## Project

Porting the Accton Wedge 100S-32X (Facebook Wedge 100S, Broadcom Tomahawk) to SONiC.

This is the **development companion repo** (`FlaxAdvisors/sonic-wedge100s-devel`). Platform code lives in `FlaxAdvisors/sonic-buildimage`.

Act as the expert. Take direction for changes but compare proposed implementations to other Accton/Broadcom platforms and the ONL wedge100s implementation.

## Repository Layout

| Repo | Local Path | Purpose |
|---|---|---|
| `FlaxAdvisors/sonic-buildimage` | `/export/sonic/sonic-buildimage` | Platform fork (clean build, based on 202511) |
| `FlaxAdvisors/sonic-wedge100s-devel` | `/export/sonic/sonic-wedge100s-devel` | This repo: tests, tools, notes, docs, workflow |

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

| Target | Access | Notes |
|---|---|---|
| SONiC switch | `ssh admin@192.168.88.12` | Kernel 6.1.0-29-2-amd64, use python3 |
| ONIE | `ssh root@192.168.88.12` | No python available |
| OpenBMC | `ssh root@192.168.88.13` (pw: `0penBmc`) | No python; `authorized_keys` cleared on reboot |
| BMC fallback | `root@fe80::ff:fe00:1%usb0` or `/dev/ttyACM0` @ 57600 | Key: `/etc/sonic/wedge100s-bmc-key` |
| Peer (Arista EOS) | `sshpass -p '0penSesame' ssh -tt admin@192.168.88.14` | |
| Serial console | `ssh bang-lorax tail -n 500 screenlog.ttyUSB2.0` | |

**BMC reachability:** After BMC reboot, `authorized_keys` is cleared. If ping works but SSH fails, use `sshpass -p '0penBmc' ssh-copy-id -o StrictHostKeyChecking=no root@192.168.88.13` instead of prompting the user.

## Key Paths

### Platform Fork (`/export/sonic/sonic-buildimage`)

| Resource | Path |
|---|---|
| Device directory | `device/accton/x86_64-accton_wedge100s_32x-r0/` |
| Platform modules | `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/` |
| Submodule patches | `src/*.patch/` |

### This Repo (`/export/sonic/sonic-wedge100s-devel`)

| Resource | Path |
|---|---|
| Workflow bible | `docs/workflow.md` |
| Developer's guide | `guides/SONiC-wedge100s-Developers-Guide.md` |
| Test suite | `tests/` |
| Notes | `notes/` |
| Skills | `.claude/skills/` |

### Reference Platforms

| Resource | Path |
|---|---|
| ONL Wedge100S | `/export/sonic/OpenNetworkLinux/packages/platforms/accton/x86-64/wedge100s-32x/` |
| Facebook Wedge100 | `device/facebook/x86_64-facebook_wedge100-r0/` (closest HW sibling) |
| AS7712 | `device/accton/x86_64-accton_as7712_32x-r0/` (same Accton SW stack) |

## Build Quick Reference

See `wedge100s-build-verify` skill and `guides/SONiC-wedge100s-Developers-Guide.md` Section 3 for full details.

```bash
# Platform .deb (trixie — host filesystem)
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb

# Submodule packages (bookworm — Docker containers)
BLDENV=bookworm make target/debs/bookworm/swss_1.0.0_amd64.deb

# Full ONIE image (no BLDENV prefix — runs both passes)
make target/sonic-broadcom.bin
```

## Test Runner

```bash
cd tests && python3 run_tests.py       # All stages
cd tests && pytest stage_01_eeprom/ -v  # Single stage
```

## Notes Rule

On completion of any investigation or implementation phase, write findings to `notes/<topic>.md` before summarizing inline. Use bullet points, code blocks, and mark hardware-verified items with `(verified on hardware YYYY-MM-DD)`.
