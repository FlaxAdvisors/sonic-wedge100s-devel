# sonic-wedge100s-devel

Development tools, tests, and documentation for the [Wedge 100S-32X SONiC platform port](https://github.com/FlaxAdvisors/sonic-buildimage).

> **Note:** This is the development companion repo. The platform code lives in [FlaxAdvisors/sonic-buildimage](https://github.com/FlaxAdvisors/sonic-buildimage) (based on the `202511` release branch).

## Contents

| Directory | Description |
|---|---|
| `tests/` | Hardware pytest suite (25+ staged phases) |
| `notes/` | Investigation findings, hardware verification, debugging sessions |
| `docs/superpowers/` | Design specs and implementation plans |
| `guides/` | Setup, configuration, and operational guides (with PDF generation) |
| `tools/` | Deployment, topology, and automation scripts |
| `cfg/` | Reference config_db.json snapshots |
| `utils/` | LEDUP diagnostic reader scripts |
| `patches/` | Build environment toggles (wedge100s-only build mode) |

## Quick Start

See `guides/SONiC-wedge100s-Initial-Setup-Guide.md` for first-time setup.

### Running Tests

```bash
# Configure target connection
cat tests/target.cfg

# Run all stages against hardware
cd tests && python3 run_tests.py

# Run a single stage
cd tests && pytest stage_01_eeprom/ -v
```

## Related Repos

- **Platform code:** [FlaxAdvisors/sonic-buildimage](https://github.com/FlaxAdvisors/sonic-buildimage) — SONiC fork with Wedge 100S-32X support
- **Upstream:** [sonic-net/sonic-buildimage](https://github.com/sonic-net/sonic-buildimage) — SONiC build infrastructure
