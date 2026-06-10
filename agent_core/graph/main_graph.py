"""Main orchestration graph for RadAgent.

The main graph is EXTREMELY SIMPLE — it only schedules subgraphs.
It never processes geometry details, C++ code, Gate specifics, or
artifact content directly. All domain logic lives in subgraphs.

Flow:
    initialize_request
      → intent_router
      → [chat] → END
      → prepare_workspace
        → context_subgraph
        → task_planning_subgraph
        → g4_modeling_subgraph
        → human_confirmation_subgraph
        → g4_codegen_subgraph
        → patch_subgraph
        → gate_subgraph
        → artifact_subgraph
        → report_subgraph
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from agent_core.gates.gate_runner import normalize_run_mode
from agent_core.graph.main_routes import (
    route_after_artifact,
    route_after_context,
    route_after_g4_codegen,
    route_after_g4_modeling,
    route_after_gates,
    route_after_human_confirmation,
    route_after_intent,
    route_after_patch,
    route_after_task_planning,
)
from agent_core.graph.main_state import RadAgentMainState
from agent_core.workspace.paths import (
    GEANT4_PROJECT_DIRNAME,
    STAGE_GATE_VALIDATION,
    STAGE_INPUT,
    STAGE_PATCH,
)

# ─── Initialize request node ─────────────────────────────────────────


async def initialize_request(state: RadAgentMainState) -> dict[str, Any]:
    """Initialize the request — pass through state to intent router."""
    return {
        "user_query": state.get("user_query", ""),
        "current_node": "initialize_request",
    }


# ─── Workspace preparation node ──────────────────────────────────────


async def prepare_workspace(state: RadAgentMainState) -> dict[str, Any]:
    """Create job directory structure and initialize state.

    Generates a job_id with a human-readable title suffix via dsv4lite
    when no explicit job_id is provided by the user.

    Sets workspace paths and persists execution_mode alongside run_mode for
    storage and UI status contracts.
    """
    from agent_core.naming import build_job_id
    from agent_core.storage import RadAgentStore
    from agent_core.workspace.manager import WorkspaceManager

    job_id = await build_job_id(
        state.get("job_id", ""),
        state.get("user_query", ""),
    )

    # Use WorkspaceManager to create job structure
    ws = WorkspaceManager()
    job = ws.create_job(job_id)

    # Write user query to request stage
    request_dir = job.stage_dir(STAGE_INPUT)
    (request_dir / "user_query.md").write_text(f"# User Query\n\n{state.get('user_query', '')}\n")

    # Determine execution_mode from run_mode (no dev mode)
    run_mode = normalize_run_mode(state.get("run_mode", "strict"))
    execution_mode_map = {
        "strict": "strict",
        "test": "test",
        "acceptance": "acceptance",
        "production": "production",
    }
    execution_mode = execution_mode_map.get(run_mode, "strict")
    store = RadAgentStore(workspace_root=ws.root)
    project = store.current_project()
    store.upsert_job(
        job_id=job_id,
        user_query=state.get("user_query", ""),
        project_id=str(project["id"]),
        status="running",
        current_phase="prepare_workspace",
        current_phase_idx=0,
        execution_mode=execution_mode,
        run_mode=run_mode,
        job_workspace=str(job.dir),
    )

    return {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "run_mode": run_mode,
        "execution_mode": execution_mode,
        "workspace_root": str(ws.root),
        "job_workspace": str(job.dir),
        "retry_count": 0,
        "max_retries_reached": False,
        "errors": [],
        "current_node": "prepare_workspace",
    }


# ─── Subgraph wrapper creators ───────────────────────────────────────
# Each subgraph is compiled independently and wrapped as a main-graph node.
# The wrapper reads paths from main state, invokes the subgraph, and
# writes subgraph output paths back to main state.


def _make_context_subgraph_node() -> Any:
    """Create the context subgraph node."""
    from agent_core.context import build_context_subgraph

    subgraph = build_context_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "user_query": state.get("user_query", ""),
                "required_sources": ["geant4"],
            }
        )
        return {
            "context_decision": result.get("context_decision", "block_no_context"),
            "context_report_path": result.get("context_report_path", ""),
            "evidence_map_path": result.get("evidence_map_path", ""),
            "current_node": "context_subgraph",
        }

    return _run


def _make_task_planning_subgraph_node() -> Any:
    """Create the task planning subgraph node."""
    from agent_core.planning import build_task_planning_subgraph

    subgraph = build_task_planning_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "user_query": state.get("user_query", ""),
                "context_report_path": state.get("context_report_path", ""),
                "evidence_map_path": state.get("evidence_map_path", ""),
            }
        )
        return {
            "task_spec_path": result.get("task_spec_path", ""),
            "simulation_scope": result.get("simulation_scope", ["geant4"]),
            "task_planning_status": result.get("task_planning_status", "failed"),
            "current_node": "task_planning_subgraph",
        }

    return _run


def _make_g4_modeling_subgraph_node() -> Any:
    """Create the G4 modeling subgraph node."""
    from agent_core.graph.subgraphs.g4_modeling_graph import build_g4_modeling_subgraph

    subgraph = build_g4_modeling_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "user_query": state.get("user_query", ""),
                "task_spec_path": state.get("task_spec_path", ""),
                "evidence_map_path": state.get("evidence_map_path", ""),
            }
        )
        return {
            "g4_model_ir_path": result.get("g4_model_ir_path", ""),
            "component_specs_dir": result.get("component_specs_dir", ""),
            "interfaces_path": result.get("interfaces_path", ""),
            "construction_ledger_path": result.get("construction_ledger_path", ""),
            "model_review_report_path": result.get("model_review_report_path", ""),
            "g4_modeling_status": result.get("g4_modeling_status", "failed"),
            "human_confirmation_required": result.get("human_confirmation_required", False),
            "current_node": "g4_modeling_subgraph",
        }

    return _run


def _make_human_confirmation_subgraph_node() -> Any:
    """Create the human confirmation subgraph node."""
    from agent_core.graph.subgraphs.human_confirmation_graph import (
        build_human_confirmation_subgraph,
    )

    subgraph = build_human_confirmation_subgraph()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "user_query": state.get("user_query", ""),
                "g4_model_ir_path": state.get("g4_model_ir_path", ""),
                "evidence_map_path": state.get("evidence_map_path", ""),
                "human_confirmation_round": state.get("human_confirmation_round", 1),
                "raw_human_response": state.get("raw_human_response", {}),
                "confirmation_request_path": state.get("confirmation_request_path", ""),
                "confirmation_response_path": state.get("confirmation_response_path", ""),
                "confirmation_record_path": state.get("confirmation_record_path", ""),
                "confirmed_model_plan_path": state.get("confirmed_model_plan_path", ""),
            }
        )
        return {
            "confirmation_status": result.get("confirmation_status", "failed"),
            "confirmation_request_path": result.get("confirmation_request_path", ""),
            "confirmation_response_path": result.get("confirmation_response_path", ""),
            "confirmation_record_path": result.get("confirmation_record_path", ""),
            "confirmed_model_plan_path": result.get("confirmed_model_plan_path", ""),
            "unconfirmed_assumptions_count": result.get("unconfirmed_assumptions_count", 0),
            "human_confirmation_required": result.get("requires_human_confirmation", False),
            "human_confirmation_round": state.get("human_confirmation_round", 1)
            + (1 if result.get("confirmation_status") == "pending" else 0),
            "confirmation_report_path": result.get("confirmation_report_path", ""),
            "human_confirmation_edited_fields": result.get("edited_fields", []),
            "current_node": "human_confirmation_subgraph",
        }

    return _run


def _make_g4_codegen_subgraph_node() -> Any:
    """Create the G4 codegen subgraph node."""
    from agent_core.graph.subgraphs.g4_codegen_graph import build_g4_codegen_subgraph

    subgraph = build_g4_codegen_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        runtime_failure_context = _load_runtime_failure_context(state)
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "g4_model_ir_path": state.get("g4_model_ir_path", ""),
                "component_specs_dir": state.get("component_specs_dir", ""),
                "construction_ledger_path": state.get("construction_ledger_path", ""),
                "run_mode": state.get("run_mode", "strict"),
                "execution_mode": state.get("execution_mode", ""),
                "confirmation_record_path": state.get("confirmation_record_path", ""),
                "confirmed_model_plan_path": state.get("confirmed_model_plan_path", ""),
                "human_confirmation_status": state.get("human_confirmation_status", ""),
                "runtime_failure_context": runtime_failure_context,
            }
        )
        return {
            "code_module_plan_path": result.get("code_module_plan_path", ""),
            "proposed_patch_path": result.get("proposed_patch_path", ""),
            "generated_code_dir": result.get("generated_code_dir", ""),
            "g4_codegen_status": result.get("g4_codegen_status", "failed"),
            "current_node": "g4_codegen_subgraph",
        }

    return _run


def _load_runtime_failure_context(state: RadAgentMainState) -> dict[str, Any]:
    """Collect real gate/build/smoke failures for a codegen retry."""
    gate_results_path = state.get("gate_results_path", "")
    if not gate_results_path or not Path(gate_results_path).is_file():
        return {}

    try:
        gate_results = json.loads(Path(gate_results_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    failed = [
        gate
        for gate in gate_results
        if isinstance(gate, dict) and gate.get("status") in {"fail", "block", "blocked"}
    ]
    if not failed:
        return {}

    job_workspace = state.get("job_workspace", "")
    artifact_paths = _collect_failure_artifact_paths(
        failed_gates=failed,
        gate_results_path=gate_results_path,
        job_workspace=job_workspace,
    )
    failure_bundle = _load_failure_bundle(job_workspace)

    return {
        "source": "gate_validation_retry",
        "retry_count": state.get("retry_count", 0),
        "gate_results_path": gate_results_path,
        "failed_gates": [
            {
                "gate_id": gate.get("gate_id"),
                "name": gate.get("name"),
                "status": gate.get("status"),
                "message": gate.get("message", ""),
                "failed_items": gate.get("failed_items", []),
                "warnings": gate.get("warnings", []),
            }
            for gate in failed
        ],
        "build_errors": _collect_gate_messages(failed, gate_ids={6}),
        "runtime_errors": _collect_gate_messages(failed, gate_ids={9, 11}),
        "artifact_errors": _collect_gate_messages(failed, gate_ids={7, 8}),
        "failure_bundle": failure_bundle,
        "artifacts": _read_failure_artifact_tails(artifact_paths),
    }


def _collect_failure_artifact_paths(
    *,
    failed_gates: list[dict[str, Any]],
    gate_results_path: str,
    job_workspace: str,
) -> list[str]:
    """Collect text/JSON artifacts that explain gate/build/runtime failures."""
    artifact_paths: list[str] = [gate_results_path]
    for gate in failed_gates:
        for raw_path in gate.get("file_paths", []) or []:
            if isinstance(raw_path, str) and _is_failure_artifact_path(raw_path):
                artifact_paths.append(raw_path)

    if job_workspace:
        job_dir = Path(job_workspace)
        output_dir = job_dir / STAGE_GATE_VALIDATION / "g4_output_package"
        for name in (
            "cmake_configure_result.json",
            "build_result.json",
            "unit_test_result.json",
            "smoke_simulation_result.json",
            "g4_summary.json",
            "event_table.csv",
            "edep_3d.csv",
            "dose_3d.csv",
            "provenance.json",
        ):
            artifact_paths.append(str(output_dir / name))
        for path in (
            job_dir / "logs" / "failure_bundle.json",
            job_dir / "logs" / "events.jsonl",
            job_dir / "logs" / "trace.json",
            job_dir
            / STAGE_PATCH
            / GEANT4_PROJECT_DIRNAME
            / "build"
            / "CMakeFiles"
            / "CMakeConfigureLog.yaml",
        ):
            artifact_paths.append(str(path))

    return artifact_paths


def _is_failure_artifact_path(raw_path: str) -> bool:
    path = Path(raw_path)
    if path.suffix.lower() in {".json", ".jsonl", ".log", ".txt", ".csv", ".yaml", ".yml"}:
        return True
    return path.name in {"stdout", "stderr"}


def _load_failure_bundle(job_workspace: str) -> dict[str, Any]:
    if not job_workspace:
        return {}
    path = Path(job_workspace) / "logs" / "failure_bundle.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "path": str(path),
        "status": data.get("status"),
        "phase": data.get("phase"),
        "errors": data.get("errors", [])[:12],
        "warnings": data.get("warnings", [])[:12],
        "failed_gates": data.get("details", {}).get("failed_gates", [])[:12],
    }


def _collect_gate_messages(
    gates: list[dict[str, Any]],
    *,
    gate_ids: set[int],
) -> list[str]:
    messages: list[str] = []
    for gate in gates:
        if gate.get("gate_id") not in gate_ids:
            continue
        message = str(gate.get("message", "")).strip()
        if message:
            messages.append(message)
        messages.extend(str(item) for item in gate.get("failed_items", [])[:8])
    return messages


def _read_failure_artifact_tails(
    paths: list[str],
    *,
    max_chars: int = 4000,
) -> list[dict[str, str]]:
    """Read bounded text tails from failure artifacts for repair prompts."""
    seen: set[str] = set()
    artifacts: list[dict[str, str]] = []
    for raw_path in paths:
        if raw_path in seen:
            continue
        seen.add(raw_path)
        path = Path(raw_path)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        artifacts.append({"path": str(path), "tail": text[-max_chars:]})
    return artifacts


def _make_patch_subgraph_node() -> Any:
    """Create the patch subgraph node."""
    from agent_core.patching import build_patch_subgraph

    subgraph = build_patch_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "proposed_patch_path": state.get("proposed_patch_path", ""),
                "generated_code_dir": state.get("generated_code_dir", ""),
            }
        )
        return {
            "patch_review_path": result.get("patch_review_path", ""),
            "applied_patch_path": result.get("applied_patch_path", ""),
            "patch_applied_at": result.get("patch_applied_at", ""),
            "patch_status": result.get("patch_status", "failed"),
            "current_node": "patch_subgraph",
        }

    return _run


def _make_gate_subgraph_node() -> Any:
    """Create the gate validation subgraph node."""
    from agent_core.gates import build_gate_validation_subgraph

    subgraph = build_gate_validation_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "execution_mode": state.get("execution_mode", "strict"),
                "g4_model_ir_path": state.get("g4_model_ir_path", ""),
                "generated_code_dir": state.get("generated_code_dir", ""),
                "applied_patch_path": state.get("applied_patch_path", ""),
                "patch_applied_at": state.get("patch_applied_at", ""),
                "task_spec_path": state.get("task_spec_path", ""),
                "context_decision": state.get("context_decision", ""),
                "retry_count": state.get("retry_count", 0),
            }
        )
        new_retry = state.get("retry_count", 0) + (
            1 if result.get("validation_status") == "failed" else 0
        )
        return {
            "gate_results_path": result.get("gate_results_path", ""),
            "validation_status": result.get("validation_status", "failed"),
            "failed_gates": result.get("failed_gates", []),
            "skipped_gates": result.get("skipped_gates", []),
            "retry_count": new_retry,
            "max_retries_reached": new_retry >= 5,
            "current_node": "gate_subgraph",
        }

    return _run


def _make_artifact_subgraph_node() -> Any:
    """Create the artifact collection subgraph node."""
    from agent_core.artifacts import build_artifact_subgraph

    subgraph = build_artifact_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "gate_results_path": state.get("gate_results_path", ""),
                "g4_model_ir_path": state.get("g4_model_ir_path", ""),
                "model_review_report_path": state.get("model_review_report_path", ""),
                "construction_ledger_path": state.get("construction_ledger_path", ""),
                "code_module_plan_path": state.get("code_module_plan_path", ""),
                "proposed_patch_path": state.get("proposed_patch_path", ""),
                "validation_status": state.get("validation_status", ""),
            }
        )
        return {
            "review_artifact_dir": result.get("review_artifact_dir", ""),
            "artifact_manifest_path": result.get("artifact_manifest_path", ""),
            "artifact_status": result.get("artifact_status", "failed"),
            "current_node": "artifact_subgraph",
        }

    return _run


def _make_report_subgraph_node() -> Any:
    """Create the report generation subgraph node."""
    from agent_core.reports import build_report_subgraph

    subgraph = build_report_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke(
            {
                "job_id": state.get("job_id", ""),
                "user_query": state.get("user_query", ""),
                "execution_mode": state.get("execution_mode", "strict"),
                "context_decision": state.get("context_decision", ""),
                "validation_status": state.get("validation_status", ""),
                "g4_model_ir_path": state.get("g4_model_ir_path", ""),
                "gate_results_path": state.get("gate_results_path", ""),
                "model_review_report_path": state.get("model_review_report_path", ""),
                "simulation_scope": state.get("simulation_scope", []),
                "failed_gates": state.get("failed_gates", []),
                "errors": state.get("errors", []),
            }
        )
        return {
            "final_report_path": result.get("final_report_path", ""),
            "verified": result.get("verified", False),
            "termination_reason": result.get("termination_reason", ""),
            "current_node": "report_subgraph",
        }

    return _run


# ─── Intent router and response node wrappers ────────────────────────


def _make_intent_router_node() -> Any:
    """Create the intent router node wrapper."""
    from agent_core.intent.nodes import intent_router_node

    return intent_router_node


def _make_chat_response_node() -> Any:
    """Create the chat response node wrapper."""
    from agent_core.response.nodes import chat_response_node

    return chat_response_node


# ─── Main graph builder ──────────────────────────────────────────────


def build_main_graph() -> StateGraph:
    """Build the main orchestration graph.

    The main graph routes through intent_router first, then either
    responds directly for chat or enters the simulation pipeline.
    """
    graph = StateGraph(RadAgentMainState)

    # Add initialization and intent routing nodes
    graph.add_node("initialize_request", initialize_request)
    graph.add_node("intent_router", _make_intent_router_node())
    graph.add_node("chat_response_node", _make_chat_response_node())

    # Add workspace preparation (not a subgraph — just directory setup)
    graph.add_node("prepare_workspace", prepare_workspace)

    # Add subgraph wrapper nodes
    graph.add_node("context_subgraph", _make_context_subgraph_node())
    graph.add_node("task_planning_subgraph", _make_task_planning_subgraph_node())
    graph.add_node("g4_modeling_subgraph", _make_g4_modeling_subgraph_node())
    graph.add_node("human_confirmation_subgraph", _make_human_confirmation_subgraph_node())
    graph.add_node("g4_codegen_subgraph", _make_g4_codegen_subgraph_node())
    graph.add_node("patch_subgraph", _make_patch_subgraph_node())
    graph.add_node("gate_subgraph", _make_gate_subgraph_node())
    graph.add_node("artifact_subgraph", _make_artifact_subgraph_node())
    graph.add_node("report_subgraph", _make_report_subgraph_node())

    # Set entry point
    graph.set_entry_point("initialize_request")

    # initialize_request → intent_router
    graph.add_edge("initialize_request", "intent_router")

    # Conditional: intent_router → response nodes or pipeline
    graph.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {
            "chat_response_node": "chat_response_node",
            "human_confirmation_subgraph": "human_confirmation_subgraph",
            "prepare_workspace": "prepare_workspace",
        },
    )

    # Response nodes → END
    graph.add_edge("chat_response_node", END)

    # Linear edges: workspace → context
    graph.add_edge("prepare_workspace", "context_subgraph")

    # Conditional: context → task_planning or report
    graph.add_conditional_edges(
        "context_subgraph",
        route_after_context,
        {
            "task_planning_subgraph": "task_planning_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: task_planning → g4_modeling or report
    graph.add_conditional_edges(
        "task_planning_subgraph",
        route_after_task_planning,
        {
            "g4_modeling_subgraph": "g4_modeling_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: g4_modeling → human_confirmation or g4_codegen or report
    graph.add_conditional_edges(
        "g4_modeling_subgraph",
        route_after_g4_modeling,
        {
            "human_confirmation_subgraph": "human_confirmation_subgraph",
            "g4_codegen_subgraph": "g4_codegen_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: human_confirmation → g4_codegen, context, or report
    graph.add_conditional_edges(
        "human_confirmation_subgraph",
        route_after_human_confirmation,
        {
            "g4_codegen_subgraph": "g4_codegen_subgraph",
            "context_subgraph": "context_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: g4_codegen → patch or report
    graph.add_conditional_edges(
        "g4_codegen_subgraph",
        route_after_g4_codegen,
        {
            "patch_subgraph": "patch_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: patch → gates or report
    graph.add_conditional_edges(
        "patch_subgraph",
        route_after_patch,
        {
            "gate_subgraph": "gate_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: gates → artifact (success) or retry subgraph or report
    graph.add_conditional_edges(
        "gate_subgraph",
        route_after_gates,
        {
            "artifact_subgraph": "artifact_subgraph",
            "context_subgraph": "context_subgraph",
            "task_planning_subgraph": "task_planning_subgraph",
            "g4_modeling_subgraph": "g4_modeling_subgraph",
            "human_confirmation_subgraph": "human_confirmation_subgraph",
            "g4_codegen_subgraph": "g4_codegen_subgraph",
            "patch_subgraph": "patch_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Artifact → report (always)
    graph.add_conditional_edges(
        "artifact_subgraph",
        route_after_artifact,
        {
            "report_subgraph": "report_subgraph",
        },
    )

    # Report → END (always)
    graph.add_edge("report_subgraph", END)

    return graph


def compile_main_graph() -> Any:
    """Build and compile the main graph, ready for execution."""
    return build_main_graph().compile()


# ─── Subgraph node access for step-by-step REPL ──────────────────────


def build_subgraph_nodes() -> dict[str, Any]:
    """Return subgraph node functions for step-by-step execution.

    Each value is an async callable ``f(state) -> dict`` that the REPL
    can invoke individually, avoiding a full-graph ainvoke().
    """
    return {
        "context": _make_context_subgraph_node(),
        "task_planning": _make_task_planning_subgraph_node(),
        "g4_modeling": _make_g4_modeling_subgraph_node(),
        "human_confirmation": _make_human_confirmation_subgraph_node(),
        "g4_codegen": _make_g4_codegen_subgraph_node(),
        "patch": _make_patch_subgraph_node(),
        "gate": _make_gate_subgraph_node(),
        "artifact": _make_artifact_subgraph_node(),
        "report": _make_report_subgraph_node(),
    }
