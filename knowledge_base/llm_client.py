#!/usr/bin/env python3
"""Shared OpenAI-compatible LLM client for knowledge-base helper scripts."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent_core.config.environment import (
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_MODEL_LITE,
    DEFAULT_MODEL_MAX,
    DEFAULT_MODEL_PRO,
    load_project_env,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def call_llm(
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    *,
    model_tier: str = "pro",
    enable_thinking: bool = False,
    timeout: int = 60,
    max_retries: int = 3,
) -> str:
    """Call the configured OpenAI-compatible chat model.

    Knowledge-base tools use text-only ReAct histories, so MiMo thinking mode is
    disabled by default to avoid multi-turn reasoning_content bookkeeping.
    """
    _load_project_env()
    model_tier = model_tier.lower().strip()
    model = _model_for_tier(model_tier)
    base_url = _base_url_for_tier(model_tier)
    api_key_env = _api_key_env_for_tier(model_tier)
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Missing API key env: {api_key_env}")

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if _is_mimo_model(model, base_url):
        payload["max_completion_tokens"] = max_tokens
        payload["thinking"] = {"type": "enabled" if enable_thinking else "disabled"}
        if not enable_thinking:
            payload["temperature"] = temperature
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = temperature

    headers = {"Content-Type": "application/json"}
    if _is_mimo_model(model, base_url):
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
    )

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries - 1:
                wait_s = 10 * (attempt + 1)
                print(f"  [RATE LIMIT] retrying in {wait_s}s...", file=sys.stderr)
                time.sleep(wait_s)
                continue
            if attempt < max_retries - 1:
                print(f"  [RETRY] LLM call failed (attempt {attempt + 1}): {exc}", file=sys.stderr)
                time.sleep(3)
                continue
            raise RuntimeError(f"LLM call failed: {exc}") from exc
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as exc:
            if attempt < max_retries - 1:
                print(f"  [RETRY] LLM call failed (attempt {attempt + 1}): {exc}", file=sys.stderr)
                time.sleep(3)
                continue
            raise RuntimeError(f"LLM call failed: {exc}") from exc

    raise RuntimeError("LLM call failed after retries")


def _load_project_env() -> None:
    load_project_env(PROJECT_ROOT / ".env")


def _model_for_tier(model_tier: str) -> str:
    if model_tier == "lite":
        return os.getenv("RADAGENT_MODEL_LITE", DEFAULT_MODEL_LITE)
    if model_tier == "max":
        return os.getenv("RADAGENT_MODEL_MAX", DEFAULT_MODEL_MAX)
    return os.getenv("RADAGENT_MODEL_PRO", DEFAULT_MODEL_PRO)


def _base_url_for_tier(model_tier: str) -> str:
    if model_tier == "lite":
        return os.getenv("RADAGENT_LITE_BASE_URL") or os.getenv(
            "RADAGENT_MODEL_BASE_URL",
            DEFAULT_MODEL_BASE_URL,
        )
    if model_tier == "max":
        return os.getenv("RADAGENT_MAX_BASE_URL") or os.getenv(
            "RADAGENT_MODEL_BASE_URL",
            DEFAULT_MODEL_BASE_URL,
        )
    return os.getenv("RADAGENT_PRO_BASE_URL") or os.getenv(
        "RADAGENT_MODEL_BASE_URL",
        DEFAULT_MODEL_BASE_URL,
    )


def _api_key_env_for_tier(model_tier: str) -> str:
    if model_tier == "lite":
        return os.getenv("RADAGENT_LITE_API_KEY_ENV", "RADAGENT_API_KEY")
    if model_tier == "max":
        return os.getenv("RADAGENT_MAX_API_KEY_ENV", "RADAGENT_API_KEY")
    return os.getenv("RADAGENT_PRO_API_KEY_ENV", "RADAGENT_API_KEY")


def _is_mimo_model(model: str, base_url: str) -> bool:
    return model.lower().startswith("mimo-") or "xiaomimimo.com" in base_url.lower()
