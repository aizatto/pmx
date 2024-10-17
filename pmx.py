#!/usr/bin/python3

import argparse
import asyncio
import json
import subprocess
import sys
import time
import math


async def run_pvesh_command(pvesh_command, api_path, options=[]):
    """Run pvesh command and return JSON output."""
    try:
        process = await asyncio.create_subprocess_exec(
            'pvesh', pvesh_command, *api_path.split(), *options, '--output-format', 'json',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            print(
                f"Error executing pvesh command on {api_path}: {stderr.decode()}", file=sys.stderr)
            return {}

        result = stdout.decode().strip()
        if result == "" or result == None:
            # happens on ha changes
            return {}
        if pvesh_command != "delete":
            return json.loads(result)
        return {}
    except subprocess.CalledProcessError as e:
        print(
            f"Error executing pvesh command on {api_path}: {e.stderr}", file=sys.stderr)


async def get_filtered_cluster_resources(args):
    """
    Fetch resources from Proxmox.

    Args:
    args: command line arguments

    Returns:
    list of dict: Result of pvesh get /cluster/resources
        - 'vmid' (int): VMID
        - 'id' (string): VMID namespaced with type, ie: lxc/100, qemu/101
        - 'node' (string): Node
        - 'type' (string): 'lxc' or 'qemu'
        - 'status' (string): Current status

    Example:
    >>> get_filtered_cluster_resources({'command': 'status'})
    """
    resources = []
    vmids = {}

    if args.node:
        if not args.ids:
            print("Missing Node ids ")
            return resources

        nodes = {}
        for node in args.ids:
            nodes[node] = False

        cluster_resources = await run_pvesh_command('get', '/cluster/resources')
        for resource in cluster_resources:
            if 'node' in resource and resource['node'] in nodes and resource['type'] in ['lxc', 'qemu']:
                nodes[resource['node']] = True

                vmid = resource['vmid']
                vmids[vmid] = True
                resources.append(resource)

        missing = []
        for node, exists in nodes.items():
            if not exists:
                missing.append(node)

        if missing:
            print("Nodes do not exist:")
            for idx, node in enumerate(missing):
                print(f'{idx + 1}. {node}')
    elif args.ids:
        for vmid in args.ids:
            vmids[vmid] = False

        cluster_resources = await run_pvesh_command('get', '/cluster/resources')
        for resource in cluster_resources:
            if resource['type'] in ['lxc', 'qemu'] and str(resource['vmid']) in vmids:
                vmid = str(resource['vmid'])
                vmids[vmid] = True
                resources.append(resource)

        missing = []
        for vmid, exists in vmids.items():
            if not exists:
                missing.append(vmid)

        if missing:
            print("VMs do not exist:")
            for idx, vmid in enumerate(missing):
                print(f'{idx + 1}. {vmid}')

    # These commands are non destructive so we can select all vms.
    # Do not allow destructive commands to select anything.
    elif args.command == "status" or \
            args.command == 'ha' or \
            args.command == 'listsnapshot':
        cluster_resources = await run_pvesh_command('get', '/cluster/resources')
        for resource in cluster_resources:
            if resource['type'] in ['lxc', 'qemu']:
                vmid = str(resource['vmid'])
                vmids[vmid] = True
                resources.append(resource)

    return resources, vmids


async def get_filtered_nodes_replication(nodes):
    guesttoreplicas = {}

    tasks = []
    for node in nodes:
        api_path = f"/nodes/{node}/replication/"
        tasks.append(run_pvesh_command('get', api_path))

    node_configs = await asyncio.gather(*tasks)
    for configs in node_configs:
        for config in configs:
            vmid = config['guest']
            replicas = guesttoreplicas.get(vmid)
            if not replicas:
                replicas = []
                guesttoreplicas[vmid] = replicas
            replicas.append(config)

    vmids = sorted(guesttoreplicas.keys())

    replications = []
    for vmid in vmids:
        configs = guesttoreplicas[vmid]
        configs = sorted(configs, key=lambda x: x['target'])
        for config in configs:
            replications.append(config)

    return replications


async def get_filtered_high_fidelity_cluster_replications(args):
    """
    Used only for retrieving replication information.

    Args:
    args: command line arguments

    Returns
    list of dict: Result of pvesh get /cluster/replication
        - 'guest' (int): VMID
        - 'id' (string): Replication Job ID
        - 'schedule' (string): Storage replication schedule. The format is a subset of `systemd` calendar events.
        - 'schedule' (string): Storage replication schedule. The format is a subset of `systemd` calendar events.
        - 'source' (string): Node currently on
        - 'target' (string): Node to be replicated to
        - 'type' (string)

    Example:
    >>> get_filtered_high_fidelity_cluster_replications({'command': 'replications'})
    [{'guest': 100, 'id': '100-0', 'jobnum': 0, 'schedule': '21:00', 'source': 'node1', 'target': 'node2', 'type': 'local'}]
    """
    replications = []

    if args.node:
        if not args.ids:
            print("Missing Node ids ")
            return replications

        nodes = {}
        for node in args.ids:
            nodes[node] = False

        pvesh_nodes = await run_pvesh_command('get', '/nodes')
        pvesh_nodes = [node["node"] for node in pvesh_nodes]
        for pvesh_node in pvesh_nodes:
            if pvesh_node in nodes:
                nodes[pvesh_node] = True

        exists = []
        missing = []
        for node, node_exists in nodes.items():
            if node_exists:
                exists.append(node)
            else:
                missing.append(node)

        if missing:
            print("Nodes do not exist:")
            for idx, node in enumerate(missing):
                print(f'{idx + 1}. {node}')

        return await get_filtered_nodes_replication(exists)
    elif args.command == 'replications' and not args.ids:
        pvesh_nodes = await run_pvesh_command('get', '/nodes')
        pvesh_nodes = [node["node"] for node in pvesh_nodes]
        return await get_filtered_nodes_replication(pvesh_nodes)
    elif args.ids:
        vmids = {}
        for vmid in args.ids:
            vmids[vmid] = False

        nodesset = {}
        lfreplicas = await get_filtered_low_fidelity_cluster_replications(args)
        for replica in lfreplicas:
            vmid = str(replica['guest'])
            if vmid in vmids:
                nodesset[replica['source']] = True
                vmids[vmid] = True

        missing = []
        for vmid, exists in vmids.items():
            if not exists:
                missing.append(vmid)

        if missing:
            print("VMs do not exist:")
            for idx, vmid in enumerate(missing):
                print(f'{idx + 1}. {vmid}')

        hfreplicas = []
        if vmids:
            hfreplicas = await get_filtered_nodes_replication(nodesset.keys())
            hfreplicas = [replica for replica in hfreplicas if str(
                replica['guest']) in vmids]

        return hfreplicas


async def get_filtered_low_fidelity_cluster_replications(args):
    replications = []

    if args.node:
        if not args.ids:
            print("Missing Node ids ")
            return replications

        nodes = {}
        for node in args.ids:
            nodes[node] = False

        json_replications = await run_pvesh_command('get', '/cluster/replication')
        for replication in json_replications:
            if replication['source'] in nodes:
                nodes[replication['node']] = True
                replications.append(replication)

        missing = []
        for node, exists in nodes.items():
            if not exists:
                missing.append(node)

        if missing:
            print("Nodes do not exist:")
            for idx, node in enumerate(missing):
                print(f'{idx + 1}. {node}')
    elif args.ids:
        vmids = {}
        for vmid in args.ids:
            vmids[vmid] = False

        json_replications = await run_pvesh_command('get', '/cluster/replication')
        for replication in json_replications:
            vmid = str(replication['guest'])
            if vmid in vmids:
                vmids[vmid] = True
                replications.append(replication)

        missing = []
        for vmid, exists in vmids.items():
            if not exists:
                missing.append(vmid)

        if missing:
            print("VMs do not exist:")
            for idx, vmid in enumerate(missing):
                print(f'{idx + 1}. {vmid}')

    return replications


async def get_cluster_ha_resources():
    """
    Docs https://pve.proxmox.com/pve-docs/api-viewer/#/cluster/ha/resources
    """
    ha_resources = {}
    output = await run_pvesh_command('get', '/cluster/ha/resources')
    for resource in output:
        sid = resource.get("sid")
        if sid is None:
            continue

        vmid = sid[3:]
        ha_resources[vmid] = resource

    return ha_resources


async def get_filtered_cluster_ha_resources(vmids):
    """
    Docs https://pve.proxmox.com/pve-docs/api-viewer/#/cluster/ha/resources
    """
    ha_resources = {}
    output = await run_pvesh_command('get', '/cluster/ha/resources')
    for resource in output:
        sid = resource.get("sid")
        if sid is None:
            continue

        vmid = sid[3:]
        if vmid not in vmids:
            continue

        ha_resources[vmid] = resource

    return ha_resources


def humanize_seconds(seconds):
    """Convert seconds to a human-readable format."""
    if seconds == 0 or \
            seconds == None:
        return ""

    minutes, seconds = divmod(math.floor(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def format_status(resource):
    """Format the status output for a single resource."""
    vm_type = resource['type']
    vmid = resource['vmid']
    name = resource['name']
    status = resource['status']
    uptime = resource.get('uptime', 0)

    # Format the uptime to be human-readable, if applicable
    uptime_str = ""
    if status == "running" and uptime > 0:
        uptime_str = humanize_seconds(uptime)
    return f"{vm_type}/{vmid}: {name} {status} {uptime_str}".strip()


def print_resource_status(args, resources):
    """Print the status of each resource."""
    for resource in resources:
        print(format_status(resource))


def validate_actions(vmid, action, status):
    """Validate if the requested action can be performed based on the status."""
    if status == "stopped" and action in ["stop", "shutdown"]:
        print(f"VM {vmid} is already stopped. Only 'start' is allowed.")
        return False
    if status == "running" and action == "start":
        print(
            f"VM {vmid} is already running. Only 'stop' or 'shutdown' are allowed.")
        return False
    return True


async def perform_command(args, resource):
    """Perform the specified action on a single resource."""
    action = args.command

    vmid = resource['vmid']
    if not resource:
        print(f"Resource {vmid} not found.")
        return

    status = resource['status']
    if not validate_actions(vmid, action, status):
        return

    api_path = f"/nodes/{resource['node']}/{resource['type']}/{vmid}/status/{action}"
    try:
        print(
            f"{action.capitalize()} command sent for {resource['type']}/{vmid}.")
        await run_pvesh_command('create', api_path)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh command: {e.stderr}", file=sys.stderr)


async def destroy_command(args, resource):
    """Destroy the specified resources."""
    purge = not args.do_not_purge_jobs
    destroy_unreferenced_disks = not args.do_not_destroy_unreferenced_disks

    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    try:
        api_path = f"/nodes/{resource['node']}/{resource['type']}/{vmid}"
        options = []
        if purge:
            options.append("--purge")
        if destroy_unreferenced_disks:
            options.append("--destroy-unreferenced-disks")
        print(f"Destroying {resource['type']}/{vmid}.")
        await run_pvesh_command('delete', api_path, options)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def snapshot_command(args, resource):
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    try:
        api_path = f"/nodes/{resource['node']}/{resource['type']}/{vmid}/snapshot"
        options = ["--snapname", args.name]
        if args.description:
            options.append("--description")
            options.append(args.description)
        print(f"Snapshotting {resource['type']}/{vmid}.")
        await run_pvesh_command('create', api_path, options)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def delsnapshot_command(args, resource):
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    try:
        api_path = f"/nodes/{resource['node']}/{resource['type']}/{vmid}/snapshot/{args.name}"
        options = []
        if args.force:
            options.append("--force")
            options.append("true")
        print(f"Delete Snapshot {resource['type']}/{vmid}.")
        await run_pvesh_command('delete', api_path, options)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def listsnapshot_command(args, resource):
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    try:
        api_path = f"/nodes/{resource['node']}/{resource['type']}/{vmid}/snapshot"
        # print(f"List Snapshot {resource['type']}/{vmid}.")
        snapshots = await run_pvesh_command('ls', api_path)
        for snapshot in snapshots:
            print(f"{resource['id']}: {snapshot['name']}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def vzdump_command(args, resource):
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    try:
        api_path = f"/nodes/{resource['node']}/vzdump"
        options = ["--vmid", str(vmid), "--compress", "zstd"]
        print(f"Vzdump {resource['id']}")
        await run_pvesh_command('create', api_path, options)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def ha_command(args, resource, ha_resource):
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    if ha_resource:
        print(f"{resource['id']}: {ha_resource['state']}")
    else:
        print(f"{resource['id']}: does not exist")


async def ha_set_command(args, resource, ha_resource):
    """
    Docs https://pve.proxmox.com/pve-docs/api-viewer/#/cluster/ha/resources/{sid}
    """
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    try:
        if ha_resource:
            if args.ha_state == ha_resource.get("state"):
                print(
                    f"{resource['type']}/{vmid} state is already {ha_resource['state']}")
                return

            sid = ha_resource["sid"]

            api_path = f"/cluster/ha/resources/{sid}"
            options = ["--state", args.ha_state]
            print(
                f"Updating ha {resource['type']}/{vmid} state: {args.ha_state}")
            await run_pvesh_command('set', api_path, options)
        else:
            sid = f'ct:{vmid}'
            if resource['type'] == 'qemu':
                sid = f'vm:{vmid}'
            options = ["--sid", sid, "--comment",
                       resource['name'], "--state", args.ha_state]
            print(
                f"Creating ha {resource['type']}/{vmid} state: {args.ha_state}")
            await run_pvesh_command('create', "/cluster/ha/resources", options)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def ha_set_started_all_command(args, resource, ha_resource):
    vmid = resource['vmid']
    if not resource or not ha_resource:
        return

    if "started" == ha_resource.get("state"):
        print(
            f"{resource['type']}/{vmid} state is already {ha_resource['state']}")
        return

    sid = ha_resource["sid"]

    api_path = f"/cluster/ha/resources/{sid}"
    options = ["--state", "started"]
    print(
        f"Updating ha {resource['type']}/{vmid} state: {args.ha_state}")
    await run_pvesh_command('set', api_path, options)


async def ha_set_ignored_all_command(args, resource, ha_resource):
    vmid = resource['vmid']
    if not resource or not ha_resource:
        return

    if "ignored" == ha_resource.get("state"):
        print(
            f"{resource['type']}/{vmid} state is already {ha_resource['state']}")
        return

    sid = ha_resource["sid"]

    api_path = f"/cluster/ha/resources/{sid}"
    options = ["--state", "ignored"]
    print(
        f"Updating ha {resource['type']}/{vmid} state: {args.ha_state}")
    await run_pvesh_command('set', api_path, options)


async def ha_remove_command(args, resource, ha_resource):
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return

    try:
        if not ha_resource:
            print(f"HA resources does not exist {resource['id']}")
            return

        sid = ha_resource["sid"]
        api_path = f"/cluster/ha/resources/{sid}"
        print(f"Remove HA {resource['type']}/{vmid}")
        await run_pvesh_command('delete', api_path)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def run_on_cluster_resources(args, resources, fn):
    if args.sync:
        for resource in resources:
            await fn(args, resource)
        return

    tasks = []
    if args.node:
        for resource in resources:
            tasks.append(fn(args, resource))
    elif args.ids:
        for id in args.ids:
            foundresource = None
            for resource in resources:
                vmid = resource.get('vmid')
                if vmid and str(vmid) == id:
                    foundresource = resource
                    break

            if not foundresource:
                continue

            tasks.append(fn(args, resource))
    else:
        for resource in resources:
            tasks.append(fn(args, resource))
    await asyncio.gather(*tasks)


async def run_on_ha_resources(args, ha_resources, fn):
    if args.sync:
        for resource in ha_resources:
            await fn(args, resource)
        return

    tasks = []
    if args.node:
        for resource in ha_resources:
            tasks.append(fn(args, resource))
    else:
        for id in args.ids:
            resources = []
            for resource in ha_resources:
                vmid = resource.get('guest')
                if vmid and str(vmid) == id:
                    resources.append(resource)

            if not resources:
                continue

            for resource in resources:
                tasks.append(fn(args, resource))
    await asyncio.gather(*tasks)


def replications_command(args, replications):
    current_unix_time = int(time.time())

    def since(unix_time):
        if unix_time == None:
            return ""

        return humanize_seconds(abs(current_unix_time - unix_time))

    for config in replications:
        disable = config.get('disable', "")
        if disable == 1:
            disable = "(disabled)"

        remove_job = config.get('remove_job', "")
        if remove_job == 1:
            remove_job = "(remove_job)"

        comment = config.get('comment')
        schedule = config.get('schedule')

        duration = humanize_seconds(config.get('duration'))
        last_sync = since(config.get('last_sync'))
        last_try = since(config.get('last_try'))
        next_sync = since(config.get('next_sync'))
        print(f"{config['id']} {config['source']} -> {config['target']} {schedule}: {duration} / {last_sync} / {last_try} / {next_sync} {comment} {disable} {remove_job}")


async def replication_schedule_now(args, replication):
    if replication.get('disable') == 1:
        return

    try:
        api_path = f"/nodes/{replication['source']}/replication/{replication['id']}/schedule_now"
        print(
            f"Replication {replication['guest']} {replication['source']} -> {replication['target']}")
        await run_pvesh_command('create', api_path)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def main_replications(args):
    if args.command == 'replications':
        replications = await get_filtered_high_fidelity_cluster_replications(args)
        replications_command(args, replications)
    elif args.command == 'replication-schedule-now':
        replications = await get_filtered_high_fidelity_cluster_replications(args)
        await run_on_ha_resources(args, replications, replication_schedule_now)
    else:
        print(f"Command missing implementation: {args.command}")


async def main_ha(args):
    ha_resources = await get_cluster_ha_resources()
    vmids = ha_resources.keys()

    args2 = argparse.Namespace()
    args2.ids = vmids
    args2.node = None
    args2.command = None
    (resources, _) = await get_filtered_cluster_resources(args2)

    if args.command == 'ha-set-started-all':
        async def ha_set_started_all_command_helper(args, resource):
            ha_resource = ha_resources.get(str(resource["vmid"]))
            await ha_set_started_all_command(args, resource, ha_resource)

        await run_on_cluster_resources(args, resources, ha_set_started_all_command_helper)
    elif args.command == 'ha-set-ignored-all':
        async def ha_set_ignored_all_command_helper(args, resource):
            ha_resource = ha_resources.get(str(resource["vmid"]))
            await ha_set_ignored_all_command(args, resource, ha_resource)

        await run_on_cluster_resources(args, resources, ha_set_ignored_all_command_helper)


async def main_vms(args):
    (resources, vmids) = await get_filtered_cluster_resources(args)

    if not resources:
        print("No resources found")
        return

    if args.command == 'status':
        print_resource_status(args, resources)
    elif args.command in ['start', 'stop', 'shutdown', 'reboot', 'resume', 'suspend']:
        await run_on_cluster_resources(args, resources, perform_command)
    elif args.command == 'destroy':
        if not args.ids:
            print(f"An ID is required when destroying a vm")
            return

        if not args.skip_confirm:
            print("Are you sure you want to destroy the following resources?")
            for idx, resource in enumerate(resources):
                print(f"{idx + 1}. {resource['id']}: {resource['name']}")
            print("\n")

            confirm = input("Enter 'y' to confirm: ").lower()
            if not (confirm == 'y' or confirm == "yes"):
                print("Cancelled destroying resources")
                return

        await run_on_cluster_resources(args, resources, destroy_command)
    elif args.command == 'snapshot':
        if not args.name:
            print("--name argument is required")
            return

        await run_on_cluster_resources(args, resources, snapshot_command)
    elif args.command == 'delsnapshot':
        if not args.name:
            print("--name argument is required")
            return

        await run_on_cluster_resources(args, resources, delsnapshot_command)
    elif args.command == 'listsnapshot':
        await run_on_cluster_resources(args, resources, listsnapshot_command)
    elif args.command == 'vzdump':
        await run_on_cluster_resources(args, resources, vzdump_command)
    elif args.command == 'ha':
        ha_resources = await get_filtered_cluster_ha_resources(vmids)

        async def ha_command_helper(args, resource):
            ha_resource = ha_resources.get(str(resource["vmid"]))
            await ha_command(args, resource, ha_resource)

        await run_on_cluster_resources(args, resources, ha_command_helper)
    elif args.command == 'ha-set':
        ha_resources = await get_filtered_cluster_ha_resources(vmids)

        async def ha_set_command_helper(args, resource):
            ha_resource = ha_resources.get(str(resource["vmid"]))
            await ha_set_command(args, resource, ha_resource)

        await run_on_cluster_resources(args, resources, ha_set_command_helper)
    elif args.command == 'ha-remove':
        if not args.ids:
            print(f"An ID is required when removing an HA configuration")
            return

        ha_resources = await get_filtered_cluster_ha_resources(vmids)

        async def ha_remove_command_helper(args, resource):
            ha_resource = ha_resources.get(str(resource["vmid"]))
            await ha_remove_command(args, resource, ha_resource)

        await run_on_cluster_resources(args, resources, ha_remove_command_helper)
    else:
        print(f"Command missing implementation: {args.command}")


async def main():
    parser = argparse.ArgumentParser(
        description='Manage Proxmox VMs and containers.')
    parser.add_argument('--node', action='store_true',
                        help='Treat ids as node names')
    parser.add_argument('--sync', action='store_true',
                        help='Run commands synchronously.')
    parser.add_argument('--skip-confirm', action='store_true',
                        help='On destroy, skip confirm.', default=False)
    parser.add_argument('--do-not-purge-jobs', action='store_true',
                        help='On destroy, skip purging from job configurations.', default=False)
    parser.add_argument('--do-not-destroy-unreferenced-disks', action='store_true',
                        help='On destroy, skip destroy unreferenced disks.', default=False)
    parser.add_argument('--name', action='store',
                        help='On snapshot, saves a name. Required for snapshot.', default=False)
    parser.add_argument('--description', action='store',
                        help='On snapshot, saves a description.', default=False)
    parser.add_argument('--force', action='store_true',
                        help='On delsnapshot, For removal from config file, even if removing disk snapshots fails.', default=False)
    parser.add_argument('--ha-state', nargs="?", choices=['started', 'stopped', 'disabled', 'ignored'],
                        help='For ha command. Requested resource state. The CRM reads this state and acts accordingly. Please note that `enabled` is just an alias for `started`.', default="started")
    parser.add_argument(
        'command',
        nargs='?',
        choices=[
            'status',
            'start',
            'stop',
            'shutdown',
            'reboot',
            'resume',
            'suspend',
            'destroy',
            'snapshot',
            'delsnapshot',
            'listsnapshot',
            'vzdump',
            'replications',
            'replication-schedule-now',
            'ha',
            'ha-set',
            'ha-set-started-all',
            'ha-set-ignored-all',
            'ha-remove',
        ],
        default="status",
        help='Action to perform.'
    )
    parser.add_argument('ids', nargs='*', help='VM/Container IDs.')
    args = parser.parse_args()

    if args.command == "replication-schedule-now" or \
            args.command == "replications":
        await main_replications(args)
    elif args.command == "ha-set-started-all" or \
            args.command == "ha-set-ignored-all":
        await main_ha(args)
    else:
        await main_vms(args)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
        sys.exit(1)
