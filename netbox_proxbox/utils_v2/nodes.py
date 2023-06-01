from .cluster import get_set_cluster
from .device_role import get_set_role
from .device_type import get_set_device_type
from .site import get_set_site

try:
    from ipam.models import IPAddress
    from dcim.models import Device
    from dcim.models import Interface
    from dcim.choices import InterfaceTypeChoices
    from dcim.models import Manufacturer
    from .extras import tag
    from django.contrib.contenttypes.models import ContentType

    from ..proxbox_api.plugins_config import (
        NETBOX_NODE_ROLE_ID,
        NETBOX_SITE_ID,
        NETBOX_MANUFACTURER
    )

except Exception as e:
    print(e)
    raise e


def find_node_by_ip(ip):
    current_ips = IPAddress.objects.filter(address=ip)
    if len(current_ips) > 0:
        for current_ip in current_ips:
            if current_ip and current_ip.assigned_object and current_ip.assigned_object.device:
                device = current_ip.assigned_object.device
                return device
    return None


def create_node(proxmox, proxmox_node, proxmox_session=None):
    role_id = NETBOX_NODE_ROLE_ID
    site_id = NETBOX_SITE_ID
    site_name = None
    role_name = None
    if proxmox_session:
        role_id = proxmox_session.get('NETBOX_NODE_ROLE_ID', role_id)
        site_id = proxmox_session.get('NETBOX_SITE_ID', site_id)
        site_name = proxmox_session.get('NETBOX_SITE_NAME', site_name)
        role_name = proxmox_session.get('NETBOX_NODE_ROLE_NAME', role_name)

    # Create json with basic NODE information
    # Create Node with json 'node_json'
    try:
        node_json = {}
        name = proxmox_node['name']
        device_role = get_set_role(role_id=role_id, role_name=role_name)
        device_type = get_set_device_type()
        site = get_set_site(site_id=site_id, site_name=site_name)
        cluster = get_set_cluster(proxmox)

        netbox_obj = Device(
            name=name
        )

        netbox_obj.device_role = device_role
        netbox_obj.device_role_id = device_role.id

        netbox_obj.device_type = device_type
        netbox_obj.device_type_id = device_type.id

        netbox_obj.site = site
        netbox_obj.site_id = site.id
        netbox_obj.status = 'active'
        netbox_obj.cluster = cluster
        netbox_obj.cluster_id = cluster.id
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


def status(netbox_node, proxmox_node):
    #
    # Compare STATUS
    #
    if proxmox_node['online'] == 1:
        # If Proxmox is 'online' and Netbox is 'offline', update it.
        if netbox_node.status == 'offline':
            netbox_node.status = 'active'

            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False


    elif proxmox_node['online'] == 0:
        # If Proxmox is 'offline' and Netbox' is 'active', update it.
        if netbox_node.status == 'active':
            netbox_node.status = 'offline'

            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False

    else:
        status_updated = False

    return status_updated


# Update CLUSTER field on /dcim/device/{id}
def update_cluster(proxmox, netbox_node, proxmox_node, proxmox_cluster):
    #
    # Compare CLUSTER
    #
    if proxmox_cluster != None:
        # If cluster is filled, but different from actual cluster, update it.
        proxmox_cluster_name = proxmox_cluster['name']
        if netbox_node.cluster is None or netbox_node.cluster.name != proxmox_cluster_name:
            # Search for Proxmox Cluster using create.cluster() function
            netbox_cluster = get_set_cluster(proxmox)
            cluster_id = netbox_cluster.id

            # Use Cluster ID to update NODE information
            netbox_node.cluster_id = cluster_id
            netbox_node.cluster = netbox_cluster

            if netbox_node.save() == True:
                cluster_updated = True
            else:
                cluster_updated = False

        else:
            cluster_updated = False

    # If cluster is empty, update it.
    elif proxmox_cluster == None:
        # Search for Proxmox Cluster using create.cluster() function
        cluster_id = get_set_cluster(proxmox).id

        # Use Cluster ID to update NODE information
        netbox_node.cluster.id = cluster_id

        if netbox_node.save() == True:
            cluster_updated = True
        else:
            cluster_updated = False

    # If cluster was not empty and also not different, do not make any change.
    else:
        cluster_updated = False

    return cluster_updated


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
def interface_ip_assign(netbox_node, proxmox_json):
    ip = proxmox_json.get("ip", None)
    try:
        node_interface = get_set_interface('bond0', netbox_node)
        # netbox_ip = nb.ipam.ip_addresses.get(address=ip)
        netbox_ip = IPAddress.objects.filter(address=ip).first()
        content_type = ContentType.objects.filter(app_label="dcim", model="interface").first()
        if netbox_ip is None:
            # Create the ip address and link it to the interface previously created
            netbox_ip = IPAddress(
                address=ip
            )
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
        return True
    except Exception as e:
        print("Error: interface_ip_assign-all - {}".format(e))
        print(e)
        return False


