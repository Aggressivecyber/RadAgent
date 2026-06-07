from __future__ import annotations

import os

from agent_core.models.schemas import ModelProfile, ModelProvider, ModelTier


def _get_provider() -> ModelProvider:
    """Detect provider from env; return MOCK if requested."""
    env_provider = os.getenv("RADAGENT_MODEL_PROVIDER", "").lower()
    if env_provider == "mock":
        return ModelProvider.MOCK
    return ModelProvider.OPENAI_COMPATIBLE


def load_model_profiles() -> dict[ModelTier, ModelProfile]:
    provider = _get_provider()
    return {
        ModelTier.LITE: ModelProfile(
            tier=ModelTier.LITE,
            provider=provider,
            model_name=os.getenv("RADAGENT_MODEL_LITE", "deepseek-v4-flash"),
            base_url=os.getenv("RADAGENT_LITE_BASE_URL", os.getenv("RADAGENT_MODEL_BASE_URL", "")),
            api_key_env=os.getenv("RADAGENT_LITE_API_KEY_ENV", "RADAGENT_API_KEY"),
            timeout_s=float(os.getenv("RADAGENT_LITE_TIMEOUT_S", "30")),
            max_retries=int(os.getenv("RADAGENT_LITE_MAX_RETRIES", "2")),
            temperature=float(os.getenv("RADAGENT_LITE_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("RADAGENT_LITE_MAX_TOKENS", "2048")),
        ),
        ModelTier.PRO: ModelProfile(
            tier=ModelTier.PRO,
            provider=provider,
            model_name=os.getenv("RADAGENT_MODEL_PRO", "deepseek-v4-pro"),
            base_url=os.getenv("RADAGENT_PRO_BASE_URL", os.getenv("RADAGENT_MODEL_BASE_URL", "")),
            api_key_env=os.getenv("RADAGENT_PRO_API_KEY_ENV", "RADAGENT_API_KEY"),
            timeout_s=float(os.getenv("RADAGENT_PRO_TIMEOUT_S", "90")),
            max_retries=int(os.getenv("RADAGENT_PRO_MAX_RETRIES", "2")),
            temperature=float(os.getenv("RADAGENT_PRO_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("RADAGENT_PRO_MAX_TOKENS", "8192")),
        ),
        ModelTier.MAX: ModelProfile(
            tier=ModelTier.MAX,
            provider=provider,
            model_name=os.getenv("RADAGENT_MODEL_MAX", "deepseek-v4-pro"),
            base_url=os.getenv("RADAGENT_MAX_BASE_URL", os.getenv("RADAGENT_MODEL_BASE_URL", "")),
            api_key_env=os.getenv("RADAGENT_MAX_API_KEY_ENV", "RADAGENT_API_KEY"),
            timeout_s=float(os.getenv("RADAGENT_MAX_TIMEOUT_S", "120")),
            max_retries=int(os.getenv("RADAGENT_MAX_MAX_RETRIES", "2")),
            temperature=float(os.getenv("RADAGENT_MAX_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("RADAGENT_MAX_TOKENS", "12000")),
        ),
    }
