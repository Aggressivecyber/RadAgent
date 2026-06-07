"""Geometry interface validator — Gate G4-C.

Validates inter-component relationships: parent-child legality,
no orphan components, single world root, interface consistency,
and interface-to-hierarchy alignment.
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
        - Interface relationships align with mother_volume hierarchy
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

        # 6. Interface-hierarchy consistency
        #    "contains" interface should match mother_volume relationships
        hierarchy_errors = self._check_interface_hierarchy(model_ir)
        errors.extend(hierarchy_errors)

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

    def _check_interface_hierarchy(self, model_ir: G4ModelIR) -> list[str]:
        """Verify 'contains' interfaces match mother_volume hierarchy.

        If an interface says A 'contains' B, then either:
        - B.mother_volume == A (direct containment), OR
        - B is a descendant of A (transitive containment)
        """
        errors: list[str] = []

        # Build parent map
        parent_map: dict[str, str | None] = {}
        for comp in model_ir.components:
            parent_map[comp.component_id] = comp.mother_volume

        for iface in model_ir.interfaces:
            if iface.relationship == "contains":
                a = iface.component_a
                b = iface.component_b

                # Verify B is contained by A (direct or transitive)
                if not self._is_ancestor(a, b, parent_map):
                    errors.append(
                        f"Interface '{iface.interface_id}' says {a} 'contains' "
                        f"{b}, but {b} is not a descendant of {a} in the "
                        f"mother_volume hierarchy (mother={parent_map.get(b)})"
                    )

            elif iface.relationship == "stacked_above":
                # Stacked components should share the same mother_volume
                a_mother = parent_map.get(iface.component_a)
                b_mother = parent_map.get(iface.component_b)
                if a_mother and b_mother and a_mother != b_mother:
                    errors.append(
                        f"Interface '{iface.interface_id}' says "
                        f"{iface.component_a} is 'stacked_above' "
                        f"{iface.component_b}, but they have different "
                        f"mother volumes ({a_mother} vs {b_mother})"
                    )

        return errors

    def _is_ancestor(
        self,
        ancestor_id: str,
        descendant_id: str,
        parent_map: dict[str, str | None],
    ) -> bool:
        """Check if ancestor_id is an ancestor of descendant_id."""
        current = descendant_id
        visited: set[str] = set()
        while current is not None:
            if current == ancestor_id:
                return True
            if current in visited:
                break  # Cycle protection
            visited.add(current)
            next_parent = parent_map.get(current)
            if next_parent is None:
                break
            current = next_parent
        return False
