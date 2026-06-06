"""TCAD input data contract using Pydantic v2."""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError


class TCADInputContract(BaseModel):
    """Schema for data flowing into the TCAD simulation module."""

    schema_version: str = "tcad_input_v1"
    simulation_id: str = Field(..., description="Unique identifier for this TCAD run")
    device_structure: dict = Field(
        ..., description="Geometry, materials, and region definitions"
    )
    mesh_config: dict = Field(..., description="Meshing strategy and refinement rules")
    physics_models: list[str] = Field(
        ..., description="Activated physics model names (e.g. Traps, EffectiveIntrinsicDensity)"
    )
    defect_model: dict = Field(
        ..., description="Trap / defect parameters (energy, capture cross-sections, density)"
    )
    bias_conditions: dict = Field(
        ..., description="Electrode biases, sweep ranges, and transient steps"
    )
    source_packages: list[str] = Field(
        default_factory=list,
        description="Upstream package names that produced this input",
    )
    coordinate_unit: str = Field(default="um", description="Spatial unit for geometry")


def validate_tcad_input(data: dict) -> TCADInputContract:
    """Validate raw dict against TCADInputContract.

    Returns the parsed model on success, raises ValueError on failure.
    """
    try:
        return TCADInputContract.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"TCAD input contract validation failed: {exc}") from exc
