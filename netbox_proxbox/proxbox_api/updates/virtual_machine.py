import requests
import json
import re

# PLUGIN_CONFIG variables
from ..plugins_config import (
    PROXMOX,
    PROXMOX_PORT,
    PROXMOX_USER,
    PROXMOX_PASSWORD,
    PROXMOX_SSL,
    NETBOX,
    NETBOX_TOKEN,
    PROXMOX_SESSION as proxmox,
    NETBOX_SESSION as nb,
)

from .. import (
    create,
)


# Update "status" field on Netbox Virtual Machine based on Proxmox information
def status(netbox_vm, proxmox_vm):
    print("[DEBUG] Update 'status' field on Netbox Virtual Machine based on Proxmox information")
    # False = status not changed on Netbox
    # True  = status changed on Netbox
    status_updated = False

    # [ running, stopped ]
    proxmox_status = proxmox_vm['status']

    # [ offline, active, planned, staged, failed, decommissioning ]
    netbox_status = netbox_vm.status.value

    if (proxmox_status == 'running' and netbox_status == 'active') or (
            proxmox_status == 'stopped' and netbox_status == 'offline'):
        # Status not updated
        print("[DEBUG] Status not updated")
        status_updated = False

    # Change status to active on Netbox if it's offline
        print("[DEBUG] Change status to active on Netbox if it's offline")
    elif proxmox_status == 'stopped' and netbox_status == 'active':
        netbox_vm.status.value = 'offline'
        netbox_vm.save()

        # Status updated
        print("[DEBUG] Status updated")
        status_updated = True

    # Change status to offline on Netbox if it's active
        print("[DEBUG] Change status to offline on Netbox if it's active")
    elif proxmox_status == 'running' and netbox_status == 'offline':
        netbox_vm.status.value = 'active'
        netbox_vm.save()

        # Status updated
        status_updated = True

    # Status not expected
        print("[DEBUG] Status not expected")
    else:
        # Status doesn't need to change
        status_updated = False

    return status_updated


def site(**kwargs):
    # If site_id equals to 0, consider it is not configured by user and must be created by Proxbox
    site_id = kwargs.get('site_id', 0)


# Function that modifies 'custom_field' of Netbox Virtual Machine.
# It uses HTTP Request and not Pynetbox (as I was not able to).
def http_update_custom_fields(**kwargs):
    # Saves kwargs variables
    domain_with_http = kwargs.get('domain_with_http')
    token = kwargs.get('token')
    vm_id = kwargs.get('vm_id', 0)
    vm_name = kwargs.get('vm_name')
    vm_cluster = kwargs.get('vm_cluster')
    custom_fields = kwargs.get('custom_fields')

    #
    # HTTP PATCH Request (partially update)
    #
    # URL 
    url = '{}/api/virtualization/virtual-machines/{}/'.format(domain_with_http, vm_id)

    # HTTP Request Headers
    headers = {
        "Authorization": "Token {}".format(token),
        "Content-Type": "application/json"
    }

    # HTTP Request Body
    body = {
        "name": vm_name,
        "cluster": vm_cluster,
        "custom_fields": custom_fields
    }

    # Makes the request and saves it to var
    r = requests.patch(url, data=json.dumps(body), headers=headers)

    # Return HTTP Status Code
    return r.status_code


