---
name: Two-repo layout for Wedge 100S SONiC port
description: Platform code in FlaxAdvisors/sonic-buildimage (topic branch workflow), devel artifacts in FlaxAdvisors/sonic-wedge100s-devel
type: reference
---

## Repository Layout

**Platform fork:** `FlaxAdvisors/sonic-buildimage` (GitHub fork of sonic-net/sonic-buildimage)
- Local clone: `/export/sonic/sonic-buildimage` (clean build clone)
- Local sandbox: `/export/sonic/sonic-buildimage.claude` (original dev workspace, being deprecated)
- Based on: `sonic-net/sonic-buildimage:202511` release branch
- Branch `upstream` tracks sonic-net 202511; `master` is integrated merge-ready state
- All changes go through topic branches (`wedge100s/<topic>`) → PR → merge to master
- See `wedge100s-topic-branches` skill for workflow

**Devel repo:** `FlaxAdvisors/sonic-wedge100s-devel`
- Local clone: `/export/sonic/sonic-wedge100s-devel`
- Contains: tests, notes, guides, tools, cfg, utils, patches, design specs/plans
- Branch `initial` has the raw import; `main` will be created after reorganization
- .claude/ directory (memory, skills, settings) lives here

**Key paths in the platform fork:**
- Device tree: `device/accton/x86_64-accton_wedge100s_32x-r0/`
- Platform modules: `platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
- Submodule patches: `src/*.patch/`
- Build rules: `platform/broadcom/platform-modules-accton.mk`
