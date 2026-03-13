from .nb_device_role import upsert_role
from .nb_device_type import upsert_device_type
from .nb_site import upsert_site
from ..plugins_config import NETBOX_NODE_ROLE_ID, NETBOX_SITE_ID, NETBOX_MANUFACTURER

# import logging
import ipaddress
import traceback

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

try:
    from ipam.models import IPAddress
    from dcim.models import Device
    from dcim.models import Interface
    from dcim.choices import InterfaceTypeChoices
    from dcim.models import Manufacturer
    from .nb_tag import tag
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import F, Func


except Exception as e:
    # logger.exception(e)
    traceback.print_exc()
    raise e


def assign_device_role(netbox_node, role):
    if role is None or isinstance(role, str):
        raise ValueError("Invalid device role returned by upsert_role: {}".format(role))

    # NetBox 4.x uses `role`; older versions use `device_role`.
    if hasattr(netbox_node, "role"):
        netbox_node.role = role
    if hasattr(netbox_node, "role_id"):
        netbox_node.role_id = role.id

    if hasattr(netbox_node, "device_role"):
        netbox_node.device_role = role
    if hasattr(netbox_node, "device_role_id"):
        netbox_node.device_role_id = role.id

    return netbox_node


def update_role(netbox_node, proxmox_node):
    try:
        role_id = NETBOX_NODE_ROLE_ID
        role_name = proxmox_node.proxbox_session.node_role_name

        # Create json with basic NODE information
        dev_role = upsert_role(role_id=role_id, role_name=role_name)
        netbox_node = assign_device_role(netbox_node, dev_role)
    except Exception as e:
        print("Error: update_role - {}".format(e))
        # logger.exception(e)
        # traceback.print_exc()
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

        netbox_obj = assign_device_role(netbox_obj, device_role)

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
        # logger.exception(e)
        # traceback.print_exc()
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
        # logger.exception(e)
        # traceback.print_exc()
    return netbox_node


def parse_host_ip(ip):
    if ip is None:
        return None
    value = str(ip).strip()
    if value == "":
        return None
    try:
        if "/" in value:
            return str(ipaddress.ip_interface(value).ip)
        return str(ipaddress.ip_address(value))
    except Exception:
        return None


def normalize_ip_for_storage(ip):
    if ip is None:
        return None
    value = str(ip).strip()
    if value == "":
        return None
    try:
        if "/" in value:
            return str(ipaddress.ip_interface(value))
        host = ipaddress.ip_address(value)
        if host.version == 4:
            return "{}/32".format(host)
        return "{}/128".format(host)
    except Exception:
        return None


def get_ips_by_host(ip):
    if ip is None:
        return IPAddress.objects.none()
    value = str(ip).strip()
    if value == "":
        return IPAddress.objects.none()

    # 1) Try exact match first (same host and prefix).
    exact_ips = IPAddress.objects.filter(address=value)
    if exact_ips.exists():
        return exact_ips

    # 2) Try normalized exact match (e.g. 10.0.0.1 -> 10.0.0.1/32).
    normalized_ip = normalize_ip_for_storage(ip)
    if normalized_ip is not None and normalized_ip != value:
        normalized_ips = IPAddress.objects.filter(address=normalized_ip)
        if normalized_ips.exists():
            return normalized_ips

    # 3) Fallback: search by host ignoring prefix length.
    host_ip = parse_host_ip(ip)
    if host_ip is None:
        return IPAddress.objects.none()
    return IPAddress.objects.annotate(addr_host=Func(F("address"), function="HOST")).filter(addr_host=host_ip)


def find_node_by_ip(ip):
    if ip is None:
        return None
    print(
        "[INFO] Gettign device with ip: {}".format(ip)
    )
    current_ips = get_ips_by_host(ip)
    for current_ip in current_ips:
        if current_ip is None:
            continue
        assigned_object = getattr(current_ip, "assigned_object", None)
        if assigned_object is None:
            continue

        device = getattr(assigned_object, "device", None)
        if device is not None:
            return device

        # Some assigned objects expose device_id without a loaded device relation.
        device_id = getattr(assigned_object, "device_id", None)
        if device_id is not None:
            return Device.objects.filter(id=device_id).first()
    return None


def status(netbox_node, proxmox_node):
    #
    # Compare STATUS
    #
    if proxmox_node.online == 1:
        # If Proxmox is 'online' and Netbox is 'offline', update it.
        if netbox_node.status == 'offline':
            netbox_node.status = 'active'
    elif proxmox_node.online == 0:
        # If Proxmox is 'offline' and Netbox' is 'active', update it.
        if netbox_node.status == 'active':
            netbox_node.status = 'offline'

    return netbox_node


