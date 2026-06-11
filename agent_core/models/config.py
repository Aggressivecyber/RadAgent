from __future__ import annotations

from agent_core.config.environment import load_environment
from agent_core.models.schemas import ModelProfile, ModelTier


def load_model_profiles() -> dict[ModelTier, ModelProfile]:
    env = load_environment()
    return {
        tier: ModelProfile(
            tier=tier_config.tier,
            provider=tier_config.provider,
            model_name=tier_config.model_name,
            base_url=tier_config.base_url,
            api_key_env=tier_config.api_key_env,
            timeout_s=tier_config.timeout_s,
            max_retries=tier_config.max_retries,
            temperature=tier_config.temperature,
            max_tokens=tier_config.max_tokens,
            context_window_tokens=tier_config.context_window_tokens,
        )
        for tier, tier_config in env.models.items()
    }
