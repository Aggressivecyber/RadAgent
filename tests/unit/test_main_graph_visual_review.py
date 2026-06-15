from __future__ import annotations

from typing import Any

import pytest
from agent_core.graph import main_graph


@pytest.mark.asyncio
async def test_gate_subgraph_does_not_forward_retired_visual_review_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCompiledGraph:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured.update(payload)
            return {
                "gate_results_path": "/tmp/gates.json",
                "validation_status": "passed",
                "failed_gates": [],
                "skipped_gates": [],
            }

    class FakeGraphBuilder:
        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph()

    monkeypatch.setattr(
        "agent_core.gates.build_gate_validation_subgraph",
        lambda: FakeGraphBuilder(),
    )

    node = main_graph._make_gate_subgraph_node()
    result = await node(
        {
            "job_id": "job_visual",
            "execution_mode": "strict",
            "run_mode": "test",
            "visual_review_status": "approved",
            "visual_review_notes": "geometry inspected",
            "visual_review_blocking": True,
        }
    )

    assert captured["run_mode"] == "test"
    assert "visual_review_status" not in captured
    assert "visual_review_notes" not in captured
    assert "visual_review_blocking" not in captured
    assert result["validation_status"] == "passed"
