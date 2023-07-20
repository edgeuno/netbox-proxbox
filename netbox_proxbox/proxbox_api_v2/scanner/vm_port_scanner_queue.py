import math
import time
import os
import json
import random
from dataclasses import dataclass, field
from socket import AF_INET, AF_INET6
from socket import SOCK_STREAM
from socket import socket
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor, Future
from typing import List, Tuple
import resource

from virtualization.models import VirtualMachine, VMInterface
from ipam.models import Service

resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))

file_path = str(os.path.dirname(os.path.realpath(__file__))) + "/../ports.json"
with open(file_path) as config_file:
    file_contents = config_file.read()

if file_contents is None:
    raise Exception(f"No contents were found at the path {file_path}")

mapped_ports = json.loads(file_contents)


@dataclass
class VMPortScannerQueue:
    tenants: List[str] = None
    initial_ports: List[int] = field(default_factory=(lambda: [22022]))
    # Internal variables
    _ports: List[int] = field(default_factory=(lambda: []))
    _preferred_ports: List[int] = field(default_factory=(lambda: []))
    _netbox_vms: List[VirtualMachine] = field(default_factory=(lambda: []))
    _run_service_queue: bool = False
    _service_queue: List[str] = field(default_factory=(lambda: []))
    _service_queue_thread: Future[None] = None
    _port_thread_max_size: int = 60000
    _max_parallel_ports: int = 100
    _ip_list: List[Tuple] = field(default_factory=(lambda: []))
    _open_port_to_process: List[tuple] = field(default_factory=(lambda: []))
    _services: list[Tuple] = field(default_factory=(lambda: []))
    _drain_service_queue: bool = False
    _tracker_print_waiting: int = 0

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

    def define_ports(self):
        self._ports = [i for i in range(1024, 65535)]
        # self._ports = [i for i in range(1024, 1500)]
        self._preferred_ports = [i for i in range(1, 1024)]
        for p in self.initial_ports:
            self._preferred_ports.insert(0, p)
            try:
                i = self._ports.index(p)
                self._ports.pop(i)
            except ValueError:
                continue
        random.shuffle(self._ports)
        if len(self._preferred_ports) > 1:
            self._ports = self._preferred_ports + self._ports

        return self._ports

    def get_vm_by_tenant(self):
        netbox_vms = []
        for i in self.tenants:
            netbox_vms1 = [i for i in VirtualMachine.objects.filter(tenant__name=i)]
            netbox_vms = netbox_vms + netbox_vms1
        return netbox_vms

    def cancel_service_queue(self):
        self._run_service_queue = False

    @staticmethod
    def set_service_to_vm(value):
        port, port_type, port_map, host, vm, ip = value
        print(f'Processing service {vm} - {ip} - {port}')
        service = Service.objects.filter(virtual_machine_id=vm.id, ports__contains=[port],
                                         ipaddresses=ip.id, protocol=port_type).first()
        if service is None:
            service = Service(
                virtual_machine=vm,
                virtual_machine_id=vm.id,
                name=port_map.get("name"),
                protocol=port_type,
                ports=[port],
            )
            service.save()

        service.ipaddresses.add(ip)
        service.name = port_map.get("name")
        service.description = f'> {host}:{port} [OPEN] -> {port_map.get("name")}: {port_map.get("description")}'
        service.save()
        print(f'Service:{service} - {port} saved ...')
        return (vm, ip, service)

    def _process_service_queue(self):
        print("Running queue")
        while self._run_service_queue:
            if self._open_port_to_process is None or len(self._open_port_to_process) < 1:
                if self._drain_service_queue:
                    self._run_service_queue = False
                    break
                if (self._tracker_print_waiting % 40) == 0:
                    print('Waiting for services ...')
                self._tracker_print_waiting = (self._tracker_print_waiting + 1) % 40
                time.sleep(0.1)
                continue
            value = self._open_port_to_process.pop(0)
            service = self.set_service_to_vm(value)
            self._services.append(service)
        return 'Finish service queue'

    def _init_queue_for_service(self):
        self._run_service_queue = True
        executor = ThreadPoolExecutor(max_workers=1)
        self._service_queue_thread = executor.submit(self._process_service_queue)
        return self._service_queue_thread

    @staticmethod
    def get_ips_for_vm(vm):
        interfaces = [i for i in vm.interfaces.all()]
        ips = []
        for i in interfaces:
            tmp = [j for j in i.ip_addresses.all()]
            ips = ips + tmp
        return ips

    def _process_vm(self, vm):
        print(f'Start processing {vm}')
        ips = self.get_ips_for_vm(vm)
        if ips is None or len(ips) < 1:
            return vm
        for ip in ips:
            self._ip_list.append((vm, ip))
        print(f'Finish processing {vm}')
        return self._ip_list

    def add_port_to_process_service(self, value):
        if not self._drain_service_queue:
            self._open_port_to_process.append(value)
        return value

    def process_port(self, pack):
        vm, ip, port = pack
        host = str(ip.address.ip)
        # print(f'Processing {host}-{port}')
        is_open = self.test_port_number(host, port, 4)
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
            value = (port, port_type, port_map, host, vm, ip)
            self.add_port_to_process_service(value)
            return value
        return None

    def process_ip_ports(self, ports):
        consolidated_list = []
        for port in ports:
            for value in self._ip_list:
                vm, ip = value
                consolidated_list.append((vm, ip, port))

        random.shuffle(consolidated_list)
        pages = math.ceil(len(consolidated_list) / self._port_thread_max_size)
        for page in range(0, pages):
            l_offset = page * self._port_thread_max_size
            r_offset = ((page + 1) * self._port_thread_max_size)
            subset = consolidated_list[l_offset:r_offset]
            print(f'\n\nProcessing subset: {l_offset}:{r_offset}\n\n')
            executor = ThreadPoolExecutor(max_workers=len(subset))
            futures = [executor.submit(self.process_port, value) for value in subset]

            for future in as_completed(futures):
                r = future.result()
            executor.shutdown()
        return True

    @staticmethod
    def remove_services_from_vm(vm, services):
        nb_services = vm.services.all()
        to_remove = []
        output = []

        for nbs in nb_services:
            is_to_delete = True
            for s in services:
                if s.id == nbs.id:
                    is_to_delete = False
                    break
            if is_to_delete:
                to_remove.append(nbs)
            else:
                output.append(nbs)
        for d in to_remove:
            print(f'Clearing service {d}')
            vm.services.remove(d)
            d.delete()

        return output

    def clear_vm_ports(self):
        print("Clearing Services ...")
        for value in self._services:
            vm, ip, service = value
            vm.services.add(service)
            vm.save()

        for nb_vm in self._netbox_vms:
            vm_services = []
            for s in self._services:
                vm, ip, service = s
                if vm.id == nb_vm.id:
                    vm_services.append(service)
            print(f'Removing closed ports for {vm} - {vm_services}')
            self.remove_services_from_vm(nb_vm, vm_services)

    def run(self):
        start_time = time.time()
        # Get the virtual machines to be process
        self._netbox_vms = self.get_vm_by_tenant()
        # Define the ips for the virtual machines to be process
        for vm in self._netbox_vms:
            self._process_vm(vm)
        # define the ports to analise
        self.define_ports()
        # Init the service queue
        self._init_queue_for_service()
        pages = math.ceil(len(self._ports) / self._max_parallel_ports)
        for page in range(0, pages):
            l_offset = page * self._max_parallel_ports
            r_offset = ((page + 1) * self._max_parallel_ports)
            ports_subset = self._ports[l_offset:r_offset]
            print(f'\n\nPORTS {l_offset}:{r_offset}\n\n')
            self.process_ip_ports(ports_subset)

        self._drain_service_queue = True
        result = self._service_queue_thread.result()
        print(result)
        self.clear_vm_ports()
        print("---Total run time %s seconds ---" % (time.time() - start_time))
