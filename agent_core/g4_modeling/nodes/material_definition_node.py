"""Material definition node — defines materials with NIST/custom classification.

Deterministic node: classifies materials from component tree
and populates material specs. May use LLM for complex custom materials.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import (
    ElementFraction,
    MaterialSpec,
)
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState
from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_MODEL_IR

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
    "Galactic": ("G4_Galactic", 1e-25),
    "G4_Galactic": ("G4_Galactic", 1e-25),
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
    Persists: model IR stage material_specs.json
    """
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Collect unique material references from components
    needed_materials: set[str] = set()
    for comp in model_ir.components:
        needed_materials.add(comp.material_id)

    material_evidence = _collect_material_evidence(model_ir, needed_materials)

    # Define each material
    materials: list[MaterialSpec] = []
    for mat_id in sorted(needed_materials):
        mat = _define_material(mat_id, source_evidence=material_evidence.get(mat_id, []))
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
        model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
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


def _define_material(
    mat_id: str,
    *,
    source_evidence: list[str] | None = None,
) -> MaterialSpec:
    """Define a single material from ID, using known databases."""
    context_evidence = _dedupe(source_evidence or [])

    # Check NIST first
    nist_material = _resolve_nist_material(mat_id)
    if nist_material is not None:
        nist_name, density = nist_material
        return MaterialSpec(
            material_id=mat_id,
            name=f"{nist_name} (NIST)",
            classification="nist",
            nist_name=nist_name,
            density_g_cm3=density,
            source_evidence=_dedupe(
                [f"nist:{nist_name}"] + context_evidence
            ),
        )

    # Check custom materials
    custom_material = _resolve_custom_material(mat_id)
    if custom_material is not None:
        custom_key, info = custom_material
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
            source_evidence=_dedupe(
                [f"known_custom_material:{custom_key}"] + context_evidence
            ),
        )

    # Unknown material — flag as open issue
    return MaterialSpec(
        material_id=mat_id,
        name=f"Unknown material '{mat_id}'",
        classification="custom",
        composition=[ElementFraction(element="Si", fraction=1.0)],
        density_g_cm3=2.33,
        source_evidence=context_evidence or [f"material_reference:{mat_id}"],
        open_issues=[
            f"Material '{mat_id}' not in known database — composition and density need verification"
        ],
    )


def _collect_material_evidence(
    model_ir: G4ModelIR,
    needed_materials: set[str],
) -> dict[str, list[str]]:
    evidence_by_material: dict[str, list[str]] = {}
    for mat_id in needed_materials:
        evidence: list[str] = []
        for comp in model_ir.components:
            if not _material_names_equivalent(comp.material_id, mat_id):
                continue
            evidence.append(f"component:{comp.component_id}:material_id={comp.material_id}")
            evidence.extend(
                f"component:{comp.component_id}:{ref}"
                for ref in comp.source_evidence
                if str(ref).strip()
            )

        if model_ir.evidence is not None:
            for item in model_ir.evidence.materials:
                if _evidence_mentions_material(item, mat_id):
                    evidence.append(_format_evidence_ref(item))

        evidence_by_material[mat_id] = _dedupe(evidence)
    return evidence_by_material


def _resolve_nist_material(mat_id: str) -> tuple[str, float] | None:
    return _NIST_LOOKUP.get(_material_key(mat_id))


def _resolve_custom_material(mat_id: str) -> tuple[str, dict[str, Any]] | None:
    return _CUSTOM_LOOKUP.get(_material_key(mat_id))


def _material_names_equivalent(left: str, right: str) -> bool:
    if _material_key(left) == _material_key(right):
        return True
    left_nist = _resolve_nist_material(left)
    right_nist = _resolve_nist_material(right)
    if left_nist and right_nist and left_nist[0] == right_nist[0]:
        return True
    left_custom = _resolve_custom_material(left)
    right_custom = _resolve_custom_material(right)
    return bool(left_custom and right_custom and left_custom[0] == right_custom[0])


def _evidence_mentions_material(item: dict[str, Any], mat_id: str) -> bool:
    text = _material_key(" ".join(str(value) for value in item.values()))
    if not text:
        return False
    return any(key and key in text for key in _candidate_material_keys(mat_id))


def _candidate_material_keys(mat_id: str) -> set[str]:
    keys = {_material_key(mat_id)}
    nist_material = _resolve_nist_material(mat_id)
    if nist_material is not None:
        nist_name = nist_material[0]
        keys.add(_material_key(nist_name))
        keys.update(
            _material_key(alias)
            for alias, candidate in _NIST_MATERIALS.items()
            if candidate[0] == nist_name
        )
    custom_material = _resolve_custom_material(mat_id)
    if custom_material is not None:
        custom_key, _ = custom_material
        keys.update(
            _material_key(alias)
            for alias in _CUSTOM_MATERIALS
            if _material_key(alias) == _material_key(custom_key)
        )
    return {key for key in keys if key}


def _format_evidence_ref(item: dict[str, Any]) -> str:
    source_type = str(item.get("source_type") or "material_evidence")
    source = str(item.get("source") or item.get("title") or "unknown_source")
    dimension = str(item.get("dimension") or "materials")
    return f"{source_type}:{source}:{dimension}"


def _material_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        clean = str(value).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped


def _build_nist_lookup() -> dict[str, tuple[str, float]]:
    lookup: dict[str, tuple[str, float]] = {}
    for alias, material in _NIST_MATERIALS.items():
        lookup[_material_key(alias)] = material
        lookup[_material_key(material[0])] = material
    return lookup


def _build_custom_lookup() -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        _material_key(alias): (alias, material)
        for alias, material in _CUSTOM_MATERIALS.items()
    }


_NIST_LOOKUP = _build_nist_lookup()
_CUSTOM_LOOKUP = _build_custom_lookup()
