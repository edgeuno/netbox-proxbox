from django.template.defaultfilters import slugify
import re

from netbox_proxbox.proxbox_api_v2.plugins_config import NETBOX_TENANT_REGEX_VALIDATOR, NETBOX_TENANT_NAME, \
    NETBOX_TENANT_DESCRIPTION

try:
    from extras.models import Tag

except Exception as e:
    print(e)
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
    # Check if Proxbox tag already exists.
    proxbox_tag = Tag.objects.filter(slug=tag_slug).first()

    if proxbox_tag is None:
        try:
            # If Proxbox tag does not exist, create one.
            output = Tag(
                name=tag_name,
                slug=tag_slug,
                color=color,
                description=tag_description
            )
            output.save()
        except Exception as e:
            print(e)
            print("Error creating the '{0}' tag. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
                tag_name, tag_slug))
            return None
    else:
        output = proxbox_tag

    return output


#
# extras.tags
#
def tag():
    proxbox_tag_name = 'Proxbox'
    proxbox_tag_slug = 'proxbox'
    description = "Proxbox Identifier (used to identify the items the plugin created)"
    return custom_tag(proxbox_tag_name, proxbox_tag_slug, description)


def base_tag(netbox_vm, other_tags=None):
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

    has_string = validate_custom_tag(netbox_vm.name)

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

    if other_tags is not None:
        for t in other_tags:
            try:
                custom_tag_name = t
                custom_tag_slug = t.replace(" ", "_").lower()
                custom_tag_obj = custom_tag(custom_tag_name, custom_tag_slug, t)
                if custom_tag_obj.id not in tags:
                    netbox_vm.tags.add(custom_tag)
                    sve_custom = True
            except Exception as e:
                print("Error: base_tag-other_tags - {}".format(e))
                print(e)

    if sve_custom:
        netbox_vm.save()

    return netbox_vm
