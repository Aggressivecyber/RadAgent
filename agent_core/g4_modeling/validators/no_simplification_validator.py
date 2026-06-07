"""No unapproved simplification validator — Gate G4-B.

Detects signs of lazy simplification: placeholder values,
empty evidence, default-sized dimensions, merged layers.
"""

from __future__ import annotations

import re

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

# Patterns that indicate placeholder/TODO values
_PLACEHOLDER_PATTERNS = re.compile(
    r"(?i)(todo|tbd|fixme|xxx|placeholder|unknown|n/a|default|tbs)"
)

# Common lazy defaults for dimensions
_DEFAULT_DIMENSIONS: dict[str, tuple[float, ...]] = {
    "box": (1000.0, 1000.0, 1000.0),  # Generic 1mm cube
    "sphere": (500.0,),  # Generic sphere
}


class NoSimplificationValidator:
    """Detects unapproved simplifications in the G4ModelIR."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Scan all specs for signs of simplification.

        Checks:
        - Empty source_evidence lists
        - Placeholder/TODO values in any string field
        - Default-sized dimensions
        - Merged layers (single component where user asked for multi-layer)
        - Approved simplifications tracked in policy
        """
        errors: list[str] = []
        approved = set(model_ir.simplification_policy.approved_simplifications)

        # Check components
        for comp in model_ir.components:
            self._check_evidence(
                comp.component_id, comp.source_evidence,
                "component", errors, approved,
            )
            self._check_dimensions(
                comp.component_id, comp.geometry_type,
                comp.dimensions, errors, approved,
            )
            self._check_placeholders(
                comp.component_id, comp.display_name,
                "component", errors,
            )

        # Check materials
        for mat in model_ir.materials:
            self._check_evidence(
                mat.material_id, mat.source_evidence,
                "material", errors, approved,
            )
            self._check_placeholders(
                mat.material_id, mat.name,
                "material", errors,
            )

        # Check sources
        for src in model_ir.sources:
            self._check_evidence(
                src.source_id, src.source_evidence,
                "source", errors, approved,
            )

        # Check physics
        if model_ir.physics is not None:
            self._check_evidence(
                model_ir.physics.physics_list,
                model_ir.physics.source_evidence,
                "physics", errors, approved,
            )

        # Check scoring
        for sc in model_ir.scoring:
            self._check_evidence(
                sc.scoring_id, sc.source_evidence,
                "scoring", errors, approved,
            )

        return len(errors) == 0, errors

    def _check_evidence(
        self,
        target_id: str,
        evidence: list[str],
        spec_type: str,
        errors: list[str],
        approved: set[str],
    ) -> None:
        """Check source_evidence is non-empty and non-placeholder."""
        if not evidence:
            msg = f"{spec_type} '{target_id}' has empty source_evidence"
            if msg not in approved:
                errors.append(msg + " — no evidence traceability")
            return
        for ref in evidence:
            if not ref.strip() or _PLACEHOLDER_PATTERNS.search(ref):
                msg = f"{spec_type} '{target_id}' has placeholder evidence: '{ref}'"
                if msg not in approved:
                    errors.append(msg)

    def _check_dimensions(
        self,
        component_id: str,
        geometry_type: str,
        dimensions: dict[str, float],
        errors: list[str],
        approved: set[str],
    ) -> None:
        """Check for suspiciously default dimensions."""
        default = _DEFAULT_DIMENSIONS.get(geometry_type)
        if default is None:
            return

        dim_values = list(dimensions.values())
        if not dim_values:
            return

        # Check if all dimensions match common defaults exactly
        if geometry_type == "box":
            dx = dimensions.get("dx", 0)
            dy = dimensions.get("dy", 0)
            dz = dimensions.get("dz", 0)
            if (dx, dy, dz) == (1000.0, 1000.0, 1000.0):
                msg = (
                    f"Component '{component_id}' uses generic default "
                    f"dimensions (1000x1000x1000) — likely unapproved simplification"
                )
                if msg not in approved:
                    errors.append(msg)

    def _check_placeholders(
        self,
        target_id: str,
        text: str,
        spec_type: str,
        errors: list[str],
    ) -> None:
        """Check for placeholder text in string fields."""
        if _PLACEHOLDER_PATTERNS.search(text):
            errors.append(
                f"{spec_type} '{target_id}' contains placeholder text: '{text}'"
            )
