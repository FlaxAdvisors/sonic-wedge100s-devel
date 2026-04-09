---
name: feedback_bmc_reboot
description: BMC reboot on Wedge100S-32X causes host power cycle — never recommend BMC reboot without verifying
type: feedback
---

BMC reboot (`sudo reboot` on root@192.168.88.13) is SAFE — it does NOT reboot the SONiC host.

**Why:** The BMC serial console (`sol.sh`) drops when BMC reboots, making it look like the host went down — but the SONiC switch keeps running. Confirmed 2026-03-20.

**How to apply:** BMC reboot is a safe recovery option for I2C bus hangs on ast-i2c.13. After ~90s the BMC is back up. Run `ssh-copy-id root@192.168.88.13` (password: `0penBmc`) to restore key access after reboot.

**NOTE:** There are better GPIO methods on the BMC to clear the host i2c bus hangs.

Also: raw `gpioset` on the BMC for QSFP TXDIS control is unsafe. The TXDIS lines are on BMC I2C bus 13 (ast-i2c.13) which the BMC's own management loop polls continuously. Raw gpioset races with that loop and causes I2C bus hangs. Use the OpenBMC REST API or proper service interface instead.
