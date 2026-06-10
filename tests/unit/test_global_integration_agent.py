from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen import global_integration_agent as gia
from agent_core.g4_codegen.global_integration_agent import run_global_integration_agent
from agent_core.g4_codegen.graph_nodes import global_integration_agent_node
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier
from agent_core.workspace.paths import STAGE_CODEGEN


def _patch() -> dict[str, Any]:
    return {
        "changed_files": [
            {
                "path": "include/DetectorConstruction.hh",
                "operation": "create_or_replace",
                "new_content": "#pragma once\nclass DetectorConstruction {};\n",
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
            {
                "path": "main.cc",
                "operation": "create_or_replace",
                "new_content": "int main() { return 0; }\n",
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
        ],
    }


def test_global_integration_normalizes_new_file_metadata() -> None:
    candidate = {
        "changed_files": [
            {
                "path": "macros/scoring.mac",
                "new_content": "/score/create/boxMesh mesh\n",
            }
        ]
    }

    normalized = gia._normalize_candidate_patch_metadata(_patch(), candidate)

    entry = normalized["changed_files"][0]
    assert entry["zone"] == "runtime_macro"
    assert entry["generated_by"] == "global_integration_agent"
    assert entry["module_name"] == "runtime_app"
    assert entry["operation"] == "create_or_replace"


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
        self.call_kwargs: list[dict[str, Any]] = []
        self.profiles = {ModelTier.MAX: _MockProfile() if mock else _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.call_kwargs.append(kwargs)
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


class _SequenceGateway:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.call_kwargs: list[dict[str, Any]] = []
        self.profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.call_kwargs.append(kwargs)
        self.prompts.append(str(kwargs["user_prompt"]))
        response = self.responses.pop(0)
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content=json.dumps(response),
            parsed_json=response,
            usage={},
        )


class _InitialThenErrorGateway:
    def __init__(self, response: dict[str, Any], *, error: str) -> None:
        self.response = response
        self.error = error
        self.calls = 0
        self.profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **_kwargs: Any) -> ModelCallResult:
        self.calls += 1
        if self.calls == 1:
            return ModelCallResult(
                task=ModelTask.CODEGEN,
                tier=ModelTier.MAX,
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="unit-test-model",
                content=json.dumps(self.response),
                parsed_json=self.response,
                usage={},
            )
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content="",
            parsed_json=None,
            usage={},
            error=self.error,
        )


class _ErrorGateway:
    def __init__(self, *, error: str) -> None:
        self.error = error
        self.prompts: list[str] = []
        self.call_kwargs: list[dict[str, Any]] = []
        self.profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.call_kwargs.append(kwargs)
        self.prompts.append(str(kwargs["user_prompt"]))
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content="",
            parsed_json=None,
            usage={},
            error=self.error,
        )


class _FailIfCalledGateway:
    profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **_kwargs: Any) -> ModelCallResult:
        raise AssertionError("initial global integration model call should be deferred")


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
                    "generated_by": "runtime_app_module_agent",
                    "module_name": "runtime_app",
                    "rationale": "wire detector header",
                }
            ]
        },
        "issues_fixed": [{"target": "main.cc", "message": "wired generated header"}],
        "errors": [],
    }
    gateway = _Gateway(response)
    codegen_dir = tmp_path / "jobs" / "global_integration_test" / STAGE_CODEGEN
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
        module_results={"simulation_core": {}, "runtime_app": {}},
        module_contracts={
            "simulation_core": {"output_files": ["include/DetectorConstruction.hh"]},
            "runtime_app": {"output_files": ["main.cc"]},
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
        / STAGE_CODEGEN
        / "integration"
        / "global_integration_context.json"
    )
    assert context_path.is_file()


