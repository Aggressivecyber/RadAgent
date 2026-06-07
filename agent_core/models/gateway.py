from __future__ import annotations

import json
import time
from typing import Any

from agent_core.models.client import call_openai_compatible_model
from agent_core.models.config import load_model_profiles
from agent_core.models.registry import tier_for_task
from agent_core.models.schemas import (
    ModelCallRequest,
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


class ModelGateway:
    def __init__(self):
        self.profiles = load_model_profiles()

    async def call(
        self,
        task: ModelTask,
        system_prompt: str,
        user_prompt: str,
        *,
        tier: ModelTier | None = None,
        response_format: str = "text",
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelCallResult:
        selected_tier = tier or tier_for_task(task)
        profile = self.profiles[selected_tier]

        req = ModelCallRequest(
            task=task,
            tier=selected_tier,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata or {},
        )

        start = time.time()

        try:
            if profile.provider == ModelProvider.MOCK:
                from agent_core.models.mock import call_mock_model
                mock_result = call_mock_model(req.task, req.metadata)
                content = json.dumps(mock_result.parsed_json or {})
                parsed_json = mock_result.parsed_json
                usage = {"mock": True}
            elif profile.provider == ModelProvider.OPENAI_COMPATIBLE:
                content, usage = await call_openai_compatible_model(profile, req)
                parsed_json = None
                if response_format == "json":
                    parsed_json = _safe_parse_json(content)
            else:
                raise NotImplementedError(f"Unsupported provider: {profile.provider}")

            return ModelCallResult(
                task=task,
                tier=selected_tier,
                provider=profile.provider,
                model_name=profile.model_name,
                content=content,
                parsed_json=parsed_json,
                usage=usage,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return ModelCallResult(
                task=task,
                tier=selected_tier,
                provider=profile.provider,
                model_name=profile.model_name,
                content="",
                parsed_json=None,
                usage={},
                latency_ms=(time.time() - start) * 1000,
                error=str(exc),
            )


def _safe_parse_json(content: str) -> dict[str, Any] | None:
    try:
        return json.loads(content)
    except Exception:
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            try:
                return json.loads(content[start_idx:end_idx + 1])
            except Exception:
                return None
    return None


_gateway: ModelGateway | None = None


def get_model_gateway() -> ModelGateway:
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway


def reset_model_gateway() -> None:
    """Reset the singleton (for testing)."""
    global _gateway
    _gateway = None
