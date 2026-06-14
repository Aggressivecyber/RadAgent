"""Material specification for Geant4 models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class ElementFraction(BaseModel):
    """An element and its fraction in a custom material."""

    element: str = Field(..., min_length=1, description="Element symbol (e.g. 'Si', 'O')")
    fraction: float = Field(..., gt=0, description="Mass or atom fraction")


class MaterialSpec(BaseModel):
    """A material definition for the Geant4 model.

    NIST materials use G4NistManager with a standard name.
    Custom materials require explicit element composition and density.
    """

    material_id: str = Field(
        ..., min_length=1, description="Unique identifier (e.g. 'silicon_dioxide')"
    )
    name: str = Field(..., min_length=1, description="Display name (e.g. 'Silicon Dioxide')")
    classification: Literal["nist", "custom"] = Field(
        ..., description="Whether this is a NIST standard or custom material"
    )
    nist_name: str | None = Field(
        default=None,
        description="G4NistManager name (e.g. 'G4_Si'). Required if classification='nist'.",
    )
    composition: list[ElementFraction] | None = Field(
        default=None,
        description="Element composition. Required if classification='custom'.",
    )
    density_g_cm3: float = Field(..., gt=0, description="Material density in g/cm³")
    state: Literal["solid", "liquid", "gas"] | None = Field(
        default="solid", description="Material state"
    )
    temperature_kelvin: float | None = Field(
        default=None,
        description="Temperature in Kelvin (optional override)",
        alias="temperature_K",
    )
    source_evidence: list[str] = Field(
        ...,
        min_length=1,
        description="Evidence references for material properties",
    )
    open_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved questions about this material",
    )
    requires_confirmation: bool = Field(
        default=False,
        description="Needs user confirmation before production code generation",
    )
    confirmed_by_user: bool = Field(default=False, description="User has confirmed")
    confirmation_source: str | None = Field(
        default=None,
        description="Confirmation source reference",
    )

    @field_validator("nist_name")
    @classmethod
    def _nist_requires_name(cls, v: str | None, info: ValidationInfo) -> str | None:
        classification = info.data.get("classification")
        if classification == "nist" and (v is None or v.strip() == ""):
            raise ValueError("nist_name is required when classification='nist'")
        return v

    @field_validator("composition")
    @classmethod
    def _custom_requires_composition(
        cls, v: list[ElementFraction] | None, info: ValidationInfo
    ) -> list[ElementFraction] | None:
        classification = info.data.get("classification")
        if classification == "custom" and (v is None or len(v) == 0):
            raise ValueError("composition is required when classification='custom'")
        return v


def validate_material_spec(
    data: dict,
) -> tuple[MaterialSpec | None, list[str]]:
    """Validate a material spec dict."""
    errors: list[str] = []
    try:
        spec = MaterialSpec.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return spec, errors