def update_role(netbox_node, proxmox_session=None):
    try:
        role_name = None
        if proxmox_session:
            role_id = proxmox_session.get('NETBOX_NODE_ROLE_ID', None)
            role_name = proxmox_session.get('NETBOX_NODE_ROLE_NAME', role_name)
        # Create json with basic NODE information

        dev_role = get_set_role(role_id=role_id, role_name=role_name)
        netbox_node.device_role = dev_role
        netbox_node.device_role_id = dev_role.id
        netbox_node.save()
        return True
    except Exception as e:
        print("Error: update_role - {}".format(e))
        print(e)
        return False


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
                        return True

        return False
    except Exception as e:
        print("Error: update_device_type - {}".format(e))
        print(e)
        return False


def node_full_update(proxmox, netbox_node, proxmox_json, proxmox_cluster, proxmox_session=None):
    try:
        changes = {}

        status_updated = status(netbox_node, proxmox_json)
        cluster_updated = update_cluster(proxmox, netbox_node, proxmox_json, proxmox_cluster)
        ip_updated = interface_ip_assign(netbox_node, proxmox_json)
        if proxmox_session:
            role_updated = update_role(netbox_node, proxmox_session)

        device_type_updated = update_device_type(netbox_node)

        changes = {
            "status": status_updated,
            "cluster": cluster_updated,
            "ip": ip_updated,
            "role": False if role_updated is None else role_updated,
            "device_type_updated": device_type_updated
        }

        return changes
    except Exception as e:
        print("Error: node_full_update - {}".format(e))
        print(e)
        raise e


def get_set_nodes(**kwargs):
    try:
        proxmox_cluster = kwargs.get('proxmox_cluster')
        proxmox_json = kwargs.get('proxmox_json')
        proxmox = kwargs.get('proxmox')
        proxmox_session = kwargs.get('proxmox_session', None)

        node_ip = proxmox_json.get("ip", None)
        try:
            node = proxmox.nodes(proxmox_json['name']).network().get()
            node_ip_mask = node_ip
            for d in node:
                if 'address' in d and d['address'] == node_ip:
                    node_ip_mask = d['cidr']
                    break
            proxmox_node_name = proxmox_json.get("name")
            proxmox_json['ip'] = node_ip_mask
        except Exception as e:
            print("Error getting the ip with mask")
            print(e)

        json_node = {}

        # Search netbox using VM name
        if node_ip:
            netbox_search = find_node_by_ip(node_ip_mask)
        if netbox_search is None:
            # netbox_search = nb.dcim.devices.filter(name=proxmox_node_name).first()
            netbox_search = Device.objects.filter(name=proxmox_node_name).first()

        # Search node on Netbox with Proxmox node name gotten
        if netbox_search == None:
            # If node does not exist, create it.
            netbox_node = create_node(proxmox, proxmox_json, proxmox_session)

            # Node created
            if netbox_node != None:
                print("[OK] Node created! -> {}".format(proxmox_node_name))

                # Update rest of configuration
                full_update = node_full_update(proxmox, netbox_node, proxmox_json, proxmox_cluster, proxmox_session)
                json_node["changes"] = full_update

                full_update_list = list(full_update.values())

                # Analyze if update was successful
                if True in full_update_list:
                    print('[OK] NODE updated. -> {}'.format(proxmox_node_name))
                else:
                    print('[OK] NODE already updated. -> {}'.format(proxmox_node_name))

                # return True as the node was successfully created.
                json_node["result"] = True

            # Error with node creation
            else:
                print('[ERROR] Something went wrong when creating the node.-> {}'.format(proxmox_node_name))
                json_node["result"] = False

        else:
            # If node already exist, try updating it.
            netbox_node = netbox_search

            # Update Netbox node information, if necessary.
            full_update = node_full_update(proxmox, netbox_node, proxmox_json, proxmox_cluster, proxmox_session)
            json_node["changes"] = full_update

            full_update_list = list(full_update.values())

            # Analyze if update was successful
            if True in full_update_list:
                print('[OK] NODE updated. -> {}'.format(proxmox_node_name))
            else:
                print('[OK] NODE already updated. -> {}'.format(proxmox_node_name))

            # return True as the node was successfully created.
            json_node["result"] = True

        return json_node
    except Exception as e:
        print("Error: nodes - {}".format(e))
        print(e)
        return None
