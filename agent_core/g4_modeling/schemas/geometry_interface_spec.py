"""Geometry interface specification for component relationships."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeometryInterfaceSpec(BaseModel):
    """Describes the spatial relationship between two components.

    Used to validate parent-child containment, detect overlaps,
    and enforce layer stacking order.
    """

    interface_id: str = Field(
        ...,
        min_length=1,
        description="Unique interface identifier",
    )
    component_a: str = Field(
        ...,
        min_length=1,
        description="First component_id in the relationship",
    )
    component_b: str = Field(
        ...,
        min_length=1,
        description="Second component_id in the relationship",
    )
    relationship: str = Field(
        ...,
        description="Relationship type: 'contains' (A contains B), "
        "'touches' (surfaces in contact), 'adjacent' (nearby but separate), "
        "'stacked_above' (B is above A along beam axis)",
    )
    expected_gap_um: float = Field(
        default=0.0,
        ge=0,
        description="Expected gap between components in um (0 for touching)",
    )
    overlap_allowed: bool = Field(
        default=False,
        description="Whether geometric overlap is permitted",
    )
    overlap_check_enabled: bool = Field(
        default=True,
        description="Whether to run Geant4 overlap check for this pair",
    )
    tolerance_um: float = Field(
        default=0.001,
        ge=0,
        description="Tolerance for overlap detection in um",
    )
    source_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence references for interface specification",
    )


def validate_geometry_interface_spec(
    data: dict,
) -> tuple[GeometryInterfaceSpec | None, list[str]]:
    """Validate a geometry interface spec dict."""
    errors: list[str] = []
    try:
        spec = GeometryInterfaceSpec.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return spec, errors
