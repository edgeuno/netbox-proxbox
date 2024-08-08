try:
    from extras.plugins import PluginMenuButton, PluginMenuItem

    # from utilities.choices import ButtonColorChoices

    menu_items = (
        PluginMenuItem(
            link="plugins:netbox_proxbox:proxmoxvm_list",
            link_text="List",
        ),
    )
except Exception as e:
    from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
    from django.conf import settings
    from packaging import version

    from utilities.choices import ChoiceSet


    # remove in v4.0.5 insert manually

    class ButtonColorChoices(ChoiceSet):
        """
        Map standard button color choices to Bootstrap 3 button classes
        """
        DEFAULT = 'outline-dark'
        BLUE = 'blue'
        INDIGO = 'indigo'
        PURPLE = 'purple'
        PINK = 'pink'
        RED = 'red'
        ORANGE = 'orange'
        YELLOW = 'yellow'
        GREEN = 'green'
        TEAL = 'teal'
        CYAN = 'cyan'
        GRAY = 'gray'
        GREY = 'gray'  # Backward compatability for <3.2
        BLACK = 'black'
        WHITE = 'white'

        CHOICES = (
            (DEFAULT, 'Default'),
            (BLUE, 'Blue'),
            (INDIGO, 'Indigo'),
            (PURPLE, 'Purple'),
            (PINK, 'Pink'),
            (RED, 'Red'),
            (ORANGE, 'Orange'),
            (YELLOW, 'Yellow'),
            (GREEN, 'Green'),
            (TEAL, 'Teal'),
            (CYAN, 'Cyan'),
            (GRAY, 'Gray'),
            (BLACK, 'Black'),
            (WHITE, 'White'),
        )


    menu_buttons = [
        PluginMenuItem(
            link="plugins:netbox_proxbox:proxmoxvm_list",
            link_text="List",
        ),
    ]

    menu = PluginMenu(
        label=f"ProxBox",
        groups=(("", menu_buttons),),
        icon_class="mdi mdi-desktop-classic",

    )

    '''
    menu_items = (
        PluginMenuItem(
            link="plugins:netbox_proxbox:proxmoxvm_list",
            link_text="List",
        ),
    )


    buttons=(
        PluginMenuButton(
            # match the names of the path for create view defined in ./urls.py
            link="plugins:netbox_proxbox:proxmoxvm_add",
            # text that appears when hovering the ubtton
            title="Add",
            # font-awesome icon to use
            icon_class="mdi mdi-plus-thick", # 'fa fa-plus' didn't work
            # defines color button to green
            color=ButtonColorChoices.GREEN,
            permissions=["netbox_proxbox.add_proxmoxvm"],
        ),
    ),
    '''