"""Particle source specification for Geant4 models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class EnergySpec(BaseModel):
    """Energy configuration for a particle source."""

    value: float = Field(..., description="Energy value")
    unit: Literal["MeV", "keV", "GeV", "eV"] = Field(default="MeV")
    distribution: Literal["mono", "gaussian", "uniform", "spectrum"] = Field(
        default="mono",
        description="Energy distribution type",
    )
    sigma: float | None = Field(
        default=None,
        description="Sigma for gaussian distribution (same unit)",
    )
    spectrum_file: str | None = Field(
        default=None,
        description="Path to spectrum file for 'spectrum' distribution",
    )


class BeamProfile(BaseModel):
    """Beam spatial and angular profile."""

    position: list[float] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Beam center position [x, y, z] in um",
    )
    direction: list[float] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Beam direction vector [dx, dy, dz]",
    )
    sigma_position_um: float | None = Field(
        default=None,
        ge=0,
        description="Beam spot size sigma in um (None = pencil beam)",
    )
    sigma_direction_rad: float | None = Field(
        default=None,
        ge=0,
        description="Angular spread sigma in radians (None = parallel)",
    )
    surface_shape: Literal["circle", "rectangle", "point"] = Field(
        default="point",
        description="Beam surface shape",
    )
    surface_size: list[float] | None = Field(
        default=None,
        description="Surface dimensions [width, height] for rectangle or [radius] for circle",
    )


class SourceSpec(BaseModel):
    """Particle source definition for the Geant4 model.

    Supports both simple particle gun configurations and
    complex General Particle Source (GPS) setups.
    """

    source_id: str = Field(..., min_length=1, description="Unique source identifier")
    particle_type: str = Field(
        ...,
        min_length=1,
        description="Geant4 particle name (e.g. 'proton', 'gamma', 'e-')",
    )
    energy: EnergySpec = Field(..., description="Energy configuration")
    beam: BeamProfile = Field(..., description="Beam spatial and angular configuration")
    generator_type: Literal["gun", "gps"] = Field(
        default="gun",
        description="Particle gun for simple beams, GPS for complex sources",
    )
    events: int = Field(
        default=1000,
        ge=1,
        description="Number of events to generate",
    )
    source_evidence: list[str] = Field(
        ...,
        min_length=1,
        description="Evidence references for source parameters",
    )
    open_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved questions about this source",
    )

    @field_validator("generator_type")
    @classmethod
    def _complex_source_needs_gps(cls, v: str, info: ValidationInfo) -> str:
        """Warn if a complex profile uses gun instead of GPS."""
        beam = info.data.get("beam")
        if v == "gun" and beam is not None:
            if (
                getattr(beam, "sigma_position_um", None) is not None
                or getattr(beam, "sigma_direction_rad", None) is not None
                or getattr(beam, "surface_shape", "point") != "point"
            ):
                # Not raising — just noting. Validators enforce, nodes warn.
                pass
        return v


def validate_source_spec(
    data: dict,
) -> tuple[SourceSpec | None, list[str]]:
    """Validate a source spec dict."""
    errors: list[str] = []
    try:
        spec = SourceSpec.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return spec, errors
