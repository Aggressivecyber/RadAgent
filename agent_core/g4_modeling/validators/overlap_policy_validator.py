"""Overlap policy validator — Gate G4-D.

Ensures overlap checks are enabled and no geometric overlaps
exist between components unless explicitly waived.
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR


class OverlapPolicyValidator:
    """Validates overlap checking policy and detects potential overlaps."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Check overlap policy compliance.

        Validates:
        - All G4PVPlacement calls should have checkOverlaps=true
        - No components overlap unless explicitly allowed
        - Interface overlap_allowed flags are consistent
        """
        errors: list[str] = []

        if not model_ir.components:
            return True, []

        # 1. Check interfaces have overlap_check_enabled=True
        for iface in model_ir.interfaces:
            if not iface.overlap_check_enabled:
                errors.append(
                    f"Interface '{iface.interface_id}' between "
                    f"'{iface.component_a}' and '{iface.component_b}' "
                    f"has overlap_check_enabled=False — must be True "
                    f"in realistic mode"
                )

        # 2. Check that no interface declares overlap_allowed=True
        #    without a matching approved_simplification
        approved = set(model_ir.simplification_policy.approved_simplifications)
        for iface in model_ir.interfaces:
            if iface.overlap_allowed:
                desc = f"overlap allowed: {iface.component_a}/{iface.component_b}"
                if desc not in approved and not model_ir.simplification_policy.allow_simplification:
                    errors.append(
                        f"Interface '{iface.interface_id}' allows overlap "
                        f"without approved simplification"
                    )

        # 3. Heuristic overlap detection for box components
        box_overlaps = self._detect_box_overlaps(model_ir)
        for msg in box_overlaps:
            if msg not in approved:
                errors.append(msg)

        return len(errors) == 0, errors

    def _detect_box_overlaps(self, model_ir: G4ModelIR) -> list[str]:
        """Simple AABB overlap detection for box components.

        Only checks sibling components (same mother_volume).
        """
        warnings: list[str] = []

        # Group by mother_volume
        siblings: dict[str | None, list] = {}
        for comp in model_ir.components:
            mother = comp.mother_volume
            siblings.setdefault(mother, []).append(comp)

        # Check each group of siblings for overlaps
        for mother, children in siblings.items():
            if len(children) < 2:
                continue
            for i in range(len(children)):
                for j in range(i + 1, len(children)):
                    a = children[i]
                    b = children[j]
                    if a.geometry_type != "box" or b.geometry_type != "box":
                        continue  # Only check box-box for now
                    if self._boxes_overlap(a, b):
                        warnings.append(
                            f"Potential overlap between siblings "
                            f"'{a.component_id}' and '{b.component_id}' "
                            f"(mother: {mother})"
                        )
        return warnings

    def _boxes_overlap(self, a: object, b: object) -> bool:
        """Check if two box components have overlapping AABBs.

        Very conservative: uses axis-aligned bounding box check
        based on dimensions and placement position.
        """
        # dx/dy/dz in G4ModelIR are full lengths; half_* fields are already half lengths.
        a_dims = getattr(a, "dimensions", {})
        b_dims = getattr(b, "dimensions", {})
        a_pos = getattr(a, "placement", None)
        b_pos = getattr(b, "placement", None)

        if not a_dims or not b_dims or a_pos is None or b_pos is None:
            return False

        a_xyz = getattr(a_pos, "position", [0, 0, 0])
        b_xyz = getattr(b_pos, "position", [0, 0, 0])

        a_hx = a_dims.get("half_x", a_dims.get("dx", 0) / 2.0)
        a_hy = a_dims.get("half_y", a_dims.get("dy", 0) / 2.0)
        a_hz = a_dims.get("half_z", a_dims.get("dz", 0) / 2.0)
        b_hx = b_dims.get("half_x", b_dims.get("dx", 0) / 2.0)
        b_hy = b_dims.get("half_y", b_dims.get("dy", 0) / 2.0)
        b_hz = b_dims.get("half_z", b_dims.get("dz", 0) / 2.0)

        # AABB overlap test: separation on any axis means the boxes do not overlap.
        for ap, ah, bp, bh in zip(
            a_xyz,
            [a_hx, a_hy, a_hz],
            b_xyz,
            [b_hx, b_hy, b_hz],
        ):
            if abs(ap - bp) >= (ah + bh):
                return False

        return True
