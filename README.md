# Proxmox VM/LXC Manager

This script helps to start/stop/shutdown vms/lxc containers on multiple nodes without accessing the nodes.

This script was created with the help of ChatGPT, and even this README.md was written by ChatGPT. I'm not a Python expert, but the script should be helpful for anyone who wants a quick way to manage VMs or containers on a Proxmox environment.

## Features
- Start, stop, or shut down Proxmox VMs and containers by ID.
- Fetch the status of VMs/containers.
- Supports both synchronous and asynchronous execution.

## Requirements
- A Proxmox environment with `pvesh` command-line tool.
- Python 3.x installed.

## Installation

1. **Download the script to your Proxmox machine:**
   ```bash
   curl -O https://raw.githubusercontent.com/aizatto/pmx/main/pmx.py
   cd proxmox-manager
   ```

2. **Make the script executable:**
   ```bash
   chmod +x pmx.py
   ```

## Usage

The script takes a followed by one or more VM/Container IDs.

Example:

```bash
./pmx.py status 100
```

Available commands:

1. `status`
1. `start`
1. `shutdown`
1. `stop`
1. `reboot`
1. `suspend`
1. `destroy`
1. `snapshot`
1. `delsnapshot`
1. `listsnapshot`
1. `replication-schedule-now`
1. `vzdump`

### **Get the status** of all your containers
```bash
./pmy.py
```

### **Get the status** of one or more VMs/containers
```bash
./pmx.py status 101 102
```

```bash
lxc/101 running 1h 23m
qemu/102 stopped
```

### **Start** a VM or container
```bash
./pmx.py start 101 102 103
```

```
Starting VM 101...
Starting VM 102...
VM 103 is already running. Only 'stop' or 'shutdown' are allowed.
```

### **Stop** a VM or container
```bash
./pmx.py stop 101 102
```

```
Stopping VM 101...
VM 102 is already stopped. Only 'start' is allowed.
```

### **Shutdown** a VM or container
```bash
./pmx.py shutdown 101
```

### **Destroy** a VM or container
```bash
./pmx.py destroy 101
```

You will be asked to confirm if you want to destroy vm. You can skip confirmation by passing `--skip-confirm`.

By default, jobs will be purged, and unreferenced disks destroyed. You can use the arguments:

1. `--do-not-purge-jobs` to not purge from job configurations
1. `--do-not-destroy-unreferenced-disks` to not destroy unreferenced disks

### **Snapshot** a VM or container

```bash
./pmx.py snapshot --name snapshot-test --description "testing snapshots" 101
```

Arguments:

1. `--name` Required. snapshot name
1. `--description` Optional

### **Delete Snapshot** of a VM or container

```bash
./pmx.py delsnapshot --name snapshot-test 101
```

Arguments:

1. `--name` Required. snapshot name

### **List Snapshots** of  VM or container

```bash
./pmx.py delsnapshot --name snapshot-test 101
```

Arguments:

1. `--name` Required. snapshot name

### **Replicate** a VM or container

```bash
./pmx.py replication-schedule-now 101
```

### Global Arguments

### Run synchronously `--sync`

By default, commands are executed asynchronously. To run them synchronously, pass the `--sync` argument:

```bash
./pmx.py --sync start 101 
```

#### Targetting a Node `--node`

You can pass a `--node` argument if you want the selector to select pods based on a node.

For example, assuming the environment looks like:

1. node1
   1. lxc/100
   1. lxc/101
2. node2
   1. lxc/103

You can return the status of all vms on the Node via
```bash
./pmx.py --node status node1
```

This works with `start`, `shutdown`, `stop`, and `destroy`.

## Notes:
- If a VM/container is `stopped`, only the `start` command will be allowed.
- If a VM/container is `running`, only the `stop` or `shutdown` commands will be allowed.
- The script retrieves the node and type (`qemu` or `lxc`) automatically from the Proxmox cluster.

## Handling Keyboard Interrupts
The script supports graceful handling of `Ctrl+C`, so you can stop execution safely.

## Contributions
Feel free to contribute! Fork the repository and submit a pull request if you'd like to improve or fix anything.

## License
This project is licensed under the [MIT License](LICENSE).

## Docs

1. [Proxmox API Viewer](https://pve.proxmox.com/pve-docs/api-viewer/index.html)
1. [pvesh](https://pve.proxmox.com/pve-docs/pvesh.1.html)
1. [pct](https://pve.proxmox.com/pve-docs/pct.1.html)
1. [qm](https://pve.proxmox.com/pve-docs/qm.1.html)