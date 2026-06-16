"""Main graph should preserve codegen continuation control fields."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_main_codegen_node_passes_repair_continuation_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_core.graph import main_graph

    seen: dict[str, Any] = {}

    class FakeCompiledSubgraph:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            seen.update(payload)
            return {
                "g4_codegen_status": "passed",
                "proposed_patch_path": "/tmp/proposed_patch.json",
                "generated_code_dir": "/tmp/geant4_project",
                "repair_continuation_status": "",
                "current_node": "geant4_project_agent",
            }

    class FakeGraph:
        def compile(self) -> FakeCompiledSubgraph:
            return FakeCompiledSubgraph()

    monkeypatch.setattr(
        "agent_core.graph.subgraphs.g4_codegen_graph.build_g4_codegen_subgraph",
        lambda: FakeGraph(),
    )
    monkeypatch.setattr(main_graph, "_load_runtime_failure_context", lambda _state: {})

    node = main_graph._make_g4_codegen_subgraph_node()
    await node(
        {
            "job_id": "job-continue",
            "g4_model_ir_path": "/tmp/missing-ir.json",
            "repair_continuation_status": "approved",
            "agentic_repair_max_turns_override": 60,
        }
    )

    assert seen["repair_continuation_status"] == "approved"
    assert seen["agentic_repair_max_turns_override"] == 60


@pytest.mark.asyncio
async def test_main_codegen_node_preserves_subgraph_current_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_core.graph import main_graph

    class FakeCompiledSubgraph:
        async def ainvoke(self, _payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "g4_codegen_status": "failed",
                "proposed_patch_path": "/tmp/proposed_patch.json",
                "generated_code_dir": "/tmp/project_agent/geant4_project",
                "repair_continuation_status": "",
                "current_node": "runtime_execution_audit",
            }

    class FakeGraph:
        def compile(self) -> FakeCompiledSubgraph:
            return FakeCompiledSubgraph()

    monkeypatch.setattr(
        "agent_core.graph.subgraphs.g4_codegen_graph.build_g4_codegen_subgraph",
        lambda: FakeGraph(),
    )
    monkeypatch.setattr(main_graph, "_load_runtime_failure_context", lambda _state: {})

    node = main_graph._make_g4_codegen_subgraph_node()
    result = await node({"job_id": "job-node"})

    assert result["current_node"] == "runtime_execution_audit"
