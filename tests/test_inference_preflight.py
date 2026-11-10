import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from automation.inference_preflight import audit, main

EXAMPLES = Path(__file__).parents[1] / "automation/examples"
NOW = datetime(2026, 1, 2, 12, 1, tzinfo=timezone.utc)


@pytest.fixture
def inputs():
    return [
        json.loads(EXAMPLES.joinpath(name).read_text())
        for name in ["inference-plan.json", "inference-inventory.json"]
    ]


def test_matching_plan_does_not_claim_inference(inputs):
    result = audit(*inputs, NOW)
    assert result["ok"]
    assert not result["inference_tested"]
    assert not result["rpc_contacted"]
    assert not result["model_hash_verified"]


def test_changed_coordinator_address_and_route(inputs):
    plan, inventory = inputs
    inventory["coordinator_addresses"] = ["192.0.2.11"]
    inventory["route"]["source"] = "192.0.2.11"
    result = audit(plan, inventory, NOW)
    assert not result["ok"]
    assert {r["code"] for r in result["findings"]} == {
        "COORDINATOR_ADDRESS_MISMATCH",
        "ROUTE_SOURCE_MISMATCH",
    }


def test_overlay_route_is_detected(inputs):
    inputs[1]["route"]["interface"] = "VPN"
    assert audit(*inputs, NOW)["findings"][0]["code"] == "ROUTE_INTERFACE_MISMATCH"


def test_low_memory_does_not_pass(inputs):
    inputs[1]["devices"][1]["free_mib"] = 20000
    result = audit(*inputs, NOW)
    assert not result["ok"]
    assert result["findings"][0]["code"] == "INSUFFICIENT_FREE_VRAM"


def test_model_size_mismatch(inputs):
    inputs[1]["model_bytes"] = 1000
    assert audit(*inputs, NOW)["findings"][0]["code"] == "MODEL_SIZE_MISMATCH"


@pytest.mark.parametrize("stamp", ["2025-01-01T00:00:00Z", "2027-01-01T00:00:00Z"])
def test_stale_and_future_inventory_fail(inputs, stamp):
    inputs[1]["collected_at"] = stamp
    assert audit(*inputs, NOW)["findings"][0]["code"] == "INVENTORY_NOT_CURRENT"


def test_gpu_roles_cannot_be_duplicated(inputs):
    inputs[1]["devices"][1]["role"] = "coordinator"
    with pytest.raises(ValueError):
        audit(*inputs, NOW)


def test_swapped_gpus_are_not_accepted(inputs):
    inputs[1]["devices"][0]["name"] = "NVIDIA GeForce RTX 4090"
    assert audit(*inputs, NOW)["findings"][0]["code"] == "GPU_NAME_MISMATCH"


@pytest.mark.parametrize("free", [float("nan"), float("inf"), -1, True, "24000"])
def test_unknown_memory_cannot_pass(inputs, free):
    inputs[1]["devices"][0]["free_mib"] = free
    with pytest.raises(ValueError):
        audit(*inputs, NOW)


def test_no_timezone_rejected(inputs):
    inputs[1]["collected_at"] = "2026-01-02T12:00:00"
    with pytest.raises(ValueError):
        audit(*inputs, NOW)


def test_cli_bad_json_returns_input_error(tmp_path, capsys):
    bad = tmp_path / "invalid.json"
    bad.write_text("{broken}")
    assert main(["--plan", str(bad), "--inventory", str(bad)]) == 2
    assert "invalid or unreadable" in capsys.readouterr().err
