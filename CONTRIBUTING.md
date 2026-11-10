# Checking changes

This repository documents a personal lab. Live state and examples have different purposes: project pages describe dated observations, while the Kuma manifest and offline fixtures are explicitly labeled examples. No check in this repository deploys anything.

Use Python 3.12 or newer for development tooling. The two standalone audit tools support Python 3.11 or newer.

```sh
python -m venv .venv
# Activate the environment using your shell's normal command.
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python tools/check_repository.py
```

The tests cover missing and stale backups, unrecognized input, future timestamps, inconsistent guest identity, stale network assumptions, GPU role mismatches, and insufficient or invalid memory readings. The repository check validates relative links, YAML relationships, prose rules, common credential patterns, private IPv4 addresses, and image metadata. It is a guardrail, not a complete secret detector.

Validate the Kubernetes objects with [kubeconform](https://github.com/yannh/kubeconform):

```sh
kubeconform -strict -summary -kubernetes-version 1.36.0 kubernetes/uptime-kuma/kuma.yaml
```

Schema validation checks API shape. It cannot prove that the image starts, the storage provisioner works, or the proposed resource budget is adequate. The example has not been deployed.

Before publishing changes, run [Gitleaks](https://github.com/gitleaks/gitleaks) against both the files and Git history, then inspect the staged diff and each image. Pattern checks cannot recognize a family photograph, private document, or identifying screen content. Re-export photo derivatives without EXIF, GPS, XMP, embedded thumbnails, or comments. Keep raw inventories, credentials, and original photos outside this repository.

```sh
gitleaks dir . --redact
gitleaks git . --redact
git diff --cached --check
git diff --cached
```

The history scan requires an initialized repository with commits. CI runs the offline Python, document, and configuration checks; it has no lab credentials. Publication review and deployment approval remain separate from those checks.
