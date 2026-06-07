"""Validators for Human Confirmation Subgraph.

Enforces that unconfirmed assumptions cannot enter formal codegen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConfirmationValidationResult:
    """Result of human confirmation validation."""
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unconfirmed_components: list[str] = field(default_factory=list)
    unconfirmed_fields: list[str] = field(default_factory=list)


def validate_human_confirmation(model_ir: dict[str, Any]) -> ConfirmationValidationResult:
    """Validate that all required human confirmations are complete.

    Any component with requires_confirmation=true and
    confirmed_by_user=false blocks formal codegen.
    """
    errors: list[str] = []
    warnings: list[str] = []
    unconfirmed_components: list[str] = []
    unconfirmed_fields: list[str] = []

    components = model_ir.get("components", [])
    for comp in components:
        cid = comp.get("component_id", "?")
        if comp.get("requires_confirmation", False) and not comp.get("confirmed_by_user", False):
            unconfirmed_components.append(cid)

    for f in model_ir.get("unconfirmed_fields", []):
        unconfirmed_fields.append(f)

    all_unconfirmed = unconfirmed_components + unconfirmed_fields

    if all_unconfirmed:
        errors.append(
            f"Unconfirmed modeling assumptions remain: {all_unconfirmed}"
        )

    # Warn if assumptions_confirmed is False but no specific unconfirmed items
    if not model_ir.get("assumptions_confirmed", False) and not all_unconfirmed:
        warnings.append("assumptions_confirmed is False but no specific unconfirmed items found")

    return ConfirmationValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        unconfirmed_components=unconfirmed_components,
        unconfirmed_fields=unconfirmed_fields,
    )
