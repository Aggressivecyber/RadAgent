"""G4 Codegen graph nodes — orchestrates the module agent pipeline.

This module contains the node functions used by g4_codegen_graph.py.
Each node is a thin wrapper that calls the appropriate module.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState
from agent_core.observability import record_event, write_failure_bundle

logger = logging.getLogger(__name__)

REQUIRED_MODULES = {
    "material",
    "geometry",
    "placement",
    "source",
    "physics",
    "sensitive_detector",
    "scoring",
    "output_manager",
    "action_initialization",
    "main_cmake",
}


# ── Planning nodes ───────────────────────────────────────────────────


async def build_codegen_plan_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Build overall codegen plan from G4ModelIR."""
    from agent_core.g4_codegen.planners.codegen_plan_builder import build_codegen_plan

    g4_model_ir = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "unknown")
    run_mode = state.get("run_mode", "strict")

    plan = build_codegen_plan(g4_model_ir, job_id, run_mode)
    return {"codegen_plan": plan, "current_node": "build_codegen_plan"}


async def plan_geometry_strategy_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Plan geometry strategy for each component."""
    from agent_core.g4_codegen.planners.geometry_strategy_planner import (
        plan_geometry_strategy,
    )

    g4_model_ir = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "unknown")

    plan = plan_geometry_strategy(g4_model_ir, job_id)
    return {"geometry_strategy_plan": plan, "current_node": "plan_geometry_strategy"}


async def plan_code_architecture_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Plan C++ class architecture."""
    from agent_core.g4_codegen.planners.code_architecture_planner import (
        plan_code_architecture,
    )

    g4_model_ir = state.get("g4_model_ir", {})
    codegen_plan = state.get("codegen_plan", {})
    job_id = state.get("job_id", "unknown")

    plan = plan_code_architecture(g4_model_ir, codegen_plan, job_id)
    return {"code_architecture_plan": plan, "current_node": "plan_code_architecture"}


async def build_module_contracts_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Build module contracts for all required modules."""
    from agent_core.g4_codegen.planners.module_contract_builder import (
        build_module_contracts,
    )

    g4_model_ir = state.get("g4_model_ir", {})
    codegen_plan = state.get("codegen_plan", {})
    job_id = state.get("job_id", "unknown")

    contracts = build_module_contracts(g4_model_ir, codegen_plan, job_id)
    return {"module_contracts": contracts, "current_node": "build_module_contracts"}


# ── Module context builder ───────────────────────────────────────────


async def build_module_contexts_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Build context for each module agent."""
    from agent_core.g4_codegen.module_agents.module_context_builder import (
        build_module_context,
    )

    g4_model_ir = state.get("g4_model_ir", {})
    codegen_plan = state.get("codegen_plan", {})
    geometry_strategy = state.get("geometry_strategy_plan", {})
    code_architecture = state.get("code_architecture_plan", {})
    module_contracts = state.get("module_contracts", {})
    job_id = state.get("job_id", "unknown")
    run_mode = state.get("run_mode", "strict")
    rag_context = state.get("rag_context", [])
    rag_score = state.get("rag_score")
    web_context = state.get("web_context", [])
    context_decision = state.get("context_decision")
    web_search_available = state.get("web_search_available")

    contexts: dict[str, Any] = {}
    for module_name, contract in module_contracts.items():
        ctx = build_module_context(
            module_name=module_name,
            module_contract=contract,
            g4_model_ir=g4_model_ir,
            codegen_plan=codegen_plan,
            geometry_strategy_plan=geometry_strategy,
            code_architecture_plan=code_architecture,
            job_id=job_id,
            run_mode=run_mode,
            rag_context=rag_context,
            rag_score=rag_score,
            web_context=web_context,
            context_decision=context_decision,
            web_search_available=web_search_available,
        )
        contexts[module_name] = ctx

    return {"module_contexts": contexts, "current_node": "build_module_contexts"}


# ── Module agent runner ──────────────────────────────────────────────


