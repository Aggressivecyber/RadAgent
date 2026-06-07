"""Component specification for Geant4 geometry decomposition."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class PlacementSpec(BaseModel):
    """Placement of a component relative to its mother volume."""

    position: list[float] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Translation [x, y, z] in global units (default um)",
    )
    rotation: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        min_length=3,
        max_length=3,
        description="Rotation [rx, ry, rz] in degrees",
    )

    @field_validator("position", "rotation")
    @classmethod
    def _finite_numbers(cls, v: list[float]) -> list[float]:
        for i, x in enumerate(v):
            if x != x:  # NaN check
                raise ValueError(f"Value at index {i} is NaN")
        return v


class ComponentSpec(BaseModel):
    """A single component in the Geant4 geometry tree.

    Every component must have:
    - A unique component_id
    - A mother_volume (None only for world volume)
    - A geometry type and dimensions
    - A material reference
    - Source evidence for traceability
    """

    component_id: str = Field(
        ..., min_length=1, description="Unique identifier (e.g. 'oxide_layer')"
    )
    display_name: str = Field(
        ..., min_length=1, description="Human-readable name"
    )
    component_type: Literal[
        "world", "assembly", "layer", "volume", "shielding", "electrode", "substrate"
    ] = Field(..., description="Semantic type of this component")
    geometry_type: Literal[
        "box", "sphere", "cylinder", "tubs", "cons", "polycone", "trapezoid"
    ] = Field(..., description="G4VSolid shape type")
    dimensions: dict[str, float] = Field(
        ...,
        description="Shape-specific dimensions in global units. "
        "Keys depend on geometry_type: box→{dx,dy,dz}, cylinder→{rmin,rmax,dz}, etc.",
    )
    material_id: str = Field(
        ..., min_length=1, description="Reference to a MaterialSpec.material_id"
    )
    placement: PlacementSpec = Field(
        default_factory=lambda: PlacementSpec(position=[0.0, 0.0, 0.0]),
        description="Placement relative to mother volume",
    )
    mother_volume: str | None = Field(
        default=None,
        description="Parent component_id. None for world volume only.",
    )
    sensitive: bool = Field(
        default=False, description="Whether this volume is a sensitive detector"
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Functional roles: dose_scoring_region, edep_region, shield, etc.",
    )
    color: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="RGB color for visualization [0-1]",
    )
    source_evidence: list[str] = Field(
        ...,
        min_length=1,
        description="Evidence references for dimensions/material. "
        "Must trace to RAG doc ID, URL, or user specification.",
    )
    open_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved questions about this component",
    )
    requires_confirmation: bool = Field(default=False, description="Needs user confirmation")
    confirmed_by_user: bool = Field(default=False, description="User has confirmed")
    confirmation_source: str | None = Field(
        default=None,
        description="Confirmation source reference",
    )

    @field_validator("mother_volume")
    @classmethod
    def _world_has_no_mother(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None and info.data.get("component_type") != "world":
            raise ValueError(
                "Only world volume may have mother_volume=None"
            )
        return v


def validate_component_spec(
    data: dict,
) -> tuple[ComponentSpec | None, list[str]]:
    """Validate a component spec dict.

    Returns (model, errors). On failure model is None.
    """
    errors: list[str] = []
    try:
        spec = ComponentSpec.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return spec, errors
