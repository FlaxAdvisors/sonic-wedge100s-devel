---
name: reference_platform_hierarchy
description: Which platform to use as reference when implementing features for Wedge 100S-32X
type: feedback
---

For platform-level implementation (chassis API, EEPROM, show commands, device config), use this reference hierarchy:

1. **`device/facebook/x86_64-facebook_wedge100-r0/`** — closest hardware sibling (same Tomahawk ASIC, same BMC lineage, same form factor)
2. **`/export/sonic/OpenNetworkLinux/packages/platforms/accton/x86-64/wedge100s-32x/`** - identical hardware, different NOS
3. **`device/accton/x86_64-accton_as7712_32x-r0/`** — same Accton/SONiC software stack, different ASIC topology

**Why:** The Facebook Wedge100 (1) shares the exact same hardware design as the Accton Wedge 100S-32X (same BMC, same EEPROM format, same I2C topology), making it a more faithful reference than the AS7712 for low-level platform behavior.

**How to apply:** Before implementing any platform feature, check the Facebook Wedge100 device directory first, then the ONL wedge100s-32x directory, and finally the AS7712 as reference.
