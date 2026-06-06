"""Simulation Intermediate Representation (IR) schema.

Internal representation of a full simulation configuration derived from
a TaskSpec.  Each sub-config corresponds to one simulation stage (Geant4,
TCAD, SPICE) with mapping metadata linking adjacent stages.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# -- Stage configurations ---------------------------------------------------

class G4Config(BaseModel):
    """Geant4 simulation parameters.

    Attributes:
        geometry: Material, dimensions, world_size.
        particle_source: Particle type, energy, direction, events.
        physics_list: Reference physics list (e.g. FTFP_BERT).
        scoring: Quantities to score, voxel size, output format.
        run_config: Thread count and output directory.
    """

    geometry: dict = Field(...)
    particle_source: dict = Field(...)
    physics_list: str = Field(default="FTFP_BERT")
    scoring: dict = Field(...)
    run_config: dict = Field(...)


class TCADConfig(BaseModel):
    """TCAD Sentaurus device simulation parameters (MVP-1 stub).

    All fields optional to allow incremental population as the TCAD
    integration matures.
    """

    device_structure: dict | None = None
    mesh_config: dict | None = None
    physics_models: dict | None = None
    defect_model: dict | None = None
    bias_conditions: dict | None = None
    simulation_type: str | None = None


class SPICEConfig(BaseModel):
    """SPICE circuit simulation parameters (stub).

    To be expanded when the circuit-level integration stage is implemented.
    """

    circuit_type: str | None = None
    models: list[dict] | None = None
    stimulus: list[dict] | None = None
    analysis: dict | None = None


# -- Inter-stage mapping ----------------------------------------------------

class MappingChain(BaseModel):
    """Mapping metadata connecting adjacent simulation stages.

    Attributes:
        g4_to_tcad: Method/params for Geant4 output -> TCAD defect profiles.
        tcad_to_spice: Method/params for TCAD IV curves -> SPICE models.
    """

    g4_to_tcad: dict | None = None
    tcad_to_spice: dict | None = None


# -- Top-level IR -----------------------------------------------------------

class SimulationIR(BaseModel):
    """Simulation Intermediate Representation.

    The canonical internal model that all pipeline stages read from and
    write to.  Produced by expanding a TaskSpec through research and
    parameter resolution.
    """

    simulation_id: str = Field(..., description="Unique simulation identifier.")
    task_spec_hash: str = Field(..., description="SHA-256 of originating TaskSpec.")
    g4_config: G4Config | None = None
    tcad_config: TCADConfig | None = None
    spice_config: SPICEConfig | None = None
    mapping_chain: MappingChain | None = None
    unit_registry: dict[str, str] = Field(
        default_factory=dict, description="Quantity name -> unit string.",
    )


# -- Validation helper -------------------------------------------------------

def validate_simulation_ir(
    data: dict,
) -> tuple[SimulationIR | None, list[str]]:
    """Validate a raw dict against the SimulationIR schema.

    Returns:
        (validated_model | None, list_of_error_strings).
    """
    try:
        return SimulationIR.model_validate(data), []
    except Exception as exc:
        errors: list[str] = []
        if hasattr(exc, "errors"):
            for e in exc.errors():
                loc = ".".join(str(p) for p in e.get("loc", []))
                errors.append(f"{loc}: {e.get('msg', str(e))}")
        else:
            errors.append(str(exc))
        return None, errors