# Update CLUSTER field on /dcim/device/{id}
def update_cluster(netbox_node, proxmox_node):
    #
    # Compare CLUSTER
    #

    # Use Cluster ID to update NODE information
    netbox_node.cluster_id = proxmox_node.cluster.nb_cluster.id
    netbox_node.cluster = proxmox_node.cluster.nb_cluster

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
    if ip is None and proxmox_node.ip is not None:
        ip = proxmox_node.ip
    ip_value = normalize_ip_for_storage(ip)
    if ip_value is None:
        print(
            "[WARN] interface_ip_assign: invalid IP value '{}' for node {}. "
            "Skipping assignment.".format(ip, netbox_node.name)
        )
        return netbox_node
    try:
        node_interface = get_set_interface('bond0', netbox_node)
        netbox_ip = get_ips_by_host(ip_value).first()
        content_type = ContentType.objects.filter(app_label="dcim", model="interface").first()
        if netbox_ip is None:
            # Create the ip address and link it to the interface previously created
            netbox_ip = IPAddress(address=ip_value)
            netbox_ip.assigned_object_type = content_type  # "dcim.interface"
            netbox_ip.assigned_object_id = node_interface.id
            netbox_ip.assigned_object = node_interface
            netbox_ip.save()
        else:
            assigned_object = netbox_ip.assigned_object
            if assigned_object is None:
                netbox_ip.assigned_object_type = content_type  # "dcim.interface"
                netbox_ip.assigned_object_id = node_interface.id
                netbox_ip.assigned_object = node_interface
                netbox_ip.save()
            else:
                # Keep current assignment when the IP already belongs to this device.
                assigned_device_id = getattr(assigned_object, "device_id", None)
                if assigned_device_id is None and hasattr(assigned_object, "device"):
                    assigned_device = getattr(assigned_object, "device", None)
                    if assigned_device is not None:
                        assigned_device_id = assigned_device.id

                if assigned_device_id != netbox_node.id:
                    print(
                        "[WARN] interface_ip_assign: IP {} already assigned to another object. "
                        "Skipping assignment for node {}.".format(ip_value, netbox_node.name)
                    )
                    return netbox_node
        # Associate the ip address to the node using the parsed family.
        ip_version = ipaddress.ip_interface(ip_value).ip.version
        if hasattr(netbox_node, "primary_ip_id"):
            netbox_node.primary_ip_id = netbox_ip.id
        if ip_version == 4:
            if hasattr(netbox_node, "primary_ip4_id"):
                netbox_node.primary_ip4_id = netbox_ip.id
        else:
            if hasattr(netbox_node, "primary_ip6_id"):
                netbox_node.primary_ip6_id = netbox_ip.id
    except Exception as e:
        print("Error: interface_ip_assign-all - {}".format(e))
        print(e)
        # logger.exception(e)
        # traceback.print_exc()
    return netbox_node


def node_full_update(netbox_node, proxmox_node):
    try:
        netbox_node = status(netbox_node, proxmox_node)
        netbox_node = update_cluster(netbox_node, proxmox_node)
        netbox_node = update_role(netbox_node, proxmox_node)
        netbox_node = update_device_type(netbox_node)
        netbox_node = interface_ip_assign(netbox_node, proxmox_node)
        netbox_node.save()

    except Exception as e:
        print("Error: node_full_update - {}".format(e))
        # logger.exception(e)
        # traceback.print_exc()
        print(e)
        raise e
    return netbox_node


def upsert_nodes(proxmox_node):
    netbox_node = None
    was_created = False
    # Search netbox using VM name
    if proxmox_node.cidr:
        netbox_node = find_node_by_ip(proxmox_node.cidr)
    if netbox_node is None:
        netbox_node = Device.objects.filter(name=proxmox_node.name).first()

    # Search node on Netbox with Proxmox node name gotten
    if netbox_node is None:
        # If node does not exist, create it.
        netbox_node = create_node(proxmox_node)
        was_created = netbox_node is not None
        if was_created:
            print("[OK] Node created! -> {}".format(proxmox_node.name))
        else:
            print('[ERROR] Something went wrong when creating the node.-> {}'.format(proxmox_node.name))
            return None

    if netbox_node is not None:
        # Update rest of configuration
        netbox_node = node_full_update(netbox_node, proxmox_node)
        # Analyze if update was successful
        print('[OK] NODE {} updated.'.format(proxmox_node.name))
    else:
        print('[ERROR] Something went wrong when creating the node.-> {}'.format(proxmox_node.name))

    return netbox_node
