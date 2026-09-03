# Netbox plugin related import
try:
    from extras.plugins import PluginConfig
except Exception as e:
    from netbox.plugins import PluginConfig

class ProxboxConfig(PluginConfig):
    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.1.1"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emerson.felipe@nmultifibra.com.br"
    base_url = "proxbox"
    required_settings = []
    default_settings = {
        'proxmox': {
            'filePath': '/home/javier/projects/netbox/plugins/netbox-proxbox/configuration_options.json',
            # May also be IP address
            'domain': 'proxbox.example.com',  # May also be IP address
            'http_port': 8006,
            'user': 'root@pam',
            'password': 'Strong@P4ssword',
            'token_name': 'tokenID',
            'token_value': '039az154-23b2-4be0-8d20-b66abc8c4686',
            'ssl': False
        },
        'netbox': {
            'domain': 'netbox.example.com',  # May also be IP address
            'http_port': 80,
            'token': '0dd7cddfaee3b38bbffbd2937d44c4a03f9c9d38',
            'ssl': False,
            'settings': {
                'virtualmachine_role_id': 0,
                'node_role_id': 0,
                'site_id': 0
            },
            'manufacturer': 'Dell',
            'virtualmachine_role_id': 0,
            'virtualmachine_role_name': 'Proxbox Basic Role',
            'node_role_id': 0,
            'site_id': 0,
            'tenant_name': 'EdgeUno',
            'tenant_regex_validator': '^e1-',
            'tenant_description': 'The vm belongs to Edgeuno',
            'create_device_when_not_found': False,
            'duplicate_ip_tag_excluded_ranges': [],
            'duplicate_ip_comment_for_excluded_ranges': True,
            'ai_tenant': {
                'enabled': False,
                'provider': 'ollama',
                'url': 'http://host.docker.internal:11434/v1/chat/completions',
                'model': 'llama3.1:8b',
                'api_key': '',
                'timeout_seconds': 20,
                'minimum_confidence': 0.8
            },
            'tenant_enrichment': {
                'enabled': False,
                'url': 'https://example.test/tenant-enrichment',
                'api_key': '',
                'timeout_seconds': 10
            }
        }
    }


config = ProxboxConfig

from . import proxbox_api
