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

The script takes a command (`start`, `stop`, `shutdown`, or `status`) followed by one or more VM/Container IDs.

### Commands

By default, commands are executed asynchronously. To run them synchronously, pass the `--sync` argument:

```bash
./pmx.py start 101 --sync
```

#### **Start** a VM or container
```bash
./pmx.py start 101 102 103
```

```
Starting VM 101...
Starting VM 102...
Starting VM 103...
```

#### **Stop** a VM or container
```bash
./pmx.py stop 101 102
```

```
Stopping VM 101...
VM 102 is already stopped.
```

#### **Shutdown** a VM or container
```bash
./pmx.py shutdown 101
```

#### **Get the status** of one or more VMs/containers
```bash
./pmx.py status 101 102
```

```bash
lxc/101 running 1h 23m
qemu/102 stopped
```

### Notes:
- If a VM/container is `stopped`, only the `start` command will be allowed.
- If a VM/container is `running`, only the `stop` or `shutdown` commands will be allowed.
- The script retrieves the node and type (`qemu` or `lxc`) automatically from the Proxmox cluster.

### Handling Keyboard Interrupts
The script supports graceful handling of `Ctrl+C`, so you can stop execution safely.

## Contributions
Feel free to contribute! Fork the repository and submit a pull request if you'd like to improve or fix anything.

## License
This project is licensed under the [MIT License](LICENSE).