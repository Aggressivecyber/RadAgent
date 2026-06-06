"""Geant4 to TCAD mapping contract schema (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MappingEntry(BaseModel):
    """Single quantity mapping from Geant4 output to TCAD input."""

    g4_quantity: str = Field(
        ..., description="Geant4 scored quantity (e.g. edep, dose, fluence)"
    )
    tcad_parameter: str = Field(
        ...,
        description="Target TCAD parameter (e.g. generation_rate, trap_density, fixed_charge)",
    )
    mapping_function: str = Field(
        ..., description="Formula or method name for the conversion"
    )
    unit_conversion: str = Field(
        ..., description="Unit conversion expression (e.g. 'Gy->cm^-3', 'MeV->J')"
    )
    source_file: str = Field(
        ..., description="Geant4 output file providing this quantity"
    )
    validity_range: dict | None = Field(
        default=None, description="Range constraints (min/max) for the mapping"
    )


class G4ToTCADContract(BaseModel):
    """Contract governing data transfer between Geant4 and TCAD stages."""

    schema_version: str = Field(default="g4_to_tcad_v1")
    simulation_id: str = Field(..., description="Unique simulation run identifier")
    mappings: list[MappingEntry] = Field(
        default_factory=list, description="Quantity mapping table"
    )
    generation_rate_profile: str = Field(
        ..., description="File path to generation rate spatial profile"
    )
    trap_profile: str | None = Field(
        default=None, description="File path to trap density profile"
    )
    fixed_charge_profile: str | None = Field(
        default=None, description="File path to fixed charge profile"
    )
    mapping_report: str = Field(
        ..., description="File path for the mapping validation report"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Physical assumptions made during mapping",
    )
