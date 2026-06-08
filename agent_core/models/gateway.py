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
        self._record_model_call_start(req, profile)

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

            result = ModelCallResult(
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
            result = ModelCallResult(
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

        # Log the tool call
        self._log_tool_call(req, result, start)

        return result

    def _record_model_call_start(self, req: ModelCallRequest, profile: Any) -> None:
        """Record a job-scoped event before the provider call starts."""
        try:
            from agent_core.observability import record_event

            job_id = req.metadata.get("job_id")
            record_event(
                job_id=job_id,
                event_type="model_call_start",
                status="running",
                phase=str(req.task),
                module_name=str(req.metadata.get("module_name", "")),
                summary=f"{req.task} via {profile.provider}",
                metrics={
                    "system_prompt_chars": len(req.system_prompt or ""),
                    "user_prompt_chars": len(req.user_prompt or ""),
                },
                details={
                    "tier": str(req.tier),
                    "provider": str(profile.provider),
                    "model_name": profile.model_name,
                    "metadata": req.metadata,
                },
            )
        except Exception:
            pass

    def _log_tool_call(self, req: ModelCallRequest, result: ModelCallResult, start: float) -> None:
        """Record tool call to the global tool logger."""
        try:
            from agent_core.models.tool_logger import (
                ToolCallRecord,
                get_tool_logger,
            )

            tool_logger = get_tool_logger()
            record = ToolCallRecord(
                tool_name="llm_call",
                task=str(req.task),
                tier=str(req.tier),
                provider=str(result.provider),
                model_name=result.model_name,
                metadata=req.metadata,
                start_time=start,
                end_time=time.time(),
                latency_ms=result.latency_ms or 0.0,
                success=result.error is None,
                error=result.error,
                content_length=len(result.content) if result.content else 0,
            )
            tool_logger.record(record)
        except Exception:
            # Never let logging break the actual call
            pass

        try:
            from agent_core.observability import record_event

            job_id = req.metadata.get("job_id")
            record_event(
                job_id=job_id,
                event_type="model_call",
                status="failed" if result.error else "passed",
                phase=str(req.task),
                module_name=str(req.metadata.get("module_name", "")),
                summary=f"{req.task} via {result.provider}",
                duration_ms=result.latency_ms,
                metrics={
                    "content_length": len(result.content or ""),
                    "parsed_json": result.parsed_json is not None,
                },
                errors=[result.error] if result.error else [],
                details={
                    "tier": str(req.tier),
                    "provider": str(result.provider),
                    "model_name": result.model_name,
                    "metadata": req.metadata,
                },
            )
        except Exception:
            pass


def _safe_parse_json(content: str) -> dict[str, Any] | None:
    try:
        return json.loads(content)
    except Exception:
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            try:
                return json.loads(content[start_idx : end_idx + 1])
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
