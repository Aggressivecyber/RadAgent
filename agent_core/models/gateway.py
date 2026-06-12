from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_core.models.client import call_openai_compatible_model
from agent_core.models.config import load_model_profiles
from agent_core.models.registry import thinking_for_task, tier_for_task
from agent_core.models.schemas import (
    ModelCallRequest,
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)
from agent_core.workspace.io import get_job_dir, get_workspace_root

logger = logging.getLogger(__name__)


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
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> ModelCallResult:
        selected_tier = tier or tier_for_task(task)
        profile = self.profiles[selected_tier]

        request_metadata = _with_default_thinking(task, metadata or {})

        req = ModelCallRequest(
            task=task,
            tier=selected_tier,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=request_metadata,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )

        start = time.time()
        call_id = uuid4().hex
        req.metadata["model_call_id"] = call_id
        transcript_path = self._write_model_call_transcript(
            req=req,
            profile=profile,
            call_id=call_id,
            status="running",
            started_at=start,
        )
        self._record_model_call_start(req, profile, transcript_path=transcript_path)

        try:
            if profile.provider == ModelProvider.MOCK:
                from agent_core.models.mock import call_mock_model

                mock_result = call_mock_model(req.task, req.metadata)
                content = json.dumps(mock_result.parsed_json or {})
                parsed_json = mock_result.parsed_json
                usage = {"mock": True}
                reasoning_content = ""
                tool_calls: list[dict[str, Any]] = []
                finish_reason = "stop"
            elif profile.provider == ModelProvider.OPENAI_COMPATIBLE and req.tools:
                from agent_core.models.client import call_openai_compatible_tools

                if _model_timeouts_enabled():
                    tools_result = await asyncio.wait_for(
                        call_openai_compatible_tools(profile, req),
                        timeout=_provider_call_deadline_s(profile),
                    )
                else:
                    tools_result = await call_openai_compatible_tools(profile, req)
                content = tools_result["content"]
                usage = tools_result["usage"]
                reasoning_content = tools_result["reasoning_content"]
                tool_calls = tools_result["tool_calls"]
                finish_reason = tools_result["finish_reason"]
                parsed_json = None
            elif profile.provider == ModelProvider.OPENAI_COMPATIBLE:
                if _model_timeouts_enabled():
                    provider_result = await asyncio.wait_for(
                        call_openai_compatible_model(profile, req),
                        timeout=_provider_call_deadline_s(profile),
                    )
                else:
                    provider_result = await call_openai_compatible_model(profile, req)
                content, usage, reasoning_content = _normalize_provider_result(
                    provider_result
                )
                parsed_json = None
                if response_format == "json":
                    parsed_json = _safe_parse_json(content)
                tool_calls = []
                finish_reason = "stop"
            else:
                raise NotImplementedError(f"Unsupported provider: {profile.provider}")

            result = ModelCallResult(
                task=task,
                tier=selected_tier,
                provider=profile.provider,
                model_name=profile.model_name,
                content=content,
                parsed_json=parsed_json,
                reasoning_content=reasoning_content,
                usage=usage,
                latency_ms=(time.time() - start) * 1000,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        except TimeoutError:
            result = ModelCallResult(
                task=task,
                tier=selected_tier,
                provider=profile.provider,
                model_name=profile.model_name,
                content="",
                parsed_json=None,
                usage={},
                latency_ms=(time.time() - start) * 1000,
                error=(
                    "Model call timed out after "
                    f"{_provider_call_deadline_s(profile):.1f}s"
                ),
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
        self._write_model_call_transcript(
            req=req,
            profile=profile,
            call_id=call_id,
            status="failed" if result.error else "passed",
            started_at=start,
            result=result,
        )

        self._log_tool_call(req, result, start, transcript_path=transcript_path)

        return result

    def _record_model_call_start(
        self,
        req: ModelCallRequest,
        profile: Any,
        *,
        transcript_path: str,
    ) -> None:
        """Record a job-scoped event before the provider call starts."""
        try:
            from agent_core.observability import record_event
            from agent_core.observability.redaction import artifact_ref

            job_id = req.metadata.get("job_id")
            record_event(
                job_id=job_id,
                event_type="model_call_start",
                status="running",
                phase=str(req.task),
                module_name=str(req.metadata.get("module_name", "")),
                summary=f"{req.task} via {profile.provider}",
                artifacts=[artifact_ref(transcript_path)] if transcript_path else [],
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
        except Exception as exc:
            logger.warning("Failed to record model_call_start event: %s", exc)

    def _log_tool_call(
        self,
        req: ModelCallRequest,
        result: ModelCallResult,
        start: float,
        *,
        transcript_path: str,
    ) -> None:
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
                metadata={**req.metadata, "transcript_path": transcript_path},
                start_time=start,
                end_time=time.time(),
                latency_ms=result.latency_ms or 0.0,
                success=result.error is None,
                error=result.error,
                content_length=len(result.content) if result.content else 0,
            )
            tool_logger.record(record)
        except Exception as exc:
            logger.warning("Failed to write model tool-call log: %s", exc)

        try:
            from agent_core.observability import record_event
            from agent_core.observability.redaction import artifact_ref

            job_id = req.metadata.get("job_id")
            record_event(
                job_id=job_id,
                event_type="model_call",
                status="failed" if result.error else "passed",
                phase=str(req.task),
                module_name=str(req.metadata.get("module_name", "")),
                summary=f"{req.task} via {result.provider}",
                duration_ms=result.latency_ms,
                artifacts=[artifact_ref(transcript_path)] if transcript_path else [],
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
        except Exception as exc:
            logger.warning("Failed to record model_call event: %s", exc)

    def _write_model_call_transcript(
        self,
        *,
        req: ModelCallRequest,
        profile: Any,
        call_id: str,
        status: str,
        started_at: float,
        result: ModelCallResult | None = None,
    ) -> str:
        """Persist full prompt/response context for job-scoped debugging."""
        job_id = str(req.metadata.get("job_id") or "")
        try:
            from agent_core.observability.redaction import sanitize

            base_dir = get_job_dir(job_id) if job_id else get_workspace_root()
            log_dir = base_dir / "logs" / "model_calls"
            log_dir.mkdir(parents=True, exist_ok=True)
            module_name = _safe_path_token(str(req.metadata.get("module_name", "model")))
            task_name = _safe_path_token(str(req.task).split(".")[-1] or "task")
            relative_path = f"logs/model_calls/{call_id}_{module_name}_{task_name}.json"
            path = base_dir / relative_path
            payload: dict[str, Any] = {
                "job_id": job_id,
                "model_call_id": call_id,
                "status": status,
                "task": str(req.task),
                "tier": str(req.tier),
                "provider": str(profile.provider),
                "model_name": profile.model_name,
                "metadata": req.metadata,
                "started_at_unix": started_at,
                "updated_at_unix": time.time(),
                "request": {
                    "response_format": req.response_format,
                    "temperature": req.temperature,
                    "max_tokens": req.max_tokens,
                    "system_prompt": req.system_prompt,
                    "user_prompt": req.user_prompt,
                    "messages": req.messages,
                    "tools": req.tools,
                    "tool_choice": req.tool_choice,
                },
            }
            if result is not None:
                payload["result"] = {
                    "error": result.error,
                    "latency_ms": result.latency_ms,
                    "usage": result.usage,
                    "content": result.content,
                    "parsed_json": result.parsed_json,
                    "reasoning_content": result.reasoning_content,
                    "tool_calls": result.tool_calls,
                    "finish_reason": result.finish_reason,
                }
            path.write_text(
                json.dumps(sanitize(payload, max_string=500000), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _write_active_model_call(base_dir, payload, relative_path)
            return relative_path
        except Exception as exc:
            logger.warning("Failed to write model call transcript: %s", exc)
            return ""


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


def _normalize_provider_result(raw: Any) -> tuple[str, dict[str, Any], str]:
    if isinstance(raw, tuple) and len(raw) == 3:
        content, usage, reasoning_content = raw
        return str(content), dict(usage or {}), str(reasoning_content or "")
    if isinstance(raw, tuple) and len(raw) == 2:
        content, usage = raw
        return str(content), dict(usage or {}), ""
    raise ValueError("Provider call must return (content, usage) or (content, usage, reasoning)")


def _provider_call_deadline_s(profile: Any) -> float:
    timeout_s = float(getattr(profile, "timeout_s", 60.0) or 60.0)
    max_retries = int(getattr(profile, "max_retries", 0) or 0)
    return max(1.0, timeout_s * (max_retries + 1) + 5.0)


def _with_default_thinking(task: ModelTask, metadata: dict[str, Any]) -> dict[str, Any]:
    merged = dict(metadata)
    merged.setdefault("enable_thinking", thinking_for_task(task))
    return merged


def _model_timeouts_enabled() -> bool:
    return os.getenv("RADAGENT_ENABLE_MODEL_TIMEOUTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _safe_path_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return token[:80] or "model"


def _write_active_model_call(job_dir: Path, payload: dict[str, Any], relative_path: str) -> None:
    active_path = job_dir / "logs" / "active_model_call.json"
    active = {
        "job_id": payload.get("job_id", ""),
        "model_call_id": payload.get("model_call_id", ""),
        "status": payload.get("status", ""),
        "task": payload.get("task", ""),
        "tier": payload.get("tier", ""),
        "provider": payload.get("provider", ""),
        "model_name": payload.get("model_name", ""),
        "module_name": payload.get("metadata", {}).get("module_name", ""),
        "started_at_unix": payload.get("started_at_unix"),
        "updated_at_unix": payload.get("updated_at_unix"),
        "transcript_path": relative_path,
    }
    active_path.write_text(json.dumps(active, indent=2, ensure_ascii=False), encoding="utf-8")


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
