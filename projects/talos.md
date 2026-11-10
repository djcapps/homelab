# Talos on Proxmox

Three virtual machines make up the cluster. Each has four vCPUs, 4 GiB RAM, and a 64 GiB disk. All three are control-plane nodes and also accept application workloads. The November 10, 2026 check found all nodes Ready on Talos 1.13.8 and Kubernetes 1.36.2, with three healthy etcd members.

Talos keeps the operating-system interface small: configuration and inspection go through its API rather than a collection of changes made over SSH. Proxmox gives me a separate place to inspect the guest's disk, memory, and host placement. Keeping those two layers distinct helps when a Kubernetes symptom starts below Kubernetes.

## What runs here

Flannel supplies pod networking, with kube-proxy handling Services. CoreDNS, the local-path provisioner, Uptime Kuma, and AWX are running. AWX has separate web and task deployments and a PostgreSQL StatefulSet. Its operator reconciles AWX; that does not make this a GitOps cluster.

There is no ingress controller in the observed deployment. Kuma is reached through a NodePort. No NetworkPolicy objects, Flux controllers, or Argo CD installation were found. The Kubernetes Metrics API is unavailable, so `kubectl top` cannot currently show node or pod usage. Prometheus runs elsewhere in the lab.

## The storage boundary

Kuma's 2 GiB volume and AWX PostgreSQL's 8 GiB volume both use local-path storage and are tied to the same Talos VM. Kuma's PV has a `Delete` reclaim policy; the PostgreSQL PV has `Retain`. Deleting either application's objects deserves a storage review first.

This is inexpensive and easy to inspect, but it constrains recovery. Kubernetes cannot move those local files to another node by rescheduling a pod. Proxmox replication can provide another copy of the **whole VM disk**, with the delay and failure modes of asynchronous replication. It does not turn local-path into replicated Kubernetes storage.

That distinction is the main lesson from this cluster. I need to check both the Kubernetes scheduler's view and the hypervisor's copy of the VM. A healthy API server alone does not establish that application data is available.

## Read-only triage

Run these from an administration machine with its existing kubeconfig and Talos credentials. Substitute the context and node you intend to inspect.

```sh
kubectl --context "$CONTEXT" get nodes -o wide
kubectl --context "$CONTEXT" get deployments,statefulsets,daemonsets -A
kubectl --context "$CONTEXT" get pods -A -o wide
kubectl --context "$CONTEXT" get pvc -A
kubectl --context "$CONTEXT" get pv
kubectl --context "$CONTEXT" get events -A --sort-by=.metadata.creationTimestamp
talosctl --nodes "$NODE" services
talosctl --nodes "$NODE" etcd status
```

For a pending application, inspect its PVC binding and PV node affinity before changing scheduling. For a failing control-plane node, check Talos services and etcd membership, then the VM's current Proxmox owner. HA can move guests, so a saved host address is not authoritative.

Old terminal pods can remain after a replacement. Check current controller readiness and the active pod's events before treating every historical `Failed` object as a present outage. Keep event and log output private; it can contain internal names and addresses.

## Next changes

Metrics Server, a tested backup/restore procedure for the local volumes, and resource requests and probes for Kuma would make this easier to operate. Each needs a small rollout and a rollback plan. Increasing replica counts alone would not solve the data placement problem.

See the [Kuma example](../kubernetes/uptime-kuma/README.md) and [hypervisor recovery notes](proxmox.md). The upstream [Talos documentation](https://docs.siderolabs.com/talos/v1.13/overview/what-is-talos) and [Kubernetes persistent volume documentation](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) cover the underlying interfaces and reclaim behavior.
