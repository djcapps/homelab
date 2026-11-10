"""Audit a saved Proxmox PBS listing. No network calls or infrastructure writes."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROW = re.compile(
    r"[\w.-]+:backup/(?P<kind>vm|ct)/(?P<id>[1-9]\d*)/"
    r"(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+"
    r"pbs-(?P<format>vm|ct)\s+backup\s+\d+\s+(?P<vmid>[1-9]\d*)"
)


def utc_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def group(item: dict) -> str:
    if item.get("kind") not in {"vm", "ct"}:
        raise ValueError("guest kind must be vm or ct")
    if type(item.get("id")) is not int or item["id"] <= 0:
        raise ValueError("guest id must be a positive integer")
    return f"{item['kind']}/{item['id']}"


def parse_listing(text: str) -> dict[str, datetime]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0].split() != ["Volid", "Format", "Type", "Size", "VMID"]:
        raise ValueError("expected the header from pvesm list STORAGE --content backup")
    latest: dict[str, datetime] = {}
    for number, line in enumerate(lines[1:], 2):
        match = ROW.fullmatch(line)
        if not match:
            raise ValueError(f"unrecognized PBS listing row {number}; refusing partial coverage")
        fields = match.groupdict()
        if fields["kind"] != fields["format"] or fields["id"] != fields["vmid"]:
            raise ValueError(f"inconsistent guest identity in row {number}")
        key = f"{fields['kind']}/{fields['id']}"
        stamp = utc_time(fields["time"])
        latest[key] = max(stamp, latest.get(key, stamp))
    return latest


def audit(text: str, policy: dict, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("the comparison time must include a timezone")
    hours = policy.get("max_age_hours")
    if type(hours) not in {int, float} or not math.isfinite(hours) or hours <= 0:
        raise ValueError("max_age_hours must be finite and positive")
    expected_list = [group(item) for item in policy["guests"]]
    if not expected_list or len(expected_list) != len(set(expected_list)):
        raise ValueError("guests must be nonempty and unique")
    excluded_items = policy.get("excluded", [])
    exclusions = {group(item): item.get("reason", "") for item in excluded_items}
    if len(exclusions) != len(excluded_items) or any(
        not isinstance(reason, str) or not reason.strip() for reason in exclusions.values()
    ):
        raise ValueError("exclusions must be unique and have a reason")
    if set(expected_list) & exclusions.keys():
        raise ValueError("a guest cannot be both expected and excluded")
    latest = parse_listing(text)
    rows = []
    for key in sorted(set(expected_list) | (latest.keys() - exclusions.keys())):
        stamp = latest.get(key)
        age = (now - stamp).total_seconds() if stamp else None
        if key not in expected_list:
            state = "untracked"
        elif stamp is None:
            state = "missing"
        elif stamp > now + timedelta(minutes=5):
            state = "future_timestamp"
        elif age > hours * 3600:
            state = "stale"
        else:
            state = "recent"
        rows.append(
            {
                "guest": key,
                "state": state,
                "latest_snapshot": stamp.isoformat() if stamp else None,
                "age_hours": round(age / 3600, 2) if age is not None else None,
            }
        )
    return {
        "checked_at": now.isoformat(),
        "ok": all(row["state"] == "recent" for row in rows),
        "max_age_hours": hours,
        "guests": rows,
        "excluded": exclusions,
        "restore_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--now", help="timezone-aware timestamp for repeatable offline checks")
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.listing.read_text(encoding="utf-8-sig"),
            json.loads(args.policy.read_text(encoding="utf-8-sig")),
            utc_time(args.now) if args.now else datetime.now(timezone.utc),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        print(f"backup audit: invalid or unreadable input ({error})", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
