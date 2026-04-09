---
name: reference_submodule_patches
description: Skill location and summary for managing sonic-buildimage submodule changes via quilt patch files
type: reference
---

Skill file: `~/.claude/skills/sonic-submodule-patches/SKILL.md`

Covers the quilt-based patch workflow used in sonic-buildimage to preserve submodule edits across `make distclean` / `make init`. Patch dirs live at `src/{submodule}.patch/` (tracked in main repo), with a `series` file listing patches in apply order. `slave.mk` auto-applies them via `quilt push -a` before each build and removes them after.

Key commands:
- Export change: `git format-patch HEAD~1 --output-directory ../{sub}.patch/`
- Apply manually: `QUILT_PATCHES=../{sub}.patch quilt push -a`
- Remove manually: `quilt pop -a -f && rm -rf .pc`
