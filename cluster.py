#!/usr/bin/env python3

import yaml
import subprocess
import sys
import os
import argparse
import json
import shutil
import socket
import logging
import re
from pathlib import Path

TEMP_DIRECTORY = Path.home() / ".config/ansible-sample-conf"
MEMO_FILE = f"{TEMP_DIRECTORY}/cluster_session.json"
DOCKERFILES_DIRECTORY = "./Dockerfiles"
DEBUG_LEVEL = 0
EXTRA_ARGS_DELIMITER = "--"

os.makedirs(TEMP_DIRECTORY, exist_ok=True)

# Helpers

def load_inventory(path_or_file):
    """Load inventory from a YAML file or directory of YAML files, merging hosts."""
    data = {}
    if os.path.isdir(path_or_file):
        for filename in os.listdir(path_or_file):
            if filename.endswith((".yaml", ".yml")):
                full_path = os.path.join(path_or_file, filename)
                with open(full_path, "r") as f:
                    file_data = yaml.safe_load(f)
                    if file_data:
                        for key, val in file_data.items():
                            if key not in data:
                                data[key] = val
                            else:
                                for group_name, group_content in val.get("children", {}).items():
                                    if "children" not in data[key]:
                                        data[key]["children"] = {}
                                    if group_name not in data[key]["children"]:
                                        data[key]["children"][group_name] = group_content
                                    else:
                                        existing_hosts = data[key]["children"][group_name].get("hosts", {})
                                        new_hosts = group_content.get("hosts", {})
                                        existing_hosts.update(new_hosts)
                                        data[key]["children"][group_name]["hosts"] = existing_hosts
    else:
        with open(path_or_file, "r") as f:
            data = yaml.safe_load(f)
    return data

def generate_docker_compose(data, sessionId):
    """Generate docker-compose.yml dictionary from inventory data with dynamic subnet."""
    docker_compose = {"services": {}}
    root = data.get("test_inv", data)
    vars = root.get("vars", {})
    dockerfile = vars.get("dockerfile")
    children = root.get("children", {})
    built_images = set()

    try:
        session_num = int(sessionId[1:])
    except ValueError:
        session_num = 0

    subnet_prefix = f"172.{19 + session_num}"

    host_ip_map = {}
    ip_counter = 2
    for group in children.values():
        for host in group.get("hosts", {}).keys():
            host_ip_map[host] = f"{subnet_prefix}.0.{ip_counter}"
            ip_counter += 1

    all_extra_hosts = [f"{name}:{ip}" for name, ip in host_ip_map.items()]

    for group in children.values():
        for host, host_vars in group.get("hosts", {}).items():
            assigned_ip = host_ip_map[host]
            docker_image = (host_vars.get("dockerfile") if host_vars else None) or dockerfile

            if docker_image and docker_image not in built_images:
                create_docker_images(docker_image, sessionId)
                built_images.add(docker_image)

            service_config = {
                "image": f"{docker_image}:latest",
                "container_name": f"{sessionId}-{host}",
                "hostname": host,
                "extra_hosts": [h for h in all_extra_hosts if not h.startswith(f"{host}:")],
                "tmpfs": ["/run", "/run/lock"],
                "networks": {
                    f"{sessionId}-cluster-net": {
                        "ipv4_address": assigned_ip
                    }
                },
                "deploy": {
                    "resources": {
                        "limits": {"cpus": "1.0", "memory": "512M"}
                    }
                },
            }

            if host_vars:
                if host_vars.get("is_entry_point"):
                    port = host_vars.get("ansible_port")
                    update_session(sessionId, entryIp=assigned_ip)
                    if port:
                        host_port = session_port_offset(port, sessionId)
                        service_config["ports"] = [f"{host_port}:22"]
                    else:
                        raise ValueError(f"Entry point {host} missing ansible_port")

            docker_compose["services"][host] = service_config

    docker_compose["networks"] = {
        f"{sessionId}-cluster-net": {
            "driver": "bridge",
            "ipam": {
                "config": [{"subnet": f"{subnet_prefix}.0.0/16"}]
            }
        }
    }
    return docker_compose

