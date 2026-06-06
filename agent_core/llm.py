"""Shared LLM configuration for the RadAgent pipeline.

Supports OpenAI, DeepSeek (OpenAI-compatible), and other providers.
Configuration via environment variables or .env file.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from pydantic import SecretStr


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """Get a configured LLM instance.

    Reads configuration from environment:
    - OPENAI_API_KEY: API key (required)
    - OPENAI_BASE_URL: Base URL (default: https://api.openai.com/v1)
    - MODEL_NAME: Model name (default: gpt-4o)

    Supports DeepSeek via:
      OPENAI_BASE_URL=https://api.deepseek.com/v1
      OPENAI_API_KEY=sk-xxx
      MODEL_NAME=deepseek-chat
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.environ.get("MODEL_NAME", "gpt-4o")

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=SecretStr(api_key),
        base_url=base_url,
    )
