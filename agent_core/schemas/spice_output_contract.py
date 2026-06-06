"""SPICE output data contract (Pydantic v2)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class SPICECircuitInfo(BaseModel):
    type: str = Field(description="Circuit topology name (e.g. CMOS_inverter)")
    supply_voltage_V: float = Field(gt=0, description="Supply voltage in volts")  # noqa: N815


class SPICEInputs(BaseModel):
    radiation_current_source: Path = Field(
        description="Path to radiation-induced current source file"
    )


class SPICEOutputFiles(BaseModel):
    waveform: Path = Field(description="Path to output waveform data file")


class SPICEChecks(BaseModel):
    nan_count: int = Field(ge=0, description="Number of NaN values in results")
    floating_node_detected: bool = Field(
        description="Whether floating nodes were detected"
    )
    simulation_completed: bool = Field(
        description="Whether the simulation ran to completion"
    )


class SPICEOutputContract(BaseModel):
    schema_version: str = Field(default="1.0.0", frozen=True)
    simulation_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    circuit: SPICECircuitInfo
    inputs: SPICEInputs
    outputs: SPICEOutputFiles
    checks: SPICEChecks

    @field_validator("schema_version")
    @classmethod
    def _version_format(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            msg = f"schema_version must be semver, got '{v}'"
            raise ValueError(msg)
        return v


def validate_spice_output(data: dict) -> SPICEOutputContract:
    """Validate a raw dict against the SPICE output contract.

    Returns the parsed model or raises ``ValidationError``.
    """
    return SPICEOutputContract.model_validate(data)
