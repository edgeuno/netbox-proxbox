from dataclasses import dataclass, field
import asyncio

from ..netbox_handler.nb_cluster import upsert_cluster

try:
    from virtualization.models import Cluster
except Exception as e:
    print(e)
    raise e

from ..proxbox_session import ProxboxSession
from ..plugins_config import (
    PROXMOX_SESSIONS_LIST, PROXMOX_SESSIONS
)


@dataclass
class ProxmoxCluster:
    proxbox_session: ProxboxSession = field(init=True)
    domain: str = ""
    name: str = ""
    status: str = ""
    quorate: int = 0,
    version: int = 0
    data: dict = None
    site_name: str = ""
    # nodes: ProxmoxNodes = field(init=False)
    nb_cluster: Cluster = None
    job_id: str = ""

    def __post_init__(self):
        if self.proxbox_session is None:
            self.reset_proxbox_session()

    def reset_proxbox_session(self):
        if self.domain is None:
            return
        self.proxbox_session = PROXMOX_SESSIONS.get(self.domain)
        return self.proxbox_session

    def complete_cluster(self):
        if self.proxbox_session is None:
            self.proxbox_session = self.reset_proxbox_session()
        if self.proxbox_session is None:
            return
        result = self.proxbox_session.session.cluster.status.get()
        cluster = result[0]
        self.data = result
        self.name = cluster.get("name", None)
        self.quorate = cluster.get("quorate", None)
        self.version = cluster.get("version", None)
        return self

    async def async_add_cluster_to_netbox(self):
        return await asyncio.to_thread(self.add_cluster_to_netbox)

    def add_cluster_to_netbox(self):
        # Save cluster in netbox
        self.nb_cluster = upsert_cluster(self)
        return self

    @staticmethod
    async def async_instance_cluster(domain, proxbox_session=None):
        return await asyncio.to_thread(ProxmoxCluster.instance_cluster, domain, proxbox_session)

    @staticmethod
    def instance_cluster(domain, proxbox_session=None):
        if domain is None:
            raise Exception("Domain can not be null")
        cluster = ProxmoxCluster(
            domain=domain,
            proxbox_session=proxbox_session
        )
        if cluster.proxbox_session is None:
            raise Exception("The cluster wasn't correctly initialize")
        # Compleate the information for the cluster
        cluster.complete_cluster()
        # Upsert the cluster in netbox
        cluster.add_cluster_to_netbox()

        return cluster
