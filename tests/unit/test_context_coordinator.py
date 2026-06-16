from __future__ import annotations

import json
import pytest
from agent_core.g4_codegen.context_coordinator import (
    coordinate_generated_context,
    lookup_generated_code_snippets,
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


def test_context_summary_includes_public_method_signatures() -> None:
    """Runtime agents need full signatures when read_file is disabled."""
    from agent_core.g4_codegen.context_coordinator import _summarize_file

    summary = _summarize_file(
        "simulation_core",
        "include/ScoringManager.hh",
        (
            "class ScoringManager {\n"
            "public:\n"
            "  ScoringManager();\n"
            "  ~ScoringManager();\n"
            "  ScoringManager& operator=(const ScoringManager&) = delete;\n"
            "  void EndOfEvent(const G4String& componentId,\n"
            "                  G4double& edep_MeV,\n"
            "                  G4double& dose_Gy);\n"
            "  G4double GetCumulativeDose(const G4String& componentId) const;\n"
            "private:\n"
            "  void Helper();\n"
            "};\n"
        ),
    )

    assert "EndOfEvent" in summary["public_methods"]
    assert "void EndOfEvent(const G4String& componentId, G4double& edep_MeV, G4double& dose_Gy)" in summary[
        "public_method_signatures"
    ]
    assert "G4double GetCumulativeDose(const G4String& componentId) const" in summary[
        "public_method_signatures"
    ]
    assert all("Helper" not in signature for signature in summary["public_method_signatures"])
    assert all("operator=" not in signature for signature in summary["public_method_signatures"])


@pytest.mark.asyncio
async def test_context_coordinator_uses_deterministic_summary_without_llm(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.models.gateway.get_model_gateway",
        lambda: (_ for _ in ()).throw(
            AssertionError("context coordinator should not call an LLM")
        ),
    )

    coordination = await coordinate_generated_context(
        job_id="context_coordination",
        module_results=_module_results(),
        module_contracts={},
        target_modules=["runtime_app"],
        coordinator_name="coordinate_core_modules_context",
    )

    assert coordination["coordinator"] == "deterministic"
    assert "summary_model" not in coordination
    assert "generated_code_lookup_manifest" in coordination
    assert coordination["module_summaries"]["simulation_core"]["symbols"] == [
        "DetectorConstruction"
    ]


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
