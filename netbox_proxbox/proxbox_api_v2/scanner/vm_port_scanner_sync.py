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

file_path = str(os.path.dirname(os.path.realpath(__file__))) + "/../ports.json"
with open(file_path) as config_file:
    file_contents = config_file.read()

if file_contents is None:
    raise Exception(f"No contents were found at the path {file_path}")

mapped_ports = json.loads(file_contents)

import resource

resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))


class VMPortScannerSync:

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
        # futures = [executor.submit(VMPortScannerSync.get_services_from_ports, vm, ip, 1000) for ip in ips]
        futures = [executor.submit(VMPortScannerSync.process_ip, vm, ip) for ip in ips]

        for future in as_completed(futures):
            r = future.result()
            if r is not None and len(r) > 0:
                services = services + r

        executor.shutdown()

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
        executor.shutdown()
        return output

    @staticmethod
    def run(tenants):
        start_time = time.time()
        workers = os.cpu_count()
        if 'sched_getaffinity' in dir(os):
            workers = len(os.sched_getaffinity(0))
        print(f'Cpus {workers}')
        pool = ProcessPoolExecutor(max_workers=workers)
        # pool = ThreadPoolExecutor(max_workers=workers)

        netbox_vms = VMPortScannerSync.get_vm_by_tenant(tenants)
        pages = math.ceil(len(netbox_vms) / workers)
        list_vms = []
        for i in range(0, workers):
            offset = i * pages
            offset1 = ((i + 1) * pages)
            ports_subset = netbox_vms[offset:offset1]
            list_vms.append(ports_subset)

        # result = VMPortScannerSync.run_bulk([netbox_vms[0]])
        result = []
        for vms_subset in list_vms:
            value = VMPortScannerSync.run_bulk(vms_subset)
            if value is not None:
                print(f'Finish list ...')
                result = result + value
        # futures = [pool.submit(VMPortScannerSync.run_bulk(vms_subset)) for vms_subset in list_vms]
        # for future in as_completed(futures):
        #     value = future.result()
        #     if value is not None:
        #         result = result + value
        # pool.shutdown()
        print(result)
        # for i in netbox_vms:
        #     if i.name == 'E1-cpanel.edgeuno.com':
        #         vm = i
        #         break
        # if vm:
        #     result = VMPortScannerSync.run_bulk([vm, netbox_vms[0]])
        #     print(result)
        # for i in netbox_vms:
        #     if i.name == 'E1-cpanel.edgeuno.com':
        #         vm = i
        #         break
        # if vm:
        #     result = VMPortScannerSync.process_vm(vm)
        #     print(result)

        print("---Total run time %s seconds ---" % (time.time() - start_time))
