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

1. Start a cluster:
   ```bash
   ./cluster.py start -i inventory
   INFO: Your session id is S01
   INFO: Building docker image 'custom_ubuntu_24_04'
   INFO: Building docker image 'custom_ubuntu_22_04'
   INFO: Starting containers...
   ```
1. (Ansible) ping all machines
   ```bash
   ./cluster.py ping
   INFO: Pinging all hosts in inventory /home/REDACTED/.config/ansible-sample-conf/inventory-S01.yml (session S01)...
   srv-ubuntu-02 | SUCCESS => {
       "changed": false,
       "ping": "pong"
   }
   srv-ubuntu-01 | SUCCESS => {
       "changed": false,
       "ping": "pong"
   }
   srv-ubuntu-03 | SUCCESS => {
       "changed": false,
       "ping": "pong"
   }
   srv-ubuntu-05 | SUCCESS => {
       "changed": false,
       "ping": "pong"
   }
   srv-ubuntu-04 | SUCCESS => {
       "changed": false,
       "ping": "pong"
   }
   srv-ubuntu-main | SUCCESS => {
       "changed": false,
       "ping": "pong"
   }
   ```
1. Stop the cluster:
```bash
./cluster.py stop
INFO: Cleaning up session S01
```

## Prerequisites

The following tools are required:

- `docker` and `docker-compose`
  - Add `{ "userns-remap": "default" }` in `/etc/docker/daemon.json`
- `python3` + `ven`
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

## Usage

### Menu

This repo provied a menu for easy utilisation, start it like that:
```bash
./menu.py
```

### CLI Commands
The entry point for CLI commands is:

```bash
./cluster.py
```


## Start a cluster

Create a new isolated cluster session from an Ansible inventory:

```bash
./cluster.py start -i inventory/
```

You can even start directely a playbook:

```bash
./cluster.py start -i inventory/ -t ../motd.yml
```
> **Note:** You can add --remove to delete this session right after.

This will:

- Create a new session (S01, S02, …)
- Generate a docker-compose file
- Generate a session-specific inventory


## Ping Hosts

```bash
./cluster.py ping
```

If multiple sessions exist, specify one:

```bash
./cluster.py ping -s S02
```

## Run Tests or Playbooks

Run a specific playbook:

```bash
./cluster.py run -t ../motd.yml
```

Run multiple playbooks:

```bash
./cluster.py run -t ../motd.yml,../test.yml
```
> **Note** : Each playbook path is separated by a `,`

If multiple sessions exist, specify one:

```bash
./cluster.py run -s S02 -t ../motd.yml
```

If you want to add more params to ansible command, add it after : 
```bash
./cluster.py run -t ../motd.yml -- --extra-vars "titi=tutu" --start-at-task "somewhere"
```
> It will take all the params after the `--`.


## List Active Sessions

Show all active sessions:

```bash
./cluster.py sessions
```

Verbose mode:

```bash
./cluster.py sessions -v
```

## Execute Commands On A Machine

### Open an interactive shell

```bash
./cluster.py shell MACHINE_NAME
```

Execute a specific command

```bash
./cluster.py shell MACHINE_NAME COMMAND
```

### Connect via SSH

```bash
./cluster.py ssh MACHINE_NAME
```

> **Note**: If multiple sessions are active, use `-s` to specify the target session (e.g., -s S01).

## Stop and Cleanup

Stop all running clusters:

```bash
./cluster.py stop
```

Stop a specific session

```bash
./cluster.py stop -s S02
```

## Example Workflow

```bash
./cluster.py run
./cluster.py run -t ../motd.yml
./cluster.py stop
```


## Inventory Notes

- Supports a single YAML inventory file or a directory of YAML files
- Hosts must define ansible_port
- SSH access is exposed on localhost with a session-based port offset
- The inventory is automatically rewritten for local execution

Minimal example:

```yaml
web01:
  ansible_port: 22
```


## Important Limitations

Because Docker containers share the host kernel:

- Kernel modules (modprobe) will not work
- Low-level system operations may behave differently
- Docker images are minimal and may require additional packages

You can customize the images in:

```text
Dockerfiles/Dockerfile.*
```


## License

Apache License 2.0


## Related Projects

Ansible Playbooks:
https://github.com/ISC-HEI/ansible-playbooks
