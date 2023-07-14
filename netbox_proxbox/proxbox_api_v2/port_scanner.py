import asyncio
import time
import json
import math
import random

import os

from socket import AF_INET, AF_INET6
from socket import SOCK_STREAM
from socket import socket
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor

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
        print(f'Start processing {vm}')
        ips = await asyncio.to_thread(VMPortScanner.get_ips_for_vm, vm)
        await asyncio.sleep(0)
        runner = []
        services = []
        for ip in ips:
            runner.append(VMPortScanner.process_ip(vm, ip))

        result = await asyncio.gather(*runner, return_exceptions=True)
        await asyncio.sleep(0)

        for r in result:
            if isinstance(r, Exception):
                continue
            if r is not None and len(r) > 0:
                services = services + r

        for s in services:
            await asyncio.to_thread(vm.services.add, s)
            await asyncio.sleep(0)
        await asyncio.to_thread(vm.save)
        print(f'Finish processing {vm}')
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
        ports_open = await VMPortScanner.process_ports(host, ports_range, 25)
        await asyncio.sleep(0)
        services = []
        for i in ports_open:
            s = await asyncio.to_thread(VMPortScanner.set_service_to_vm, vm, ip, i)
            if s is not None:
                services.append(s)
        # services = await asyncio.to_thread(VMPortScanner.remove_services_from_vm, vm, services)
        print(f'Open ports: {ports_open}')
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
        print(f'Start Scanning {host}...')
        s = math.ceil(len(ports) / (limit if limit is not None or limit != 0 else len(ports)))
        open_ports = []
        for i in range(0, pages):
            try:
                offset = i * limit
                offset1 = ((i + 1) * limit)
                # print(f'{host}:{offset}-{offset1}')
                ports_subset = ports[offset:offset1]
                runner = []
                for j in ports_subset:
                    runner.append(VMPortScanner.test_port_number(host, j, 3))
                result = await asyncio.gather(*runner, return_exceptions=True)
                await asyncio.sleep(0)
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
        print(f'Finish scanning {host}...')
        print("--- %s seconds ---" % (time.time() - start_time))
        return open_ports

    @staticmethod
    async def async_run(tenants):
        start_time = time.time()
        # Get the vm with the tenant
        limit = 100
        netbox_vms = await asyncio.to_thread(VMPortScanner.get_vm_by_tenant, tenants)
        # pages = math.ceil(len(netbox_vms) / (limit if limit is not None or limit != 0 else len(netbox_vms)))
        # for i in range(0, pages):
        try:
            #         offset = i * limit
            #         offset1 = ((i + 1) * limit)
            #         print(f'running {offset}:{offset1}')
            vms_subset = netbox_vms  # netbox_vms[offset:offset1]
            runner = []
            for vm in vms_subset:
                runner.append(VMPortScanner.process_vm(vm))
            result = await asyncio.gather(*runner, return_exceptions=True)
            print(result)
            # print("---Partial run time %s seconds ---" % (time.time() - start_time))
        except Exception as e:
            print(e)
        # vm = netbox_vms[0]
        # vm1 = netbox_vms[1]
        # runner = [VMPortScanner.process_vm(vm), VMPortScanner.process_vm(vm1)]
        # # runner = [VMPortScanner.process_vm(vm1)]
        # results = await asyncio.gather(*runner)
        # print(results)
        print("---Total run time %s seconds ---" % (time.time() - start_time))


