# CPLD Register Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose ~15 new CPLD sysfs attributes covering PSU alarm/input-OK, power rail health, reset reason, ROV voltage, board revision, and COM-e status — closing GAP-002, GAP-010, GAP-012, GAP-013, GAP-014, GAP-020, GAP-025, and GAP-030.

**Architecture:** Add register defines + show functions + DEVICE_ATTRs to `wedge100s_cpld.c`, extend `poll_cpld()` in `wedge100s-i2c-daemon.c` to mirror new attrs to `/run/wedge100s/`, then wire into Python platform API (`psu.py`, `component.py`). All changes are additive — no existing behavior changes.

**Tech Stack:** C (kernel module, userspace daemon), Python 3 (SONiC platform API), pytest (hardware tests over SSH)

**Platform fork path prefix:** `/export/sonic/sonic-buildimage/platform/broadcom/sonic-platform-modules-accton/wedge100s-32x/`
**Devel repo path prefix:** `/export/sonic/sonic-wedge100s-devel/`
**Topic branch:** `wedge100s/i2c-bmc-sysfs` in `/export/sonic/sonic-buildimage`

---

### Task 1: Add PSU alarm and input-OK sysfs attributes to CPLD driver

**Gaps:** GAP-013, GAP-014
**Files:**
- Modify: `modules/wedge100s_cpld.c`

- [ ] **Step 1: Add register bit defines**

In `wedge100s_cpld.c`, after the existing PSU bit defines (line 51), add:

```c
#define PSU1_INPUT_OK_BIT  2  /* 0 = input bad, 1 = input OK */
#define PSU1_ALARM_BIT     3  /* 0 = alarm active, 1 = normal */
#define PSU2_INPUT_OK_BIT  6  /* 0 = input bad, 1 = input OK */
#define PSU2_ALARM_BIT     7  /* 0 = alarm active, 1 = normal */
```

- [ ] **Step 2: Add show functions for PSU alarm**

After `show_psu2_pgood()` (line 200), add:

```c
/** @brief Show PSU1 alarm status (1=normal, 0=alarm). Active-high bit 3 of reg 0x10. */
static ssize_t show_psu1_alarm(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_PSU_STATUS);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n",
                     (val >> PSU1_ALARM_BIT) & 1);
}

/** @brief Show PSU1 input power OK (1=OK, 0=bad). Active-high bit 2 of reg 0x10. */
static ssize_t show_psu1_input_ok(struct device *dev,
                                   struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_PSU_STATUS);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n",
                     (val >> PSU1_INPUT_OK_BIT) & 1);
}

/** @brief Show PSU2 alarm status (1=normal, 0=alarm). Active-high bit 7 of reg 0x10. */
static ssize_t show_psu2_alarm(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_PSU_STATUS);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n",
                     (val >> PSU2_ALARM_BIT) & 1);
}

/** @brief Show PSU2 input power OK (1=OK, 0=bad). Active-high bit 6 of reg 0x10. */
static ssize_t show_psu2_input_ok(struct device *dev,
                                   struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_PSU_STATUS);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n",
                     (val >> PSU2_INPUT_OK_BIT) & 1);
}
```

- [ ] **Step 3: Add DEVICE_ATTR entries and register them**

After the existing `DEVICE_ATTR` block (line 292), add:

```c
static DEVICE_ATTR(psu1_alarm,    S_IRUGO, show_psu1_alarm,    NULL);
static DEVICE_ATTR(psu1_input_ok, S_IRUGO, show_psu1_input_ok, NULL);
static DEVICE_ATTR(psu2_alarm,    S_IRUGO, show_psu2_alarm,    NULL);
static DEVICE_ATTR(psu2_input_ok, S_IRUGO, show_psu2_input_ok, NULL);
```

Add to the `wedge100s_cpld_attrs[]` array (before the NULL terminator):

```c
    &dev_attr_psu1_alarm.attr,
    &dev_attr_psu1_input_ok.attr,
    &dev_attr_psu2_alarm.attr,
    &dev_attr_psu2_input_ok.attr,
```

- [ ] **Step 4: Update the file header docstring**

Add to the sysfs attributes comment block at the top of the file:

