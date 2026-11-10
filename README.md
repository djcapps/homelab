# Homelab

A small rack, two GPU workstations, and a fairly persistent list of things to fix. I use this lab to work on networking, Linux, virtualization, Kubernetes, automation, and local AI infrastructure. It also runs services I use at home, including photo storage and monitoring.

![My desk, mini rack, and two GPU workstations](images/desk-area.jpg)

*The lab on November 10, 2026. This photo has light AI-assisted retouching and privacy redactions; [photo notes](images/README.md) describe the edits. The [rack close-up](projects/proxmox.md) uses an original photograph.*

## The lab

Three Lenovo Tiny systems run Proxmox. A fourth runs Fedora for file storage, backups, and administration. The GPU workstations handle inference separately from the services in the rack. This inventory was checked on November 10, 2026.

| System | CPU | RAM | Role |
| --- | --- | --- | --- |
| ThinkCentre M90q Gen 5 | Core i9-14900 | 32 GB | Proxmox |
| ThinkCentre M90q Gen 3 | Core i9-12900T | 32 GB | Proxmox |
| ThinkStation P330 Tiny | Core i7-9700T | 24 GB | Proxmox |
| ThinkCentre M920q | Core i5-8500T | 32 GB | Fedora NAS and backup host |
| GPU workstation | Ryzen 9 9950X | 64 GB | RTX 5090, 32 GB VRAM |
| GPU workstation | Ryzen 7 7800X3D | 32 GB | RTX 4090, 24 GB VRAM |

The Proxmox hosts use local ZFS storage. The NAS has an 8 TB data disk and a separate 4 TB backup disk. Neither arrangement provides local disk redundancy. Managed Ethernet connects the lab; the Proxmox links currently run at 1 Gbps.

## Architecture

```mermaid
flowchart TB
    router[Home router] --- lan[Managed Ethernet switches]
    lan --- pve[Three Proxmox hosts]
    lan --- nas[Fedora NAS and backup host]
    lan --- gpu[RTX 5090 and RTX 4090 workstations]
    pve --> talos[Three Talos control-plane VMs]
    pve --> services[Monitoring, DNS, Immich and other guests]
    talos --> apps[Uptime Kuma and AWX]
    apps --> local[Local volumes on one Talos VM]
    services -->|Immich originals| nas
    pve -->|Guest backups| nas
    gpu --> inference[Manual llama.cpp CUDA and RPC workloads]
```

This is a logical dependency diagram, not a cable or VLAN map. The Talos VMs also run application workloads. Their local volumes and the NAS remain important failure points; three control-plane nodes do not make every application highly available.

## Projects

**[Talos and Kubernetes](projects/talos.md).** Three control-plane VMs run Talos 1.13.8 and Kubernetes 1.36.2. The notes cover Flannel, local-path storage, AWX, and what happens when the VM holding an application's data is unavailable.

**[Uptime Kuma](kubernetes/uptime-kuma/README.md).** A single-replica deployment monitors services, while a separate collector reports its status to the home dashboard. The example manifest and [monitoring notes](projects/monitoring.md) explain why an empty or stale response must not look healthy.

**[Proxmox and recovery](projects/proxmox.md).** Five guests are managed by Proxmox HA with asynchronous ZFS replication. Backups are a separate concern. The runbook follows a guest from host failure through storage checks and application verification, with a [backup freshness checker](automation/README.md#backup-freshness).

**[Local GPU inference](projects/gpu-inference.md).** Native Windows llama.cpp uses CUDA locally and an RPC worker on the other workstation. Saved tests show actual inference with an 80B model across both GPUs. The services start manually. The current review found an address mismatch in the launch configuration, which needs revalidation before the next run.

## What I'm working on

The next useful work is fairly practical: test a full restore of Kuma and the photo library, add resource metrics and probes to Kubernetes, and validate the inference launcher's network assumptions after address changes. A GitOps rollout can follow once storage and recovery behavior are documented. These are proposed improvements, not completed deployments.

The [automation directory](automation/README.md) contains offline checks and examples. [Validation instructions](CONTRIBUTING.md) cover the code, manifests, links, and publication checks. Examples use substitute identifiers; credentials and the private network map stay outside this repository.
