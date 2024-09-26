#!/usr/bin/python3

import argparse
import asyncio
import json
import subprocess
import sys
import time
import threading

def run_pvesh_command(pvesh_command, api_path, options = []):
    """Run pvesh command and return JSON output."""
    try:
        result = subprocess.run(
            ['pvesh', pvesh_command] + api_path.split() + options + ['--output-format', 'json'],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if pvesh_command != "delete":
            return json.loads(result.stdout)
        return ""
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh command on {api_path}: {e.stderr}", file=sys.stderr)

def get_cluster_resources(args):
    """Fetch and cache resources from Proxmox."""
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

    elif args.command == "status":
        cluster_resources = run_pvesh_command('get', '/cluster/resources')
        for resource in cluster_resources:
            if resource['type'] in ['lxc', 'qemu']:
                resources.append(resource)

    return resources

def humanize_seconds(seconds):
    """Convert seconds to a human-readable format."""
    minutes, seconds = divmod(seconds, 60)
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
        print(f"VM {vmid} is already running. Only 'stop' or 'shutdown' are allowed.")
        return False
    return True

def perform_action(args, resource):
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
        print(f"{action.capitalize()} command sent for {resource['type']}/{vmid}.")
        run_pvesh_command('create', api_path)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh command: {e.stderr}", file=sys.stderr)

def destroy_resource(args, resource):
    """Destroy the specified resources."""
    purge = not args.do_not_purge_jobs
    destroy_unreferenced_disks = not args.do_not_destroy_unreferenced_disks
    
    vmid = resource['vmid']
    if not resource:
        print(f"Resource ID {vmid} not found.")
        return
    
    try:
        api_path = f"/nodes/{resource['node']}/{resource['type']}/{vmid}"
        options= []
        if purge:
            options.append("--purge")
        if destroy_unreferenced_disks:
            options.append("--destroy-unreferenced-disks")
        print(f"Destroying {resource['type']}/{vmid}.")
        run_pvesh_command('delete', api_path, options)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pvesh api_path: {e.stderr}", file=sys.stderr)

async def run_on_resources(args, resources, fn):
    if args.sync:
        for resource in resources:
            await fn(resource)
    else:
        tasks = []
        for resource in resources:
            tasks.append(fn(resource))
        await asyncio.gather(*tasks)

async def main():
    parser = argparse.ArgumentParser(description='Manage Proxmox VMs and containers.')
    parser.add_argument('--node', action='store_true', help='Treat ids as node names')
    parser.add_argument('--sync', action='store_true', help='Run commands synchronously.')
    parser.add_argument('--skip-confirm', action='store_true', help='On destroy, skip confirm.', default=False)
    parser.add_argument('--do-not-purge-jobs', action='store_true', help='On destroy, skip purging from job configurations.', default=False)
    parser.add_argument('--do-not-destroy-unreferenced-disks', action='store_true', help='On destroy, skip destroy unreferenced disks.', default=False)
    parser.add_argument('command', nargs='?', choices=['start', 'stop', 'shutdown', 'status', 'destroy'], default="status", help='Action to perform.')
    parser.add_argument('ids', nargs='*', help='VM/Container IDs.')
    args = parser.parse_args()

    resources = get_cluster_resources(args)

    if not resources:
        print("No resources found")
        return
    
    if args.command == 'status':
        print_resource_status(args, resources)
    elif args.command in ['start', 'stop', 'shutdown']:
        async def fn(resource):
            perform_action(args, resource)
        
        await run_on_resources(args, resources, fn)
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

        async def fn(resource):
            destroy_resource(args, resource)

        await run_on_resources(args, resources, fn)
    else:
        print("Supported commands are 'start', 'stop', 'shutdown', 'status', 'destroy'.")
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
        sys.exit(1)
