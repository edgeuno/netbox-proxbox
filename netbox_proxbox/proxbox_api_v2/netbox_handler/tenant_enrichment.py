import requests
from django.db import IntegrityError
from django.template.defaultfilters import slugify
from tenancy.models import Tenant, TenantGroup

from netbox_proxbox.models import ProxmoxVM

from .ai_tenant import _choose_tenant, _registered_candidates, provider_factory
from .nb_virtualmachine import get_vm_by_unique_name_cluster_tenant


def _parse_response(data):
    if not isinstance(data, dict):
        raise ValueError("Tenant enrichment response must be an object")
    status = data.get("status")
    if status == "no_match":
        return None
    if status != "matched":
        raise ValueError("Unsupported tenant enrichment status")
    tenant = data.get("tenant")
    name = tenant.get("name") if isinstance(tenant, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Tenant enrichment response is missing tenant.name")
    name = name.strip()
    max_length = Tenant._meta.get_field("name").max_length
    if max_length and len(name) > max_length:
        raise ValueError("Tenant enrichment name is too long")
    return name


def _request_tenant(settings, vm, tags):
    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["Authorization"] = "Bearer {}".format(settings["api_key"])
    response = requests.post(
        settings["url"],
        headers=headers,
        json={
            "schema_version": 1,
            "vm": {
                "name": vm.name,
                "comment": vm.comments or "",
                "tags": tags,
            },
        },
        timeout=settings["timeout_seconds"],
    )
    response.raise_for_status()
    return _parse_response(response.json())


def _tenant_slug(name):
    max_length = Tenant._meta.get_field("slug").max_length
    value = slugify(name)
    if max_length:
        value = value[:max_length].rstrip("-")
    if not value:
        raise ValueError("Tenant enrichment name does not produce a valid slug")
    return value


def _find_exact_tenant(name):
    matches = list(Tenant.objects.filter(name__iexact=name)[:2])
    if len(matches) > 1:
        raise ValueError("Multiple tenants have the enriched name")
    if matches:
        return matches[0]
    matches = list(Tenant.objects.filter(slug=_tenant_slug(name))[:2])
    if len(matches) > 1:
        raise ValueError("Multiple tenants have the enriched slug")
    return matches[0] if matches else None


def _create_tenant(name):
    existing = _find_exact_tenant(name)
    if existing:
        return existing, False
    group = TenantGroup.objects.filter(name__iexact="Customers").first()
    if group is None:
        group, _ = TenantGroup.objects.get_or_create(
            slug="customers", defaults={"name": "Customers"}
        )
    try:
        return Tenant.objects.create(
            name=name, slug=_tenant_slug(name), group=group
        ), True
    except IntegrityError:
        existing = _find_exact_tenant(name)
        if existing:
            return existing, False
        raise


def run_tenant_enrichment(
    job_id, settings=None, ai_settings=None, provider=None
):
    if settings is None or ai_settings is None:
        from ..plugins_config import AI_TENANT_SETTINGS, TENANT_ENRICHMENT_SETTINGS

        settings = settings or TENANT_ENRICHMENT_SETTINGS
        ai_settings = ai_settings or AI_TENANT_SETTINGS

    stats = {
        "eligible": 0,
        "no_match": 0,
        "assigned": 0,
        "created": 0,
        "errors": 0,
    }
    if not settings.get("enabled", False):
        return stats

    ai_enabled = ai_settings.get("enabled", False)
    ai_provider = provider or (provider_factory(ai_settings) if ai_enabled else None)
    proxbox_vms = ProxmoxVM.objects.filter(
        latest_job=str(job_id),
        virtual_machine__isnull=False,
        virtual_machine__tenant__isnull=True,
    ).select_related("virtual_machine").prefetch_related("virtual_machine__tags")

    seen = set()
    for proxbox_vm in proxbox_vms:
        vm = proxbox_vm.virtual_machine
        if vm.id in seen:
            continue
        seen.add(vm.id)
        stats["eligible"] += 1
        try:
            tags = sorted(tag.name for tag in vm.tags.all())
            tenant_name = _request_tenant(settings, vm, tags)
            if tenant_name is None:
                stats["no_match"] += 1
                continue

            tenant = _find_exact_tenant(tenant_name)
            confidence = None
            if tenant is None and ai_enabled:
                try:
                    candidates = _registered_candidates([tenant_name])
                    if candidates:
                        tenant, confidence = _choose_tenant(
                            ai_provider,
                            vm.name,
                            vm.comments or "",
                            candidates,
                            ai_settings["minimum_confidence"],
                            {
                                "external_tenant_name": tenant_name,
                                "tags": tags,
                            },
                        )
                except Exception as error:
                    print(
                        "[TENANT ENRICHMENT] AI lookup failed for VM {}: {}".format(
                            vm.id, error
                        )
                    )

            created = False
            if tenant is None:
                tenant, created = _create_tenant(tenant_name)

            vm.refresh_from_db(fields=["tenant"])
            if vm.tenant_id is not None:
                continue
            conflict = get_vm_by_unique_name_cluster_tenant(vm, tenant.id)
            if conflict is not None:
                raise ValueError(
                    "VM name, cluster, and tenant conflict with VM {}".format(
                        conflict.id
                    )
                )
            vm.tenant_id = tenant.id
            vm.tenant = tenant
            vm.save()
            stats["assigned"] += 1
            stats["created"] += int(created)
            print(
                "[TENANT ENRICHMENT] VM {} assigned to tenant {} (ID {}, "
                "created={}, ai_confidence={!r}).".format(
                    vm.id, tenant.name, tenant.id, created, confidence
                )
            )
        except Exception as error:
            stats["errors"] += 1
            print(
                "[TENANT ENRICHMENT] VM {} was not changed: {}".format(
                    vm.id, error
                )
            )

    print(
        "[TENANT ENRICHMENT] Finished: eligible={eligible}, no_match={no_match}, "
        "assigned={assigned}, created={created}, errors={errors}.".format(**stats)
    )
    return stats