def is_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except:
        return False

def path_exist(path):
    if not Path(path).exists():
        logging.error(f"Path {path} doesn't exist")
        sys.exit(1)

def check_dependencies():
    logging.debug("Checking dependencies...")
    dependencies = ["docker", "sshpass", "ansible-playbook"]
    missing = []

    for tool in dependencies:
        logging.debug(f"Checking for {tool}.")
        if shutil.which(tool) is None:
            missing.append(tool)

    if "docker" not in missing:
        logging.debug("Checking for docker compose.")
        result = subprocess.run(["docker", "compose", "version"], capture_output=True)
        if result.returncode != 0:
            missing.append("docker compose (plugin)")

    if missing:
        logging.error(f"Missing dependencies: {', '.join(missing)}")
        logging.error("Please install the missing tools before running this script.")
        sys.exit(1)

# logging

def setup_logging(quiet=False, debug=0):
    if quiet:
        level = logging.ERROR
    elif debug >= 1:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
    )

def run_cmd(cmd):
    logging.debug(f"Running command: {' '.join(cmd)}")

    return subprocess.run(
        cmd,
        check=True,
        stdout=None if DEBUG_LEVEL >= 2 else subprocess.DEVNULL,
        stderr=None if DEBUG_LEVEL >= 2 else subprocess.DEVNULL
    )

# docker images

def create_docker_images(dockerfile, sessionId):
    image_name = dockerfile
    dockerfile_path = os.path.join(DOCKERFILES_DIRECTORY, f"Dockerfile.{dockerfile}")
    logging.info(f"Building docker image '{dockerfile}'")
    run_cmd(["docker", "build", "-t", image_name, "-f", dockerfile_path, "."])

# session

def create_session(path):
    sessions = {}

    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                sessions = json.load(f)
            except json.JSONDecodeError:
                sessions = {}

    if sessions:
        numbers = [int(s[1:]) for s in sessions if s.startswith("S") and s[1:].isdigit()]
        next_number = max(numbers) + 1 if numbers else 1
    else:
        next_number = 1

    new_session = f"S{next_number:02d}"
    sessions[new_session] = {"path": path}

    with open(MEMO_FILE, "w") as f:
        json.dump(sessions, f)

    return new_session

def update_session(sessionId, path=None, entryIp=None):
    sessions = get_all_sessions() or {}
    session_data = sessions.get(sessionId, {"path": None, "entryIp": "0.0.0.0"})

    if path is not None: session_data["path"] = path
    if entryIp is not None: session_data["entryIp"] = entryIp

    sessions[sessionId] = session_data

    with open(MEMO_FILE, "w") as f:
        json.dump(sessions, f, indent=2)

def get_session(sessionId):
    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                data = json.load(f)
                return data.get(sessionId)
            except json.JSONDecodeError:
                return None
    return None

def get_all_sessions():
    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                data = json.load(f)
                return data
            except json.JSONDecodeError:
                return None
    return None

def generate_session_inventory(data, sessionId, output_path):
    root_name = "test_inv" if "test_inv" in data else None
    root = data[root_name] if root_name else data
    vars_root = root.get("vars", {})
    ansible_pass = vars_root.get("ansible_ssh_pass", "password")

    jump_host_base_port = 22
    for group in root.get("children", {}).values():
            for host_name, host_vars in group.get("hosts", {}).items():
                if host_vars and host_vars.get("is_entry_point") is True:
                    jump_host_base_port = host_vars.get("ansible_port", 22)
                    break

    jump_port = session_port_offset(jump_host_base_port, sessionId)
    ansible_user = vars_root.get("ansible_user", "ubuntu")

    session_root = {
        "vars": {**vars_root},
        "children": {}
    }

    for group_name, group in root.get("children", {}).items():
        session_root["children"][group_name] = {"hosts": {}}

        for host, host_vars in group.get("hosts", {}).items():
            if host_vars:
                new_vars = {**host_vars}
            else:
                new_vars = {}

            if host_vars and host_vars.get("is_entry_point"):
                new_vars["ansible_host"] = "127.0.0.1"
                new_vars["ansible_port"] = jump_port
                new_vars["ansible_ssh_common_args"] = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            else:
                new_vars["ansible_host"] = host
                new_vars["ansible_port"] = 22

                proxy_cmd = f"ssh -W %h:%p -q {ansible_user}@127.0.0.1 -p {jump_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
                new_vars["ansible_ssh_common_args"] = f"-o ProxyCommand='sshpass -p {ansible_pass} {proxy_cmd}'"

            session_root["children"][group_name]["hosts"][host] = new_vars

    session_inventory = {root_name: session_root} if root_name else session_root

    with open(output_path, "w") as f:
        yaml.dump(session_inventory, f, sort_keys=False)

