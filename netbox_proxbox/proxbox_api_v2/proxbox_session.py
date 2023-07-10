import json
from django.utils import timezone
from dataclasses import dataclass, field

from proxmoxer import ProxmoxAPI


@dataclass
class ProxboxSession:
    # Connection settings
    domain: str = 'proxbox.example.com'
    http_port: int = 8006
    user: str = 'root@pam'
    token_name: str = 'tokenID'
    token_value: str = '039az154-23b2-4be0-8d20-b66abc8c4686'
    ssl: bool = False
    site_name: str = 'unknown'
    node_role_name: str = "Hypervisor"
    session: ProxmoxAPI = None

    # Node creation Values
    manufacturer: str = "Dell",
    virtualmachine_role_id: int = 0,
    virtualmachine_role_name: str = "Proxbox Basic Role",
    node_role_id: int = 0,
    site_id: int = 0,
    tenant_name: str = "EdgeUno",
    tenant_regex_validator: str = "^e1-",
    tenant_description: str = "The vm belongs to Edgeuno"

    # Initialize the proxmox api with the data from the instance
    def __post_init__(self):
        self.reset_session()

    def reset_session(self):
        try:
            self.session = ProxmoxAPI(
                self.domain,
                user=self.user,
                token_name=self.token_name,
                token_value=self.token_value,
                verify_ssl=self.ssl
            )
        except Exception as e:
            print(f"Error connecting to the domain {self.domain}")
            print(e)
            self.session = None
        return self

    @staticmethod
    def instance_from_dict(dictionary: dict):
        domain = dictionary.get("domain", None)
        http_port = dictionary.get("http_port", None)
        user = dictionary.get("user", None)
        token_name = dictionary.get("token_name", None)
        token_value = dictionary.get("token_value", None)
        ssl = dictionary.get("ssl", None)
        site_name = dictionary.get("site_name", None)
        node_role_name = dictionary.get("node_role_name", None)
        manufacturer = dictionary.get("manufacturer", None)
        virtualmachine_role_id = dictionary.get("virtualmachine_role_id", None)
        virtualmachine_role_name = dictionary.get("virtualmachine_role_name", None)
        node_role_id = dictionary.get("node_role_id", None)
        site_id = dictionary.get("site_id", None)
        tenant_name = dictionary.get("tenant_name", None)
        tenant_regex_validator = dictionary.get("tenant_regex_validator", None)
        tenant_description = dictionary.get("tenant_description", None)

        return ProxboxSession(
            domain=domain,
            http_port=http_port,
            user=user,
            token_name=token_name,
            token_value=token_value,
            ssl=ssl,
            site_name=site_name,
            node_role_name=node_role_name,
            manufacturer=manufacturer,
            virtualmachine_role_id=virtualmachine_role_id,
            virtualmachine_role_name=virtualmachine_role_name,
            node_role_id=node_role_id,
            site_id=site_id,
            tenant_name=tenant_name,
            tenant_regex_validator=tenant_regex_validator,
            tenant_description=tenant_description,
        )

    @staticmethod
    def get_from_file(file_path, domain):
        with open(file_path) as config_file:
            file_contents = config_file.read()

        if file_contents is None:
            return ProxboxSession()

        parsed_json = json.loads(file_contents)

        proxmox_config = parsed_json.get("proxmox")
        netbox_config = parsed_json.get("netbox")

        proxmox_config_item = None
        for p in proxmox_config:
            if p.get("domain") == domain:
                proxmox_config_item = ProxboxSession.mix_proxmox_netbox_config(p, netbox_config)
                break

        if proxmox_config_item is None:
            return ProxboxSession()

        return ProxboxSession.instance_from_dict(p)

    @staticmethod
    def mix_proxmox_netbox_config(proxmox_item, netbox_item):
        proxmox_item["manufacturer"] = netbox_item.get("manufacturer", None)
        proxmox_item["virtualmachine_role_id"] = netbox_item.get("virtualmachine_role_id", None)
        proxmox_item["virtualmachine_role_name"] = netbox_item.get("virtualmachine_role_name", None)
        proxmox_item["node_role_id"] = netbox_item.get("node_role_id", None)
        proxmox_item["site_id"] = netbox_item.get("site_id", None)
        proxmox_item["tenant_name"] = netbox_item.get("tenant_name", None)
        proxmox_item["tenant_regex_validator"] = netbox_item.get("tenant_regex_validator", None)
        proxmox_item["tenant_description"] = netbox_item.get("tenant_description", None)

        return proxmox_item

    @staticmethod
    def get_list_from_file(file_path):
        print('[{:%H:%M:%S}] Starting reading configuration file at {}...'.format(timezone.now(), file_path))

        with open(file_path) as config_file:
            file_contents = config_file.read()

        if file_contents is None:
            raise Exception(f"No contents were found at the path {file_path}")

        parsed_json = json.loads(file_contents)

        proxmox_config = parsed_json.get("proxmox")
        netbox_config = parsed_json.get("netbox")

        outputList = []
        outputDict = {}
        # Go thought the list and get the session in the output list
        for proxmox_config_item in proxmox_config:
            # Set the general values to the item
            proxmox_config_item = ProxboxSession.mix_proxmox_netbox_config(proxmox_config_item, netbox_config)

            # Instate the instance and added to the list
            s = ProxboxSession.instance_from_dict(proxmox_config_item)
            if s.session is None:
                continue
            outputList.append(s)
            outputDict[s.domain] = s

        return outputList, outputDict
