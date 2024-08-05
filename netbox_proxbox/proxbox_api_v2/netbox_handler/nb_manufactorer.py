from django.template.defaultfilters import slugify

# import logging
import traceback

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

try:
    from dcim.models import Manufacturer

    from ..plugins_config import (
        NETBOX_NODE_ROLE_ID,
        NETBOX_SITE_ID,
        NETBOX_MANUFACTURER
    )

except Exception as e:
    # logger.exception(e)
    traceback.print_exc()
    raise e


def get_set_manufacturer():
    proxbox_manufacturer_name = NETBOX_MANUFACTURER
    proxbox_manufacturer_slug = slugify(proxbox_manufacturer_name)
    proxbox_manufacturer_desc = 'Manufacturer Proxbox will use if none is configured by user in PLUGINS_CONFIG'

    # Check if Proxbox manufacturer already exists.
    proxbox_manufacturer = Manufacturer.objects.filter(name=proxbox_manufacturer_name).first()

    if proxbox_manufacturer is None:
        try:
            # If Proxbox manufacturer does not exist, create one.
            manufacturer = Manufacturer(
                name=proxbox_manufacturer_name,
                slug=proxbox_manufacturer_slug,
                description=proxbox_manufacturer_desc
            )
            manufacturer.save()
        except Exception as e:
            # logger.exception(e)
            # traceback.print_exc()
            print(e)
            return "Error creating the '{0}' manufacturer. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
                proxbox_manufacturer_name, proxbox_manufacturer_slug)

    else:
        manufacturer = proxbox_manufacturer

    return manufacturer
