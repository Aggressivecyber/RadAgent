"""Shared fixtures for MVP-1 E2E tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

E2E_QUERY = "模拟 10 MeV 质子垂直入射 300 微米硅片，输出能量沉积和剂量分布。"

# --- Valid task spec for the E2E scenario ---
VALID_TASK_SPEC = {
    "simulation_scope": ["geant4"],
    "particle": {"type": "proton", "energy_MeV": 10.0, "direction": [0, 0, 1], "events": 1000},
    "target": {"material": "Si", "size_um": [1000.0, 1000.0, 300.0], "geometry_type": "box"},
    "outputs": ["energy_deposition", "dose_distribution"],
    "metadata": {"source": "heuristic_parser"},
}

# --- Minimal valid code generation response ---
VALID_CODE_GEN_RESPONSE = {
    "files": {
        "DetectorConstruction.cc": (
            '#include "DetectorConstruction.hh"\n'
            '#include "G4Box.hh"\n'
            'G4VPhysicalVolume* DetectorConstruction::Construct() {\n'
            '  auto si = new G4Box("Si", 500*um, 500*um, 150*um);\n'
            '  return si;\n'
            "}\n"
        ),
        "DetectorConstruction.hh": (
            "#pragma once\n"
            '#include "G4VUserDetectorConstruction.hh"\n'
            "class DetectorConstruction : public G4VUserDetectorConstruction {\n"
            "  public:\n"
            "    G4VPhysicalVolume* Construct() override;\n"
            "};\n"
        ),
        "geant4_sim.cc": (
            '#include "DetectorConstruction.hh"\n'
            "int main() { return 0; }\n"
        ),
        "CMakeLists.txt": (
            "cmake_minimum_required(VERSION 3.16)\n"
            "project(geant4_sim)\n"
            "find_package(Geant4 REQUIRED)\n"
            "add_executable(geant4_sim geant4_sim.cc src/DetectorConstruction.cc)\n"
            "target_link_libraries(geant4_sim ${Geant4_LIBRARIES})\n"
        ),
    },
    "description": "Minimal Geant4 proton-silicon simulation",
    "assumptions": ["300um Si target", "10 MeV proton"],
}

# --- RAG context that scores >= 0.90 in _compute_score ---
# Must have source_type/doc_type that triggers all three scoring buckets:
#   has_manual (0.30) + has_examples (0.25) + has_contracts (0.20) + base (0.15) = 0.90
HIGH_SCORE_RAG_CONTEXT = [
    {
        "text": "G4Box constructs a box solid with half-lengths...",
        "source": "geant4_manual.md",
        "source_type": "manual",
        "doc_type": "manual",
    },
    {
        "code": "auto box = new G4Box('Si', 500*um, 500*um, 150*um);",
        "language": "cpp",
        "source": "examples/silicon_detector.cc",
        "description": "Silicon detector geometry example",
        "source_type": "example_code",
        "doc_type": "example_code",
    },
    {
        "contract_name": "g4_output_v1",
        "schema": "edep_3d.csv, dose_3d.csv, event_table.csv, g4_summary.json, provenance.json",
        "source": "builtin_default",
        "source_type": "data_contract",
        "doc_type": "contract",
    },
]


@pytest.fixture
def e2e_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate workspace to tmp_path via RADAGENT_WORKSPACE_ROOT."""
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "jobs").mkdir()
    return tmp_path


@pytest.fixture
def e2e_initial_state() -> dict:
    """Build standard E2E initial state (dev mode)."""
    return {
        "user_query": E2E_QUERY,
        "job_id": "",
        "errors": [],
        "retry_count": 0,
        "max_retries_reached": False,
        "execution_mode": "dev_no_geant4_env",
        "skipped_gates": [],
    }


def _make_mock_llm() -> MagicMock:
    """Create a mock LLM that returns appropriate responses for different prompts.

    The mock inspects the prompt content to decide which response to return:
    - task parser prompt → valid task spec JSON
    - code generator prompt → valid code gen JSON
    - fix prompt → same as code gen
    """
    mock_llm = MagicMock()

    task_response = MagicMock()
    task_response.content = json.dumps(VALID_TASK_SPEC)

    code_response = MagicMock()
    code_response.content = json.dumps(VALID_CODE_GEN_RESPONSE)

    async def _ainvoke(prompt: str, **kwargs: object) -> MagicMock:
        if isinstance(prompt, str):
            prompt_lower = prompt.lower()
            if "task parser" in prompt_lower or "task specification" in prompt_lower:
                return task_response
        return code_response

    mock_llm.ainvoke = AsyncMock(side_effect=_ainvoke)
    return mock_llm


def get_e2e_patches(tmp_path: Path) -> list:
    """Build the list of (patch_target, mock_object) tuples for a dev-mode E2E run.

    Mock strategy:
    1. LLM: mock get_llm to return a context-aware mock that returns valid JSON
    2. RAG retrieval: mock _retrieve_source to bypass tool instantiation entirely
       and return HIGH_SCORE_RAG_CONTEXT (scores 0.90 → allow_rag)
    3. Geant4: mock _check_geant4 → False (triggers gate skips)
    4. Registry: mock _REGISTRY_PATH → empty file (forces dev_no_geant4_env)
    """
    mock_llm = _make_mock_llm()

    # Create an empty registry so prepare_local_rag_workspace detects no Geant4
    empty_registry = tmp_path / "empty_registry.json"
    empty_registry.write_text(json.dumps({"sources": {}}))

    return [
        # (patch_target, mock_object)
        ("agent_core.llm.get_llm", MagicMock(return_value=mock_llm)),
        (
            "agent_core.nodes.retrieve_required_context._retrieve_source",
            AsyncMock(return_value=HIGH_SCORE_RAG_CONTEXT),
        ),
        (
            "agent_core.tools.geant4_runner.Geant4Runner._check_geant4",
            MagicMock(return_value=False),
        ),
        (
            "agent_core.nodes.prepare_local_rag_workspace._REGISTRY_PATH",
            empty_registry,
        ),
    ]
