import random
import re
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.template.defaultfilters import slugify
from tenancy.models import (
    Contact,
    ContactAssignment,
    ContactRole,
    Tenant,
    TenantGroup,
)

from netbox_proxbox.models import ProxmoxVM

from .ai_tenant import _choose_tenant, _registered_candidates, provider_factory
from .nb_tag import validate_custom_tag
from .nb_virtualmachine import (
    client_tenant_parser,
    get_vm_by_unique_name_cluster_tenant,
    set_contact_to_vm,
    set_tenant,
)


COMPANY_WORDS = {
    "company",
    "communications",
    "corp",
    "corporation",
    "group",
    "inc",
    "limited",
    "llc",
    "ltd",
    "partners",
    "sa",
    "sas",
    "services",
    "solutions",
    "systems",
    "technology",
    "technologies",
    "telecom",
}
DOMAIN_NOISE = {"co", "com", "io", "mail", "net", "org", "www"}
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "icloud.com",
    "outlook.com",
    "protonmail.com",
    "yahoo.com",
}
CLIENT_ID_RE = re.compile(
    r"\bclient\s*:.*?\(\s*id\s*:\s*(\d+)\s*\)", re.IGNORECASE
)
CANDIDATE_RE = re.compile(
    r"\bclient\s*:\s*(.*?)\s*\(([^()]+)\)\s*"
    r"\(\s*id\s*:\s*\d+\s*\)",
    re.IGNORECASE,
)
CUSTOMER_TAG_RE = re.compile(r"(?:^|-)cust-(\d+)$", re.IGNORECASE)
EMAIL_RE = re.compile(r"\bemail\s*:\s*[^\s@]+@([^\s;]+)", re.IGNORECASE)
EXTERNAL_REQUEST_RETRIES = 10
MAX_RETRY_DELAY_SECONDS = 30


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

    raw_contacts = data.get("contacts", [])
    if not isinstance(raw_contacts, list):
        raise ValueError("Tenant enrichment contacts must be an array")
    contacts = []
    seen_emails = set()
    for raw_contact in raw_contacts:
        if not isinstance(raw_contact, dict):
            continue
        email = raw_contact.get("email")
        contact_name = raw_contact.get("name")
        phone = raw_contact.get("phone")
        if not isinstance(email, str) or not isinstance(contact_name, str):
            continue
        email = email.strip()
        contact_name = contact_name.strip()
        phone = phone.strip() if isinstance(phone, str) else phone
        if (
            not email
            or not contact_name
            or (phone is not None and not isinstance(phone, str))
        ):
            continue
        try:
            validate_email(email)
        except ValidationError:
            continue
        if any(
            value and len(value) > Contact._meta.get_field(field).max_length
            for field, value in (
                ("email", email),
                ("name", contact_name),
                ("phone", phone),
            )
        ):
            continue
        email_key = email.casefold()
        if email_key in seen_emails:
            continue
        seen_emails.add(email_key)
        contacts.append({"email": email, "name": contact_name, "phone": phone})
    return {
        "name": name,
        "contacts": contacts,
        "skipped_contacts": len(raw_contacts) - len(contacts),
    }


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


