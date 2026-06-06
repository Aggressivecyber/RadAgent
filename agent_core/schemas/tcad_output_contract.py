"""TCAD output data contract (Pydantic v2)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class TCADDeviceInfo(BaseModel):
    type: str = Field(description="Device topology (e.g. NMOS, FinFET)")
    temperature_K: float = Field(gt=0, description="Simulation temperature in kelvin")
    bias_condition: str = Field(description="Bias description (e.g. Vgs=0.8V Vds=1.2V)")


class TCADDefectModel(BaseModel):
    model_name: str = Field(description="Defect/trap model name")
    trap_density_cm3: float = Field(gt=0, description="Trap density in cm^-3")
    electron_capture_cross_section_cm2: float = Field(
        gt=0, description="Electron capture cross-section in cm^2"
    )
    hole_capture_cross_section_cm2: float = Field(
        gt=0, description="Hole capture cross-section in cm^2"
    )


class TCADOutputFiles(BaseModel):
    iv_curve: Path = Field(description="Path to I-V curve data file")
    transient_current: Path = Field(description="Path to transient current data file")
    charge_collection: Path = Field(description="Path to charge collection data file")


class TCADChecks(BaseModel):
    converged: bool = Field(description="Whether the simulation converged")
    nan_count: int = Field(ge=0, description="Number of NaN values in results")


class TCADOutputContract(BaseModel):
    schema_version: str = Field(default="1.0.0", frozen=True)
    simulation_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    device: TCADDeviceInfo
    defect_model: TCADDefectModel
    outputs: TCADOutputFiles
    checks: TCADChecks

    @field_validator("schema_version")
    @classmethod
    def _version_format(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            msg = f"schema_version must be semver, got '{v}'"
            raise ValueError(msg)
        return v


def validate_tcad_output(data: dict) -> TCADOutputContract:
    """Validate a raw dict against the TCAD output contract.

    Returns the parsed model or raises ``ValidationError``.
    """
    return TCADOutputContract.model_validate(data)
