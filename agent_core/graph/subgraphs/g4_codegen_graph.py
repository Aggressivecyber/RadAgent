"""G4 Codegen Subgraph — generates modular C++ from Geant4 Model IR.

Reads ONLY the Model IR (no user query re-interpretation).
Each codegen node produces exactly one module.
The integration assembler combines all modules into a buildable project.

Flow:
    load_model_ir
    → geometry_builder_plan
    → material_registry_codegen
    → component_geometry_codegen
    → placement_codegen
    → source_codegen
    → physics_macro_codegen
    → sensitive_detector_codegen
    → scoring_codegen
    → output_manager_codegen
    → integration_assembler
    → geometry_validation
    → persist_codegen_output
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.g4_codegen import load_model_ir, persist_codegen_output
from agent_core.g4_codegen.nodes.code_module_planner import code_module_planner
from agent_core.g4_codegen.nodes.integration_assembler import integration_assembler
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState
from agent_core.g4_modeling.codegen import (
    component_geometry_codegen,
    material_registry_codegen,
    output_manager_codegen,
    physics_macro_codegen,
    placement_codegen,
    scoring_codegen,
    sensitive_detector_codegen,
    source_codegen,
)
from agent_core.g4_modeling.nodes import (
    geometry_builder_plan_node,
    geometry_validation_node,
)


def build_g4_codegen_subgraph() -> StateGraph:
    """Build the G4 Codegen Subgraph."""
    graph = StateGraph(G4CodegenSubgraphState)

    # I/O adapters
    graph.add_node("load_model_ir", load_model_ir)
    graph.add_node("persist_codegen_output", persist_codegen_output)

    # Code module planner (determines which modules to generate)
    graph.add_node("code_module_planner", code_module_planner)

    # Builder plan node
    graph.add_node("geometry_builder_plan_node", geometry_builder_plan_node)

    # 8 codegen nodes (each produces one module)
    graph.add_node("material_registry_codegen", material_registry_codegen)
    graph.add_node("component_geometry_codegen", component_geometry_codegen)
    graph.add_node("placement_codegen", placement_codegen)
    graph.add_node("source_codegen", source_codegen)
    graph.add_node("physics_macro_codegen", physics_macro_codegen)
    graph.add_node("sensitive_detector_codegen", sensitive_detector_codegen)
    graph.add_node("scoring_codegen", scoring_codegen)
    graph.add_node("output_manager_codegen", output_manager_codegen)

    # Assembly and validation (using g4_codegen nodes)
    graph.add_node("integration_assembler_node", integration_assembler)
    graph.add_node("geometry_validation_node", geometry_validation_node)

    # Flow
    graph.set_entry_point("load_model_ir")
    graph.add_edge("load_model_ir", "code_module_planner")
    graph.add_edge("code_module_planner", "geometry_builder_plan_node")

    graph.add_edge("geometry_builder_plan_node", "material_registry_codegen")
    graph.add_edge("material_registry_codegen", "component_geometry_codegen")
    graph.add_edge("component_geometry_codegen", "placement_codegen")
    graph.add_edge("placement_codegen", "source_codegen")
    graph.add_edge("source_codegen", "physics_macro_codegen")
    graph.add_edge("physics_macro_codegen", "sensitive_detector_codegen")
    graph.add_edge("sensitive_detector_codegen", "scoring_codegen")
    graph.add_edge("scoring_codegen", "output_manager_codegen")
    graph.add_edge("output_manager_codegen", "integration_assembler_node")

    graph.add_edge("integration_assembler_node", "geometry_validation_node")
    graph.add_edge("geometry_validation_node", "persist_codegen_output")
    graph.add_edge("persist_codegen_output", END)

    return graph
