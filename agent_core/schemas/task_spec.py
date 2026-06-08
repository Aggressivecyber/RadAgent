"""TaskSpec schema for structured simulation task specification."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class SimulationScope(StrEnum):
    """Supported simulation domains."""

    GEANT4 = "geant4"
    TCAD = "tcad"
    SPICE = "spice"


class ParticleSpec(BaseModel):
    """Particle source specification."""

    type: str = Field(description="Particle type, e.g. proton, neutron, gamma")
    energy_MeV: float = Field(gt=0, description="Kinetic energy in MeV")  # noqa: N815
    direction: list[float] = Field(
        min_length=3,
        max_length=3,
        description="Unit direction vector [x, y, z]",
    )
    events: int = Field(default=1000, gt=0, description="Number of primary events")


class TargetSpec(BaseModel):
    """Irradiation target specification."""

    material: str = Field(description="Target material, e.g. Silicon, SiO2")
    size_um: list[float] = Field(
        min_length=3,
        max_length=3,
        description="Dimensions [x, y, z] in um",
    )
    geometry_type: str = Field(
        default="box",
        description="Geometry primitive: box, sphere, cylinder",
    )


class DeviceSpec(BaseModel):
    """Semiconductor device specification."""

    device_type: str = Field(description="Device type, e.g. NMOS, PMOS, FinFET")
    temperature_K: float = Field(  # noqa: N815
        default=300.0,
        gt=0,
        description="Operating temperature in Kelvin",
    )
    bias_condition: str = Field(default="reverse_bias", description="Bias condition")


class CircuitSpec(BaseModel):
    """Circuit-level specification."""

    circuit_type: str = Field(description="Circuit type, e.g. inverter, SRAM_cell")
    supply_voltage_V: float = Field(  # noqa: N815
        default=1.8,
        gt=0,
        description="Supply voltage in volts",
    )


_VALID_OUTPUTS: frozenset[str] = frozenset(
    {
        "dose_map",
        "tid_profile",
        "energy_spectrum",
        "iv_curve",
        "transfer_curve",
        "gain",
        "noise",
        "threshold_shift",
        "leakage_current",
        "timing_plot",
        # Common aliases that LLMs and users frequently produce
        "energy_deposition",
        "dose_distribution",
        "dose",
        "edep",
        "energy_deposition_map",
        "fluence_map",
        "let_spectrum",
        "particle_flux",
        "charge_collection",
        "transient_current",
        "event_data",
        "hit_data",
    }
)


class TaskSpec(BaseModel):
    """Structured simulation task specification parsed from user request."""

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "simulation_scope": ["geant4", "tcad"],
                    "particle": {
                        "type": "proton",
                        "energy_MeV": 100.0,
                        "direction": [0.0, 0.0, -1.0],
                        "events": 200000,
                    },
                    "target": {
                        "material": "Silicon",
                        "size_um": [100.0, 100.0, 50.0],
                        "geometry_type": "box",
                    },
                    "device": {
                        "device_type": "NMOS",
                        "temperature_K": 300.0,
                        "bias_condition": "reverse_bias",
                    },
                    "outputs": [
                        "dose_map",
                        "tid_profile",
                        "leakage_current",
                    ],
                    "physics_options": {
                        "physics_list": "FTFP_BERT",
                        "em_physics": "G4EmStandardPhysics_option4",
                    },
                    "metadata": {"project": "TID_characterization"},
                }
            ],
        },
    }

    simulation_scope: list[SimulationScope] = Field(
        min_length=1,
        description="Simulation domains to execute",
    )
    particle: ParticleSpec | None = Field(
        default=None,
        description="Particle source configuration",
    )
    target: TargetSpec | None = Field(
        default=None,
        description="Irradiation target configuration",
    )
    device: DeviceSpec | None = Field(
        default=None,
        description="Device configuration",
    )
    circuit: CircuitSpec | None = Field(
        default=None,
        description="Circuit configuration",
    )
    outputs: list[str] = Field(
        default_factory=list,
        description="Requested output types",
    )
    physics_options: dict[str, str] | None = Field(
        default=None,
        description="Physics list and model options",
    )
    metadata: dict[str, str] | None = Field(
        default=None,
        description="Additional metadata",
    )

    @model_validator(mode="after")
    def _validate_outputs(self) -> TaskSpec:
        """Ensure every requested output is from the known set."""
        invalid = [o for o in self.outputs if o not in _VALID_OUTPUTS]
        if invalid:
            raise ValueError(f"Unknown output types: {invalid}. Valid: {sorted(_VALID_OUTPUTS)}")
        return self


def validate_task_spec(data: dict) -> tuple[TaskSpec | None, list[str]]:
    """Validate a raw dict and return (spec, errors).

    Returns:
        Tuple of parsed TaskSpec (or None on failure) and list of error strings.
    """
    try:
        spec = TaskSpec.model_validate(data)
        return spec, []
    except Exception as exc:
        if hasattr(exc, "errors"):
            msgs = [f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()]
        else:
            msgs = [str(exc)]
        return None, msgs
