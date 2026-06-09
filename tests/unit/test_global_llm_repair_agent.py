from __future__ import annotations

import json
from typing import Any

import pytest
from agent_core.g4_codegen.global_llm_repair import run_global_llm_repair
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier


def _patch() -> dict[str, Any]:
    return {
        "changed_files": [
            {
                "path": "include/MaterialRegistry.hh",
                "operation": "create_or_replace",
                "new_content": "#pragma once\nclass MaterialRegistry {};\n",
                "zone": "green",
                "generated_by": "material_module_agent",
                "module_name": "material",
                "rationale": "test",
            },
            {
                "path": "src/MaterialRegistry.cc",
                "operation": "create_or_replace",
                "new_content": '#include "MaterialRegistry.hh"\n',
                "zone": "green",
                "generated_by": "material_module_agent",
                "module_name": "material",
                "rationale": "test",
            },
        ]
    }


class _Profile:
    provider = ModelProvider.OPENAI_COMPATIBLE
    model_name = "unit-test-model"


class _Gateway:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.prompts.append(str(kwargs["user_prompt"]))
        return ModelCallResult(
            task=ModelTask.FAILURE_DIAGNOSIS,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content=json.dumps(self.response),
            parsed_json=self.response,
            usage={},
        )


async def _rag_evidence(_query: str) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": "g4-manual",
            "title": "Geant4 Manual",
            "content": "G4ExceptionDescription is used for exception text.",
            "source": "rag",
            "score": 1.0,
        }
    ]


async def _empty_evidence(_query: str) -> list[dict[str, Any]]:
    return []


@pytest.mark.asyncio
async def test_global_llm_repair_prompt_contains_project_files_and_failure_context(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    response = {
        "status": "no_change",
        "proposed_patch": _patch(),
        "issues_fixed": [],
        "errors": [],
    }
    gateway = _Gateway(response)
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair._search_global_repair_rag",
        _rag_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair._search_global_repair_web",
        _empty_evidence,
    )

    repaired, report = await run_global_llm_repair(
        _patch(),
        job_id="global_repair_test",
        runtime_failure_context={
            "build_errors": [
                "MaterialRegistry.cc: invalid operands to binary expression"
            ],
        },
    )

    assert report["status"] == "passed"
    assert repaired["changed_files"]
    prompt = gateway.prompts[0]
    assert "include/MaterialRegistry.hh" in prompt
    assert "src/MaterialRegistry.cc" in prompt
    assert "invalid operands to binary expression" in prompt
    assert "G4ExceptionDescription" in prompt


@pytest.mark.asyncio
async def test_global_llm_repair_rejects_content_field(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    bad_patch = _patch()
    bad_patch["changed_files"][0]["content"] = "forbidden"
    response = {
        "status": "repaired",
        "proposed_patch": bad_patch,
        "issues_fixed": [{"target": "material", "message": "bad schema"}],
        "errors": [],
    }
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair.get_model_gateway",
        lambda: _Gateway(response),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair._search_global_repair_rag",
        _rag_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair._search_global_repair_web",
        _empty_evidence,
    )

    repaired, report = await run_global_llm_repair(
        _patch(),
        job_id="global_repair_bad_schema",
        runtime_failure_context={"build_errors": ["compile failed"]},
    )

    assert repaired == _patch()
    assert report["status"] == "failed"
    assert any("content field is forbidden" in error for error in report["errors"])


@pytest.mark.asyncio
async def test_global_llm_repair_requires_evidence_for_real_provider(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair.get_model_gateway",
        lambda: _Gateway({"status": "no_change", "proposed_patch": _patch()}),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair._search_global_repair_rag",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_llm_repair._search_global_repair_web",
        _empty_evidence,
    )

    _repaired, report = await run_global_llm_repair(
        _patch(),
        job_id="global_repair_no_evidence",
        runtime_failure_context={"build_errors": ["compile failed"]},
    )

    assert report["status"] == "failed"
    assert any("requires RAG/web evidence" in error for error in report["errors"])