@pytest.mark.asyncio
async def test_global_integration_defers_large_initial_context_to_runtime_gate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    large_patch = _patch()
    large_patch["changed_files"].append(
        {
            "path": "src/LargeGenerated.cc",
            "operation": "create_or_replace",
            "new_content": "int generated_value = 0;\n" * 4000,
            "zone": "green",
            "generated_by": "large_module_agent",
            "module_name": "large",
            "rationale": "force large initial integration context",
        }
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _FailIfCalledGateway(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _web_evidence,
    )
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        large_patch,
        job_id="global_integration_defer_initial",
        module_results={"simulation_core": {}, "runtime_app": {}, "large": {}},
        runtime_repair_rounds=1,
    )

    assert report["status"] == "passed"
    assert report["deferred_until_runtime_gate"] is True
    assert runtime_attempts == [1]
    assert report["runtime_gate_attempts"][0]["status"] == "pass"
    assert repaired["metadata"]["global_integration_agent"]["deferred_until_runtime_gate"] is True
    assert repaired["metadata"]["final_runtime_gate"]["required"] is True


@pytest.mark.asyncio
async def test_deferred_initial_integration_uses_runtime_observation_for_repair(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    large_patch = _patch()
    large_patch["changed_files"].append(
        {
            "path": "src/LargeGenerated.cc",
            "operation": "create_or_replace",
            "new_content": "int generated_value = 0;\n" * 4000,
            "zone": "green",
            "generated_by": "large_module_agent",
            "module_name": "large",
            "rationale": "force large initial integration context",
        }
    )
    gateway = _SequenceGateway(
        [
            {
                "status": "integrated",
                "proposed_patch": {
                    "changed_files": [
                        {"path": "main.cc", "new_content": "int main() { return 0; }\n"}
                    ]
                },
                "issues_fixed": [
                    {"target": "main.cc", "message": "repaired from runtime observation"}
                ],
                "errors": [],
            }
        ]
    )
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        if attempt == 1:
            return {
                "status": "fail",
                "attempt": attempt,
                "errors": ["BUILD_ERROR_SENTINEL: Hit must satisfy G4THitsCollection API"],
                "warnings": [],
                "missing_outputs": ["g4_summary.json"],
            }
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

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
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        large_patch,
        job_id="global_integration_defer_runtime_repair",
        module_results={"simulation_core": {}, "runtime_app": {}, "large": {}},
        runtime_repair_rounds=2,
    )

    assert report["status"] == "passed"
    assert report["deferred_until_runtime_gate"] is True
    assert runtime_attempts == [1, 2]
    assert len(gateway.prompts) == 1
    assert "runtime repair round 1" in gateway.prompts[0]
    assert "BUILD_ERROR_SENTINEL" in gateway.prompts[0]
    main_entry = next(f for f in repaired["changed_files"] if f["path"] == "main.cc")
    assert "return 0" in main_entry["new_content"]


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
        module_results={"simulation_core": {}, "runtime_app": {}},
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
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    main_entry = next(f for f in repaired["changed_files"] if f["path"] == "main.cc")
    assert main_entry["zone"] == "green"
    assert main_entry["generated_by"] == "runtime_app_module_agent"
    assert main_entry["module_name"] == "runtime_app"


