from django.template.defaultfilters import slugify

try:
    from virtualization.models import VirtualMachine, VMInterface
    from tenancy.models import Tenant, TenantGroup, Contact, ContactRole, ContactAssignment
    from ipam.models import IPAddress
    from django.contrib.contenttypes.models import ContentType
    from dcim.choices import InterfaceTypeChoices

    from .device_role import get_set_role
    from ..proxbox_api.plugins_config import (
        # PROXMOX,
        # PROXMOX_PORT,
        # PROXMOX_USER,
        # PROXMOX_PASSWORD,
        # PROXMOX_SSL,
        NETBOX_TENANT_NAME,
        NETBOX_TENANT_REGEX_VALIDATOR,
        NETBOX_VM_ROLE_ID,
        NETBOX_VM_ROLE_NAME,
    )

    from .cluster import get_set_cluster
    from .extras import tag, custom_tag
    import re


except Exception as e:
    print(e)
    raise e

ipv4_regex = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(\/\d{1,3})?"
ipv6_regex = r"([a-zA-Z0-9]{1,4}(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?(:[a-zA-Z0-9]{0,4})?:([a-zA-Z0-9]{0,4})?:([a-zA-Z0-9]{0,4})?(\.\d{1,3}\.\d{1,3}\.\d{1,3})?(\/\d{1,3})?)"


def get_nb_vm_by_data(cluster_name, vmid, node):
    # print('[OK] Getting getting vm from netbox for {} , {}, {}'.format(cluster_name, vmid, node))
    netbox_vm = VirtualMachine.objects.filter(cluster__name=cluster_name, custom_field_data__proxmox_id=vmid,
                                              custom_field_data__proxmox_node=node).first()
    # netbox_vm = None
    # for vm in netbox_vm_all:
    #     netbox_vm = vm
    #     break
    return netbox_vm


def get_nb_vm_by_name(cluster_name, proxmox_vm_name):
    netbox_vm = None
    netbox_vm = VirtualMachine.objects.filter(cluster__name=cluster_name, name=proxmox_vm_name).first()
    # for vm in netbox_vm_all:
    #     netbox_vm = vm
    #     break
    return netbox_vm


def get_nb_by_(cluster_name, vmid, node, proxmox_vm_name):
    netbox_vm = get_nb_vm_by_name(cluster_name, proxmox_vm_name)
    if netbox_vm == None:
        netbox_vm = get_nb_vm_by_data(cluster_name, vmid, node)
    return netbox_vm


#
# virtualization.virtual_machines
#
# def get_virtual_machine_data(proxmox, proxmox_vm):
#     # Create json with basic VM/CT information
#     vm_json = {}
#
#     if proxmox_vm['status'] == 'running':
#         vm_json["status"] = 'active'
#     elif proxmox_vm == 'stopped':
#         vm_json["status"] = 'offline'
#
#     cluster = get_set_cluster(proxmox)
#     vm_json["name"] = proxmox_vm['name']
#     # vm_json["status"] = 'active'
#     vm_json["cluster_id"] = cluster.id
#     # vm_json["cluster"] = cluster
#     # vm_json["role"] = extras.role(role_id=NETBOX_VM_ROLE_ID).id
#     vm_json["tags"] = [tag().id]
#     return vm_json


def virtual_machine(proxmox, proxmox_vm):
    # Create VM/CT with json 'vm_json'
    # vm_json = get_virtual_machine_data(proxmox, proxmox_vm)
    try:
        status = 'offline'
        if proxmox_vm['status'] == 'running':
            status = 'active'
        elif proxmox_vm == 'stopped':
            status = 'offline'

        cluster = get_set_cluster(proxmox)
        netbox_obj = VirtualMachine(name=proxmox_vm['name'])
        netbox_obj.status = status
        netbox_obj.cluster_id = cluster.id
        netbox_obj.cluster = cluster

        netbox_obj.save()

        c_tag = tag()
        netbox_obj.tags.add(c_tag)
        print("VIRTUAL MACHINE CREATED")
        print(netbox_obj)

    except Exception as e:
        print("Error: virtual.proxbox.create.virtual_machine - {}".format(e))
        print("[virtual.proxbox.create.virtual_machine] Creation of VM/CT failed.")
        print(e)
        netbox_obj = None

    else:
        return netbox_obj

    # In case nothing works, returns error
    netbox_obj = None
    return netbox_obj


