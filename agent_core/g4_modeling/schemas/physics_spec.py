"""Physics list specification for Geant4 models."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PhysicsSpec(BaseModel):
    """Physics list selection with mandatory reasoning.

    Prevents defaulting to FTFP_BERT without justification.
    The selection_reasoning field must explain why the chosen
    physics list covers the required processes for the simulation.
    """

    physics_list: str = Field(
        ..., min_length=1,
        description="Geant4 physics list name (e.g. 'FTFP_BERT', 'QGSP_BIC_HP', "
        "'Shielding', 'Livermore')",
    )
    selection_reasoning: str = Field(
        ..., min_length=10,
        description="Mandatory explanation of why this physics list was chosen. "
        "Must reference particle type, energy range, and target output.",
    )
    em_physics: str | None = Field(
        default=None,
        description="EM physics option: 'standard', 'livermore', 'penelope', 'option4'",
    )
    hadronic: str | None = Field(
        default=None,
        description="Hadronic physics option: 'bertini', 'binary_cascade', 'qgsp', etc.",
    )
    decay: bool = Field(
        default=True,
        description="Whether to include decay processes",
    )
    cuts: dict[str, float] | None = Field(
        default=None,
        description="Production cuts by particle type (e.g. {'gamma': 0.1, 'e-': 0.1}) "
        "in mm. None = use Geant4 defaults.",
    )
    hp_neutron: bool = Field(
        default=False,
        description="Whether NeutronHP is needed (requires G4NDL data)",
    )
    source_evidence: list[str] = Field(
        ...,
        min_length=1,
        description="Evidence references for physics list selection",
    )
    open_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved questions about physics configuration",
    )

    @field_validator("selection_reasoning")
    @classmethod
    def _reasoning_must_be_substantive(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 10:
            raise ValueError(
                "selection_reasoning must be at least 10 characters and explain "
                "why this physics list covers the required processes"
            )
        return stripped


def validate_physics_spec(
    data: dict,
) -> tuple[PhysicsSpec | None, list[str]]:
    """Validate a physics spec dict."""
    errors: list[str] = []
    try:
        spec = PhysicsSpec.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return spec, errors
