"""Source definition node — configures particle source from requirements.

Deterministic node: configures particle gun or GPS based on task spec.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def source_definition_node(state: RadiationAgentState) -> dict[str, Any]:
    """Configure particle source from task spec and evidence.

    Reads: g4_model_ir (components, coordinate_system), task_spec
    Writes: g4_model_ir.sources
    """
    model_ir_dict = state.get("g4_model_ir", {})
    task_spec = state.get("task_spec", {})

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
    from agent_core.g4_modeling.schemas.source_spec import (
        BeamProfile,
        EnergySpec,
        SourceSpec,
    )

    model_ir = G4ModelIR.model_validate(model_ir_dict)
    z_offset = _default_source_z_offset(model_ir)
    particles = _source_particles(task_spec)

    sources = [
        _source_from_particle(
            particle,
            index=index,
            default_z_offset=z_offset,
            EnergySpec=EnergySpec,
            BeamProfile=BeamProfile,
            SourceSpec=SourceSpec,
        )
        for index, particle in enumerate(particles)
    ]

    model_ir.sources = sources

    model_ir.ledger.add_entry(
        node_name="source_definition_node",
        action="create",
        target_id="sources",
        description=(
            f"Configured {len(sources)} source(s): "
            + ", ".join(
                f"{source.source_id}:{source.particle_type} "
                f"{source.energy.value} {source.energy.unit} "
                f"{source.energy.distribution}/{source.generator_type}"
                for source in sources
            )
        ),
        modified_fields=["sources"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "source_definition_node",
    }


def _source_particles(task_spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return source component dicts, preserving backwards-compatible particle input."""
    composite = task_spec.get("particles")
    if isinstance(composite, list) and composite:
        return [item for item in composite if isinstance(item, dict)] or [{}]
    particle = task_spec.get("particle")
    if isinstance(particle, dict) and particle:
        return [particle]
    return [{}]


def _default_source_z_offset(model_ir: Any) -> float:
    """Place auto-positioned sources outside the positive-z target extent."""
    z_offset = -500.0
    for comp in model_ir.components:
        if comp.component_type != "world" and comp.mother_volume:
            dims = comp.dimensions
            dz = dims.get("dz", 0)
            pos_z = comp.placement.position[2]
            top_edge = pos_z + dz
            if top_edge > z_offset:
                z_offset = -(top_edge + 500.0)
    return z_offset


def _source_from_particle(
    particle: dict[str, Any],
    *,
    index: int,
    default_z_offset: float,
    EnergySpec: Any,
    BeamProfile: Any,
    SourceSpec: Any,
) -> Any:
    """Build one SourceSpec from a task particle/source component."""
    particle_type = particle.get("type", "proton")
    energy_value = particle.get("energy_MeV", 10.0)
    energy_unit = particle.get("energy_unit", "MeV")
    energy_distribution = particle.get("energy_distribution", "mono")
    energy_sigma = particle.get("energy_sigma")
    spectrum_file = particle.get("spectrum_file")
    direction = particle.get("direction", [0, 0, 1])
    events = particle.get("events", 1000)

    user_position = particle.get("position")
    position = user_position if user_position is not None else [0.0, 0.0, default_z_offset]

    angular_distribution = _angular_distribution(particle.get("angular_distribution", "mono"))
    complex_source = (
        energy_distribution != "mono"
        or particle.get("sigma_position_um") is not None
        or particle.get("sigma_direction_rad") is not None
        or angular_distribution != "mono"
    )
    requested_generator = particle.get("generator_type")
    if requested_generator == "gps" or complex_source:
        generator_type = "gps"
    elif requested_generator == "gun":
        generator_type = "gun"
    else:
        generator_type = "gun"

    surface_shape = _surface_shape(particle.get("surface_shape", "point"))
    source_id = str(
        particle.get("source_id")
        or ("primary_source" if index == 0 else f"source_{index + 1}")
    )

    energy = EnergySpec(
        value=energy_value,
        unit=energy_unit,
        distribution=energy_distribution,
        sigma=energy_sigma,
        spectrum_file=spectrum_file,
    )

    beam = BeamProfile(
        position=position,
        direction=direction,
        sigma_position_um=particle.get("sigma_position_um"),
        sigma_direction_rad=particle.get("sigma_direction_rad"),
        angular_distribution=angular_distribution,
        angular_spectrum_file=particle.get("angular_spectrum_file"),
        surface_shape=surface_shape,
        surface_size=particle.get("surface_size"),
    )

    return SourceSpec(
        source_id=source_id,
        particle_type=particle_type,
        energy=energy,
        beam=beam,
        generator_type=generator_type,
        events=events,
        relative_weight=particle.get("relative_weight"),
        source_evidence=[
            f"task_spec.particles[{index}]: "
            f"source_id={source_id}, particle={particle_type}, "
            f"energy={energy_value} {energy_unit}, distribution={energy_distribution}, "
            f"generator={generator_type}, position={position}, direction={direction}, "
            f"angular_distribution={angular_distribution}"
        ],
    )


def _surface_shape(value: Any) -> Literal["circle", "rectangle", "point"]:
    return value if value in {"circle", "rectangle", "point"} else "point"


def _angular_distribution(value: Any) -> Literal[
    "mono",
    "gaussian",
    "isotropic",
    "cosine",
    "custom",
]:
    return (
        value
        if value in {"mono", "gaussian", "isotropic", "cosine", "custom"}
        else "mono"
    )