def base_status(netbox_vm, proxmox_vm):
    # False = status not changed on Netbox
    # True  = status changed on Netbox
    status_updated = False

    # [ running, stopped ]
    proxmox_status = proxmox_vm['status']

    # [ offline, active, planned, staged, failed, decommissioning ]
    netbox_status = netbox_vm.status

    if (proxmox_status == 'running' and netbox_status == 'active') or (
            proxmox_status == 'stopped' and netbox_status == 'offline'):
        # Status not updated
        status_updated = False

    # Change status to active on Netbox if it's offline
    elif proxmox_status == 'stopped' and netbox_status == 'active':
        netbox_vm.status = 'offline'
        # Status updated
        status_updated = True

    # Change status to offline on Netbox if it's active
    elif proxmox_status == 'running' and netbox_status == 'offline':
        netbox_vm.status = 'active'
        # Status updated
        status_updated = True

    # Status not expected
    else:
        # Status doesn't need to change
        status_updated = False

    return status_updated, netbox_vm


def base_local_context_data(netbox_vm, proxmox_vm, PROXMOX, PROXMOX_PORT, domain=None):
    current_local_context = netbox_vm.local_context_data

    proxmox_values = {}

    # Add and change values from Proxmox
    proxmox_values["name"] = proxmox_vm["name"]
    proxmox_values["url"] = "https://{}:{}".format(PROXMOX, PROXMOX_PORT)  # URL
    proxmox_values["id"] = proxmox_vm["vmid"]  # VM ID
    proxmox_values["node"] = proxmox_vm["node"]
    proxmox_values["type"] = proxmox_vm["type"]
    proxmox_values["vm_url"] = 'https://{}:{}/#v1:0:={}%2F{}'.format(PROXMOX, PROXMOX_PORT, proxmox_vm["type"],
                                                                     proxmox_vm["vmid"])
    if domain:
        proxmox_values["domain"] = '{}'.format(domain)

    maxmem = int(int(proxmox_vm["maxmem"]) / 1000000000)  # Convert bytes to gigabytes
    proxmox_values["memory"] = "{} {}".format(maxmem, 'GB')  # Add the 'GB' unit of measurement

    maxdisk = int(int(proxmox_vm["maxdisk"]) / 1000000000)  # Convert bytes to gigabytes
    proxmox_values["disk"] = "{} {}".format(maxdisk, 'GB')  # Add the 'GB' unit of measurement

    proxmox_values["vcpu"] = proxmox_vm["maxcpu"]  # Add the 'GB' unit of measurement

    # Verify if 'local_context' is empty and if true, creates initial values.
    if current_local_context == None:
        netbox_vm.local_context_data = {"proxmox": proxmox_values}
        return True, netbox_vm

    # Compare current Netbox values with Porxmox values
    elif current_local_context.get('proxmox') != proxmox_values:
        # Update 'proxmox' key on 'local_context_data'
        current_local_context.update(proxmox=proxmox_values)

        netbox_vm.local_context_data = current_local_context
        return True, netbox_vm

    # If 'local_context_data' already updated
    else:
        return False, netbox_vm

    return False, netbox_vm


def base_resources(netbox_vm, proxmox_vm):
    # Save values from Proxmox
    vcpus = float(proxmox_vm["maxcpu"])

    # Convert bytes to megabytes and then convert float to integer
    memory_Mb = proxmox_vm["maxmem"]
    memory_Mb = int(memory_Mb / 1048576)

    # Convert bytes to gigabytes and then convert float to integer
    disk_Gb = proxmox_vm["maxdisk"]
    disk_Gb = int(disk_Gb / 1000000000)

    # JSON with new resources info
    new_resources_json = {}

    # Compare VCPU
    if netbox_vm.vcpus != None:
        # Convert Netbox VCPUs to float, since it is coming as string from Netbox
        netbox_vm.vcpus = float(netbox_vm.vcpus)

        if netbox_vm.vcpus != vcpus:
            netbox_vm.vcpus = vcpus

    elif netbox_vm.vcpus == None:
        netbox_vm.vcpus = vcpus

    # Compare Memory
    if netbox_vm.memory != None:
        if netbox_vm.memory != memory_Mb:
            netbox_vm.memory = memory_Mb

    elif netbox_vm.memory == None:
        netbox_vm.memory = memory_Mb

    # Compare Disk
    if netbox_vm.disk != None:
        if netbox_vm.disk != disk_Gb:
            netbox_vm.disk = disk_Gb

    elif netbox_vm.disk == None:
        netbox_vm.disk = disk_Gb

    return False, netbox_vm


