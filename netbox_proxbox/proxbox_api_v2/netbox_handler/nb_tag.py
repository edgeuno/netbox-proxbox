import colorsys
import hashlib
import re

from django.template.defaultfilters import slugify

from netbox_proxbox.proxbox_api_v2.plugins_config import NETBOX_TENANT_REGEX_VALIDATOR, NETBOX_TENANT_NAME, \
    NETBOX_TENANT_DESCRIPTION

# import logging
import traceback

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

try:
    from extras.models import Tag

except Exception as e:
    # logger.exception(e)
    traceback.print_exc()
    raise e


#
def validate_custom_tag(name):
    has_string = False
    try:
        rgx = r"" + NETBOX_TENANT_REGEX_VALIDATOR
        matches = re.finditer(rgx, name, re.MULTILINE | re.IGNORECASE)
        it = matches.__next__()
        it.group().lower().strip()
        has_string = True
    except Exception as e:
        pass
    return has_string


def custom_tag(tag_name="Proxbox", tag_slug="proxbox", tag_description="No description", color='ff5722'):
    try:
        output, _ = Tag.objects.get_or_create(
            slug=tag_slug,
            defaults={
                "name": tag_name,
                "color": color,
                "description": tag_description,
            },
        )
        return output
    except Exception as e:
        output = Tag.objects.filter(name__iexact=tag_name).first()
        if output is not None:
            return output
        print(e)
        print("Error creating the '{0}' tag. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
            tag_name, tag_slug))
        return None


#
# extras.tags
#
def tag():
    proxbox_tag_name = 'Proxbox'
    proxbox_tag_slug = 'proxbox'
    description = "Proxbox Identifier (used to identify the items the plugin created)"
    return custom_tag(proxbox_tag_name, proxbox_tag_slug, description)


PROXMOX_TAG_PREFIX = "proxmox-"


def parse_proxmox_tags(value):
    if value is None:
        value = ""
    if not isinstance(value, str):
        return None

    tags = []
    seen = set()
    for tag_name in value.split(";"):
        tag_name = tag_name.strip()
        key = tag_name.lower()
        if tag_name and key not in seen:
            tags.append(tag_name)
            seen.add(key)
    return tags


def proxmox_tags_from(proxmox_vm, config):
    data = getattr(proxmox_vm, "data", None)
    if isinstance(data, dict) and "tags" in data:
        tags = parse_proxmox_tags(data["tags"])
        if tags is not None:
            return tags
    if isinstance(config, dict):
        return parse_proxmox_tags(config.get("tags"))
    return None


def proxmox_tag_slug(tag_name):
    source = tag_name.strip().lower()
    tag_slug = slugify(source) or "tag"
    if not re.fullmatch(r"[a-z0-9_-]+", source):
        tag_slug = "{}-{}".format(
            tag_slug, hashlib.sha256(source.encode()).hexdigest()[:8]
        )
    return PROXMOX_TAG_PREFIX + tag_slug


def proxmox_tag_color(tag_name):
    source = tag_name.strip().lower()
    letters = "".join(char for char in source if char.isascii() and char.isalpha())
    if not letters:
        return "a0a0a0"

    hue = int.from_bytes(hashlib.sha256(letters.encode()).digest(), "big") % 360
    level = min(max(len([part for part in source.split("-") if part]) - 1, 0), 5)
    saturation = (50 + 5 * level) / 100
    brightness = (75 - 5 * level) / 100
    rgb = colorsys.hsv_to_rgb(hue / 360, saturation, brightness)
    return "".join("{:02x}".format(round(value * 255)) for value in rgb)


def sync_proxmox_tags(netbox_vm, tag_names):
    desired_slugs = set()
    for tag_name in tag_names:
        tag_slug = proxmox_tag_slug(tag_name)
        desired_slugs.add(tag_slug)
        tag_obj = custom_tag(
            tag_name,
            tag_slug,
            "Imported from Proxmox",
            proxmox_tag_color(tag_name),
        )
        if tag_obj is not None:
            netbox_vm.tags.add(tag_obj)

    for tag_obj in netbox_vm.tags.filter(slug__startswith=PROXMOX_TAG_PREFIX):
        if tag_obj.slug not in desired_slugs:
            netbox_vm.tags.remove(tag_obj)


def base_tag(netbox_vm, proxmox_tags=None, match_name=None):
    # Get current tags
    tags = netbox_vm.tags.all()

    # Get tag names from tag objects
    tags_name = []
    for c_tag in tags:
        tags_name.append(c_tag.name)

    # If Proxbox not found int Netbox tag's list, update object with the tag.
    sve_custom = False
    p_tag = tag()
    if p_tag.name not in tags_name:
        netbox_vm.tags.add(p_tag)
        # Save new tag to object
        sve_custom = True

    # custom edgeuno tags

    has_string = validate_custom_tag(match_name or netbox_vm.name)

    customer_tag_name = "Customer"
    customer_tag_slug = "customer"
    customer_observation = "The vm belongs to a customer"
    customer_tag = custom_tag(customer_tag_name, customer_tag_slug, customer_observation)

    if NETBOX_TENANT_NAME is not None:
        e1_tag_name = NETBOX_TENANT_NAME
        e1_tag_slug = slugify(NETBOX_TENANT_NAME)
        e1_observation = NETBOX_TENANT_DESCRIPTION
        e1_tag = custom_tag(e1_tag_name, e1_tag_slug, e1_observation)

        if has_string and NETBOX_TENANT_NAME is not None:
            if customer_tag in tags:
                netbox_vm.tags.remove(customer_tag)
            if e1_tag not in tags:
                netbox_vm.tags.add(e1_tag)
                sve_custom = True
        else:
            if e1_tag in tags:
                netbox_vm.tags.remove(e1_tag)
            if customer_tag not in tags:
                netbox_vm.tags.add(customer_tag)
                sve_custom = True

    if proxmox_tags is not None:
        sync_proxmox_tags(netbox_vm, proxmox_tags)


    if sve_custom:
        netbox_vm.save()

    return netbox_vm
