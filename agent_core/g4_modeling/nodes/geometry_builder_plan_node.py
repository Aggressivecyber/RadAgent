"""Geometry builder plan node — generates CodeGenerationPlan from G4ModelIR.

Deterministic node: translates the validated model IR into a structured
code generation plan that codegen nodes will follow.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState as RadiationAgentState
from agent_core.g4_modeling.schemas.code_module_plan import (
    CodeGenerationPlan,
    CodeModulePlan,
)
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

logger = logging.getLogger(__name__)


async def geometry_builder_plan_node(state: RadiationAgentState) -> dict[str, Any]:
    """Generate CodeGenerationPlan from validated G4ModelIR.

    Reads: g4_model_ir
    Writes: g4_model_ir (adds code_gen_plan to ledger), persists plan
    """
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Collect unique material IDs
    all_material_ids = sorted({c.material_id for c in model_ir.components})

    # Build module list in dependency order
    modules: list[CodeModulePlan] = []

    # 1. Material registry (no dependencies)
    modules.append(CodeModulePlan(
        module_name="MaterialRegistry",
        module_type="material_registry",
        source_files=["MaterialRegistry.cc"],
        header_files=["MaterialRegistry.hh"],
        config_files=["material_config.json"],
        depends_on=[],
        linked_component_ids=[],
        linked_material_ids=all_material_ids,
    ))

    # 2. Per-component geometry builders
    for comp in model_ir.components:
        module_name = _to_class_name(comp.component_id) + "Builder"
        modules.append(CodeModulePlan(
            module_name=module_name,
            module_type="component_geometry",
            source_files=[f"{module_name}.cc"],
            header_files=[f"{module_name}.hh"],
            depends_on=["MaterialRegistry"],
            linked_component_ids=[comp.component_id],
            linked_material_ids=[comp.material_id],
        ))

    # 3. Placement (depends on all geometry builders)
    geometry_module_names = [
        m.module_name for m in modules if m.module_type == "component_geometry"
    ]
    modules.append(CodeModulePlan(
        module_name="PlacementManager",
        module_type="placement",
        source_files=["PlacementManager.cc"],
        header_files=["PlacementManager.hh"],
        depends_on=geometry_module_names,
        linked_component_ids=[c.component_id for c in model_ir.components],
        linked_material_ids=[],
    ))

    # 4. Source
    modules.append(CodeModulePlan(
        module_name="PrimaryGeneratorAction",
        module_type="source",
        source_files=["PrimaryGeneratorAction.cc"],
        header_files=["PrimaryGeneratorAction.hh"],
        config_files=["source.mac"],
        depends_on=[],
        linked_component_ids=[],
        linked_material_ids=[],
    ))

    # 5. Physics macro
    modules.append(CodeModulePlan(
        module_name="PhysicsConfig",
        module_type="physics_macro",
        config_files=["physics_list.mac", "physics_config.json"],
        depends_on=[],
        linked_component_ids=[],
        linked_material_ids=[],
    ))

    # 6. Sensitive detectors (depends on geometry builders)
    sd_comp_ids: list[str] = []
    for sd in model_ir.sensitive_detectors:
        sd_comp_ids.extend(sd.linked_component_ids)

    modules.append(CodeModulePlan(
        module_name="SensitiveDetectorManager",
        module_type="sensitive_detector",
        source_files=["SensitiveDetectorManager.cc", "Hit.cc"],
        header_files=["SensitiveDetectorManager.hh", "Hit.hh"],
        depends_on=geometry_module_names,
        linked_component_ids=sorted(set(sd_comp_ids)),
        linked_material_ids=[],
    ))

    # 7. Scoring manager (depends on SDs)
    modules.append(CodeModulePlan(
        module_name="ScoringManager",
        module_type="scoring",
        source_files=["ScoringManager.cc"],
        header_files=["ScoringManager.hh"],
        depends_on=["SensitiveDetectorManager"],
        linked_component_ids=[],
        linked_material_ids=[],
    ))

    # 8. Output manager
    modules.append(CodeModulePlan(
        module_name="OutputManager",
        module_type="output_manager",
        source_files=["OutputManager.cc"],
        header_files=["OutputManager.hh"],
        depends_on=["ScoringManager"],
        linked_component_ids=[],
        linked_material_ids=[],
    ))

    # Compute assembly order (topological sort by dependencies)
    assembly_order = _topological_sort(modules)

    plan = CodeGenerationPlan(
        plan_id=f"plan_{model_ir.model_ir_id}",
        job_id=job_id or model_ir.job_id,
        modules=modules,
        assembly_order=assembly_order,
        total_source_files=sum(len(m.source_files) for m in modules),
        total_header_files=sum(len(m.header_files) for m in modules),
    )

    model_ir.ledger.add_entry(
        node_name="geometry_builder_plan_node",
        action="create",
        target_id=plan.plan_id,
        description=f"Generated code plan: {len(modules)} modules, "
        f"{plan.total_source_files} sources, {plan.total_header_files} headers",
        modified_fields=[],
    )

    # Persist
    if job_id:
        model_ir_dir = get_stage_dir(job_id, "03_model_ir")
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        plan_file = model_ir_dir / "code_generation_plan.json"
        plan_file.write_text(json.dumps(
            plan.model_dump(mode="json"), indent=2, ensure_ascii=False,
        ))

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "code_modules": [m.model_dump(mode="json") for m in modules],
        "current_node": "geometry_builder_plan_node",
    }


def _to_class_name(component_id: str) -> str:
    """Convert component_id to PascalCase class name prefix."""
    return "".join(
        word.capitalize() for word in component_id.replace("-", "_").split("_")
    )


def _topological_sort(modules: list[CodeModulePlan]) -> list[str]:
    """Sort module names by dependency order (Kahn's algorithm)."""
    name_set = {m.module_name for m in modules}
    in_degree: dict[str, int] = {m.module_name: 0 for m in modules}
    graph: dict[str, list[str]] = {m.module_name: [] for m in modules}

    for m in modules:
        for dep in m.depends_on:
            if dep in name_set:
                graph[dep].append(m.module_name)
                in_degree[m.module_name] += 1

    queue = [n for n, d in in_degree.items() if d == 0]
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If cycle exists, append remaining nodes
    for n in in_degree:
        if n not in result:
            result.append(n)

    return result
