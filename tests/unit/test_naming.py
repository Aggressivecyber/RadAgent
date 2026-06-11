"""Tests for agent_core.naming.

Verifies:
  - sanitize_title handles various inputs correctly
  - generate_job_title produces valid slugs
  - build_job_id combines UUID + creation timestamp
  - Fallback works when LLM is unavailable
  - User-provided job_id is preserved unchanged
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from agent_core.naming import (
    _fallback_slug,
    build_job_id,
    generate_job_title,
    sanitize_title,
)


class TestSanitizeTitle:
    """Verify sanitize_title produces filesystem-safe slugs."""

    def test_basic_english(self) -> None:
        result = sanitize_title("Proton Detector Simulation")
        assert result == "proton_detector_simulation"

    def test_special_characters(self) -> None:
        result = sanitize_title("Si/CdTe @ 300K!")
        assert result == "si_cdte_300k"

    def test_chinese_input_removed(self) -> None:
        """Chinese characters are stripped, leaving only ASCII parts."""
        result = sanitize_title("建立铝外壳探测器")
        assert result == ""

    def test_mixed_chinese_english(self) -> None:
        """Chinese removed, English words joined with underscores."""
        result = sanitize_title("建立 Proton 探测器 Model")
        assert result == "proton_model"

    def test_truncation(self) -> None:
        long_input = "a" * 100
        result = sanitize_title(long_input)
        assert len(result) <= 60

    def test_empty_input(self) -> None:
        assert sanitize_title("") == ""

    def test_only_spaces(self) -> None:
        assert sanitize_title("   ") == ""

    def test_consecutive_underscores_collapsed(self) -> None:
        result = sanitize_title("hello   world")
        assert result == "hello_world"

    def test_leading_trailing_underscores_stripped(self) -> None:
        result = sanitize_title("_hello_world_")
        assert result == "hello_world"

    def test_numbers_preserved(self) -> None:
        result = sanitize_title("300K Geant4 Simulation v2")
        assert result == "300k_geant4_simulation_v2"


class TestFallbackSlug:
    """Verify _fallback_slug extracts English words from queries."""

    def test_extracts_english_words(self) -> None:
        result = _fallback_slug("建立 Proton 探测器 with Geant4")
        assert result == "proton_with_geant"

    def test_no_english_words(self) -> None:
        result = _fallback_slug("建立包含铝外壳的探测器模型")
        assert result == ""

    def test_short_words_ignored(self) -> None:
        """Words shorter than 2 chars are filtered out."""
        result = _fallback_slug("a big simulation X run")
        assert result == "big_simulation_run"

    def test_three_words_max(self) -> None:
        result = _fallback_slug("alpha beta gamma delta epsilon")
        assert result == "alpha_beta_gamma"


class TestGenerateJobTitle:
    """Verify generate_job_title with mocked model gateway calls."""

    @pytest.mark.asyncio
    async def test_llm_returns_valid_title(self) -> None:
        with patch("agent_core.naming._call_model_gateway", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "proton_detector_sim"
            result = await generate_job_title("建立质子探测器模型")
            assert result == "proton_detector_sim"

    @pytest.mark.asyncio
    async def test_llm_returns_mixed_case(self) -> None:
        with patch("agent_core.naming._call_model_gateway", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Proton_Detector_Sim"
            result = await generate_job_title("proton detector")
            assert result == "proton_detector_sim"

    @pytest.mark.asyncio
    async def test_llm_fails_fallback(self) -> None:
        with patch("agent_core.naming._call_model_gateway", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ""
            result = await generate_job_title("Build a proton detector with Geant4")
            # Fallback: first 3 English words
            assert result == "build_proton_detector"

    @pytest.mark.asyncio
    async def test_llm_fails_no_english_fallback(self) -> None:
        with patch("agent_core.naming._call_model_gateway", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ""
            result = await generate_job_title("建立探测器模型")
            assert result == ""


class TestBuildJobId:
    """Verify build_job_id combines UUID and creation timestamp correctly."""

    @pytest.mark.asyncio
    async def test_format_uses_timestamp_suffix_without_semantic_title(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FixedDateTime(datetime):
            @classmethod
            def now(cls) -> datetime:
                return cls(2026, 6, 11, 15, 4, 5)

        async def _fail_title_generation(user_query: str) -> str:
            raise AssertionError("build_job_id must not generate semantic title suffixes")

        monkeypatch.setattr("agent_core.naming.datetime", _FixedDateTime)
        monkeypatch.setattr(
            "agent_core.naming.uuid.uuid4",
            lambda: SimpleNamespace(hex="abcdef1234567890"),
        )
        monkeypatch.setattr(
            "agent_core.naming.generate_job_title",
            _fail_title_generation,
        )

        result = await build_job_id("", "proton detector")

        assert result == "job_abcdef12__20260611_150405"

    @pytest.mark.asyncio
    async def test_user_provided_id_preserved(self) -> None:
        result = await build_job_id("my_custom_job", "any query")
        assert result == "my_custom_job"

    @pytest.mark.asyncio
    async def test_uuid_part_is_hex_and_suffix_is_creation_time(self) -> None:
        result = await build_job_id("", "query")
        uuid_part, timestamp = result.split("__")
        uuid_hex = uuid_part[4:]  # strip "job_"

        assert len(uuid_hex) == 8
        int(uuid_hex, 16)  # Must be valid hex
        assert len(timestamp) == 15
        assert timestamp[8] == "_"
        datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
