"""Scoring design node — creates scoring specs from model IR.

Deterministic node: defines voxel/region scoring based on sensitive
detectors and component roles.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def scoring_design_node(state: RadiationAgentState) -> dict[str, Any]:
    """Design scoring configuration for the model.

    Reads: g4_model_ir (components, sensitive_detectors, coordinate_system)
    Writes: g4_model_ir.scoring
    """
    model_ir_dict = state.get("g4_model_ir", {})
    task_spec = state.get("task_spec", {})

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
    from agent_core.g4_modeling.schemas.scoring_spec import (
        RegionScore,
        ScoringSpec,
        VoxelGrid,
    )

    model_ir = G4ModelIR.model_validate(model_ir_dict)
    requested = _requested_scoring_outputs(task_spec, model_ir.evidence)

    scoring: list[ScoringSpec] = []

    # 1. Per-sensitive-region scoring (edep + dose)
    for sd in model_ir.sensitive_detectors:
        for comp_id in sd.linked_component_ids:
            comp = model_ir.component_by_id(comp_id)
            if comp is None:
                continue

            # Region scoring for edep
            edep_scoring = ScoringSpec(
                scoring_id=f"{comp_id}_edep",
                scoring_type="region",
                quantities=["edep_MeV"],
                region_scores=[
                    RegionScore(
                        region_component_id=comp_id,
                        quantity="edep_MeV",
                    )
                ],
                output_format="csv",
                source_evidence=[
                    f"Auto-generated: region edep scoring for {comp_id}",
                ],
            )
            scoring.append(edep_scoring)

            # Region scoring for dose when requested or implied by component roles.
            if _component_requests_dose(comp) or requested["dose_region"] or requested["dose_3d"]:
                dose_scoring = ScoringSpec(
                    scoring_id=f"{comp_id}_dose",
                    scoring_type="region",
                    quantities=["dose_Gy"],
                    region_scores=[
                        RegionScore(
                            region_component_id=comp_id,
                            quantity="dose_Gy",
                        )
                    ],
                    output_format="csv",
                    source_evidence=[
                        f"Auto-generated: region dose scoring for {comp_id}",
                    ],
                )
                scoring.append(dose_scoring)

    # 2. Voxel scoring for requested 3D maps. Requests can come from normalized
    # task outputs, requirement evidence, or component roles.
    for comp in model_ir.components:
        wants_voxel_edep = _component_requests_voxel_edep(comp) or (
            requested["edep_3d"] and _is_scoring_target(comp)
        )
        wants_voxel_dose = _component_requests_voxel_dose(comp) or (
            requested["dose_3d"] and _is_scoring_target(comp)
        )
        if not wants_voxel_edep and not wants_voxel_dose:
            continue

        voxel_size = _voxel_size_for_component(comp)
        if wants_voxel_dose:
            voxel_scoring = ScoringSpec(
                scoring_id=f"{comp.component_id}_voxel_dose",
                scoring_type="voxel",
                quantities=["dose_Gy"],
                voxel_grid=VoxelGrid(
                    target_component_id=comp.component_id,
                    voxel_size=voxel_size,
                ),
                output_format="csv",
                source_evidence=[
                    f"Auto-generated: voxel dose map for {comp.component_id}, "
                    f"voxel_size={voxel_size} um",
                ],
            )
            scoring.append(voxel_scoring)
        if wants_voxel_edep:
            voxel_scoring = ScoringSpec(
                scoring_id=f"{comp.component_id}_voxel_edep",
                scoring_type="voxel",
                quantities=["edep_MeV"],
                voxel_grid=VoxelGrid(
                    target_component_id=comp.component_id,
                    voxel_size=voxel_size,
                ),
                output_format="csv",
                source_evidence=[
                    f"Auto-generated: voxel edep map for {comp.component_id}, "
                    f"voxel_size={voxel_size} um",
                ],
            )
            scoring.append(voxel_scoring)

    # 3. Event table scoring (if any sensitive detectors exist)
    if model_ir.sensitive_detectors:
        all_sensitive_ids: list[str] = []
        for sd in model_ir.sensitive_detectors:
            all_sensitive_ids.extend(sd.linked_component_ids)

        event_table = ScoringSpec(
            scoring_id="event_table",
            scoring_type="region",
            quantities=["edep_MeV", "event_id", "track_id"],
            region_scores=[
                RegionScore(
                    region_component_id=cid,
                    quantity="edep_MeV",
                )
                for cid in all_sensitive_ids
            ],
            output_format="csv",
            source_evidence=[
                "Auto-generated: event table for all sensitive components",
            ],
        )
        scoring.append(event_table)

    model_ir.scoring = scoring

    model_ir.ledger.add_entry(
        node_name="scoring_design_node",
        action="create",
        target_id="scoring",
        description=f"Created {len(scoring)} scoring configurations: "
        f"{[s.scoring_id for s in scoring]}",
        modified_fields=["scoring"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "scoring_design_node",
    }


def _voxel_size_for_component(comp: Any) -> list[float]:
    dims = comp.dimensions
    dx = dims.get("dx", 100.0)
    dy = dims.get("dy", 100.0)
    dz = dims.get("dz", 100.0)

    # Voxel size: about 1/10 of each dimension, at least 1 um.
    return [
        max(1.0, round(dx / 10.0, 1)),
        max(1.0, round(dy / 10.0, 1)),
        max(1.0, round(dz / 10.0, 1)),
    ]


def _requested_scoring_outputs(task_spec: dict[str, Any], evidence: Any) -> dict[str, bool]:
    outputs = _collect_output_tokens(task_spec, evidence)
    return {
        "edep_region": _has_any(
            outputs,
            {
                "edep",
                "energy_deposition",
                "energy_deposition_per_event",
                "total_energy_deposition",
            },
        ),
        "edep_3d": _has_any(
            outputs,
            {
                "edep_3d",
                "3d_edep",
                "3d_edep_map",
                "edep_map",
                "voxel_edep",
                "energy_deposition_map",
                "energy_deposition_3d_map",
                "3d_energy_deposition",
            },
        ),
        "dose_region": _has_any(outputs, {"dose", "dose_gy", "dose_region"}),
        "dose_3d": _has_any(
            outputs,
            {
                "dose_3d",
                "3d_dose",
                "3d_dose_map",
                "dose_map",
                "voxel_dose",
                "dose_distribution",
                "dose_distribution_3d",
                "3d_dose_distribution",
            },
        ),
        "event_table": _has_any(
            outputs,
            {"event_table", "event_data", "events", "per_event", "energy_deposition_per_event"},
        ),
    }


def _collect_output_tokens(task_spec: dict[str, Any], evidence: Any) -> set[str]:
    raw_values: list[Any] = []
    outputs = task_spec.get("outputs") if isinstance(task_spec, dict) else None
    if isinstance(outputs, list):
        raw_values.extend(outputs)

    scoring_evidence = getattr(evidence, "scoring", None)
    for item in scoring_evidence or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                raw_values.append(text)
            else:
                raw_values.append(decoded)
        else:
            raw_values.append(text)

    tokens: set[str] = set()
    for value in raw_values:
        for token in _flatten_output_value(value):
            normalized = _normalize_output_token(token)
            if normalized:
                tokens.add(normalized)
    return tokens


def _flatten_output_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_flatten_output_value(item))
        return tokens
    if isinstance(value, dict):
        tokens = []
        for key, item in value.items():
            tokens.append(str(key))
            tokens.extend(_flatten_output_value(item))
        return tokens
    return [str(value)]


def _normalize_output_token(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
        .replace(".csv", "")
    )


def _has_any(outputs: set[str], aliases: set[str]) -> bool:
    return any(alias in outputs for alias in aliases)


def _role_text(comp: Any) -> str:
    return " ".join(str(role).lower() for role in getattr(comp, "roles", []) or [])


def _component_requests_dose(comp: Any) -> bool:
    return "dose" in _role_text(comp)


def _component_requests_voxel_edep(comp: Any) -> bool:
    role_text = _role_text(comp)
    return "3d_edep" in role_text or "voxel_edep" in role_text


def _component_requests_voxel_dose(comp: Any) -> bool:
    role_text = _role_text(comp)
    return "3d_dose" in role_text or "voxel_dose" in role_text


def _is_scoring_target(comp: Any) -> bool:
    if getattr(comp, "component_type", "") == "world":
        return False
    if bool(getattr(comp, "sensitive", False)):
        return True
    role_text = _role_text(comp)
    return any(token in role_text for token in ("scoring", "detector", "target", "sensitive"))
