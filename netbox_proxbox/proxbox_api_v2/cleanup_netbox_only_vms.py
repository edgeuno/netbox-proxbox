"""Report and remove NetBox VMs that are missing from Proxmox."""

import os
from datetime import datetime, timezone
from pathlib import Path

from django.db import connection, transaction
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxVM


NETBOX_URL = "http://0.0.0.0:8182/virtualization/virtual-machines/{}/"
HEADERS = [
    "NetBox VM ID", "VMID", "NetBox Status", "Proxmox Status", "Tenant",
    "Proxmox Node", "Proxmox Tags", "NetBox Comment", "Proxmox Comment",
    "Proxmox Domain", "NetBox URL", "Proxmox URL", "Result",
    "Cleanup Status", "Cleanup Error",
]
CLEANUP_RESULTS = ("Missing VMID", "Missing in Proxmox", "Unable to validate")

QUERY = """
SELECT
    vm.id AS netbox_vm_id,
    CASE
        WHEN pvm.proxmox_vm_id IS NOT NULL THEN pvm.proxmox_vm_id
        WHEN vm.custom_field_data->>'proxmox_id' ~ '^\\d+$'
            THEN (vm.custom_field_data->>'proxmox_id')::integer
    END AS vmid,
    vm.status AS netbox_status,
    COALESCE(vm.comments, '') AS netbox_comment,
    tenant.name AS tenant,
    COALESCE(
        pvm.node,
        vm.custom_field_data->>'proxmox_node',
        vm.local_context_data->'proxmox'->>'node'
    ) AS stored_node,
    COALESCE(
        pvm.domain,
        vm.local_context_data->'proxmox'->>'domain'
    ) AS domain,
    COALESCE(
        pvm.type,
        vm.custom_field_data->>'proxmox_type',
        vm.local_context_data->'proxmox'->>'type'
    ) AS stored_type,
    COALESCE(
        NULLIF(BTRIM(pvm.url), ''),
        vm.local_context_data->'proxmox'->>'vm_url'
    ) AS proxmox_url
FROM virtualization_virtualmachine AS vm
LEFT JOIN netbox_proxbox_proxmoxvm AS pvm ON pvm.virtual_machine_id = vm.id
LEFT JOIN tenancy_tenant AS tenant ON tenant.id = vm.tenant_id
ORDER BY vm.id
"""


def default_output():
    directory = Path(os.environ.get(
        "PROXBOX_CLEANUP_REPORT_DIR", "/opt/netbox/runtime/cleanup_reports"
    ))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return directory / "netbox_vm_cleanup_{}.xlsx".format(stamp)


def select_vms():
    with connection.cursor() as cursor:
        cursor.execute(QUERY)
        columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _inventory(domain, sessions, inventories):
    if not domain:
        return None, "Proxmox domain is NULL"
    session = sessions.get(domain)
    if session is None or session.session is None:
        return None, "No Proxmox connection for domain {}".format(domain)
    if domain not in inventories:
        try:
            resources = session.session.cluster.resources.get(type="vm")
            inventories[domain] = {
                int(vm["vmid"]): vm for vm in resources
            }
        except Exception as error:
            inventories[domain] = error
    inventory = inventories[domain]
    if isinstance(inventory, Exception):
        return None, "Unable to list PVE VMs: {}".format(inventory)
    return inventory, ""


def _config(session, live, row):
    node = live.get("node") or row["stored_node"]
    vm_type = live.get("type") or row["stored_type"]
    if not node or vm_type not in ("qemu", "lxc"):
        return {}, "Unable to identify the Proxmox node or VM type"
    try:
        endpoint = getattr(session.session.nodes(node), vm_type)(row["vmid"])
        return endpoint.config.get(), ""
    except Exception as error:
        return {}, "Unable to read PVE config: {}".format(error)


def classify_vms(rows, sessions, progress=None):
    inventories = {}
    results = []
    for index, row in enumerate(rows, 1):
        result = dict(row)
        result.update(
            proxmox_status="", proxmox_node=row["stored_node"] or "",
            proxmox_tags="", proxmox_comment="", cleanup_error="",
        )
        if row["vmid"] is None:
            result.update(result="Missing VMID", cleanup_status="Pending cleanup")
        else:
            inventory, error = _inventory(row["domain"], sessions, inventories)
            if error:
                result.update(
                    result="Unable to validate", cleanup_status="Pending cleanup",
                    cleanup_error=error,
                )
            else:
                live = inventory.get(int(row["vmid"]))
                if live is None:
                    result.update(
                        result="Missing in Proxmox",
                        cleanup_status="Pending cleanup",
                    )
                else:
                    config, warning = _config(sessions[row["domain"]], live, row)
                    result.update(
                        result="Present in Proxmox", cleanup_status="Kept",
                        proxmox_status=live.get("status", ""),
                        proxmox_node=live.get("node") or row["stored_node"] or "",
                        proxmox_tags=config.get("tags", live.get("tags", "")),
                        proxmox_comment=config.get("description", ""),
                        cleanup_error=warning,
                    )
        results.append(result)
        if progress and (index == len(rows) or index % 100 == 0):
            progress("Validated {}/{} NetBox VMs".format(index, len(rows)))
    return results