def session_port_offset(base_port, sessionId):
    port = base_port + (int(sessionId[1:]) - 1) * 100
    while is_port_open(port):
        port += 10
    return port

# Functions link to command

def start(inventory, test_path, delete):
    logging.debug(f"Using inventory: {inventory}")
    sessionId = create_session(inventory)
    logging.info(f"Your session id is {sessionId}")

    logging.debug("Loading inventory...")
    try:
        data = load_inventory(inventory)
    except Exception:
        logging.exception("Error reading inventory")
        sys.exit(1)

    logging.debug("Generating docker-compose.yml...")
    docker_compose = generate_docker_compose(data, sessionId)

    logging.debug("Generating session inventory...")
    session_inventory_path = f"{TEMP_DIRECTORY}/inventory-{sessionId}.yml"
    generate_session_inventory(data, sessionId, session_inventory_path)

    update_session(sessionId, session_inventory_path)

    with open(f"{TEMP_DIRECTORY}/docker-compose-{sessionId}.yml", "w") as f:
        yaml.dump(docker_compose, f, sort_keys=False)

    logging.info("Starting containers...")
    try:
        run_cmd([
                "docker", "compose",
                "-p", sessionId.lower(),
                "-f", f"{TEMP_DIRECTORY}/docker-compose-{sessionId}.yml",
                "up", "-d", "--build"
            ])
        if (test_path):
            run(test_path, sessionId)
            if (delete):
                stop(sessionId)
    except subprocess.CalledProcessError:
        logging.error("Error starting Docker containers")
        sys.exit(1)

def run(test_path, sessionId, extra_args=None):
    if extra_args and extra_args[0] == EXTRA_ARGS_DELIMITER:
        extra_args.pop(0)

    sessions = get_all_sessions()

    if not sessions:
        logging.error("Error: no active session found. Please start a session first.")
        sys.exit(1)

    if sessionId:
        if sessionId not in sessions:
            logging.error(f"Error: session {sessionId} does not exist")
            sys.exit(1)
    else:
        if len(sessions) == 1:
            sessionId = next(iter(sessions))
        else:
            logging.error("Error: multiple sessions found, please specify one with -s")
            sys.exit(1)

    inventory = sessions.get(sessionId)["path"]
    if not inventory:
        logging.error("Error: no inventory associated with this session")
        sys.exit(1)

    logging.info(f"Running playbook {test_path} on inventory {inventory} (session {sessionId})...")
    tests = test_path.split(",")
    for test in tests:  
        command = ["ansible-playbook", "-i", inventory, test, "-e", "conf_dir=" + os.path.dirname(os.path.abspath(__file__))]

        if extra_args:
            command.extend(extra_args)

        logging.debug(f"command:'{command}'")
        subprocess.run(command)

def stop(sessionId=None):
    sessions = get_all_sessions()
    if not sessions:
        logging.info("No active sessions to stop.")
        return

    target_sessions = [sessionId] if sessionId else list(sessions.keys())

    for s in target_sessions:
        if s not in sessions:
            logging.error(f"Session {s} does not exist.")
            continue
            
        logging.info(f"Cleaning up session {s}")
        compose_file = f"{TEMP_DIRECTORY}/docker-compose-{s}.yml"
        
        if os.path.exists(compose_file):
            run_cmd([
                "docker", "compose",
                "-p", s.lower(),
                "-f", compose_file,
                "kill"
            ])
            run_cmd([
                "docker", "compose",
                "-p", s.lower(),
                "-f", compose_file,
                "down"
            ])
            os.remove(compose_file)
            inv_file = f"{TEMP_DIRECTORY}/inventory-{s}.yml"
            if os.path.exists(inv_file): os.remove(inv_file)

    new_sessions = {k: v for k, v in sessions.items() if k not in target_sessions}
    if not new_sessions:
        if os.path.exists(MEMO_FILE): os.remove(MEMO_FILE)
        if os.path.exists(TEMP_DIRECTORY): shutil.rmtree(TEMP_DIRECTORY)
    else:
        with open(MEMO_FILE, "w") as f:
            json.dump(new_sessions, f, indent=2)

