from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from agent_core.g4_codegen.context_coordinator import (
    coordinate_generated_context,
    lookup_generated_code_snippets,
)
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


def _module_results() -> dict[str, Any]:
    return {
        "simulation_core": {
            "module_name": "simulation_core",
            "status": "generated",
            "generated_files": [
                {
                    "path": "include/DetectorConstruction.hh",
                    "operation": "create_or_replace",
                    "new_content": (
                        "#pragma once\n"
                        "class DetectorConstruction {\n"
                        "public:\n"
                        "  DetectorConstruction();\n"
                        "  G4LogicalVolume* GetScoringVolume(const G4String& name) const;\n"
                        "};\n"
                    ),
                    "generated_by": "simulation_core_module_agent",
                    "module_name": "simulation_core",
                    "rationale": "test",
                }
            ],
        }
    }


@pytest.mark.asyncio
async def test_context_coordinator_uses_lite_context_summary_model(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []

    class Gateway:
        profiles = {
            ModelTier.LITE: SimpleNamespace(provider=ModelProvider.OPENAI_COMPATIBLE)
        }

        async def call(self, **kwargs: Any) -> ModelCallResult:
            calls.append(kwargs)
            return ModelCallResult(
                task=kwargs["task"],
                tier=kwargs["tier"],
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="flash-test",
                content=json.dumps(
                    {
                        "status": "ok",
                        "module_summaries": {
                            "simulation_core": {
                                "role": "detector",
                                "files": ["include/DetectorConstruction.hh"],
                                "public_interfaces": [
                                    "GetScoringVolume(const G4String& name) const"
                                ],
                                "constructor_contracts": ["DetectorConstruction()"],
                                "symbols": ["DetectorConstruction"],
                                "integration_notes": ["read header before use"],
                                "risks": [],
                            }
                        },
                        "cross_module_contracts": [],
                        "runtime_contract_notes": [],
                        "recommended_code_reads": [
                            {
                                "path": "include/DetectorConstruction.hh",
                                "reason": "confirm API",
                            }
                        ],
                        "warnings": [],
                    }
                ),
                parsed_json=None,
                latency_ms=12.0,
            )

    monkeypatch.setattr(
        "agent_core.g4_codegen.context_coordinator.get_model_gateway",
        lambda: Gateway(),
    )

    coordination = await coordinate_generated_context(
        job_id="context_coordination",
        module_results=_module_results(),
        module_contracts={},
        target_modules=["runtime_app"],
        coordinator_name="coordinate_core_modules_context",
    )

    assert calls
    assert calls[0]["task"] == ModelTask.CONTEXT_SUMMARY
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[0]["metadata"]["enable_thinking"] is False
    assert coordination["summary_model"]["model_name"] == "flash-test"
    assert "generated_code_lookup_manifest" in coordination


def test_generated_code_lookup_reads_exact_previous_module_snippet(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

    result = lookup_generated_code_snippets(
        [
            {
                "path": "include/DetectorConstruction.hh",
                "symbol": "GetScoringVolume",
                "context_lines": 2,
                "max_chars": 1000,
            }
        ],
        job_id="lookup",
        module_results=_module_results(),
    )

    assert result["status"] == "ok"
    assert result["snippets"][0]["path"] == "include/DetectorConstruction.hh"
    assert "GetScoringVolume" in result["snippets"][0]["content"]
