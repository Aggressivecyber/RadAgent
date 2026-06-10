"""Tests for agent_core.models.registry — task-to-tier mapping."""

from __future__ import annotations

from agent_core.models.registry import (
    TASK_DEFAULT_TIER,
    THINKING_DEFAULT_BY_TASK,
    thinking_for_task,
    tier_for_task,
)
from agent_core.models.schemas import ModelTask, ModelTier


class TestTaskDefaultTier:
    """Verify task-to-tier mapping is correct."""

    def test_all_tasks_have_tier(self) -> None:
        """Every ModelTask should have a default tier."""
        for task in ModelTask:
            assert task in TASK_DEFAULT_TIER, f"Task {task} missing from TASK_DEFAULT_TIER"

    def test_all_tasks_have_thinking_default(self) -> None:
        """Every ModelTask should declare whether MiMo thinking mode is used."""
        for task in ModelTask:
            assert task in THINKING_DEFAULT_BY_TASK, (
                f"Task {task} missing from THINKING_DEFAULT_BY_TASK"
            )

    def test_intent_routing_uses_lite(self) -> None:
        """Intent routing should use LITE tier."""
        assert tier_for_task(ModelTask.INTENT_ROUTING) == ModelTier.LITE

    def test_simple_extraction_uses_lite(self) -> None:
        """Simple extraction should use LITE tier."""
        assert tier_for_task(ModelTask.SIMPLE_EXTRACTION) == ModelTier.LITE

    def test_context_summary_uses_lite(self) -> None:
        """Context summary should use LITE tier."""
        assert tier_for_task(ModelTask.CONTEXT_SUMMARY) == ModelTier.LITE

    def test_task_planning_uses_pro(self) -> None:
        """Task planning should use PRO tier."""
        assert tier_for_task(ModelTask.TASK_PLANNING) == ModelTier.PRO

    def test_g4_modeling_uses_pro(self) -> None:
        """G4 modeling should use PRO tier."""
        assert tier_for_task(ModelTask.G4_MODELING) == ModelTier.PRO

    def test_codegen_uses_pro(self) -> None:
        """Codegen should use PRO tier."""
        assert tier_for_task(ModelTask.CODEGEN) == ModelTier.PRO

    def test_gate_explanation_uses_max(self) -> None:
        """Gate explanation should use MAX tier."""
        assert tier_for_task(ModelTask.GATE_EXPLANATION) == ModelTier.MAX

    def test_final_review_uses_max(self) -> None:
        """Final review should use MAX tier."""
        assert tier_for_task(ModelTask.FINAL_REVIEW) == ModelTier.MAX

    def test_failure_diagnosis_uses_max(self) -> None:
        """Failure diagnosis should use MAX tier."""
        assert tier_for_task(ModelTask.FAILURE_DIAGNOSIS) == ModelTier.MAX

    def test_thinking_defaults_match_task_complexity(self) -> None:
        """Complex build/review tasks use thinking; routing and summaries do not."""
        assert thinking_for_task(ModelTask.INTENT_ROUTING) is False
        assert thinking_for_task(ModelTask.SIMPLE_EXTRACTION) is False
        assert thinking_for_task(ModelTask.CONTEXT_SUMMARY) is False
        assert thinking_for_task(ModelTask.HUMAN_CONFIRMATION) is False
        assert thinking_for_task(ModelTask.G4_MODELING) is True
        assert thinking_for_task(ModelTask.CODEGEN) is True
        assert thinking_for_task(ModelTask.FINAL_REVIEW) is True

    def test_lite_tasks_subset(self) -> None:
        """Verify the exact set of LITE tasks."""
        lite_tasks = {t for t, tier in TASK_DEFAULT_TIER.items() if tier == ModelTier.LITE}
        expected = {
            ModelTask.INTENT_ROUTING,
            ModelTask.SIMPLE_EXTRACTION,
            ModelTask.CONTEXT_SUMMARY,
            ModelTask.CREDIBILITY_ASSESSMENT,
        }
        assert lite_tasks == expected

    def test_max_tasks_subset(self) -> None:
        """Verify the exact set of MAX tasks."""
        max_tasks = {t for t, tier in TASK_DEFAULT_TIER.items() if tier == ModelTier.MAX}
        expected = {
            ModelTask.GATE_EXPLANATION,
            ModelTask.FINAL_REVIEW,
            ModelTask.FAILURE_DIAGNOSIS,
        }
        assert max_tasks == expected
