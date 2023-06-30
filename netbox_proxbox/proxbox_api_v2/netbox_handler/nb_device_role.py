try:
    from django.template.defaultfilters import slugify
    from dcim.models import DeviceRole
except Exception as e:
    print(e)
    raise e


def upsert_role(**kwargs):
    """
    TODO: Improve this function! make it so only calls the device role creation once
    """

    # If role_id equals to 0, consider it is not configured by user and must be created by Proxbox
    role_id = kwargs.get("role_id", 0)
    role_name = kwargs.get('role_name', None)
    if role_name:
        role = DeviceRole.objects.filter(name=role_name).first()
        if role is None:
            try:
                role = DeviceRole(
                    name=role_name,
                    slug=slugify(role_name),
                    color='ff5722',
                    vm_role=True
                )
                role.save()
            except:
                role = None
        if role:
            return role

    if not isinstance(role_id, int):
        return 'Role ID must be INTEGER. Netbox PLUGINS_CONFIG is configured incorrectly.'

    # If user configured ROLE_ID in Netbox's PLUGINS_CONFIG, use it.
    if role_id > 0:
        # role = None
        # try:
        role = DeviceRole.objects.filter(id=role_id).first()
        # except Exception as e:
        #     print(e)
        # pass

        if role is None:
            return "Role ID of Virtual Machine or Node invalid. Maybe the ID passed does not exist or it is not a integer!"

    elif role_id == 0:
        role_proxbox_name = "Proxbox Basic Role"
        role_proxbox_slug = 'proxbox-basic-role'

        # Verify if basic role is already created
        role_proxbox = DeviceRole.objects.filter(
            name=role_proxbox_name,
            slug=role_proxbox_slug
        ).first()

        # Create a basic Proxbox VM/Node Role if not created yet.
        if role_proxbox == None:

            try:
                role = DeviceRole(
                    name=role_proxbox_name,
                    slug=role_proxbox_slug,
                    color='ff5722',
                    vm_role=True
                )
                role.save()
            except:
                return "Error creating the '{0}' role. Possible errors: the name '{0}' or slug '{1}' is already used.".format(
                    role_proxbox_name, role_proxbox_slug)

        # If basic role already created, use it.
        else:
            role = role_proxbox

    else:
        return 'Role ID configured is invalid.'

    return role
