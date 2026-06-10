"""G4 Codegen graph nodes — orchestrates the module agent pipeline.

This module contains the node functions used by g4_codegen_graph.py.
Each node is a thin wrapper that calls the appropriate module.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState
from agent_core.observability import record_event, write_failure_bundle
from agent_core.workspace.paths import GEANT4_PROJECT_DIRNAME, STAGE_CODEGEN, STAGE_PATCH

REQUIRED_MODULES = {
    "simulation_core",
    "beam_physics",
    "runtime_app",
}
GLOBAL_INTEGRATION_RUNTIME_REPAIR_ROUNDS = 8
RUNTIME_AUDIT_REPAIR_ROUNDS = 4
PHYSICS_REVIEW_REPAIR_ROUNDS = 4


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
    runtime_failure_context = state.get("runtime_failure_context", {})

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
            runtime_failure_context=runtime_failure_context,
        )
        contexts[module_name] = ctx

    return {"module_contexts": contexts, "current_node": "build_module_contexts"}


async def context_coordinator_node(
    state: G4CodegenSubgraphState,
    coordinator_name: str,
    target_modules: list[str],
) -> dict[str, Any]:
    """Summarize generated code for later agents and expose code lookup manifest."""
    from agent_core.g4_codegen.context_coordinator import coordinate_generated_context

    job_id = state.get("job_id", "unknown")
    coordination = await coordinate_generated_context(
        job_id=job_id,
        module_results=state.get("module_results", {}),
        module_contracts=state.get("module_contracts", {}),
        target_modules=target_modules,
        coordinator_name=coordinator_name,
    )
    module_contexts = dict(state.get("module_contexts", {}))
    for module_name in target_modules:
        ctx = dict(module_contexts.get(module_name, {}))
        if not ctx:
            continue
        ctx["context_coordination"] = coordination
        ctx["generated_code_lookup_manifest"] = coordination.get(
            "generated_code_lookup_manifest", {}
        )
        ctx["existing_generated_file_summaries"] = coordination.get("file_summaries", [])
        module_contexts[module_name] = ctx
    return {
        "context_coordination": {coordinator_name: coordination},
        "module_contexts": module_contexts,
        "current_node": coordinator_name,
    }


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
    latest_coordination = _latest_context_coordination(state.get("context_coordination", {}))
    if latest_coordination:
        ctx["context_coordination"] = latest_coordination
        ctx["generated_code_lookup_manifest"] = latest_coordination.get(
            "generated_code_lookup_manifest", {}
        )
        ctx["existing_generated_file_summaries"] = latest_coordination.get(
            "file_summaries", summaries
        )
    else:
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


def _latest_context_coordination(coordination_by_node: dict[str, Any]) -> dict[str, Any]:
    """Return the most recent context coordination payload from graph state."""
    if not isinstance(coordination_by_node, dict) or not coordination_by_node:
        return {}
    for value in reversed(list(coordination_by_node.values())):
        if isinstance(value, dict):
            return value
    return {}


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
        "constructor_signatures": _extract_constructor_signatures(content),
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

    methods: list[str] = []
    public_blocks = re.findall(
        r"\bpublic:\s*(.*?)(?=\bprivate:|\bprotected:|\n};|$)",
        content,
        re.DOTALL,
    )
    for block in public_blocks:
        for match in re.finditer(
            r"(?:~?[A-Za-z_]\w*|operator\s+\w+)\s*\(",
            block,
        ):
            name = match.group(0).split("(", 1)[0].strip()
            if name in {"if", "for", "while", "switch", "return"}:
                continue
            methods.append(name)
    return sorted(set(methods))


def _extract_constructor_signatures(content: str) -> list[str]:
    """Extract public constructor declaration signatures from C++ headers."""
    import re

    classes = _extract_classes(content)
    if not classes:
        return []
    public_blocks = re.findall(
        r"\bpublic:\s*(.*?)(?=\bprivate:|\bprotected:|\n};|$)",
        content,
        re.DOTALL,
    )
    signatures: list[str] = []
    for class_name in classes:
        pattern = (
            rf"(?:explicit\s+)?{re.escape(class_name)}\s*"
            r"\([^;{}]*\)\s*(?:=\s*default)?\s*;"
        )
        for block in public_blocks:
            for match in re.finditer(pattern, block, re.DOTALL):
                signatures.append(re.sub(r"\s+", " ", match.group(0)).strip().rstrip(";"))
    return sorted(set(signatures))


def _get_agent_function(module_name: str):  # type: ignore[no-untyped-def]
    """Get the agent function for a module."""
    from agent_core.g4_codegen.module_agents.beam_physics_agent import (
        run_beam_physics_agent,
    )
    from agent_core.g4_codegen.module_agents.runtime_app_agent import run_runtime_app_agent
    from agent_core.g4_codegen.module_agents.simulation_core_agent import (
        run_simulation_core_agent,
    )

    agents = {
        "simulation_core": run_simulation_core_agent,
        "beam_physics": run_beam_physics_agent,
        "runtime_app": run_runtime_app_agent,
    }
    return agents[module_name]


async def run_module_layer_node(
    state: G4CodegenSubgraphState,
    layer_name: str,
    module_names: list[str],
) -> dict[str, Any]:
    """Run a layer of module pipelines concurrently."""
    from agent_core.config.environment import resolve_safe_concurrency

    layer_started = time.monotonic()
    max_concurrency = resolve_safe_concurrency(
        len(module_names),
        override_env="RADAGENT_G4_MODULE_MAX_CONCURRENCY",
        hard_cap=4,
        memory_per_worker_gb=2.0,
    )
    record_event(
        job_id=state.get("job_id", "unknown"),
        event_type="module_layer_start",
        status="running",
        phase="g4_codegen",
        layer=layer_name,
        summary=f"Starting module layer {layer_name}",
        metrics={"module_count": len(module_names), "max_concurrency": max_concurrency},
        details={"modules": module_names},
    )
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_one(module_name: str) -> dict[str, Any]:
        async with semaphore:
            local_state: dict[str, Any] = dict(state)
            agent_update = await run_module_agent_node(local_state, module_name)
            agent_update["current_node"] = f"run_{layer_name}"
            return agent_update

    module_updates = await asyncio.gather(*[_run_one(module_name) for module_name in module_names])
    combined: dict[str, Any] = {
        "current_node": f"run_{layer_name}",
        "module_results": dict(state.get("module_results", {})),
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
            "max_concurrency": max_concurrency,
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
    job_id = state.get("job_id", "unknown")

    patch = assemble_proposed_patch(module_results, job_id)
    return {
        "proposed_patch": patch,
        "current_node": "integration_assembler",
    }


async def layer_consistency_gate_node(
    state: G4CodegenSubgraphState,
    layer_name: str,
    module_names: list[str],
) -> dict[str, Any]:
    """Check that every coarse module in a layer produced files."""
    from agent_core.workspace.io import get_job_dir

    module_results = state.get("module_results", {})
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    for module_name in module_names:
        result = module_results.get(module_name, {})
        module_ok = result.get("status") in {"generated", "repaired"}
        has_files = bool(result.get("generated_files"))
        status = "pass" if module_ok and has_files else "fail"
        checks.append(
            {
                "check": f"{module_name}_layer_completion",
                "status": status,
                "message": (
                    f"module_status={result.get('status')}; "
                    f"generated_files={len(result.get('generated_files', []))}"
                ),
            }
        )
        if status != "pass":
            errors.append(
                f"{module_name} did not pass layer gate "
                f"(module={result.get('status')}, "
                f"generated_files={len(result.get('generated_files', []))})"
            )

    gate = {
        "layer_name": layer_name,
        "status": "pass" if not errors else "fail",
        "modules": module_names,
        "checks": checks,
        "errors": errors,
    }

    gate_dir = get_job_dir(state.get("job_id", "unknown")) / STAGE_CODEGEN / "layer_gates"
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


async def global_integration_agent_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Run the high-privilege global integration agent."""
    from agent_core.g4_codegen.global_integration_agent import (
        run_global_integration_agent,
    )

    job_id = state.get("job_id", "unknown")
    repaired_patch, report = await run_global_integration_agent(
        state.get("proposed_patch", {}),
        job_id=job_id,
        module_results=state.get("module_results", {}),
        module_contracts=state.get("module_contracts", {}),
        module_contexts=state.get("module_contexts", {}),
        interface_contracts=state.get("interface_contracts", {}),
        runtime_failure_context=state.get("runtime_failure_context", {}),
        runtime_repair_rounds=GLOBAL_INTEGRATION_RUNTIME_REPAIR_ROUNDS,
    )
    record_event(
        job_id=job_id,
        event_type="global_integration_agent_result",
        status="passed" if report.get("status") == "passed" else "failed",
        phase="g4_codegen",
        module_name="global_integration_agent",
        summary="Global integration agent completed",
        metrics={
            "issues_fixed": len(report.get("issues_fixed", [])),
            "changed_file_count": len(report.get("changed_files", [])),
        },
        errors=report.get("errors", []),
        details=report,
    )
    return {
        "proposed_patch": repaired_patch,
        "global_integration_agent_report": report,
        "current_node": "global_integration_agent",
        "codegen_errors": list(state.get("codegen_errors", [])) + report.get("errors", []),
    }


