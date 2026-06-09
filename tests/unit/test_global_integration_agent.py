from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen.global_integration_agent import run_global_integration_agent
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier


def _patch() -> dict[str, Any]:
    return {
        "changed_files": [
            {
                "path": "include/DetectorConstruction.hh",
                "operation": "create_or_replace",
                "new_content": "#pragma once\nclass DetectorConstruction {};\n",
                "zone": "green",
                "generated_by": "geometry_module_agent",
                "module_name": "geometry",
                "rationale": "test",
            },
            {
                "path": "main.cc",
                "operation": "create_or_replace",
                "new_content": "int main() { return 0; }\n",
                "zone": "green",
                "generated_by": "main_cmake_module_agent",
                "module_name": "main_cmake",
                "rationale": "test",
            },
        ],
    }


class _Profile:
    provider = ModelProvider.OPENAI_COMPATIBLE
    model_name = "unit-test-model"


class _MockProfile:
    provider = ModelProvider.MOCK
    model_name = "mock"


class _Gateway:
    def __init__(self, response: dict[str, Any], *, mock: bool = False) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.profiles = {ModelTier.MAX: _MockProfile() if mock else _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.prompts.append(str(kwargs["user_prompt"]))
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content=json.dumps(self.response),
            parsed_json=self.response,
            usage={},
        )


async def _database_evidence(_query: str) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": "g4-run-manager",
            "title": "Geant4 Run Manager",
            "content": "G4RunManager wires detector construction and physics list.",
            "source": "database",
            "score": 1.0,
        }
    ]


async def _web_evidence(_query: str) -> list[dict[str, Any]]:
    return [
        {
            "title": "Geant4 application guide",
            "url": "https://geant4-userdoc.web.cern.ch/",
            "snippet": "User initialization classes are registered on the run manager.",
            "source_type": "web",
            "confidence": 0.8,
        }
    ]


async def _empty_evidence(_query: str) -> list[dict[str, Any]]:
    return []


@pytest.mark.asyncio
async def test_global_integration_agent_reads_modules_files_database_and_web(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    response = {
        "status": "integrated",
        "proposed_patch": {
            "changed_files": [
                {
                    "path": "main.cc",
                    "operation": "create_or_replace",
                    "new_content": '#include "DetectorConstruction.hh"\nint main() { return 0; }\n',
                    "zone": "green",
                    "generated_by": "main_cmake_module_agent",
                    "module_name": "main_cmake",
                    "rationale": "wire detector header",
                }
            ]
        },
        "issues_fixed": [{"target": "main.cc", "message": "wired generated header"}],
        "errors": [],
    }
    gateway = _Gateway(response)
    codegen_dir = tmp_path / "jobs" / "global_integration_test" / "06_codegen"
    codegen_dir.mkdir(parents=True)
    (codegen_dir / "global_integration_agent_report.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "errors": ["previous constructor mismatch"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _web_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_test",
        module_results={"geometry": {}, "main_cmake": {}},
        module_contracts={
            "geometry": {"output_files": ["include/DetectorConstruction.hh"]},
            "main_cmake": {"output_files": ["main.cc"]},
        },
        module_gate_results={
            "geometry": {"hard": {"status": "pass"}, "llm": {"status": "pass"}},
            "main_cmake": {"hard": {"status": "pass"}, "llm": {"status": "pass"}},
        },
    )

    assert report["status"] == "passed"
    assert report["changed_files"] == ["main.cc"]
    assert report["capabilities_used"]["database_search"] is True
    assert report["capabilities_used"]["web_search"] is True
    files_by_path = {entry["path"]: entry for entry in repaired["changed_files"]}
    assert set(files_by_path) == {"include/DetectorConstruction.hh", "main.cc"}
    assert '#include "DetectorConstruction.hh"' in files_by_path["main.cc"]["new_content"]
    prompt = gateway.prompts[0]
    assert "available_modules" in prompt
    assert "DetectorConstruction.hh" in prompt
    assert "database_search" in prompt
    assert "web_search" in prompt
    assert "previous constructor mismatch" in prompt
    context_path = (
        Path(tmp_path)
        / "jobs"
        / "global_integration_test"
        / "06_codegen"
        / "integration"
        / "global_integration_context.json"
    )
    assert context_path.is_file()


@pytest.mark.asyncio
async def test_global_integration_agent_rejects_content_field(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    bad_patch = _patch()
    bad_patch["changed_files"][0]["content"] = "forbidden"
    response = {
        "status": "integrated",
        "proposed_patch": bad_patch,
        "issues_fixed": [],
        "errors": [],
    }
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway(response),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_bad_schema",
        module_results={"geometry": {}, "main_cmake": {}},
    )

    assert repaired == _patch()
    assert report["status"] == "failed"
    assert any("content field is forbidden" in error for error in report["errors"])


@pytest.mark.asyncio
async def test_global_integration_agent_partial_patch_inherits_file_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    response = {
        "status": "integrated",
        "proposed_patch": {
            "changed_files": [
                {
                    "path": "main.cc",
                    "new_content": '#include "DetectorConstruction.hh"\nint main() { return 0; }\n',
                }
            ]
        },
        "issues_fixed": [{"target": "main.cc", "message": "minimal partial edit"}],
        "errors": [],
    }
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway(response),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_partial_metadata",
        module_results={"geometry": {}, "main_cmake": {}},
    )

    assert report["status"] == "passed"
    main_entry = next(f for f in repaired["changed_files"] if f["path"] == "main.cc")
    assert main_entry["zone"] == "green"
    assert main_entry["generated_by"] == "main_cmake_module_agent"
    assert main_entry["module_name"] == "main_cmake"


@pytest.mark.asyncio
async def test_global_integration_agent_requires_evidence_for_real_provider(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway({"status": "no_change", "proposed_patch": _patch()}),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_no_evidence",
        module_results={"geometry": {}, "main_cmake": {}},
    )

    assert report["status"] == "failed"
    assert any("requires local database or web-search evidence" in e for e in report["errors"])


@pytest.mark.asyncio
async def test_global_integration_agent_mock_provider_keeps_patch_and_requires_runtime_gate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway({}, mock=True),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_mock",
        module_results={"geometry": {}, "main_cmake": {}},
    )

    assert report["status"] == "passed"
    assert report["mock_provider_only"] is True
    assert repaired["metadata"]["global_integration_agent"]["runtime_gate_required"] is True
