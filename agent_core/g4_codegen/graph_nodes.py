"""G4 Codegen graph nodes — orchestrates the module agent pipeline.

This module contains the node functions used by g4_codegen_graph.py.
Each node is a thin wrapper that calls the appropriate module.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState

logger = logging.getLogger(__name__)


# ── Planning nodes ───────────────────────────────────────────────────


async def build_codegen_plan_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Build overall codegen plan from G4ModelIR."""
    from agent_core.g4_codegen.planners.codegen_plan_builder import build_codegen_plan

    g4_model_ir = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "unknown")
    run_mode = state.get("run_mode", "dev")

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
    run_mode = state.get("run_mode", "dev")

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

    # P0-14: Persist effective context (with summaries) to disk
    from agent_core.config.workspace import get_job_dir as _get_job_dir
    _ctx_dir = _get_job_dir(job_id) / "06_codegen" / "module_contexts"
    _ctx_dir.mkdir(parents=True, exist_ok=True)
    _eff_path = _ctx_dir / f"{module_name}.effective.json"
    _eff_path.write_text(json.dumps(ctx, indent=2, ensure_ascii=False))

    # Import and run the appropriate agent
    agent_fn = _get_agent_function(module_name)
    result = await agent_fn(ctx)

    # Save result
    save_module_result(result, job_id)

    # Update state
    module_results = dict(state.get("module_results", {}))
    module_results[module_name] = result.model_dump()

    return {
        "module_results": module_results,
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
    return re.findall(r'\bclass\s+(\w+)', content)


def _extract_public_methods(content: str) -> list[str]:
    """Extract public method names from C++ content."""
    import re
    # Match methods after 'public:' keyword
    return re.findall(r'\bpublic:\s*(?:.*?)?\b(\w+)\s*\(', content, re.DOTALL)




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

    P0-10: Passes module_status to hard gate so it can reject
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

    gate_results = dict(state.get("module_gate_results", {}))
    if module_name not in gate_results:
        gate_results[module_name] = {}
    gate_results[module_name]["hard"] = gate_result.model_dump()

    # Persist
    from agent_core.config.workspace import get_job_dir
    job_id = state.get("job_id", "unknown")
    gate_dir = get_job_dir(job_id) / "06_codegen" / "module_gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    gate_path = gate_dir / f"{module_name}_hard_gate.json"
    gate_path.write_text(json.dumps(gate_result.model_dump(), indent=2))

    return {
        "module_gate_results": gate_results,
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
        if module_name not in gate_results:
            gate_results[module_name] = {}
        gate_results[module_name]["llm"] = {
            "module_name": module_name,
            "gate_type": "llm",
            "status": "skipped",
            "errors": ["Hard gate failed — LLM gate skipped"],
        }
        return {
            "module_gate_results": gate_results,
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

    if module_name not in gate_results:
        gate_results[module_name] = {}
    gate_results[module_name]["llm"] = gate_result.model_dump()

    # Persist
    from agent_core.config.workspace import get_job_dir
    job_id = state.get("job_id", "unknown")
    gate_dir = get_job_dir(job_id) / "06_codegen" / "module_gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    gate_path = gate_dir / f"{module_name}_llm_gate.json"
    gate_path.write_text(json.dumps(gate_result.model_dump(), indent=2))

    return {
        "module_gate_results": gate_results,
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
    needs_repair = (
        hard_gate.get("status") == "fail"
        or llm_gate.get("status") == "fail"
    )

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

    repaired = await repair_module(module_name, ctx, original_result, gate)
    save_repair_summary(module_name, repaired, state.get("job_id", "unknown"))

    # Update results
    updated_results = dict(module_results)
    updated_results[module_name] = repaired.model_dump()

    repair_results = dict(state.get("module_repair_results", {}))
    repair_results[module_name] = {
        "status": repaired.status,
        "attempts": len(repaired.repair_attempts),
    }

    # P0-14/P0-15: If repair failed, mark codegen as failed
    updates: dict[str, Any] = {
        "module_results": updated_results,
        "module_repair_results": repair_results,
        "current_node": f"repair_{module_name}",
    }

    if repaired.status == "failed":
        updates["g4_codegen_status"] = "failed"
        codegen_errors = list(state.get("codegen_errors", []))
        codegen_errors.append(
            f"Module '{module_name}' repair failed after "
            f"{len(repaired.repair_attempts)} attempts: "
            + "; ".join(repaired.errors[:3])
        )
        updates["codegen_errors"] = codegen_errors
        logger.warning(
            "Module %s repair failed — terminating codegen for this module",
            module_name,
        )

    return updates


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


async def static_semantic_scanner_node(
    state: G4CodegenSubgraphState,
) -> dict[str, Any]:
    """Run static semantic scan on proposed_patch."""
    from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code

    proposed_patch = state.get("proposed_patch", {})
    job_id = state.get("job_id", "unknown")

    scan = scan_generated_code(proposed_patch, job_id)
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

    gate = await run_cross_file_llm_gate(proposed_patch, module_gate_results, job_id)
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

    # Check static semantic scan status
    static_scan = state.get("static_semantic_scan", {})

    if not has_code:
        status = "failed"
    elif static_scan.get("status") == "fail":
        status = "failed"
    elif cross_hard.get("status") == "fail":
        status = "failed"
    elif cross_llm.get("status") == "fail":
        status = "failed"
    else:
        status = "passed"

    # Target directory for generated Geant4 files is 08_geant4
    geant4_dir = job_dir / "08_geant4"
    geant4_dir.mkdir(parents=True, exist_ok=True)
    generated_code_dir = str(geant4_dir)

    return {
        "proposed_patch_path": str(patch_path),
        "generated_code_dir": generated_code_dir,
        "g4_codegen_status": status,
        "current_node": "persist_codegen_output",
    }
