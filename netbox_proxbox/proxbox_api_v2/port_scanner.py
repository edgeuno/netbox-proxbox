import asyncio
import time
import json
import math

import os

from virtualization.models import VirtualMachine, VMInterface
from tenancy.models import Tenant, TenantGroup, Contact, ContactRole, ContactAssignment
from ipam.models import Service

file_path = str(os.path.dirname(os.path.realpath(__file__))) + "/ports.json"
with open(file_path) as config_file:
    file_contents = config_file.read()

if file_contents is None:
    raise Exception(f"No contents were found at the path {file_path}")

mapped_ports = json.loads(file_contents)

# https://github.com/silverwind/port-numbers/blob/master/ports.json
# SuperFastPython.com
# https://superfastpython.com/asyncio-port-scanner/
class VMPortScanner:

    @staticmethod
    def get_vm_by_tenant(tenants):
        netbox_vms = []
        for i in tenants:
            netbox_vms1 = [i for i in VirtualMachine.objects.filter(tenant__name=i)]
            netbox_vms = netbox_vms + netbox_vms1
        return netbox_vms

    @staticmethod
    def get_ips_for_vm(vm):

        interfaces = [i for i in vm.interfaces.all()]
        ips = []
        for i in interfaces:
            tmp = [j for j in i.ip_addresses.all()]
            ips = ips + tmp
        # print(ips)
        return ips

        # service = Service.objects.filter(virtual_machine_id=vm.id,ports__contains=[12345]).first()
        # if service is None:
        #     service = Service(
        #         virtual_machine=vm,
        #         virtual_machine_id=vm.id,
        #         name="test1",
        #         protocol="tcp",
        #         ports=[12345],
        #     )
        #     service.save()
        # service.ipaddresses.add(vm.primary_ip4)
        # service.save()
        #
        # vm.services.add(service)
        # vm.save()
        # return vm

    @staticmethod
    async def process_vm(vm):
        print(f'processing {vm}')
        ips = await asyncio.to_thread(VMPortScanner.get_ips_for_vm, vm)
        runner = []
        services = []
        for ip in ips:
            runner.append(VMPortScanner.process_ip(vm, ip))

        result = await asyncio.gather(*runner, return_exceptions=True)

        for r in result:
            if isinstance(r, Exception):
                continue
            if r is not None and len(r) > 0:
                services = services + r

        for s in services:
            await asyncio.to_thread(vm.services.add, s)
        await asyncio.to_thread(vm.save)
        return vm

    @staticmethod
    def set_service_to_vm(vm, ip, port_open):
        t_port, port_type, port_map, host = port_open
        service = Service.objects.filter(virtual_machine_id=vm.id, ports__contains=[t_port],
                                         ipaddresses=ip.id, protocol=port_type).first()
        if service is None:
            service = Service(
                virtual_machine=vm,
                virtual_machine_id=vm.id,
                name=port_map.get("name"),
                protocol=port_type,
                ports=[t_port],
            )
            service.save()

        service.ipaddresses.add(ip)
        service.name = port_map.get("name")
        service.description = f'> {host}:{t_port} [OPEN] -> {port_map.get("name")}: {port_map.get("description")}'
        service.save()

        return service

    @staticmethod
    def remove_services_from_vm(vm, services):
        nb_services = vm.services.all()
        to_remove = []
        output = []

        for nbs in nb_services:
            is_to_delete = True
            for s in services:
                if s.ports != nbs.ports:
                    continue
                if s.protocol != nbs.protocol:
                    continue
                ips = s.ipaddresses.all()
                nbips = nbs.ipaddresses.all()
                has_ip = False
                for nbitm in nbips:
                    for itm in ips:
                        if nbitm == itm:
                            has_ip = True
                            break
                if has_ip:
                    is_to_delete = False
                    break
            if is_to_delete:
                to_remove.append(nbs)
            else:
                output.append(nbs)
        for d in to_remove:
            vm.services.remove(d)
            d.delete()

        return output

    @staticmethod
    async def process_ip(vm, ip):
        host = str(ip.address.ip)
        ports_range = range(1, 65535)
        ports_open = await VMPortScanner.process_ports(host, ports_range, 100)
        services = []
        for i in ports_open:
            s = await asyncio.to_thread(VMPortScanner.set_service_to_vm, vm, ip, i)
            if s is not None:
                services.append(s)
        services = await asyncio.to_thread(VMPortScanner.remove_services_from_vm, vm, services)
        return services

    @staticmethod
    async def test_port_number(host, port, timeout=3):
        # create coroutine for opening a connection
        coro = asyncio.open_connection(host, port)
        # execute the coroutine with a timeout
        try:
            # open the connection and wait for a moment
            _, writer = await asyncio.wait_for(coro, timeout)
            # close connection once opened
            writer.close()
            # indicate the connection can be opened
            return True, host, port
        except Exception as e:
            # indicate the connection cannot be opened
            return False, host, port

    @staticmethod
    async def process_ports(host, ports, limit=100):
        start_time = time.time()
        # report a status message
        print(f'Scanning {host}...')
        pages = math.ceil(len(ports) / (limit if limit is not None or limit != 0 else len(ports)))
        open_ports = []
        for i in range(0, pages):
            try:
                offset = i * limit
                offset1 = ((i + 1) * limit)
                print(f'{host}:{offset}-{offset1}')
                ports_subset = ports[offset:offset1]
                runner = []
                for j in ports_subset:
                    runner.append(VMPortScanner.test_port_number(host, j, 3))
                result = await asyncio.gather(*runner, return_exceptions=True)
                # result.append((True, host, 12345))
                # result.append((True, host, 12346))
                for k in result:
                    r, t_hots, t_port = k
                    if r:
                        # report the report if open
                        port_type = 'tcp'
                        port_map = mapped_ports.get(f'{t_port}/tcp')
                        if port_map is None:
                            port_map = mapped_ports.get(f'{t_port}/udp')
                            port_type = 'udp'
                        if port_map is None:
                            port_type = 'tcp'
                            port_map = {'description': 'Unknown', 'name': f'{t_port}'}
                        message = f'> {host}:{t_port} [OPEN] -> {port_map.get("name")}: {port_map.get("description")}'
                        print(message)
                        open_ports.append((t_port, port_type, port_map, host))
            except Exception as e:
                print(e)
        # append((12345, 'tcp', mapped_ports.get(f'{12345}/tcp'), host))
        # open_ports.append((12346, 'tcp', {'description': 'Unknown', 'name': f'{12346}'}, host))
        print("--- %s seconds ---" % (time.time() - start_time))
        return open_ports

    @staticmethod
    async def async_run(tenants):
        start_time = time.time()
        # Get the vm with the tenant
        limit = 100
        netbox_vms = await asyncio.to_thread(VMPortScanner.get_vm_by_tenant, tenants)
        pages = math.ceil(len(netbox_vms) / (limit if limit is not None or limit != 0 else len(netbox_vms)))
        for i in range(0, pages):
            try:
                offset = i * limit
                offset1 = ((i + 1) * limit)
                print(f'running {offset}:{offset1}')
                vms_subset = netbox_vms[offset:offset1]
                runner = []
                for vm in vms_subset:
                    runner.append(VMPortScanner.process_vm(vm))
                result = await asyncio.gather(*runner, return_exceptions=True)
                print(result)
                print("---Partial run time %s seconds ---" % (time.time() - start_time))
            except Exception as e:
                print(e)
        # vm = netbox_vms[0]
        # vm1 = netbox_vms[1]
        # runner = [VMPortScanner.process_vm(vm), VMPortScanner.process_vm(vm1)]
        # # runner = [VMPortScanner.process_vm(vm1)]
        # results = await asyncio.gather(*runner)
        # print(results)
        print("---Total run time %s seconds ---" % (time.time() - start_time))
