from django.core.management.base import BaseCommand, CommandError

from netbox_proxbox.proxbox_api_v2.cleanup_netbox_only_vms import (
    counts,
    run_cleanup,
)


class Command(BaseCommand):
    help = "Remove NetBox VMs with no VMID or no matching VM in Proxmox"

    def add_arguments(self, parser):
        parser.add_argument("--output")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            results, output = run_cleanup(
                output=options["output"],
                dry_run=options["dry_run"],
                progress=self.stdout.write,
            )
        except Exception as error:
            raise CommandError(str(error)) from error

        total = counts(results)
        self.stdout.write("Checked: {}".format(total["checked"]))
        self.stdout.write("Missing VMID: {}".format(total["missing_vmid"]))
        self.stdout.write("Missing in Proxmox: {}".format(total["missing_in_proxmox"]))
        self.stdout.write("Present in Proxmox: {}".format(total["present"]))
        self.stdout.write("Unable to validate: {}".format(total["unable"]))
        self.stdout.write("Deleted: {}".format(total["deleted"]))
        self.stdout.write("Failed: {}".format(total["failed"]))
        self.stdout.write("Kept: {}".format(total["kept"]))
        self.stdout.write("Dry run targets: {}".format(total["dry_run"]))
        self.stdout.write("Report: {}".format(output))
