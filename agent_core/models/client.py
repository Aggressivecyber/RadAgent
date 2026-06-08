from __future__ import annotations

import os
from typing import Any

import httpx

from agent_core.config.environment import load_environment
from agent_core.models.schemas import ModelCallRequest, ModelProfile


def _httpx_client_kwargs(profile: ModelProfile) -> dict[str, Any]:
    env = load_environment()
    kwargs: dict[str, Any] = {"timeout": profile.timeout_s, "trust_env": False}
    if env.proxy:
        kwargs["proxy"] = env.proxy
    return kwargs


async def call_openai_compatible_model(
    profile: ModelProfile,
    req: ModelCallRequest,
) -> tuple[str, dict]:
    if not profile.base_url:
        raise RuntimeError(f"Missing base_url for model tier {profile.tier}")

    api_key = os.getenv(profile.api_key_env or "")
    if not api_key:
        raise RuntimeError(f"Missing API key env: {profile.api_key_env}")

    payload = {
        "model": profile.model_name,
        "messages": [
            {"role": "system", "content": req.system_prompt},
            {"role": "user", "content": req.user_prompt},
        ],
        "temperature": req.temperature if req.temperature is not None else profile.temperature,
        "max_tokens": req.max_tokens if req.max_tokens is not None else profile.max_tokens,
    }

    if req.response_format == "json":
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = profile.base_url.rstrip("/") + "/chat/completions"

    last_error = None
    for _ in range(profile.max_retries + 1):
        try:
            async with httpx.AsyncClient(**_httpx_client_kwargs(profile)) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return content, usage
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

    api_key = os.getenv(profile.api_key_env or "")
    if not api_key:
        raise RuntimeError(f"Missing API key env: {profile.api_key_env}")

    payload: dict[str, Any] = {
        "model": profile.model_name,
        "messages": messages,
        "temperature": temperature if temperature is not None else profile.temperature,
        "max_tokens": max_tokens if max_tokens is not None else profile.max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

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