async def run_module_agent_node(
    state: G4CodegenSubgraphState,
    module_name: str,
) -> dict[str, Any]:
    """Run a specific module agent.

    This is a generic node factory — call with the module name.
    """
    from agent_core.g4_codegen.module_agents.base import save_module_result

    module_contexts = state.get("module_contexts", {})
    ctx = module_contexts.get(module_name, {})
    job_id = state.get("job_id", "unknown")

    # Build summaries from completed modules so this agent knows
    # what has already been generated.
    summaries: list[dict[str, Any]] = []
    completed = state.get("module_results", {})
    for prev_module, prev_result in completed.items():
        if prev_module == module_name:
            continue
        for f in prev_result.get("generated_files", []):
            summaries.append(_extract_file_summary(prev_module, f))

    # Inject summaries into the context dict
    ctx = dict(ctx)
    ctx["existing_generated_file_summaries"] = summaries
    ctx["actual_context_used_by_agent"] = True

    # Import and run the appropriate agent
    agent_fn = _get_agent_function(module_name)
    result = await agent_fn(ctx)

    # Save result
    save_module_result(result, job_id)
    record_event(
        job_id=job_id,
        event_type="module_agent_result",
        status="passed" if result.status in {"generated", "repaired"} else "failed",
        phase="g4_codegen",
        module_name=module_name,
        summary=f"{module_name} module agent returned {result.status}",
        metrics={"generated_file_count": len(result.generated_files)},
        artifacts=[
            {"path": f.path, "byte_count": len(f.new_content.encode("utf-8", errors="ignore"))}
            for f in result.generated_files
        ],
        errors=list(result.errors),
        warnings=list(result.warnings),
    )

    return {
        "module_results": {module_name: result.model_dump()},
        "module_contexts": {module_name: ctx},
        "current_node": f"run_{module_name}_agent",
    }


# ── File summary extraction ──────────────────────────────────────────


def _extract_file_summary(module_name: str, file_data: dict[str, Any]) -> dict[str, Any]:
    """Extract a lightweight summary from a generated file for cross-module context."""
    content = file_data.get("new_content", "") or file_data.get("content", "")
    return {
        "module_name": module_name,
        "path": file_data.get("path", ""),
        "generated_by": file_data.get("generated_by", f"{module_name}_module_agent"),
        "classes": _extract_classes(content),
        "public_methods": _extract_public_methods(content),
        "includes": _extract_includes(content),
        "provided_symbols": _extract_classes(content),  # symbols ≈ class names
    }


def _extract_includes(content: str) -> list[str]:
    """Extract #include directives from C++ content."""
    import re

    return re.findall(r'#include\s+[<"]([^>"]+)[>"]', content)


def _extract_classes(content: str) -> list[str]:
    """Extract class names from C++ content."""
    import re

    return re.findall(r"\bclass\s+(\w+)", content)


def _extract_public_methods(content: str) -> list[str]:
    """Extract public method names from C++ content."""
    import re

    # Match methods after 'public:' keyword
    return re.findall(r"\bpublic:\s*(?:.*?)?\b(\w+)\s*\(", content, re.DOTALL)


def _get_agent_function(module_name: str):  # type: ignore[no-untyped-def]
    """Get the agent function for a module."""
    from agent_core.g4_codegen.module_agents.action_initialization_agent import (
        run_action_initialization_agent,
    )
    from agent_core.g4_codegen.module_agents.geometry_agent import run_geometry_agent
    from agent_core.g4_codegen.module_agents.main_cmake_agent import run_main_cmake_agent
    from agent_core.g4_codegen.module_agents.material_agent import run_material_agent
    from agent_core.g4_codegen.module_agents.output_manager_agent import (
        run_output_manager_agent,
    )
    from agent_core.g4_codegen.module_agents.physics_agent import run_physics_agent
    from agent_core.g4_codegen.module_agents.placement_agent import run_placement_agent
    from agent_core.g4_codegen.module_agents.scoring_agent import run_scoring_agent
    from agent_core.g4_codegen.module_agents.sensitive_detector_agent import (
        run_sensitive_detector_agent,
    )
    from agent_core.g4_codegen.module_agents.source_agent import run_source_agent

    agents = {
        "material": run_material_agent,
        "geometry": run_geometry_agent,
        "placement": run_placement_agent,
        "source": run_source_agent,
        "physics": run_physics_agent,
        "sensitive_detector": run_sensitive_detector_agent,
        "scoring": run_scoring_agent,
        "output_manager": run_output_manager_agent,
        "action_initialization": run_action_initialization_agent,
        "main_cmake": run_main_cmake_agent,
    }
    return agents[module_name]


