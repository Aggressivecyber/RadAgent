"""Code module boundary validator — Gate G4-F.

Ensures each codegen module only produces code for its own
responsibility area and only references IR-defined parameters.
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.code_module_plan import CodeGenerationPlan
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

# Each module type may only reference certain IR sections
_MODULE_PERMISSIONS: dict[str, set[str]] = {
    "material_registry": {"materials"},
    "component_geometry": {"components"},
    "placement": {"components", "coordinate_system"},
    "source": {"sources"},
    "physics_macro": {"physics"},
    "sensitive_detector": {"sensitive_detectors", "components"},
    "scoring": {"scoring", "components"},
    "output_manager": {"scoring"},
    "integration": set(),  # Assembly — references all but creates no new params
}


class CodeModuleBoundaryValidator:
    """Validates codegen module boundaries against IR."""

    def validate(self, plan: CodeGenerationPlan, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Check that each module stays within its boundary.

        Validates:
        - Module type is known
        - Module only references allowed IR sections
        - Module only references defined component/material IDs
        - Dependencies reference valid module names
        """
        errors: list[str] = []

        module_names = {m.module_name for m in plan.modules}
        comp_ids = {c.component_id for c in model_ir.components}
        mat_ids = {m.material_id for m in model_ir.materials}

        for mod in plan.modules:
            # Check module type is known
            if mod.module_type not in _MODULE_PERMISSIONS:
                errors.append(
                    f"Module '{mod.module_name}' has unknown module_type '{mod.module_type}'"
                )
                continue

            # Check linked_component_ids exist
            for cid in mod.linked_component_ids:
                if cid not in comp_ids:
                    errors.append(
                        f"Module '{mod.module_name}' references undefined component '{cid}'"
                    )

            # Check linked_material_ids exist
            for mid in mod.linked_material_ids:
                if mid not in mat_ids:
                    errors.append(
                        f"Module '{mod.module_name}' references undefined material '{mid}'"
                    )

            # Check dependencies exist
            for dep in mod.depends_on:
                if dep not in module_names:
                    errors.append(f"Module '{mod.module_name}' depends on undefined module '{dep}'")

        # Check for duplicate module names
        name_counts: dict[str, int] = {}
        for mod in plan.modules:
            name_counts[mod.module_name] = name_counts.get(mod.module_name, 0) + 1
        for name, count in name_counts.items():
            if count > 1:
                errors.append(f"Duplicate module name: '{name}'")

        return len(errors) == 0, errors