```c
 *   psu1_alarm    (RO) — 1 = normal, 0 = alarm     (bit 3 of 0x10, active-high)
 *   psu1_input_ok (RO) — 1 = input OK, 0 = bad     (bit 2 of 0x10, active-high)
 *   psu2_alarm    (RO) — 1 = normal, 0 = alarm     (bit 7 of 0x10, active-high)
 *   psu2_input_ok (RO) — 1 = input OK, 0 = bad     (bit 6 of 0x10, active-high)
```

- [ ] **Step 5: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

Expected: Build succeeds. The .deb contains the updated `wedge100s_cpld.ko`.

- [ ] **Step 6: Commit**

```bash
git add modules/wedge100s_cpld.c
git commit -m "feat(platform): expose PSU alarm and input-OK sysfs attributes

Add 4 new read-only sysfs attributes from CPLD register 0x10:
  psu1_alarm, psu1_input_ok, psu2_alarm, psu2_input_ok

OCP spec v1.3 section 7.7.2 defines bits D[2],D[3],D[6],D[7] of
register 0x10 for PSU input power quality and alarm status.

Closes: GAP-013, GAP-014"
```

---

### Task 2: Add power rail health and board revision sysfs attributes

**Gaps:** GAP-012, GAP-030
**Files:**
- Modify: `modules/wedge100s_cpld.c`

- [ ] **Step 1: Add new register defines**

After `REG_PSU_STATUS` (line 43), add:

```c
#define REG_BOARD_REV       0x00  /* D[3:0]=BRD_REV, D[5:4]=MODEL_ID */
#define REG_PWR_STATUS1     0x11  /* D[0]=PWR_STBY_OK */
#define REG_PWR_STATUS2     0x12  /* D[0]=VCORE_VRDY, D[1]=VCORE_HOT, D[2]=VANLOG_VRDY,
                                   * D[3]=VANLOG_HOT, D[4]=V3V3_VRDY, D[5]=V3V3_HOT */
```

- [ ] **Step 2: Add show functions**

```c
/** @brief Show board revision (4-bit BRD_REV from reg 0x00 bits [3:0]). */
static ssize_t show_board_rev(struct device *dev,
                               struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_BOARD_REV);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n", val & 0x0f);
}

/** @brief Show model ID (2-bit MODEL_ID from reg 0x00 bits [5:4]). 0=wedge100 TOR. */
static ssize_t show_model_id(struct device *dev,
                              struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_BOARD_REV);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n", (val >> 4) & 0x03);
}

/** @brief Show standby power OK (1=OK). Bit 0 of reg 0x11. */
static ssize_t show_pwr_stby_ok(struct device *dev,
                                 struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_PWR_STATUS1);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "%d\n", val & 1);
}

/** @brief Show power status 2 register as hex (reg 0x12).
 *
 *  Bit 0: VCORE_VRDY (1=OK), Bit 1: VCORE_HOT (1=over-temp active),
 *  Bit 2: VANLOG_VRDY (1=OK), Bit 3: VANLOG_HOT (1=over-temp active),
 *  Bit 4: V3V3_VRDY (1=OK), Bit 5: V3V3_HOT (1=over-temp active).
 */
static ssize_t show_pwr_status2(struct device *dev,
                                 struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_PWR_STATUS2);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val);
}
```

- [ ] **Step 3: Add DEVICE_ATTR entries and register**

```c
static DEVICE_ATTR(board_rev,    S_IRUGO, show_board_rev,    NULL);
static DEVICE_ATTR(model_id,     S_IRUGO, show_model_id,     NULL);
static DEVICE_ATTR(pwr_stby_ok,  S_IRUGO, show_pwr_stby_ok,  NULL);
static DEVICE_ATTR(pwr_status2,  S_IRUGO, show_pwr_status2,  NULL);
```

Add to `wedge100s_cpld_attrs[]` before NULL:

```c
    &dev_attr_board_rev.attr,
    &dev_attr_model_id.attr,
    &dev_attr_pwr_stby_ok.attr,
    &dev_attr_pwr_status2.attr,
```

- [ ] **Step 4: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 5: Commit**

