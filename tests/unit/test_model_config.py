"""Tests for agent_core.models.config — model profile configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

from agent_core.models.config import load_model_profiles
from agent_core.models.schemas import ModelProvider, ModelTier


class TestLoadModelProfiles:
    """Verify model profiles load correctly with defaults and env overrides."""

    def test_default_profiles_exist(self) -> None:
        """All three tiers should have profiles."""
        profiles = load_model_profiles()
        assert ModelTier.LITE in profiles
        assert ModelTier.PRO in profiles
        assert ModelTier.MAX in profiles

    def test_lite_default_provider(self) -> None:
        """Lite tier should use OPENAI_COMPATIBLE provider."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.LITE].provider == ModelProvider.OPENAI_COMPATIBLE

    def test_pro_default_provider(self) -> None:
        """Pro tier should use OPENAI_COMPATIBLE provider."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.PRO].provider == ModelProvider.OPENAI_COMPATIBLE

    def test_max_default_provider(self) -> None:
        """Max tier should use OPENAI_COMPATIBLE provider."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.MAX].provider == ModelProvider.OPENAI_COMPATIBLE

    def test_lite_default_model_name(self) -> None:
        """Lite tier default model name."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.LITE].model_name == "dsv4lite"

    def test_pro_default_model_name(self) -> None:
        """Pro tier default model name."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.PRO].model_name == "dsv4pro"

    def test_max_default_model_name(self) -> None:
        """Max tier default model name (currently same as pro)."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.MAX].model_name == "dsv4pro"

    def test_env_override_lite_model(self) -> None:
        """Environment variable should override lite model name."""
        with patch.dict(os.environ, {"RADAGENT_MODEL_LITE": "custom-lite"}):
            profiles = load_model_profiles()
            assert profiles[ModelTier.LITE].model_name == "custom-lite"

    def test_env_override_pro_model(self) -> None:
        """Environment variable should override pro model name."""
        with patch.dict(os.environ, {"RADAGENT_MODEL_PRO": "custom-pro"}):
            profiles = load_model_profiles()
            assert profiles[ModelTier.PRO].model_name == "custom-pro"

    def test_env_override_max_model(self) -> None:
        """Environment variable should override max model name."""
        with patch.dict(os.environ, {"RADAGENT_MODEL_MAX": "custom-max"}):
            profiles = load_model_profiles()
            assert profiles[ModelTier.MAX].model_name == "custom-max"

    def test_tier_timeouts_differ(self) -> None:
        """Each tier should have different timeout defaults."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.LITE].timeout_s < profiles[ModelTier.PRO].timeout_s
        assert profiles[ModelTier.PRO].timeout_s < profiles[ModelTier.MAX].timeout_s

    def test_tier_max_tokens_differ(self) -> None:
        """Each tier should have different max_tokens defaults."""
        profiles = load_model_profiles()
        assert profiles[ModelTier.LITE].max_tokens < profiles[ModelTier.PRO].max_tokens
        assert profiles[ModelTier.PRO].max_tokens < profiles[ModelTier.MAX].max_tokens
