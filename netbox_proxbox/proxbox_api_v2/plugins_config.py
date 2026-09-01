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

PROXMOX_SESSIONS_LIST, PROXMOX_SESSIONS, NETBOX_SETTINGS = ProxboxSession.get_list_from_file(
    PROXMOX_SETTING_FILE_PATH
)

NETBOX_VM_ROLE_ID = NETBOX_SETTINGS["virtualmachine_role_id"]
NETBOX_VM_ROLE_NAME = NETBOX_SETTINGS["virtualmachine_role_name"]
NETBOX_NODE_ROLE_ID = NETBOX_SETTINGS["node_role_id"]
NETBOX_SITE_ID = NETBOX_SETTINGS["site_id"]
NETBOX_TENANT_NAME = NETBOX_SETTINGS["tenant_name"]
NETBOX_TENANT_REGEX_VALIDATOR = NETBOX_SETTINGS["tenant_regex_validator"]
NETBOX_TENANT_DESCRIPTION = NETBOX_SETTINGS["tenant_description"]
NETBOX_MANUFACTURER = NETBOX_SETTINGS["manufacturer"]
NETBOX_CREATE_DEVICE_WHEN_NOT_FOUND = NETBOX_SETTINGS["create_device_when_not_found"]

print(
    "[INFO] Loaded NetBox settings from {}: tenant_name={!r}, tenant_regex_validator={!r}".format(
        PROXMOX_SETTING_FILE_PATH,
        NETBOX_TENANT_NAME,
        NETBOX_TENANT_REGEX_VALIDATOR,
    )
)