```bash
git add modules/wedge100s_cpld.c
git commit -m "feat(platform): expose board revision and power rail health sysfs

Add 4 new read-only sysfs attributes:
  board_rev   — PCB revision from reg 0x00 bits [3:0]
  model_id    — model identifier from reg 0x00 bits [5:4] (0=wedge100 TOR)
  pwr_stby_ok — standby power OK from reg 0x11 bit 0
  pwr_status2 — power rail health byte from reg 0x12 (VCORE/VANLOG/V3V3 VRDY+HOT)

Closes: GAP-012, GAP-030"
```

---

### Task 3: Add reset reason and ROV sysfs attributes

**Gaps:** GAP-010, GAP-020
**Files:**
- Modify: `modules/wedge100s_cpld.c`

- [ ] **Step 1: Add register defines**

```c
#define REG_ROV_STATUS      0x0b  /* D[3:0]=TH_ROV, D[6:4]=VCORE_IDSEL */
#define REG_RESET_REASON    0x0d  /* Reset reason code (8-bit) */
#define REG_RESET_SOURCE1   0x0e  /* Per-source reset active bits */
#define REG_RESET_SOURCE2   0x0f  /* BMC-initiated reset active bits */
```

- [ ] **Step 2: Add show functions**

```c
/** @brief Show Tomahawk ROV voltage code (reg 0x0B bits [3:0]).
 *
 *  Decode: 0000=1.200V, 0001=1.175V, ..., 1111=0.825V (25mV steps).
 *  Returns the raw 4-bit code; user-space decodes to voltage.
 */
static ssize_t show_rov_status(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_ROV_STATUS);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val);
}

/** @brief Show reset reason code (reg 0x0D, 8-bit).
 *
 *  0x00=unknown, 0x01=standby reset, 0x02=main reset,
 *  0x03=front panel button, 0x10-0x13=SW reset, 0x20-0x26=BMC reset.
 */
static ssize_t show_reset_reason(struct device *dev,
                                  struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_RESET_REASON);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val);
}

/** @brief Show reset source 1 register (reg 0x0E) — per-source active bits. */
static ssize_t show_reset_source1(struct device *dev,
                                   struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_RESET_SOURCE1);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val);
}

/** @brief Show reset source 2 register (reg 0x0F) — BMC-initiated reset bits. */
static ssize_t show_reset_source2(struct device *dev,
                                   struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_RESET_SOURCE2);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val);
}
```

- [ ] **Step 3: Add DEVICE_ATTRs and register**

```c
static DEVICE_ATTR(rov_status,     S_IRUGO, show_rov_status,     NULL);
static DEVICE_ATTR(reset_reason,   S_IRUGO, show_reset_reason,   NULL);
static DEVICE_ATTR(reset_source1,  S_IRUGO, show_reset_source1,  NULL);
static DEVICE_ATTR(reset_source2,  S_IRUGO, show_reset_source2,  NULL);
```

Add to `wedge100s_cpld_attrs[]` before NULL:

```c
    &dev_attr_rov_status.attr,
    &dev_attr_reset_reason.attr,
    &dev_attr_reset_source1.attr,
    &dev_attr_reset_source2.attr,
```

- [ ] **Step 4: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 5: Commit**

```bash
git add modules/wedge100s_cpld.c
git commit -m "feat(platform): expose reset reason, reset source, and ROV sysfs

Add 4 new read-only sysfs attributes:
  rov_status    — Tomahawk ROV voltage + VCORE_IDSEL from reg 0x0B
  reset_reason  — last reset reason code from reg 0x0D
  reset_source1 — per-source reset active bits from reg 0x0E
  reset_source2 — BMC-initiated reset active bits from reg 0x0F

Closes: GAP-010, GAP-020"
```

---

### Task 4: Add COM-e status sysfs attribute

**Gap:** GAP-025
**Files:**
- Modify: `modules/wedge100s_cpld.c`

- [ ] **Step 1: Add register define**

```c
#define REG_COME_STATUS     0x18  /* D[2:0]=COM type, D[3]=GbE link, D[4:7]=suspend states */
```

- [ ] **Step 2: Add show function**

