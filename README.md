# Ansible virtual cluster

![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Ansible](https://img.shields.io/badge/Ansible-000000?style=for-the-badge&logo=ansible&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache-red.svg?style=for-the-badge)


Test playbooks on a virtual cluster.

The (virtual) cluster is generated from an Ansible inventory, and playbooks can
be run without fear on the virtual infrastructure.

This repository will also provide an example and documentation for the
configuration required for our [playbooks](https://github.com/ISC-HEI/ansible-playbooks).

## Limitations
Since the virtual cluster is based on docker, some operations are restricted,
for instance:
  * All operations modifying kernel parameters (modules changes, ..., changing `/proc` or `/sys` parameters, network changes)
  * Modifying `/etc/hosts`

## Key Features

- Infrastructure-as-Inventory  
  The Ansible inventory defines the entire cluster topology.

- Session-based cluster isolation

  Multiple cluster can be run at the same time

  Each cluster runs in its own session (S01, S02, …).

- Automatic Docker Compose generation
  No manual Docker configuration is required.

- Playbook execution  
  Run Ansible ping or full playbooks against the cluster.

- Clean lifecycle
  Start, test, and destroy clusters cleanly.

- Menu for easy utilisation.

- `ssh` can be used to inspect the machines

## In brief

Detailed usage: [here](Usage.md).

1. Start a cluster: `./cluster.py start -i inventory`
1. ping (Ansible) all machines `./cluster.py ping`
1. Stop the cluster: `./cluster.py stop`
1. Run a playbook: `./cluster.py run -t ../motd.yml -e "my_var=foo"`

## Prerequisites

The following tools are required:

- `docker` and `docker-compose`
  - Add `{ "userns-remap": "default" }` in `/etc/docker/daemon.json`
- `python3` + `venv`
- `ansible`

## Installation

1. If not already done, clone the playbooks repository:
   ```bash
   git clone https://github.com/ISC-HEI/ansible-playbooks.git
   cd ansible-playbooks
   ```
1. `ansible-playbook` will have it's every day config in the `conf` directory, so let's clone in `conf-sim`
   ```bash
   git clone https://github.com/ISC-HEI/ansible-playbooks.git conf-sim
   cd conf-sim
   ```
1. Activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Inventory (only for sim)

- SSH access is exposed on localhost with a session-based port offset
- The `dockerfile: X` parameter is used to choose the image from `Dockerfiles/Dockerfile.X`

## `conf` documentation

The configuration is stored in `./conf` :
* `./conf`
  * `inventory/*.yml` <- all .yml files will be included in the inventory
  * `users/*.yml` <- all .yml files will be included to generate users/groups/...
  * `files/skel/` <- used as /etc/skel for users that have never logged in
  * `files/global/` <- here goes files
  * `authorized_keys/USER_NAME.pub` <- ssh public keys (same syntax as `authorized_keys`

  ### `conf/inventory`
  :warning: Beware of name collision since all files in `inventory/*.yml` will be included.

  Here is a commented sample inventory.
  ```yaml
  europa: # the cluster is named europa
    vars:
      ansible_user: ubuntu # used by ansible for ssh connection, sudo -u root with no password is required
      users: europa_users # group of users as defined in users/roles*.yml
      admins: global_admins # group of users as defined in users/roles*.yml
      usergroups: europa_groups # unix group of users defined in users/roles*.yml
      zabbix_server: germany # this host will be the zabbix server for all europa machines
      syslog_server: italy   # syslog server for all europa machines
      mailer: # will configure monit and msmtp
        server: mail.example.com
        user: account@example.com
        password: !vault | # password for sending mail
          $ANSIBLE_VAULT;1.1;AES256
          38643235393935336361656531646338323861633066383432613664646435353332393265383732
          3133613634623635646663643039326230303938653131610a316434356134656664386537386335
          66666434393830303166313462356665336564303264653463386139633863613234623733653462
          6238636533663063650a303539396432316562363430663533316663366336656535306466323834
          3735
        dest: !vault | # mail destination
          $ANSIBLE_VAULT;1.1;AES256
          32623266353033393038333631663661356362656163393466353062383162376336636166373231
          6535356566343636376465346236623133386638373966350a393133666633393162383664383136
          62373834373838663565353039306162343264313636353065643163356537616235366537333835
          3761613266363430380a363664373737346431306366653665383263353139626231363964316135
          6464
    children:
      mgmt: # mgmt is a group of machines
        hosts:
          europamain:
            ansible_host: 192.168.33.12
            users: null # only admins allowed, so prevent inherit from europa.users variable
            usergroups: null
      workers: # workers is another group of machines
        hosts:
          worker00:
            ansible_host: 192.168.55.10
          worker01:
            ansible_host: 192.168.55.11
          worker02:
            ansible_host: 192.168.55.12
      monitoring: # yet another group of machine
        hosts:
          germany: # should host the zabbix server (not playbook available yet)
            ansible_host: 192.168.33.12
            usergroups: null
            users: null
          italy: # since italy is the syslog_server, it will be configured for receiving syslogs
            ansible_host: 192.168.33.13
            usergroups: null
            users: null
  ```
  :point_up: On every host `/etc/hosts` will be completed using ansible_host (if it is an IP address).

  ### `conf/users`
  :warning: Beware of name collision since all files in `users/*.yml` will be included.

  Groups and unix groups are defined like this:
  ```yaml
  global_admins:
    - ubuntu # the user defined as ansible_user must be an admin or root
    - foo
    - bar

  europa_users:
    - titi
    - tutu

  europa_groups:
    - testgroup
  ```

  :point_up: Variables with names starting with uid_ and gid_ will be merged into a globalb uid and gid array.

  ```yaml
  uid_abc:
    - {  id: '2001', name: 'foo',    shell: '/bin/bash'    }
    - {  id: '1000', name: 'ubuntu', shell: '/bin/bash'    }
    - {  id: '2000', name: 'titi',   shell: '/bin/bash'    }
    - {  id: '1001', name: 'foo',    shell: '/usr/bin/zsh' }

  gid_abc:
    - { id: '140', name: 'sudonopass'}
    - { id: '141', name: 'testgroup'}
  ```

  :warning: id (from uid and gid) are expected to be unique
  :point_up: uid and gid are treated as recommendation -> the user or group created on the machine will use an unused uid/gid.

## Related Projects

Ansible Playbooks:
https://github.com/ISC-HEI/ansible-playbooks
