from .nb_device_role import upsert_role
from .nb_device_type import upsert_device_type
from .nb_site import upsert_site
from ..plugins_config import NETBOX_NODE_ROLE_ID, NETBOX_SITE_ID, NETBOX_MANUFACTURER

try:
    from ipam.models import IPAddress
    from dcim.models import Device
    from dcim.models import Interface
    from dcim.choices import InterfaceTypeChoices
    from dcim.models import Manufacturer
    from .nb_tag import tag
    from django.contrib.contenttypes.models import ContentType


except Exception as e:
    print(e)
    raise e


def update_role(netbox_node, proxmox_node):
    try:
        role_id = NETBOX_NODE_ROLE_ID
        role_name = proxmox_node.proxbox_session.node_role_name

        # Create json with basic NODE information
        dev_role = upsert_role(role_id=role_id, role_name=role_name)
        netbox_node.device_role = dev_role
        netbox_node.device_role_id = dev_role.id
        netbox_node.save()
    except Exception as e:
        print("Error: update_role - {}".format(e))
        print(e)
    return netbox_node


def create_node(proxmox_node):
    role_id = NETBOX_NODE_ROLE_ID
    site_id = NETBOX_SITE_ID
    site_name = proxmox_node.proxbox_session.site_name
    role_name = proxmox_node.proxbox_session.node_role_name

    # Create json with basic NODE information
    # Create Node with json 'node_json'
    try:
        name = proxmox_node.name
        device_role = upsert_role(role_id=role_id, role_name=role_name)
        device_type = upsert_device_type()
        site = upsert_site(site_id=site_id, site_name=site_name)

        netbox_obj = Device(name=name)

        netbox_obj.device_role = device_role
        netbox_obj.device_role_id = device_role.id

        netbox_obj.device_type = device_type
        netbox_obj.device_type_id = device_type.id

        netbox_obj.site = site
        netbox_obj.site_id = site.id
        netbox_obj.status = 'active'
        netbox_obj.cluster = proxmox_node.cluster.nb_cluster
        netbox_obj.cluster_id = proxmox_node.cluster.nb_cluster.id
        netbox_obj.save()
    except Exception as e:
        print("[proxbox_api.create.node] Creation of NODE failed.")
        print(e)
        # In case nothing works, returns error
        return None
    else:
        if netbox_obj:
            c_tag = tag()
            netbox_obj.tags.add(c_tag)
        return netbox_obj


def update_device_type(netbox_node):
    try:
        device_type = netbox_node.device_type
        if device_type:
            manufacturer = device_type.manufacturer
            if manufacturer:
                if manufacturer.name.lower() == 'proxbox basic manufacturer':
                    default_manufacturer = Manufacturer.objects.filter(name=NETBOX_MANUFACTURER).first()
                    if default_manufacturer:
                        device_type.manufacturer = default_manufacturer
                        device_type.manufacturer_id = default_manufacturer.id
                        device_type.save()
    except Exception as e:
        print("Error: update_device_type - {}".format(e))
        print(e)
    return netbox_node


def find_node_by_ip(ip):
    current_ips = IPAddress.objects.filter(address=ip)
    if len(current_ips) > 0:
        for current_ip in current_ips:
            if current_ip and current_ip.assigned_object and current_ip.assigned_object.device:
                device = current_ip.assigned_object.device
                return device
    return None


def status(netbox_node, proxmox_node):
    #
    # Compare STATUS
    #
    if proxmox_node.online == 1:
        # If Proxmox is 'online' and Netbox is 'offline', update it.
        if netbox_node.status == 'offline':
            netbox_node.status = 'active'
            netbox_node.save()
    elif proxmox_node.online == 0:
        # If Proxmox is 'offline' and Netbox' is 'active', update it.
        if netbox_node.status == 'active':
            netbox_node.status = 'offline'

            netbox_node.save()

    return netbox_node


