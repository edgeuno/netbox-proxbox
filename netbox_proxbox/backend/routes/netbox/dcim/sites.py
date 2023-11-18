from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

class Sites(NetboxBase):
    default_name = "Proxbox Basic Site"
    default_slug = "proxbox-basic-site"
    default_description = "Proxbox Basic Site (used to identify the items the plugin created)"
    
    app = "dcim"
    endpoint = "sites"
    object_name = "Site"