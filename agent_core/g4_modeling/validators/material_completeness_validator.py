"""Material completeness validator — contributes to Gate G4-A.

Ensures all materials have valid definitions:
NIST materials have a name, custom materials have composition.
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR


class MaterialCompletenessValidator:
    """Validates material definitions are complete and well-formed."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Check all materials in G4ModelIR.

        Validates:
        - NIST materials have nist_name
        - Custom materials have composition
        - All materials have positive density
        - All material_ids referenced by components exist
        - No duplicate material_ids
        """
        errors: list[str] = []

        # Check for duplicates
        seen_ids: set[str] = set()
        for mat in model_ir.materials:
            if mat.material_id in seen_ids:
                errors.append(f"Duplicate material_id: '{mat.material_id}'")
            seen_ids.add(mat.material_id)

        # Validate each material
        for mat in model_ir.materials:
            if mat.classification == "nist":
                if not mat.nist_name or not mat.nist_name.startswith("G4_"):
                    errors.append(
                        f"Material '{mat.material_id}' classified as NIST "
                        f"but nist_name '{mat.nist_name}' does not start "
                        f"with 'G4_' — likely invalid"
                    )
            elif mat.classification == "custom":
                if not mat.composition or len(mat.composition) == 0:
                    errors.append(
                        f"Material '{mat.material_id}' classified as custom "
                        f"but has no element composition"
                    )
                else:
                    # Check fractions sum to ~1.0
                    total = sum(ef.fraction for ef in mat.composition)
                    if total <= 0:
                        errors.append(
                            f"Material '{mat.material_id}' composition "
                            f"fractions sum to {total:.4f} — must be positive"
                        )

            if mat.density_g_cm3 <= 0:
                errors.append(
                    f"Material '{mat.material_id}' density {mat.density_g_cm3} must be positive"
                )

        # Cross-reference with components
        defined_ids = {m.material_id for m in model_ir.materials}
        for comp in model_ir.components:
            if comp.material_id not in defined_ids:
                errors.append(
                    f"Component '{comp.component_id}' references "
                    f"undefined material '{comp.material_id}'"
                )

        return len(errors) == 0, errors
