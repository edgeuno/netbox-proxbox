# Default Plugins settings
from django.utils import timezone
from netbox_proxbox import ProxboxConfig

# PLUGIN_CONFIG variable defined by user in Netbox 'configuration.py' file
from netbox.settings import PLUGINS_CONFIG

from netbox_proxbox.proxbox_api_v2.proxbox_session import ProxboxSession

print('[{:%H:%M:%S}] Starting scrapper for {}...'.format(timezone.now(), __name__))

DEFAULT_PLUGINS_CONFIG = ProxboxConfig.default_settings
DEFAULT_PROXBOX_SETTING = DEFAULT_PLUGINS_CONFIG.get("proxmox")
DEFAULT_PROXBOX_FILE_PATH = DEFAULT_PROXBOX_SETTING.get("filePath")

####################################################################################################
#                                                                                                  #
#         FILE_PATH FOR THE CONFIGURATION VARIABLES FROM PLUGINS_CONFIG DEFINED BY USER ON         #
#         NETBOX configuration.py                                                                  #
#                                                                                                  #
####################################################################################################

# Get Proxmox credentials values from PLUGIN_CONFIG
USER_PLUGINS_CONFIG = PLUGINS_CONFIG.get("netbox_proxbox")
PROXBOX_SETTINGS = USER_PLUGINS_CONFIG.get("proxmox")
PROXMOX_SETTING_FILE_PATH = PROXBOX_SETTINGS.get("filePath", DEFAULT_PROXBOX_FILE_PATH)
QUEUE_NAME = 'netbox_proxbox.netbox_proxbox'

### Pluging netbox settings

DEFAULT_NETBOX_SETTING = DEFAULT_PLUGINS_CONFIG.get("netbox")
DEFAULT_NETBOX_SETTINGS = DEFAULT_NETBOX_SETTING.get("settings")
DEFAULT_NETBOX_VM_ROLE_ID = DEFAULT_NETBOX_SETTINGS.get("virtualmachine_role_id", 0)
DEFAULT_NETBOX_VM_ROLE_NAME = DEFAULT_NETBOX_SETTINGS.get("virtualmachine_role_name", "Proxbox Basic Role")
DEFAULT_NETBOX_NODE_ROLE_ID = DEFAULT_NETBOX_SETTINGS.get("node_role_id", 0)
DEFAULT_NETBOX_SITE_ID = DEFAULT_NETBOX_SETTINGS.get("site_id", 0)

NETBOX_SETTING = USER_PLUGINS_CONFIG.get("netbox", DEFAULT_NETBOX_SETTING)
NETBOX_SETTINGS = NETBOX_SETTING.get("settings", DEFAULT_NETBOX_SETTINGS)
NETBOX_TENANT_NAME = "proxbox_tenant"
NETBOX_TENANT_REGEX_VALIDATOR = "proxbox"
NETBOX_TENANT_DESCRIPTION = "Proxbox custom tenant and tag"
NETBOX_MANUFACTURER = "Proxbox Basic Manufacturer"
if NETBOX_SETTINGS is not None:
    NETBOX_VM_ROLE_ID = NETBOX_SETTINGS.get("virtualmachine_role_id", DEFAULT_NETBOX_VM_ROLE_ID)
    NETBOX_VM_ROLE_NAME = NETBOX_SETTINGS.get("virtualmachine_role_name", DEFAULT_NETBOX_VM_ROLE_NAME)
    NETBOX_NODE_ROLE_ID = NETBOX_SETTINGS.get("node_role_id", DEFAULT_NETBOX_NODE_ROLE_ID)
    NETBOX_SITE_ID = NETBOX_SETTINGS.get("site_id", DEFAULT_NETBOX_SITE_ID)
    NETBOX_TENANT_NAME = NETBOX_SETTINGS.get("tenant_name", NETBOX_TENANT_NAME)
    NETBOX_TENANT_REGEX_VALIDATOR = NETBOX_SETTINGS.get("tenant_regex_validator", NETBOX_TENANT_REGEX_VALIDATOR)
    NETBOX_TENANT_DESCRIPTION = NETBOX_SETTINGS.get("tenant_description", NETBOX_TENANT_DESCRIPTION)
    NETBOX_MANUFACTURER = NETBOX_SETTINGS.get("manufacturer", NETBOX_TENANT_DESCRIPTION)

PROXMOX_SESSIONS_LIST, PROXMOX_SESSIONS = ProxboxSession.get_list_from_file(PROXMOX_SETTING_FILE_PATH)
