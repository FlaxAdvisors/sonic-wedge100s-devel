# TPM Integration Investigation (GAP-023)

**Date:** 2026-04-09
**Task:** P2 Feature Work — Task 7: TPM integration investigation
**Branch:** `initial` (devel repo — no platform fork changes)
**Status:** DEFERRED — hardware limitation (BMC-only TPM 1.2)

## Summary

Probed the Wedge 100S TPM from both the BMC and the SONiC host to
determine whether SONiC integration is feasible. The investigation
**confirms the PLATFORM_GUIDE's assessment**: the TPM is BMC-only and
is a TPM 1.2 part, which SONiC 202511 does not support. No further work
is warranted. Recommendation: close GAP-023 as deferred.

One correction to the platform guide: the TPM is wired to **BMC I2C
bus 9**, not bus 10 as section 15 states. The bus-10 reference in
section 15 / the bus-topology table on line 852 should be updated.

## Investigation Steps

All probes were performed with `wedge100s-i2c-daemon`,
`wedge100s-bmc-daemon`, and `pmon` stopped per the I2C bus safety rule.
Daemons were restarted after probing; all three verified `active`.

### Host-side (SONiC, 192.168.88.12)

Host kernel: `6.12.41+deb13-sonic-amd64`.

```text
# ls /dev/tpm*
ls: cannot access '/dev/tpm*': No such file or directory

# ls /sys/class/tpm/
(empty)

# dmesg | grep -i tpm
[    1.120020] ima: No TPM chip found, activating TPM-bypass!
[    4.516953] systemd[1]: systemd-pcrextend.socket - TPM PCR Measurements
               was skipped because of an unmet condition check
               (ConditionSecurity=measured-uki).
[    4.600963] systemd[1]: systemd-tpm2-setup-early.service - Early TPM SRK
               Setup was skipped ...
```

- **No TPM visible on host.** IMA falls back to TPM-bypass; systemd-tpm2
  services skip because no TPM2 device exists.
- Host kernel *has* `tpm_i2c_infineon.ko` available, but nothing
  instantiates the I2C client because the TPM is on the BMC-side I2C
  topology, not on any CP2112 mux leg.

### BMC-side (OpenBMC, 192.168.88.13)

Accessed via switch-host → BMC key (`/etc/sonic/wedge100s-bmc-key`).
Direct sshpass from the devel host hit persistent connection stalls
during this session; switch-jump using the key worked reliably.

BMC kernel: `4.1.51 armv5tejl` (Facebook OpenBMC 0.4 "rocko").

```text
# lsmod | grep -i tpm
tpm_i2c_infineon 6388 1 - Live 0xbf02f000
tpm              17553 2 tpm_i2c_infineon, Live 0xbf025000

# ls /sys/class/tpm/
tpm0

# ls /dev/tpm*
/dev/tpm   /dev/tpm0

# readlink -f /sys/class/tpm/tpm0/device
/sys/bus/i2c/devices/9-0020
```

The TPM is driven by `tpm_i2c_infineon` on the BMC as **i2c client
9-0020** (bus 9, address 0x20). The driver is loaded at BMC boot via
`/etc/modules-load.d` (entries: `tpm`, `tpm_i2c_infineon`) and the I2C
client is instantiated from `/etc/init.d/setup_i2c.sh`:

```text
# 9 0x20 tpm_i2c_infineon added by trousers.init.sh
```

This also correctly identifies a **documentation bug** — the
PLATFORM_GUIDE reports BMC_I2C_10; hardware and BMC init scripts agree on
BMC_I2C_9.

### TPM identification

```text
# cat /sys/class/tpm/tpm0/device/caps
Manufacturer: 0x49465800
TCG version: 1.2
Firmware version: 133.32

# cat /sys/class/tpm/tpm0/device/enabled
0
# cat /sys/class/tpm/tpm0/device/active
0
# cat /sys/class/tpm/tpm0/device/owned
0
```

Interpretation:

- Manufacturer `0x49465800` = ASCII `"IFX\0"` = **Infineon**.
- **TCG version 1.2** — this is a **TPM 1.2** part, not 2.0.
- Firmware 133.32.
- TPM is currently **disabled, inactive, and unowned** — no SRK exists;
  no one has ever taken ownership.

Also confirmed via TrouSerS userspace (tcsd is already running on the
BMC, pid 900, owned by `tss`):

```text
# tpm_version
  TPM 1.2 Version Info:
  Chip Version:        1.2.133.32
  Spec Level:          2
  Errata Revision:     3
  TPM Vendor ID:       IFX
  Vendor Specific data: 85200050 0074706d 3530ffff ff
  TPM Version:         01010000
  Manufacturer Info:   49465800
```

Vendor-specific data embeds the ASCII `tpm50` — this matches Infineon's
SLB 96xx I2C TPM 1.2 product family. The specific part mapping
(SLB 9635 vs SLB 9645) is not distinguishable from this signature alone,
but the TCG generation is unambiguous: **TPM 1.2 over I2C, Infineon**.
For all downstream decisions, the part being 1.2 is what matters; the
exact SKU does not change the outcome.

The BMC rootfs already carries the TPM 1.2 toolchain:

```text
/usr/sbin/tpm_selftest
/usr/sbin/tpm_version
/usr/sbin/tpm_getpubek
/etc/init.d/trousers        (init script, tcsd running)
```

