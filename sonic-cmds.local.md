# SONiC Command Reference — Wedge 100S-32X Test Suite

All commands executed against the SONiC switch target via SSH in `tests/`.
Variables shown as `[NAME]`; example values shown where helpful.

---

## show — Platform

```bash
show version
show platform summary
show platform syseeprom
show platform temperature
show platform fan
show platform psustatus
show environment
show reboot-cause
```

## show — Interfaces

```bash
show interfaces status
show interfaces status [PORT]               # e.g. Ethernet0
show ip interfaces
show interfaces transceiver presence
show interfaces transceiver eeprom [PORT]
show interfaces counters
show interfaces portchannel
show interfaces autoneg status
show interfaces autoneg status [PORT]
show interfaces breakout
show lldp neighbors
counterpoll show
portstat -j
portstat -c
sonic-clear counters
```

## config — Interface

```bash
config interface speed [PORT] [SPEED]       # e.g. 100000
config interface fec [PORT] [rs|none|fc]
config interface autoneg [PORT] [enabled|disabled]
config interface advertised-speeds [PORT] [SPEEDS]
config interface advertised-types [PORT] [TYPE]
config interface ip add [IFACE] [IP/MASK]
config interface ip remove [IFACE] [IP/MASK]
config interface breakout [PORT] '[MODE]' -y -f
config interface breakout [PORT] '[MODE]' -y -f -l
config interface shutdown [PORT]
config interface startup [PORT]
```

## config — PortChannel / LAG

```bash
config portchannel add [NAME]               # e.g. PortChannel1
config portchannel del [NAME]
config portchannel member add [LAG] [PORT]
config portchannel member del [LAG] [PORT]
```

## config — General

```bash
config save [PATH] -y
config reload [CONFIG_FILE] -y
config feature state [FEATURE] [enabled|disabled]
```

## redis-cli — CONFIG_DB (db 4)

```bash
redis-cli -n 4 hget 'PORT|[PORT]' [FIELD]
redis-cli -n 4 hset 'PORT|[PORT]' [FIELD] [VALUE]
redis-cli -n 4 hdel 'PORT|[PORT]' [FIELD1] [FIELD2]
redis-cli -n 4 hgetall 'PORTCHANNEL|[LAG]'
redis-cli -n 4 exists 'PORTCHANNEL|[LAG]'
redis-cli -n 4 exists 'PORTCHANNEL_MEMBER|[LAG]|[PORT]'
redis-cli -n 4 keys 'PORTCHANNEL_INTERFACE|[LAG]|*'
redis-cli -n 4 keys 'BREAKOUT_CFG|*'
redis-cli -n 4 hget 'BREAKOUT_CFG|[PORT]' brkout_mode
redis-cli -n 4 del 'INTERFACE|[PORT]'
redis-cli -n 4 hset 'INTERFACE|[PORT]' NULL NULL
redis-cli -n 4 hget 'FEATURE|[FEATURE]' state
```

## redis-cli — APP_DB (db 0)

```bash
redis-cli -n 0 hget 'PORT_TABLE:[PORT]' [FIELD]
redis-cli -n 0 hget 'LAG_TABLE:[LAG]' oper_status
redis-cli -n 0 hget 'LAG_MEMBER_TABLE:[LAG]:[PORT]' status
```

## redis-cli — COUNTERS_DB (db 2)

```bash
redis-cli -n 2 hgetall COUNTERS_PORT_NAME_MAP
redis-cli -n 2 hget COUNTERS_PORT_NAME_MAP [PORT]
redis-cli -n 2 hget 'COUNTERS:[OID]' [STAT]
redis-cli -n 2 hgetall 'COUNTERS:[OID]'
redis-cli -n 2 hkeys 'COUNTERS:[OID]'
redis-cli -n 2 hget COUNTERS_LAG_NAME_MAP [LAG]
```

## redis-cli — STATE_DB (db 6)

```bash
redis-cli -n 6 hgetall 'LAG_TABLE|[LAG]'
redis-cli -n 6 hget 'PORT_TABLE|[PORT]' [FIELD]
redis-cli -n 6 hgetall 'PROCESS_STATS|pmon'
redis-cli -n 6 hgetall 'TRANSCEIVER_INFO|[PORT]'
redis-cli -n 6 hgetall 'TRANSCEIVER_DOM_SENSOR|[PORT]'
redis-cli -n 6 hgetall 'TRANSCEIVER_STATUS|[PORT]'
```

## redis-cli — ASIC_DB (db 1)

```bash
redis-cli -n 1 exists 'ASIC_STATE:SAI_OBJECT_TYPE_LAG:[OID]'
redis-cli -n 1 keys 'ASIC_STATE:SAI_OBJECT_TYPE_LAG_MEMBER:*'
redis-cli -n 1 hget 'ASIC_STATE:SAI_OBJECT_TYPE_PORT:[OID]' [ATTR]
```

