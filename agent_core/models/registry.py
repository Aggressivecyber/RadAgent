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
    ModelTask.CREDIBILITY_ASSESSMENT: ModelTier.LITE,
    ModelTask.FINAL_REVIEW: ModelTier.MAX,
    ModelTask.FAILURE_DIAGNOSIS: ModelTier.MAX,
    ModelTask.SIMULATION_BRIEFING: ModelTier.LITE,
}


THINKING_DEFAULT_BY_TASK: dict[ModelTask, bool] = {
    ModelTask.INTENT_ROUTING: False,
    ModelTask.SIMPLE_EXTRACTION: False,
    ModelTask.CONTEXT_SUMMARY: False,
    ModelTask.TASK_PLANNING: True,
    ModelTask.MODEL_READINESS: True,
    ModelTask.G4_MODELING: True,
    ModelTask.HUMAN_CONFIRMATION: False,
    ModelTask.CODEGEN: True,
    ModelTask.GATE_EXPLANATION: True,
    ModelTask.CREDIBILITY_ASSESSMENT: False,
    ModelTask.FINAL_REVIEW: True,
    ModelTask.FAILURE_DIAGNOSIS: True,
    ModelTask.SIMULATION_BRIEFING: False,
}


def tier_for_task(task: ModelTask) -> ModelTier:
    return TASK_DEFAULT_TIER[task]


def thinking_for_task(task: ModelTask) -> bool:
    return THINKING_DEFAULT_BY_TASK[task]