async def runtime_execution_audit_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Audit whether the latest runtime gate actually produced trustworthy artifacts."""
    from agent_core.g4_codegen.global_integration_agent import (
        run_global_integration_agent,
    )
    from agent_core.g4_codegen.runtime_execution_auditor import (
        run_runtime_execution_auditor,
        runtime_audit_to_runtime_observation,
    )

    job_id = state.get("job_id", "unknown")
    global_report = state.get("global_integration_agent_report", {})
    audit = await run_runtime_execution_auditor(
        job_id=job_id,
        global_integration_report=global_report,
    )
    record_event(
        job_id=job_id,
        event_type="runtime_execution_audit",
        status="passed" if audit.get("status") == "pass" else "failed",
        phase="g4_codegen",
        module_name="runtime_execution_auditor",
        summary=f"Runtime execution audit {audit.get('status')}",
        metrics={
            "actually_ran": audit.get("actually_ran"),
            "artifact_contract_passed": audit.get("artifact_contract_passed"),
            "data_trustworthy": audit.get("data_trustworthy"),
            "blocking_error_count": len(audit.get("blocking_errors", [])),
        },
        errors=list(audit.get("blocking_errors", [])),
        warnings=list(audit.get("warnings", [])),
        details=audit,
    )

    updates: dict[str, Any] = {
        "runtime_execution_audit": audit,
        "current_node": "runtime_execution_audit",
    }
    if audit.get("status") == "pass":
        return updates

    observation = runtime_audit_to_runtime_observation(audit)
    repair_patch, repair_report = await run_global_integration_agent(
        state.get("proposed_patch", {}),
        job_id=job_id,
        module_results=state.get("module_results", {}),
        module_contracts=state.get("module_contracts", {}),
        module_contexts=state.get("module_contexts", {}),
        interface_contracts=state.get("interface_contracts", {}),
        runtime_failure_context=observation,
        runtime_repair_rounds=RUNTIME_AUDIT_REPAIR_ROUNDS,
        runtime_attempt_offset=len(global_report.get("runtime_gate_attempts", [])),
    )
    second_audit = await run_runtime_execution_auditor(
        job_id=job_id,
        global_integration_report=repair_report,
    )
    second_audit["previous_audit"] = audit
    updates.update(
        {
            "proposed_patch": repair_patch,
            "global_integration_agent_report": repair_report,
            "runtime_execution_audit": second_audit,
            "codegen_errors": (
                list(state.get("codegen_errors", []))
                + repair_report.get("errors", [])
                + list(second_audit.get("blocking_errors", []))
            ),
        }
    )
    return updates


async def physics_quality_review_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Run an LLM physics fidelity review and optionally return fixes to integration."""
    from agent_core.g4_codegen.global_integration_agent import (
        run_global_integration_agent,
    )
    from agent_core.g4_codegen.physics_quality_reviewer import (
        physics_review_to_runtime_observation,
        run_physics_quality_reviewer,
    )

    job_id = state.get("job_id", "unknown")
    proposed_patch = state.get("proposed_patch", {})
    global_report = state.get("global_integration_agent_report", {})

    review = await run_physics_quality_reviewer(
        proposed_patch=proposed_patch,
        g4_model_ir=state.get("g4_model_ir", {}),
        module_contracts=state.get("module_contracts", {}),
        module_contexts=state.get("module_contexts", {}),
        global_integration_report=global_report,
        job_id=job_id,
    )
    record_event(
        job_id=job_id,
        event_type="physics_quality_review",
        status="passed" if review.get("status") == "pass" else "failed",
        phase="g4_codegen",
        module_name="physics_quality_reviewer",
        summary=f"Physics quality review {review.get('status')}",
        metrics={
            "overall_score": review.get("overall_score"),
            "required_fix_count": len(review.get("required_fixes", [])),
        },
        errors=[
            f"{fix.get('target', 'physics_review')}: {fix.get('message', '')}"
            for fix in review.get("required_fixes", [])
            if isinstance(fix, dict)
        ],
        details=review,
    )

    updates: dict[str, Any] = {
        "physics_quality_review": review,
        "current_node": "physics_quality_review",
    }
    if review.get("status") == "pass":
        return updates

    observation = physics_review_to_runtime_observation(review)
    repair_patch, repair_report = await run_global_integration_agent(
        proposed_patch,
        job_id=job_id,
        module_results=state.get("module_results", {}),
        module_contracts=state.get("module_contracts", {}),
        module_contexts=state.get("module_contexts", {}),
        interface_contracts=state.get("interface_contracts", {}),
        runtime_failure_context=observation,
        runtime_repair_rounds=PHYSICS_REVIEW_REPAIR_ROUNDS,
        runtime_attempt_offset=len(global_report.get("runtime_gate_attempts", [])),
    )
    second_review = await run_physics_quality_reviewer(
        proposed_patch=repair_patch,
        g4_model_ir=state.get("g4_model_ir", {}),
        module_contracts=state.get("module_contracts", {}),
        module_contexts=state.get("module_contexts", {}),
        global_integration_report=repair_report,
        job_id=job_id,
    )
    second_review["previous_review"] = review
    updates.update(
        {
            "proposed_patch": repair_patch,
            "global_integration_agent_report": repair_report,
            "physics_quality_review": second_review,
            "codegen_errors": (
                list(state.get("codegen_errors", []))
                + repair_report.get("errors", [])
                + [
                    f"{fix.get('target', 'physics_review')}: {fix.get('message', '')}"
                    for fix in second_review.get("required_fixes", [])
                    if isinstance(fix, dict)
                ]
            ),
        }
    )
    return updates


