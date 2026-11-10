import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from automation.backup_audit import audit, main, parse_listing, utc_time

EXAMPLES = Path(__file__).parents[1] / "automation/examples"
NOW = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)


@pytest.fixture
def inputs():
    return (
        EXAMPLES.joinpath("pbs-listing.txt").read_text(),
        json.loads(EXAMPLES.joinpath("backup-policy.json").read_text()),
    )


def test_latest_snapshot_and_restore_boundary(inputs):
    listing, policy = inputs
    result = audit(listing, policy, NOW)
    assert result["ok"]
    assert result["restore_verified"] is False
    assert {r["guest"]: r["age_hours"] for r in result["guests"]}["vm/201"] == 8


def test_header_only_is_missing_coverage(inputs):
    result = audit("Volid Format Type Size VMID\n", inputs[1], NOW)
    assert not result["ok"]
    assert {r["state"] for r in result["guests"]} == {"missing"}


def test_stale_snapshot_fails(inputs):
    listing, policy = inputs
    policy["max_age_hours"] = 7
    assert {r["state"] for r in audit(listing, policy, NOW)["guests"]} == {"stale"}


def test_future_snapshot_fails(inputs):
    listing, policy = inputs
    result = audit(listing.replace("2026-01-02", "2026-01-03"), policy, NOW)
    assert not result["ok"]
    assert {r["state"] for r in result["guests"]} == {"future_timestamp"}


def test_unknown_group_requires_policy_decision(inputs):
    listing, policy = inputs
    listing += "example:backup/ct/302/2026-01-02T04:00:00Z pbs-ct backup 12 302\n"
    result = audit(listing, policy, NOW)
    assert not result["ok"]
    assert next(r for r in result["guests"] if r["guest"] == "ct/302")["state"] == "untracked"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "HTTP 401",
        "Volid Format Type Size VMID\ntruncated",
        "Volid Format Type Size VMID\nx:backup/vm/201/2026-01-02T04:00:00Z pbs-vm backup 1 202",
    ],
)
def test_invalid_input_never_becomes_healthy(text):
    with pytest.raises(ValueError):
        parse_listing(text)


@pytest.mark.parametrize("age", [0, -1, float("nan"), float("inf"), True])
def test_invalid_age_policy(inputs, age):
    listing, policy = inputs
    policy["max_age_hours"] = age
    with pytest.raises(ValueError):
        audit(listing, policy, NOW)


def test_conflicting_exclusion_rejected(inputs):
    listing, policy = inputs
    policy["excluded"].append({"kind": "vm", "id": 201, "reason": "conflict"})
    with pytest.raises(ValueError):
        audit(listing, policy, NOW)


def test_naive_time_rejected():
    with pytest.raises(ValueError):
        utc_time("2026-01-02T12:00:00")


def test_cli_bad_file_returns_input_error(tmp_path, capsys):
    assert main(["--listing", str(tmp_path / "absent"), "--policy", str(tmp_path / "absent")]) == 2
    assert "invalid or unreadable" in capsys.readouterr().err