# Update 'custom_fields' field on Netbox Virtual Machine based on Proxbox
def custom_fields(netbox_vm, proxmox_vm):
    print("[DEBUG] Update 'custom_fields' field on Netbox Virtual Machine based on Proxbox")
    # Create the new 'custom_field' with info from Proxmox
    print("[DEBUG] Create the new 'custom_field' with info from Proxmox")
    custom_fields_update = {}

    # Check if there is 'custom_field' configured on Netbox
    print("[DEBUG] Check if there is 'custom_field' configured on Netbox")
    if len(netbox_vm.custom_fields) == 0:
        print("[ERROR] There's no 'Custom Fields' registered by the Netbox Plugin user")

    # If any 'custom_field' configured, get it and update, if necessary.
        print("[DEBUG] If any 'custom_field' configured, get it and update, if necessary.")
    elif len(netbox_vm.custom_fields) > 0:

        # Get current configured custom_fields
        print("[DEBUG] Get current configured custom_fields.")
        custom_fields_names = list(netbox_vm.custom_fields.keys())

        #
        # VERIFY IF CUSTOM_FIELDS EXISTS AND THEN UPDATE INFORMATION, IF NECESSARY.
        #
        # Custom Field 'proxmox_id'
        print("[DEBUG] VERIFY IF CUSTOM_FIELDS EXISTS AND THEN UPDATE INFORMATION, IF NECESSARY.")
        if 'proxmox_id' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_id") != proxmox_vm['vmid']:
                custom_fields_update["proxmox_id"] = proxmox_vm['vmid']
        else:
            print("[ERROR] 'proxmox_id' custom field not registered yet or configured incorrectly]")

        # Custom Field 'proxmox_node'
        print("[DEBUG] Custom Field 'proxmox_node'")
        if 'proxmox_node' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_node") != proxmox_vm['node']:
                custom_fields_update["proxmox_node"] = proxmox_vm['node']
        else:
            print("[ERROR] 'proxmox_node' custom field not registered yet or configured incorrectly")

        # Custom Field 'proxmox_type'
        print("[DEBUG] Custom Field 'proxmox_type'")
        if 'proxmox_type' in custom_fields_names:
            if netbox_vm.custom_fields.get("proxmox_type") != proxmox_vm['type']:
                custom_fields_update["proxmox_type"] = proxmox_vm['type']
        else:
            print("[ERROR] 'proxmox_type' custom field not registered yet or configured incorrectly")

        # Only updates information if changes found
        print("[DEBUG] Only updates information if changes found")
        if len(custom_fields_update) > 0:

            # As pynetbox does not have a way to update custom_fields, use API HTTP request
            print("[DEBUG] As pynetbox does not have a way to update custom_fields, use API HTTP request")
            custom_field_updated = http_update_custom_fields(
                domain_with_http=NETBOX,
                token=NETBOX_TOKEN,
                vm_id=netbox_vm.id,
                vm_name=netbox_vm.name,
                vm_cluster=netbox_vm.cluster.id,
                custom_fields=custom_fields_update
            )

            # Verify HTTP reply CODE
            print("[DEBUG] Verify HTTP reply CODE")
            if custom_field_updated != 200:
                print(
                    "[ERROR] Some error occured trying to update 'custom_fields' through HTTP Request. HTTP Code: {}. -> {}".format(
                        custom_field_updated, netbox_vm.name))
                return False

            else:
                # If none error occured, considers VM updated.
                print("[DEBUG] If none error occured, considers VM updated.")
                return True

        return False


# Update 'local_context_data' field on Netbox Virtual Machine based on Proxbox
def local_context_data(netbox_vm, proxmox_vm):
    print("[DEBUG] Update 'local_context_data' field on Netbox Virtual Machine based on Proxbox")
    current_local_context = netbox_vm.local_context_data

    proxmox_values = {}

    # Add and change values from Proxmox
    print("[DEBUG] Add and change values from Proxmox")
    proxmox_values["name"] = proxmox_vm["name"]
    proxmox_values["url"] = "https://{}:{}".format(PROXMOX, PROXMOX_PORT)  # URL
    proxmox_values["id"] = proxmox_vm["vmid"]  # VM ID
    proxmox_values["node"] = proxmox_vm["node"]
    proxmox_values["type"] = proxmox_vm["type"]

    maxmem = int(int(proxmox_vm["maxmem"]) / 1000000000)  # Convert bytes to gigabytes
    proxmox_values["memory"] = "{} {}".format(maxmem, 'GB')  # Add the 'GB' unit of measurement

    maxdisk = int(int(proxmox_vm["maxdisk"]) / 1000000000)  # Convert bytes to gigabytes
    proxmox_values["disk"] = "{} {}".format(maxdisk, 'GB')  # Add the 'GB' unit of measurement

    proxmox_values["vcpu"] = proxmox_vm["maxcpu"]  # Add the 'GB' unit of measurement

    # Verify if 'local_context' is empty and if true, creates initial values.
    print("[DEBUG] Verify if 'local_context' is empty and if true, creates initial values.")
    if current_local_context == None:
        netbox_vm.local_context_data = {"proxmox": proxmox_values}
        netbox_vm.save()
        return True

    # Compare current Netbox values with Porxmox values
    elif current_local_context.get('proxmox') != proxmox_values:
        print("[DEBUG] Compare current Netbox values with Porxmox values")
        # Update 'proxmox' key on 'local_context_data'
        current_local_context.update(proxmox=proxmox_values)

        netbox_vm.local_context_data = current_local_context
        netbox_vm.save()
        return True

    # If 'local_context_data' already updated
    else:
        return False

    return False


