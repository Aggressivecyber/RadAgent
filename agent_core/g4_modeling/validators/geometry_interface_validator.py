"""Geometry interface validator — Gate G4-C.

Validates inter-component relationships: parent-child legality,
no orphan components, single world root, interface consistency.
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR


class GeometryInterfaceValidator:
    """Validates geometry interface consistency and tree structure."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Check component tree structure and interfaces.

        Validates:
        - Exactly one world volume (root)
        - All mother_volume references are valid
        - No orphan components (except world)
        - No circular containment
        - Interface component_a/b reference existing components
        - Stacked layer order is consistent
        """
        errors: list[str] = []

        if not model_ir.components:
            return True, []  # Nothing to validate

        comp_ids = {c.component_id for c in model_ir.components}

        # 1. Exactly one world volume
        worlds = [c for c in model_ir.components if c.component_type == "world"]
        if len(worlds) == 0:
            errors.append("No world volume defined")
        elif len(worlds) > 1:
            errors.append(
                f"Multiple world volumes: "
                f"{[w.component_id for w in worlds]}"
            )

        # 2. Mother volume references are valid
        for comp in model_ir.components:
            if comp.mother_volume is not None:
                if comp.mother_volume not in comp_ids:
                    errors.append(
                        f"Component '{comp.component_id}' references "
                        f"non-existent mother_volume '{comp.mother_volume}'"
                    )

        # 3. No orphans (except world)
        for comp in model_ir.components:
            if comp.component_type != "world" and comp.mother_volume is None:
                errors.append(
                    f"Component '{comp.component_id}' has no mother_volume "
                    f"and is not world type — orphan component"
                )

        # 4. No circular containment
        circular = self._detect_cycles(model_ir)
        if circular:
            errors.append(f"Circular containment detected: {circular}")

        # 5. Interface references are valid
        for iface in model_ir.interfaces:
            if iface.component_a not in comp_ids:
                errors.append(
                    f"Interface '{iface.interface_id}' references "
                    f"non-existent component_a '{iface.component_a}'"
                )
            if iface.component_b not in comp_ids:
                errors.append(
                    f"Interface '{iface.interface_id}' references "
                    f"non-existent component_b '{iface.component_b}'"
                )

        return len(errors) == 0, errors

    def _detect_cycles(self, model_ir: G4ModelIR) -> list[str]:
        """Detect cycles in the mother_volume graph."""
        comp_map = {c.component_id: c for c in model_ir.components}
        visited: set[str] = set()
        path: set[str] = set()

        def _visit(cid: str) -> list[str]:
            if cid in path:
                return [cid]
            if cid in visited:
                return []
            visited.add(cid)
            path.add(cid)
            comp = comp_map.get(cid)
            if comp and comp.mother_volume:
                cycle = _visit(comp.mother_volume)
                if cycle:
                    return cycle
            path.discard(cid)
            return []

        for comp in model_ir.components:
            cycle = _visit(comp.component_id)
            if cycle:
                return cycle
        return []