```c
/** @brief Show COM-e status register (reg 0x18) as hex.
 *
 *  D[2:0]: B_COM_TYPE (board type), D[3]: COM_GBE0_LINK1000_N (1=no link),
 *  D[4]: COM_SUS_STAT_N, D[5-7]: COM_SUS_S3/S4/S5_N.
 */
static ssize_t show_come_status(struct device *dev,
                                 struct device_attribute *attr, char *buf)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct wedge100s_cpld_data *data = i2c_get_clientdata(client);
    int val;

    mutex_lock(&data->update_lock);
    val = cpld_read(client, REG_COME_STATUS);
    mutex_unlock(&data->update_lock);

    if (val < 0)
        return val;
    return scnprintf(buf, PAGE_SIZE, "0x%02x\n", val);
}
```

- [ ] **Step 3: Add DEVICE_ATTR and register**

```c
static DEVICE_ATTR(come_status, S_IRUGO, show_come_status, NULL);
```

Add to `wedge100s_cpld_attrs[]` before NULL:

```c
    &dev_attr_come_status.attr,
```

- [ ] **Step 4: Build verify and commit**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
git add modules/wedge100s_cpld.c
git commit -m "feat(platform): expose COM-e status register sysfs attribute

Add come_status read-only sysfs attribute from reg 0x18.
Reports COM-e board type, GbE link, and suspend states.

Closes: GAP-025"
```

---

### Task 5: Extend i2c-daemon to mirror new CPLD attributes

**Files:**
- Modify: `utils/wedge100s-i2c-daemon.c`

- [ ] **Step 1: Add new attributes to poll_cpld()**

In `poll_cpld()` (around line 1142), the daemon mirrors PSU attrs from CPLD sysfs to `/run/wedge100s/`. Extend the `psu_attrs[]` array and add a new static-attrs block. Replace the existing `poll_cpld()` function:

```c
static void poll_cpld(void)
{
    /* cpld_version: static hardware info — read once at first tick only. */
    {
        char dst[128];
        struct stat st;
        snprintf(dst, sizeof(dst), RUN_DIR "/cpld_version");
        if (stat(dst, &st) != 0) {
            char src[128], val[64];
            snprintf(src, sizeof(src), CPLD_SYSFS "/cpld_version");
            FILE *f = fopen(src, "r");
            if (f) {
                if (fgets(val, (int)sizeof(val), f)) {
                    int n = (int)strlen(val);
                    while (n > 0 && (val[n-1]=='\n'||val[n-1]=='\r'||val[n-1]==' '))
                        val[--n] = '\0';
                    write_str_file(dst, val);
                }
                fclose(f);
            }
        }
    }

    /* Static attrs: read once at first tick (hardware constants). */
    static const char *static_attrs[] = {
        "board_rev", "model_id", "come_status", NULL
    };
    for (int i = 0; static_attrs[i]; i++) {
        char dst[128];
        struct stat st;
        snprintf(dst, sizeof(dst), RUN_DIR "/%s", static_attrs[i]);
        if (stat(dst, &st) != 0) {
            char src[128], val[64];
            snprintf(src, sizeof(src), CPLD_SYSFS "/%s", static_attrs[i]);
            FILE *f = fopen(src, "r");
            if (f) {
                if (fgets(val, (int)sizeof(val), f)) {
                    int n = (int)strlen(val);
                    while (n > 0 && (val[n-1]=='\n'||val[n-1]=='\r'||val[n-1]==' '))
                        val[--n] = '\0';
                    write_str_file(dst, val);
                }
                fclose(f);
            }
        }
    }

    /* Dynamic attrs: read every tick. */
    static const char *dynamic_attrs[] = {
        "psu1_present", "psu1_pgood", "psu1_alarm", "psu1_input_ok",
        "psu2_present", "psu2_pgood", "psu2_alarm", "psu2_input_ok",
        "pwr_stby_ok", "pwr_status2",
        "rov_status", "reset_reason", "reset_source1", "reset_source2",
        NULL
    };
    for (int i = 0; dynamic_attrs[i]; i++) {
        char src[128], dst[128], val[64];
        snprintf(src, sizeof(src), CPLD_SYSFS "/%s", dynamic_attrs[i]);
        snprintf(dst, sizeof(dst), RUN_DIR   "/%s", dynamic_attrs[i]);
        FILE *f = fopen(src, "r");
        if (!f) continue;
        if (fgets(val, (int)sizeof(val), f)) {
            int n = (int)strlen(val);
            while (n > 0 && (val[n-1]=='\n'||val[n-1]=='\r'||val[n-1]==' '))
                val[--n] = '\0';
            write_str_file(dst, val);
        }
        fclose(f);
    }
}
```

- [ ] **Step 2: Build verify**

```bash
cd /export/sonic/sonic-buildimage
BLDENV=trixie make target/debs/trixie/sonic-platform-accton-wedge100s-32x_1.1_amd64.deb
```

- [ ] **Step 3: Commit**

```bash
git add utils/wedge100s-i2c-daemon.c
git commit -m "feat(i2c-daemon): mirror new CPLD sysfs attrs to /run/wedge100s/

