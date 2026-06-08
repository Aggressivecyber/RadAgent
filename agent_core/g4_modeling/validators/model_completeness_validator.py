"""Model completeness validator — Gate G4-A.

Ensures the G4ModelIR has all required sections populated
for the declared modeling_mode.
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR


class ModelCompletenessValidator:
    """Validates that G4ModelIR sections are complete."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Check all required sections of G4ModelIR.

        Returns (passed, list_of_error_messages).
        """
        errors: list[str] = []

        # Components: must have at least world + one non-world
        if not model_ir.components:
            errors.append("No components defined in G4ModelIR")
        else:
            non_world = [c for c in model_ir.components if c.component_type != "world"]
            if not non_world:
                errors.append("Only world volume defined — no geometry components")

        # Materials
        if not model_ir.materials:
            errors.append("No materials defined in G4ModelIR")
        else:
            material_ids = {m.material_id for m in model_ir.materials}
            for comp in model_ir.components:
                if comp.material_id not in material_ids:
                    errors.append(
                        f"Component '{comp.component_id}' references "
                        f"undefined material '{comp.material_id}'"
                    )

        # Sources
        if not model_ir.sources:
            errors.append("No particle sources defined in G4ModelIR")

        # Physics
        if model_ir.physics is None:
            errors.append("No physics list defined in G4ModelIR")

        # Scoring
        if not model_ir.scoring:
            errors.append("No scoring configurations defined in G4ModelIR")

        # Interfaces (required for realistic mode)
        if model_ir.modeling_mode == "realistic":
            if not model_ir.interfaces:
                errors.append("No geometry interfaces defined — required in realistic mode")

        # Sensitive detectors
        sensitive_components = [c for c in model_ir.components if c.sensitive]
        if sensitive_components and not model_ir.sensitive_detectors:
            errors.append("Components marked as sensitive but no SDs defined")

        return len(errors) == 0, errors
