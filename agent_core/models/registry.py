from __future__ import annotations

from agent_core.models.schemas import ModelTask, ModelTier

TASK_DEFAULT_TIER: dict[ModelTask, ModelTier] = {
    ModelTask.INTENT_ROUTING: ModelTier.LITE,
    ModelTask.SIMPLE_EXTRACTION: ModelTier.LITE,
    ModelTask.CONTEXT_SUMMARY: ModelTier.LITE,
    ModelTask.TASK_PLANNING: ModelTier.PRO,
    ModelTask.MODEL_READINESS: ModelTier.PRO,
    ModelTask.G4_MODELING: ModelTier.PRO,
    ModelTask.HUMAN_CONFIRMATION: ModelTier.PRO,
    ModelTask.CODEGEN: ModelTier.PRO,
    ModelTask.GATE_EXPLANATION: ModelTier.MAX,
    ModelTask.FINAL_REVIEW: ModelTier.MAX,
    ModelTask.FAILURE_DIAGNOSIS: ModelTier.MAX,
}


def tier_for_task(task: ModelTask) -> ModelTier:
    return TASK_DEFAULT_TIER[task]
