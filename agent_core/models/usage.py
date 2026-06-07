"""Usage tracking utilities for the model gateway."""

from __future__ import annotations

import logging

from agent_core.models.schemas import ModelCallResult

logger = logging.getLogger(__name__)


def log_model_usage(result: ModelCallResult) -> None:
    """Log model call usage for cost tracking."""
    usage = result.usage
    if not usage:
        return

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    logger.info(
        "Model call: task=%s tier=%s model=%s latency=%.0fms "
        "prompt_tokens=%d completion_tokens=%d total_tokens=%d",
        result.task.value,
        result.tier.value,
        result.model_name,
        result.latency_ms or 0,
        prompt_tokens,
        completion_tokens,
        total_tokens,
    )