Extend poll_cpld() to mirror 13 new CPLD attributes:
  Static (read once): board_rev, model_id, come_status
  Dynamic (every tick): psu{1,2}_{alarm,input_ok}, pwr_stby_ok,
    pwr_status2, rov_status, reset_reason, reset_source{1,2}"
```

---

### Task 6: Wire PSU alarm and input-OK into Python platform API

**Gap:** GAP-013, GAP-014
**Files:**
- Modify: `sonic_platform/psu.py`

- [ ] **Step 1: Add cache path constants**

Near the existing `/run/wedge100s/psu` path definitions in `psu.py`, add:

```python
_PSU_ALARM_CACHE    = '/run/wedge100s/psu{}_alarm'
_PSU_INPUT_OK_CACHE = '/run/wedge100s/psu{}_input_ok'
```

- [ ] **Step 2: Add alarm and input-OK methods to Psu class**

```python
    def get_psu_alarm(self):
        """Return True if PSU has an active alarm condition.

        Returns:
            bool: True if alarm active (abnormal), False if normal.
        """
        path = _PSU_ALARM_CACHE.format(self._index)
        try:
            with open(path) as f:
                # CPLD: 1=normal, 0=alarm — invert for "has alarm" semantics
                return f.read().strip() == '0'
        except OSError:
            return False

    def get_input_status(self):
        """Return True if PSU input power is OK.

        Returns:
            bool: True if input power is within acceptable range.
        """
        path = _PSU_INPUT_OK_CACHE.format(self._index)
        try:
            with open(path) as f:
                return f.read().strip() == '1'
        except OSError:
            return False
```

- [ ] **Step 3: Commit**

```bash
git add sonic_platform/psu.py
git commit -m "feat(platform): add PSU alarm and input-OK to Python API

Wire psu{1,2}_alarm and psu{1,2}_input_ok daemon cache files into
Psu.get_psu_alarm() and Psu.get_input_status() methods.

