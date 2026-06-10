"""Physics list node — selects physics list with reasoning.

LLM-driven node: selects appropriate physics list based on
particle type, energy range, and scoring requirements.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_modeling.prompts.requirement_capture_prompt import (
    PHYSICS_SELECTION_PROMPT,
)
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def physics_list_node(state: RadiationAgentState) -> dict[str, Any]:
    """Select physics list with reasoning.

    Reads: g4_model_ir (sources, components, materials, evidence)
    Writes: g4_model_ir.physics
    """
    model_ir_dict = state.get("g4_model_ir", {})
    task_spec = state.get("task_spec", {})
    state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Gather context
    particle_type = "proton"
    energy = 10.0
    energy_unit = "MeV"
    source_summary = "proton at 10.0 MeV"
    if model_ir.sources:
        src = model_ir.sources[0]
        particle_type = _particle_summary(model_ir.sources)
        energy = src.energy.value
        energy_unit = src.energy.unit
        source_summary = _source_summary(model_ir.sources)

    material_names = [m.name for m in model_ir.materials]
    scoring_reqs = [s.scoring_type for s in model_ir.scoring]

    physics = _physics_from_user_options(task_spec, particle_type, energy, energy_unit)
    if physics is None:
        # Try LLM-based selection via model gateway
        try:
            from agent_core.models.gateway import get_model_gateway
            from agent_core.models.schemas import ModelTask, ModelTier

            gateway = get_model_gateway()

            evidence_text = ""
            if model_ir.evidence and model_ir.evidence.physics:
                evidence_text = json.dumps(
                    model_ir.evidence.physics[:3],
                    indent=2,
                    ensure_ascii=False,
                )

            prompt = PHYSICS_SELECTION_PROMPT.format(
                particle_type=source_summary,
                energy=energy,
                energy_unit=energy_unit,
                materials=", ".join(material_names) if material_names else "unknown",
                scoring_requirements=", ".join(scoring_reqs) if scoring_reqs else "edep, dose",
                evidence=evidence_text or "No specific physics evidence available",
            )
            result = await gateway.call(
                task=ModelTask.G4_MODELING,
                tier=ModelTier.PRO,
                system_prompt="You are a Geant4 physics list selection expert.",
                user_prompt=prompt,
                response_format="json",
                temperature=0.0,
                max_tokens=2048,
            )

            if result.error:
                raise RuntimeError(result.error)

            raw_content = result.content.strip()
            if "```" in raw_content:
                raw_content = raw_content.split("```")[1]
                if raw_content.startswith("json"):
                    raw_content = raw_content[4:]

            raw = json.loads(raw_content.strip())
            physics = PhysicsSpec.model_validate(raw)

        except Exception as exc:
            logger.warning("LLM physics selection failed: %s", exc)
            physics = _default_physics_for_sources(model_ir.sources)

    model_ir.physics = physics

    model_ir.ledger.add_entry(
        node_name="physics_list_node",
        action="create",
        target_id="physics",
        description=f"Selected physics list: {physics.physics_list}",
        modified_fields=["physics"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "physics_list_node",
    }


def _physics_from_user_options(
    task_spec: dict[str, Any],
    particle_type: str,
    energy: float,
    energy_unit: str,
) -> PhysicsSpec | None:
    options = task_spec.get("physics_options")
    if not isinstance(options, dict):
        return None
    physics_list = str(options.get("physics_list", "")).strip()
    if not physics_list:
        return None
    cuts = _production_cuts_from_options(options)
    hp_neutron = _bool_option(options.get("hp_neutron"))
    return PhysicsSpec(
        physics_list=physics_list,
        selection_reasoning=(
            f"User requested physics list {physics_list} via task_spec.physics_options "
            f"for {particle_type} at {energy} {energy_unit}; preserving explicit user "
            "configuration over automatic selection."
        ),
        em_physics=_optional_string(options.get("em_physics")),
        hadronic=_optional_string(options.get("hadronic")),
        decay=_bool_option(options.get("decay"), default=True),
        cuts=cuts or None,
        hp_neutron=hp_neutron,
        source_evidence=[
            f"task_spec.physics_options: physics_list={physics_list}",
        ],
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_option(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _production_cuts_from_options(options: dict[str, Any]) -> dict[str, float]:
    raw_cuts = options.get("cuts")
    if isinstance(raw_cuts, dict):
        return {
            str(key): float(value)
            for key, value in raw_cuts.items()
            if _is_float_like(value)
        }
    cut_keys = {"gamma", "e-", "e+", "electron", "positron", "proton", "neutron"}
    return {
        str(key): float(value)
        for key, value in options.items()
        if str(key) in cut_keys and _is_float_like(value)
    }


def _is_float_like(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _particle_summary(sources: list[Any]) -> str:
    particles: list[str] = []
    for source in sources:
        particle = str(getattr(source, "particle_type", "")).strip()
        if particle and particle not in particles:
            particles.append(particle)
    return ", ".join(particles) if particles else "proton"


def _source_summary(sources: list[Any]) -> str:
    if not sources:
        return "proton at 10.0 MeV"
    return "; ".join(
        f"{source.source_id}: {source.particle_type} "
        f"{source.energy.value} {source.energy.unit} "
        f"{source.energy.distribution}"
        for source in sources
    )


def _default_physics_for_sources(sources: list[Any]) -> PhysicsSpec:
    """Fallback physics selection that considers every source component."""
    if not sources:
        return _default_physics("proton", 10.0, "MeV")
    particles = [str(source.particle_type).lower() for source in sources]
    summary = _source_summary(sources)
    if any(particle == "neutron" for particle in particles):
        return PhysicsSpec(
            physics_list="QGSP_BIC_HP",
            selection_reasoning=(
                "Composite radiation field includes neutron transport, so "
                f"QGSP_BIC_HP with NeutronHP is selected for all sources: {summary}."
            ),
            hp_neutron=True,
            source_evidence=[
                f"Default composite-source selection for {summary}",
            ],
        )
    hadrons = {"proton", "neutron", "alpha", "deuteron", "triton", "ion"}
    if any(particle in hadrons for particle in particles):
        return PhysicsSpec(
            physics_list="QGSP_BIC",
            selection_reasoning=(
                "Composite radiation field includes hadronic charged-particle "
                f"transport, so QGSP_BIC is selected for sources: {summary}."
            ),
            source_evidence=[
                f"Default composite-source selection for {summary}",
            ],
        )
    src = sources[0]
    return _default_physics(src.particle_type, src.energy.value, src.energy.unit)


def _default_physics(particle_type: str, energy: float, energy_unit: str) -> PhysicsSpec:
    """Provide a reasonable default physics selection."""
    if particle_type.lower() in ("gamma", "e-", "e+", "electron", "positron"):
        if energy < 1.0 and energy_unit == "GeV":
            pl = "Livermore"
            reason = (
                f"Low-energy electromagnetic particle ({particle_type} at "
                f"{energy} {energy_unit}) — Livermore provides accurate "
                f"low-energy EM processes for dosimetry applications"
            )
        else:
            pl = "FTFP_BERT"
            reason = (
                f"Electromagnetic particle ({particle_type} at {energy} "
                f"{energy_unit}) — FTFP_BERT provides comprehensive EM "
                f"and hadronic coverage"
            )
    elif particle_type.lower() in ("neutron",):
        pl = "QGSP_BIC_HP"
        reason = (
            f"Neutron transport at {energy} {energy_unit} — "
            f"QGSP_BIC_HP with NeutronHP provides accurate thermal and "
            f"epithermal neutron transport"
        )
    else:
        pl = "QGSP_BIC"
        reason = (
            f"Proton/hadron at {energy} {energy_unit} — "
            f"QGSP_BIC provides accurate hadronic cascade modeling "
            f"for proton therapy energy ranges"
        )

    return PhysicsSpec(
        physics_list=pl,
        selection_reasoning=reason,
        source_evidence=[f"Default selection for {particle_type} at {energy} {energy_unit}"],
    )
