#!/usr/bin/python3

import argparse
import asyncio
import json
import subprocess
import sys
import time
import math


def run_pvesh_command(pvesh_command, api_path, options=[]):
    """Run pvesh command and return JSON output."""
    try:
        result = subprocess.run(
            ['pvesh', pvesh_command] + api_path.split() + options +
            ['--output-format', 'json'],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if pvesh_command != "delete":
            return json.loads(result.stdout)
        return ""
    except subprocess.CalledProcessError as e:
        print(
            f"Error executing pvesh command on {api_path}: {e.stderr}", file=sys.stderr)


def get_cluster_resources(args):
    """Fetch resources from Proxmox."""
    resources = []

    if args.node:
        if not args.ids:
            print("Missing Node ids ")
            return resources

        nodes = {}
        for node in args.ids:
            nodes[node] = False

        cluster_resources = run_pvesh_command('get', '/cluster/resources')
        for resource in cluster_resources:
            if 'node' in resource and resource['node'] in nodes and resource['type'] in ['lxc', 'qemu']:
                nodes[resource['node']] = True
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
        vmids = {}
        for vmid in args.ids:
            vmids[vmid] = False

        cluster_resources = run_pvesh_command('get', '/cluster/resources')
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

    # These commands are non destructive
    elif args.command == "status" or \
            args.command == 'listsnapshot':
        cluster_resources = run_pvesh_command('get', '/cluster/resources')
        for resource in cluster_resources:
            if resource['type'] in ['lxc', 'qemu']:
                resources.append(resource)

    return resources


def get_nodes_replication(nodes):
    guesttoreplicas = {}

    for node in nodes:
        api_path = f"/nodes/{node}/replication/"
        configs = run_pvesh_command('get', api_path)
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

# To only be used for status information


def get_high_fidelity_cluster_replications(args):
    replications = []

    if args.node:
        if not args.ids:
            print("Missing Node ids ")
            return replications

        nodes = {}
        for node in args.ids:
            nodes[node] = False

        pvesh_nodes = run_pvesh_command('get', '/nodes')
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

        return get_nodes_replication(exists)
    elif args.command == 'replications' and not args.ids:
        pvesh_nodes = run_pvesh_command('get', '/nodes')
        pvesh_nodes = [node["node"] for node in pvesh_nodes]
        return get_nodes_replication(pvesh_nodes)
    elif args.ids:
        vmids = {}
        for vmid in args.ids:
            vmids[vmid] = False

        nodesset = {}
        lfreplicas = get_low_fidelity_cluster_replications(args)
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
        if not missing:
            hfreplicas = get_nodes_replication(nodesset.keys())
            hfreplicas = [replica for replica in hfreplicas if str(
                replica['guest']) in vmids]

        return hfreplicas


def get_low_fidelity_cluster_replications(args):
    replications = []

    if args.node:
        if not args.ids:
            print("Missing Node ids ")
            return replications

        nodes = {}
        for node in args.ids:
            nodes[node] = False

        json_replications = run_pvesh_command('get', '/cluster/replication')
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

        json_replications = run_pvesh_command('get', '/cluster/replication')
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
        run_pvesh_command('create', api_path)
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
        run_pvesh_command('delete', api_path, options)
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
        run_pvesh_command('create', api_path, options)
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
        run_pvesh_command('delete', api_path, options)
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
        snapshots = run_pvesh_command('ls', api_path)
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
        options = ["--vmid", vmid, "--compress", "zstd"]
        print(f"Vzdump {resource['type']}/{vmid}.")
        run_pvesh_command('create', api_path, options)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def run_on_resources(args, resources, fn):
    if args.sync:
        for resource in resources:
            await fn(args, resource)
    else:
        tasks = []
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
    if replication['disable']:
        return

    try:
        api_path = f"/nodes/{replication['source']}/replication/{replication['id']}/schedule_now"
        print(
            f"Replication {replication['guest']} {replication['source']} -> {replication['target']}")
        run_pvesh_command('create', api_path)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)


async def main_replications(args):
    if args.command == 'replications':
        replications = get_high_fidelity_cluster_replications(args)
        replications_command(args, replications)
    elif args.command == 'replication-schedule-now':
        await run_on_resources(args, replications, replication_schedule_now)
    else:
        print(f"Command missing implementation: {args.command}")


async def main_vms(args):
    resources = get_cluster_resources(args)

    if not resources:
        print("No resources found")
        return

    if args.command == 'status':
        print_resource_status(args, resources)
    elif args.command in ['start', 'stop', 'shutdown', 'reboot', 'resume', 'suspend']:
        await run_on_resources(args, resources, perform_command)
    elif args.command == 'destroy':
        if not args.skip_confirm:
            print("Are you sure you want to destroy the following resources?")
            for idx, resource in enumerate(resources):
                print(f"{idx + 1}. {resource['id']}: {resource['name']}")
            print("\n")

            confirm = input("Enter 'y' to confirm: ").lower()
            if not (confirm == 'y' or confirm == "yes"):
                print("Cancelled destroying resources")
                return

        await run_on_resources(args, resources, destroy_command)
    elif args.command == 'snapshot':
        if not args.name:
            print("--name argument is required")
            return

        await run_on_resources(args, resources, snapshot_command)
    elif args.command == 'delsnapshot':
        if not args.name:
            print("--name argument is required")
            return

        await run_on_resources(args, resources, delsnapshot_command)
    elif args.command == 'listsnapshot':
        await run_on_resources(args, resources, listsnapshot_command)
    elif args.command == 'vzdump':
        await run_on_resources(args, resources, vzdump_command)
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
        ],
        default="status",
        help='Action to perform.'
    )
    parser.add_argument('ids', nargs='*', help='VM/Container IDs.')
    args = parser.parse_args()

    if args.command == "replication-schedule-now" or \
            args.command == "replications":
        await main_replications(args)
    else:
        await main_vms(args)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
        sys.exit(1)
