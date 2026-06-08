"""Geant4 Model IR — the central state for complex model construction.

All nodes in the complex modeling pipeline read and write this IR.
No node may pass critical model information via natural language
or undocumented side channels.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.construction_ledger import ConstructionLedger
from agent_core.g4_modeling.schemas.geometry_interface_spec import GeometryInterfaceSpec
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
from agent_core.g4_modeling.schemas.scoring_spec import ScoringSpec
from agent_core.g4_modeling.schemas.sensitive_detector_spec import SensitiveDetectorSpec
from agent_core.g4_modeling.schemas.source_spec import SourceSpec


class SimplificationPolicy(BaseModel):
    """Controls what simplifications are allowed in the model."""

    allow_simplification: bool = Field(
        default=False,
        description="Whether any simplification is permitted",
    )
    requires_user_approval: bool = Field(
        default=True,
        description="Whether simplifications need explicit user approval",
    )
    approved_simplifications: list[str] = Field(
        default_factory=list,
        description="List of approved simplification descriptions",
    )


class GlobalUnits(BaseModel):
    """Unit system for the entire model."""

    length: str = Field(default="um", description="Default length unit")
    energy: str = Field(default="MeV", description="Default energy unit")
    dose: str = Field(default="Gy", description="Default dose unit")
    time: str = Field(default="s", description="Default time unit")


class CoordinateSystem(BaseModel):
    """Global coordinate system definition."""

    system: Literal["cartesian", "cylindrical", "spherical"] = Field(
        default="cartesian",
    )
    origin_definition: str = Field(
        default="world_center",
        description="Where the origin is placed (e.g. 'sensor_center', 'world_center')",
    )
    axis_definition: dict[str, str] = Field(
        default_factory=lambda: {
            "x": "sensor_width",
            "y": "sensor_length",
            "z": "beam_direction",
        },
        description="Semantic meaning of each axis",
    )
    unit: str = Field(default="um")


class EvidencePack(BaseModel):
    """Evidence map organized by modeling dimension."""

    evidence_decision: Literal["allow_rag", "allow_with_web_supplement", "block_no_context"] = (
        Field(
            ...,
            description="Overall evidence sufficiency decision",
        )
    )
    geometry: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence for geometry decisions",
    )
    materials: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence for material definitions",
    )
    source: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence for source configuration",
    )
    physics: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence for physics list selection",
    )
    scoring: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence for scoring design",
    )


class G4ModelIR(BaseModel):
    """Geant4 Model Intermediate Representation.

    This is the SINGLE SOURCE OF TRUTH for the complex model.
    All nodes read from and write to this structure. C++ codegen
    may ONLY use parameters declared in this IR.
    """

    schema_version: str = Field(
        default="g4_model_ir_v1",
        description="IR schema version for forward compatibility",
    )
    model_ir_id: str = Field(
        ...,
        min_length=1,
        description="Unique model IR identifier",
    )
    job_id: str = Field(
        ...,
        min_length=1,
        description="Job ID this model belongs to",
    )
    modeling_mode: Literal["simple", "realistic"] = Field(
        default="realistic",
        description="Modeling mode — 'realistic' enforces all quality gates",
    )
    target_system: str = Field(
        default="",
        description="Description of the target system being modeled",
    )

    # Policy
    simplification_policy: SimplificationPolicy = Field(
        default_factory=SimplificationPolicy,
    )

    # Units and coordinates
    global_units: GlobalUnits = Field(default_factory=GlobalUnits)
    coordinate_system: CoordinateSystem = Field(
        default_factory=CoordinateSystem,
    )

    # Evidence
    evidence: EvidencePack | None = Field(
        default=None,
        description="Evidence map populated by evidence_retrieval_node",
    )

    # Geometry
    components: list[ComponentSpec] = Field(
        default_factory=list,
        description="All geometry components in the model",
    )
    interfaces: list[GeometryInterfaceSpec] = Field(
        default_factory=list,
        description="Inter-component spatial relationships",
    )

    # Materials
    materials: list[MaterialSpec] = Field(
        default_factory=list,
        description="All material definitions",
    )

    # Particle source
    sources: list[SourceSpec] = Field(
        default_factory=list,
        description="Particle source configurations (usually one)",
    )

    # Physics
    physics: PhysicsSpec | None = Field(
        default=None,
        description="Physics list selection with reasoning",
    )

    # Scoring
    scoring: list[ScoringSpec] = Field(
        default_factory=list,
        description="Scoring configurations",
    )

    # Sensitive detectors
    sensitive_detectors: list[SensitiveDetectorSpec] = Field(
        default_factory=list,
        description="Sensitive detector definitions",
    )

    # Construction audit
    ledger: ConstructionLedger = Field(
        default_factory=ConstructionLedger,
        description="Audit trail of all node modifications",
    )

    # Open issues
    open_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved issues that prevent final model validation",
    )

    # Human confirmation tracking
    human_confirmation: dict[str, Any] = Field(
        default_factory=dict,
        description="Human confirmation status and metadata",
    )
    confirmed_fields: list[str] = Field(
        default_factory=list,
        description="Fields confirmed by user",
    )
    unconfirmed_fields: list[str] = Field(
        default_factory=list,
        description="Fields still requiring user confirmation",
    )
    assumptions_confirmed: bool = Field(
        default=False,
        description="Whether all assumptions have been confirmed by user",
    )

    @field_validator("components")
    @classmethod
    def _world_volume_must_exist(cls, v: list[ComponentSpec]) -> list[ComponentSpec]:
        """If components are defined, exactly one must be 'world'."""
        if not v:
            return v
        world_count = sum(1 for c in v if c.component_type == "world")
        if world_count == 0:
            raise ValueError("At least one component with type='world' is required")
        if world_count > 1:
            raise ValueError("Exactly one component with type='world' is allowed")
        return v

    def component_by_id(self, component_id: str) -> ComponentSpec | None:
        """Look up a component by its ID."""
        for c in self.components:
            if c.component_id == component_id:
                return c
        return None

    def material_by_id(self, material_id: str) -> MaterialSpec | None:
        """Look up a material by its ID."""
        for m in self.materials:
            if m.material_id == material_id:
                return m
        return None

    def children_of(self, component_id: str) -> list[ComponentSpec]:
        """Return all components whose mother_volume is the given ID."""
        return [c for c in self.components if c.mother_volume == component_id]


def validate_g4_model_ir(
    data: dict,
) -> tuple[G4ModelIR | None, list[str]]:
    """Validate a G4ModelIR dict.

    Returns (model, errors). On failure model is None.
    """
    errors: list[str] = []
    try:
        ir = G4ModelIR.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return ir, errors
