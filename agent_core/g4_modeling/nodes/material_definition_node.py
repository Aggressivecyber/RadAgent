"""Material definition node — defines materials with NIST/custom classification.

Deterministic node: classifies materials from component tree
and populates material specs. May use LLM for complex custom materials.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import (
    ElementFraction,
    MaterialSpec,
)
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)

# Well-known Geant4 NIST materials
_NIST_MATERIALS: dict[str, tuple[str, float]] = {
    "Si": ("G4_Si", 2.330),
    "Silicon": ("G4_Si", 2.330),
    "Al": ("G4_Al", 2.699),
    "Aluminum": ("G4_Al", 2.699),
    "Cu": ("G4_Cu", 8.960),
    "Copper": ("G4_Cu", 8.960),
    "Ge": ("G4_Ge", 5.323),
    "Germanium": ("G4_Ge", 5.323),
    "Air": ("G4_AIR", 0.001225),
    "Pb": ("G4_Pb", 11.35),
    "Lead": ("G4_Pb", 11.35),
    "W": ("G4_W", 19.30),
    "Tungsten": ("G4_W", 19.30),
    "Fe": ("G4_Fe", 7.874),
    "Iron": ("G4_Fe", 7.874),
    "Water": ("G4_WATER", 1.000),
}

# Well-known custom materials
_CUSTOM_MATERIALS: dict[str, dict[str, Any]] = {
    "SiO2": {
        "name": "Silicon Dioxide",
        "composition": [
            {"element": "Si", "fraction": 0.4675},
            {"element": "O", "fraction": 0.5325},
        ],
        "density_g_cm3": 2.65,
        "state": "solid",
    },
    "SiliconDioxide": {
        "name": "Silicon Dioxide",
        "composition": [
            {"element": "Si", "fraction": 0.4675},
            {"element": "O", "fraction": 0.5325},
        ],
        "density_g_cm3": 2.65,
        "state": "solid",
    },
    "FR4": {
        "name": "FR-4 Epoxy Glass",
        "composition": [
            {"element": "Si", "fraction": 0.216},
            {"element": "O", "fraction": 0.408},
            {"element": "C", "fraction": 0.232},
            {"element": "H", "fraction": 0.018},
            {"element": "Al", "fraction": 0.026},
            {"element": "Ca", "fraction": 0.026},
            {"element": "N", "fraction": 0.036},
            {"element": "Br", "fraction": 0.038},
        ],
        "density_g_cm3": 1.85,
        "state": "solid",
    },
}


async def material_definition_node(state: RadiationAgentState) -> dict[str, Any]:
    """Define all materials needed by the component tree.

    Reads: g4_model_ir (components)
    Writes: g4_model_ir.materials
    Persists: 03_model_ir/material_specs.json
    """
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Collect unique material references from components
    needed_materials: set[str] = set()
    for comp in model_ir.components:
        needed_materials.add(comp.material_id)

    # Define each material
    materials: list[MaterialSpec] = []
    for mat_id in sorted(needed_materials):
        mat = _define_material(mat_id)
        materials.append(mat)

    model_ir.materials = materials

    model_ir.ledger.add_entry(
        node_name="material_definition_node",
        action="create",
        target_id=model_ir.model_ir_id,
        description=f"Defined {len(materials)} materials: {[m.material_id for m in materials]}",
        modified_fields=["materials"],
    )

    # Persist
    if job_id:
        model_ir_dir = get_stage_dir(job_id, "03_model_ir")
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        mat_file = model_ir_dir / "material_specs.json"
        mat_file.write_text(
            json.dumps(
                [m.model_dump(mode="json") for m in materials],
                indent=2,
                ensure_ascii=False,
            )
        )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "material_definition_node",
    }


def _define_material(mat_id: str) -> MaterialSpec:
    """Define a single material from ID, using known databases."""
    # Check NIST first
    if mat_id in _NIST_MATERIALS:
        nist_name, density = _NIST_MATERIALS[mat_id]
        return MaterialSpec(
            material_id=mat_id,
            name=f"{mat_id} (NIST)",
            classification="nist",
            nist_name=nist_name,
            density_g_cm3=density,
            source_evidence=[f"NIST material: {nist_name}"],
        )

    # Check custom materials
    if mat_id in _CUSTOM_MATERIALS:
        info = _CUSTOM_MATERIALS[mat_id]
        return MaterialSpec(
            material_id=mat_id,
            name=info["name"],
            classification="custom",
            composition=[
                ElementFraction(element=e["element"], fraction=e["fraction"])
                for e in info["composition"]
            ],
            density_g_cm3=info["density_g_cm3"],
            state=info.get("state", "solid"),
            source_evidence=[f"Known custom material: {mat_id}"],
        )

    # Unknown material — flag as open issue
    return MaterialSpec(
        material_id=mat_id,
        name=f"Unknown material '{mat_id}'",
        classification="custom",
        composition=[ElementFraction(element="Si", fraction=1.0)],
        density_g_cm3=2.33,  # Silicon default
        source_evidence=[],
        open_issues=[
            f"Material '{mat_id}' not in known database — composition and density need verification"
        ],
    )