Closes: GAP-013, GAP-014 (Python API wiring)"
```

---

### Task 7: Wire reset reason into chassis platform API

**Gap:** GAP-010
**Files:**
- Modify: `sonic_platform/chassis.py`

- [ ] **Step 1: Add CPLD reset-reason decode to get_reboot_cause()**

In `chassis.py`, update `get_reboot_cause()` to read the CPLD reset reason register as a secondary source. Locate the existing `get_reboot_cause()` method and add CPLD register parsing:

```python
    # CPLD reset-reason code → SONiC (category, description) mapping.
    # OCP spec v1.3 section 7.7.7, register 0x0D.
    _CPLD_RESET_MAP = {
        0x00: (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, "Unknown (CPLD default)"),
        0x01: (ChassisBase.REBOOT_CAUSE_POWER_LOSS, "Standby power domain reset"),
        0x02: (ChassisBase.REBOOT_CAUSE_POWER_LOSS, "Main power domain reset"),
        0x03: (ChassisBase.REBOOT_CAUSE_HARDWARE_BUTTON, "Front panel push button"),
        0x04: (ChassisBase.REBOOT_CAUSE_HARDWARE_BUTTON, "On-board debug push button"),
        0x05: (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, "Facebook debug header reset"),
        0x10: (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, "Software hot reset"),
        0x11: (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, "Software warm reset"),
        0x12: (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, "Software cold reset"),
        0x13: (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, "Software power reset"),
        0x20: (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, "BMC request reset (BMC only)"),
        0x21: (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, "BMC request Tomahawk reset"),
        0x22: (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, "BMC request COM-e reset"),
        0x23: (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, "BMC request main power reset"),
        0x24: (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, "BMC request full board reset"),
        0x25: (ChassisBase.REBOOT_CAUSE_WATCHDOG, "BMC watchdog timer-1 reset"),
        0x26: (ChassisBase.REBOOT_CAUSE_WATCHDOG, "BMC watchdog timer-2 reset"),
    }

    def get_reboot_cause(self):
        """Return the most recent reboot cause from CPLD register 0x0D.

        Falls back to the SONiC reboot-cause file if CPLD data is unavailable.

        Returns:
            tuple: (REBOOT_CAUSE_xxx, description_string)
        """
        # Try CPLD hardware register first (most authoritative).
        cpld_path = '/run/wedge100s/reset_reason'
        try:
            with open(cpld_path) as f:
                code = int(f.read().strip(), 0)
            if code in self._CPLD_RESET_MAP:
                return self._CPLD_RESET_MAP[code]
            return (self.REBOOT_CAUSE_HARDWARE_OTHER,
                    "CPLD reset code 0x{:02x}".format(code))
        except (OSError, ValueError):
            pass

        # Fallback: SONiC reboot-cause file.
        try:
            with open('/var/log/sonic/reboot-cause/previous-reboot-cause.txt') as f:
                cause = f.read().strip()
            if cause:
                return (self.REBOOT_CAUSE_NON_HARDWARE, cause)
        except OSError:
            pass

        return (self.REBOOT_CAUSE_NON_HARDWARE, "Unknown")
```

- [ ] **Step 2: Remove old get_reboot_cause() if it exists**

Check if there's an existing `get_reboot_cause()` in the file and replace it entirely with the version above.

- [ ] **Step 3: Commit**

```bash
git add sonic_platform/chassis.py
git commit -m "feat(platform): wire CPLD reset-reason register into get_reboot_cause()

Read /run/wedge100s/reset_reason (CPLD reg 0x0D) to report hardware
reboot cause. Maps OCP spec v1.3 section 7.7.7 codes to SONiC
REBOOT_CAUSE_xxx categories. Falls back to reboot-cause file.

Closes: GAP-010 (Python API wiring)"
```

---

### Task 8: Write hardware tests for new CPLD attributes

**Files:**
- Modify: `tests/stage_09_cpld/test_cpld.py` (in devel repo)

- [ ] **Step 1: Add new attributes to the test list**

Update `SYSFS_ATTRS` at the top of `test_cpld.py`:

```python
SYSFS_ATTRS = [
    "cpld_version",
    "psu1_present",
    "psu1_pgood",
    "psu1_alarm",
    "psu1_input_ok",
    "psu2_present",
    "psu2_pgood",
    "psu2_alarm",
    "psu2_input_ok",
    "led_sys1",
    "led_sys2",
    "board_rev",
    "model_id",
    "pwr_stby_ok",
    "pwr_status2",
    "rov_status",
    "reset_reason",
    "reset_source1",
    "reset_source2",
    "come_status",
]
```

- [ ] **Step 2: Add specific validation tests**

Append to `test_cpld.py`:

```python
# ------------------------------------------------------------------
# New CPLD attributes (GAP-010, 012, 013, 014, 020, 025, 030)
# ------------------------------------------------------------------

def test_psu_alarm_valid(ssh):
    """psu{1,2}_alarm are 0 (alarm) or 1 (normal)."""
    for n in (1, 2):
        val = _read_int_attr(ssh, f"psu{n}_alarm")
        print(f"  psu{n}_alarm: {val}")
        assert val in (0, 1), f"psu{n}_alarm={val}, expected 0 or 1"


