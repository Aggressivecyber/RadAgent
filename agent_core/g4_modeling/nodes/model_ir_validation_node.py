"""Model IR validation node — runs all validators on the G4ModelIR.

Deterministic node: executes the full validator suite and records
results. Returns errors that block progression or warnings that
may require attention.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState
from agent_core.g4_modeling.validators import (
    CoordinateConsistencyValidator,
    EvidenceTraceabilityValidator,
    GeometryInterfaceValidator,
    MaterialCompletenessValidator,
    ModelCompletenessValidator,
    NoSimplificationValidator,
    OverlapPolicyValidator,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class _ValidatorProto(Protocol):
    """Protocol for validators that check G4ModelIR."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]: ...


async def model_ir_validation_node(state: RadiationAgentState) -> dict[str, Any]:
    """Run all validators on the G4ModelIR.

    Reads: g4_model_ir
    Writes: model_ir_errors, persists validation report
    """
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    all_errors: list[str] = []
    validation_results: list[dict[str, Any]] = []

    # Run each validator
    validators: list[tuple[str, _ValidatorProto]] = [
        ("ModelCompleteness", ModelCompletenessValidator()),
        ("NoSimplification", NoSimplificationValidator()),
        ("CoordinateConsistency", CoordinateConsistencyValidator()),
        ("MaterialCompleteness", MaterialCompletenessValidator()),
        ("GeometryInterface", GeometryInterfaceValidator()),
        ("OverlapPolicy", OverlapPolicyValidator()),
        ("EvidenceTraceability", EvidenceTraceabilityValidator()),
    ]

    for name, validator_instance in validators:
        try:
            passed, errors = validator_instance.validate(model_ir)
            validation_results.append(
                {
                    "validator": name,
                    "passed": passed,
                    "errors": errors,
                }
            )
            if not passed:
                all_errors.extend(errors)
        except Exception as exc:
            msg = f"{name} validator crashed: {exc}"
            logger.error(msg)
            all_errors.append(msg)
            validation_results.append(
                {
                    "validator": name,
                    "passed": False,
                    "errors": [msg],
                }
            )

    model_ir.ledger.add_entry(
        node_name="model_ir_validation_node",
        action="validate",
        target_id=model_ir.model_ir_id,
        description=f"Ran {len(validators)} validators: "
        f"{sum(1 for r in validation_results if r['passed'])} passed, "
        f"{len(all_errors)} errors",
        modified_fields=[],
    )

    # Persist validation report
    if job_id:
        model_ir_dir = get_stage_dir(job_id, "03_model_ir")
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        report_file = model_ir_dir / "validation_report.json"
        report_file.write_text(
            json.dumps(
                {
                    "model_ir_id": model_ir.model_ir_id,
                    "total_validators": len(validators),
                    "passed": sum(1 for r in validation_results if r["passed"]),
                    "failed": sum(1 for r in validation_results if not r["passed"]),
                    "total_errors": len(all_errors),
                    "results": validation_results,
                },
                indent=2,
                ensure_ascii=False,
            )
        )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "model_ir_errors": all_errors,
        "current_node": "model_ir_validation_node",
    }
