"""No unapproved simplification validator — Gate G4-B.

Detects signs of lazy simplification: placeholder values,
empty evidence, default-sized dimensions, merged layers,
missing required components.

This is a CRITICAL gate — if the user requests a complex detector
but the Model IR only contains world + silicon_detector, this gate
MUST fail.
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

# Signs of an oversimplified model — if ALL these are true, it's a red flag
_SIMPLIFICATION_INDICATORS = {
    "housing",
    "pcb",
    "oxide",
    "electrode",
    "sensitive",
}

# If user asked for complex model, these component patterns should exist
_COMPLEX_MODEL_PATTERNS = [
    ("housing", {"housing", "enclosure", "shield", "case"}),
    ("pcb", {"pcb", "board", "carrier", "substrate_carrier"}),
    ("oxide", {"oxide", "sio2", "gate_oxide", "insulator"}),
    ("electrode", {"electrode", "contact", "metal_contact"}),
    ("sensitive", {"sensitive", "active", "depletion"}),
]


class NoSimplificationValidator:
    """Detects unapproved simplifications in the G4ModelIR.

    Enhanced checks:
    1. Empty source_evidence
    2. Placeholder/TODO values
    3. Default-sized dimensions
    4. Missing complex model components (housing, pcb, oxide, electrodes)
    5. Multi-layer merge detection (single silicon box instead of stack)
    6. Complex model keyword detection in target_system
    """

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Scan all specs for signs of simplification.

        Returns (passed, list_of_error_messages).
        """
        errors: list[str] = []
        approved = set(model_ir.simplification_policy.approved_simplifications)

        component_ids = {c.component_id for c in model_ir.components}
        component_names_lower = {
            c.component_id.lower() + " " + c.display_name.lower()
            for c in model_ir.components
        }

        # ── Check 1: Complex model keyword detection ──
        target_lower = model_ir.target_system.lower()
        is_complex_request = any(
            kw in target_lower
            for kw in ("detector", "sensor", "pixel", "strip", "stack", "radiation", "rad-hard")
        )

        if is_complex_request:
            # Check which complex patterns are present
            for category, patterns in _COMPLEX_MODEL_PATTERNS:
                found = any(
                    any(p in name_lower for p in patterns)
                    for name_lower in component_names_lower
                )
                if not found:
                    # Check if user explicitly approved the omission
                    approved_key = f"omit_{category}"
                    if approved_key not in approved:
                        errors.append(
                            f"Complex model requested but no {category} component found. "
                            f"Component IDs: {sorted(component_ids)}"
                        )

        # ── Check 2: Multi-layer merge detection ──
        # If there's only 1 non-world volume and the target mentions "stack",
        # that's a simplification red flag
        non_world_components = [
            c for c in model_ir.components
            if c.component_type not in ("world",)
        ]
        if len(non_world_components) <= 2 and is_complex_request:
            errors.append(
                f"Complex model has only {len(non_world_components)} non-world components "
                f"(expected multi-layer stack). Possible layer merge simplification."
            )

        # ── Check 3: Component evidence and dimensions ──
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

        # ── Check 4: Material evidence ──
        for mat in model_ir.materials:
            self._check_evidence(
                mat.material_id, mat.source_evidence,
                "material", errors, approved,
            )
            self._check_placeholders(
                mat.material_id, mat.name,
                "material", errors,
            )

        # ── Check 5: Source evidence ──
        for src in model_ir.sources:
            self._check_evidence(
                src.source_id, src.source_evidence,
                "source", errors, approved,
            )

        # ── Check 6: Physics evidence ──
        if model_ir.physics is not None:
            self._check_evidence(
                model_ir.physics.physics_list,
                model_ir.physics.source_evidence,
                "physics", errors, approved,
            )

        # ── Check 7: Scoring evidence ──
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
