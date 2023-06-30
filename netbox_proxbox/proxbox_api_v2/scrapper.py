'''
Execution Steps
1. Get all the data in the configuration options file
2. for each domain get all the cluster information
3. Create the cluster in netbox
4. Get the nodes for the cluster
5. For each node get the quemu/lxc machines
6. For Each machine get the resource information
7. Remove the unused machines
'''

import asyncio
import uuid

from .plugins_config import PROXMOX_SESSIONS_LIST
from .proxmox.proxmox_cluster import ProxmoxCluster
from .proxmox.proxmox_node import ProxmoxNodes

from django.utils import timezone

from .proxmox.proxmox_virtualmachine import ProxmoxVirtualMachine


class Scrapper:

    @staticmethod
    async def get_all_clusters(job_id=None):
        if job_id is None:
            job_id = uuid.uuid4()
        runner = []
        clusters = []
        # Get all the cluster from the configuration
        for session in PROXMOX_SESSIONS_LIST:
            cluster = ProxmoxCluster.async_instance_cluster(session.domain)
            runner.append(cluster)
        results = await asyncio.gather(*runner, return_exceptions=True)

        # Get all clusters that didn't fail
        for cluster in results:
            if isinstance(cluster, Exception):
                continue
            cluster.job_id = job_id
            clusters.append(cluster)
        return clusters

    @staticmethod
    async def get_all_nodes(clusters):
        nodes = []
        node_runner = []
        for cluster in clusters:
            if isinstance(cluster, Exception):
                continue
            nodes = ProxmoxNodes.get_nodes_from_cluster(cluster)
            for node in nodes:
                # Get all the network data for the cluster
                node_runner.append(node.async_get_node_network())

        nodes_result = await asyncio.gather(*node_runner, return_exceptions=True)

        # Get all the nodes that didn't fail
        for node in nodes_result:
            if isinstance(node, Exception):
                continue
            nodes.append(node)
        return nodes

    @staticmethod
    async def get_all_vms(clusters, nodes):
        vms = []
        runner = []
        for c in clusters:
            runner.append(ProxmoxVirtualMachine.async_get_vms_from_cluster(c, nodes))

        results = await asyncio.gather(*runner, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                continue
            vms = vms + r

        return vms

    @staticmethod
    async def async_run():
        job_id = uuid.uuid4()
        message_init = '[{:%H:%M:%S}] Initializing run for job {}...'.format(timezone.now(), job_id)
        print(message_init)
        # get all the clusters
        clusters = await Scrapper.get_all_clusters(job_id)

        # Get the nodes from the clusters
        nodes = await Scrapper.get_all_nodes(clusters)

        await Scrapper.get_all_vms(clusters, nodes)

        await ProxmoxVirtualMachine.async_clear_vms(str(job_id))

        print(message_init)

        print('[{:%H:%M:%S}] Finish run for job {}...'.format(timezone.now(), job_id))

    @staticmethod
    def run():
        print(PROXMOX_SESSIONS_LIST)
        for session in PROXMOX_SESSIONS_LIST:
            proxmox_cluster = ProxmoxCluster.instance_cluster(session.domain)
            print(proxmox_cluster)