async def persist_codegen_output_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Persist final codegen output."""
    job_id = state.get("job_id", "unknown")
    proposed_patch = state.get("proposed_patch", {})

    from agent_core.workspace.io import get_job_dir

    job_dir = get_job_dir(job_id)
    codegen_dir = job_dir / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)

    # Save proposed patch to standard location
    patch_path = codegen_dir / "proposed_patch.json"
    patch_path.write_text(json.dumps(proposed_patch, indent=2, ensure_ascii=False))

    # Determine status
    has_code = bool(proposed_patch.get("changed_files"))
    global_integration = state.get("global_integration_agent_report", {})
    runtime_audit = state.get("runtime_execution_audit", {})
    physics_review = state.get("physics_quality_review", {})

    module_results = state.get("module_results", {})
    modules_in_patch = {
        f.get("module_name") for f in proposed_patch.get("changed_files", []) if isinstance(f, dict)
    }
    missing_modules = REQUIRED_MODULES - set(module_results.keys())
    missing_from_patch = REQUIRED_MODULES - modules_in_patch
    failed_modules = [
        module_name
        for module_name in REQUIRED_MODULES
        if module_results.get(module_name, {}).get("status") not in {"generated", "repaired"}
    ]

    new_errors: list[str] = []

    if not has_code:
        status = "failed"
    elif missing_modules or missing_from_patch or failed_modules:
        status = "failed"
    elif global_integration and global_integration.get("status") != "passed":
        status = "failed"
    elif global_integration and global_integration.get("status") == "passed" and not runtime_audit:
        status = "failed"
    elif runtime_audit and runtime_audit.get("status") != "pass":
        status = "failed"
    elif physics_review and physics_review.get("status") != "pass":
        status = "failed"
    else:
        status = "passed"

    # Target directory for generated Geant4 files.
    geant4_dir = job_dir / STAGE_PATCH / GEANT4_PROJECT_DIRNAME
    geant4_dir.mkdir(parents=True, exist_ok=True)
    generated_code_dir = str(geant4_dir)

    if missing_modules:
        new_errors.append(f"Missing module results: {sorted(missing_modules)}")
    if missing_from_patch:
        new_errors.append(f"Missing modules from patch: {sorted(missing_from_patch)}")
    if failed_modules:
        new_errors.append(f"Failed module generation: {sorted(failed_modules)}")
    if global_integration and global_integration.get("status") != "passed":
        new_errors.append("Global integration agent failed")
    if global_integration and global_integration.get("status") == "passed" and not runtime_audit:
        new_errors.append("Runtime execution audit missing")
    if runtime_audit and runtime_audit.get("status") != "pass":
        new_errors.append("Runtime execution auditor rejected the simulation artifacts")
    if physics_review and physics_review.get("status") != "pass":
        new_errors.append("Physics quality reviewer requested revision or failed")

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
            "failed_module_count": len(failed_modules),
            "physics_review_score": physics_review.get("overall_score"),
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
                "failed_modules": sorted(failed_modules),
                "runtime_execution_audit": runtime_audit,
                "physics_quality_review": physics_review,
            },
        )
    return updates
