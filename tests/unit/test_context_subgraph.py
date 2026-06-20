"""Tests for Context Subgraph nodes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from agent_core.context.nodes import (
    extract_user_context_requirements,
    retrieve_rag_context,
    retrieve_web_context,
    route_sources,
    save_evidence_map,
    score_combined_context,
    score_rag_context,
)
from agent_core.context.graph import _route_after_rag
from agent_core.workspace.paths import STAGE_CONTEXT
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier


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


class TestContextGraphRouting:
    def test_rag_sufficient_still_scores_combined_context(self) -> None:
        assert _route_after_rag({"needs_web_supplement": False}) == "score_combined_context"

    def test_rag_gap_retrieves_web_context(self) -> None:
        assert _route_after_rag({"needs_web_supplement": True}) == "retrieve_web_context"


def _model_result(parsed_json: dict) -> ModelCallResult:
    return ModelCallResult(
        task=ModelTask.SIMPLE_EXTRACTION,
        tier=ModelTier.LITE,
        provider=ModelProvider.MOCK,
        model_name="mock-lite",
        content="{}",
        parsed_json=parsed_json,
    )


class TestExtractUserContextRequirements:
    async def test_uses_lite_model_to_extract_source_from_user_query(
        self,
        temp_workspace: Path,
    ) -> None:
        job_dir = temp_workspace / "jobs" / "test_job" / STAGE_CONTEXT
        job_dir.mkdir(parents=True)
        model_call = AsyncMock(
            return_value=_model_result(
                {
                    "coverage": {
                        "geometry": True,
                        "materials": True,
                        "source": True,
                        "physics": True,
                        "scoring": True,
                        "output": True,
                    },
                    "evidence": {
                        "source": ["150 MeV proton pencil beam"],
                    },
                    "missing_information": [],
                    "confidence": 0.92,
                }
            )
        )

        with patch("agent_core.models.gateway.get_model_gateway") as get_gateway:
            get_gateway.return_value.call = model_call
            result = await extract_user_context_requirements(
                {
                    "job_id": "test_job",
                    "user_query": (
                        "Build a Geant4 proton depth-dose benchmark for a "
                        "150 MeV pencil beam through water, aluminum, and silicon layers."
                    ),
                }
            )

        requirements = result["user_context_requirements"]
        assert requirements["coverage"]["source"] is True
        assert requirements["missing_hard_required"] == []
        assert requirements["extraction_source"] == "lite_model"
        assert (job_dir / "user_context_requirements.json").exists()
        assert model_call.await_args.kwargs["tier"] == ModelTier.LITE
        assert model_call.await_args.kwargs["task"] == ModelTask.SIMPLE_EXTRACTION


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


class TestScoreCombinedContext:
    async def test_lite_extracted_source_prevents_false_block_on_rag_source_gap(
        self,
        temp_workspace: Path,
    ) -> None:
        job_dir = temp_workspace / "jobs" / "test_job" / STAGE_CONTEXT
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job",
            "user_context_requirements": {
                "coverage": {
                    "geometry": True,
                    "materials": True,
                    "source": True,
                    "physics": True,
                    "scoring": True,
                    "output": True,
                },
                "missing_hard_required": [],
                "extraction_source": "lite_model",
            },
            "rag_score": 0.49,
            "rag_report": {"missing_hard_required": ["source"]},
            "web_context": [],
        }

        result = await score_combined_context(state)

        assert result["context_decision"] == "allow_rag"
        report = json.loads(Path(result["context_report_path"]).read_text())
        assert report["user_missing_hard_required"] == []
        assert report["rag_missing_hard_required"] == ["source"]

    async def test_missing_user_parameters_routes_to_requirements_review_not_context_failure(
        self,
        temp_workspace: Path,
    ) -> None:
        job_dir = temp_workspace / "jobs" / "test_job" / STAGE_CONTEXT
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job",
            "user_context_requirements": {
                "coverage": {
                    "geometry": False,
                    "materials": False,
                    "source": False,
                    "physics": False,
                    "scoring": False,
                    "output": False,
                },
                "missing_hard_required": ["geometry", "materials", "scoring", "source"],
                "missing_information": [
                    "MOSFET 几何结构",
                    "辐照源类型、能量和方向",
                    "敏感体积和计分目标",
                ],
                "extraction_source": "lite_model",
            },
            "rag_score": 0.2,
            "rag_report": {"missing_hard_required": ["source"]},
            "web_context": [],
        }

        result = await score_combined_context(state)

        assert result["context_decision"] == "allow_with_web_supplement"
        report = json.loads(Path(result["context_report_path"]).read_text())
        assert report["decision_reason"] == "missing_user_parameters_requirements_review"
        assert report["user_missing_hard_required"] == [
            "geometry",
            "materials",
            "scoring",
            "source",
        ]

    async def test_empty_request_without_requirement_signal_still_blocks(
        self,
        temp_workspace: Path,
    ) -> None:
        job_dir = temp_workspace / "jobs" / "test_job" / STAGE_CONTEXT
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job",
            "user_query": "",
            "user_context_requirements": {
                "coverage": {
                    "geometry": False,
                    "materials": False,
                    "source": False,
                    "physics": False,
                    "scoring": False,
                    "output": False,
                },
                "missing_hard_required": ["geometry", "materials", "scoring", "source"],
                "missing_information": [],
                "confidence": 0.0,
                "extraction_source": "heuristic",
            },
            "rag_score": 0.0,
            "rag_report": {"missing_hard_required": ["geometry", "materials", "scoring", "source"]},
            "web_context": [],
        }

        result = await score_combined_context(state)

        assert result["context_decision"] == "block_no_context"


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