@pytest.mark.asyncio
async def test_global_integration_agent_continues_when_external_evidence_unavailable(
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
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    assert any("evidence were unavailable" in item for item in report["warnings"])


@pytest.mark.asyncio
async def test_global_integration_accepts_empty_patch_for_no_change(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway({"status": "no_change", "proposed_patch": {"changed_files": []}}),
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
        job_id="global_integration_no_change_empty_patch",
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    assert report["changed_files"] == []
    assert repaired["changed_files"] == _patch()["changed_files"]


@pytest.mark.asyncio
async def test_global_integration_prompt_keeps_files_and_runtime_observation_first(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _Gateway({"status": "no_change", "proposed_patch": _patch()})
    build_result = tmp_path / "build_result.json"
    build_result.write_text(
        json.dumps(
            {
                "success": False,
                "errors": "BUILD_ERROR_SENTINEL: constructor mismatch",
                "stderr": "DetectorConstruction.cc failed to compile",
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
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_prompt_budget",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_failure_context={
            "job_id": "global_integration_prompt_budget",
            "status": "failed",
            "phase": "gate_validation",
            "errors": ["Missing C++ standard setting (CXX_STANDARD or c++17)"],
            "details": {
                "failed_gates": [
                    {
                        "gate_id": 6,
                        "name": "Build/Parse",
                        "status": "fail",
                        "failed_items": ["Build failed"],
                        "message": "Build failed",
                        "file_paths": [str(build_result)],
                    }
                ]
            },
        },
    )

    assert report["status"] == "passed"
    prompt = gateway.prompts[0]
    assert '"project_files"' in prompt
    assert '"runtime_failure_context"' in prompt
    assert "class DetectorConstruction" in prompt
    assert "BUILD_ERROR_SENTINEL" in prompt
    assert "G4-G No Magic Number" not in gia.GLOBAL_INTEGRATION_SYSTEM_PROMPT
    assert "No Magic Number" not in prompt
    assert prompt.find('"project_files"') < prompt.find('"runtime_failure_context"')
    assert gateway.call_kwargs[0]["max_tokens"] == gia.RUNTIME_REPAIR_MAX_TOKENS
    assert gateway.call_kwargs[0]["metadata"]["enable_thinking"] is True


@pytest.mark.asyncio
async def test_initial_global_integration_timeout_continues_to_runtime_gate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _ErrorGateway(error="Model call timed out after 365.0s")
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

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
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_initial_timeout_runtime_fallback",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_repair_rounds=1,
    )

    assert report["status"] == "passed"
    assert report["errors"] == []
    assert runtime_attempts == [1]
    assert report["runtime_gate_attempts"][0]["status"] == "pass"
    assert "Initial global integration model call failed" in report["warnings"][0]
    assert report["llm_status"] == "initial_model_error_runtime_fallback"
    assert repaired["metadata"]["global_integration_agent"]["runtime_gate_required"] is True
    assert gateway.call_kwargs[0]["max_tokens"] == gia.INITIAL_INTEGRATION_MAX_TOKENS
    assert gateway.call_kwargs[0]["metadata"]["enable_thinking"] is True


@pytest.mark.asyncio
async def test_runtime_observation_model_timeout_still_fails(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _ErrorGateway(error="Model call timed out after 365.0s")

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
        _empty_evidence,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_runtime_timeout_still_fails",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_failure_context={"status": "fail", "errors": ["real build failed"]},
        runtime_repair_rounds=1,
    )

    assert report["status"] == "failed"
    assert report["runtime_gate_attempts"] == []
    assert report["errors"] == [
        "Global integration model call failed: Model call timed out after 365.0s"
    ]
    assert gateway.call_kwargs[0]["max_tokens"] == gia.RUNTIME_REPAIR_MAX_TOKENS
    assert gateway.call_kwargs[0]["metadata"]["enable_thinking"] is True


def test_global_integration_runtime_gate_ignores_magic_number_style(tmp_path) -> None:
    project_dir = tmp_path / "geant4_project"
    output_dir = tmp_path / "g4_output_package"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    output_dir.mkdir()
    (src_dir / "OutputManager.cc").write_text(
        "#include <array>\n"
        "void f() {\n"
        "  std::array<int, 3> nBins = {10, 10, 10};\n"
        "}\n",
        encoding="utf-8",
    )
    (output_dir / "g4_summary.json").write_text(
        json.dumps({"job_id": "style", "events_requested": 2}),
        encoding="utf-8",
    )
    (output_dir / "provenance.json").write_text(
        json.dumps({"job_id": "style"}),
        encoding="utf-8",
    )
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.25,0.01\n1,0.50,0.004\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.25\n1,0,0,0.50\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.004\n",
        encoding="utf-8",
    )
    (output_dir / "smoke_simulation_result.json").write_text(
        json.dumps({"success": True, "errors": ""}),
        encoding="utf-8",
    )

    gate = gia._summarize_runtime_gate_result(
        result={"success": True, "warnings": []},
        attempt=1,
        project_dir=project_dir,
        output_dir=output_dir,
    )

    assert gate["status"] == "pass"
    assert gate["errors"] == []


def test_global_integration_runtime_gate_rejects_empty_zero_smoke_outputs(tmp_path) -> None:
    project_dir = tmp_path / "geant4_project"
    output_dir = tmp_path / "g4_output_package"
    project_dir.mkdir()
    output_dir.mkdir()
    (output_dir / "g4_summary.json").write_text(
        json.dumps({"job_id": "quality", "events_requested": 10, "smoke_success": True}),
        encoding="utf-8",
    )
    (output_dir / "event_table.csv").write_text("EventID,edep_MeV,dose_Gy\n", encoding="utf-8")
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )
    (output_dir / "provenance.json").write_text('{"job_id":"quality"}\n', encoding="utf-8")
    (output_dir / "smoke_simulation_result.json").write_text(
        json.dumps(
            {
                "success": True,
                "errors": "parameter value (Phantom) is not listed in the candidate List.",
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "cmake_configure_result.json",
        "build_result.json",
        "unit_test_result.json",
    ):
        (output_dir / name).write_text('{"success": true}', encoding="utf-8")

    gate = gia._summarize_runtime_gate_result(
        result={"success": True, "warnings": []},
        attempt=1,
        project_dir=project_dir,
        output_dir=output_dir,
    )

    assert gate["status"] == "fail"
    assert any("event_table.csv has no event rows" in error for error in gate["errors"])
    assert any("edep_3d.csv has no non-zero edep_MeV bins" in error for error in gate["errors"])
    assert any("dose_3d.csv has no non-zero dose_Gy bins" in error for error in gate["errors"])
    assert any("Smoke simulation stderr" in error for error in gate["errors"])


def test_runtime_failure_context_includes_smoke_log_and_runtime_sources(tmp_path) -> None:
    project_dir = tmp_path / "runtime_attempt_1" / "geant4_project"
    output_dir = tmp_path / "runtime_attempt_1" / "g4_output_package"
    (project_dir / "src").mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (project_dir / "main.cc").write_text("int main() { return 0; }\n", encoding="utf-8")
    (project_dir / "src" / "ScoringManager.cc").write_text(
        "void CollectEventData() { /* scoring observation */ }\n",
        encoding="utf-8",
    )
    smoke_path = output_dir / "smoke_simulation_result.json"
    smoke_path.write_text(
        json.dumps(
            {
                "success": False,
                "log_tail": "SMOKE_LOG_SENTINEL: entered run initialization",
                "errors": "Segmentation fault (core dumped)",
            }
        ),
        encoding="utf-8",
    )

    compact = gia._compact_runtime_failure_context(
        {
            "status": "fail",
            "project_dir": str(project_dir),
            "artifacts": [str(smoke_path)],
            "errors": ["runtime failed"],
        }
    )

    artifact_text = json.dumps(compact["artifact_summaries"], ensure_ascii=False)
    source_text = json.dumps(compact["runtime_project_files"], ensure_ascii=False)
    assert "SMOKE_LOG_SENTINEL" in artifact_text
    assert "src/ScoringManager.cc" in source_text
    assert "scoring observation" in source_text


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
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    assert report["mock_provider_only"] is True
    assert repaired["metadata"]["global_integration_agent"]["runtime_gate_required"] is True


@pytest.mark.asyncio
async def test_global_integration_agent_reacts_to_runtime_gate_observation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    responses = [
        {
            "status": "integrated",
            "proposed_patch": {
                "changed_files": [
                    {"path": "main.cc", "new_content": "int main() { return 1; }\n"}
                ]
            },
            "issues_fixed": [{"target": "main.cc", "message": "initial integration"}],
            "errors": [],
        },
        {
            "status": "integrated",
            "proposed_patch": {
                "changed_files": [
                    {"path": "main.cc", "new_content": "int main() { return 0; }\n"}
                ]
            },
            "issues_fixed": [{"target": "main.cc", "message": "fixed runtime failure"}],
            "errors": [],
        },
    ]
    gateway = _SequenceGateway(responses)
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        if attempt == 1:
            return {
                "status": "fail",
                "attempt": attempt,
                "errors": ["compile failed: main.cc returned wrong wiring"],
                "warnings": [],
                "missing_outputs": ["g4_summary.json"],
            }
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

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
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_react",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_repair_rounds=2,
    )

    assert report["status"] == "passed"
    assert runtime_attempts == [1, 2]
    assert len(gateway.prompts) == 2
    assert "runtime repair round 1" in gateway.prompts[1]
    assert "compile failed: main.cc returned wrong wiring" in gateway.prompts[1]
    main_entry = next(f for f in repaired["changed_files"] if f["path"] == "main.cc")
    assert "return 0" in main_entry["new_content"]


@pytest.mark.asyncio
async def test_global_integration_runtime_attempt_offset_resumes_after_existing_attempt(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    response = {
        "status": "integrated",
        "proposed_patch": {
            "changed_files": [
                {"path": "main.cc", "new_content": "int main() { return 0; }\n"}
            ]
        },
        "issues_fixed": [{"target": "main.cc", "message": "resume from attempt 1"}],
        "errors": [],
    }
    gateway = _Gateway(response)
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

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
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_resume_offset",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_failure_context={"status": "fail", "errors": ["attempt 1 failed"]},
        runtime_repair_rounds=1,
        runtime_attempt_offset=1,
    )

    assert report["status"] == "passed"
    assert runtime_attempts == [2]
    assert "runtime repair round 1" in gateway.prompts[0]
    assert "attempt 1 failed" in gateway.prompts[0]


@pytest.mark.asyncio
async def test_global_integration_persists_repairing_state_before_retry_call(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _InitialThenErrorGateway(
        {
            "status": "integrated",
            "proposed_patch": {
                "changed_files": [
                    {"path": "main.cc", "new_content": "int main() { return 1; }\n"}
                ]
            },
            "issues_fixed": [{"target": "main.cc", "message": "initial integration"}],
            "errors": [],
        },
        error="network interrupted",
    )
    persisted_statuses: list[tuple[str, int]] = []
    original_persist_report = gia._persist_report

    def capture_report(report: dict[str, Any], job_id: str) -> None:
        persisted_statuses.append(
            (str(report.get("status")), len(report.get("runtime_gate_attempts", [])))
        )
        original_persist_report(report, job_id)

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "fail",
            "attempt": int(kwargs["attempt"]),
            "errors": ["compile failed after initial patch"],
            "warnings": [],
            "missing_outputs": ["g4_summary.json"],
        }

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
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._persist_report",
        capture_report,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_incremental_persist",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_repair_rounds=2,
    )

    assert report["status"] == "failed"
    assert ("repairing", 1) in persisted_statuses
    assert report["runtime_gate_attempts"][0]["errors"] == ["compile failed after initial patch"]
    persisted_patch = json.loads(
        (
            tmp_path
            / "jobs"
            / "global_integration_incremental_persist"
            / STAGE_CODEGEN
            / "proposed_patch.json"
        ).read_text(encoding="utf-8")
    )
    main_entry = next(f for f in persisted_patch["changed_files"] if f["path"] == "main.cc")
    assert "return 1" in main_entry["new_content"]


@pytest.mark.asyncio
async def test_global_integration_node_uses_five_runtime_react_rounds(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_global_integration_agent(proposed_patch: dict[str, Any], **kwargs: Any):
        captured.update(kwargs)
        return proposed_patch, {"status": "passed", "errors": [], "issues_fixed": []}

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.run_global_integration_agent",
        fake_run_global_integration_agent,
    )

    result = await global_integration_agent_node(
        {
            "job_id": "node_rounds",
            "proposed_patch": _patch(),
            "module_results": {},
            "module_contracts": {},
            "module_contexts": {},
            "interface_contracts": {},
            "runtime_failure_context": {},
            "codegen_errors": [],
        }
    )

    assert captured["runtime_repair_rounds"] == 5
    assert result["global_integration_agent_report"]["status"] == "passed"
