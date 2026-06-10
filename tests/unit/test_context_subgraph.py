"""Tests for Context Subgraph nodes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from agent_core.context.nodes import (
    retrieve_rag_context,
    retrieve_web_context,
    route_sources,
    save_evidence_map,
    score_rag_context,
)
from agent_core.workspace.paths import STAGE_CONTEXT


@pytest.fixture
def temp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary workspace for testing."""
    workspace = tmp_path / "sim_ws"
    workspace.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    return workspace


class TestRouteSources:
    async def test_default_geant4(self) -> None:
        state = {"required_sources": ["geant4"]}
        result = await route_sources(state)
        assert result["required_sources"] == ["geant4"]


class TestRetrieveRagContext:
    async def test_creates_context_files(self, temp_workspace: Path) -> None:
        job_dir = temp_workspace / "jobs" / "test_job" / STAGE_CONTEXT
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job",
            "user_query": "10 MeV proton silicon",
            "required_sources": ["geant4"],
        }

        # Mock RAG client to avoid actual API call
        with patch("agent_core.context.nodes._get_rag_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.backend_available = AsyncMock(return_value=False)
            mock_get_client.return_value = mock_client

            result = await retrieve_rag_context(state)

        assert "rag_context" in result
        assert "rag_score" in result
        assert "rag_report" in result
        assert isinstance(result["rag_context"], list)


class TestScoreRagContext:
    async def test_high_score_allows(self) -> None:
        state = {"rag_score": 0.8}
        result = await score_rag_context(state)
        assert result["context_decision"] == "allow_rag"
        assert result["needs_web_supplement"] is False

    async def test_low_score_needs_web(self) -> None:
        state = {"rag_score": 0.2}
        result = await score_rag_context(state)
        assert result["needs_web_supplement"] is True


class TestRetrieveWebContext:
    async def test_no_web_tool(self, temp_workspace: Path) -> None:
        job_dir = temp_workspace / "jobs" / "test_job" / STAGE_CONTEXT
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job",
            "user_query": "test query",
        }

        with patch("agent_core.tools.web_search_tool.WebSearchTool", side_effect=ImportError):
            result = await retrieve_web_context(state)

        assert result["web_search_available"] is False
        assert result["web_context"] == []


class TestSaveEvidenceMap:
    async def test_saves_evidence_map(self, temp_workspace: Path) -> None:
        job_dir = temp_workspace / "jobs" / "test_job" / STAGE_CONTEXT
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job",
            "rag_context": [{"text": "test"}],
            "web_urls": ["https://example.com"],
            "web_context": [{"title": "test", "url": "https://example.com"}],
            "context_decision": "allow_with_web_supplement",
        }

        result = await save_evidence_map(state)
        assert "evidence_map_path" in result
        assert Path(result["evidence_map_path"]).exists()

        evidence = json.loads(Path(result["evidence_map_path"]).read_text())
        assert evidence["decision"] == "allow_with_web_supplement"
        assert evidence["web_sources"][0]["urls"] == ["https://example.com"]
