import pytz
from django.db import connection, transaction
from datetime import datetime

from .nb_virtualmachine import upsert_netbox_vm
from ..plugins_config import PROXMOX_SESSIONS

from ...models import ProxmoxVM

# import logging
import traceback

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)


def get_resources(proxmox_vm):
    # Save values from Proxmox
    vcpus = float(proxmox_vm.maxcpu)

    # Convert bytes to megabytes and then convert float to integer
    memory_Mb = proxmox_vm.maxmem
    memory_Mb = int(memory_Mb / 1048576)

    # Convert bytes to gigabytes and then convert float to integer
    disk_Gb = proxmox_vm.maxdisk
    disk_Gb = int(disk_Gb / 1000000000)

    return vcpus, memory_Mb, disk_Gb


def upsert_proxbox_item(proxmox_vm) -> ProxmoxVM:
    proxmox_session = proxmox_vm.proxbox_session
    port = proxmox_session.http_port if proxmox_session.http_port else 8006
    domain = proxmox_vm.domain
    vmid = proxmox_vm.vmid
    node = proxmox_vm.node

    config = None
    vm_type = proxmox_vm.type
    try:
        if vm_type == 'qemu':
            config = proxmox_session.session.nodes(node).qemu(vmid).config.get()
        if vm_type == 'lxc':
            config = proxmox_session.session.nodes(node).lxc(vmid).config.get()
    except Exception as e:
        print("Error: set_get_proxbox_item-1 - {}".format(e))
        # logger.exception(e)
        # traceback.print_exc()
        print(e)
        config = None

    vcpus, memory_Mb, disk_Gb = get_resources(proxmox_vm)

    proxbox_vm = ProxmoxVM.objects.filter(domain=domain, proxmox_vm_id=vmid).first()
    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM.objects.filter(domain=domain, name=proxmox_vm.name).first()

    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM(
            name=proxmox_vm.name,
            proxmox_vm_id=vmid,
            type=vm_type,
            domain=domain,
            latest_job=proxmox_vm.cluster.job_id,
            latest_update=(datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        )
        proxbox_vm.save()
    if proxbox_vm:
        proxbox_vm.name = proxmox_vm.name
        proxbox_vm.instance_data = proxmox_vm.data,
        proxbox_vm.config_data = config
        proxbox_vm.url = 'https://{}:{}/#v1:0:={}%2F{} '.format(domain, port, vm_type, vmid)
        proxbox_vm.latest_job = proxmox_vm.cluster.job_id
        proxbox_vm.latest_update = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        proxbox_vm.cluster_id = proxmox_vm.cluster.nb_cluster.id
        proxbox_vm.cluster = proxmox_vm.cluster.nb_cluster
        proxbox_vm.node = node
        proxbox_vm.vcpus = vcpus
        proxbox_vm.memory = memory_Mb
        proxbox_vm.disk = disk_Gb
        proxbox_vm.proxmox_vm_id = vmid
        proxbox_vm.domain = domain

        proxbox_vm.save()

        netbox_vm = upsert_netbox_vm(proxmox_vm, config)
        proxbox_vm.virtual_machine_id = netbox_vm.id
        proxbox_vm.virtual_machine = netbox_vm

        proxbox_vm.save()

    return proxbox_vm


def delete_proxbox_vm_sql(proxbox_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE from netbox_proxbox_proxmoxvm where id = %s ",
                           [proxbox_id])
        return True
    except Exception as e:
        # logger.exception(e)
        # traceback.print_exc()
        print("Error: delete_proxbox_vm_sql - {}".format(e))
        print(e)
        return False


def get_proxmox_config(vm):
    config = None
    proxbox_vm = None
    domain = None
    node = None
    vmid = None
    type = None
    proxmox = None
    try:
        proxbox_vm = ProxmoxVM.objects.filter(virtual_machine_id=vm.id).first()
        if proxbox_vm:
            # If there is an item get the configuration from proxmox
            domain = proxbox_vm.domain
            node = proxbox_vm.node
            vmid = proxbox_vm.proxmox_vm_id
            type = proxbox_vm.type

        # Get the domain from the context data of the vm if no proxbox item exist
        if domain is None:
            domain = vm.local_context_data['proxmox'].get('domain')
        if node is None:
            node = vm.local_context_data['proxmox'].get('node')
        if vmid is None:
            vmid = vm.local_context_data['proxmox'].get('id')
        if type is None:
            type = vm.local_context_data['proxmox'].get('type')

        if domain is not None:
            try:
                proxmox_session = PROXMOX_SESSIONS.get(domain, None)
                if proxmox_session is not None:
                    proxmox = proxmox_session.session
            except:
                pass

        if proxmox is not None and node is not None and vmid is not None:
            if type == 'qemu':
                config = proxmox.nodes(node).qemu(vmid).config.get()
            if type == 'lxc':
                config = proxmox.nodes(node).lxc(vmid).config.get()
    except Exception as e:
        print("Error: get_promox_config-1 - {}".format(e))
        # logger.exception(e)
        # traceback.print_exc()
        print(e)
        config = None
    return config, proxbox_vm, domain, node, vmid, type


def upsert_proxbox_from_vm(vm, domain, node, vmid, job_id, cluster, type, config):
    proxmox_session = PROXMOX_SESSIONS.get(domain)
    proxmox = proxmox_session.session
    port = proxmox_session.http_port

    vcpus = vm.vcpus
    memory_Mb = vm.memory
    disk_Gb = vm.disk
    proxbox_vm = ProxmoxVM.objects.filter(domain=domain, name=vm.name).first()
    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM.objects.filter(domain=domain, proxmox_vm_id=vmid).first()

    if proxbox_vm is None:
        proxbox_vm = ProxmoxVM(
            name=vm.name,
            proxmox_vm_id=vmid,
            type=type,
            domain=domain,
            latest_job=job_id,
            latest_update=(datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        )
        proxbox_vm.save()
    if proxbox_vm:
        proxbox_vm.config_data = config
        proxbox_vm.url = 'https://{}:{}/#v1:0:={}%2F{} '.format(domain, port, type, vmid)
        proxbox_vm.latest_job = job_id
        proxbox_vm.latest_update = (datetime.now()).replace(microsecond=0, tzinfo=pytz.utc)
        proxbox_vm.cluster_id = cluster.id
        proxbox_vm.cluster = cluster
        proxbox_vm.node = node
        proxbox_vm.vcpus = vcpus
        proxbox_vm.memory = memory_Mb
        proxbox_vm.disk = disk_Gb
        proxbox_vm.proxmox_vm_id = vmid
        proxbox_vm.domain = domain

        proxbox_vm.virtual_machine_id = vm.id
        proxbox_vm.virtual_machine = vm

        proxbox_vm.save()

    return proxbox_vm
