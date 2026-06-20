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
async def test_main_codegen_node_passes_existing_runtime_failure_context(
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
            "job_id": "job-patch-retry",
            "runtime_failure_context": {
                "source": "patch_review_retry",
                "errors": ["REJECT (red zone): include/main.cc"],
            },
        }
    )

    assert seen["runtime_failure_context"]["source"] == "patch_review_retry"
    assert "include/main.cc" in seen["runtime_failure_context"]["errors"][0]


@pytest.mark.asyncio
async def test_main_codegen_node_prefers_patch_retry_context_over_gate_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_core.graph import main_graph

    seen: dict[str, Any] = {}

    class FakeCompiledSubgraph:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            seen.update(payload)
            return {"g4_codegen_status": "passed"}

    class FakeGraph:
        def compile(self) -> FakeCompiledSubgraph:
            return FakeCompiledSubgraph()

    monkeypatch.setattr(
        "agent_core.graph.subgraphs.g4_codegen_graph.build_g4_codegen_subgraph",
        lambda: FakeGraph(),
    )
    monkeypatch.setattr(
        main_graph,
        "_load_runtime_failure_context",
        lambda _state: {"source": "gate_validation_retry", "errors": ["old gate"]},
    )

    node = main_graph._make_g4_codegen_subgraph_node()
    await node(
        {
            "job_id": "job-patch-retry",
            "runtime_failure_context": {
                "source": "patch_review_retry",
                "errors": ["REJECT (red zone): include/main.cc"],
            },
        }
    )

    assert seen["runtime_failure_context"]["source"] == "patch_review_retry"
    assert "include/main.cc" in seen["runtime_failure_context"]["errors"][0]


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


@pytest.mark.asyncio
async def test_main_patch_node_returns_repair_context_on_rejection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from agent_core.graph import main_graph

    review_path = tmp_path / "patch_review.json"
    review_path.write_text(
        '{"errors":["REJECT (red zone): include/main.cc"]}',
        encoding="utf-8",
    )

    class FakeCompiledSubgraph:
        async def ainvoke(self, _payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "patch_status": "rejected",
                "patch_review_path": str(review_path),
                "errors": ["Patch rejected due to review errors"],
            }

    class FakeGraph:
        def compile(self) -> FakeCompiledSubgraph:
            return FakeCompiledSubgraph()

    monkeypatch.setattr(
        "agent_core.patching.build_patch_subgraph",
        lambda: FakeGraph(),
    )

    node = main_graph._make_patch_subgraph_node()
    result = await node(
        {
            "job_id": "job-patch-repair",
            "patch_retry_count": 1,
            "runtime_failure_context": {"source": "previous"},
        }
    )

    assert result["patch_status"] == "rejected"
    assert result["patch_retry_count"] == 2
    assert result["runtime_failure_context"]["source"] == "patch_review_retry"
    assert result["runtime_failure_context"]["history"][0]["source"] == "previous"
    assert "include/main.cc" in result["runtime_failure_context"]["errors"][0]