class VMPortScannerSync:
    @staticmethod
    def get_vm_by_tenant(tenants):
        netbox_vms = []
        for i in tenants:
            netbox_vms1 = [i for i in VirtualMachine.objects.filter(tenant__name=i)]
            netbox_vms = netbox_vms + netbox_vms1
        return netbox_vms

    @staticmethod
    def test_port_number(host, port, timeout=3):
        net = AF_INET
        if ":" in host:
            net = AF_INET6
        # create and configure the socket
        with socket(net, SOCK_STREAM) as sock:
            # set a timeout of a few seconds
            sock.settimeout(timeout)
            # connecting may fail
            try:
                # attempt to connect
                sock.connect((host, port))
                # a successful connection was made
                return True
            except:
                # ignore the failure
                return False

    @staticmethod
    def get_ips_for_vm(vm):
        interfaces = [i for i in vm.interfaces.all()]
        values = []
        for i in interfaces:
            tmp = [(j, vm) for j in i.ip_addresses.all()]
            values = values + tmp
        return values

    @staticmethod
    def get_ports_for_ip(input):
        ip, vm = input
        output = [(ip, vm, port) for port in range(1, 65535)]
        return output

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
    def get_service_from_port(value, timeout=3):
        ip, vm, port = value

        host = str(ip.address.ip)

        is_open = VMPortScannerSync.test_port_number(host, port, timeout)

        if is_open:
            port_type = 'tcp'
            port_map = mapped_ports.get(f'{port}/tcp')
            if port_map is None:
                port_map = mapped_ports.get(f'{port}/udp')
                port_type = 'udp'
            if port_map is None:
                port_type = 'tcp'
                port_map = {'description': 'Unknown', 'name': f'{port}'}
            message = f'> {host}:{port} [OPEN] -> {port_map.get("name")}: {port_map.get("description")}'
            print(message)
            open_port = (port, port_type, port_map, host)
            service = VMPortScannerSync.set_service_to_vm(vm, ip, open_port)
            vm.services.add(service)

            return vm, ip, port, service
        # rn = random.randint(0, 9)
        # if rn > 8:
        #     print(f'> {host}:{port} [CLOSE]')
        return None

    @staticmethod
    def random_list(input):
        bias_port = [22, 80, 8080, 22022, 443]
        random.shuffle(input)
        for i, v in enumerate(input):
            ip, vm, port = v
            if port in bias_port:
                element = input.pop(i)
                input.insert(0, element)

        return input

    @staticmethod
    def process_vms(vms):
        start_time = time.time()
        print(f'Start processing {vms}')
        ips = []
        ports_to_scan = []
        output = []

        for vm in vms:
            value = VMPortScannerSync.get_ips_for_vm(vm)
            ips = ips + value
        if ips is None or len(ips) < 1:
            return vms

        for value in ips:
            r = VMPortScannerSync.get_ports_for_ip(value)
            ports_to_scan = ports_to_scan + r

        ports_to_scan = VMPortScannerSync.random_list(ports_to_scan)
        limit = 10000
        total = len(ports_to_scan)
        pages = math.ceil( total / limit)

        #list_ports = []
        for i in range(0, pages):
            offset = i * limit
            offset1 = ((i + 1) * limit)
            print(f'Processing items: {offset}:{offset1}  of {total}')
            ports_subset = ports_to_scan[offset:offset1]
            #list_ports.append(ports_subset)

            executor = ThreadPoolExecutor(max_workers=limit)
            futures = [executor.submit(VMPortScannerSync.get_service_from_port, port, 4) for port in ports_subset]

            for future in as_completed(futures):
                r = future.result()
                if r is not None:
                    r_vm, r_ip, r_port, r_service = r
                    output.append((r_vm, r_service))
            executor.shutdown()
        print("---Total run time %s seconds ---" % (time.time() - start_time))
        print(f'Finish processing {vms}')
        return output

    @staticmethod
    def run(tenants):
        start_time = time.time()
        workers = os.cpu_count()
        if 'sched_getaffinity' in dir(os):
            workers = len(os.sched_getaffinity(0))
        print(f'Cpus {workers}')

        netbox_vms = VMPortScannerSync.get_vm_by_tenant(tenants)

        for i in netbox_vms:
            if i.name == 'E1-cpanel.edgeuno.com':
                vm = i
                break
        if vm:
            result = VMPortScannerSync.process_vms([vm, netbox_vms[0]])
            print(result)
        # for i in netbox_vms:
        #     if i.name == 'E1-cpanel.edgeuno.com':
        #         vm = i
        #         break
        # if vm:
        #     result = VMPortScannerSync.process_vm(vm)
        #     print(result)

        print("---Total run time %s seconds ---" % (time.time() - start_time))