# ── Module gate runners ──────────────────────────────────────────────


async def run_module_hard_gate_node(
    state: G4CodegenSubgraphState,
    module_name: str,
) -> dict[str, Any]:
    """Run hard gate for a specific module.

    Passes module_status to hard gate so it can reject
    failed ModuleAgentResult.
    """
    module_results = state.get("module_results", {})
    result = module_results.get(module_name, {})
    generated_files_data = result.get("generated_files", [])
    module_status = result.get("status", "unknown")

    from agent_core.g4_codegen.schemas import GeneratedModuleFile

    files = [GeneratedModuleFile(**f) for f in generated_files_data]

    gate_fn = _get_hard_gate_function(module_name)
    gate_result = gate_fn(files, module_status=module_status)

    # Persist
    from agent_core.config.workspace import get_job_dir

    job_id = state.get("job_id", "unknown")
    gate_dir = get_job_dir(job_id) / "06_codegen" / "module_gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    gate_path = gate_dir / f"{module_name}_hard_gate.json"
    gate_path.write_text(json.dumps(gate_result.model_dump(), indent=2))
    record_event(
        job_id=job_id,
        event_type="module_gate_result",
        status="passed" if gate_result.status == "pass" else "failed",
        phase="g4_codegen",
        module_name=module_name,
        gate_name=f"{module_name}_hard_gate",
        summary=f"{module_name} hard gate {gate_result.status}",
        metrics={
            "check_count": len(gate_result.checks),
            "error_count": len(gate_result.errors),
        },
        artifacts=[{"path": str(gate_path)}],
        errors=list(gate_result.errors),
        warnings=list(gate_result.warnings),
    )

    return {
        "module_gate_results": {module_name: {"hard": gate_result.model_dump()}},
        "current_node": f"{module_name}_hard_gate",
    }


def _get_hard_gate_function(module_name: str):  # type: ignore[no-untyped-def]
    """Get the hard gate function for a module."""
    from agent_core.g4_codegen.module_gates.action_hard_gate import run_action_hard_gate
    from agent_core.g4_codegen.module_gates.geometry_hard_gate import run_geometry_hard_gate
    from agent_core.g4_codegen.module_gates.main_cmake_hard_gate import run_main_cmake_hard_gate
    from agent_core.g4_codegen.module_gates.material_hard_gate import run_material_hard_gate
    from agent_core.g4_codegen.module_gates.output_manager_hard_gate import (
        run_output_manager_hard_gate,
    )
    from agent_core.g4_codegen.module_gates.physics_hard_gate import run_physics_hard_gate
    from agent_core.g4_codegen.module_gates.placement_hard_gate import run_placement_hard_gate
    from agent_core.g4_codegen.module_gates.scoring_hard_gate import run_scoring_hard_gate
    from agent_core.g4_codegen.module_gates.sensitive_detector_hard_gate import (
        run_sensitive_detector_hard_gate,
    )
    from agent_core.g4_codegen.module_gates.source_hard_gate import run_source_hard_gate

    gates = {
        "material": run_material_hard_gate,
        "geometry": run_geometry_hard_gate,
        "placement": run_placement_hard_gate,
        "source": run_source_hard_gate,
        "physics": run_physics_hard_gate,
        "sensitive_detector": run_sensitive_detector_hard_gate,
        "scoring": run_scoring_hard_gate,
        "output_manager": run_output_manager_hard_gate,
        "action_initialization": run_action_hard_gate,
        "main_cmake": run_main_cmake_hard_gate,
    }
    return gates[module_name]


