> Although **Proxbox is under constant development**, I do it with **best effort** and **spare time**. I have no financial gain with this and hope you guys understand, as I know it is pretty useful to some people. If you want to **speed up its development**, solve the problem or create new features with your own code and create a **[Pull Request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests)** so that I can **review** it. **I also would like to appreciate the people who already contributed with code or/and bug reports.** Without this help, surely Proxbox would be much less useful as it is already today to several environments!

<div align="center">
	<a href="https://docs.netbox.dev.br/en/netbox/plugins/netbox-proxbox">
		<img width="532" src="https://github.com/N-Multifibra/proxbox/blob/main/etc/img/proxbox-full-logo.png" alt="Proxbox logo">
	</a>
	<br>
	
<div>
	
### [New Documentation available!](https://docs.netbox.dev.br/en/netbox/plugins/netbox-proxbox)
</div>
<br>
</div>




## Netbox Plugin which integrates [Proxmox](https://www.proxmox.com/) and [Netbox](https://netbox.readthedocs.io/)!

>**Edgeuno:** These project is a fork of the original [proxbox](https://github.com/netdevopsbr/netbox-proxbox) plugin,
the main changes are in the ability to set multi tenancy, improve information for the cluster, the devices (node), and
the virtual machines, these include but not limited to ip address association, better group assignation, and use of
django
queues in order to have a recurring synchronization with all the machines in proxbox.
Better synchronization with remove machines in proxmox.

> **ALERT:** Braking changes has being made with version `0.0.10`.

> **ALERT:** Last version compatible with nextbox 3.5.2

> **ALERT:** From version 4.0.x onward use version `0.0.12`
 
> - Django's queues are no longer in use, the model was change to a script is used to run the synchronization tool
> - The configuration for the cluster is now set in a file for reduce complexity of the file `configuration.py`
> - Some of the code from the of official proxbox has being merge with this repository.

> **NOTE:** Although the Proxbox plugin is in development, it only uses **GET requests** and there is **no risk to harm your Proxmox environment** by changing things incorrectly.

<br>

Proxbox is currently able to get the following information from Proxmox:

- **Cluster name**
- **Nodes:**
  - Status (online / offline)
  - Name
  - Ip info 
- **Virtual Machines and Containers:**
  - Status (online / offline)
  - Name
  - ID
  - CPU
  - Disk
  - Memory
  - Node (Server)
  - Ip info

---

<div align="center">
	
### Versions


The following table shows the Netbox and Proxmox versions compatible (tested) with Proxbox plugin.

| netbox version   | proxmox version | proxbox version |
|------------------|-------------|-----------------|
| >= v4.0.7        | >= v6.2.0  | =v0.0.12        |
| >= v3.5.2        | >= v6.2.0  | =v0.0.11        |
| >= v3.2.0        | >= v6.2.0 | =v0.0.4         |
| >= v3.0.0 < v3.2 | >= v6.2.0 | =v0.0.3         |


</div>

---

### Summary
[1. Installation](#1-installation)
- [1.1. Install package](#11-install-package)
  - ~~[1.1.1. Using pip (production use)](#111-using-pip-production-use---not-working-yet)~~
  - [1.1.2. Using git (development use)](#112-using-git-development-use)
- [1.2. Enable the Plugin](#12-enable-the-plugin)
- [1.3. Configure Plugin](#13-configure-plugin)
  - [1.3.1. Change Netbox 'configuration.py' to add PLUGIN parameters](#131-change-netbox-configurationpy-to-add-plugin-parameters)
  - [1.3.2. Change Netbox 'settings.py' to include Proxbox Template directory](#132-change-netbox-settingspy-to-include-proxbox-template-directory)
- [1.4. Run Database Migrations](#14-run-database-migrations)
- [1.5 Restart WSGI Service](#15-restart-wsgi-service)
- [1.6 Running the script](#16-running-the-script)
- ~~[1.6. Queue Initialization](#16-queue-initialization)~~
- ~~[1.7. Service](#17-service)~~

[2. Configuration Parameters](#2-configuration-parameters)

[3. Custom Fields](#3-custom-fields)
- [3.1. Custom Field Configuration](#31-custom-field-configuration)
	- [3.1.1. Proxmox ID](#311-proxmox-id)
	- [3.1.2. Proxmox Node](#312-proxmox-node)
	- [3.1.3. Proxmox Type](#313-proxmox-type-qemu-or-lxc)
	- [3.1.4. Proxmox Keep Interface](#314-proxmox-keep-interface)
- [3.2. Custom Field Example](#32-custom-field-example)

[4. Usage](#4-usage)

[5. Enable Logs](#5-enable-logs)

[6. Contributing](#6-contributing)

[7. Roadmap](#7-roadmap)

[8. Get Help from Community!](#8-get-help-from-community)

---

## 1. Installation

The instructions below detail the process for installing and enabling Proxbox plugin.
~~The plugin is available as a Python package in pypi and can be installed with pip.~~

### ~~1.1. Install package~~

#### ~~1.1.1. Using pip (production use)~~

~~Enter Netbox's virtual environment.~~
```
source /opt/netbox/venv/bin/activate
```

~~Install the plugin package.~~
```
(venv) $ pip install netbox-proxbox
```

For the moment installation via package is not supported maybe in the future

#### 1.1.2. Using git (development use)
**OBS:** This method is recommended for testing and development purposes and is not for production use.

Move to netbox main folder
```
cd /opt/netbox/netbox
```

Clone netbox-proxbox repository
```
git clone https://github.com/netdevopsbr/netbox-proxbox.git
```


```
cd netbox-proxbox
source /opt/netbox/venv/bin/activate
```
Install netbox-proxbox for development
```
python3 setup.py develop
```

Install netbox-proxbox for production
```
python3 setup.py install
```

---

### 1.2. Enable the Plugin

Enable the plugin in **/opt/netbox/netbox/netbox/configuration.py**:
```python
PLUGINS = ['netbox_proxbox']
```

---

### 1.3. Configure Plugin

#### 1.3.1. Change Netbox '**[configuration.py](https://github.com/netbox-community/netbox/blob/develop/netbox/netbox/configuration.example.py)**' to add PLUGIN parameters
The plugin's configuration is also located in **/opt/netbox/netbox/netbox/configuration.py**:

The values for the file configuration_options can be found in the section [Configuration Parameters](#2-configuration-parameters) section.

**OBS:** You do not need to configure all the parameters, only the one's different from the default values. It means that if you have some value equal to the one below, you can skip its configuration. For netbox you should ensure the domain/port either targets gunicorn or a true http port that is not redirected to https.

```python
PLUGINS_CONFIG = {
    'netbox_proxbox': {
        'proxmox': {
            'filePath': '/opt/netbox/plugins/netbox-proxbox/configuration_options.json',
        },
    }
}
```

<br>

#### 1.3.2. Change Netbox '**[settings.py](https://github.com/netbox-community/netbox/blob/develop/netbox/netbox/settings.py)**' to include Proxbox Template directory

> Probably on the next release of Netbox, it will not be necessary to make the configuration below! As the [Pull Request #8733](https://github.com/netbox-community/netbox/pull/8734) got merged to develop branch

**It is no longer necessary to modify the templates section in `settings.py` and you may revert any changes.**

---

### 1.4. Run Database Migrations

```
(venv) $ cd /opt/netbox/netbox/
(venv) $ python3 manage.py migrate
```

---

### 1.5. Restart WSGI Service

Restart the WSGI service to load the new plugin:
```
# sudo systemctl restart netbox
```

### 1.6 Running the script

After installing the plugin to run the process just run
```shell
$ /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py proxboxscrapper
```

#### Set the cron job
There is a file called `proxbox_runner.sh` which can be used for running the cron job.

To enable run
```shell
crontab -e
```
and copy the following line to run the script every hour and to set the output to a file for later review
```
## Proxbox runner
0 * * * * /usr/bin/bash -l /opt/netbox/plugins/netbox-proxbox/proxbox_runner.sh > /opt/netbox/plugins/netbox-proxbox/proxbox_runner.txt
```

### ~~1.6. Queue Initialization~~

#### ~~Queue File: **rq.sh:**~~ 
~~In the root of the repository there is a shell script that can initialize 5 queues and one scheduler, 
is recommended to use screen for running the queues in the background~~

```shell
(venv) $ screen -S proxbox_queues
(venv) $ cd /opt/netbox/plugins/netbox-proxbox
(venv) $ sh rq.sh
```
~~To detach the screen just press ``ctrl+a+d``~~


#### ~~Individual Queues~~
~~To run the synchronization some queue workers are needed~~

```shell
(venv) $ /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox
```

~~Initialize the scheduler~~

```shell
(venv) $ /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqscheduler high default low netbox_proxbox.netbox_proxbox
```

~~To make it work as a background process we recommend to use screen~~

```shell
(venv) $ screen -S proxbox_queues
(venv) $ /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqworker high default low netbox_proxbox.netbox_proxbox &  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py rqscheduler high default low netbox_proxbox.netbox_proxbox
```

~~To detach the screen just press ``ctrl+a+d``~~

 

---

### ~~1.7. Service~~

#### ~~Service~~
~~A service can be set so the project queues don't relay on setting a screen:
- Create a file call `proxbox.service`~~
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
#### ~~Todo~~
~~Set the correct `stdout` execution logs.~~
---

## 2. Configuration Parameters

The following options are available:

* `proxmox`: (List<Dict>) Proxmox related configuration to access the cluster.
* `proxmox.domain`: (String) Domain or IP address of Proxmox.
* `proxmox.http_port`: (Integer) Proxmox HTTP port (default: 8006).
* `proxmox.user`: (String) Proxmox Username.
* `proxmox.token_name`: (String) Proxmox TokenID.
* `proxmox.token_value`: (String) Proxmox Token Value.
* `proxmox.ssl`: (Bool) Defines the use of SSL (default: False).
* `proxmox.site_name`: (String) Name of the site where the cluster is located.
* `proxmox.node_role_name`: (String) Name of the role in netbox for the nodes of the cluster, if not in netbox it will be created.

* `netbox`: (Dict) Netbox related configuration to use pynetbox.
* `netbox.manufacturer`: (String) Default name for the manufacturer of the machine that contains the node
* `netbox.settings.virtualmachine_role_id`: (Integer) Role ID to be used by Proxbox when creating Virtual Machines
* `netbox.settings.virtualmachine_role_name`: (String) Default name of the role for the virtual machine in netbox
* `netbox.settings.node_role_id`: (Integer) Role ID to be used by Proxbox when creating Nodes (Devices)
* `netbox.settings.site_id` (Integer) Site ID to be used by Proxbox when creating Nodes (Devices)
* `netbox.tenant_name`: (String) Default name for the tenant of the virtual machine
* `netbox.tenant_regex_validator`: (String) If information about the tenant is set in the description of the virtual machine, give how to parse it so the default tenant is given. This helps when a lot of virtual machines belong to another tenants
* `netbox.tenant_description`: (String) Description for the default tenant

---

## 3. Custom Fields

To get Proxmox ID, Node and Type information, is necessary to configure Custom Fields.
Below the parameters needed to make it work:

<br>

### 3.1. Custom Field Configuration

#### 3.1.1. Proxmox ID

Required values (must be equal)
- [Custom Field] **Type:** Integer
- [Custom Field] **Name:** proxmox_id
- [Assignment] **Content-type:** Virtualization > virtual machine
- [Validation Rules] **Minimum value:** 0

Optional values (maybe different)
- [Custom Field] **Label:** [Proxmox] ID
- [Custom Field] **Description:** Proxmox VM/CT ID

<br>

#### 3.1.2. Proxmox Node

Required values (must be equal)
- [Custom Field] **Type:** Text
- [Custom Field] **Name:** proxmox_node
- [Assignment] **Content-type:** Virtualization > virtual machine

Optional values (maybe different)
- [Custom Field] **Label:** [Proxmox] Node
- [Custom Field] **Description:** Proxmox Node (Server)

<br>

#### 3.1.3. Proxmox Type (qemu or lxc)

Required values (must be equal)
- [Custom Field] **Type:** Selection
- [Custom Field] **Name:** proxmox_type
- [Assignment] **Content-type:** Virtualization > virtual machine
- [Choices] **Choices:** qemu,lxc

Optional values (maybe different)
- [Custom Field] **Label:** [Proxmox] Type
- [Custom Field] **Description:** Proxmox type (VM or CT)

<br>

#### 3.1.4. Proxmox Keep Interface

Required values (must be equal)
- [Custom Field] **Type:** Boolean (true/false)
- [Custom Field] **Name:** proxmox_keep_interface
- [Assignment] **Content-type:** DCIM > Interface

<br>

### 3.2. Custom Field Example

![custom field image](etc/img/custom_field_example.png?raw=true "preview")

---

## 4. Usage

If everything is working correctly, you should see in Netbox's navigation the **Proxmox VM/CT** button in **Plugins** dropdown list.

On **Proxmox VM/CT** page, click button ![full update button](etc/img/proxbox_full_update_button.png?raw=true "preview")

It will redirect you to a new page and you just have to wait until the plugin runs through all Proxmox Cluster and create the VMs and CTs in Netbox.

**OBS:** Due the time it takes to full update the information, your web brouse might show a timeout page (like HTTP Code 504) even though it actually worked.

---

## 5. Enable Logs

So that Proxbox plugin logs what is happening to the terminal, copy the following code and paste to `configuration.py` Netbox configuration file:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
```

You can customize this using the following link: [Django Docs - Logging](https://docs.djangoproject.com/en/4.1/topics/logging/).
Although the above standard configuration should do the trick to things work.

---

## 6. Contributing
Developing tools for this project based on [ntc-netbox-plugin-onboarding](https://github.com/networktocode/ntc-netbox-plugin-onboarding) repo.

Issues and pull requests are welcomed.

---

## 7. Roadmap
- Start using custom models to optimize the use of the Plugin and stop using 'Custom Fields'
- Automatically remove Nodes on Netbox when removed on Promox (as it already happens with Virtual Machines and Containers)
- Add individual update of VM/CT's and Nodes (currently is only possible to update all at once)
- Add periodic update of the whole environment so that the user does not need to manually click the update button.
- Create virtual machines and containers directly on Netbox, having no need to access Proxmox.
- Add 'Console' button to enable console access to virtual machines

---

## 8. Get Help from Community!
If you are struggling to get Proxbox working, feel free to contact someone from community (including me) to help you.
Below some of the communities available:
- **[Official - Slack Community (english)](https://netdev.chat/)**
- **[Community Discord Channel - 🇧🇷 (pt-br)](https://discord.gg/X6FudvXW)**
- **[Community Telegram Chat - 🇧🇷 (pt-br)](https://t.me/netboxbr)**
