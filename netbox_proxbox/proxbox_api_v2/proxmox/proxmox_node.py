import asyncio
from dataclasses import dataclass, field

from dcim.models import Device

from .proxmox_cluster import ProxmoxCluster
from ..netbox_handler.nb_nodes import upsert_nodes
from ..plugins_config import PROXMOX_SESSIONS
from ..proxbox_session import ProxboxSession


@dataclass
class ProxmoxNodes:
    domain: str
    id: str = ""
    ip: str = ""
    name: str = ""
    level: str = ""
    local: int = 0
    nodeid: int = 0
    online: int = 0
    proxbox_session: ProxboxSession = None
    data: dict = None
    network_data: dict = None
    # Full network data
    cidr: str = None
    bridge_ports: str = None
    type: str = None
    address: str = None
    iface: str = None
    families: list = None
    autostart: int = None
    active: int = None
    method6: str = None
    priority: int = None
    bridge_stp: str = None
    bridge_fd: str = None
    gateway: str = None
    method: str = None
    netmask: str = None

    cluster: ProxmoxCluster = None
    # Netbox node device
    nb_node: Device = None

    def __post_init__(self):
        if self.proxbox_session is None:
            self.reset_proxbox_session()
        # if self.cidr is None:
        #     self.get_node_network()

    def reset_proxbox_session(self):
        if self.domain is None:
            return
        self.proxbox_session = PROXMOX_SESSIONS.get(self.domain)
        return self

    async def async_get_node_network(self):
        return await asyncio.to_thread(self.get_node_network)

    def get_node_network(self):
        print(f"Getting Node for {self.name}")
        result = self.proxbox_session.session.nodes(self.name).network().get()
        for d in result:
            if 'address' in d and d['address'] == self.ip:
                self.cidr = d['cidr'] if 'cidr' in d else None
                self.bridge_ports = d['bridge_ports'] if 'bridge_ports' in d else None
                self.address = d['address'] if 'address' in d else None
                self.iface = d['iface'] if 'iface' in d else None
                self.families = d['families'] if 'families' in d else None
                self.autostart = d['autostart'] if 'autostart' in d else None
                self.active = d['active'] if 'active' in d else None
                self.method6 = d['method6'] if 'method6' in d else None
                self.priority = d['priority'] if 'priority' in d else None
                self.bridge_stp = d['bridge_stp'] if 'bridgeStp' in d else None
                self.bridge_fd = d['bridge_fd'] if 'bridgeFd' in d else None
                self.address = d['address'] if 'address' in d else None
                self.gateway = d['gateway'] if 'gateway' in d else None
                self.method = d['method'] if 'method' in d else None
                self.netmask = d['netmask'] if 'netmask' in d else None
                self.network_data = d
                break
        self.nb_node = upsert_nodes(self)
        return self

    @staticmethod
    def instance_from_object(value: dict, domain: str = None, cluster: ProxmoxCluster = None):
        if value is None:
            return None

        return ProxmoxNodes(
            domain=domain,
            id=value.get("id", None),
            ip=value.get("ip", None),
            name=value.get("name", None),
            level=value.get("level", None),
            local=value.get("local", None),
            nodeid=value.get("nodeid", None),
            online=value.get("online", None),
            cluster=cluster,
            data=value
        )

    @staticmethod
    def get_nodes_from_list(value: list, domain: str = None, cluster: ProxmoxCluster = None):
        output = []
        for i in value:
            try:
                data = ProxmoxNodes.instance_from_object(i, domain, cluster)
                output.append(data)
            except Exception as e:
                print(e)
                continue
        return output
        # return [ProxmoxNodes.instance_from_object(i, domain) for i in value]

    @staticmethod
    def get_nodes_from_cluster(cluster):
        rawNodes = cluster.data[1:]
        nodes = ProxmoxNodes.get_nodes_from_list(rawNodes, cluster.domain, cluster)
        return nodes