def test_psu_input_ok_valid(ssh):
    """psu{1,2}_input_ok are 0 (bad) or 1 (OK)."""
    for n in (1, 2):
        val = _read_int_attr(ssh, f"psu{n}_input_ok")
        print(f"  psu{n}_input_ok: {val}")
        assert val in (0, 1), f"psu{n}_input_ok={val}, expected 0 or 1"


def test_psu_present_implies_input_ok(ssh):
    """A present and powered PSU should have input_ok=1 under normal conditions."""
    for n in (1, 2):
        present  = _read_int_attr(ssh, f"psu{n}_present")
        pgood    = _read_int_attr(ssh, f"psu{n}_pgood")
        input_ok = _read_int_attr(ssh, f"psu{n}_input_ok")
        alarm    = _read_int_attr(ssh, f"psu{n}_alarm")
        print(f"  PSU{n}: present={present} pgood={pgood} input_ok={input_ok} alarm={alarm}")
        if present == 1 and pgood == 1:
            assert input_ok == 1, (
                f"PSU{n}: present and pgood but input_ok=0 — check AC power"
            )
            assert alarm == 1, (
                f"PSU{n}: present and pgood but alarm active — check PSU health"
            )


def test_board_rev_range(ssh):
    """board_rev is a 4-bit value (0-15)."""
    val = _read_int_attr(ssh, "board_rev")
    print(f"\nboard_rev: {val}")
    assert 0 <= val <= 15, f"board_rev={val} out of range [0, 15]"


def test_model_id_is_wedge100(ssh):
    """model_id should be 0 for wedge100 TOR platform."""
    val = _read_int_attr(ssh, "model_id")
    print(f"\nmodel_id: {val}")
    assert val == 0, (
        f"model_id={val}, expected 0 (wedge100 TOR). "
        "1=6-pack line card, 2=6-pack fabric card."
    )


def test_pwr_stby_ok(ssh):
    """Standby power must be OK in a running system."""
    val = _read_int_attr(ssh, "pwr_stby_ok")
    print(f"\npwr_stby_ok: {val}")
    assert val == 1, "pwr_stby_ok=0 — standby power domain not OK"


def test_pwr_status2_healthy(ssh):
    """Power status 2: all VRDY bits set, no HOT bits set in normal operation."""
    val = _read_int_attr(ssh, "pwr_status2")
    print(f"\npwr_status2: 0x{val:02x}")
    vcore_vrdy  = (val >> 0) & 1
    vcore_hot   = (val >> 1) & 1
    vanlog_vrdy = (val >> 2) & 1
    vanlog_hot  = (val >> 3) & 1
    v3v3_vrdy   = (val >> 4) & 1
    v3v3_hot    = (val >> 5) & 1
    print(f"  VCORE: vrdy={vcore_vrdy} hot={vcore_hot}")
    print(f"  VANLOG: vrdy={vanlog_vrdy} hot={vanlog_hot}")
    print(f"  V3V3: vrdy={v3v3_vrdy} hot={v3v3_hot}")
    assert vcore_vrdy == 1, "VCORE_VRDY=0 — Tomahawk core voltage not ready"
    assert vanlog_vrdy == 1, "VANLOG_VRDY=0 — Tomahawk analog voltage not ready"
    assert v3v3_vrdy == 1, "V3V3_VRDY=0 — 3.3V rail not ready"
    assert vcore_hot == 0, "VCORE_HOT=1 — Tomahawk core VRM over-temperature!"
    assert vanlog_hot == 0, "VANLOG_HOT=1 — Tomahawk analog VRM over-temperature!"
    assert v3v3_hot == 0, "V3V3_HOT=1 — 3.3V VRM over-temperature!"


def test_reset_reason_valid(ssh):
    """reset_reason is a recognized OCP spec code."""
    val = _read_int_attr(ssh, "reset_reason")
    print(f"\nreset_reason: 0x{val:02x}")
    known_codes = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05,
                   0x10, 0x11, 0x12, 0x13,
                   0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26}
    assert val in known_codes, (
        f"reset_reason=0x{val:02x} is not a known OCP spec reset code"
    )