No TPM 2.0 tooling (`tpm2-tools`, `tpm2-abrmd`) on the BMC — consistent
with the hardware being TPM 1.2 only.

## Answers to the Investigation Questions

1. **Is the TPM accessible from the BMC? Which address? Which part?**
   Yes. Bound at `9-0020` (BMC i2c bus **9**, addr `0x20`) via the
   Linux `tpm_i2c_infineon` driver. Exposed at `/dev/tpm0` and
   `/sys/class/tpm/tpm0/`. `tpm_version` confirms Infineon TPM 1.2.
   **Platform guide bus number is wrong — should be 9, not 10.**

2. **Is the TPM accessible from the host? If not, what would be needed?**
   No. Host has no `/dev/tpm*`, `/sys/class/tpm/` is empty, and
   `ima: No TPM chip found, activating TPM-bypass!` appears at boot.
   The TPM's I2C signals terminate on the BMC's AST2400 controller and
   are **physically not wired to the COM-e CPU's I2C buses or the
   CP2112 USB-HID bridge**. There is no pinmux or bus arbiter that
   could hand the chip to the host — you cannot reconfigure this with
   software. To get host access you would need a BMC-mediated proxy:
   a userspace daemon on the BMC that exposes TSS/TPM commands over
   the BMC↔host USB-CDC-ECM or the OOB REST API, plus a host-side
   pseudo-TPM shim. That is a significant effort and creates new
   attack surface on an already-weak OpenBMC.

3. **Is the TPM 1.2 or 2.0?**
   **TPM 1.2.** `caps` says `TCG version: 1.2`; `tpm_version` says
   `Spec Level: 2, Errata Revision: 3, TPM Version: 01010000`.

4. **If TPM 1.2 only: SONiC 202511 TPM support status.**
   SONiC 202511 does not ship TPM 1.2 userspace. The host systemd 257
   build has `+TPM2` baked in and spins up `systemd-tpm2-setup-*` at
   boot — all of which depend on a TPM 2.0 `/dev/tpmrm0` device.
   There is no TrouSerS, `tpm-tools`, or `tcsd` in the SONiC base
   image. Measured boot, remote attestation, and secure key storage
   features in SONiC assume TPM 2.0. Integrating a TPM 1.2 would
   require back-porting the TrouSerS/`tpm-tools` stack into the SONiC
   image — which has its own CVE history and is upstream-EOL. Not a
   reasonable path forward.

5. **BMC-only + remote attestation cost.**
   The only theoretically-useful integration path is **BMC-side
   attestation**: BMC measures its own firmware into the TPM and
   exports a quote over the OOB network. This would require:
   - Bringing up and *owning* the TPM on the BMC (currently disabled,
     unowned — would need first-boot provisioning).
   - Writing BMC measured-boot hooks (U-Boot on the AST2400 does not
     do measured boot out of the box in this OpenBMC revision).
   - An attestation service on the BMC to serve quotes.
   - A verifier on the host or on an external system.
   Plus the underlying OpenBMC is Rocko (2017 Yocto, EOL) with a 4.1
   kernel and the known security posture documented in
   `PLATFORM_GUIDE.md` §15 (default password cannot be changed, no
   IPMI auth, REST unauthenticated, BMC↔host USB provides root). A
   TPM quote over an untrusted BMC transport adds little trust.

## Decision

**Close GAP-023 as DEFERRED — hardware limitation (BMC-only TPM 1.2).**

Rationale:

- Hardware is TPM 1.2, and SONiC 202511's security plumbing is TPM 2.0.
- TPM is physically BMC-side only; no software workaround can expose
  it to the host I2C topology.
- A BMC-mediated proxy would be large, legacy-dependent, and of
  dubious value given the OpenBMC security posture.
- No SONiC feature currently in the port requires a TPM.

No new `wedge100s/security` branch is created. No platform fork
changes. This note is the sole artifact of Task 7.

## Follow-up Items (not blocking)

These are low-priority corrections that belong in a future docs pass,
not in this investigation commit:

- **Platform guide bus correction:** `PLATFORM_GUIDE.md` §15 and the
  bus-topology table at line 852 should change "BMC_I2C_10" to
  "BMC_I2C_9" for the TPM entry. Hardware-verified on 2026-04-09.
- `PLATFORM_GUIDE.md` §15 "SONiC Security Implementation Status" row
  for TPM should be updated from "BMC-side only; requires firmware
  support" to "BMC-side only, TPM 1.2 (Infineon IFX, fw 133.32);
  SONiC 202511 requires TPM 2.0 — not feasible."
- The GAP-023 entry in `DESIGNGAPS.md` can be marked deferred with a
  pointer to this note.

## Hardware-Verified Facts (2026-04-09)

- BMC `/dev/tpm0` exists and responds to `tpm_version` (verified on
  hardware 2026-04-09).
- BMC i2c client: `9-0020`, driver `tpm_i2c_infineon` (verified on
  hardware 2026-04-09).
- TPM 1.2, Infineon, fw 133.32, disabled/inactive/unowned (verified
  on hardware 2026-04-09).
- Host SONiC kernel logs `ima: No TPM chip found, activating
  TPM-bypass!` at boot; no `/dev/tpm*`, no `/sys/class/tpm/*`
  (verified on hardware 2026-04-09).
- `wedge100s-i2c-daemon`, `wedge100s-bmc-daemon`, and `pmon` were
  stopped before probing and confirmed `active` after restart
  (verified on hardware 2026-04-09).
