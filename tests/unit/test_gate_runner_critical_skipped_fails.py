from __future__ import annotations

from agent_core.gates.gate_runner import compute_validation_status


def test_critical_skipped_gate_fails() -> None:
    status = compute_validation_status(
        [
            {"gate_id": 1, "status": "pass"},
            {"gate_id": 6, "status": "skipped"},
        ],
        "test",
    )

    assert status == "failed"


def test_explicit_non_critical_skipped_gate_does_not_fail() -> None:
    status = compute_validation_status(
        [
            {"gate_id": 1, "status": "pass"},
            {"gate_id": 10, "status": "skipped", "critical": False},
        ],
        "acceptance",
    )

    assert status == "passed"
