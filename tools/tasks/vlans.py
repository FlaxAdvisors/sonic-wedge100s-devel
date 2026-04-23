"""VlanTask — create VLANs and add members."""
from .base import Change, ConfigTask


class VlanTask(ConfigTask):

    def check(self) -> list:
        changes = []
        for vlan in self.topology["vlans"]:
            vid = vlan["id"]

            # VLAN exists?
            out, _, _ = self.ssh.run(
                f"redis-cli -n 4 exists 'VLAN|Vlan{vid}'", timeout=10
            )
            if out.strip() != "1":
                changes.append(Change(
                    item=f"VLAN {vid}",
                    current="missing",
                    desired="present",
                    cmd=f"sudo config vlan add {vid}",
                ))

            # Members
            for member in vlan["members"]:
                out, _, _ = self.ssh.run(
                    f"redis-cli -n 4 exists 'VLAN_MEMBER|Vlan{vid}|{member}'",
                    timeout=10,
                )
                if out.strip() != "1":
                    changes.append(Change(
                        item=f"VLAN {vid} member {member}",
                        current="missing",
                        desired="untagged member",
                        cmd=f"sudo config vlan member add --untagged {vid} {member}",
                    ))
                else:
                    # Verify tagging_mode is untagged
                    out, _, _ = self.ssh.run(
                        f"redis-cli -n 4 hget 'VLAN_MEMBER|Vlan{vid}|{member}' tagging_mode",
                        timeout=10,
                    )
                    if out.strip() != "untagged":
                        changes.append(Change(
                            item=f"VLAN {vid} member {member} tagging",
                            current=out.strip() or "unset",
                            desired="untagged",
                            cmd=f"sudo config vlan member del {vid} {member} && sudo config vlan member add --untagged {vid} {member}",
                        ))

        return changes

    def _strip_router_interface(self, port: str) -> None:
        """Remove any router-interface config on a port so it can be added
        to a VLAN as a member.  `config vlan member add` hard-aborts with
        'Error: <port> is a router interface!' if an INTERFACE table entry
        exists — that happens when the factory/default config mapped the
        port as a routed L3 port (typical for T1/T2 fabric configs).

        We use direct CONFIG_DB DEL rather than `config interface ip remove`
        because the CLI requires the `bgp` container to be running (it calls
        into the BGP container to drop the interface from BGP's knowledge).
        On boxes where bgp is masked (common on test/lab setups) the CLI
        fails with 'container is not running'.  orchagent sees CONFIG_DB
        deletes via its regular notification path and properly cleans up
        the port's L3 state — so direct DEL is correct here.
        """
        # Enumerate keys: both the bare 'INTERFACE|Ethernet24' marker and
        # each 'INTERFACE|Ethernet24|<ip>/<prefix>' entry.
        keys_out, _, _ = self.ssh.run(
            f"redis-cli -n 4 keys 'INTERFACE|{port}' 'INTERFACE|{port}|*'",
            timeout=10,
        )
        for key in keys_out.split():
            self.ssh.run(f"redis-cli -n 4 del '{key}'", timeout=10)

    def apply(self, changes: list) -> None:
        for change in changes:
            # Strip router-interface config before adding a VLAN member;
            # otherwise 'config vlan member add' aborts with
            # 'Error: <port> is a router interface!'.
            if (" member " in change.item
                    and change.current == "missing"):
                port = change.item.split()[-1]
                if port.startswith("Ethernet"):
                    self._strip_router_interface(port)
            out, err, rc = self.ssh.run(change.cmd, timeout=30)
            if rc != 0:
                print(f"  [warn] {change.cmd!r} rc={rc}: {err.strip()}")

    def verify(self) -> bool:
        remaining = self.check()
        if remaining:
            for c in remaining:
                print(f"  [vlans] FAIL: {c}")
            return False
        return True