async def run_module_llm_gate_node(
    state: G4CodegenSubgraphState,
    module_name: str,
) -> dict[str, Any]:
    """Run LLM gate for a specific module.

    Only runs if hard gate passed.
    """
    gate_results = state.get("module_gate_results", {})
    module_gate = gate_results.get(module_name, {})
    hard_gate = module_gate.get("hard", {})

    if hard_gate.get("status") != "pass":
        # Hard gate failed — skip LLM gate
        skipped_gate = {
            "module_name": module_name,
            "gate_type": "llm",
            "status": "skipped",
            "errors": ["Hard gate failed — LLM gate skipped"],
        }
        return {
            "module_gate_results": {module_name: {"llm": skipped_gate}},
            "current_node": f"{module_name}_llm_gate",
        }

    from agent_core.g4_codegen.module_gates.llm_gate_base import run_llm_gate

    module_contexts = state.get("module_contexts", {})
    module_results = state.get("module_results", {})
    result = module_results.get(module_name, {})
    ctx = module_contexts.get(module_name, {})
    generated_files = result.get("generated_files", [])

    gate_result = await run_llm_gate(
        module_name=module_name,
        module_context=ctx,
        generated_files_content=generated_files,
        hard_gate_result=hard_gate,
    )

    # Persist
    from agent_core.config.workspace import get_job_dir

    job_id = state.get("job_id", "unknown")
    gate_dir = get_job_dir(job_id) / "06_codegen" / "module_gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    gate_path = gate_dir / f"{module_name}_llm_gate.json"
    gate_path.write_text(json.dumps(gate_result.model_dump(), indent=2))
    record_event(
        job_id=job_id,
        event_type="module_gate_result",
        status="passed" if gate_result.status == "pass" else "failed",
        phase="g4_codegen",
        module_name=module_name,
        gate_name=f"{module_name}_llm_gate",
        summary=f"{module_name} LLM gate {gate_result.status}",
        metrics={
            "check_count": len(gate_result.checks),
            "error_count": len(gate_result.errors),
            "overall_score": gate_result.scorecard.get("overall_score"),
        },
        artifacts=[{"path": str(gate_path)}],
        errors=list(gate_result.errors),
        warnings=list(gate_result.warnings),
        details={"scorecard": gate_result.scorecard},
    )

    return {
        "module_gate_results": {module_name: {"llm": gate_result.model_dump()}},
        "current_node": f"{module_name}_llm_gate",
    }


# ── Module repair node ───────────────────────────────────────────────


async def repair_module_node(
    state: G4CodegenSubgraphState,
    module_name: str,
) -> dict[str, Any]:
    """Repair a failed module if needed.

    P0-14/P0-15: When repair reaches max attempts and still fails:
    - module status → "failed"
    - g4_codegen_status → "failed"
    - codegen_errors updated
    - Graph routes to persist (not back to hard gate)
    """
    gate_results = state.get("module_gate_results", {})
    module_gate = gate_results.get(module_name, {})
    hard_gate = module_gate.get("hard", {})
    llm_gate = module_gate.get("llm", {})

    # Check if repair is needed
    needs_repair = hard_gate.get("status") == "fail" or llm_gate.get("status") == "fail"

    if not needs_repair:
        return {"current_node": f"repair_{module_name}"}

    from agent_core.g4_codegen.repair.module_repair_loop import (
        repair_module,
        save_repair_summary,
    )
    from agent_core.g4_codegen.schemas import ModuleAgentResult, ModuleGateResult

    module_results = state.get("module_results", {})
    module_contexts = state.get("module_contexts", {})

    original_result = ModuleAgentResult(**module_results.get(module_name, {}))
    if hard_gate.get("status") == "fail":
        gate = ModuleGateResult(**hard_gate)
    else:
        gate = ModuleGateResult(**llm_gate)
    ctx = module_contexts.get(module_name, {})

    job_id = state.get("job_id", "unknown")
    repaired = await repair_module(module_name, ctx, original_result, gate, job_id=job_id)
    save_repair_summary(module_name, repaired, job_id)
    record_event(
        job_id=job_id,
        event_type="module_repair_result",
        status="passed" if repaired.status in {"generated", "repaired"} else "failed",
        phase="g4_codegen",
        module_name=module_name,
        summary=f"{module_name} repair returned {repaired.status}",
        metrics={
            "attempt_count": len(repaired.repair_attempts),
            "generated_file_count": len(repaired.generated_files),
        },
        errors=list(repaired.errors),
        warnings=list(repaired.warnings),
    )

    # P0-14/P0-15: If repair failed, mark codegen as failed
    updates: dict[str, Any] = {
        "module_results": {module_name: repaired.model_dump()},
        "module_repair_results": {
            module_name: {
                "status": repaired.status,
                "attempts": len(repaired.repair_attempts),
            }
        },
        "current_node": f"repair_{module_name}",
    }

    if repaired.status == "failed":
        updates["g4_codegen_status"] = "failed"
        updates["codegen_errors"] = list(state.get("codegen_errors", [])) + [
            f"Module '{module_name}' repair failed after "
            f"{len(repaired.repair_attempts)} attempts: " + "; ".join(repaired.errors[:3])
        ]
        logger.warning(
            "Module %s repair failed — terminating codegen for this module",
            module_name,
        )

    return updates


