import asyncio
import math
from django.utils import timezone
from dataclasses import dataclass, field

from .proxmox_cluster import ProxmoxCluster
from .proxmox_node import ProxmoxNodes
from ..netbox_handler.nb_proxbox import upsert_proxbox_item
from ..proxbox_session import ProxboxSession
from ..plugins_config import (
    PROXMOX_SESSIONS_LIST, PROXMOX_SESSIONS
)
from ..netbox_handler.nb_virtualmachine import get_total_count_by_job, get_vm_to_delete_by_job, async_delete_vm, \
    async_get_total_count_by_job, async_get_vm_to_delete_by_job

from ...models import ProxmoxVM


@dataclass
class ProxmoxVirtualMachine:
    domain: str = None
    template: int = 0
    cpu: int = 0
    status: str = None
    netout: int = 0
    type: str = 'lxc'
    maxmem: int = 0
    diskread: int = 0
    diskwrite: int = 0
    id: str = None
    maxdisk: int = 0
    disk: int = 0
    node: str = None
    name: str = None
    maxcpu: int = 0
    netin: int = 0
    uptime: int = 0
    mem: int = 0
    vmid: int = 0
    data: dict = None
    cluster: ProxmoxCluster = None
    proxmox_node: ProxmoxNodes = None
    proxbox_session: ProxboxSession = None
    nb_vm: ProxmoxVM = None

    def __post_init__(self):
        if self.proxbox_session is None:
            self.reset_proxbox_session()

    def reset_proxbox_session(self):
        if self.domain is None:
            return
        self.proxbox_session = PROXMOX_SESSIONS.get(self.domain)
        return self.proxbox_session

    async def async_add_vm_to_netbox(self):
        return await asyncio.to_thread(self.add_vm_to_netbox)

    def add_vm_to_netbox(self):
        try:
            self.nb_vm = upsert_proxbox_item(self)
        except Exception as e:
            print(f"Error with the vm {self.name} at {self.domain}")
            print(e)
            raise e
        return self

    @staticmethod
    def instance_from_object(value: dict, cluster=None, node=None):
        if value is None:
            return None

        return ProxmoxVirtualMachine(
            domain=value.get("domain", None),
            template=value.get("template", None),
            cpu=value.get("cpu", None),
            status=value.get("status", None),
            netout=value.get("netout", None),
            type=value.get("type", None),
            maxmem=value.get("maxmem", None),
            diskread=value.get("diskread", None),
            diskwrite=value.get("diskwrite", None),
            id=value.get("id", None),
            maxdisk=value.get("maxdisk", None),
            disk=value.get("disk", None),
            node=value.get("node", None),
            name=value.get("name", None),
            maxcpu=value.get("maxcpu", None),
            netin=value.get("netin", None),
            uptime=value.get("uptime", None),
            mem=value.get("mem", None),
            vmid=value.get("vmid", None),
            data=value,
            cluster=cluster,
            proxmox_node=node,

        )

    @staticmethod
    async def async_get_vms_from_cluster(cluster, nodes):
        runner = []
        vm_totals = []
        proxmox_vms = cluster.proxbox_session.session.cluster.resources.get(type='vm')
        for vm in proxmox_vms:
            is_template = vm.get("template")
            if is_template == 1:
                continue
            node = next(iter([x for x in nodes if x.name == vm.get('node') and x.cluster.name == cluster.name]), None)
            if node is None:
                continue
            vm['domain'] = cluster.domain
            vm_value = ProxmoxVirtualMachine.instance_from_object(vm, cluster, node)
            # await vm_value.async_add_vm_to_netbox()
            runner.append(vm_value.async_add_vm_to_netbox())
            if len(runner) > 9:
                r1 = await asyncio.gather(*runner, return_exceptions=True)
                vm_totals = vm_totals + r1
                runner = []
                await asyncio.sleep(0)

        results = await asyncio.gather(*runner, return_exceptions=True)
        if len(results) > 0:
            vm_totals = vm_totals + results

        vms = []
        for r in vm_totals:
            if isinstance(r, Exception):
                continue
            vms.append(r)

        return vms

    @staticmethod
    async def async_clear_vms(job_id):
        print('[{:%H:%M:%S}] Starting cleaning vms job {}...'.format(timezone.now(), job_id))
        output = []
        # Get all the vm's to be deleted
        limit = 100
        count = await async_get_total_count_by_job(job_id)
        print('[{:%H:%M:%S}] Cleaning {} jobs...'.format(timezone.now(), count))
        # if there are no task just finish the process
        if count < 1:
            return

        runner = []
        pages = math.ceil(count / limit)
        print('[{:%H:%M:%S}] Total pages: {}'.format(timezone.now(), pages))
        for n in range(pages):
            # Get the vms to be deleted
            print('[{:%H:%M:%S}] Getting the list of VMs...'.format(timezone.now()))
            try:
                results = await async_get_vm_to_delete_by_job(job_id, n + 1, limit)
                print('[{:%H:%M:%S}] Got for this page {}'.format(timezone.now(), len(results)))
                if results is None or len(results) < 1:
                    continue

                for vm in results:
                    runner.append(async_delete_vm(vm, job_id))
                    # print('[{:%H:%M:%S}] Deleting VM...{}'.format(timezone.now(), vm))
                    # try:
                    #     r = await async_delete_vm(vm, job_id)
                    #     if isinstance(r, Exception):
                    #         continue
                    #     print('[{:%H:%M:%S}] Adding to output...{}'.format(timezone.now(), r))
                    #     output.append(r)
                    # except Exception as e1:
                    #     print(e1)

            except Exception as e:
                print(e)

        res_vms = await asyncio.gather(*runner, return_exceptions=True)
        for r in res_vms:
            if isinstance(r, Exception):
                continue
            output.append(r)
        return output
