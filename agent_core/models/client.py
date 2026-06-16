from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from agent_core.config.environment import load_environment
from agent_core.models.schemas import ModelCallRequest, ModelProfile

_CLIENTS: dict[tuple[int, str, str, float | None], httpx.AsyncClient] = {}


def _httpx_client_kwargs(profile: ModelProfile) -> dict[str, Any]:
    env = load_environment()
    kwargs: dict[str, Any] = {
        "timeout": profile.timeout_s if _model_timeouts_enabled() else None,
        "limits": httpx.Limits(max_keepalive_connections=20, max_connections=40),
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


def _model_streaming_enabled() -> bool:
    return os.getenv("RADAGENT_ENABLE_MODEL_STREAMING", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
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


async def _get_http_client(profile: ModelProfile) -> httpx.AsyncClient:
    env = load_environment()
    loop = asyncio.get_running_loop()
    timeout = profile.timeout_s if _model_timeouts_enabled() else None
    key = (id(loop), str(profile.base_url or ""), str(env.proxy or ""), timeout)
    client = _CLIENTS.get(key)
    if client is None:
        client = httpx.AsyncClient(**_httpx_client_kwargs(profile))
        _CLIENTS[key] = client
    return client


def reset_model_http_clients() -> None:
    """Close and clear cached model HTTP clients.

    The test suite and configuration reload paths need deterministic client
    state. This function is intentionally sync so fixtures can call it from
    either async or non-async contexts.
    """
    clients = list(_CLIENTS.values())
    _CLIENTS.clear()
    if not clients:
        return

    async def _close_all() -> None:
        await asyncio.gather(
            *(client.aclose() for client in clients if hasattr(client, "aclose")),
            return_exceptions=True,
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_close_all())
    else:
        loop.create_task(_close_all())


async def _post_json_with_retries(
    profile: ModelProfile,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    failure_label: str,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(profile.max_retries + 1):
        try:
            client = await _get_http_client(profile)
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_error = exc
            if attempt >= profile.max_retries or not _is_retryable_model_error(exc):
                break
            await asyncio.sleep(_retry_delay_s(exc, attempt))

    raise RuntimeError(f"{failure_label} failed after retries: {last_error}")


async def _stream_json_with_retries(
    profile: ModelProfile,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    failure_label: str,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(profile.max_retries + 1):
        try:
            client = await _get_http_client(profile)
            return await _stream_chat_completion(
                client,
                url,
                headers=headers,
                payload=payload,
                on_chunk=on_chunk,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= profile.max_retries or not _is_retryable_model_error(exc):
                break
            await asyncio.sleep(_retry_delay_s(exc, attempt))

    raise RuntimeError(f"{failure_label} failed after retries: {last_error}")


async def _stream_chat_completion(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    on_chunk: Callable[[str], Awaitable[None]] | None,
) -> dict[str, Any]:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_call_parts: dict[int, dict[str, Any]] = {}
    usage: dict[str, Any] = {}
    finish_reason = ""
    stream_payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    async with client.stream("POST", url, headers=headers, json=stream_payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                line = line.removeprefix("data:").strip()
            if not line or line == "[DONE]":
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(chunk.get("usage"), dict):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                delta = {}
            text = str(delta.get("content") or "")
            reasoning = str(delta.get("reasoning_content") or "")
            if text:
                content_parts.append(text)
                if on_chunk:
                    await on_chunk(text)
            if reasoning:
                reasoning_parts.append(reasoning)
            for tool_delta in delta.get("tool_calls") or []:
                if not isinstance(tool_delta, dict):
                    continue
                index = int(tool_delta.get("index") or 0)
                current = tool_call_parts.setdefault(
                    index,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tool_delta.get("id"):
                    current["id"] = str(tool_delta["id"])
                if tool_delta.get("type"):
                    current["type"] = str(tool_delta["type"])
                function_delta = tool_delta.get("function") or {}
                if isinstance(function_delta, dict):
                    function = current.setdefault("function", {"name": "", "arguments": ""})
                    if not isinstance(function, dict):
                        function = {"name": "", "arguments": ""}
                        current["function"] = function
                    progress_bits: list[str] = []
                    if function_delta.get("name"):
                        name_delta = str(function_delta["name"])
                        function["name"] = name_delta
                        progress_bits.append(f"准备调用工具 {name_delta}")
                    if function_delta.get("arguments"):
                        argument_delta = str(function_delta["arguments"])
                        function["arguments"] = str(function.get("arguments") or "") + argument_delta
                        progress_bits.append(argument_delta)
                    if on_chunk and progress_bits:
                        await on_chunk(" ".join(progress_bits))
            finish_reason = str(choice.get("finish_reason") or finish_reason)
    tool_calls = [tool_call_parts[index] for index in sorted(tool_call_parts)]
    return {
        "choices": [
            {
                "message": {
                    "content": "".join(content_parts),
                    "reasoning_content": "".join(reasoning_parts),
                    "tool_calls": tool_calls,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }

def _is_retryable_model_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 408 or status_code == 429 or 500 <= status_code <= 599
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _retry_delay_s(exc: Exception, attempt: int) -> float:
    retry_after = _retry_after_s(exc)
    if retry_after is not None:
        return retry_after
    return float(min(2**attempt, 8))


def _retry_after_s(exc: Exception) -> float | None:
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    raw = exc.response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return max(0.0, min(value, 60.0))


async def call_openai_compatible_model(
    profile: ModelProfile,
    req: ModelCallRequest,
    *,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
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

    if on_chunk and _model_streaming_enabled():
        try:
            data = await _stream_json_with_retries(
                profile,
                url,
                headers=headers,
                payload=payload,
                failure_label="Model call",
                on_chunk=on_chunk,
            )
        except RuntimeError:
            data = await _post_json_with_retries(
                profile,
                url,
                headers=headers,
                payload=payload,
                failure_label="Model call",
            )
    else:
        data = await _post_json_with_retries(
            profile,
            url,
            headers=headers,
            payload=payload,
            failure_label="Model call",
        )
    message = data["choices"][0]["message"]
    content = message["content"]
    usage = data.get("usage", {})
    reasoning_content = str(message.get("reasoning_content") or "")
    return content, usage, reasoning_content


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

    data = await _post_json_with_retries(
        profile,
        url,
        headers=headers,
        payload=payload,
        failure_label="Multi-turn chat",
    )
    return data["choices"][0]["message"]["content"]


async def call_openai_compatible_tools(
    profile: ModelProfile,
    req: ModelCallRequest,
    *,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
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

    if on_chunk and _model_streaming_enabled():
        try:
            data = await _stream_json_with_retries(
                profile,
                url,
                headers=headers,
                payload=payload,
                failure_label="Tools model call",
                on_chunk=on_chunk,
            )
        except RuntimeError:
            data = await _post_json_with_retries(
                profile,
                url,
                headers=headers,
                payload=payload,
                failure_label="Tools model call",
            )
    else:
        data = await _post_json_with_retries(
            profile,
            url,
            headers=headers,
            payload=payload,
            failure_label="Tools model call",
        )
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
