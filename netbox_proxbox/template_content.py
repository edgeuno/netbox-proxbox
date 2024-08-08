
try:
    from extras.plugins import PluginTemplateExtension
except Exception as e:
    from netbox.plugins import PluginTemplateExtension

from .models import ProxmoxVM


class ProxboxVMAttachFields(PluginTemplateExtension):
    model = 'virtualization.virtualmachine'

    def right_page(self):
        obj = self.context['object']
        proxbox_vm = ProxmoxVM.objects.filter(virtual_machine_id=obj.id).first()
        return self.render(
            'netbox_proxbox/proxbox_vm_attach.html', extra_context={
                'proxbox': proxbox_vm,
            }
        )


template_extensions = [ProxboxVMAttachFields]