async def run_module_layer_node(
    state: G4CodegenSubgraphState,
    layer_name: str,
    module_names: list[str],
) -> dict[str, Any]:
    """Run a layer of module pipelines concurrently."""
    layer_started = time.monotonic()
    record_event(
        job_id=state.get("job_id", "unknown"),
        event_type="module_layer_start",
        status="running",
        phase="g4_codegen",
        layer=layer_name,
        summary=f"Starting module layer {layer_name}",
        metrics={"module_count": len(module_names)},
        details={"modules": module_names},
    )

    async def _run_one(module_name: str) -> dict[str, Any]:
        local_state: dict[str, Any] = dict(state)
        result: dict[str, Any] = {}

        agent_update = await run_module_agent_node(local_state, module_name)
        _merge_update(local_state, agent_update)
        _merge_update(result, agent_update)

        for _attempt in range(4):
            hard_update = await run_module_hard_gate_node(local_state, module_name)
            _merge_update(local_state, hard_update)
            _merge_update(result, hard_update)
            hard = local_state.get("module_gate_results", {}).get(module_name, {}).get("hard", {})

            if hard.get("status") == "pass":
                llm_update = await run_module_llm_gate_node(local_state, module_name)
                _merge_update(local_state, llm_update)
                _merge_update(result, llm_update)
                llm = local_state.get("module_gate_results", {}).get(module_name, {}).get("llm", {})
                if llm.get("status") == "pass":
                    break

            repair_update = await repair_module_node(local_state, module_name)
            _merge_update(local_state, repair_update)
            _merge_update(result, repair_update)
            repair = local_state.get("module_repair_results", {}).get(module_name, {})
            if repair.get("status") == "failed":
                break

        result["current_node"] = f"run_{layer_name}"
        return result

    module_updates = await asyncio.gather(*[_run_one(module_name) for module_name in module_names])
    combined: dict[str, Any] = {
        "current_node": f"run_{layer_name}",
        "module_results": dict(state.get("module_results", {})),
        "module_gate_results": dict(state.get("module_gate_results", {})),
        "module_repair_results": dict(state.get("module_repair_results", {})),
        "codegen_errors": list(state.get("codegen_errors", [])),
        "codegen_warnings": list(state.get("codegen_warnings", [])),
    }
    for update in module_updates:
        _merge_update(combined, update)
    combined["current_node"] = f"run_{layer_name}"
    layer_errors = [
        error
        for update in module_updates
        for error in update.get("codegen_errors", [])
    ]
    record_event(
        job_id=state.get("job_id", "unknown"),
        event_type="module_layer_end",
        status="failed" if layer_errors else "passed",
        phase="g4_codegen",
        layer=layer_name,
        summary=f"Finished module layer {layer_name}",
        duration_ms=(time.monotonic() - layer_started) * 1000,
        metrics={
            "module_count": len(module_names),
            "error_count": len(layer_errors),
        },
        errors=layer_errors,
    )
    return combined


