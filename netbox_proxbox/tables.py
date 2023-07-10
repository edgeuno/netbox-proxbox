# tables.py
import django_tables2 as table

from netbox.tables import NetBoxTable
from .models import ProxmoxVM

class ProxmoxVMTable(NetBoxTable):
    """Table for displaying the synchronize objects"""
    id = table.LinkColumn()
    cluster = table.LinkColumn()
    virtual_machine = table.LinkColumn()
    proxmox_vm_id = table.LinkColumn()

    class Meta(NetBoxTable.Meta):
        model = ProxmoxVM
        fields = (
            "id",
            "virtual_machine",
            "proxmox_vm_id",
            "status",
            "type",
            "node",
            "cluster",
        )