def get_ip(test_str):
    # print('[OK] parsing ipv4. -> {}'.format(test_str))
    regex = r"ip=" + ipv4_regex
    # test_str = "name=eth0,bridge=vmbr504,firewall=1,gw=172.16.19.1,hwaddr=5A:70:3F:05:0D:AC,ip=172.16.19.251/24,type=veth"
    try:
        matches = re.finditer(regex, test_str, re.MULTILINE)
        it = matches.__next__()
        ip = it.group().replace('ip=', '').strip()
        # print('[OK] Parse. -> {}'.format(ip))
        return ip
    except Exception as e:
        # print("Error: get_ip - {}".format(e))
        return None


def get_ipv6(test_str):
    # ipv6 regex
    # print('[OK] parsing ipv6. -> {}'.format(test_str))
    regex = r"ip6=" + ipv6_regex

    # test_str = "name=eth0,bridge=vmbr502,gw=172.16.17.1,gw6=fc00:16:17::1,hwaddr=CA:F3:00:D6:31:2A,ip=172.16.17.203/24,ip6=2001:db8:3:4::192.0.2.33/64,type=veth"
    try:
        matches = re.finditer(regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        ip = it.group().replace('ip6=', '').strip()
        # print('[OK] Parse. -> {}'.format(ip))
        return ip
    except Exception as e:
        # print("Error: get_ipv6 - {}".format(e))
        return None


def handle_ip_already_set(netbox_vm, netbox_ip, family=4):
    netbox_vm_with_ip = None
    # Check for ipv4 or ipv6 if there is a vm with the same ip
    if family == 4:
        netbox_vm_with_ip = VirtualMachine.objects.filter(primary_ip4_id=netbox_ip.id).first()
    else:
        netbox_vm_with_ip = VirtualMachine.objects.filter(primary_ip6_id=netbox_ip.id).first()
    # If there is not vm with the ip or is the same as the incoming vm
    if netbox_vm_with_ip is None or netbox_vm.id == netbox_vm_with_ip.id:
        return True, netbox_vm, netbox_ip
    # If the netbox_vm is not the same as the netbox_vm_with_ip then we are going to set up a tag and a comment
    # with the ip and the vm id that has the same ip
    name = 'Repeated Ip'
    tag_description = "No description"
    color = 'ff3c3f'
    repeated_tag = custom_tag(name, slugify(name), tag_description, color)
    if repeated_tag:
        netbox_vm.tags.add(repeated_tag)
    netbox_vm.comments = netbox_vm.comments + '\nDuplicated ip - Name: {} - id {}'.format(netbox_vm_with_ip.name,
                                                                                          netbox_vm_with_ip.id)
    netbox_vm.save()
    return False, netbox_vm, None


def set_ipv(netbox_vm, vm_interface, ip, family=4):
    if ip is not None:
        # Search the ip in netbox and get the content type for virtualization
        netbox_ip = IPAddress.objects.filter(address=ip).first()
        content_type = ContentType.objects.filter(app_label="virtualization", model="vminterface").first()
        if netbox_ip is None:
            # Create the ip address and link it to the interface previously created
            netbox_ip = IPAddress(address=ip)
            netbox_ip.assigned_object_type = content_type
            netbox_ip.assigned_object_id = vm_interface.id
            netbox_ip.assigned_object = vm_interface
            netbox_ip.save()

            # netbox_vm.primary_ip_id = netbox_ip.id
            # netbox_vm.primary_ip4 = netbox_ip
            # netbox_vm.save()
        r, netbox_vm, netbox_ip = handle_ip_already_set(netbox_vm, netbox_ip, family)
        if netbox_ip:
            # Associate the ip address to the interface
            netbox_ip.assigned_object_type = content_type
            netbox_ip.assigned_object_id = vm_interface.id
            netbox_ip.assigned_object = vm_interface
            netbox_ip.save()

            if family == 4:
                netbox_vm.primary_ip4 = netbox_ip
                netbox_vm.primary_ip4_id = netbox_ip.id
            else:
                netbox_vm.primary_ip6 = netbox_ip
                netbox_vm.primary_ip6_id = netbox_ip.id

            netbox_vm.primary_ip_id = netbox_ip.id

            # netbox_vm.save()
    return netbox_vm


def set_ipv4(netbox_vm, vm_interface, ipv4):
    return set_ipv(netbox_vm, vm_interface, ipv4, 4)


def set_ipv6(netbox_vm, vm_interface, ipv6):
    return set_ipv(netbox_vm, vm_interface, ipv6, 6)


def get_main_ip(test_str):
    ipv4 = None
    ipv6 = None

    try:
        # print('[OK] Parsing main ip for ipv4 -> {}').format(test_str)
        rgx = r"main(\s)?ip:(\s)?"
        matches = re.finditer(rgx + ipv4_regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        ipv4 = it.group().lower() \
            .replace('mainip:', '') \
            .replace('mainip: ', '') \
            .replace('main ip:', '') \
            .replace('main ip: ', '') \
            .strip()
        ipv4 = (re.sub(rgx, '', ipv4)).strip()
    except Exception as e:
        # print("Error: get_main_ip-ip4 - {}".format(e))
        pass
    try:
        # print('[OK] Parsing main ip for ipv6')
        rgx = r"main(\s)?ip:(\s)?"
        matches = re.finditer(rgx + ipv6_regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        ipv6 = it.group().lower() \
            .replace('mainip:', '') \
            .replace('mainip: ', '') \
            .replace('main ip:', '') \
            .replace('main ip: ', '') \
            .strip()
        ipv6 = (re.sub(rgx, '', ipv6)).strip()
    except Exception as e:
        # print("Error: get_main_ip-ip6 - {}".format(e))
        pass
    try:
        if ipv4 is None:
            # print('[OK] Parsing ip address allocation for ipv4')
            rgx = r"ip(\s)?address(\s)?allocation:(\s)?"
            matches = re.finditer(rgx + ipv4_regex, test_str, re.MULTILINE | re.IGNORECASE)
            it = matches.__next__()
            ipv4 = it.group().lower() \
                .replace('ipaddressallocation:', '') \
                .replace('ipaddressallocation :', '') \
                .replace('ip addressallocation:', '') \
                .replace('ip addressallocation :', '') \
                .replace('ip address allocation:', '') \
                .replace('ip address allocation :', '') \
                .strip()
            ipv4 = (re.sub(rgx, '', ipv4)).strip()
    except Exception as e:
        # print("Error: get_main_ip-ip4-location - {}".format(e))
        pass
    try:
        if ipv6 is None:
            # print('[OK] Parsing ip address allocation for ipv6')
            rgx = r"ip(\s)?address(\s)?allocation:(\s)?"
            matches = re.finditer(rgx + ipv6_regex, test_str, re.MULTILINE | re.IGNORECASE)
            it = matches.__next__()
            ipv6 = it.group().lower() \
                .replace('ipaddressallocation:', '') \
                .replace('ipaddressallocation :', '') \
                .replace('ip addressallocation:', '') \
                .replace('ip addressallocation :', '') \
                .replace('ip address allocation:', '') \
                .replace('ip address allocation :', '') \
                .strip()
            ipv6 = (re.sub(rgx, '', ipv6)).strip()
    except Exception as e:
        # print("Error: get_main_ip-ip6-allocation - {}".format(e))
        pass
    return ipv4, ipv6


def base_add_ip(proxmox, netbox_vm, proxmox_vm):
    vm_type = proxmox_vm['type']
    vmid = proxmox_vm['vmid']
    node = proxmox_vm['node']
    config = None
    network_str = None
    ipv4 = None
    ipv6 = None
    try:
        if vm_type == 'qemu':
            config = proxmox.nodes(node).qemu(vmid).config.get()
            # print('[OK] Got Configuration for quemu. -> {}'.format(vmid))
        if vm_type == 'lxc':
            config = proxmox.nodes(node).lxc(vmid).config.get()
            # print('[OK] Got Configuration for lxc. -> {}'.format(vmid))
    except  Exception as e:
        print("Error: base_add_ip-1 - {}".format(e))
        print(e)
        config = None

    if config is None:
        return False, netbox_vm

    try:
        if vm_type == 'qemu':
            if 'ipconfig0' in config:
                network_str = config['ipconfig0']
            elif 'net0' in config:
                network_str = config['net0']
        if vm_type == 'lxc':
            if 'net0' in config:
                network_str = config['net0']
            elif 'ipconfig0' in config:
                network_str = config['ipconfig0']
    except  Exception as e:
        print("Error: base_add_ip-2 - {}".format(e))
        network_str = None

    try:
        if network_str is not None:
            ipv4 = get_ip(network_str)
            ipv6 = get_ipv6(network_str)
            if ipv4 is None and ipv6 is None:
                # print('[OK] ipv4 or ipv6 not found searching in the observations for . -> {}'.format(vmid))
                if 'description' in config:
                    ipv4, ipv6 = get_main_ip(config['description'])
            if not (ipv4 is None and ipv6 is None):
                try:
                    # Create the interface if it doesn't exist
                    vm_interface = get_set_interface('eth0', netbox_vm)
                    netbox_vm = set_ipv6(netbox_vm, vm_interface, ipv6)
                    netbox_vm = set_ipv4(netbox_vm, vm_interface, ipv4)
                except Exception as e:
                    print("Error: base_add_ip-3 - {}".format(e))
                    print(e)
                netbox_vm.save()
    except Exception as e:
        print("Error: base_add_ip-4 - {}".format(e))
        print(e)
    return True, netbox_vm


def get_set_tenant_group(tenant, netbox_vm):
    tags_name = []
    tags = netbox_vm.tags.all()
    tenant_group_name = 'Customers'
    for c_tag in tags:
        if 'proxbox' == c_tag.name.lower():
            pass
        else:
            tags_name.append(c_tag.name.lower())
    if NETBOX_TENANT_NAME is not None and NETBOX_TENANT_NAME.lower() in tags_name:
        tenant_group_name = NETBOX_TENANT_NAME
    tenant_group = TenantGroup.objects.filter(name=tenant_group_name).first()
    if tenant_group is None:
        tenant_group = TenantGroup(
            name=tenant_group_name,
            slug=slugify(tenant_group_name)
        )
        tenant_group.save()
    tenant.group_id = tenant_group.id
    tenant.group = tenant_group
    tenant.save()
    return tenant


def client_tenant_parser(test_str):
    client = None
    tenant_name = None
    client_regex = r"client(\s)?(:)?.*(id)?:"
    try:
        matches = re.finditer(client_regex, test_str, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        client = it.group() \
            .replace('client:', '') \
            .replace('client :', '') \
            .replace('Client:', '') \
            .replace('Client :', '') \
            .replace('id:', '') \
            .replace('id :', '') \
            .replace('(id :', '') \
            .replace('(ID:', '') \
            .replace('Id:', '') \
            .replace('Id :', '') \
            .replace('(Id :', '') \
            .replace('(ID :', '') \
            .strip()
        sub_str_regex = r"\(.*\)"
        m_result = None
        try:
            m_result = re.finditer(sub_str_regex, client, re.MULTILINE | re.IGNORECASE).__next__().group().strip()
        except Exception as e:
            # print("Error: client_tenant_parser - {}".format(e))
            # print(e)
            pass
        if m_result:
            if m_result.replace('(', '').replace(')', '').strip():
                tenant_name = m_result.replace('(', '').replace(')', '').strip()
            client = client.replace(m_result, '').strip()
        else:
            tenant_name = client
        # print('[OK] Tenant parse. -> {}'.format(client))
    except Exception as e:
        # print("Error: client_tenant_parser-all - {}".format(e))
        pass
    return tenant_name, client


def contact_parse_set(test_str, name):
    contact = None
    contact_role = None
    try:
        # print('[OK] Parsing contact from. -> {}'.format(test_str))
        contact_email = None
        contact_regex = r"email(\s)?(:)?(\s)?\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+"
        try:
            matches = re.finditer(contact_regex, test_str, re.MULTILINE | re.IGNORECASE)
            it = matches.__next__()
            contact_email = it.group() \
                .replace('email:', '') \
                .replace('email :', '') \
                .replace('Email:', '') \
                .replace('Email :', '') \
                .strip()
            # print('[OK] Contact email parsed. -> {}'.format(contact_email))
        except Exception as e:
            # print("Error: contact_parse_set - {}".format(e))
            # print(e)
            pass
        if contact_email is None:
            return None, None

        contact = Contact.objects.filter(email=contact_email).first()
        if contact is None:
            # print('[OK] Creating contact for {} with email {}'.format(name, contact_email))
            # new_contact = {"name": name, "email": contact_email}
            contact = Contact(
                name=name,
                email=contact_email
            )
            contact.save()

        contact_role = ContactRole.objects.filter(name="vm").first()
        if contact_role is None:
            # print('[OK] Creating role. -> {}'.format("vm"))
            contact_role = ContactRole(
                name="vm",
                slug=slugify("vm")
            )
            contact_role.save()
    except Exception as e:
        print("Error: contact_parse_set - {}".format(e))
        print(e)

    return contact, contact_role


def set_assign_contact(test_str, name, object_id, content_type):
    if content_type is None:
        content_type = content_type = ContentType.objects.filter(app_label="tenancy", model="tenant").first()

    contact = None
    contact_role = None
    contact_assigment = None
    try:
        contact, contact_role = contact_parse_set(test_str, name)
        if not (contact and contact_role):
            return contact, contact_role, contact_assigment
        contact_assigment = ContactAssignment.objects.filter(
            object_id=object_id,
            contact_id=contact.id,
            content_type_id=content_type.id,
            role_id=contact_role.id
        ).first()
        if contact_assigment is None:
            # print('[OK] Assigning contact {} to tenant {}'.format(contact.name, name))

            contact_assigment = ContactAssignment(
                object_id=object_id,
                contact=contact,
                content_type_id=content_type.id,
                contact_id=contact.id,
                role=contact_role,
                role_id=contact_role.id,
                priority="primary"
            )
            contact_assigment.save()
            # print('[OK] Contact assigned {} to tenant {}'.format(contact.name, name))
            # assign_contact_to_tenant(tenant, contact, contact_role, content_type)
    except Exception as e:
        print("Error: set_assign_contact - {}".format(e))
        print(e)
    return contact, contact_role, contact_assigment


def get_set_tenant_from_configuration(test_str):
    tenant_name, client = client_tenant_parser(test_str)
    if tenant_name is None:
        return None
    nb_tenant = Tenant.objects.filter(name=tenant_name).first()

    if nb_tenant is None:
        nb_tenant = Tenant.objects.filter(slug=slugify(tenant_name)).first()

    if nb_tenant is None:
        try:
            nb_tenant = Tenant(
                name=tenant_name,
                slug=slugify(tenant_name)
            )
            nb_tenant.save()
        except Exception as e:
            print(e)
            raise e
    content_type = ContentType.objects.filter(app_label="tenancy", model="tenant").first()
    # set_assign_contact(test_str, client, nb_tenant.id, 'tenancy.tenant')
    set_assign_contact(test_str, client, nb_tenant.id, content_type)
    return nb_tenant


#


def set_tenant(netbox_vm, observation):
    # print('[OK] Getting tenant from. -> {}'.format(observation))
    tenant = get_set_tenant_from_configuration(observation)
    if tenant is None:
        return netbox_vm
    tenant = get_set_tenant_group(tenant, netbox_vm)

    netbox_vm.tenant_id = tenant.id
    netbox_vm.tenant = tenant

    netbox_vm.save()

    return netbox_vm


def set_contact_to_vm(test_str, netbox_vm):
    # content_type = 'virtualization.virtualmachine'
    content_type = ContentType.objects.filter(app_label="virtualization", model="virtualmachine").first()
    try:
        # print('[OK] Parsing contact from. -> {}'.format(test_str))
        tenant = netbox_vm.tenant
        tenant_name, client = client_tenant_parser(test_str)
        set_assign_contact(test_str, client, netbox_vm.id, content_type)
        return netbox_vm
    except Exception as e:
        print("Error: set_contact_to_vm - {}".format(e))
        print(e)
        return netbox_vm


def default_tenant(netbox_vm):
    has_string = False
    try:
        rgx = r"" + NETBOX_TENANT_REGEX_VALIDATOR
        matches = re.finditer(rgx, netbox_vm.name, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        it.group().lower().strip()
        has_string = True
    except Exception as e:
        pass
        # print("Error: default_tenant-1 - {}".format(e))
        # print(e)

    if has_string:
        if NETBOX_TENANT_NAME is not None:
            nb_tenant = Tenant.objects.filter(name=NETBOX_TENANT_NAME).first()
            if nb_tenant is None:
                nb_tenant = Tenant(
                    name=NETBOX_TENANT_NAME,
                    slug=slugify(NETBOX_TENANT_NAME)
                )
                nb_tenant.save()
            if nb_tenant is not None:
                nb_tenant = get_set_tenant_group(nb_tenant, netbox_vm)
                netbox_vm.tenant_id = nb_tenant.id
                netbox_vm.tenant = nb_tenant
                netbox_vm.save()

    return netbox_vm


def base_add_configuration(proxmox, netbox_vm, proxmox_vm):
    vm_type = proxmox_vm['type']
    vmid = proxmox_vm['vmid']
    node = proxmox_vm['node']
    config = None
    try:
        if NETBOX_TENANT_NAME is not None:
            netbox_vm = default_tenant(netbox_vm)
    except Exception as e:
        print("Error: base_add_configuration-1 - {}".format(e))
        print(e)
    try:
        if vm_type == 'qemu':
            config = proxmox.nodes(node).qemu(vmid).config.get()
            # print('[OK] Got Configuration for quemu. -> {}'.format(vmid))
        if vm_type == 'lxc':
            config = proxmox.nodes(node).lxc(vmid).config.get()
            # print('[OK] Got Configuration for lxc. -> {}'.format(vmid))
    except Exception as e:
        print("Error: base_add_configuration-2 - {}".format(e))
        print(e)
        config = None

    if config is None:
        return False, netbox_vm

    try:
        if 'description' in config:
            if config['description']:
                netbox_vm.comments = config['description']
            netbox_vm = set_tenant(netbox_vm, config['description'])
            netbox_vm = set_contact_to_vm(config['description'], netbox_vm)
        # else:
        # print('no description')
    except Exception as e:
        print("Error: base_add_configuration-3 - {}".format(e))
        print(e)
    return True, netbox_vm


def update_vm_role(netbox_vm, proxmox_vm):
    vm_type = proxmox_vm['type']
    role_name = NETBOX_VM_ROLE_NAME
    try:
        if vm_type == 'qemu':
            role_name = "VPS"
        if vm_type == 'lxc':
            role_name = "LXC"
    except  Exception as e:
        pass
    role = get_set_role(role_id=NETBOX_VM_ROLE_ID, role_name=role_name)
    netbox_vm.role_id = role.id
    netbox_vm.role = role
    netbox_vm.save()
    return True, netbox_vm


def base_custom_fields(netbox_vm, proxmox_vm):
    try:
        netbox_vm.custom_field_data["proxmox_id"] = proxmox_vm['vmid']
        netbox_vm.custom_field_data["proxmox_node"] = proxmox_vm['node']
        netbox_vm.custom_field_data["proxmox_type"] = proxmox_vm['type']
        return False, netbox_vm
    except Exception as e:
        print(e)
        return netbox_vm


def get_set_interface(name, netbox_node):
    dev_interface = VMInterface.objects.filter(name=name, virtual_machine_id=netbox_node.id).first()
    if dev_interface is None:
        # new_interface_json = {"device_id": netbox_node.id, "name": name, type: InterfaceTypeChoices.TYPE_LAG}
        dev_interface = VMInterface(name=name)
        dev_interface.description = "LAG"
        dev_interface.virtual_machine_id = netbox_node.id
        dev_interface.virtual_machine = netbox_node
        dev_interface.type = InterfaceTypeChoices.TYPE_LAG
        dev_interface.save()

    return dev_interface


def get_set_vm(cluster, proxmox_vm):
    cluster_name = cluster.name
    vm_name = proxmox_vm['name']
    vmid = proxmox_vm['vmid']
    node = proxmox_vm['node']

    netbox_vm = VirtualMachine.objects.filter(cluster__name=cluster_name, name=vm_name).first()
    if netbox_vm is None:
        netbox_vm = VirtualMachine.objects.filter(cluster__name=cluster_name, custom_field_data__proxmox_id=vmid,
                                                  custom_field_data__proxmox_node=node).first()

    status = 'offline'
    if proxmox_vm['status'] == 'running':
        status = 'active'
    elif proxmox_vm == 'stopped':
        status = 'offline'

    if netbox_vm is None:
        try:
            netbox_vm = VirtualMachine(name=vm_name)
            netbox_vm.cluster_id = cluster.id
            netbox_vm.cluster = cluster
            netbox_vm.save()
            print("VIRTUAL MACHINE CREATED")
            print(netbox_vm)

        except Exception as e:
            print("Error: get_set_vm - {}".format(e))
            print("[get_set_vm] Creation of VM/CT failed.")
            print(e)
            netbox_obj = None

    if netbox_vm:
        netbox_vm.status = status
        netbox_vm.cluster_id = cluster.id
        netbox_vm.cluster = cluster
        netbox_vm.save()
        c_tag = tag()
        netbox_vm.tags.add(c_tag)

    return netbox_vm
