"""DefaultsCleanupTask — wipe SONiC's LeafRouter L3-fabric defaults.

SONiC's first-boot `sonic-cfggen` falls back to DEVICE_METADATA.type=LeafRouter
when no minigraph.xml is present and auto-allocates sequential /31 P2P
addresses on every port in hwsku.json (the canonical T1-leaf BGP-peer-per-link
layout).  Our deploy.py builds an L2 topology (VLANs, PortChannels, no router
interfaces), so every fresh install lands with CONFIG_DB state that actively
conflicts with what downstream tasks want to configure.

Historically we caught this lazily — `vlans.py`'s _strip_router_interface()
cleans up ports as they're added to VLANs.  This task runs FIRST so every
subsequent task sees a clean slate:

  - DEVICE_METADATA.localhost.type  -> ToRRouter  (L2 TOR; suppresses auto-L3)
  - INTERFACE|Ethernet*             -> deleted    (both bare + |<ip>/<prefix>)
  - DEVICE_NEIGHBOR|*               -> deleted    (BGP peer hints)
  - DEVICE_NEIGHBOR_METADATA|*      -> deleted
  - BGP_NEIGHBOR|*                  -> deleted
  - BGP_PEER_RANGE|*                -> deleted
  - bgp.service                     -> masked     (no BGP on L2 ToR)

Direct CONFIG_DB redis DEL is used rather than `config interface ip remove`
because the CLI requires the bgp container to be running and we're about to
mask bgp.service — the CLI would fail mid-cleanup.  orchagent sees CONFIG_DB
deletes via its normal notification path and properly tears down L3 state.
"""
from .base import Change, ConfigTask


L3_TABLES = [
    "INTERFACE",
    "DEVICE_NEIGHBOR",
    "DEVICE_NEIGHBOR_METADATA",
    "BGP_NEIGHBOR",
    "BGP_PEER_RANGE",
    "BGP_MONITORS",
]

DESIRED_TYPE = "ToRRouter"


class DefaultsCleanupTask(ConfigTask):

    def _redis_keys(self, pattern: str) -> list:
        out, _, _ = self.ssh.run(
            f"redis-cli -n 4 --scan --pattern '{pattern}'", timeout=15
        )
        return [k for k in out.split() if k]

    def _current_device_type(self) -> str:
        out, _, _ = self.ssh.run(
            "redis-cli -n 4 hget 'DEVICE_METADATA|localhost' type",
            timeout=10,
        )
        return out.strip()

    def _bgp_is_masked(self) -> bool:
        out, _, _ = self.ssh.run(
            "systemctl is-enabled bgp.service 2>&1 || true", timeout=10
        )
        # 'masked' on stdout when masked; otherwise 'enabled'/'disabled'/'alias'
        return "masked" in out.lower()

    def check(self) -> list:
        changes = []

        # 1. DEVICE_METADATA.localhost.type
        cur_type = self._current_device_type()
        if cur_type != DESIRED_TYPE:
            changes.append(Change(
                item="DEVICE_METADATA.localhost.type",
                current=cur_type or "unset",
                desired=DESIRED_TYPE,
                cmd=(f"redis-cli -n 4 hset 'DEVICE_METADATA|localhost' "
                     f"type '{DESIRED_TYPE}'"),
            ))

        # 2. L3 fabric tables — enumerate remaining keys
        for table in L3_TABLES:
            keys = self._redis_keys(f"{table}|*")
            for key in keys:
                changes.append(Change(
                    item=key,
                    current="present",
                    desired="removed",
                    cmd=f"redis-cli -n 4 del '{key}'",
                ))

        # 3. bgp.service should be masked
        if not self._bgp_is_masked():
            changes.append(Change(
                item="bgp.service",
                current="enabled",
                desired="masked",
                cmd="sudo systemctl mask --now bgp.service",
            ))

        return changes

    def apply(self, changes: list) -> None:
        for change in changes:
            _, err, rc = self.ssh.run(change.cmd, timeout=30)
            if rc != 0:
                print(f"  [warn] {change.cmd!r} rc={rc}: {err.strip()}")

    def verify(self) -> bool:
        remaining = self.check()
        if remaining:
            for c in remaining:
                print(f"  [defaults_cleanup] FAIL: {c}")
            return False
        return True
