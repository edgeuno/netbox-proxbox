<p align="center">
  <img width="532" src="https://github.com/N-Multifibra/proxbox/blob/main/etc/img/proxbox-full-logo.png" alt="Proxbox logo">
</p>

# proxbox 

**Edgeuno:** These project is a fork of the original [proxbox](https://github.com/netdevopsbr/netbox-proxbox) plugin,
the main changes are in the ability to set multi tenancy, improve information for the cluster, the devices (node), and
the virtual machines, these include but not limited to ip address association, better group assignation, and use of
django
queues in order to have a recurring synchronization with all the machines in proxbox.
Better syncroniztion with remove machines in proxmox.

**Note:** **This branch was created for legacy purposes**. it will be no longer in develop, we change the way the scrapping from proxmox is done, 
is no longer done in queues but instead is done with a script that can be set to be executed in a cron job or executed directly in the console.

**NOTE:** Although the Proxbox plugin is in development, it only uses GET requests and there is no risk to harm your
Proxmox environment by changing things incorrectly.

Netbox plugin which integrates Proxmox and Netbox using proxmoxer and pynetbox.

It is currently able to get the following information from Proxmox:

- Cluster name
- Nodes:
    - Status (online / offline)
    - Name
- Virtual Machines and Containers:
    - Status (online / offline)
    - Name
    - ID
    - CPU
    - Disk
    - Memory
    - Node (Server)

### Versions

The following table shows the Netbox and Proxmox versions compatible (tested) with Proxbox plugin.

| netbox version        | proxmox version          | proxbox version
| ------------- |-------------|-------------|
| > = 2.10.9 | > = v6.2.0 | v0.0.3

---

### Summary

[1. Installation](#1-installation)

- [1.1. Install package](#11-install-package)
    - [1.1.1. Using pip (production use)](#111-using-pip-production-use)
    - [1.1.2. Using git (development use)](#112-using-git-development-use)
- [1.2. Enable the Plugin](#12-enable-the-plugin)
- [1.3. Configure Plugin](#13-configure-plugin)
- [1.4. Run Database Migrations](#14-run-database-migrations)
- [1.5 Restart WSGI Service](#15-restart-wsgi-service)
- [1.6. Queue Initialization](#16-queue-initialization)
- [1.7. Service](#17-service)

[2. Configuration Parameters](#2-configuration-parameters)

[3. Custom Fields](#3-custom-fields)

- [3.1. Custom Field Configuration](#31-custom-field-configuration)
    - [3.1.1. Proxmox ID](#311-proxmox-id)
    - [3.1.2. Proxmox Node](#312-proxmox-node)
    - [3.1.3. Proxmox Type](#313-proxmox-type-qemu-or-lxc)
- [3.2. Custom Field Example](#32-custom-field-example)

[4. Usage](#4-usage)

[5. Contributing](#5-contributing)

[6. Roadmap](#6-roadmap)

---

## 1. Installation

The instructions below detail the process for installing and enabling Proxbox plugin.
The plugin is available as a Python package in pypi and can be installed with pip (Not working yet).

### 1.1. Install package

#### 1.1.1. Using pip (production use - not working yet!)

Enter Netbox's virtual environment.

```
source /opt/netbox/venv/bin/activate
```

Install the plugin package.

```
(venv) $ pip install netbox-proxbox
```

#### 1.1.2. Using git (development use)

**OBS:** ~~This method is recommended for testing and development purposes and is not for production use.~~ In order to
start the process a call to [http://{my.netbox.instance}/plugins/proxbox/queue/]() is needed. In future versions there
will be more control over
the process (a django queue is needed).

Move to netbox main folder

```
cd /opt/netbox/plugins
```

Clone netbox-proxbox repository

```
git clone https://github.com/edgeuno/netbox-proxbox
```

Install netbox-proxbox

```
cd netbox-proxbox
source /opt/netbox/venv/bin/activate
python3 setup.py develop
```

### 1.2. Enable the Plugin

Enable the plugin in **/opt/netbox/netbox/netbox/configuration.py**:

```python
PLUGINS = ['netbox_proxbox']
```

### 1.3. Configure Plugin

The plugin's configuration is also located in **/opt/netbox/netbox/netbox/configuration.py**:

Replace the values with your own following the [Configuration Parameters](#configuration-parameters) section.

**OBS:** You do not need to configure all the parameters, only the one's different from the default values. It means
that if you have some values equal to the one below, you can skip its configuration.

```python
PLUGINS_CONFIG = {
    'netbox_proxbox': {
        'proxmox': [{
            'domain': 'proxbox.example.com',  # May also be IP address
            'http_port': 8006,
            'user': 'root@pam',
            'token': {
                'name': 'tokenID',  # Only type the token name and not the 'user@pam:tokenID' format
                'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
            },
            'ssl': False,
            'site_name': 'Site_Name',  # Name of the site in netbox
            'site_id': 2,  # Id of the site in netbox, if the name is set the id is not required
            'node_role_name': 'Hypervisor',  # Name of the role for the device in netbox
            'node_role_id': 11,  # Id of the role for the device in netbox, if the name is set the id is not required
        }],
        'netbox': {
            'domain': 'netbox.example.com',  # May also be IP address
            'http_port': 80,
            'token': '0dd7cddfaee3b38bbffbd2937d44c4a03f9c9d38',
            'ssl': False,  # There is no support to SSL on Netbox yet, so let it always False.
            'settings': {
                'virtualmachine_role_id': 0,
                'virtualmachine_role_name': 'Proxbox Basic Role',
                'node_role_id': 0,
                'site_id': 0,
                'tenant_name': 'EdgeUno',  # Set the custom tags and tenant for own machines
                'tenant_regex_validator': '.*', # Set a regex for matching the name of the machines to give then the tenat and tag
                'tenant_description': 'The vm belongs to Edgeuno'  # A description of the tenant and the tag
            }
        }
    }
}
```

### 1.4. Run Database Migrations

```
(venv) $ cd /opt/netbox/netbox/
(venv) $ python3 manage.py migrate
```

### 1.5. Restart WSGI Service

Restart the WSGI service to load the new plugin:

```
# sudo systemctl restart netbox netbox-rq
```

### 1.6. Queue Initialization

#### Queue File: **rq.sh:** 
In the root of the repository there is a shell script that can initialize 5 queues and one scheduler, 
is recommended to use screen for running the queues in the background

```shell
(venv) $ screen -S proxbox_queues
(venv) $ cd /opt/netbox/plugins/netbox-proxbox
(venv) $ sh rq.sh
```
To detach the screen just press ``ctrl+a+d``


#### Individual Queues
To run the synchronization some queue workers are needed

```shell
(venv) $ /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox
```

Initialize the scheduler

```shell
(venv) $ /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqscheduler high default low netbox_proxbox.netbox_proxbox
```

To make it work as a background process we recommend to use screen

```shell
(venv) $ screen -S proxbox_queues
(venv) $ /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox &  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqscheduler high default low netbox_proxbox.netbox_proxbox
```

To detach the screen just press ``ctrl+a+d``

 

---

### 1.7. Service

#### Service
A service can be set so the project queues don't relay on setting a screen:
- Create a file call `proxbox.service`
 ```shell
$ touch /etc/systemd/system/proxbox.service
``` 
- Set the service coping into `proxbox.service` (here we are assuming that the virtual environment for netbox is installed at `/opt/netbox/venv`):
```shell
[Unit]
Description=Proxbox service
[Service]
Type=simple
User=root
WorkingDirectory=/opt/netbox/
VIRTUAL_ENV=/opt/netbox/venv
Environment=PATH=$VIRTUAL_ENV/bin:$PATH
ExecStart=/opt/netbox/plugins/netbox-proxbox/rq.sh &
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
- Enable the service:
```shell
 $ systemctl enable proxbox
```
- Start the service:
```shell
$ systemctl start proxbox
```
- Monitor the service:
```shell
$ journalctl -u proxbox -f
```
#### Todo
Set the correct `stdout` execution logs.

---

## 2. Configuration Parameters

The following options are available:

* `proxmox`: (Dict) Proxmox related configuration to use proxmoxer.
* `proxmox.domain`: (String) Domain or IP address of Proxmox.
* `proxmox.http_port`: (Integer) Proxmox HTTP port (default: 8006).
* `proxmox.password`: (String) Proxmox Password.
* `proxmox.token`: (Dict) Contains Proxmox TokenID (name) and Token Value (value).
* `proxmox.token.name`: (String) Proxmox TokenID.
* `proxmox.token.value`: (String) Proxmox Token Value.
* `proxmox.ssl`: (Bool) Defines the use of SSL (default: False).
* `proxmox.site_name`: (String) Name of the site in netbox.
* `proxmox.site_id`: (String) ID of the site in netbox, if the name is set the id is not required.
* `proxmox.site_name`: (String) Name of the role for the device in netbox.
* `proxmox.node_role_name`: (String) Name of the role for the device in netbox.
* `proxmox.node_role_id`: (String) ID of the role for the device in netbox, if the name is set the id is not required.


* `netbox`: (Dict) Netbox related configuration to use pynetbox.
* `netbox.domain`: (String) Domain or IP address of Netbox.
* `netbox.http_port`: (Integer) Netbox HTTP PORT (default: 80).
* `netbox.token`: (String) Netbox Token Value.
* `netbox.ssl`: (Bool) Defines the use of SSL (default: False). - Proxbox doesn't support SSL on Netbox yet.
* `netbox.settings`: (Dict) Default items of Netbox to be used by Proxbox.
    - If not configured, Proxbox will automatically create a basic configuration to make it work.
    - The ID of each item can be easily found on the URL of the item you want to use.
* `netbox.settings.manufacturer`: (String) Name of the manufacturer to use for default.
* `netbox.settings.virtualmachine_role_id`: (Integer) Role ID to be used by Proxbox when creating Virtual
  Machines (`deprecated`).
* `netbox.settings.virtualmachine_role_name`: (String) Name of the default role for the virtual machines (Is the machine
  is quemu the role will be VPS, if the machine is lxc the role will be LXC, otherwise the default role will be used).
* `netbox.settings.node_role_id`: (Integer) Role ID to be used by Proxbox when creating Nodes (Devices)(`deprecated`).
* `netbox.settings.site_id`: (Integer) Site ID to be used by Proxbox when creating Nodes (Devices)(`deprecated`).
* `netbox.settings.tenant_name`: (String) Set the custom tags and tenant for own machines.
* `netbox.settings.tenant_regex_validator`: (String) Set a regex for matching the name of the machines to give then the
  tenat and tag.

---

## 3. Custom Fields

To get Proxmox ID, Node and Type information, is necessary to configure Custom Fields.
Below the parameters needed to make it work:

---

### 3.1. Custom Field Configuration

#### 3.1.1. Proxmox ID

Required values (must be equal)

- [Custom Field] **Type:** Integer
- [Custom Field] **Name:** proxmox_id
- [Assignment] **Content-type:** Virtualization > virtual machine
- [Validation Rules] **Minimum value:** 0

Optional values (may be different)

- [Custom Field] **Label:** [Proxmox] ID
- [Custom Field] **Description:** Proxmox VM/CT ID

---

#### 3.1.2. Proxmox Node

Required values (must be equal)

- [Custom Field] **Type:** Text
- [Custom Field] **Name:** proxmox_node
- [Assignment] **Content-type:** Virtualization > virtual machine

Optional values (may be different)

- [Custom Field] **Label:** [Proxmox] Node
- [Custom Field] **Description:** Proxmox Node (Server)

---

#### 3.1.3. Proxmox Type (qemu or lxc)

Required values (must be equal)

- [Custom Field] **Type:** Selection
- [Custom Field] **Name:** proxmox_type
- [Assignment] **Content-type:** Virtualization > virtual machine
- [Choices] **Choices:** qemu,lxc

Optional values (may be different)

- [Custom Field] **Label:** [Proxmox] Type
- [Custom Field] **Description:** Proxmox type (VM or CT)

---

### 3.2. Custom Field Example

![custom field image](etc/img/custom_field_example.png?raw=true "preview")

---

## 4. Usage

If everything is working correctly, you should see in Netbox's navigation the **Proxmox VM/CT** button in **Plugins**
dropdown list.

~~On **Proxmox VM/CT** page, click
button ![full update button](etc/img/proxbox_full_update_button.png?raw=true "preview")~~

~~It will redirect you to a new page and you just have to wait until the plugin runs through all Proxmox Cluster and
create the VMs and CTs in Netbox.~~

**OBS:** ~~Due the time it takes to full update the information, your web browser might show a timeout page (like HTTP
Code 504) even though it actually worked.~~

In order to
start the process a call to [http://{my.netbox.instance}/plugins/proxbox/queue/]() is needed. In future versions there
will be more control over
the process (a django queue is needed).

---

## 5. Contributing

Developing tools for this project based
on [ntc-netbox-plugin-onboarding](https://github.com/networktocode/ntc-netbox-plugin-onboarding) repo.

Issues and pull requests are welcomed.

## 6. Roadmap

- Start using custom models to optimize the use of the Plugin and stop using 'Custom Fields'
- Automatically remove Nodes on Netbox when removed on Promox (as it already happens with Virutal Machines and
  Containers)
- Add individual update of VM/CT's and Nodes (currently is only possible to update all at once)
- Add periodic update of the whole environment so that the user does not need to manually click the update button.
- Create virtual machines and containers directly on Netbox, having no need to access Proxmox.
- Add 'Console' button to enable console access to virtual machines