# Update CLUSTER field on /dcim/device/{id}
def update_cluster(netbox_node, proxmox_node):
    #
    # Compare CLUSTER
    #

    # Use Cluster ID to update NODE information
    netbox_node.cluster_id = proxmox_node.cluster.nb_cluster.id
    netbox_node.cluster = proxmox_node.cluster.nb_cluster
    netbox_node.save()

    return netbox_node


def get_set_interface(name, netbox_node):
    dev_interface = Interface.objects.filter(name=name, device_id=netbox_node.id).first()
    if dev_interface is None:
        # new_interface_json = {"device_id": netbox_node.id, "name": name, type: InterfaceTypeChoices.TYPE_LAG}
        dev_interface = Interface(
            name=name,
            # form_factor=0,
            description="LAG",
            device=netbox_node,
            device_id=netbox_node.id,
            type=InterfaceTypeChoices.TYPE_LAG
        )
        dev_interface.save()

    return dev_interface


# Assing node ip if it doesn't have it
def interface_ip_assign(netbox_node, proxmox_node):
    ip = proxmox_node.cidr
    try:
        node_interface = get_set_interface('bond0', netbox_node)
        netbox_ip = IPAddress.objects.filter(address=ip).first()
        content_type = ContentType.objects.filter(app_label="dcim", model="interface").first()
        if netbox_ip is None:
            # Create the ip address and link it to the interface previously created
            netbox_ip = IPAddress(address=ip)
            netbox_ip.assigned_object_type = content_type  # "dcim.interface"
            netbox_ip.assigned_object_id = node_interface.id
            netbox_ip.assigned_object = node_interface
            netbox_ip.save()
        else:
            try:
                netbox_ip.assigned_object_type = content_type  # "dcim.interface"
                netbox_ip.assigned_object_id = node_interface.id
                netbox_ip.assigned_object = node_interface
                netbox_ip.save()
            except Exception as e:
                print("Error: interface_ip_assign-update - {}".format(e))
                # print('')
                print(e)
        # Associate the ip address to the vm
        # Reload the ip in order to get the correct family version
        netbox_ip = IPAddress.objects.filter(address=ip).first()
        netbox_node.primary_ip_id = netbox_ip.id
        if netbox_ip.family == 4:
            netbox_node.primary_ip4 = netbox_ip
            netbox_node.primary_ip4_id = netbox_ip.id
        else:
            netbox_node.primary_ip6 = netbox_ip
            netbox_node.primary_ip6_id = netbox_ip.id
        netbox_node.save()
    except Exception as e:
        print("Error: interface_ip_assign-all - {}".format(e))
        print(e)
    return netbox_node


def node_full_update(netbox_node, proxmox_node):
    try:
        netbox_node = status(netbox_node, proxmox_node)
        netbox_node = update_cluster(netbox_node, proxmox_node)
        netbox_node = update_role(netbox_node, proxmox_node)
        netbox_node = update_device_type(netbox_node)
        netbox_node = interface_ip_assign(netbox_node, proxmox_node)

    except Exception as e:
        print("Error: node_full_update - {}".format(e))
        print(e)
        raise e
    return netbox_node


def upsert_nodes(proxmox_node):
    netbox_node = None
    # Search netbox using VM name
    if proxmox_node.cidr:
        netbox_node = find_node_by_ip(proxmox_node.cidr)
    if netbox_node is None:
        netbox_node = Device.objects.filter(name=proxmox_node.name).first()

    # Search node on Netbox with Proxmox node name gotten
    if netbox_node is None:
        # If node does not exist, create it.
        netbox_node = create_node(proxmox_node)
        print("[OK] Node created! -> {}".format(proxmox_node.name))

    if netbox_node is not None:
        # Update rest of configuration
        netbox_node = node_full_update(netbox_node, proxmox_node)
        # Analyze if update was successful
        print('[OK] NODE {} updated.'.format(proxmox_node.name))
    else:
        print('[ERROR] Something went wrong when creating the node.-> {}'.format(proxmox_node.name))

    return netbox_node