def cleanup_vms(results, dry_run=False, progress=None):
    targets = [
        row for row in results
        if row["result"] in CLEANUP_RESULTS
    ]
    for index, row in enumerate(targets, 1):
        if dry_run:
            row["cleanup_status"] = "Dry run"
            continue
        try:
            with transaction.atomic():
                vm = VirtualMachine.objects.get(pk=row["netbox_vm_id"])
                ProxmoxVM.objects.filter(virtual_machine_id=vm.pk).delete()
                vm.delete()
            row["cleanup_status"] = "Deleted"
        except Exception as error:
            row["cleanup_status"] = "Failed"
            row["cleanup_error"] = str(error)
        if progress and (index == len(targets) or index % 25 == 0):
            progress("Cleaned {}/{} eligible VMs".format(index, len(targets)))


def _report_values(row):
    return [
        row["netbox_vm_id"], row["vmid"], row["netbox_status"],
        row["proxmox_status"], row["tenant"], row["proxmox_node"],
        row["proxmox_tags"], row["netbox_comment"], row["proxmox_comment"],
        row["domain"], NETBOX_URL.format(row["netbox_vm_id"]),
        row["proxmox_url"] or "", row["result"], row["cleanup_status"],
        row["cleanup_error"],
    ]


def counts(results):
    values = {
        "checked": len(results), "missing_vmid": 0, "missing_in_proxmox": 0,
        "present": 0, "unable": 0, "deleted": 0, "failed": 0, "kept": 0,
        "dry_run": 0,
    }
    result_keys = {
        "Missing VMID": "missing_vmid",
        "Missing in Proxmox": "missing_in_proxmox",
        "Present in Proxmox": "present",
        "Unable to validate": "unable",
    }
    for row in results:
        values[result_keys[row["result"]]] += 1
        status = row["cleanup_status"]
        if status == "Deleted":
            values["deleted"] += 1
        elif status == "Failed":
            values["failed"] += 1
        elif status == "Kept":
            values["kept"] += 1
        elif status == "Dry run":
            values["dry_run"] += 1
    return values


def write_report(results, output):
    output = Path(output)
    report_results = [
        row for row in results
        if row["result"] in CLEANUP_RESULTS
    ]
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    details = workbook.create_sheet("VM results")
    totals = counts(results)
    summary_rows = [
        ["NetBox VM cleanup report", None],
        ["Generated UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")],
        ["NetBox VMs checked", totals["checked"]],
        ["VMs in report", len(report_results)],
        ["Missing NetBox VMID", totals["missing_vmid"]],
        ["VMID missing in Proxmox", totals["missing_in_proxmox"]],
        ["Present in Proxmox", totals["present"]],
        ["Unable to validate", totals["unable"]],
        ["Deleted", totals["deleted"]],
        ["Failed", totals["failed"]],
        ["Kept", totals["kept"]],
        ["Dry run targets", totals["dry_run"]],
    ]
    for row in summary_rows:
        summary.append(row)
    details.append(HEADERS)
    for row in report_results:
        details.append(_report_values(row))

    navy = "17365D"
    summary["A1"].font = Font(size=18, bold=True, color="FFFFFF")
    summary["A1"].fill = PatternFill("solid", fgColor=navy)
    summary.merge_cells("A1:B1")
    summary.column_dimensions["A"].width = 30
    summary.column_dimensions["B"].width = 72
    for cell in summary["A"][1:]:
        cell.font = Font(bold=True, color=navy)
    summary.sheet_view.showGridLines = False

    for cell in details[1]:
        cell.fill = PatternFill("solid", fgColor=navy)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    details.freeze_panes = "A2"
    details.auto_filter.ref = details.dimensions
    details.sheet_view.showGridLines = False
    widths = [14, 10, 14, 16, 20, 20, 35, 40, 40, 28, 55, 65, 22, 20, 55]
    for index, width in enumerate(widths, 1):
        details.column_dimensions[details.cell(1, index).column_letter].width = width
    for excel_row in details.iter_rows(min_row=2):
        for cell in (excel_row[10], excel_row[11]):
            if cell.value:
                cell.hyperlink = cell.value
                cell.style = "Hyperlink"
        for cell in excel_row[6:9] + excel_row[14:15]:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    if report_results:
        table = Table(displayName="CleanupResults", ref="A1:O{}".format(details.max_row))
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        details.add_table(table)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)


def run_cleanup(output=None, dry_run=False, progress=print):
    from netbox_proxbox.proxbox_api_v2.plugins_config import PROXMOX_SESSIONS

    output = Path(output) if output else default_output()
    rows = select_vms()
    results = classify_vms(rows, PROXMOX_SESSIONS, progress)
    write_report(results, output)
    cleanup_vms(results, dry_run, progress)
    write_report(results, output)
    return results, output