def _merge_update(target: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge a graph-node update into local state."""
    for key, value in update.items():
        if key in {"codegen_errors", "codegen_warnings"}:
            target.setdefault(key, [])
            target[key].extend(value or [])
        elif isinstance(target.get(key), dict) and isinstance(value, dict):
            _deep_merge_dict(target[key], value)
        else:
            target[key] = value


def _deep_merge_dict(target: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            _deep_merge_dict(target[key], value)
        else:
            target[key] = value


# ── Integration nodes ────────────────────────────────────────────────


async def build_interface_contracts_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Build interface contracts (CAD/GDML, G4→TCAD, TCAD→SPICE)."""
    from agent_core.g4_codegen.interface_contracts import build_interface_contracts

    g4_model_ir = state.get("g4_model_ir", {})
    geometry_strategy = state.get("geometry_strategy_plan", {})
    job_id = state.get("job_id", "unknown")

    contracts = build_interface_contracts(g4_model_ir, geometry_strategy, job_id)
    return {"interface_contracts": contracts, "current_node": "build_interface_contracts"}


async def integration_assembler_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Assemble proposed_patch from passed module results."""
    from agent_core.g4_codegen.integration.integration_assembler import (
        assemble_proposed_patch,
    )

    module_results = state.get("module_results", {})
    module_gate_results = state.get("module_gate_results", {})
    job_id = state.get("job_id", "unknown")

    patch = assemble_proposed_patch(module_results, module_gate_results, job_id)
    return {
        "proposed_patch": patch,
        "current_node": "integration_assembler",
    }


async def layer_consistency_gate_node(
    state: G4CodegenSubgraphState,
    layer_name: str,
    module_names: list[str],
) -> dict[str, Any]:
    """Check that every module in a parallel layer passed before the next layer."""
    from agent_core.config.workspace import get_job_dir

    module_results = state.get("module_results", {})
    module_gate_results = state.get("module_gate_results", {})
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    for module_name in module_names:
        result = module_results.get(module_name, {})
        hard = module_gate_results.get(module_name, {}).get("hard", {})
        llm = module_gate_results.get(module_name, {}).get("llm", {})
        module_ok = result.get("status") in {"generated", "repaired"}
        hard_ok = hard.get("status") == "pass"
        llm_ok = llm.get("status") == "pass"
        status = "pass" if module_ok and hard_ok and llm_ok else "fail"
        checks.append(
            {
                "check": f"{module_name}_layer_completion",
                "status": status,
                "message": (
                    f"module_status={result.get('status')}; "
                    f"hard={hard.get('status')}; llm={llm.get('status')}"
                ),
            }
        )
        if status != "pass":
            errors.append(
                f"{module_name} did not pass layer gate "
                f"(module={result.get('status')}, hard={hard.get('status')}, "
                f"llm={llm.get('status')})"
            )

    gate = {
        "layer_name": layer_name,
        "status": "pass" if not errors else "fail",
        "modules": module_names,
        "checks": checks,
        "errors": errors,
    }

    gate_dir = get_job_dir(state.get("job_id", "unknown")) / "06_codegen" / "layer_gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    (gate_dir / f"{layer_name}.json").write_text(json.dumps(gate, indent=2, ensure_ascii=False))
    record_event(
        job_id=state.get("job_id", "unknown"),
        event_type="layer_gate_result",
        status="passed" if gate["status"] == "pass" else "failed",
        phase="g4_codegen",
        layer=layer_name,
        gate_name=layer_name,
        summary=f"{layer_name} {gate['status']}",
        metrics={"check_count": len(checks), "error_count": len(errors)},
        errors=errors,
        details={"checks": checks},
    )

    updated_layer_gates = dict(state.get("layer_gate_results", {}))
    updated_layer_gates[layer_name] = gate

    updates: dict[str, Any] = {
        "layer_gate_results": updated_layer_gates,
        "codegen_errors": list(state.get("codegen_errors", [])) + errors,
        "current_node": layer_name,
    }
    if errors:
        updates["g4_codegen_status"] = "failed"
    return updates


async def global_code_repair_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Run the global repair pass over the assembled multi-module patch."""
    from agent_core.g4_codegen.global_repair import run_global_code_repair

    proposed_patch = state.get("proposed_patch", {})
    job_id = state.get("job_id", "unknown")
    repaired_patch, report = run_global_code_repair(proposed_patch, job_id)
    record_event(
        job_id=job_id,
        event_type="global_repair_result",
        status="passed" if report.get("status") == "passed" else "failed",
        phase="g4_codegen",
        summary="Global code repair completed",
        metrics={"issues_fixed": len(report.get("issues_fixed", []))},
        errors=report.get("errors", []),
        details=report,
    )
    return {
        "proposed_patch": repaired_patch,
        "global_code_repair_report": report,
        "current_node": "global_code_repair_agent",
        "codegen_errors": list(state.get("codegen_errors", [])) + report.get("errors", []),
    }


async def static_semantic_scanner_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Run static semantic scan on proposed_patch."""
    from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code

    proposed_patch = state.get("proposed_patch", {})
    job_id = state.get("job_id", "unknown")

    scan = scan_generated_code(proposed_patch, job_id)
    record_event(
        job_id=job_id,
        event_type="static_semantic_scan_result",
        status="passed" if scan.get("status") == "pass" else "failed",
        phase="g4_codegen",
        gate_name="static_semantic_scanner",
        summary=f"Static semantic scan {scan.get('status')}",
        metrics={"finding_count": len(scan.get("findings", []))},
        errors=[str(f) for f in scan.get("findings", []) if isinstance(f, str)],
        details={"status": scan.get("status")},
    )
    return {"static_semantic_scan": scan, "current_node": "static_semantic_scanner"}


async def cross_file_hard_gate_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Run cross-file hard gate."""
    from agent_core.g4_codegen.integration.cross_file_hard_gate import (
        run_cross_file_hard_gate,
    )

    proposed_patch = state.get("proposed_patch", {})
    code_architecture = state.get("code_architecture_plan", {})
    job_id = state.get("job_id", "unknown")

    gate = run_cross_file_hard_gate(proposed_patch, code_architecture, job_id)
    record_event(
        job_id=job_id,
        event_type="cross_file_gate_result",
        status="passed" if gate.get("status") == "pass" else "failed",
        phase="g4_codegen",
        gate_name="cross_file_hard_gate",
        summary=f"Cross-file hard gate {gate.get('status')}",
        metrics={"error_count": len(gate.get("errors", []))},
        errors=list(gate.get("errors", [])),
        warnings=list(gate.get("warnings", [])),
    )
    return {"cross_file_hard_gate": gate, "current_node": "cross_file_hard_gate"}


async def cross_file_llm_gate_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Run cross-file LLM gate."""
    from agent_core.g4_codegen.integration.cross_file_llm_gate import (
        run_cross_file_llm_gate,
    )

    proposed_patch = state.get("proposed_patch", {})
    module_gate_results = state.get("module_gate_results", {})
    job_id = state.get("job_id", "unknown")

    gate = await run_cross_file_llm_gate(
        proposed_patch,
        module_gate_results,
        job_id,
        static_semantic_scan=state.get("static_semantic_scan", {}),
        cross_file_hard_gate=state.get("cross_file_hard_gate", {}),
        interface_contracts=state.get("interface_contracts", {}),
    )
    record_event(
        job_id=job_id,
        event_type="cross_file_gate_result",
        status="passed" if gate.get("status") == "pass" else "failed",
        phase="g4_codegen",
        gate_name="cross_file_llm_gate",
        summary=f"Cross-file LLM gate {gate.get('status')}",
        metrics={
            "error_count": len(gate.get("errors", [])),
            "overall_score": gate.get("scorecard", {}).get("overall_score"),
        },
        errors=list(gate.get("errors", [])),
        warnings=list(gate.get("warnings", [])),
        details={"scorecard": gate.get("scorecard", {})},
    )
    return {"cross_file_llm_gate": gate, "current_node": "cross_file_llm_gate"}


async def persist_codegen_output_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Persist final codegen output."""
    job_id = state.get("job_id", "unknown")
    proposed_patch = state.get("proposed_patch", {})

    from agent_core.config.workspace import get_job_dir

    job_dir = get_job_dir(job_id)
    codegen_dir = job_dir / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    # Save proposed patch to standard location
    patch_path = codegen_dir / "proposed_patch.json"
    patch_path.write_text(json.dumps(proposed_patch, indent=2, ensure_ascii=False))

    # Determine status
    has_code = bool(proposed_patch.get("changed_files"))
    cross_hard = state.get("cross_file_hard_gate", {})
    cross_llm = state.get("cross_file_llm_gate", {})
    global_repair = state.get("global_code_repair_report", {})

    # Check static semantic scan status
    static_scan = state.get("static_semantic_scan", {})

    module_results = state.get("module_results", {})
    module_gate_results = state.get("module_gate_results", {})
    layer_gate_results = state.get("layer_gate_results", {})
    modules_in_patch = {
        f.get("module_name") for f in proposed_patch.get("changed_files", []) if isinstance(f, dict)
    }
    missing_modules = REQUIRED_MODULES - set(module_results.keys())
    missing_from_patch = REQUIRED_MODULES - modules_in_patch
    failed_module_gates = [
        module_name
        for module_name in REQUIRED_MODULES
        if module_gate_results.get(module_name, {}).get("hard", {}).get("status") != "pass"
        or module_gate_results.get(module_name, {}).get("llm", {}).get("status") != "pass"
    ]
    failed_layer_gates = [
        layer_name
        for layer_name, layer_gate in layer_gate_results.items()
        if layer_gate.get("status") != "pass"
    ]

    new_errors: list[str] = []

    if not has_code:
        status = "failed"
    elif missing_modules or missing_from_patch or failed_module_gates or failed_layer_gates:
        status = "failed"
    elif static_scan.get("status") == "fail":
        status = "failed"
    elif global_repair and global_repair.get("status") != "passed":
        status = "failed"
    elif cross_hard.get("status") == "fail":
        status = "failed"
    elif cross_llm.get("status") != "pass":
        status = "failed"
    else:
        status = "passed"

    # Target directory for generated Geant4 files is 08_geant4
    geant4_dir = job_dir / "08_geant4"
    geant4_dir.mkdir(parents=True, exist_ok=True)
    generated_code_dir = str(geant4_dir)

    if missing_modules:
        new_errors.append(f"Missing module results: {sorted(missing_modules)}")
    if missing_from_patch:
        new_errors.append(f"Missing modules from patch: {sorted(missing_from_patch)}")
    if failed_module_gates:
        new_errors.append(f"Failed module gates: {sorted(failed_module_gates)}")
    if failed_layer_gates:
        new_errors.append(f"Failed layer gates: {sorted(failed_layer_gates)}")

    updates: dict[str, Any] = {
        "proposed_patch_path": str(patch_path),
        "generated_code_dir": generated_code_dir,
        "g4_codegen_status": status,
        "current_node": "persist_codegen_output",
    }
    if new_errors:
        updates["codegen_errors"] = list(state.get("codegen_errors", [])) + new_errors
    record_event(
        job_id=job_id,
        event_type="g4_codegen_persist",
        status="passed" if status == "passed" else "failed",
        phase="g4_codegen",
        summary=f"G4 codegen status {status}",
        metrics={
            "changed_file_count": len(proposed_patch.get("changed_files", [])),
            "missing_module_count": len(missing_modules),
            "failed_module_gate_count": len(failed_module_gates),
        },
        artifacts=[{"path": str(patch_path)}, {"path": generated_code_dir}],
        errors=list(state.get("codegen_errors", [])) + new_errors,
    )
    if status != "passed":
        write_failure_bundle(
            job_id=job_id,
            status=status,
            phase="g4_codegen",
            errors=list(state.get("codegen_errors", [])) + new_errors,
            artifacts=[{"path": str(patch_path)}, {"path": generated_code_dir}],
            details={
                "missing_modules": sorted(missing_modules),
                "missing_from_patch": sorted(missing_from_patch),
                "failed_module_gates": sorted(failed_module_gates),
                "failed_layer_gates": sorted(failed_layer_gates),
            },
        )
    return updates