def _retry_after_seconds(error):
    response = getattr(error, "response", None)
    value = response.headers.get("Retry-After") if response is not None else None
    if not value:
        return 0
    try:
        return max(0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0


def _is_retryable_request_error(error):
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    if not isinstance(error, requests.HTTPError) or error.response is None:
        return False
    status = error.response.status_code
    return status == 429 or 500 <= status <= 599


def _call_with_retry(service, vm_id, function, *args):
    for retry in range(EXTERNAL_REQUEST_RETRIES + 1):
        try:
            return function(*args)
        except Exception as error:
            if retry == EXTERNAL_REQUEST_RETRIES or not _is_retryable_request_error(
                error
            ):
                raise
            backoff = min(2**retry, MAX_RETRY_DELAY_SECONDS)
            delay = min(
                backoff + random.uniform(0, backoff * 0.25),
                MAX_RETRY_DELAY_SECONDS,
            )
            delay = max(delay, _retry_after_seconds(error))
            print(
                "[TENANT ENRICHMENT] {} retry {}/{} for VM {} in {:.1f}s: {}".format(
                    service,
                    retry + 1,
                    EXTERNAL_REQUEST_RETRIES,
                    vm_id,
                    delay,
                    error,
                )
            )
            time.sleep(delay)


def _apply_enrichment(vm, enrichment, tenant, confidence, override, stats):
    created = False
    if tenant is None:
        tenant, created = _create_tenant(enrichment["name"])

    vm.refresh_from_db(fields=["tenant"])
    if not override and vm.tenant_id is not None:
        return
    conflict = get_vm_by_unique_name_cluster_tenant(vm, tenant.id)
    if conflict is not None:
        raise ValueError(
            "VM name, cluster, and tenant conflict with VM {}".format(conflict.id)
        )
    vm.tenant_id = tenant.id
    vm.tenant = tenant
    vm.save()
    stats["assigned"] += 1
    stats["created"] += int(created)
    contact_stats = _sync_contacts(tenant, enrichment["contacts"], vm.id)
    for key, value in contact_stats.items():
        stats[key] += value
    print(
        "[TENANT ENRICHMENT] VM {} assigned to tenant {} (ID {}, "
        "created={}, ai_confidence={!r}).".format(
            vm.id, tenant.name, tenant.id, created, confidence
        )
    )


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
    max_length = Tenant._meta.get_field("name").max_length
    if max_length and len(name) > max_length:
        raise ValueError("Tenant name is too long")
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


def _sync_contacts(tenant, contacts, vm_id):
    stats = {
        "contacts_created": 0,
        "contacts_updated": 0,
        "contacts_assigned": 0,
        "contact_errors": 0,
    }
    if not contacts:
        return stats

    try:
        role = ContactRole.objects.filter(
            name__iexact="Maintenance Management"
        ).first()
        if role is None:
            role, _ = ContactRole.objects.get_or_create(
                slug="maintenance-management",
                defaults={"name": "Maintenance Management"},
            )
        object_type = ContentType.objects.get_for_model(Tenant)
    except Exception as error:
        stats["contact_errors"] = len(contacts)
        print(
            "[TENANT ENRICHMENT] Contact setup failed for VM {}: {}".format(
                vm_id, error
            )
        )
        return stats

    for index, data in enumerate(contacts, start=1):
        try:
            matches = list(Contact.objects.filter(email__iexact=data["email"])[:2])
            if len(matches) > 1:
                raise ValueError("multiple NetBox contacts use this email")
            if matches:
                contact = matches[0]
                changed = False
                if contact.name != data["name"]:
                    contact.name = data["name"]
                    changed = True
                if data["phone"] and contact.phone != data["phone"]:
                    contact.phone = data["phone"]
                    changed = True
                if changed:
                    contact.save()
                    stats["contacts_updated"] += 1
            else:
                contact = Contact.objects.create(
                    name=data["name"],
                    email=data["email"],
                    phone=data["phone"] or "",
                )
                stats["contacts_created"] += 1

            assignment, assignment_created = ContactAssignment.objects.get_or_create(
                object_type=object_type,
                object_id=tenant.id,
                contact=contact,
                role=role,
                defaults={"priority": "primary"},
            )
            if assignment_created:
                stats["contacts_assigned"] += 1
            elif assignment.priority != "primary":
                assignment.priority = "primary"
                assignment.save()
        except Exception as error:
            stats["contact_errors"] += 1
            print(
                "[TENANT ENRICHMENT] Contact {} failed for VM {}: {}".format(
                    index, vm_id, error
                )
            )
    return stats


def _words(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", ascii_value)


def _company_marker(words):
    legal_suffixes = {"".join(words[-size:]) for size in (2, 3)}
    return bool(COMPANY_WORDS.intersection(words)) or bool(
        legal_suffixes.intersection({"sa", "sas"})
    )


def _looks_like_person(value):
    words = _words(value)
    return (
        2 <= len(words) <= 4
        and all(word.isalpha() for word in words)
        and not _company_marker(words)
    )


def _email_domain(comment):
    match = EMAIL_RE.search(comment or "")
    return match.group(1).strip(".,)").lower() if match else None


def _tenant_candidates(comment):
    match = CANDIDATE_RE.search(comment or "")
    if match is None:
        return client_tenant_parser(comment or "")
    outside_name, inside_name = (value.strip() for value in match.groups())
    return inside_name, outside_name


def _domain_matches_name(domain, name):
    if not domain or domain in PUBLIC_EMAIL_DOMAINS:
        return False
    labels = [label for label in domain.split(".") if label not in DOMAIN_NOISE]
    words = _words(name)
    if not labels or not words:
        return False
    joined = "".join(words)
    acronym = "".join(word[0] for word in words)
    variants = set(words + [joined])
    variants.update(acronym[:size] for size in range(2, len(acronym) + 1))
    return any(label in variants for label in labels)


def _local_company(legacy_tenant, legacy_contact, domain):
    candidates = (legacy_tenant, legacy_contact)
    domain_matches = [
        name for name in candidates if _domain_matches_name(domain, name)
    ]
    domain_choice = domain_matches[0] if len(domain_matches) == 1 else None

    marked = [name for name in candidates if _company_marker(_words(name))]
    if len(marked) == 1:
        name_choice = marked[0]
    else:
        people = [name for name in candidates if _looks_like_person(name)]
        name_choice = (
            next((name for name in candidates if name not in people), None)
            if len(people) == 1
            else None
        )

    if domain_choice and name_choice and _words(domain_choice) == _words(name_choice):
        return domain_choice
    return None


def _group_keys(comment, tags):
    client_match = CLIENT_ID_RE.search(comment or "")
    client_id = client_match.group(1) if client_match else None
    tag_ids = {
        match.group(1)
        for tag in tags
        for match in [CUSTOMER_TAG_RE.search(tag)]
        if match
    }
    tag_id = next(iter(tag_ids)) if len(tag_ids) == 1 else None
    keys = set()
    if not (client_id and tag_id and client_id != tag_id):
        if client_id:
            keys.add(("customer", client_id))
        if tag_id:
            keys.add(("customer", tag_id))
    domain = _email_domain(comment)
    if domain and domain not in PUBLIC_EMAIL_DOMAINS:
        keys.add(("domain", domain))
    return keys


def _assign_tenant(vm, tenant):
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


def _sync_local_contact(vm, tenant, contact_name):
    match = EMAIL_RE.search(vm.comments or "")
    if not match:
        return {
            "contacts_created": 0,
            "contacts_updated": 0,
            "contacts_assigned": 0,
            "contact_errors": 0,
        }
    email = match.group(0).split(":", 1)[1].strip()
    validate_email(email)
    matches = list(Contact.objects.filter(email__iexact=email)[:2])
    if len(matches) > 1:
        raise ValueError("multiple NetBox contacts use this email")
    created = updated = 0
    if matches:
        contact = matches[0]
        if contact.name != contact_name:
            contact.name = contact_name
            contact.save()
            updated = 1
    else:
        contact = Contact.objects.create(name=contact_name, email=email)
        created = 1
    role = ContactRole.objects.filter(name__iexact="vm").first()
    if role is None:
        role, _ = ContactRole.objects.get_or_create(
            slug="vm", defaults={"name": "vm"}
        )
    assigned = 0
    for obj in (tenant, vm):
        object_type = ContentType.objects.get_for_model(obj)
        _, was_created = ContactAssignment.objects.get_or_create(
            object_type=object_type,
            object_id=obj.id,
            contact=contact,
            role=role,
            defaults={"priority": "primary"},
        )
        assigned += int(was_created)
    return {
        "contacts_created": created,
        "contacts_updated": updated,
        "contacts_assigned": assigned,
        "contact_errors": 0,
    }


def _legacy_fallback(vm):
    vm = set_tenant(vm, vm.comments or "")
    set_contact_to_vm(vm.comments or "", vm)
    return vm


def _run_legacy_fallback(vm, stats, reason):
    try:
        _legacy_fallback(vm)
        stats["legacy_fallback"] += 1
        print(
            "[TENANT OVERRIDE] VM {} used legacy fallback: {}".format(
                vm.id, reason
            )
        )
    except Exception as error:
        stats["errors"] += 1
        print("[TENANT OVERRIDE] VM {} legacy fallback failed: {}".format(vm.id, error))


def run_tenant_enrichment(
    job_id, settings=None, ai_settings=None, provider=None, override=False
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
        "contacts_created": 0,
        "contacts_updated": 0,
        "contacts_assigned": 0,
        "contacts_skipped": 0,
        "contact_errors": 0,
        "configured_tenant": 0,
        "legacy_fallback": 0,
    }
    if not settings.get("enabled", False):
        return stats

    ai_enabled = ai_settings.get("enabled", False)
    filters = {
        "latest_job": str(job_id),
        "virtual_machine__isnull": False,
    }
    if not override:
        filters["virtual_machine__tenant__isnull"] = True
    proxbox_vms = (
        ProxmoxVM.objects.filter(**filters)
        .select_related("virtual_machine")
        .prefetch_related("virtual_machine__tags")
    )

    rows = []
    seen = set()
    for proxbox_vm in proxbox_vms:
        vm = proxbox_vm.virtual_machine
        if vm.id in seen:
            continue
        seen.add(vm.id)
        match_name = getattr(proxbox_vm, "name", None) or vm.name
        if override and validate_custom_tag(match_name):
            stats["configured_tenant"] += 1
            continue
        stats["eligible"] += 1
        try:
            tags = sorted(tag.name for tag in vm.tags.all())
            rows.append((vm, tags))
        except Exception as error:
            stats["errors"] += 1
            print(
                "[TENANT ENRICHMENT] VM {} was not changed: {}".format(
                    vm.id, error
                )
            )
            if override:
                _run_legacy_fallback(vm, stats, error)

    ai_provider = provider
    workers = settings.get("batch_size", 10) if override else 1
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {}
        remaining = iter(rows)

        def submit_tenant_request():
            try:
                vm, tags = next(remaining)
            except StopIteration:
                return
            if override:
                future = executor.submit(
                    _call_with_retry,
                    "tenant request",
                    vm.id,
                    _request_tenant,
                    settings,
                    vm,
                    tags,
                )
            else:
                future = executor.submit(_request_tenant, settings, vm, tags)
            pending[future] = ("tenant", vm, tags, None)

        for _ in range(workers):
            submit_tenant_request()

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                stage, vm, tags, enrichment = pending.pop(future)
                if stage == "ai":
                    try:
                        tenant, confidence = future.result()
                    except Exception as error:
                        tenant, confidence = None, None
                        print(
                            "[TENANT ENRICHMENT] AI lookup failed for VM {}: {}".format(
                                vm.id, error
                            )
                        )
                    try:
                        _apply_enrichment(
                            vm,
                            enrichment,
                            tenant,
                            confidence,
                            override,
                            stats,
                        )
                    except Exception as error:
                        stats["errors"] += 1
                        print(
                            "[TENANT ENRICHMENT] VM {} was not changed: {}".format(
                                vm.id, error
                            )
                        )
                        if override:
                            _run_legacy_fallback(vm, stats, error)
                    submit_tenant_request()
                    continue

                try:
                    enrichment = future.result()
                    if enrichment is None:
                        stats["no_match"] += 1
                        if override:
                            _run_legacy_fallback(
                                vm, stats, "enrichment returned no_match"
                            )
                        submit_tenant_request()
                        continue
                    tenant_name = enrichment["name"]
                    stats["contacts_skipped"] += enrichment["skipped_contacts"]
                    tenant = _find_exact_tenant(tenant_name)
                    if tenant is None and ai_enabled:
                        try:
                            candidates = _registered_candidates([tenant_name])
                            if candidates:
                                ai_provider = ai_provider or provider_factory(
                                    ai_settings
                                )
                                args = (
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
                                if override:
                                    ai_future = executor.submit(
                                        _call_with_retry,
                                        "AI request",
                                        vm.id,
                                        _choose_tenant,
                                        *args,
                                    )
                                else:
                                    ai_future = executor.submit(_choose_tenant, *args)
                                pending[ai_future] = ("ai", vm, tags, enrichment)
                                continue
                        except Exception as error:
                            print(
                                "[TENANT ENRICHMENT] AI lookup failed for VM {}: {}".format(
                                    vm.id, error
                                )
                            )
                    _apply_enrichment(
                        vm, enrichment, tenant, None, override, stats
                    )
                except Exception as error:
                    stats["errors"] += 1
                    print(
                        "[TENANT ENRICHMENT] VM {} was not changed: {}".format(
                            vm.id, error
                        )
                    )
                    if override:
                        _run_legacy_fallback(vm, stats, error)
                submit_tenant_request()

    print(
        "[TENANT ENRICHMENT] Finished: eligible={eligible}, no_match={no_match}, "
        "assigned={assigned}, created={created}, errors={errors}, "
        "contacts_created={contacts_created}, contacts_updated={contacts_updated}, "
        "contacts_assigned={contacts_assigned}, contacts_skipped={contacts_skipped}, "
        "contact_errors={contact_errors}, configured_tenant={configured_tenant}, "
        "legacy_fallback={legacy_fallback}.".format(**stats)
    )
    return stats


def run_local_tenant_assignment(job_id):
    stats = {
        "eligible": 0,
        "assigned": 0,
        "created": 0,
        "local_classification": 0,
        "group_consensus": 0,
        "configured_tenant": 0,
        "legacy_fallback": 0,
        "contacts_created": 0,
        "contacts_updated": 0,
        "contacts_assigned": 0,
        "contact_errors": 0,
        "errors": 0,
    }
    proxbox_vms = (
        ProxmoxVM.objects.filter(
            latest_job=str(job_id), virtual_machine__isnull=False
        )
        .select_related("virtual_machine")
        .prefetch_related("virtual_machine__tags")
    )
    rows = []
    seen = set()
    for proxbox_vm in proxbox_vms:
        vm = proxbox_vm.virtual_machine
        if vm.id in seen:
            continue
        seen.add(vm.id)
        match_name = getattr(proxbox_vm, "name", None) or vm.name
        if validate_custom_tag(match_name):
            stats["configured_tenant"] += 1
            continue
        legacy_tenant, legacy_contact = _tenant_candidates(vm.comments or "")
        if not legacy_tenant or not legacy_contact:
            _run_legacy_fallback(vm, stats, "description is not parseable")
            continue
        tags = sorted(tag.name for tag in vm.tags.all())
        company = _local_company(
            legacy_tenant, legacy_contact, _email_domain(vm.comments)
        )
        rows.append(
            {
                "vm": vm,
                "candidates": (legacy_tenant, legacy_contact),
                "company": company,
                "keys": _group_keys(vm.comments, tags),
            }
        )
        stats["eligible"] += 1

    resolved_by_group = defaultdict(list)
    for row in rows:
        if row["company"]:
            for key in row["keys"]:
                resolved_by_group[key].append(row["company"])
    consensus = {}
    for key, names in resolved_by_group.items():
        normalized = {tuple(_words(name)) for name in names}
        if len(names) >= 2 and len(normalized) == 1:
            consensus[key] = normalized.pop()

    for row in rows:
        vm = row["vm"]
        company = row["company"]
        source = "local_classification"
        if company is None:
            proposals = {consensus[key] for key in row["keys"] if key in consensus}
            matches = [
                candidate
                for candidate in row["candidates"]
                if tuple(_words(candidate)) in proposals
            ]
            if (
                len(proposals) == 1
                and matches
                and len({tuple(_words(name)) for name in matches}) == 1
            ):
                company = matches[0]
                source = "group_consensus"
        if company is None:
            _run_legacy_fallback(vm, stats, "local evidence is insufficient")
            continue

        contacts = [
            name
            for name in row["candidates"]
            if tuple(_words(name)) != tuple(_words(company))
        ]
        if not contacts:
            _run_legacy_fallback(
                vm, stats, "tenant and contact are indistinguishable"
            )
            continue
        contact_name = contacts[0]
        try:
            tenant, created = _create_tenant(company)
            _assign_tenant(vm, tenant)
            stats["assigned"] += 1
            stats["created"] += int(created)
            stats[source] += 1
            print(
                "[TENANT OVERRIDE] VM {} assigned to {} using {}.".format(
                    vm.id, tenant.name, source
                )
            )
            try:
                contact_stats = _sync_local_contact(
                    vm, tenant, contact_name
                )
                for key, value in contact_stats.items():
                    stats[key] += value
            except Exception as error:
                stats["contact_errors"] += 1
                print(
                    "[TENANT OVERRIDE] Contact failed for VM {}: {}".format(
                        vm.id, error
                    )
                )
        except Exception as error:
            stats["errors"] += 1
            _run_legacy_fallback(vm, stats, error)

    print(
        "[TENANT OVERRIDE] Finished: "
        + ", ".join("{}={}".format(key, value) for key, value in stats.items())
        + "."
    )
    return stats


def run_override_tenant_assignment(
    job_id, enrichment_settings=None, ai_settings=None, provider=None
):
    if enrichment_settings is None or ai_settings is None:
        from ..plugins_config import AI_TENANT_SETTINGS, TENANT_ENRICHMENT_SETTINGS

        enrichment_settings = enrichment_settings or TENANT_ENRICHMENT_SETTINGS
        ai_settings = ai_settings or AI_TENANT_SETTINGS
    if enrichment_settings.get("enabled", False):
        return run_tenant_enrichment(
            job_id,
            enrichment_settings,
            ai_settings,
            provider,
            override=True,
        )
    return run_local_tenant_assignment(job_id)
