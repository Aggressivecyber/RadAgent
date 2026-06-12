from __future__ import annotations

import os
from typing import Any

import httpx

from agent_core.config.environment import load_environment
from agent_core.models.schemas import ModelCallRequest, ModelProfile


def _httpx_client_kwargs(profile: ModelProfile) -> dict[str, Any]:
    env = load_environment()
    kwargs: dict[str, Any] = {
        "timeout": profile.timeout_s if _model_timeouts_enabled() else None,
        "trust_env": False,
    }
    if env.proxy:
        kwargs["proxy"] = env.proxy
    return kwargs


def _model_timeouts_enabled() -> bool:
    return os.getenv("RADAGENT_ENABLE_MODEL_TIMEOUTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _auth_headers(profile: ModelProfile) -> dict[str, str]:
    api_key = os.getenv(profile.api_key_env or "")
    if not api_key:
        raise RuntimeError(f"Missing API key env: {profile.api_key_env}")

    headers = {"Content-Type": "application/json"}
    if _is_mimo_model(profile):
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def call_openai_compatible_model(
    profile: ModelProfile,
    req: ModelCallRequest,
) -> tuple[str, dict, str]:
    if not profile.base_url:
        raise RuntimeError(f"Missing base_url for model tier {profile.tier}")

    payload = {
        "model": profile.model_name,
        "messages": [
            {"role": "system", "content": req.system_prompt},
            {"role": "user", "content": req.user_prompt},
        ],
        "temperature": req.temperature if req.temperature is not None else profile.temperature,
    }
    _apply_token_limit(payload, profile, req.max_tokens)
    _apply_mimo_thinking(payload, profile, req)

    if req.response_format == "json":
        payload["response_format"] = {"type": "json_object"}

    headers = _auth_headers(profile)

    url = profile.base_url.rstrip("/") + "/chat/completions"

    last_error = None
    for _ in range(profile.max_retries + 1):
        try:
            async with httpx.AsyncClient(**_httpx_client_kwargs(profile)) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                content = message["content"]
                usage = data.get("usage", {})
                reasoning_content = str(message.get("reasoning_content") or "")
                return content, usage, reasoning_content
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Model call failed after retries: {last_error}")


async def call_multi_turn_chat(
    profile: ModelProfile,
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Multi-turn chat with an OpenAI-compatible API.

    Args:
        profile: Model profile with endpoint and credentials.
        messages: Full message list (system + history + user).
        temperature: Override profile temperature.
        max_tokens: Override profile max_tokens.

    Returns:
        The assistant's response text.

    Raises:
        RuntimeError: After exhausting retries.
    """
    if not profile.base_url:
        raise RuntimeError(f"Missing base_url for model tier {profile.tier}")

    payload: dict[str, Any] = {
        "model": profile.model_name,
        "messages": messages,
        "temperature": temperature if temperature is not None else profile.temperature,
    }
    _apply_token_limit(payload, profile, max_tokens)
    _apply_mimo_thinking(payload, profile, None)

    headers = _auth_headers(profile)

    url = profile.base_url.rstrip("/") + "/chat/completions"

    last_error = None
    for _ in range(profile.max_retries + 1):
        try:
            async with httpx.AsyncClient(**_httpx_client_kwargs(profile)) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Multi-turn chat failed after retries: {last_error}")


async def call_openai_compatible_tools(
    profile: ModelProfile,
    req: ModelCallRequest,
) -> dict[str, Any]:
    """OpenAI-compatible call with native function calling (agentic loops).

    Returns a dict with: content, usage, reasoning_content, tool_calls,
    finish_reason. Uses ``req.messages`` when provided (full multi-turn),
    otherwise falls back to the system/user pair.
    """
    if not profile.base_url:
        raise RuntimeError(f"Missing base_url for model tier {profile.tier}")

    if req.messages:
        messages = [dict(m) for m in req.messages]
    else:
        messages = [
            {"role": "system", "content": req.system_prompt},
            {"role": "user", "content": req.user_prompt},
        ]

    payload: dict[str, Any] = {
        "model": profile.model_name,
        "messages": messages,
        "temperature": req.temperature if req.temperature is not None else profile.temperature,
    }
    _apply_token_limit(payload, profile, req.max_tokens)
    _apply_mimo_thinking(payload, profile, req)

    if req.tools:
        payload["tools"] = req.tools
        if req.tool_choice is not None:
            payload["tool_choice"] = req.tool_choice
        else:
            payload["tool_choice"] = "auto"

    headers = _auth_headers(profile)
    url = profile.base_url.rstrip("/") + "/chat/completions"

    last_error: Exception | None = None
    for _ in range(profile.max_retries + 1):
        try:
            async with httpx.AsyncClient(**_httpx_client_kwargs(profile)) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]
                message = choice["message"]
                tool_calls = message.get("tool_calls") or []
                # Normalize tool_calls so callers don't re-parse provider shapes.
                normalized: list[dict[str, Any]] = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function") or {}
                    normalized.append(
                        {
                            "id": tc.get("id", ""),
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", ""),
                        }
                    )
                return {
                    "content": str(message.get("content") or ""),
                    "usage": data.get("usage", {}),
                    "reasoning_content": str(message.get("reasoning_content") or ""),
                    "tool_calls": normalized,
                    "finish_reason": str(choice.get("finish_reason") or ""),
                }
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Tools model call failed after retries: {last_error}")


def _apply_token_limit(
    payload: dict[str, Any],
    profile: ModelProfile,
    max_tokens: int | None,
) -> None:
    token_limit = max_tokens if max_tokens is not None else profile.max_tokens
    if _is_mimo_model(profile):
        payload["max_completion_tokens"] = token_limit
    else:
        payload["max_tokens"] = token_limit


def _apply_mimo_thinking(
    payload: dict[str, Any],
    profile: ModelProfile,
    req: ModelCallRequest | None,
) -> None:
    if not _is_mimo_model(profile):
        return
    enabled = bool(req and req.metadata.get("enable_thinking"))
    payload["thinking"] = {"type": "enabled" if enabled else "disabled"}
    if enabled:
        payload.pop("temperature", None)


def _is_mimo_model(profile: ModelProfile) -> bool:
    model_name = str(profile.model_name).lower()
    base_url = str(profile.base_url or "").lower()
    return model_name.startswith("mimo-") or "xiaomimimo.com" in base_url
