# Small operational checks

These tools grew out of two checks in the lab: whether each expected guest has a recent backup, and whether a saved inference configuration still matches the machines that will run it. They read exported state and return JSON. Neither changes infrastructure.

The Python tools need Python 3.11 or newer and use only the standard library. The files in `examples/` are **synthetic fixtures**, with substitute guest IDs, documentation-only addresses, and invented sample free-memory values. They are not operational results.

## Backup freshness

On a Proxmox host with existing access to the intended PBS storage, save:

```sh
pvesm list YOUR_PBS_STORAGE --content backup > pbs-listing.txt
```

Keep the real export outside this repository. Copy `examples/backup-policy.json` to a private location and list every expected guest, including stopped guests that still need protection. Give each exclusion a reason. Then run:

```sh
python automation/backup_audit.py --listing /private/pbs-listing.txt --policy /private/backup-policy.json
```

The parser expects the standard `pvesm list` text header and PBS `backup/vm` or `backup/ct` rows. It rejects unrecognized rows rather than silently dropping coverage. Missing, stale, future-dated, and untracked guests fail the audit. A new guest still needs to be added to the expected policy; this tool cannot discover a guest that has never appeared in its input.

The age threshold includes time between scheduled jobs. The example uses 30 hours for a daily schedule; choose your own tolerance. A snapshot's presence is not a verification job, checksum check, or restore test. The output always includes `restore_verified: false`.

Offline example, using a fixed clock so it stays reproducible:

```sh
python automation/backup_audit.py --listing automation/examples/pbs-listing.txt --policy automation/examples/backup-policy.json --now 2026-01-02T12:00:00Z
```

## Inference preflight

The Windows collector uses `nvidia-smi`, `Find-NetRoute`, file metadata, and the worker's existing SSH login. It requires exactly one NVIDIA GPU per host, which matches this setup. It does not contact the RPC port: opening another client can interfere with a single-client worker.

```powershell
.\automation\Export-InferenceInventory.ps1 `
  -WorkerSsh 'YOUR_USER@YOUR_WORKER' `
  -WorkerAddress '192.0.2.20' `
  -ModelPath 'D:\models\your-model.gguf' |
  Set-Content -Encoding utf8 C:\private\inference-inventory.json
```

Replace the documentation address with your worker's actual address. Prepare a private plan from `examples/inference-plan.json`, then compare it to the fresh export:

```sh
python automation/inference_preflight.py --plan /private/inference-plan.json --inventory /private/inference-inventory.json
```

It checks inventory age, coordinator address, route destination/source/interface, GPU names by role, model byte count, and a free-VRAM budget. Model budgets in the example come from the recorded 8,192-token profile's model buffers, rounded up; the 2 GiB reserve is an example allowance, not a measured requirement. Account for KV cache, context size, runtime buffers, and other GPU applications when setting your own budget. Passing this arithmetic check does not establish that a model will fit.

A file size check is a quick guard, not integrity verification. Verify the publisher's model hash separately. This tool also cannot establish current firewall scope, RPC authentication, GPU ordering inside a new runtime, or successful inference.

Offline example:

```sh
python automation/inference_preflight.py --plan automation/examples/inference-plan.json --inventory automation/examples/inference-inventory.json --now 2026-01-02T12:01:00Z
```

Both Python commands return `0` when their checks pass, `1` for an operational finding, and `2` for invalid or unreadable input. A stale export is a finding, not a healthy result. Never publish real exports without a separate privacy review.