def sessions(verbose):
    sessions = get_all_sessions()
    if (sessions):
        for s in sessions:
            if (verbose):
                print(f"{s}    {sessions[s]}")
            else:
                print(s)

def shell(machine_name, sessionId, command=None):
    sessions = get_all_sessions()
    if not sessions:
        logging.error("Error: no active sessions found.")
        sys.exit(1)

    if not sessionId:
        if len(sessions) == 1:
            sessionId = list(sessions.keys())[0]
        else:
            logging.error(f"Multiple sessions active: {list(sessions.keys())}. Use -s [ID]")
            sys.exit(1)

    container_name = f"{sessionId}-{machine_name}"
    
    docker_exec = ["docker", "exec", "-it", container_name]

    if command:
        docker_exec.extend(["sh", "-c", command])
    else:
        docker_exec.append("/bin/bash")

    try:
        subprocess.run(docker_exec)
    except Exception as e:
        logging.error(f"Could not connect to {machine_name}: {e}")

def ssh(machine_name, sessionId):
    sessions = get_all_sessions()
    if not sessions:
        logging.error("Error: no active sessions found.")
        sys.exit(1)

    if not sessionId:
        if len(sessions) == 1:
            sessionId = list(sessions.keys())[0]
        else:
            logging.error(f"Multiple sessions active: {list(sessions.keys())}. Use -s [ID]")
            sys.exit(1)

    inventory_path = sessions[sessionId]["path"]
    with open(inventory_path, "r") as f:
        inv_data = yaml.safe_load(f)
    
    root_key = "test_inv" if "test_inv" in inv_data else None
    root = inv_data[root_key] if root_key else inv_data
    vars_root = root.get("vars", {})
    
    ansible_user = vars_root.get("ansible_user", "ubuntu")
    ansible_pass = vars_root.get("ansible_ssh_pass", "password")

    logging.info(f"Connecting to {machine_name} via SSH (session {sessionId})...")
    
    cmd = ["sshpass", "-p", ansible_pass, "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    
    found = False
    for group in root.get("children", {}).values():
        if machine_name in group.get("hosts", {}):
            host_vars = group["hosts"][machine_name]
            target_host = host_vars.get("ansible_host", machine_name)
            target_port = host_vars.get("ansible_port", 22)
            
            if host_vars.get("is_entry_point"):
                cmd.extend(["-p", str(target_port), f"{ansible_user}@127.0.0.1"])
            else:
                proxy_args = host_vars.get("ansible_ssh_common_args", "")
                if "ProxyCommand" in proxy_args:
                    match = re.search(r"ProxyCommand='(.*)'", proxy_args)
                    if match:
                        cmd.extend(["-o", f"ProxyCommand={match.group(1)}"])
                
                cmd.extend([f"{ansible_user}@{target_host}"])
            found = True
            break
    
    if not found:
        logging.error(f"Machine {machine_name} not found in inventory.")
        sys.exit(1)

    try:
        subprocess.run(cmd)
    except Exception as e:
        logging.error(f"SSH connection failed: {e}")

def ping(sessionId):
    sessions = get_all_sessions()

    if not sessions:
        logging.error("Error: no active session found. Please start a session first.")
        sys.exit(1)

    if sessionId:
        if sessionId not in sessions:
            logging.error(f"Error: session {sessionId} does not exist")
            sys.exit(1)
    else:
        if len(sessions) == 1:
            sessionId = next(iter(sessions))
        else:
            logging.error("Error: multiple sessions found, please specify one with -s")
            sys.exit(1)

    inventory = sessions.get(sessionId)["path"]
    if not inventory:
        logging.error("Error: no inventory associated with this session")
        sys.exit(1)

    logging.info(f"Pinging all hosts in inventory {inventory} (session {sessionId})...")
    subprocess.run(["ansible", "all", "-m", "ping", "-i", inventory])

# Main function

def main():
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-q", "--quiet", help="Only print errors", action="store_true")
    parent_parser.add_argument("-d", "--debug", type=int, default=0, metavar="N", help="Debug level (0=info, 1=verbose, 2=commands output)")

    parser = argparse.ArgumentParser(
        description="Manage virtual cluster with Docker + Ansible",
        parents=[parent_parser]
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # START
    start_parser = subparsers.add_parser("start", help="Start the virtual cluster", parents=[parent_parser])
    start_parser.add_argument("-i", "--inventory", required=True, help="Inventory YAML file or directory path")
    start_parser.add_argument("-t", "--test", help="Playbook path")
    start_parser.add_argument("--remove", action="store_true", help="Remove the session, usefull with the --test flag")


    # RUN
    run_parser = subparsers.add_parser("run", help="Run playbook on hosts", parents=[parent_parser])
    run_parser.add_argument("-t", "--test", required=True, help="Playbook path")
    run_parser.add_argument("-s", "--session", help="The session ID, optional if only one session")

    run_parser.add_argument("extra_ansible_args", nargs=argparse.REMAINDER, help="All extra args for ansible")

    # STOP
    stop_parser = subparsers.add_parser("stop", help="Stop the virtual cluster", parents=[parent_parser])
    stop_parser.add_argument("-s", "--session", help="The session ID to stop, if empty stops all")

    # SESSIONS
    session_parser = subparsers.add_parser("sessions", help="Show all the active sessions")
    session_parser.add_argument("-v", "--verbose", help="Show all the infos about a session", action="store_true")

    # SHELL
    shell_parser = subparsers.add_parser("shell", help="Open a shell in a specific machine", parents=[parent_parser])
    shell_parser.add_argument("machine", help="The machine name")
    shell_parser.add_argument("cmd", nargs="?", default=None, help="The command to execute (optional)")
    shell_parser.add_argument("-s", "--session", help="The session ID, optional if only one session")

    # SSH
    ssh_parser = subparsers.add_parser("ssh", help="Connect to a machine using SSH", parents=[parent_parser])
    ssh_parser.add_argument("machine", help="The machine name")
    ssh_parser.add_argument("-s", "--session", help="The session ID, optional if only one session")

    # PING
    ping_parser = subparsers.add_parser("ping", help="Ping hosts", parents=[parent_parser])
    ping_parser.add_argument("-s", "--session", help="The session ID, optional if only one session")

    args = parser.parse_args()

    extra_ansible_args = getattr(args, "extra_ansible_args", [])

    global INVENTORY, TEST_PATH
    INVENTORY = getattr(args, "inventory", None)
    TEST_PATH = getattr(args, "test", None)
    sessionId = getattr(args, "session", None)

    global DEBUG_LEVEL
    DEBUG_LEVEL = args.debug
    setup_logging(args.quiet, args.debug)

    check_dependencies()

    match args.command:
        case "start":
            path_exist(INVENTORY)
            delete = getattr(args, "remove", False)
            if TEST_PATH:
                for path in TEST_PATH.split(","):
                    path_exist(path.strip())
            start(INVENTORY, TEST_PATH, delete)
        case "run":
            if INVENTORY: path_exist(INVENTORY)
            if TEST_PATH:
                for path in TEST_PATH.split(","):
                    path_exist(path.strip())
            run(TEST_PATH, sessionId, extra_ansible_args)
        case "stop":
            stop(sessionId)
        case "sessions":
            sessions(args.verbose)
        case "shell":
            shell(args.machine, args.session, args.cmd)
        case "ssh":
            ssh(args.machine, args.session)
        case "ping":
            ping(sessionId)

if __name__ == "__main__":
    main()