class VMPortScannerSyncMultithread:
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
        return ips

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
    def test_port_number(host, port, timeout=3):
        net = AF_INET
        if ":" in host:
            net = AF_INET6
        # create and configure the socket
        with socket(net, SOCK_STREAM) as sock:
            # set a timeout of a few seconds
            sock.settimeout(timeout)
            # connecting may fail
            try:
                # attempt to connect
                sock.connect((host, port))
                # a successful connection was made
                return True, host, port
            except:
                # ignore the failure
                return False, host, port

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
        print(f'Service:{service} saved ...')
        return service

    @staticmethod
    def get_service_from_port(vm, ip, port, timeout=3):
        open_port = None

        host = str(ip.address.ip)

        is_open, t_host, t_port = VMPortScannerSync.test_port_number(host, port, timeout)

        if is_open:
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
            open_port = (t_port, port_type, port_map, host)

        return open_port

    @staticmethod
    def get_services_from_ports(vm, ip, limit=100):
        start_time = time.time()
        host = str(ip.address.ip)
        ports = range(1, 65535)
        # report a status message
        print(f'Start Scanning {host}...')
        pages = math.ceil(len(ports) / (limit if limit is not None or limit != 0 else len(ports)))
        services = []

        for i in range(0, pages):
            try:
                offset = i * limit
                offset1 = ((i + 1) * limit)
                ports_subset = ports[offset:offset1]

                executor = ThreadPoolExecutor(max_workers=len(ports_subset))

                # dispatch all tasks
                futures = [executor.submit(VMPortScannerSync.get_service_from_port, vm, ip, port, 4) for port in
                           ports_subset]

                # report results in order
                for future in as_completed(futures):
                    value = future.result()
                    if value is not None:
                        service = VMPortScannerSync.set_service_to_vm(vm, ip, value)
                        if service is not None:
                            print(service)
                            services.append(service)

                # shutdown the thread pool
                executor.shutdown()
            except Exception as e:
                print(e)
        print(f'Finish scanning {host}...')
        print("--- %s seconds ---" % (time.time() - start_time))
        return services

        print("--- %s seconds ---" % (time.time() - start_time))

    @staticmethod
    def process_ports(host, ports, limit=100):
        start_time = time.time()
        print(f'tracking for: {host} 2')
        # report a status message
        print(f'Start Scanning {host}...')
        # result = VMPortScannerSync.test_port_number(host, 22021)
        pages = math.ceil(len(ports) / (limit if limit is not None or limit != 0 else len(ports)))
        open_ports = []

        for i in range(0, pages):
            try:
                offset = i * limit
                offset1 = ((i + 1) * limit)
                ports_subset = ports[offset:offset1]

                executor = ThreadPoolExecutor(max_workers=len(ports_subset))

                # dispatch all tasks
                futures = [executor.submit(VMPortScannerSync.test_port_number, host, port, 4) for port in ports_subset]
                # report results in order
                for future in as_completed(futures):
                    value = future.result()
                    # print(f'tracking for: {host} 3: {value}')
                    is_open, t_host, t_port = value
                    if is_open:
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
                    # else:
                    #     print(f'> {host}:{t_port} close')
                # shutdown the thread pool
                executor.shutdown()
            except Exception as e:
                print(e)
        print(f'Finish scanning {host}...')
        print("--- %s seconds ---" % (time.time() - start_time))
        return open_ports

    @staticmethod
    def process_ip(vm, ip):
        print(f'tracking for: {vm} 1')
        host = str(ip.address.ip)
        ports_range = range(1, 65535)

        ports_open = VMPortScannerSync.process_ports(host, ports_range, 1000)
        # print(ports_open)
        services = []
        for port in ports_open:
            s = VMPortScannerSync.set_service_to_vm(vm, ip, port)
            if s is not None:
                services.append(s)
        # services = await asyncio.to_thread(VMPortScanner.remove_services_from_vm, vm, services)
        print(f'Open ports: {ports_open}')
        return services

    @staticmethod
    def process_vm(vm):
        print(f'Start processing {vm}')
        ips = VMPortScannerSync.get_ips_for_vm(vm)
        if ips is None or len(ips) < 1:
            return vm
        services = []
        executor = ThreadPoolExecutor(max_workers=len(ips))
        # futures = [executor.submit(VMPortScannerSync.get_services_from_ports, vm, ip, 10) for ip in ips]
        futures = [executor.submit(VMPortScannerSync.process_ip, vm, ip) for ip in ips]

        for future in as_completed(futures):
            r = future.result()
            if r is not None and len(r) > 0:
                services = services + r

        for s in services:
            vm.services.add(s)
        vm.save()
        print(f'Finish processing {vm}')
        return vm

    @staticmethod
    def run_bulk(vms):
        output = []
        if vms is None or len(vms) < 1:
            return output
        executor = ThreadPoolExecutor(max_workers=len(vms))
        futures = [executor.submit(VMPortScannerSync.process_vm, vm) for vm in vms]
        # report results in order
        for future in as_completed(futures):
            value = future.result()
            output.append(value)

        return output

    @staticmethod
    def run(tenants):
        start_time = time.time()
        workers = os.cpu_count()
        if 'sched_getaffinity' in dir(os):
            workers = len(os.sched_getaffinity(0))
        print(f'Cpus {workers}')
        # pool = ProcessPoolExecutor(max_workers=workers)
        # pool = ThreadPoolExecutor(max_workers=workers)

        netbox_vms = VMPortScannerSync.get_vm_by_tenant(tenants)
        partition_vm = math.ceil(len(netbox_vms) / workers)
        list_vms = []
        for i in range(0, workers):
            offset = i * partition_vm
            offset1 = ((i + 1) * partition_vm)
            ports_subset = netbox_vms[offset:offset1]
            list_vms.append(ports_subset)

        result = VMPortScannerSync.run_bulk([netbox_vms[0]])
        # for vms_subset in list_vms:
        #     value = VMPortScannerSync.run_bulk(vms_subset)
        #     if value is not None:
        #         result = result + value
        # futures = [pool.submit(VMPortScannerSync.run_bulk(vms_subset)) for vms_subset in list_vms]
        # for future in as_completed(futures):
        #     value = future.result()
        #     if value is not None:
        #         result = result + value
        print(result)

        # for i in netbox_vms:
        #     if i.name == 'E1-cpanel.edgeuno.com':
        #         vm = i
        #         break
        # if vm:
        #     result = VMPortScannerSync.run_bulk([vm])
        #     print(result)
        # for i in netbox_vms:
        #     if i.name == 'E1-cpanel.edgeuno.com':
        #         vm = i
        #         break
        # if vm:
        #     result = VMPortScannerSync.process_vm(vm)
        #     print(result)

        print("---Total run time %s seconds ---" % (time.time() - start_time))
