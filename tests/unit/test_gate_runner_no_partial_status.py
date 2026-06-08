from __future__ import annotations

import pytest
from agent_core.gates.gate_runner import compute_validation_status


@pytest.mark.parametrize(
    ("gates", "expected"),
    [
        ([{"gate_id": 1, "status": "pass"}], "passed"),
        ([{"gate_id": 1, "status": "fail"}], "failed"),
        ([{"gate_id": 1, "status": "blocked"}], "blocked"),
    ],
)
def test_validation_status_values_are_canonical(
    gates: list[dict[str, object]], expected: str
) -> None:
    assert compute_validation_status(gates, "production") == expected
