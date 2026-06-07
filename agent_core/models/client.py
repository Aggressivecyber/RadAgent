from __future__ import annotations

import os

import httpx

from agent_core.models.schemas import ModelCallRequest, ModelProfile


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
            async with httpx.AsyncClient(timeout=profile.timeout_s) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return content, usage
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Model call failed after retries: {last_error}")
