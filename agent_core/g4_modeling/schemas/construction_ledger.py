"""Construction ledger for auditing G4 model building steps."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConstructionLedgerEntry(BaseModel):
    """A single entry in the construction ledger.

    Records what a node did, what it modified, and what evidence it used.
    """

    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp of the entry",
    )
    node_name: str = Field(
        ...,
        min_length=1,
        description="Name of the pipeline node that created this entry",
    )
    action: Literal["create", "modify", "validate", "delete"] = Field(
        ...,
        description="Type of action performed",
    )
    target_id: str = Field(
        ...,
        min_length=1,
        description="ID of the affected entity (component_id, material_id, etc.)",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of what was done",
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Evidence references used for this action",
    )
    modified_fields: list[str] = Field(
        default_factory=list,
        description="G4ModelIR fields modified by this action",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Any warnings generated during this action",
    )


class ConstructionLedger(BaseModel):
    """Audit trail for the G4 model construction process.

    Every node that modifies the G4ModelIR must append an entry.
    The ledger enables:
    - Review of what each node did
    - Failure rollback to a specific step
    - Evidence traceability
    """

    schema_version: str = Field(
        default="construction_ledger_v1",
        description="Ledger schema version",
    )
    steps: list[ConstructionLedgerEntry] = Field(
        default_factory=list,
        description="Ordered list of construction steps",
    )

    def add_entry(
        self,
        node_name: str,
        action: Literal["create", "modify", "validate", "delete"],
        target_id: str,
        description: str,
        *,
        evidence_refs: list[str] | None = None,
        modified_fields: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> ConstructionLedgerEntry:
        """Create and append a new ledger entry."""
        entry = ConstructionLedgerEntry(
            node_name=node_name,
            action=action,
            target_id=target_id,
            description=description,
            evidence_refs=evidence_refs or [],
            modified_fields=modified_fields or [],
            warnings=warnings or [],
        )
        # Return new ledger with entry appended (immutable pattern)
        self.steps.append(entry)
        return entry

    def entries_for_node(self, node_name: str) -> list[ConstructionLedgerEntry]:
        """Return all entries created by a specific node."""
        return [s for s in self.steps if s.node_name == node_name]

    def entries_for_target(self, target_id: str) -> list[ConstructionLedgerEntry]:
        """Return all entries affecting a specific target."""
        return [s for s in self.steps if s.target_id == target_id]


def validate_construction_ledger(
    data: dict,
) -> tuple[ConstructionLedger | None, list[str]]:
    """Validate a construction ledger dict."""
    errors: list[str] = []
    try:
        ledger = ConstructionLedger.model_validate(data)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors
    return ledger, errors
