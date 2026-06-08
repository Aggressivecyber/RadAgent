"""Sensitive detector specification for Geant4 models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HitFieldSpec(BaseModel):
    """A single field in a sensitive detector hit collection."""

    name: str = Field(..., min_length=1, description="Field name (e.g. 'edep_MeV')")
    dtype: str = Field(
        default="float",
        description="C++ type: 'float', 'double', 'int', 'long'",
    )
    unit: str | None = Field(
        default=None,
        description="Physical unit (e.g. 'MeV', 'um', 's')",
    )


class SensitiveDetectorSpec(BaseModel):
    """Sensitive detector definition linked to geometry components.

    Each SD attaches to one or more logical volumes (via component_ids)
    and records specified hit fields during simulation.
    """

    sd_id: str = Field(..., min_length=1, description="Unique SD identifier")
    name: str = Field(
        ...,
        min_length=1,
        description="Geant4 SD class name (e.g. 'SiliconSensitiveDetector')",
    )
    linked_component_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Component IDs this SD attaches to",
    )
    scoring_ids: list[str] = Field(
        default_factory=list,
        description="Scoring specs that consume data from this SD",
    )
    collection_name: str = Field(
        default="HitsCollection",
        description="G4HCname for the hit collection",
    )
    hit_fields: list[HitFieldSpec] = Field(
        ...,
        min_length=1,
        description="Fields recorded per step/hit",
    )
    open_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved questions about this SD",
    )


def validate_sensitive_detector_spec(
    data: dict,
) -> tuple[SensitiveDetectorSpec | None, list[str]]:
    """Validate a sensitive detector spec dict."""
    errors: list[str] = []
    try:
        spec = SensitiveDetectorSpec.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return spec, errors
