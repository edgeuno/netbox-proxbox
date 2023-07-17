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

import resource

resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))



class VMPortScannerSyncSinglePort:
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

        is_open = VMPortScannerSyncSinglePort.test_port_number(host, port, timeout)

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
            service = VMPortScannerSyncSinglePort.set_service_to_vm(vm, ip, open_port)
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
            value = VMPortScannerSyncSinglePort.get_ips_for_vm(vm)
            ips = ips + value
        if ips is None or len(ips) < 1:
            return vms

        for value in ips:
            r = VMPortScannerSyncSinglePort.get_ports_for_ip(value)
            ports_to_scan = ports_to_scan + r

        ports_to_scan = VMPortScannerSyncSinglePort.random_list(ports_to_scan)
        limit = 1000
        executor = ThreadPoolExecutor(max_workers=limit)
        futures = [executor.submit(VMPortScannerSyncSinglePort.get_service_from_port, port, 4) for port in ports_to_scan]

        for future in as_completed(futures):
            r = future.result()
            if r is not None:
                r_vm, r_ip, r_port, r_service = r
                output.append((r_vm, r_service))
        executor.shutdown()
        # total = len(ports_to_scan)
        # pages = math.ceil( total / limit)
        #
        # #list_ports = []
        # for i in range(0, pages):
        #     offset = i * limit
        #     offset1 = ((i + 1) * limit)
        #     print(f'Processing items: {offset}:{offset1}  of {total}')
        #     ports_subset = ports_to_scan[offset:offset1]
        #     #list_ports.append(ports_subset)
        #
        #     executor = ThreadPoolExecutor(max_workers=limit)
        #     futures = [executor.submit(VMPortScannerSyncSinglePort.get_service_from_port, port, 4) for port in ports_subset]
        #
        #     for future in as_completed(futures):
        #         r = future.result()
        #         if r is not None:
        #             r_vm, r_ip, r_port, r_service = r
        #             output.append((r_vm, r_service))
        #     executor.shutdown()
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

        netbox_vms = VMPortScannerSyncSinglePort.get_vm_by_tenant(tenants)

        for i in netbox_vms:
            if i.name == 'E1-cpanel.edgeuno.com':
                vm = i
                break
        if vm:
            result = VMPortScannerSyncSinglePort.process_vms([vm, netbox_vms[0]])
            print(result)
        # for i in netbox_vms:
        #     if i.name == 'E1-cpanel.edgeuno.com':
        #         vm = i
        #         break
        # if vm:
        #     result = VMPortScannerSyncSinglePort.process_vm(vm)
        #     print(result)

        print("---Total run time %s seconds ---" % (time.time() - start_time))
