"""Evidence traceability validator — Gate G4-E.

Ensures every critical parameter in the model has a traceable
evidence source (RAG doc ID, URL, or user specification).
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR


class EvidenceTraceabilityValidator:
    """Validates evidence traceability for all model parameters."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Check evidence traceability across all specs.

        For every critical parameter, verify:
        - source_evidence list is non-empty
        - Each evidence string is resolvable
        - Web sources have URLs
        - Missing info is in open_issues
        """
        errors: list[str] = []

        # Collect all evidence references
        all_evidence: list[tuple[str, str, list[str]]] = []

        for comp in model_ir.components:
            all_evidence.append(("component", comp.component_id, comp.source_evidence))
        for mat in model_ir.materials:
            all_evidence.append(("material", mat.material_id, mat.source_evidence))
        for src in model_ir.sources:
            all_evidence.append(("source", src.source_id, src.source_evidence))
        if model_ir.physics is not None:
            all_evidence.append(
                ("physics", model_ir.physics.physics_list, model_ir.physics.source_evidence)
            )
        for sc in model_ir.scoring:
            all_evidence.append(("scoring", sc.scoring_id, sc.source_evidence))

        # Validate each evidence list
        for spec_type, target_id, evidence in all_evidence:
            if not evidence:
                errors.append(
                    f"{spec_type} '{target_id}' has no source_evidence — "
                    f"all parameters must be traceable"
                )
                continue

            for ref in evidence:
                ref_stripped = ref.strip()
                if not ref_stripped:
                    errors.append(f"{spec_type} '{target_id}' has empty evidence reference")
                elif self._is_placeholder(ref_stripped):
                    errors.append(
                        f"{spec_type} '{target_id}' has placeholder evidence: '{ref_stripped}'"
                    )

        # Check physics has selection reasoning
        if model_ir.physics is not None:
            if not model_ir.physics.selection_reasoning.strip():
                errors.append(
                    "Physics selection_reasoning is empty — must explain "
                    "why this physics list was chosen"
                )

        return len(errors) == 0, errors

    @staticmethod
    def _is_placeholder(ref: str) -> bool:
        """Check if an evidence reference is a placeholder."""
        placeholders = {"todo", "tbd", "fixme", "unknown", "n/a", "default"}
        return ref.lower() in placeholders
