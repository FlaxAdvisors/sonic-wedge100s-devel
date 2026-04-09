---
name: Clean fork status
description: Status of the FlaxAdvisors/sonic-buildimage clean fork — 11 PRs merged, sonic-utilities patch needs test fix, build verification pending
type: project
---

## Clean Fork — Status as of 2026-04-08

**Completed:**
- Repo reset: master = upstream/202511, upstream tracking branch created
- 10 topic branches created and merged via PRs #9-#18
- Documentation PR #19 merged (Sphinx, pydoc, Doxygen)
- Design spec: `docs/superpowers/specs/2026-04-08-clean-fork-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-08-clean-fork.md`

**Pending:**
1. **sonic-utilities patch 0001 needs test expectations updated** — our patch fixes sfpshow SFF-8636 PM display but upstream tests assert old broken behavior. 4 tests fail: `test_qsfp_dd_pm`, `test_qsfp_dd_pm_with_ns`, `test_qsfp_dd_pm_without_ns`, `test_qsfp_dd_pm_all`. Fix goes on `wedge100s/submodule-patches` branch → PR to master.
2. **Build verification** — `BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb` failed due to #1. Rebuild after patch fix.
3. **SSH connectivity to target** — blocked at time of session end, needs serial console debugging.

**Why:** `BUILD_SKIP_TEST=y` only skips .deb tests, not Python wheel tests. The wheel test gate is `$($*_TEST)` in slave.mk line 1014 — unset defaults to running pytest.
