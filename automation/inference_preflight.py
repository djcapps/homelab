"""Compare an inference plan to a saved inventory without contacting either GPU."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def address(value: str) -> str:
    return str(ipaddress.ip_address(value))


def number(value: object, name: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return value


def devices_by_role(devices: list[dict]) -> dict[str, dict]:
    result = {device["role"]: device for device in devices}
    if len(devices) != 2 or set(result) != {"coordinator", "worker"}:
        raise ValueError("exactly one coordinator GPU and one worker GPU are required")
    for device in devices:
        if not isinstance(device.get("name"), str) or not device["name"].strip():
            raise ValueError("each GPU needs a name")
    return result


def audit(plan: dict, inventory: dict, now: datetime, max_age_minutes: float = 15) -> dict:
    if now.tzinfo is None or number(max_age_minutes, "max_age_minutes") == 0:
        raise ValueError("use an aware clock and a positive inventory age limit")
    stamp = datetime.fromisoformat(inventory["collected_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("inventory timestamp must include a timezone")
    age = (now - stamp).total_seconds()
    findings = []

    def check(condition: bool, code: str, detail: str) -> None:
        if not condition:
            findings.append({"code": code, "detail": detail})

    check(
        -60 <= age <= max_age_minutes * 60,
        "INVENTORY_NOT_CURRENT",
        "Collect a fresh inventory; stale or future samples cannot establish readiness.",
    )
    coordinator, worker = address(plan["coordinator_address"]), address(plan["worker_address"])
    if coordinator == worker:
        raise ValueError("coordinator and worker must be different addresses")
    if not isinstance(plan["interface"], str) or not plan["interface"].strip():
        raise ValueError("interface must be a nonempty string")
    present = [address(item) for item in inventory["coordinator_addresses"]]
    route = inventory["route"]
    check(
        coordinator in present,
        "COORDINATOR_ADDRESS_MISMATCH",
        "The configured coordinator address is absent from the current interfaces.",
    )
    check(
        address(route["destination"]) == worker,
        "ROUTE_DESTINATION_MISMATCH",
        "The recorded route must be for the intended worker.",
    )
    check(
        address(route["source"]) == coordinator,
        "ROUTE_SOURCE_MISMATCH",
        "The selected route uses a different source address than the plan.",
    )
    check(
        route["interface"] == plan["interface"],
        "ROUTE_INTERFACE_MISMATCH",
        "The selected route does not use the intended interface.",
    )
    expected_bytes = number(plan["model_bytes"], "model_bytes")
    if expected_bytes <= 0 or type(plan["model_bytes"]) is not int:
        raise ValueError("planned model_bytes must be a positive integer")
    actual_bytes = number(inventory["model_bytes"], "observed model_bytes")
    check(
        actual_bytes == expected_bytes,
        "MODEL_SIZE_MISMATCH",
        "The local model size differs from the plan; investigate before loading it.",
    )
    expected = devices_by_role(plan["devices"])
    actual = devices_by_role(inventory["devices"])
    for role in ("coordinator", "worker"):
        wanted, found = expected[role], actual[role]
        check(
            wanted["name"] == found["name"],
            "GPU_NAME_MISMATCH",
            f"{role}: the observed GPU name differs from the plan.",
        )
        required = number(wanted["model_budget_mib"], "model budget") + number(
            wanted["reserve_mib"], "reserve"
        )
        free = number(found["free_mib"], "free GPU memory")
        check(
            free >= required,
            "INSUFFICIENT_FREE_VRAM",
            f"{role}: {free:g} MiB free, {required:g} MiB budgeted including reserve.",
        )
    return {
        "checked_at": now.isoformat(),
        "ok": not findings,
        "findings": findings,
        "inference_tested": False,
        "rpc_contacted": False,
        "model_hash_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--now", help="timezone-aware timestamp for offline fixture checks")
    parser.add_argument("--max-age-minutes", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        now = (
            datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            if args.now
            else datetime.now(timezone.utc)
        )
        report = audit(
            json.loads(args.plan.read_text(encoding="utf-8-sig")),
            json.loads(args.inventory.read_text(encoding="utf-8-sig")),
            now,
            args.max_age_minutes,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        print(f"inference preflight: invalid or unreadable input ({error})", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
