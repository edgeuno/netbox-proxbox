from .nb_manufactorer import get_set_manufacturer
from .nb_tag import tag

# import logging
import traceback

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

try:
    from dcim.models import DeviceType

    from ..plugins_config import (
        NETBOX_NODE_ROLE_ID,
        NETBOX_SITE_ID,
        NETBOX_MANUFACTURER
    )

except Exception as e:
    # logger.exception(e)
    traceback.print_exc()
    raise e


def upsert_device_type():
    proxbox_device_type_model = 'Proxbox Model'
    proxbox_device_type_slug = 'proxbox-model'
    proxbox_device_type_comments = "Device Type Proxbox will use when creating the Cluster's Nodes. When the Node is created, you can change the device type to the actual server model."

    # Check if Proxbox manufacturer already exists.
    proxbox_device_types = DeviceType.objects.filter(
        model=proxbox_device_type_model,
        slug=proxbox_device_type_slug
    ).first()
    manufacturer = get_set_manufacturer()
    if proxbox_device_types is None:
        try:
            # If Proxbox manufacturer does not exist, create one.
            device_type = DeviceType(
                manufacturer_id=manufacturer.id,
                manufacturer=manufacturer,
                model=proxbox_device_type_model,
                slug=proxbox_device_type_slug,
                comments=proxbox_device_type_comments,
                tags=[tag().id]
            )
            device_type.save()
        except Exception as e:
            msg = "Error creating the '{0}' device type. Possible errors: the model '{0}' or slug '{1}' is already used.".format(
                proxbox_device_type_model, proxbox_device_type_slug)
            print(msg)
            print(e)
            # traceback.print_exc()
            # logger.exception(e)
            return msg

    else:
        try:
            proxbox_device_types.manufacturer_id = manufacturer.id
            proxbox_device_types.manufacturer = manufacturer
            proxbox_device_types.save()
        except Exception as e:
            print(e)
            print("Error: proxbox_device_types-device_type - {}".format(e))
            # logger.exception(e)
            # traceback.print_exc()
        device_type = proxbox_device_types

    return device_type
