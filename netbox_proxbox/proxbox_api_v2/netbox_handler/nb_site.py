
# import logging
import traceback

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

try:
    from dcim.models import Site
    from .nb_tag import tag
    from ..plugins_config import (
        NETBOX_NODE_ROLE_ID,
        NETBOX_SITE_ID,
        NETBOX_MANUFACTURER
    )

except Exception as e:
    # logger.exception(e)
    traceback.print_exc()
    raise e


def upsert_site(**kwargs):
    """
    TODO: Improve this function
    """
    # If site_id equals to 0, consider it is not configured by user and must be created by Proxbox
    site_id = kwargs.get('site_id', 0)
    site_name = kwargs.get('site_name', None)
    if site_name:
        site = Site.objects.filter(name=site_name).first()
        if site:
            return site

    if not isinstance(site_id, int):
        return 'Site ID must be INTEGER. Netbox PLUGINS_CONFIG is configured incorrectly.'

    # If user configured SITE_ID in Netbox's PLUGINS_CONFIG, use it.
    if site_id > 0:
        site = Site.objects.filter(id=site_id).first()

        if site is None:
            return "Role ID of Virtual Machine or Node invalid. Maybe the ID passed does not exist or it is not a integer!"

    elif site_id == 0:
        site_proxbox_name = "Proxbox Basic Site"
        site_proxbox_slug = 'proxbox-basic-site'

        # Verify if basic site is already created
        site_proxbox = Site.objects.filter(
            name=site_proxbox_name,
            slug=site_proxbox_slug
        ).first()

        # Create a basic Proxbox site if not created yet.
        if site_proxbox is None:
            try:
                site = Site(
                    name=site_proxbox_name,
                    slug=site_proxbox_slug,
                    status='active',
                    tags=[tag().id]
                )
                site.save()
            except Exception as e:
                # logger.exception(e)
                # traceback.print_exc()
                print(e)
                return "Error creating the '{0}' site. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
                    site_proxbox_name, site_proxbox_slug)

        # If basic site already created, use it.
        else:
            site = site_proxbox

    else:
        return 'Site ID configured is invalid.'

    return site