## docker

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
docker ps --format '{{.Names}}' --filter name=[NAME]
docker images --format '{{.Repository}}\t{{.Tag}}\t{{.Size}}'
docker exec [CONTAINER] [COMMAND]
docker exec pmon ls -la /dev/ttyACM0
docker exec pmon supervisorctl status ledd
```

## systemctl

```bash
systemctl is-active [SERVICE]
systemctl is-failed [SERVICE]
systemctl show [SERVICE] --property=[PROP] --value
systemctl status [SERVICE]
sudo systemctl start [SERVICE]
sudo systemctl stop [SERVICE]
sudo systemctl restart [SERVICE]
```

## i2c

```bash
i2cdetect -l
i2cdetect -y [BUS]
i2cget -y [BUS] 0x[ADDR] [REG]
```

## Utilities

```bash
decode-syseeprom
watchdogutil status
sonic-cfggen -d --var-json [TABLE]
teamdctl [LAG] state
ping -c [COUNT] -W [TIMEOUT] [HOST]
ping -f -c [COUNT] [HOST] -W [TIMEOUT]
journalctl -u [SERVICE] -n [LINES]
```

## Filesystem & Kernel

```bash
uname -n
uname -r
uname -a
uname -m
lsmod | grep [MODULE]
ls [PATH]
ls -la [PATH]
cat [FILE]
wc -c < [FILE]
hexdump -n [BYTES] -e '1/1 "[FORMAT]' [FILE]
echo [TEXT] | sudo tee [FILE] > /dev/null
readlink [SYMLINK] | xargs basename
test -f [FILE] && echo EXISTS || echo MISSING
test -d [DIR] && echo YES || echo NO
find [PATH] -name [PATTERN] -type [TYPE]
```

## sonic_platform Python API

Executed as root via `ssh.run_python()`. Standard preamble:

```python
from sonic_platform.platform import Platform
chassis = Platform().get_chassis()
```

### EEPROM / Chassis

```python
chassis.get_system_eeprom_info()
chassis.get_name()
chassis.get_base_mac()
```

### Thermal

```python
thermals = chassis.get_all_thermals()
t.get_name(); t.get_temperature(); t.get_high_threshold()
t.get_high_critical_threshold(); t.get_status(); t.get_position_in_parent()
```

### Fan

```python
drawers = chassis.get_all_fan_drawers()
fans = drawer.get_all_fans()
f.get_name(); f.get_presence(); f.get_status()
f.get_speed(); f.get_speed_rpm(); f.get_direction(); f.get_position_in_parent()
```

### PSU

```python
psus = chassis.get_all_psus()
p.get_name(); p.get_presence(); p.get_status(); p.get_powergood_status()
p.get_type(); p.get_capacity()
p.get_voltage(); p.get_current(); p.get_power()
p.get_input_voltage(); p.get_input_current(); p.get_position_in_parent()
```

### SFP / QSFP (ports 1–32)

```python
sfp = chassis.get_sfp(INDEX)
sfp.get_name(); sfp.get_presence(); sfp.get_eeprom_path()
sfp.get_error_description(); sfp.get_position_in_parent()
sfp.get_xcvr_api().get_transceiver_info()
chassis.get_port_or_cage_type(INDEX)    # expects SfpBase.SFP_PORT_TYPE_BIT_QSFP28
```

### Components (firmware)

```python
comps = chassis.get_all_components()
c.get_name(); c.get_firmware_version()
```

### BMC

```python
from sonic_platform import bmc
bmc.send_command(CMD)
bmc.file_read_int(PATH)
```

---

## Key Files Read During Tests

| Path | Purpose |
|------|---------|
| `/run/wedge100s/syseeprom` | System EEPROM cache |
| `/run/wedge100s/sfp_N_present` | QSFP presence (0/1) |
| `/run/wedge100s/sfp_N_eeprom` | QSFP EEPROM page 0 |
| `/run/wedge100s/thermal_N` | Temperature (millidegrees C) |
| `/run/wedge100s/fan_present` | Fan presence bitmask |
| `/run/wedge100s/fan_N_front` | Front rotor RPM |
| `/run/wedge100s/fan_N_rear` | Rear rotor RPM |
| `/run/wedge100s/psu_N_vin` | PSU input voltage (LINEAR11) |
| `/run/wedge100s/psu_N_iin` | PSU input current |
| `/run/wedge100s/psu_N_iout` | PSU output current |
| `/run/wedge100s/psu_N_pout` | PSU output power |
| `/sys/bus/i2c/devices/1-0032/cpld_version` | CPLD version |
| `/sys/bus/i2c/devices/1-0032/psu1_present` | PSU 1 present |
| `/sys/bus/i2c/devices/1-0032/psu1_pgood` | PSU 1 power good |
| `/sys/bus/i2c/devices/1-0032/psu2_present` | PSU 2 present |
| `/sys/bus/i2c/devices/1-0032/psu2_pgood` | PSU 2 power good |
| `/sys/bus/i2c/devices/1-0032/led_sys1` | System LED 1 |
| `/sys/bus/i2c/devices/1-0032/led_sys2` | System LED 2 |
| `/sys/class/thermal/thermal_zone*/temp` | Kernel thermal zones |
| `/sys/class/hwmon/hwmon*/temp*_input` | hwmon temperature inputs |
| `/etc/sonic/sonic_version.yml` | SONiC version metadata |
| `/etc/sonic/clean_boot.json` | Clean-boot state flag |
| `/etc/sonic/pre_test_config.json` | Pre-test config snapshot |
| `/usr/share/sonic/device/x86_64-accton_wedge100s_32x-r0/platform.json` | Platform port map |
| `/usr/share/sonic/device/x86_64-accton_wedge100s_32x-r0/Accton-WEDGE100S-32X/hwsku.json` | HW SKU definition |
