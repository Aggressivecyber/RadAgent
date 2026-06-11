from __future__ import annotations

from typing import Any

import pytest
from agent_core.graph import main_graph


@pytest.mark.asyncio
async def test_gate_subgraph_receives_visual_review_state(
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
            "visual_review_status": "approved",
            "visual_review_notes": "geometry inspected",
            "visual_review_blocking": True,
        }
    )

    assert captured["visual_review_status"] == "approved"
    assert captured["visual_review_notes"] == "geometry inspected"
    assert captured["visual_review_blocking"] is True
    assert result["validation_status"] == "passed"
