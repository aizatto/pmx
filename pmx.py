#!/usr/bin/python3

import subprocess
import sys
import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading

def run_pvesh_command(command):
    """Run a pvesh command and return the output."""
    try:
        result = subprocess.run(['pvesh'] + command + ['--output-format', 'json'],
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running pvesh command: {e}")
        print(f"stderr: {e.stderr}")
        raise

def cache_resources():
    """Cache resources information from /cluster/resources."""
    resources = run_pvesh_command(['get', '/cluster/resources'])
    resource_cache = {}
    for resource in resources:
        resource_id = resource['id'].split('/', 1)[1]
        resource_type = resource['type']
        node = resource['node']
        status = resource['status']
        
        if resource_type in ['qemu', 'lxc']:
            resource_cache[resource_id] = {
                'type': resource_type,
                'name': resource['name'],
                'node': node,
                'status': status,
                'uptime': resource.get('uptime', 0)  # Default to 0 if not available
            }
    return resource_cache

def perform_action(node, resource_id, resource_type, action):
    """Perform the specified action (start, stop, shutdown) on the resource."""
    try:
        if resource_type == 'qemu':
            run_pvesh_command(['create', f'/nodes/{node}/qemu/{resource_id}/status/{action}'])
        elif resource_type == 'lxc':
            run_pvesh_command(['create', f'/nodes/{node}/lxc/{resource_id}/status/{action}'])
    except Exception as e:
        print(f"Error performing action on {resource_type}/{resource_id}: {e}")
        raise

def format_uptime(seconds):
    """Convert uptime in seconds to a human-friendly format."""
    return str(timedelta(seconds=int(seconds)))

def validate_action(resource_id, resource_status, action):
    """Validate if the action can be performed based on the current status."""
    if resource_status == 'stopped' and action != 'start':
        return False, f"Resource ID {resource_id}: Machine is already stopped."
    if resource_status == 'running' and action in ['start']:
        return False, f"Resource ID {resource_id}: Machine is already started."
    return True, ""

def animate_progress(stop_event):
    """Print an animation to indicate ongoing asynchronous tasks."""
    chars = ['.', '..', '...']
    while not stop_event.is_set():
        for char in chars:
            if stop_event.is_set():
                break
            sys.stdout.write(f'\r{char}')
            sys.stdout.flush()
            time.sleep(0.5)
    sys.stdout.write('\rDone!        \n')

def main():
    if len(sys.argv) < 2:
        print("Usage: pmx.py <command> <ID1> [<ID2> ...] [--sync]")
        sys.exit(1)

    command = sys.argv[1]
    if command not in ['start', 'stop', 'shutdown', 'status']:
        print("Supported commands are 'start', 'stop', 'shutdown', and 'status'.")
        sys.exit(1)

    sync_mode = '--sync' in sys.argv
    ids = [arg for arg in sys.argv[2:] if arg != '--sync']

    if not ids:
        print("Usage: pmx.py <command> <ID1> [<ID2> ...] [--sync]")
        sys.exit(1)

    # Cache resources
    try:
        resource_cache = cache_resources()
    except Exception as e:
        print(f"Failed to cache resources: {e}")
        sys.exit(1)

    stop_event = threading.Event()
    progress_thread = threading.Thread(target=animate_progress, args=(stop_event,))
    progress_thread.start()

    try:
        with ThreadPoolExecutor() as executor:
            futures = []

            if command == 'status':
                for resource_id in ids:
                    if resource_id in resource_cache:
                        status_info = resource_cache[resource_id]
                        name = status_info['name']
                        uptime = status_info['uptime']
                        status_output = f"{status_info['type']}/{resource_id}: {name} {status_info['status']}"
                        if status_info['status'] == 'running':
                            status_output += f" {format_uptime(uptime)}"
                        print(status_output)
                    else:
                        print(f"Resource with ID {resource_id} not found or invalid.")
                        sys.exit(1)  # Exit if any resource ID is not found

            else:
                for resource_id in ids:
                    if resource_id in resource_cache:
                        status_info = resource_cache[resource_id]
                        resource_type = status_info['type']
                        node = status_info['node']
                        status = status_info['status']

                        valid, message = validate_action(resource_id, status, command)
                        if not valid:
                            print(message)
                            continue

                        future = executor.submit(perform_action, node, resource_id, resource_type, command)
                        futures.append(future)
                    else:
                        print(f"Resource with ID {resource_id} not found or invalid.")
                        sys.exit(1)  # Exit if any resource ID is not found

                if sync_mode:
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"Error performing action: {e}")
                            sys.exit(1)
                else:
                    print("Actions are running asynchronously. Check individual results for errors.")
                    for future in futures:
                        try:
                            future.result()
                        except Exception as e:
                            print(f"Error performing action: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        stop_event.set()
        progress_thread.join()
        sys.exit(1)

    finally:
        # Stop the progress animation and wait for the thread to finish
        stop_event.set()
        progress_thread.join()

if __name__ == "__main__":
    main()