# Updates following fields based on Proxmox: "vcpus", "memory", "disk", if necessary.
def resources(netbox_vm, proxmox_vm):
    print("[DEBUG] Updates following fields based on Proxmox: 'vcpus', 'memory', 'disk', if necessary.")
    # Save values from Proxmox
    vcpus = float(proxmox_vm["maxcpu"])

    # Convert bytes to megabytes and then convert float to integer
    memory_Mb = proxmox_vm["maxmem"]
    memory_Mb = int(memory_Mb / 1000000)

    # Convert bytes to gigabytes and then convert float to integer
    disk_Gb = proxmox_vm["maxdisk"]
    disk_Gb = int(disk_Gb / 1000000000)

    # JSON with new resources info
    new_resources_json = {}

    # Compare VCPU
    print("[DEBUG] Compare VCPU")
    if netbox_vm.vcpus != None:
        # Convert Netbox VCPUs to float, since it is coming as string from Netbox
        print("[DEBUG] Convert Netbox VCPUs to float, since it is coming as string from Netbox")
        netbox_vm.vcpus = float(netbox_vm.vcpus)

        if netbox_vm.vcpus != vcpus:
            new_resources_json["vcpus"] = vcpus

    elif netbox_vm.vcpus == None:
        new_resources_json["vcpus"] = vcpus

    # Compare Memory
    print("[DEBUG] Compare Memory")
    if netbox_vm.memory != None:
        if netbox_vm.memory != memory_Mb:
            new_resources_json["memory"] = memory_Mb

    elif netbox_vm.memory == None:
        new_resources_json["memory"] = memory_Mb

    # Compare Disk
    print("[DEBUG] Compare Disk")
    if netbox_vm.disk != None:
        if netbox_vm.disk != disk_Gb:
            new_resources_json["disk"] = disk_Gb

    elif netbox_vm.disk == None:
        new_resources_json["disk"] = disk_Gb

    # If new information found, save it to Netbox object.
    print("[DEBUG] If new information found, save it to Netbox object.")
    if len(new_resources_json) > 0:
        resources_updated = netbox_vm.update(new_resources_json)

        if resources_updated == True:
            return True
        else:
            return False


def get_ip(node, vmid, type):
    test_str = None
    try:
        if type == 'qemu':
            config1 = proxmox.nodes(node).qemu(vmid).config.get()
            test_str = config1['ipconfig0']
        if type == 'lxc':
            config2 = proxmox.nodes(node).lxc(vmid).config.get()
            test_str = config2['net0']
    except Exception as e:
        test_str = None
        pass
    if test_str is None:
        return None

    regex = r"ip=\d(\d)?(\d)?.\d(\d)?(\d)?.\d(\d)?(\d)?.\d(\d)?(\d)?(\/(\d)?(\d)?(\d)?)?"

    # test_str = "name=eth0,bridge=vmbr504,firewall=1,gw=172.16.19.1,hwaddr=5A:70:3F:05:0D:AC,ip=172.16.19.251/24,type=veth"
    try:
        matches = re.finditer(regex, test_str, re.MULTILINE)
        it = matches.__next__()
        ip = it.group().replace('ip=', '').strip()
        return ip
    except Exception as e:
        return None
        pass


def add_ip(netbox_vm, proxmox_vm):
    try:
        # Get the ip from the configuration of the vm
        print("[DEBUG] Get the ip from the configuration of the vm")
        ip_addresses = get_ip(proxmox_vm['node'], proxmox_vm['vmid'], proxmox_vm['type'])
        # if no ip is retrieve do nothing
        print("[DEBUG] if no ip is retrieve do nothing")
        if ip_addresses is None:
            return False
        # Check if the vm has already assigned a main ip address
        print("[DEBUG] Check if the vm has already assigned a main ip address")
        if netbox_vm.primary_ip4 is None:
            # Create the interface that is going to allocate the ip
            print("[DEBUG] Create the interface that is going to allocate the ip")
            virtual_machine = netbox_vm.id
            name = 'eth0'
            new_interface_json = {"virtual_machine": virtual_machine, "name": name}
            vm_interface = nb.virtualization.interfaces.create(new_interface_json)
            # Create the ip address and link it to the interface previously created
            print("[DEBUG] Create the ip address and link it to the interface previously created")
            address = {
                "address": ip_addresses,
                "assigned_object_type": "virtualization.vminterface",
                "assigned_object_id": vm_interface.id
            }
            netbox_ip = nb.ipam.ip_addresses.create(address)
            # Associate the ip address to the vm
            print("[DEBUG] Associate the ip address to the vm")
            netbox_vm.primary_ip = netbox_ip
            netbox_vm.primary_ip4 = netbox_ip
            netbox_vm.save()
        else:
            # Update the ip address associated to the interface
            print("[DEBUG] Update the ip address associated to the interface")
            id = netbox_vm.primary_ip4.id
            current_ip = nb.ipam.ip_addresses.get(id=id)
            current_ip.address = ip_addresses
            current_ip.save()
            netbox_vm.primary_ip = current_ip
            netbox_vm.primary_ip4 = current_ip
            netbox_vm.save()
        return True
    except Exception as e:
        return False
