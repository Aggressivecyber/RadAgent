from __future__ import annotations

import pytest
from agent_core.gates.gate_runner import compute_validation_status, normalize_run_mode


def test_dev_run_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported run_mode"):
        normalize_run_mode("dev")


def test_compute_validation_status_never_returns_partial() -> None:
    status = compute_validation_status([{"gate_id": 1, "status": "pass"}], "strict")

    assert status == "passed"
    assert status not in {"partial", "PARTIAL", "dev_pass", "skipped_pass"}
