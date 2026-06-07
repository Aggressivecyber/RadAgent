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


def validate_human_confirmation_state(state: dict[str, Any]) -> dict[str, Any]:
    """Validate human confirmation completeness from pipeline state.

    Returns dict with: passed, checked_items, failed_items, message
    """
    errors: list[str] = []
    checked_items: list[str] = []

    required = state.get("human_confirmation_required", False)
    status = state.get("confirmation_status", "not_required")

    checked_items.append(f"confirmation_required={required}")
    checked_items.append(f"confirmation_status={status}")

    if not required:
        return {
            "passed": True,
            "checked_items": checked_items,
            "failed_items": [],
            "message": "Human confirmation not required.",
        }

    if status not in {"approved", "edited"}:
        errors.append(f"Invalid confirmation status: {status}")

    if state.get("unconfirmed_assumptions_count", 0) > 0:
        errors.append("Unconfirmed assumptions remain.")

    if not state.get("confirmation_record_path"):
        errors.append("Missing confirmation_record_path.")

    if not state.get("confirmed_model_plan_path"):
        errors.append("Missing confirmed_model_plan_path.")

    return {
        "passed": not errors,
        "checked_items": checked_items,
        "failed_items": errors,
        "message": (
            "All required confirmations complete."
            if not errors
            else "Human confirmation incomplete."
        ),
    }
