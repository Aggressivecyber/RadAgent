"""Scoring specification for Geant4 models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VoxelGrid(BaseModel):
    """3D voxel grid for scoring."""

    target_component_id: str = Field(
        ..., min_length=1,
        description="Component to voxelise for scoring",
    )
    voxel_size: list[float] = Field(
        ..., min_length=3, max_length=3,
        description="Voxel dimensions [dx, dy, dz] in global units (default um)",
    )


class RegionScore(BaseModel):
    """Per-region scoring configuration."""

    region_component_id: str = Field(
        ..., min_length=1,
        description="Component to score in",
    )
    quantity: str = Field(
        ..., min_length=1,
        description="Quantity to score: 'edep_MeV', 'dose_Gy', 'fluence', etc.",
    )


class ScoringSpec(BaseModel):
    """Scoring design for the Geant4 model.

    Defines what quantities to score, where, and how.
    Ensures compatibility with g4_output_package contract.
    """

    scoring_id: str = Field(
        ..., min_length=1, description="Unique scoring identifier"
    )
    scoring_type: Literal["voxel", "region", "mesh"] = Field(
        ..., description="Type of scoring: voxel grid, per-region, or mesh"
    )
    quantities: list[str] = Field(
        ..., min_length=1,
        description="Quantities to score: 'edep_MeV', 'dose_Gy', 'fluence_cm2', etc.",
    )
    voxel_grid: VoxelGrid | None = Field(
        default=None,
        description="Voxel grid configuration (required if scoring_type='voxel')",
    )
    region_scores: list[RegionScore] = Field(
        default_factory=list,
        description="Per-region scoring entries (required if scoring_type='region')",
    )
    output_format: Literal["csv", "root", "hdf5"] = Field(
        default="csv",
        description="Output file format (csv for g4_output_package compatibility)",
    )
    source_evidence: list[str] = Field(
        ...,
        min_length=1,
        description="Evidence references for scoring design choices",
    )
    open_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved questions about scoring configuration",
    )


def validate_scoring_spec(
    data: dict,
) -> tuple[ScoringSpec | None, list[str]]:
    """Validate a scoring spec dict."""
    errors: list[str] = []
    try:
        spec = ScoringSpec.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return spec, errors
