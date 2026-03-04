# Usage

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

## Stop

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