def test_rov_voltage_sane(ssh):
    """ROV status should indicate a reasonable Tomahawk core voltage."""
    val = _read_int_attr(ssh, "rov_status")
    th_rov = val & 0x0f
    vcore_idsel = (val >> 4) & 0x07
    # ROV code 0=1.200V, 15=0.825V; typical is 4-8 (1.100V-0.975V)
    voltage = 1.200 - (th_rov * 0.025)
    print(f"\nrov_status: 0x{val:02x} → TH_ROV={th_rov} ({voltage:.3f}V), VCORE_IDSEL={vcore_idsel}")
    assert 0.825 <= voltage <= 1.200, f"ROV voltage {voltage}V out of expected range"
```

- [ ] **Step 3: Run tests on hardware**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_09_cpld/ -v
```

Expected: All new tests pass (after deploying the updated .deb to the target).

- [ ] **Step 4: Commit**

```bash
git add tests/stage_09_cpld/test_cpld.py
git commit -m "test(cpld): add tests for new CPLD sysfs attributes

Cover GAP-010 (reset reason), GAP-012 (power rail health),
GAP-013/014 (PSU alarm/input), GAP-020 (ROV), GAP-025 (COM-e),
GAP-030 (board rev). Validates register values, cross-checks
PSU state consistency, and decodes power rail health bits."
```

---

### Task 9: Hardware verification of PSU register 0x10 polarity

**Gap:** GAP-002
**Files:**
- Create: `tests/stage_06_psu/test_psu_register_polarity.py` (in devel repo)

- [ ] **Step 1: Write polarity verification test**

This test reads all 8 bits of register 0x10 and cross-checks against physical PSU state:

```python
"""Stage 06 supplement — Verify PSU CPLD register 0x10 bit polarity.

GAP-002: OCP spec v1.3 section 7.7.2 defines 8 bits in register 0x10.
This test reads all 8 bits and validates polarity against known PSU state.

Requires: Both PSUs physically installed and powered.
"""

import pytest

RUN_DIR = "/run/wedge100s"


def _read_int(ssh, attr):
    out, _, rc = ssh.run(f"cat {RUN_DIR}/{attr}", timeout=10)
    assert rc == 0, f"Could not read {RUN_DIR}/{attr}"
    return int(out.strip(), 0)


def test_register_0x10_all_bits(ssh):
    """Read all 8 PSU status bits and print comprehensive report.

    With both PSUs installed and powered, expected values:
      psu1_present=1, psu1_pgood=1, psu1_input_ok=1, psu1_alarm=1 (normal)
      psu2_present=1, psu2_pgood=1, psu2_input_ok=1, psu2_alarm=1 (normal)
    """
    bits = {}
    for attr in ('psu1_present', 'psu1_pgood', 'psu1_input_ok', 'psu1_alarm',
                 'psu2_present', 'psu2_pgood', 'psu2_input_ok', 'psu2_alarm'):
        bits[attr] = _read_int(ssh, attr)
        print(f"  {attr}: {bits[attr]}")

    # Cross-check: if present and pgood, input_ok and alarm should be normal
    for n in (1, 2):
        if bits[f'psu{n}_present'] == 1 and bits[f'psu{n}_pgood'] == 1:
            assert bits[f'psu{n}_input_ok'] == 1, (
                f"PSU{n}: present+pgood but input_ok=0 — "
                "polarity may be inverted (OCP spec: 0=bad, 1=OK)"
            )
            assert bits[f'psu{n}_alarm'] == 1, (
                f"PSU{n}: present+pgood but alarm=0 — "
                "polarity may be inverted (OCP spec: 0=alarm, 1=normal)"
            )
```

- [ ] **Step 2: Run on hardware**

```bash
cd /export/sonic/sonic-wedge100s-devel
pytest tests/stage_06_psu/test_psu_register_polarity.py -v
```

Expected: PASS with all 8 bits showing expected values for two installed, powered PSUs.

- [ ] **Step 3: Commit**

```bash
git add tests/stage_06_psu/test_psu_register_polarity.py
git commit -m "test(psu): verify register 0x10 all-8-bit polarity on hardware

GAP-002: Cross-checks psu{1,2}_{present,pgood,input_ok,alarm} against
expected physical state with both PSUs installed and powered."
```
