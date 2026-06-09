from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from agent_core.g4_codegen.repair.module_repair_loop import (
    _collect_repair_evidence,
    repair_module,
)
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult, ModuleGateResult


@dataclass
class _FakeRagResult:
    doc_id: str = "g4-doc"
    title: str = "Geant4 macro commands"
    content: str = "/run/initialize must be issued before /run/beamOn in batch macros."
    source: str = "local-geant4-docs"
    score: float = 0.9


class _FakeRagClient:
    async def backend_available(self) -> bool:
        return True

    async def search(self, query: str, top_k: int, min_score: float) -> list[_FakeRagResult]:
        assert "Geant4" in query
        assert top_k == 6
        assert min_score == 0.25
        return [_FakeRagResult()]


@dataclass
class _FakeWebResult:
    title: str = "Geant4 Application Developers Guide"
    url: str = "https://geant4-userdoc.web.cern.ch/"
    snippet: str = "Official Geant4 documentation for run macros."
    source_type: str = "web"
    confidence: float = 0.8


class _FakeWebSearchTool:
    search_available = True

    async def search(self, query: str, max_results: int) -> list[_FakeWebResult]:
        assert "Geant4" in query
        assert max_results == 5
        return [_FakeWebResult()]


def _original_result() -> ModuleAgentResult:
    return ModuleAgentResult(
        module_name="physics",
        status="generated",
        generated_files=[
            GeneratedModuleFile(
                path="macros/physics_list.mac",
                operation="create_or_replace",
                new_content="# PLACEHOLDER\n",
                generated_by="physics_module_agent",
                module_name="physics",
                rationale="test",
            )
        ],
    )


def _gate_result() -> ModuleGateResult:
    return ModuleGateResult(
        module_name="physics",
        gate_type="hard",
        status="fail",
        errors=["macros/physics_list.mac: Found forbidden pattern: PLACEHOLDER marker"],
    )


@pytest.mark.asyncio
async def test_collect_repair_evidence_calls_rag_and_web(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

    with (
        patch("agent_core.context.nodes._get_rag_client", return_value=_FakeRagClient()),
        patch("agent_core.context.nodes._ensure_indexed", new=AsyncMock(return_value=True)),
        patch("agent_core.tools.web_search_tool.WebSearchTool", _FakeWebSearchTool),
    ):
        evidence = await _collect_repair_evidence(
            module_name="physics",
            gate_result=_gate_result(),
            module_context={"job_id": "repair_job"},
            current_result=_original_result(),
            job_id="repair_job",
            attempt=1,
        )

    assert evidence["rag"]["status"] == "pass"
    assert evidence["rag"]["results"][0]["source"] == "local-geant4-docs"
    assert evidence["web"]["status"] == "pass"
    assert evidence["web"]["results"][0]["url"].startswith("https://geant4")
    assert (
        tmp_path
        / "jobs"
        / "repair_job"
        / "06_codegen"
        / "repair"
        / "physics_repair_evidence_attempt_1.json"
    ).exists()


@pytest.mark.asyncio
async def test_repair_module_passes_retrieval_context_to_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

    with (
        patch(
            "agent_core.g4_codegen.repair.module_repair_loop._collect_repair_evidence",
            new=AsyncMock(
                return_value={
                    "rag": {
                        "status": "pass",
                        "results": [{"title": "G4 docs", "content": "Use /run/initialize"}],
                    },
                    "web": {
                        "status": "pass",
                        "results": [{"url": "https://geant4-userdoc.web.cern.ch/"}],
                    },
                }
            ),
        ) as collect_evidence,
        patch("agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway") as gateway_fn,
    ):
        gateway = AsyncMock()
        gateway.call.return_value = AsyncMock(error="stop after prompt capture", content="")
        gateway_fn.return_value = gateway

        await repair_module(
            "physics",
            {"module_name": "physics", "job_id": "repair_job"},
            _original_result(),
            _gate_result(),
            job_id="repair_job",
            max_attempts=1,
        )

    collect_evidence.assert_awaited_once()
    user_prompt = gateway.call.await_args.kwargs["user_prompt"]
    assert "retrieval_context" in user_prompt
    assert "Use /run/initialize" in user_prompt
    assert "https://geant4-userdoc.web.cern.ch/" in user_prompt
