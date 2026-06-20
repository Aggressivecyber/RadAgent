"""Tests for the agentic module agent (native tool-calling into a shared workspace).

Replaces the former one-shot JSON module-agent tests. The model is simulated by a
scripted fake gateway that emits write_file tool calls; the agent must write its
owned files into the shared staging workspace and return them as generated_files.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

from agent_core.agent_loop.loop import AgentLoopResult
from agent_core.g4_codegen.agentic_repair import AGENTIC_SYSTEM_PROMPT
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult
from agent_core.g4_codegen.module_agents import base as module_base
from agent_core.g4_codegen.module_agents import runtime_app_agent
from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.module_agents.beam_physics_agent import BEAM_PHYSICS_SYSTEM_PROMPT
from agent_core.g4_codegen.module_agents.beam_physics_agent import run_beam_physics_agent
from agent_core.g4_codegen.module_agents.runtime_app_agent import RUNTIME_APP_SYSTEM_PROMPT
from agent_core.g4_codegen.module_agents.runtime_app_agent import (
    _group_context as runtime_app_group_context,
)
from agent_core.g4_codegen.module_agents.simulation_core_agent import (
    SIMULATION_CORE_SYSTEM_PROMPT,
    _group_context as simulation_core_group_context,
)
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


def test_agentic_module_prompts_do_not_request_json_responses() -> None:
    """Module agents write files with tools; JSON response instructions waste turns."""
    combined = "\n".join(
        [
            SIMULATION_CORE_SYSTEM_PROMPT,
            BEAM_PHYSICS_SYSTEM_PROMPT,
            RUNTIME_APP_SYSTEM_PROMPT,
        ]
    ).lower()

    assert "只返回 json" not in combined
    assert "return json" not in combined


def test_runtime_app_prompt_requires_browser_visualization_artifacts() -> None:
    prompt = RUNTIME_APP_SYSTEM_PROMPT

    assert "geometry_view.json" in prompt
    assert "particle_tracks.json" in prompt
    assert "energy_deposits.json" in prompt
    assert "真实 step" in prompt
    assert "不得伪造" in prompt
    assert "fGeometryComponents" in prompt
    assert "只有 OutputManager.hh" in prompt
    assert "event_table.csv 和 g4_summary.json" in prompt
    assert "同一个" in prompt


def test_runtime_geometry_size_uses_radius_for_cylinders_with_dz() -> None:
    assert runtime_app_agent._geometry_size_mm(
        {"r": 40000.0, "dz": 60000.0},
        0.001,
    ) == [80.0, 80.0, 60.0]
    assert runtime_app_agent._geometry_size_mm(
        {"r_inner": 32500.0, "r_outer": 57500.0, "dz": 80000.0},
        0.001,
    ) == [115.0, 115.0, 80.0]


def test_module_prompts_prevent_common_geant4_repair_failures() -> None:
    """Initial generation should avoid recurring compile/runtime repair patterns."""
    combined = "\n".join(
        [
            SIMULATION_CORE_SYSTEM_PROMPT,
            BEAM_PHYSICS_SYSTEM_PROMPT,
            RUNTIME_APP_SYSTEM_PROMPT,
        ]
    )

    assert "G4ThreeVector.hh" in combined
    assert "G4Circle.hh" in combined
    assert "G4RotationMatrix.hh" in combined
    assert "class G4RotationMatrix" in combined
    assert "#include <vector>" in combined
    assert "同级" in combined and "包裹" in combined
    assert "voxel" in combined and "max_size" in combined
    assert "SensitiveDetector" in combined
    assert "placeholder" in combined


def test_module_prompt_treats_human_confirmations_as_hard_constraints() -> None:
    prompt = module_base.MODULE_AGENTIC_SYSTEM_PROMPT

    assert "human_confirmation_context" in prompt
    assert "confirmed_constraints" in prompt
    assert "硬约束" in prompt
    assert "默认推断" in prompt


def test_agentic_repair_prompt_requires_batched_error_fixing() -> None:
    """Repair should batch compiler-output fixes instead of one tiny edit per turn."""
    prompt = AGENTIC_SYSTEM_PROMPT

    assert "batch" in prompt.lower()
    assert "same build output" in prompt.lower()
    assert "G4ThreeVector.hh" in prompt
    assert "G4Circle.hh" in prompt
    assert "core dumped" in prompt
    assert "overlap" in prompt.lower()
    assert "output contract" in prompt.lower()
    assert "SensitiveDetector" in prompt
    assert "G4ThreadLocal" in prompt
    assert "tls.hh" in prompt
    assert "physics-list" in prompt
    assert "placeholder" in prompt
    assert "search_text" in prompt
    assert "list_files" in prompt
    assert "fGeometryComponents" in prompt
    assert "geometry_view.json" in prompt
    assert "event_table.csv and g4_summary.json" in prompt


def test_generated_content_validator_rejects_function_body_include() -> None:
    files = [
        GeneratedModuleFile(
            path="src/DetectorConstruction.cc",
            operation="create_or_replace",
            new_content=(
                '#include "DetectorConstruction.hh"\n'
                "void DetectorConstruction::ConstructSDandField() {\n"
                '  #include "SensitiveDetector.hh"\n'
                "}\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        )
    ]

    issues = module_base._find_generated_content_issues(files)

    assert any("include inside function body" in item for item in issues)


def test_generated_content_validator_rejects_placeholder_event_track_ids() -> None:
    files = [
        GeneratedModuleFile(
            path="src/SensitiveDetector.cc",
            operation="create_or_replace",
            new_content=(
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  hit->SetEventID(0); // placeholder event id\n"
                "  hit->SetTrackID(0);\n"
                "  return true;\n"
                "}\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        )
    ]

    issues = module_base._find_generated_content_issues(files)

    assert any("placeholder event/track id" in item for item in issues)


def test_sensitive_detector_postprocess_replaces_placeholder_event_id() -> None:
    source = (
        '#include "SensitiveDetector.hh"\n'
        '#include "G4Step.hh"\n'
        "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
        "  auto* hit = new ::Hit();\n"
        "  const G4Track* track = step->GetTrack();\n"
        "  hit->SetEventID(0);  // placeholder; overwritten in EndOfEvent\n"
        "  hit->SetTrackID(track->GetTrackID());\n"
        "  return true;\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/SensitiveDetector.cc",
        source,
    )
    files = [
        GeneratedModuleFile(
            path="src/SensitiveDetector.cc",
            operation="create_or_replace",
            new_content=content,
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        )
    ]

    assert "SetEventID(0)" not in content
    assert "placeholder" not in content.lower()
    assert "G4RunManager::GetRunManager()->GetCurrentEvent()" in content
    assert "currentEvent ? currentEvent->GetEventID() : -1" in content
    assert '#include "G4RunManager.hh"' in content
    assert '#include "G4Event.hh"' in content
    assert not any(
        "placeholder event/track id" in item
        for item in module_base._find_generated_content_issues(files)
    )


def test_sensitive_detector_postprocess_removes_stale_placeholder_event_comments() -> None:
    source = (
        '#include "SensitiveDetector.hh"\n'
        '#include "G4RunManager.hh"\n'
        '#include "G4Event.hh"\n'
        "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
        "  auto* hit = new ::Hit();\n"
        "  const G4Event* currentEvent = G4RunManager::GetRunManager()->GetCurrentEvent();\n"
        "  // Event ID is set in EndOfEvent from the hits collection context;\n"
        "  // store 0 here as a placeholder that EndOfEvent will overwrite if needed.\n"
        "  // The actual event ID is available from G4HCofThisEvent in EndOfEvent.\n"
        "  hit->SetEventID(currentEvent ? currentEvent->GetEventID() : -1);\n"
        "  hit->SetTrackID(step->GetTrack()->GetTrackID());\n"
        "  return true;\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/SensitiveDetector.cc",
        source,
    )
    files = [
        GeneratedModuleFile(
            path="src/SensitiveDetector.cc",
            operation="create_or_replace",
            new_content=content,
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        )
    ]

    assert "placeholder" not in content.lower()
    assert "currentEvent ? currentEvent->GetEventID() : -1" in content
    assert not any(
        "placeholder event/track id" in item
        for item in module_base._find_generated_content_issues(files)
    )


def test_sensitive_detector_postprocess_qualifies_dynamic_cast_hit_type() -> None:
    source = (
        '#include "SensitiveDetector.hh"\n'
        '#include "Hit.hh"\n'
        "void SensitiveDetector::EndOfEvent(G4HCofThisEvent*) {\n"
        "  for (std::size_t i = 0; i < fHitsCollection->entries(); ++i) {\n"
        "    Hit* hit = dynamic_cast<Hit*>((*fHitsCollection)[i]);\n"
        "    if (hit) { hit->SetEventID(1); }\n"
        "  }\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/SensitiveDetector.cc",
        source,
    )

    assert "Hit* hit = dynamic_cast<Hit*>" not in content
    assert "::Hit* hit = dynamic_cast<::Hit*>" in content


def test_sensitive_detector_postprocess_qualifies_collection_hit_pointer() -> None:
    source = (
        '#include "SensitiveDetector.hh"\n'
        '#include "Hit.hh"\n'
        "void SensitiveDetector::EndOfEvent(G4HCofThisEvent*) {\n"
        "  for (G4int i = 0; i < fHitsCollection->entries(); ++i) {\n"
        "    Hit* hit = (*fHitsCollection)[i];\n"
        "    if (hit) { hit->SetEventID(1); }\n"
        "  }\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/SensitiveDetector.cc",
        source,
    )

    assert not re.search(r"(?<!:)Hit\* hit = \(\*fHitsCollection\)\[i\];", content)
    assert "::Hit* hit = (*fHitsCollection)[i];" in content


def test_detector_construction_postprocess_normalizes_scoring_manager_api() -> None:
    source = (
        '#include "DetectorConstruction.hh"\n'
        '#include "ScoringManager.hh"\n'
        '#include "G4SystemOfUnits.hh"\n'
        "DetectorConstruction::DetectorConstruction()\n"
        "  : fScoringManager(nullptr)\n"
        "{\n"
        "  fScoringManager = new ScoringManager();\n"
        "}\n"
        "DetectorConstruction::~DetectorConstruction()\n"
        "{\n"
        "  delete fScoringManager;\n"
        "}\n"
        "void DetectorConstruction::ConstructSDandField()\n"
        "{\n"
        '  const G4String componentId = "silicon_detector";\n'
        "  G4LogicalVolume* siLog = GetLogicalVolume(componentId);\n"
        "  fScoringManager->RegisterRegionScoring(componentId, siLog);\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/DetectorConstruction.cc",
        source,
    )

    assert "new ScoringManager()" not in content
    assert "delete fScoringManager" not in content
    assert "do not delete it.}" not in content
    assert "do not delete it.\n}" in content
    assert "fScoringManager = ScoringManager::Instance();" in content
    assert "RegisterRegionScoring" not in content
    assert "fScoringManager->RegisterRegion(componentId, regionMassKg);" in content
    assert "regionMassKg" in content
    assert "siMassKg" not in content


def test_detector_construction_postprocess_removes_physical_volume_registry_calls() -> None:
    source = (
        '#include "DetectorConstruction.hh"\n'
        "G4VPhysicalVolume* DetectorConstruction::Construct()\n"
        "{\n"
        "  G4VPhysicalVolume* worldPV = nullptr;\n"
        "  G4VPhysicalVolume* siPV = nullptr;\n"
        '  pm->PlaceVolume("world", worldPV);\n'
        '  pm->PlaceVolume("silicon_detector", siPV);\n'
        '  pm->PlaceVolume("valid_component", worldLV, false, childLV, G4ThreeVector(), nullptr, true);\n'
        "  return worldPV;\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/DetectorConstruction.cc",
        source,
    )

    assert 'pm->PlaceVolume("world", worldPV);' not in content
    assert 'pm->PlaceVolume("silicon_detector", siPV);' not in content
    assert 'pm->PlaceVolume("valid_component", worldLV, false, childLV, G4ThreeVector(), nullptr, true);' in content
    assert "legacy physical-volume registry call removed: pm->PlaceVolume" not in content
    assert "legacy physical-volume registry call removed" in content


def test_scoring_manager_postprocess_adds_stable_header_api() -> None:
    source = (
        "#ifndef SCORING_MANAGER_HH\n"
        "#define SCORING_MANAGER_HH\n"
        '#include "globals.hh"\n'
        "#include <vector>\n"
        "class ScoringManager\n"
        "{\n"
        "public:\n"
        "  ScoringManager();\n"
        "  ~ScoringManager();\n"
        "  void RegisterRegion(const G4String& componentId,\n"
        "                      G4double massKg,\n"
        "                      const std::vector<G4String>& quantities);\n"
        "};\n"
        "#endif\n"
    )

    content = module_base._postprocess_generated_module_content(
        "include/ScoringManager.hh",
        source,
    )

    assert "static ScoringManager* Instance();" in content
    assert "void RegisterRegion(const G4String& componentId, G4double massKg);" in content


def test_scoring_manager_postprocess_adds_stable_source_api() -> None:
    source = (
        '#include "ScoringManager.hh"\n'
        "ScoringManager::ScoringManager() {}\n"
        "ScoringManager::~ScoringManager() {}\n"
        "void ScoringManager::RegisterRegion(const G4String& componentId,\n"
        "                                    G4double massKg,\n"
        "                                    const std::vector<G4String>& quantities)\n"
        "{\n"
        "  (void)componentId;\n"
        "  (void)massKg;\n"
        "  (void)quantities;\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/ScoringManager.cc",
        source,
    )

    assert "ScoringManager* ScoringManager::Instance()" in content
    assert "static ScoringManager instance;" in content
    assert "void ScoringManager::RegisterRegion(const G4String& componentId, G4double massKg)" in content
    assert 'RegisterRegion(componentId, massKg, {"edep_MeV", "dose_Gy"});' in content


def test_stepping_action_postprocess_includes_scoring_manager_when_used() -> None:
    source = (
        '#include "SteppingAction.hh"\n'
        '#include "G4Step.hh"\n'
        "void SteppingAction::UserSteppingAction(const G4Step* step) {\n"
        '  ScoringManager::Instance()->AccumulateEdep("silicon_detector", 1.0, 0);\n'
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/SteppingAction.cc",
        source,
    )

    assert '#include "ScoringManager.hh"' in content


def test_generated_content_validator_ignores_hit_allocation_text_in_comments() -> None:
    files = [
        GeneratedModuleFile(
            path="src/SensitiveDetector.cc",
            operation="create_or_replace",
            new_content=(
                "// Create a new Hit (use global scope to avoid hiding by\n"
                "// G4VSensitiveDetector::Hit)\n"
                "auto* hit = new ::Hit();\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        )
    ]

    issues = module_base._find_generated_content_issues(files)

    assert not any("unqualified Hit allocation" in item for item in issues)


def test_generated_content_validator_allows_negated_placeholder_comments() -> None:
    files = [
        GeneratedModuleFile(
            path="src/SensitiveDetector.cc",
            operation="create_or_replace",
            new_content=(
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  // Event ID from the current event (not a placeholder)\n"
                "  hit->SetEventID(event ? event->GetEventID() : -1);\n"
                "  // G4Event at scoring time -- no placeholder values are used.\n"
                "  hit->SetTrackID(step->GetTrack()->GetTrackID());\n"
                "  return true;\n"
                "}\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        )
    ]

    issues = module_base._find_generated_content_issues(files)

    assert not any("placeholder event/track id" in item for item in issues)


def test_generated_content_validator_rejects_unwired_runtime_output_manager() -> None:
    files = [
        GeneratedModuleFile(
            path="include/OutputManager.hh",
            operation="create_or_replace",
            new_content=(
                "class OutputManager {\n"
                "public:\n"
                "  void AddTrackPoint(const TrackPoint& tp);\n"
                "  void AddEnergyDepositPoint(const EnergyDepositPoint& edp);\n"
                "};\n"
            ),
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
        GeneratedModuleFile(
            path="include/SteppingAction.hh",
            operation="create_or_replace",
            new_content=(
                "class EventAction;\n"
                "class ScoringManager;\n"
                "class SteppingAction {\n"
                "public:\n"
                "  SteppingAction(EventAction* eventAction, ScoringManager* scoringMgr);\n"
                "};\n"
            ),
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
        GeneratedModuleFile(
            path="src/SteppingAction.cc",
            operation="create_or_replace",
            new_content=(
                '#include "SteppingAction.hh"\n'
                "void SteppingAction::UserSteppingAction(const G4Step* step) {\n"
                "  G4double edep = step->GetTotalEnergyDeposit();\n"
                "  if (edep <= 0.0) return;\n"
                "  // Actually, the cleanest approach is to add OutputManager later.\n"
                "}\n"
            ),
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
        GeneratedModuleFile(
            path="src/ActionInitialization.cc",
            operation="create_or_replace",
            new_content=(
                "void ActionInitialization::Build() const {\n"
                "  auto* eventAction = new EventAction(fOutputManager, scoringMgr);\n"
                "  SetUserAction(new SteppingAction(eventAction, scoringMgr));\n"
                "}\n"
            ),
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
    ]

    issues = module_base._find_generated_content_issues(files)

    assert any("runtime OutputManager data flow not wired" in item for item in issues)


def test_generated_content_validator_rejects_unqualified_hit_allocation_in_sd() -> None:
    files = [
        GeneratedModuleFile(
            path="src/SensitiveDetector.cc",
            operation="create_or_replace",
            new_content=(
                '#include "SensitiveDetector.hh"\n'
                '#include "Hit.hh"\n'
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  auto* hit = new Hit();\n"
                "  fHitsCollection->insert(hit);\n"
                "  return true;\n"
                "}\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        )
    ]

    issues = module_base._find_generated_content_issues(files)

    assert any("unqualified Hit allocation" in item for item in issues)


def test_generated_content_validator_rejects_sensitive_detector_constructor_mismatch() -> None:
    files = [
        GeneratedModuleFile(
            path="include/SensitiveDetector.hh",
            operation="create_or_replace",
            new_content=(
                "class SensitiveDetector {\n"
                "public:\n"
                "  SensitiveDetector(const G4String& name, const G4String& hits, ScoringManager* scoring);\n"
                "};\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        ),
        GeneratedModuleFile(
            path="src/DetectorConstruction.cc",
            operation="create_or_replace",
            new_content=(
                "void DetectorConstruction::ConstructSDandField() {\n"
                '  auto* sd = new SensitiveDetector("HpgeCrystalSD", "hpge_crystal_Hits");\n'
                "}\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        ),
    ]

    issues = module_base._find_generated_content_issues(files)

    assert any("SensitiveDetector constructor argument mismatch" in item for item in issues)


def test_sensitive_detector_constructor_validator_ignores_copy_constructor() -> None:
    files = [
        GeneratedModuleFile(
            path="include/SensitiveDetector.hh",
            operation="create_or_replace",
            new_content=(
                "class SensitiveDetector {\n"
                "public:\n"
                "  SensitiveDetector(const SensitiveDetector&);\n"
                "  SensitiveDetector(const G4String& name, const G4String& hits, ScoringManager* scoring);\n"
                "};\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        ),
        GeneratedModuleFile(
            path="src/DetectorConstruction.cc",
            operation="create_or_replace",
            new_content=(
                "void DetectorConstruction::ConstructSDandField() {\n"
                '  auto* sd = new SensitiveDetector("HpgeCrystalSD", "hpge_crystal_Hits");\n'
                "}\n"
            ),
            generated_by="test",
            module_name="simulation_core",
            rationale="test",
        ),
    ]

    issues = module_base._find_generated_content_issues(files)

    assert any("expected 3, found 2" in item for item in issues)


def test_simulation_core_later_file_groups_can_trust_prior_file_summaries() -> None:
    """Later file groups should not spend a model turn rereading same-module headers."""
    ctx = simulation_core_group_context(
        {"module_contract": {"responsibilities": []}},
        group_name="detector_geometry",
        output_files=["include/DetectorConstruction.hh", "src/DetectorConstruction.cc"],
        group_goal="test",
        prior_files=[
            {
                "path": "include/MaterialRegistry.hh",
                "header_or_interface_content": "class MaterialRegistry { public: void RegisterMaterials(); };",
            }
        ],
    )

    responsibilities = "\n".join(ctx["module_contract"]["responsibilities"]).lower()
    assert "prior_files" in responsibilities
    assert "do not reread" in responsibilities


def test_simulation_core_file_groups_disable_read_file_tool() -> None:
    """Simulation core has full IR/prior context and should not spend turns reading."""
    ctx = simulation_core_group_context(
        {"module_contract": {"responsibilities": []}},
        group_name="materials_and_placement",
        output_files=["include/MaterialRegistry.hh", "src/MaterialRegistry.cc"],
        group_goal="test",
        prior_files=[],
    )

    assert ctx["agent_tool_policy"] == {"allow_read_file": False}


def test_runtime_app_file_groups_disable_read_file_tool() -> None:
    """Runtime app should use provided summaries/templates instead of read_file turns."""
    cpp_ctx = runtime_app_group_context(
        {
            "module_contract": {"responsibilities": []},
            "existing_generated_file_summaries": [
                {
                    "path": "include/DetectorConstruction.hh",
                    "classes": ["DetectorConstruction"],
                    "constructor_signatures": ["DetectorConstruction()"],
                    "public_methods": ["Construct"],
                }
            ],
        },
        group_name="runtime_cpp",
        output_files=["main.cc", "CMakeLists.txt"],
        group_goal="test",
        prior_files=[],
    )
    macro_ctx = runtime_app_group_context(
        {"module_contract": {"responsibilities": []}},
        group_name="runtime_macros",
        output_files=["macros/run.mac"],
        group_goal="test",
        prior_files=[],
    )

    assert cpp_ctx["agent_tool_policy"] == {"allow_read_file": False}
    assert cpp_ctx["existing_generated_file_summaries"][0]["path"] == (
        "include/DetectorConstruction.hh"
    )
    assert macro_ctx["agent_tool_policy"] == {"allow_read_file": False}


@pytest.mark.asyncio
async def test_beam_physics_agent_disables_read_file_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Beam/physics generation should not spend a first turn reading geometry headers."""
    captured_contexts: list[dict[str, Any]] = []

    async def fake_run_module_agent(
        *,
        module_name: str,
        module_context: dict[str, Any],
        system_prompt: str = "",
    ) -> ModuleAgentResult:
        del system_prompt
        assert module_name == "beam_physics"
        captured_contexts.append(module_context)
        return ModuleAgentResult(
            module_name="beam_physics",
            status="generated",
            generated_files=[],
        )

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.beam_physics_agent.run_module_agent",
        fake_run_module_agent,
    )

    await run_beam_physics_agent(
        {
            "job_id": "job_beam_no_read",
            "module_name": "beam_physics",
            "module_contract": {"output_files": ["src/PrimaryGeneratorAction.cc"]},
        }
    )

    assert captured_contexts[0]["agent_tool_policy"] == {"allow_read_file": False}


@pytest.mark.asyncio
async def test_beam_physics_agent_exposes_write_tools_without_read_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Beam/physics should be able to finish in one write batch without read_file."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    owned = {
        "include/PrimaryGeneratorAction.hh": "#pragma once\n",
        "src/PrimaryGeneratorAction.cc": '#include "PrimaryGeneratorAction.hh"\n',
        "include/PhysicsListFactoryWrapper.hh": "#pragma once\n",
        "src/PhysicsListFactoryWrapper.cc": '#include "PhysicsListFactoryWrapper.hh"\n',
        "macros/physics_list.mac": "/run/setCut 10 um\n",
    }
    fake_gw = _FakeGateway(owned)
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_beam_physics_agent(
        {
            "job_id": "job_beam_write_only",
            "module_name": "beam_physics",
            "module_contract": {"output_files": list(owned.keys())},
        }
    )

    tool_names = [tool["function"]["name"] for tool in fake_gw.call_kwargs[0]["tools"]]
    assert result.status == "generated"
    assert fake_gw.calls == 1
    assert "read_file" not in tool_names
    assert tool_names == ["edit_file", "write_file"]


@pytest.mark.asyncio
async def test_runtime_app_cpp_exposes_write_tools_without_read_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Runtime C++ should start writing from upstream summaries in one batch."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    owned = {
        "include/OutputManager.hh": "#pragma once\nclass OutputManager {};\n",
        "src/OutputManager.cc": '#include "OutputManager.hh"\n',
        "include/ActionInitialization.hh": "#pragma once\nclass ActionInitialization {};\n",
        "src/ActionInitialization.cc": '#include "ActionInitialization.hh"\n',
        "include/RunAction.hh": "#pragma once\nclass RunAction {};\n",
        "src/RunAction.cc": '#include "RunAction.hh"\n',
        "include/EventAction.hh": "#pragma once\nclass EventAction {};\n",
        "src/EventAction.cc": '#include "EventAction.hh"\n',
        "include/SteppingAction.hh": "#pragma once\nclass SteppingAction {};\n",
        "src/SteppingAction.cc": '#include "SteppingAction.hh"\n',
    }
    fake_gw = _FakeGateway(owned)
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await runtime_app_agent.run_runtime_app_agent(
        {
            "job_id": "job_runtime_write_only",
            "module_name": "runtime_app",
            "module_contract": {"output_files": []},
            "existing_generated_file_summaries": [
                {
                    "path": "include/DetectorConstruction.hh",
                    "classes": ["DetectorConstruction"],
                    "constructor_signatures": ["DetectorConstruction()"],
                    "public_methods": ["Construct"],
                },
                {
                    "path": "include/PrimaryGeneratorAction.hh",
                    "classes": ["PrimaryGeneratorAction"],
                    "constructor_signatures": ["PrimaryGeneratorAction()"],
                    "public_methods": ["GeneratePrimaries"],
                },
            ],
        }
    )

    tool_names = [tool["function"]["name"] for tool in fake_gw.call_kwargs[0]["tools"]]
    assert result.status == "generated"
    assert fake_gw.calls == 1
    assert "read_file" not in tool_names
    assert tool_names == ["edit_file", "write_file"]


class _FakeGateway:
    """Emits a write_file tool call for each owned file, then stops."""

    def __init__(self, owned_files: dict[str, str]) -> None:
        self._owned = owned_files
        self._fired = False
        self.calls = 0
        self.call_kwargs: list[dict[str, Any]] = []

    async def call(self, **kwargs: Any) -> ModelCallResult:  # type: ignore[no-untyped-def]
        self.calls += 1
        self.call_kwargs.append(kwargs)
        if not self._fired:
            self._fired = True
            tool_calls = [
                {
                    "id": f"call_{i}",
                    "name": "write_file",
                    "arguments": json.dumps({"path": path, "content": content}),
                }
                for i, (path, content) in enumerate(self._owned.items())
            ]
            return ModelCallResult(
                task=ModelTask.CODEGEN,
                tier=ModelTier.PRO,
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="fake",
                content="",
                tool_calls=tool_calls,
                finish_reason="tool_calls",
            )
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="fake",
            content="DONE",
            tool_calls=[],
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_agentic_module_agent_writes_owned_files_to_shared_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    owned = {
        "include/Hit.hh": "#pragma once\nclass Hit {};\n",
        "src/Hit.cc": '#include "Hit.hh"\n',
    }
    fake_gw = _FakeGateway(owned)
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )
    # Skip the example-lookup pre-fetch (it hits the gateway / knowledge base).
    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_agentic_test",
        "module_name": "simulation_core",
        "module_contract": {"output_files": list(owned.keys())},
    }
    result = await run_module_agent("simulation_core", module_context)

    assert result.status == "generated"
    assert {f.path for f in result.generated_files} == set(owned.keys())
    by_path = {f.path: f.new_content for f in result.generated_files}
    assert "class Hit" in by_path["include/Hit.hh"]
    assert by_path["src/Hit.cc"].startswith('#include "Hit.hh"')
    # Files were actually written to the shared staging workspace.
    staged = workspace / "jobs" / "job_agentic_test"
    found = list(staged.rglob("module_workspace"))
    assert found, "module_workspace staging dir must exist"
    written = found[0]
    assert (written / "include" / "Hit.hh").read_text().startswith("#pragma once")


@pytest.mark.asyncio
async def test_agentic_module_agent_seeds_canonical_template_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Module agents should modify a real template scaffold, not fill keywords."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    seen: dict[str, Any] = {}

    class FakeGateway:
        pass

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    async def fake_run_agent_loop(**kwargs: Any) -> AgentLoopResult:
        seen.update(kwargs)
        project_dir = kwargs["toolkit"].project_dir
        assert (project_dir / "config" / "simulation_config.json").is_file()
        assert (project_dir / "include" / "OutputManager.hh").is_file()
        assert (project_dir / "src" / "DetectorConstruction.cc").is_file()
        (project_dir / "include" / "Hit.hh").write_text("#pragma once\nclass Hit {};\n", encoding="utf-8")
        return AgentLoopResult(
            content="DONE",
            stop_reason="stop_hook",
            n_turns=1,
            messages=[],
            tool_audit=[],
        )

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: FakeGateway(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )
    monkeypatch.setattr(
        "agent_core.agent_loop.run_agent_loop",
        fake_run_agent_loop,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_template_workspace",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["include/Hit.hh"]},
        },
    )

    assert result.status == "generated"
    assert "canonical template" in seen["system_prompt"].lower()
    assert "read_file" in seen["user_message"]
    assert "edit_file" in seen["user_message"]
    assert "fill keyword" not in seen["user_message"].lower()


@pytest.mark.asyncio
async def test_agentic_module_agent_does_not_accept_unchanged_template_file_as_generated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A preseeded template file is context, not proof that the model did work."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    class FakeGateway:
        pass

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    async def fake_run_agent_loop(**kwargs: Any) -> AgentLoopResult:
        assert (kwargs["toolkit"].project_dir / "main.cc").is_file()
        return AgentLoopResult(
            content="DONE",
            stop_reason="natural",
            n_turns=1,
            messages=[],
            tool_audit=[],
        )

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: FakeGateway(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )
    monkeypatch.setattr(
        "agent_core.agent_loop.run_agent_loop",
        fake_run_agent_loop,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_template_not_generated",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
        },
    )

    assert result.status == "failed"
    assert result.generated_files == []
    assert any("not modified by current module agent" in error for error in result.errors)


@pytest.mark.asyncio
async def test_agentic_module_agent_stops_after_owned_files_are_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Writing all owned files in one tool round should not require a DONE round-trip."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    owned = {
        "include/PrimaryGeneratorAction.hh": "#pragma once\nclass PrimaryGeneratorAction {};\n",
        "src/PrimaryGeneratorAction.cc": '#include "PrimaryGeneratorAction.hh"\n',
    }
    fake_gw = _FakeGateway(owned)
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_fast_stop",
        "module_name": "beam_physics",
        "module_contract": {"output_files": list(owned.keys())},
    }
    result = await run_module_agent("beam_physics", module_context)

    assert result.status == "generated"
    assert fake_gw.calls == 1
    assert result.repair_attempts[0]["stop_reason"] == "stop_hook"
    assert result.repair_attempts[0]["n_turns"] == 1


@pytest.mark.asyncio
async def test_agentic_module_agent_disables_provider_thinking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tool-driven module codegen should avoid slow provider thinking mode."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({"main.cc": "int main(){return 0;}\n"})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_no_thinking",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
        },
    )

    assert fake_gw.call_kwargs[0]["metadata"]["enable_thinking"] is False


@pytest.mark.asyncio
async def test_agentic_module_agent_defaults_to_model_window_compaction_without_prompt_truncation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Module agents should let the shared loop manage window-aware compression."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    monkeypatch.delenv("RADAGENT_MODULE_AGENT_HISTORY_CHARS", raising=False)
    monkeypatch.delenv("RADAGENT_MODULE_CONTEXT_PROMPT_CHARS", raising=False)
    seen: dict[str, Any] = {}

    class FakeGateway:
        pass

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    async def fake_run_agent_loop(**kwargs: Any) -> AgentLoopResult:
        seen.update(kwargs)
        project_dir = kwargs["toolkit"].project_dir
        (project_dir / "main.cc").write_text("int main(){return 0;}\n", encoding="utf-8")
        return AgentLoopResult(
            content="DONE",
            stop_reason="stop_hook",
            n_turns=1,
            messages=[],
            tool_audit=[],
        )

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: FakeGateway(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )
    monkeypatch.setattr(
        "agent_core.agent_loop.run_agent_loop",
        fake_run_agent_loop,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_module_compaction",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
            "g4_model_ir_subset": {"components": [{"payload": "x" * 80_000}]},
        },
    )

    assert result.status == "generated"
    assert seen["max_history_chars"] is None
    assert seen["preserve_recent_tool_messages"] == 1
    assert "...[module_context truncated]" not in seen["user_message"]
    assert "x" * 1_000 in seen["user_message"]


@pytest.mark.asyncio
async def test_agentic_module_agent_context_compaction_preserves_human_confirmations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default module prompts should not truncate user-confirmed hard constraints."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    monkeypatch.delenv("RADAGENT_MODULE_CONTEXT_PROMPT_CHARS", raising=False)
    seen: dict[str, Any] = {}

    class FakeGateway:
        pass

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    async def fake_run_agent_loop(**kwargs: Any) -> AgentLoopResult:
        seen.update(kwargs)
        project_dir = kwargs["toolkit"].project_dir
        (project_dir / "main.cc").write_text("int main(){return 0;}\n", encoding="utf-8")
        return AgentLoopResult(
            content="DONE",
            stop_reason="stop_hook",
            n_turns=1,
            messages=[],
            tool_audit=[],
        )

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: FakeGateway(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )
    monkeypatch.setattr(
        "agent_core.agent_loop.run_agent_loop",
        fake_run_agent_loop,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_preserve_hc",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
            "g4_model_ir_subset": {"low_value_payload": "x" * 90_000},
            "human_confirmation_context": {
                "status": "confirmed",
                "critical_confirmations": ["geometry.detector_radius_mm"],
                "confirmed_constraints": [
                    {
                        "category": "geometry",
                        "parameter": "detector_radius_mm",
                        "value": "25 mm",
                        "impact": "Controls the visible detector size and scoring volume.",
                    }
                ],
            },
        },
    )

    assert result.status == "generated"
    assert "...[module_context truncated]" not in seen["user_message"]
    assert "human_confirmation_context" in seen["user_message"]
    assert "detector_radius_mm" in seen["user_message"]
    assert "25 mm" in seen["user_message"]
    assert "x" * 1_000 in seen["user_message"]


@pytest.mark.asyncio
async def test_agentic_module_agent_context_compaction_preserves_repair_lessons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default module prompts should keep repair lessons learned from prior failures."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    monkeypatch.delenv("RADAGENT_MODULE_CONTEXT_PROMPT_CHARS", raising=False)
    seen: dict[str, Any] = {}

    class FakeGateway:
        pass

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    async def fake_run_agent_loop(**kwargs: Any) -> AgentLoopResult:
        seen.update(kwargs)
        project_dir = kwargs["toolkit"].project_dir
        (project_dir / "main.cc").write_text("int main(){return 0;}\n", encoding="utf-8")
        return AgentLoopResult(
            content="DONE",
            stop_reason="stop_hook",
            n_turns=1,
            messages=[],
            tool_audit=[],
        )

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: FakeGateway(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )
    monkeypatch.setattr(
        "agent_core.agent_loop.run_agent_loop",
        fake_run_agent_loop,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_preserve_lessons",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
            "g4_model_ir_subset": {"low_value_payload": "x" * 90_000},
            "agentic_repair_lessons": {
                "source": "agentic_repair_lessons",
                "lesson_count": 1,
                "lessons": [
                    {
                        "id": "visual_workbench_artifact",
                        "prompt_instruction": (
                            "Write real geometry_view.json, particle_tracks.json, "
                            "and energy_deposits.json from runtime data."
                        ),
                        "count": 3,
                    }
                ],
            },
        },
    )

    assert result.status == "generated"
    assert "...[module_context truncated]" not in seen["user_message"]
    assert "agentic_repair_lessons" in seen["user_message"]
    assert "visual_workbench_artifact" in seen["user_message"]
    assert "energy_deposits.json" in seen["user_message"]
    assert "x" * 1_000 in seen["user_message"]


@pytest.mark.asyncio
async def test_agentic_module_agent_can_disable_read_file_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """File groups with complete prior context should be forced to write, not inspect."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({"main.cc": "int main(){return 0;}\n"})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_no_read_file",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
            "agent_tool_policy": {"allow_read_file": False},
        },
    )

    tool_names = {
        tool["function"]["name"]
        for tool in fake_gw.call_kwargs[0]["tools"]
    }
    assert "read_file" not in tool_names
    assert tool_names == {"write_file", "edit_file"}


@pytest.mark.asyncio
async def test_agentic_module_agent_fails_on_critical_generated_content_issue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Critical C++ anti-patterns should stop before expensive integration repair."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    bad_source = (
        '#include "DetectorConstruction.hh"\n'
        "void DetectorConstruction::ConstructSDandField() {\n"
        '  #include "SensitiveDetector.hh"\n'
        "}\n"
    )
    fake_gw = _FakeGateway({"src/DetectorConstruction.cc": bad_source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_critical_issue",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["src/DetectorConstruction.cc"]},
        },
    )

    assert result.status == "failed"
    assert any("include inside function body" in error for error in result.errors)


@pytest.mark.asyncio
async def test_agentic_module_agent_qualifies_hit_allocation_before_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A deterministic Hit namespace fix should happen before build/repair."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "SensitiveDetector.hh"\n'
        '#include "Hit.hh"\n'
        "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
        "  auto* hit = new Hit();\n"
        "  fHitsCollection->insert(hit);\n"
        "  return true;\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/SensitiveDetector.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_hit_namespace",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["src/SensitiveDetector.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "::Hit* hit = new ::Hit();" in content
    assert "new Hit()" not in content


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_events_requested_summary_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """g4_summary.json must expose the runtime-audited events_requested field."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "OutputManager.hh"\n'
        "void OutputManager::WriteSummary(G4int totalEvents) {\n"
        '  ofs << "  \\"total_events\\": " << totalEvents << ",\\n";\n'
        "}\n"
    )
    fake_gw = _FakeGateway({"src/OutputManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_summary_contract",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/OutputManager.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '\\"events_requested\\": ' in content
    assert content.index('\\"events_requested\\"') > content.index('\\"total_events\\"')


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_events_requested_for_endl_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "OutputManager.hh"\n'
        "void OutputManager::WriteSummary(G4int totalEvents) {\n"
        '  ofs << "  \\"total_events\\": " << totalEvents << "," << std::endl;\n'
        "}\n"
    )
    fake_gw = _FakeGateway({"src/OutputManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_summary_contract_endl",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/OutputManager.cc"]},
        },
    )

    assert result.status == "generated"
    assert '\\"events_requested\\": ' in result.generated_files[0].new_content


@pytest.mark.asyncio
async def test_agentic_module_agent_replaces_shell_mkdir_in_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        "#include <cstdlib>\n"
        "int main(int argc, char** argv) {\n"
        '  std::string cmd = "mkdir -p " + outDir;\n'
        "  std::system(cmd.c_str());\n"
        "  return 0;\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"main.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_main_mkdir",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "std::filesystem::create_directories(outDir)" in content
    assert "std::system" not in content
    assert "#include <filesystem>" in content


@pytest.mark.asyncio
async def test_agentic_module_agent_converts_g4string_to_filesystem_path_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """std::filesystem::path cannot be constructed directly from G4String."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "OutputManager.hh"\n'
        "#include <filesystem>\n"
        "void OutputManager::WriteAll() {\n"
        "  std::filesystem::path outPath(fOutputDir);\n"
        '  std::filesystem::path summaryPath = fOutputDir / "g4_summary.json";\n'
        "}\n"
    )
    fake_gw = _FakeGateway({"src/OutputManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_g4string_filesystem_path",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/OutputManager.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "std::filesystem::path outPath(fOutputDir.c_str());" in content
    assert (
        'std::filesystem::path summaryPath = std::filesystem::path(fOutputDir.c_str()) / "g4_summary.json";'
        in content
    )


@pytest.mark.asyncio
async def test_agentic_module_agent_derives_output_tables_from_deposits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "OutputManager.hh"\n'
        "#include <fstream>\n"
        "#include <iomanip>\n"
        "#include <map>\n"
        "void OutputManager::AddEnergyDeposit(G4int eventID, G4int trackID,\n"
        "                                      const G4String& volume,\n"
        "                                      G4double x, G4double y, G4double z,\n"
        "                                      G4double edepMeV)\n"
        "{\n"
        "  if (eventID >= 100) return;\n"
        "  if (edepMeV <= 0.0) return;\n"
        "  std::lock_guard<std::mutex> lock(fMutex);\n"
        "  fDeposits.push_back({eventID, trackID, volume, x, y, z, edepMeV});\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  G4double totalEdep = 0.0;\n"
        "  for (const auto& r : fEventRows) totalEdep += r.edepMeV;\n"
        "}\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  for (const auto& r : fEventRows) {\n"
        "    ofs << r.eventID << \",\" << r.edepMeV << \",\" << r.doseGy << \"\\n\";\n"
        "  }\n"
        "}\n"
        "void OutputManager::WriteEdep3dCsv()\n"
        "{\n"
        "  for (const auto& b : fVoxelBins) {\n"
        "    ofs << b.x << \",\" << b.y << \",\" << b.z << \",\" << b.edepMeV << \"\\n\";\n"
        "  }\n"
        "}\n"
        "void OutputManager::WriteDose3dCsv()\n"
        "{\n"
        "  for (const auto& b : fVoxelBins) {\n"
        "    ofs << b.x << \",\" << b.y << \",\" << b.z << \",\" << b.doseGy << \"\\n\";\n"
        "  }\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/OutputManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_output_tables_from_deposits",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/OutputManager.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "_BuildEventRowsFromDeposits" in content
    assert "_BuildVoxelBinsFromDeposits" in content
    assert "const auto eventRowsForOutput = _BuildEventRowsFromDeposits" in content
    assert "const auto voxelBinsForOutput = _BuildVoxelBinsFromDeposits" in content
    assert "for (const auto& r : eventRowsForOutput)" in content
    assert "for (const auto& b : voxelBinsForOutput)" in content


@pytest.mark.asyncio
async def test_agentic_module_agent_derives_event_records_from_energy_deposits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "OutputManager.hh"\n'
        "#include <fstream>\n"
        "#include <iomanip>\n"
        "#include <map>\n"
        "void OutputManager::RecordEnergyDeposit(G4int eventID, G4int trackID,\n"
        "                                        const G4String& volume,\n"
        "                                        const G4ThreeVector& position,\n"
        "                                        G4double edep_MeV)\n"
        "{\n"
        "  if (edep_MeV <= 0.0) return;\n"
        "  fEnergyDeposits.push_back({eventID, trackID, volume, position, edep_MeV});\n"
        "  fEdepGrid[{0, 0, 0}] += edep_MeV;\n"
        "  fDoseGrid[{0, 0, 0}] += edep_MeV * 1.0e-13;\n"
        "}\n"
        "void OutputManager::WriteEventTableCSV()\n"
        "{\n"
        "  ofs << \"EventID,edep_MeV,dose_Gy\" << \"\\n\";\n"
        "  for (const auto& rec : fEventRecords) {\n"
        "    ofs << rec.eventID << rec.edep_MeV << rec.dose_Gy;\n"
        "  }\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  G4double totalEdep = 0.0;\n"
        "  G4double totalDose = 0.0;\n"
        "  for (const auto& rec : fEventRecords) {\n"
        "    totalEdep += rec.edep_MeV;\n"
        "    totalDose += rec.dose_Gy;\n"
        "  }\n"
        "  ofs << \"  \\\"total_events\\\": \" << static_cast<G4int>(fEventRecords.size()) << \",\\n\";\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/OutputManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_output_event_records_from_energy_deposits",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/OutputManager.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "eventRecordFallbackByEvent" in content
    assert "for (const auto& item : eventRecordFallbackByEvent)" in content
    assert "eventRecordCountForSummary" in content
    assert "totalEdep += deposit.edep_MeV" in content


@pytest.mark.asyncio
async def test_agentic_module_agent_derives_event_rows_from_energy_deposit_points(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "OutputManager.hh"\n'
        "#include <fstream>\n"
        "#include <iomanip>\n"
        "#include <map>\n"
        "void OutputManager::AddEnergyDepositPoint(const EnergyDepositPoint& edp)\n"
        "{\n"
        "  if (edp.eventID < 100) {\n"
        "    fEnergyDepositPoints.push_back(edp);\n"
        "  }\n"
        "}\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  ofs << \"EventID,edep_MeV,dose_Gy\\n\";\n"
        "  for (const auto& r : fEventRows) {\n"
        "    ofs << r.eventID << \",\" << r.edep_MeV << \",\" << r.dose_Gy << \"\\n\";\n"
        "  }\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  G4int totalEvents = static_cast<G4int>(fEventRows.size());\n"
        "  G4double totalEdep = 0.0;\n"
        "  G4double totalDose = 0.0;\n"
        "  for (const auto& r : fEventRows) {\n"
        "    totalEdep += r.edep_MeV;\n"
        "    totalDose += r.dose_Gy;\n"
        "  }\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/OutputManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_output_event_rows_from_energy_deposit_points",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/OutputManager.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "eventRowsFromEnergyDepositPoints" in content
    assert "fEnergyDepositPoints" in content
    assert "for (const auto& r : eventRowsForOutput)" in content
    assert "totalEdep += r.edep_MeV" in content


def test_output_manager_point_fallback_declares_event_rows_in_summary_without_total_events() -> None:
    source = (
        '#include "OutputManager.hh"\n'
        "#include <fstream>\n"
        "#include <iomanip>\n"
        "void OutputManager::AddEnergyDepositPoint(const EnergyDepositPoint& edp)\n"
        "{\n"
        "  fEnergyDepositPoints.push_back(edp);\n"
        "}\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  for (const auto& r : fEventRows) {\n"
        "    ofs << r.eventID << \",\" << r.edep_MeV << \",\" << r.dose_Gy << \"\\n\";\n"
        "  }\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  G4double totalEdep = 0.0;\n"
        "  G4double totalDose = 0.0;\n"
        "  for (const auto& r : fEventRows) {\n"
        "    totalEdep += r.edep_MeV;\n"
        "    totalDose += r.dose_Gy;\n"
        "  }\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/OutputManager.cc",
        source,
    )

    summary = content[content.index("void OutputManager::WriteSummaryJson") :]
    assert (
        "const auto eventRowsForOutput = "
        "_BuildEventRowsFromEnergyDepositPoints(fEventRows, fEnergyDepositPoints, fEventsRequested);"
        in summary
    )
    assert summary.index("const auto eventRowsForOutput") < summary.index(
        "for (const auto& r : eventRowsForOutput)"
    )
    assert "for (const auto& r : fEventRows)" not in summary


def test_output_manager_point_fallback_repairs_summary_when_helper_already_exists() -> None:
    source = (
        '#include "OutputManager.hh"\n'
        "#include <vector>\n"
        "namespace {\n"
        "std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints(\n"
        "    const std::vector<EventRow>& rows,\n"
        "    const std::vector<EnergyDepositPoint>&,\n"
        "    G4int)\n"
        "{\n"
        "    std::vector<EventRow> eventRowsFromEnergyDepositPoints;\n"
        "    return rows;\n"
        "}\n"
        "}\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  const auto eventRowsForOutput = _BuildEventRowsFromEnergyDepositPoints(\n"
        "      fEventRows, fEnergyDepositPoints, fEventsRequested);\n"
        "  for (const auto& r : eventRowsForOutput) {}\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  G4double totalEdep = 0.0;\n"
        "  G4double totalDose = 0.0;\n"
        "  for (const auto& r : fEventRows) {\n"
        "    totalEdep += r.edep_MeV;\n"
        "    totalDose += r.dose_Gy;\n"
        "  }\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/OutputManager.cc",
        source,
    )

    summary = content[content.index("void OutputManager::WriteSummaryJson") :]
    assert "const auto eventRowsForOutput" in summary
    assert "for (const auto& r : eventRowsForOutput)" in summary
    assert "for (const auto& r : fEventRows)" not in summary


def test_output_manager_point_fallback_does_not_leak_event_rows_into_provenance() -> None:
    source = (
        '#include "OutputManager.hh"\n'
        "#include <vector>\n"
        "namespace {\n"
        "std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints(\n"
        "    const std::vector<EventRow>& rows,\n"
        "    const std::vector<EnergyDepositPoint>&,\n"
        "    G4int)\n"
        "{\n"
        "    std::vector<EventRow> eventRowsFromEnergyDepositPoints;\n"
        "    return rows;\n"
        "}\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  (void)fEnergyDepositPoints.size();\n"
        "  G4double totalEdep = 0.0;\n"
        "  for (const auto& row : fEventRows) {\n"
        "    totalEdep += row.edep_MeV;\n"
        "  }\n"
        "}\n"
        "void OutputManager::WriteProvenanceJson()\n"
        "{\n"
        "  ofs << fEventRows.size();\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/OutputManager.cc",
        source,
    )

    summary = content[
        content.index("void OutputManager::WriteSummaryJson") : content.index(
            "void OutputManager::WriteProvenanceJson"
        )
    ]
    provenance = content[content.index("void OutputManager::WriteProvenanceJson") :]
    assert "for (const auto& row : eventRowsForOutput)" in summary
    assert "eventRowsForOutput.size()" not in provenance
    assert "fEventRows.size()" in provenance


def test_output_manager_point_fallback_repairs_event_table_when_helper_already_exists() -> None:
    source = (
        '#include "OutputManager.hh"\n'
        "#include <vector>\n"
        "namespace {\n"
        "std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints(\n"
        "    const std::vector<EventRow>& rows,\n"
        "    const std::vector<EnergyDepositPoint>&,\n"
        "    G4int)\n"
        "{\n"
        "    std::vector<EventRow> eventRowsFromEnergyDepositPoints;\n"
        "    return rows;\n"
        "}\n"
        "}\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  (void)fEnergyDepositPoints.size();\n"
        "  for (const auto& row : fEventRows) {\n"
        "    ofs << row.eventID << row.edep_MeV << row.dose_Gy;\n"
        "  }\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/OutputManager.cc",
        source,
    )

    event_table = content[content.index("void OutputManager::WriteEventTableCsv") :]
    assert "const auto eventRowsForOutput" in event_table
    assert "for (const auto& row : eventRowsForOutput)" in event_table
    assert "for (const auto& row : fEventRows)" not in event_table


def test_output_manager_point_fallback_fills_zero_dose_for_existing_edep_rows() -> None:
    source = (
        '#include "OutputManager.hh"\n'
        "#include <vector>\n"
        "namespace {\n"
        "constexpr G4double kRadAgentPointFallbackDosePerMeV = 1.602176634e-13;\n"
        "bool _HasPositiveEventRowsFromPoints(const std::vector<EventRow>& rows)\n"
        "{\n"
        "    for (const auto& row : rows) {\n"
        "        if (row.edepMeV > 0.0 || row.doseGy > 0.0) {\n"
        "            return true;\n"
        "        }\n"
        "    }\n"
        "    return false;\n"
        "}\n"
        "std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints(\n"
        "    const std::vector<EventRow>& rows,\n"
        "    const std::vector<EnergyDepositPoint>& points,\n"
        "    G4int eventsRequested)\n"
        "{\n"
        "    if (_HasPositiveEventRowsFromPoints(rows) || points.empty()) {\n"
        "        return rows;\n"
        "    }\n"
        "    std::vector<EventRow> eventRowsFromEnergyDepositPoints;\n"
        "    return eventRowsFromEnergyDepositPoints;\n"
        "}\n"
        "}\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  (void)fEnergyDepositPoints.size();\n"
        "  ofs << \"EventID,edep_MeV,dose_Gy\\n\";\n"
        "  const auto eventRowsForOutput = _BuildEventRowsFromEnergyDepositPoints(\n"
        "      fEventRows, fEnergyDepositPoints, fEventsRequested);\n"
        "  for (const auto& row : eventRowsForOutput) {\n"
        "    ofs << row.eventID << row.edepMeV << row.doseGy;\n"
        "  }\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/OutputManager.cc",
        source,
    )

    helper = content[
        content.index("std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints") :
        content.index("void OutputManager::WriteEventTableCsv")
    ]
    assert "_RadAgentRowsNeedDoseBackfill" in helper
    assert "backfilled.doseGy = backfilled.edepMeV * kRadAgentPointFallbackDosePerMeV" in helper
    assert "backfilled.dose_Gy" not in helper
    assert "return backfilledRows;" in helper


def test_output_manager_point_fallback_inserts_camelcase_helper_fields() -> None:
    source = (
        '#include "OutputManager.hh"\n'
        "#include <vector>\n"
        "struct EventRow { G4int eventID; G4double edepMeV; G4double doseGy; };\n"
        "struct EnergyDepositPoint { G4int eventID; G4double edepMeV; };\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  (void)fEnergyDepositPoints.size();\n"
        "  ofs << \"EventID,edep_MeV,dose_Gy\\n\";\n"
        "  for (const auto& row : fEventRows) {\n"
        "    ofs << row.eventID << row.edepMeV << row.doseGy;\n"
        "  }\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/OutputManager.cc",
        source,
    )

    helper = content[: content.index("void OutputManager::WriteEventTableCsv")]
    event_table = content[content.index("void OutputManager::WriteEventTableCsv") :]
    assert "point.edepMeV" in helper
    assert "row.edepMeV += point.edepMeV" in helper
    assert "row.doseGy += point.edepMeV * kRadAgentPointFallbackDosePerMeV" in helper
    assert "point.edep_MeV" not in helper
    assert "row.dose_Gy" not in helper
    assert "for (const auto& row : eventRowsForOutput)" in event_table


def test_output_manager_postprocess_adds_array_include_for_std_array() -> None:
    source = (
        '#include "OutputManager.hh"\n'
        "#include <vector>\n"
        "void OutputManager::WriteParticleTracksJson()\n"
        "{\n"
        "  std::vector<std::array<G4double, 3>> points;\n"
        "  points.push_back({0.0, 1.0, 2.0});\n"
        "}\n"
    )

    content = module_base._postprocess_generated_module_content(
        "src/OutputManager.cc",
        source,
    )

    assert "#include <array>" in content


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_system_units_include_for_unit_symbols(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "Hit.hh"\n'
        '#include "G4UnitsTable.hh"\n'
        "void Hit::Print() {\n"
        '  G4cout << G4BestUnit(fEdepMeV * MeV, "Energy") << G4BestUnit(fTime * s, "Time");\n'
        "}\n"
    )
    fake_gw = _FakeGateway({"src/Hit.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_units_include",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["src/Hit.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4SystemOfUnits.hh"' in content
    assert content.index('#include "G4SystemOfUnits.hh"') < content.index("void Hit::Print")


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_run_manager_include_for_runtime_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "SteppingAction.hh"\n'
        "void SteppingAction::UserSteppingAction(const G4Step*) {\n"
        "  auto* event = G4RunManager::GetRunManager()->GetCurrentEvent();\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/SteppingAction.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_run_manager_include",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/SteppingAction.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4RunManager.hh"' in content
    assert content.index('#include "G4RunManager.hh"') < content.index(
        "G4RunManager::GetRunManager()"
    )


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_particle_definition_include(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        "#pragma once\n"
        '#include "G4String.hh"\n'
        "class PrimaryGeneratorAction {\n"
        "  G4ParticleDefinition* ResolveParticle(const G4String& name) const;\n"
        "};\n"
    )
    fake_gw = _FakeGateway({"include/PrimaryGeneratorAction.hh": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "beam_physics",
        {
            "job_id": "job_particle_definition_include",
            "module_name": "beam_physics",
            "module_contract": {"output_files": ["include/PrimaryGeneratorAction.hh"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4ParticleDefinition.hh"' in content
    assert content.index('#include "G4ParticleDefinition.hh"') < content.index(
        "G4ParticleDefinition*"
    )


@pytest.mark.asyncio
async def test_agentic_module_agent_replaces_rotation_matrix_forward_declaration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        "#pragma once\n"
        '#include "G4ThreeVector.hh"\n'
        "class G4RotationMatrix;\n"
        "class PlacementManager {\n"
        "  G4RotationMatrix* MakeRotation();\n"
        "};\n"
    )
    fake_gw = _FakeGateway({"include/PlacementManager.hh": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_rotation_matrix_forward_decl",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["include/PlacementManager.hh"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "class G4RotationMatrix;" not in content
    assert '#include "G4RotationMatrix.hh"' in content
    assert content.index('#include "G4RotationMatrix.hh"') < content.index(
        "G4RotationMatrix*"
    )


@pytest.mark.asyncio
async def test_agentic_module_agent_normalizes_rotation_matrix_pointer_constness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    header = (
        "#pragma once\n"
        '#include "G4RotationMatrix.hh"\n'
        "class PlacementManager {\n"
        "  void Place(const G4RotationMatrix* rot);\n"
        "};\n"
    )
    source = (
        '#include "PlacementManager.hh"\n'
        "void PlacementManager::Place(const G4RotationMatrix* rot) {\n"
        "  auto* pv = new G4PVPlacement(rot, pos, logical, name, mother, false, 0, true);\n"
        "}\n"
    )
    fake_gw = _FakeGateway(
        {
            "include/PlacementManager.hh": header,
            "src/PlacementManager.cc": source,
        }
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_rotation_matrix_constness",
            "module_name": "simulation_core",
            "module_contract": {
                "output_files": ["include/PlacementManager.hh", "src/PlacementManager.cc"]
            },
        },
    )

    assert result.status == "generated"
    by_path = {file.path: file.new_content for file in result.generated_files}
    assert "const G4RotationMatrix* rot" not in by_path["include/PlacementManager.hh"]
    assert "const G4RotationMatrix* rot" not in by_path["src/PlacementManager.cc"]
    assert "G4RotationMatrix* rot" in by_path["include/PlacementManager.hh"]
    assert "G4RotationMatrix* rot" in by_path["src/PlacementManager.cc"]


@pytest.mark.asyncio
async def test_agentic_module_agent_normalizes_vis_attributes_member_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "DetectorConstruction.hh"\n'
        '#include "G4VisAttributes.hh"\n'
        '#include "G4Colour.hh"\n'
        "G4VPhysicalVolume* DetectorConstruction::Construct() {\n"
        "  G4VisAttributes worldVisAtt(G4Colour(1.0, 1.0, 1.0));\n"
        "  worldVisAtt->SetVisibility(false);\n"
        "  worldLogical->SetVisAttributes(worldVisAtt);\n"
        "  return worldPhys;\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/DetectorConstruction.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_vis_attributes_member_access",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["src/DetectorConstruction.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "worldVisAtt->SetVisibility" not in content
    assert "worldVisAtt.SetVisibility(false);" in content


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_colour_include_for_colour_literals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "DetectorConstruction.hh"\n'
        "G4VPhysicalVolume* DetectorConstruction::Construct() {\n"
        "  worldLV->SetVisAttributes(G4Colour(1.0, 1.0, 1.0, 0.05));\n"
        "  return worldPhys;\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/DetectorConstruction.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_colour_include",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["src/DetectorConstruction.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4Colour.hh"' in content
    assert content.index('#include "G4Colour.hh"') < content.index("G4Colour(")


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_vis_attributes_include_for_static_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "DetectorConstruction.hh"\n'
        "G4VPhysicalVolume* DetectorConstruction::Construct() {\n"
        "  worldLV->SetVisAttributes(G4VisAttributes::GetInvisible());\n"
        "  return worldPhys;\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/DetectorConstruction.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_vis_attributes_include",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["src/DetectorConstruction.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4VisAttributes.hh"' in content
    assert content.index('#include "G4VisAttributes.hh"') < content.index(
        "G4VisAttributes::GetInvisible"
    )


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_particle_table_include(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "PrimaryGeneratorAction.hh"\n'
        "G4ParticleDefinition* PrimaryGeneratorAction::ResolveParticle(const G4String& name) {\n"
        "  return G4ParticleTable::GetParticleTable()->FindParticle(name);\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/PrimaryGeneratorAction.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "beam_physics",
        {
            "job_id": "job_particle_table_include",
            "module_name": "beam_physics",
            "module_contract": {"output_files": ["src/PrimaryGeneratorAction.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4ParticleTable.hh"' in content
    assert content.index('#include "G4ParticleTable.hh"') < content.index("G4ParticleTable::")


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_material_include_for_material_pointer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        "#pragma once\n"
        '#include "globals.hh"\n'
        "class G4LogicalVolume;\n"
        "class PlacementManager {\n"
        "public:\n"
        "  void PlaceBox(G4Material* material, G4LogicalVolume* mother);\n"
        "};\n"
    )
    fake_gw = _FakeGateway({"include/PlacementManager.hh": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_material_include",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["include/PlacementManager.hh"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4Material.hh"' in content
    assert content.index('#include "G4Material.hh"') < content.index("G4Material*")


@pytest.mark.asyncio
async def test_agentic_module_agent_adds_solid_include_for_solid_methods(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "ScoringManager.hh"\n'
        '#include "G4LogicalVolume.hh"\n'
        "void ScoringManager::RegisterVoxelScoring(G4LogicalVolume* lv) {\n"
        "  auto* solid = lv->GetSolid();\n"
        "  solid->BoundingLimits(xmin, ymin, zmin, xmax, ymax, zmax);\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/ScoringManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_solid_include",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["src/ScoringManager.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert '#include "G4VSolid.hh"' in content
    assert content.index('#include "G4VSolid.hh"') < content.index("BoundingLimits")


@pytest.mark.asyncio
async def test_agentic_module_agent_normalizes_threadlocal_macro_and_include(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        "#pragma once\n"
        '#include "G4Allocator.hh"\n'
        "class Hit;\n"
        "extern G4THREADLOCAL G4Allocator<Hit>* HitAllocator;\n"
    )
    fake_gw = _FakeGateway({"include/Hit.hh": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "simulation_core",
        {
            "job_id": "job_threadlocal_include",
            "module_name": "simulation_core",
            "module_contract": {"output_files": ["include/Hit.hh"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "G4THREADLOCAL" not in content
    assert "G4ThreadLocal G4Allocator<Hit>* HitAllocator" in content
    assert '#include "tls.hh"' in content
    assert content.index('#include "tls.hh"') < content.index("G4ThreadLocal")


@pytest.mark.asyncio
async def test_agentic_module_agent_removes_undeclared_output_manager_summary_overload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        '#include "OutputManager.hh"\n'
        "void OutputManager::WriteAll(G4int eventsProcessed) {\n"
        "  WriteSummaryJson(eventsProcessed);\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  // Overload not needed; use the parameterised version\n"
        "}\n"
        "void OutputManager::WriteSummaryJson(G4int eventsProcessed)\n"
        "{\n"
        "  ofs << \"  \\\"events_requested\\\": \" << eventsProcessed << \",\\n\";\n"
        "}\n"
    )
    fake_gw = _FakeGateway({"src/OutputManager.cc": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_output_manager_summary_overload",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["src/OutputManager.cc"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "void OutputManager::WriteSummaryJson()\n" not in content
    assert "void OutputManager::WriteSummaryJson(G4int eventsProcessed)" in content


@pytest.mark.asyncio
async def test_agentic_module_agent_removes_unsupported_set_cut_macros(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    source = (
        "/control/verbose 1\n"
        "/run/setCutForGamma    100 um\n"
        "/run/setCutForElectron 100 um\n"
        "/run/initialize\n"
        "/run/beamOn 20\n"
    )
    fake_gw = _FakeGateway({"macros/run.mac": source})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    result = await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_macro_cut",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["macros/run.mac"]},
        },
    )

    assert result.status == "generated"
    content = result.generated_files[0].new_content
    assert "/run/setCutForGamma" not in content
    assert "/run/setCutForElectron" not in content
    assert "/run/setCut 0.1 mm" in content


@pytest.mark.asyncio
async def test_agentic_module_agent_flags_missing_owned_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the model never writes an owned file, the result records the error."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({})  # writes nothing
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway", lambda: fake_gw
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_missing",
        "module_name": "beam_physics",
        "module_contract": {"output_files": ["src/PrimaryGeneratorAction.cc"]},
    }
    result = await run_module_agent("beam_physics", module_context)
    assert result.status == "failed"
    assert any("owned file" in e for e in result.errors)


@pytest.mark.asyncio
async def test_agentic_module_agent_fails_when_only_some_owned_files_are_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Partial module output must not be marked generated and released downstream."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({"main.cc": "int main(){return 0;}\n"})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_partial",
        "module_name": "runtime_app",
        "module_contract": {"output_files": ["main.cc", "macros/run.mac"]},
    }
    result = await run_module_agent("runtime_app", module_context)

    assert result.status == "failed"
    assert {file.path for file in result.generated_files} == {"main.cc"}
    assert result.errors == [
        "module agent owned file not modified by current module agent: macros/run.mac"
    ]


@pytest.mark.asyncio
async def test_runtime_app_agent_templates_macros_without_second_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime app should not spend a model call on deterministic Geant4 macros."""
    from agent_core.g4_codegen.module_agents import runtime_app_agent
    from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

    calls: list[list[str]] = []

    async def fake_run_module_agent(
        *,
        module_name: str,
        module_context: dict[str, Any],
        system_prompt: str = "",
    ) -> ModuleAgentResult:
        del system_prompt
        assert module_name == "runtime_app"
        output_files = list(module_context["module_contract"]["output_files"])
        calls.append(output_files)
        return ModuleAgentResult(
            module_name="runtime_app",
            status="generated",
            generated_files=[
                GeneratedModuleFile(
                    path=path,
                    new_content=(
                        "#pragma once\n"
                        "class DetectorConstruction;\n"
                        "class OutputManager;\n"
                        "class ActionInitialization {\n"
                        "public:\n"
                        "  ActionInitialization(DetectorConstruction*, OutputManager*);\n"
                        "};\n"
                        if path == "include/ActionInitialization.hh"
                        else f"// {path}\n"
                    ),
                    generated_by="runtime_app_module_agent",
                    module_name="runtime_app",
                    rationale="test",
                )
                for path in output_files
            ],
        )

    monkeypatch.setattr(runtime_app_agent, "run_module_agent", fake_run_module_agent)

    result = await runtime_app_agent.run_runtime_app_agent(
        {
            "job_id": "job_runtime_groups",
            "g4_model_ir_subset": {"sources": [{"events": 37}]},
            "module_contract": {
                "output_files": [
                    "include/OutputManager.hh",
                    "src/OutputManager.cc",
                    "include/ActionInitialization.hh",
                    "src/ActionInitialization.cc",
                    "include/RunAction.hh",
                    "src/RunAction.cc",
                    "include/EventAction.hh",
                    "src/EventAction.cc",
                    "include/SteppingAction.hh",
                    "src/SteppingAction.cc",
                    "main.cc",
                    "CMakeLists.txt",
                    "macros/run.mac",
                    "macros/init.mac",
                    "macros/init_vis.mac",
                    "macros/vis.mac",
                    "macros/gui.mac",
                ]
            },
        }
    )

    assert len(calls) == 1
    assert calls[0] == [
        "include/OutputManager.hh",
        "src/OutputManager.cc",
        "include/ActionInitialization.hh",
        "src/ActionInitialization.cc",
        "include/RunAction.hh",
        "src/RunAction.cc",
        "include/EventAction.hh",
        "src/EventAction.cc",
        "include/SteppingAction.hh",
        "src/SteppingAction.cc",
    ]
    assert result.status == "generated"
    assert len(result.generated_files) == 17

    by_path = {file.path: file for file in result.generated_files}
    assert by_path["main.cc"].generated_by == "runtime_app_cpp_template"
    assert by_path["CMakeLists.txt"].generated_by == "runtime_app_cpp_template"
    assert "G4UIExecutive" in by_path["main.cc"].new_content
    assert "std::filesystem::create_directories" in by_path["main.cc"].new_content
    assert '#include "G4VModularPhysicsList.hh"' in by_path["main.cc"].new_content
    assert '#include "G4VUserPhysicsList.hh"' in by_path["main.cc"].new_content
    assert '#include "OutputManager.hh"' in by_path["main.cc"].new_content
    assert "auto* outputManager = new OutputManager();" in by_path["main.cc"].new_content
    assert (
        "new ActionInitialization(detector, outputManager)"
        in by_path["main.cc"].new_content
    )
    assert "file(GLOB sources" in by_path["CMakeLists.txt"].new_content
    assert by_path["macros/run.mac"].generated_by == "runtime_app_macro_template"
    assert "/run/beamOn 37" in by_path["macros/run.mac"].new_content
    assert "/run/setCut 0.1 mm" in by_path["macros/run.mac"].new_content
    assert "/run/setCutForGamma" not in by_path["macros/run.mac"].new_content
    assert "/vis/" not in by_path["macros/run.mac"].new_content
    assert "/control/execute macros/vis.mac" in by_path["macros/init_vis.mac"].new_content
    assert "/run/beamOn 100" in by_path["macros/vis.mac"].new_content


@pytest.mark.asyncio
async def test_runtime_app_agent_repairs_unwired_stepping_output_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime postprocessing should harden the repeated missing edep/track flow."""
    from agent_core.g4_codegen.module_agents import runtime_app_agent
    from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

    def content_for(path: str) -> str:
        if path == "include/OutputManager.hh":
            return (
                "#pragma once\n"
                "struct TrackPoint;\n"
                "struct EnergyDepositPoint;\n"
                "class OutputManager {\n"
                "public:\n"
                "  void AddTrackPoint(const TrackPoint& tp);\n"
                "  void AddEnergyDepositPoint(const EnergyDepositPoint& edp);\n"
                "};\n"
            )
        if path == "include/SteppingAction.hh":
            return (
                "#pragma once\n"
                '#include "G4UserSteppingAction.hh"\n'
                "class G4Step;\n"
                "class EventAction;\n"
                "class ScoringManager;\n"
                "class SteppingAction : public G4UserSteppingAction {\n"
                "public:\n"
                "  SteppingAction(EventAction* eventAction, ScoringManager* scoringMgr);\n"
                "  void UserSteppingAction(const G4Step* step) override;\n"
                "private:\n"
                "  EventAction* fEventAction;\n"
                "  ScoringManager* fScoringManager;\n"
                "};\n"
            )
        if path == "src/SteppingAction.cc":
            return (
                '#include "SteppingAction.hh"\n'
                '#include "EventAction.hh"\n'
                '#include "ScoringManager.hh"\n'
                '#include "G4Step.hh"\n'
                '#include "G4StepPoint.hh"\n'
                '#include "G4Track.hh"\n'
                '#include "G4ParticleDefinition.hh"\n'
                '#include "G4ThreeVector.hh"\n'
                '#include "G4SystemOfUnits.hh"\n'
                '#include "G4RunManager.hh"\n'
                '#include "G4Event.hh"\n'
                "SteppingAction::SteppingAction(EventAction* eventAction, ScoringManager* scoringMgr)\n"
                "    : fEventAction(eventAction), fScoringManager(scoringMgr) {}\n"
                "void SteppingAction::UserSteppingAction(const G4Step* step) {\n"
                "  G4double edep = step->GetTotalEnergyDeposit();\n"
                "  if (edep <= 0.0) return;\n"
                "  const G4Track* track = step->GetTrack();\n"
                "  G4StepPoint* preStep = step->GetPreStepPoint();\n"
                "  G4ThreeVector pos = preStep->GetPosition();\n"
                '  G4String volumeName = "unknown";\n'
                "  if (preStep->GetPhysicalVolume()) volumeName = preStep->GetPhysicalVolume()->GetName();\n"
                '  G4String componentId = "silicon_detector";\n'
                "  if (fScoringManager) fScoringManager->RecordEnergyDeposit(componentId, edep / MeV, pos);\n"
                "  G4int eventID = -1;\n"
                "  const G4Event* currentEvent = G4RunManager::GetRunManager()->GetCurrentEvent();\n"
                "  if (currentEvent) eventID = currentEvent->GetEventID();\n"
                "  G4int trackID = track->GetTrackID();\n"
                "  G4String particleName = track->GetDefinition()->GetParticleName();\n"
                "  G4double kineticEnergy = track->GetKineticEnergy() / MeV;\n"
                "}\n"
            )
        if path == "src/ActionInitialization.cc":
            return (
                '#include "ActionInitialization.hh"\n'
                '#include "SteppingAction.hh"\n'
                "void ActionInitialization::Build() const {\n"
                "  auto* eventAction = new EventAction(fOutputManager, scoringMgr);\n"
                "  SetUserAction(new SteppingAction(eventAction, scoringMgr));\n"
                "}\n"
            )
        return f"// {path}\n"

    async def fake_run_module_agent(
        *,
        module_name: str,
        module_context: dict[str, Any],
        system_prompt: str = "",
    ) -> ModuleAgentResult:
        del system_prompt
        assert module_name == "runtime_app"
        return ModuleAgentResult(
            module_name="runtime_app",
            status="generated",
            generated_files=[
                GeneratedModuleFile(
                    path=path,
                    new_content=content_for(path),
                    generated_by="runtime_app_module_agent",
                    module_name="runtime_app",
                    rationale="test",
                )
                for path in module_context["module_contract"]["output_files"]
            ],
        )

    monkeypatch.setattr(runtime_app_agent, "run_module_agent", fake_run_module_agent)

    result = await runtime_app_agent.run_runtime_app_agent(
        {
            "job_id": "job_runtime_unwired_flow",
            "g4_model_ir_subset": {"sources": [{"events": 5}]},
            "module_contract": {
                "output_files": [
                    *runtime_app_agent.RUNTIME_APP_FILE_GROUPS[0][1],
                    "main.cc",
                    "CMakeLists.txt",
                    *runtime_app_agent.RUNTIME_APP_FILE_GROUPS[1][1],
                ]
            },
        }
    )

    by_path = {file.path: file.new_content for file in result.generated_files}
    assert result.status == "generated"
    assert (
        "SteppingAction(EventAction* eventAction, ScoringManager* scoringMgr, "
        "OutputManager* outputMgr)"
    ) in by_path["include/SteppingAction.hh"]
    assert "OutputManager*  fOutputManager;" in by_path["include/SteppingAction.hh"]
    assert "fOutputManager(outputMgr)" in by_path["src/SteppingAction.cc"]
    assert "fOutputManager->AddTrackPoint(tp);" in by_path["src/SteppingAction.cc"]
    assert "fOutputManager->AddEnergyDepositPoint(edp);" in by_path[
        "src/SteppingAction.cc"
    ]
    assert "new SteppingAction(eventAction, scoringMgr, fOutputManager)" in by_path[
        "src/ActionInitialization.cc"
    ]
    issues = module_base._find_generated_content_issues(result.generated_files)
    assert not any("runtime OutputManager data flow not wired" in item for item in issues)


@pytest.mark.asyncio
async def test_runtime_app_agent_adds_ir_geometry_fallback_to_geometry_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_core.g4_codegen.module_agents import runtime_app_agent
    from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

    def content_for(path: str) -> str:
        if path == "include/OutputManager.hh":
            return (
                "#pragma once\n"
                "class OutputManager {\n"
                "public:\n"
                "  struct GeometryComponent {\n"
                "    int id; const char* name; const char* shape; const char* material;\n"
                "    double sizeX_mm; double sizeY_mm; double sizeZ_mm;\n"
                "    double posX_mm; double posY_mm; double posZ_mm;\n"
                "    double rotX_deg; double rotY_deg; double rotZ_deg; double opacity;\n"
                "  };\n"
                "  void WriteGeometryViewJson();\n"
                "private:\n"
                "  std::vector<GeometryComponent> fGeometryComponents;\n"
                "};\n"
            )
        if path == "src/OutputManager.cc":
            return (
                '#include "OutputManager.hh"\n'
                "#include <fstream>\n"
                "void OutputManager::WriteGeometryViewJson()\n"
                "{\n"
                "  std::ofstream ofs(\"geometry_view.json\");\n"
                "  ofs << \"{\\n  \\\"components\\\": [\\n\";\n"
                "  for (size_t i = 0; i < fGeometryComponents.size(); ++i) {\n"
                "    const auto& c = fGeometryComponents[i];\n"
                "    ofs << \"    {\\\"id\\\": \\\"\" << c.name << \"\\\"}\";\n"
                "  }\n"
                "  ofs << \"  ]\\n}\\n\";\n"
                "}\n"
            )
        return f"// {path}\n"

    async def fake_run_module_agent(
        *,
        module_name: str,
        module_context: dict[str, Any],
        system_prompt: str = "",
    ) -> ModuleAgentResult:
        del system_prompt
        assert module_name == "runtime_app"
        return ModuleAgentResult(
            module_name="runtime_app",
            status="generated",
            generated_files=[
                GeneratedModuleFile(
                    path=path,
                    new_content=content_for(path),
                    generated_by="runtime_app_module_agent",
                    module_name="runtime_app",
                    rationale="test",
                )
                for path in module_context["module_contract"]["output_files"]
            ],
        )

    monkeypatch.setattr(runtime_app_agent, "run_module_agent", fake_run_module_agent)

    result = await runtime_app_agent.run_runtime_app_agent(
        {
            "job_id": "job_runtime_geometry_fallback",
            "g4_model_ir_subset": {
                "global_units": {"length": "mm"},
                "components": [
                    {
                        "component_id": "world",
                        "display_name": "World",
                        "component_type": "world",
                        "geometry_type": "box",
                        "dimensions": {"dx": 200.0, "dy": 200.0, "dz": 200.0},
                        "material_id": "G4_AIR",
                        "placement": {"position": [0.0, 0.0, 0.0]},
                    },
                    {
                        "component_id": "silicon_detector",
                        "display_name": "Silicon detector",
                        "component_type": "substrate",
                        "geometry_type": "box",
                        "dimensions": {"dx": 20.0, "dy": 20.0, "dz": 0.5},
                        "material_id": "G4_Si",
                        "placement": {"position": [0.0, 0.0, 0.0]},
                        "roles": ["edep_region"],
                    },
                ],
            },
            "module_contract": {
                "output_files": [
                    *runtime_app_agent.RUNTIME_APP_FILE_GROUPS[0][1],
                    "main.cc",
                    "CMakeLists.txt",
                    *runtime_app_agent.RUNTIME_APP_FILE_GROUPS[1][1],
                ]
            },
        }
    )

    by_path = {file.path: file.new_content for file in result.generated_files}
    output_manager = by_path["src/OutputManager.cc"]
    assert "_RadAgentIrGeometryComponents" in output_manager
    assert 'R"RADGEOM(' in output_manager
    assert 'R"RADAGENT_GEOMETRY(' not in output_manager
    assert '"silicon_detector"' in output_manager
    assert '"size_mm": [20' in output_manager
    assert "fGeometryComponents.empty()" in output_manager


@pytest.mark.asyncio
async def test_runtime_app_agent_replaces_geometry_writer_when_no_geometry_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_core.g4_codegen.module_agents import runtime_app_agent
    from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

    def content_for(path: str) -> str:
        if path == "include/OutputManager.hh":
            return (
                "#pragma once\n"
                "class OutputManager {\n"
                "public:\n"
                "  void WriteGeometryViewJson();\n"
                "private:\n"
                "  G4String fOutputDir;\n"
                "};\n"
            )
        if path == "src/OutputManager.cc":
            return (
                '#include "OutputManager.hh"\n'
                "#include <fstream>\n"
                "void OutputManager::WriteGeometryViewJson()\n"
                "{\n"
                "  std::ofstream ofs(\"geometry_view.json\");\n"
                "  ofs << \"{\\n  \\\"components\\\": []\\n}\\n\";\n"
                "}\n"
            )
        return f"// {path}\n"

    async def fake_run_module_agent(
        *,
        module_name: str,
        module_context: dict[str, Any],
        system_prompt: str = "",
    ) -> ModuleAgentResult:
        del system_prompt
        assert module_name == "runtime_app"
        return ModuleAgentResult(
            module_name="runtime_app",
            status="generated",
            generated_files=[
                GeneratedModuleFile(
                    path=path,
                    new_content=content_for(path),
                    generated_by="runtime_app_module_agent",
                    module_name="runtime_app",
                    rationale="test",
                )
                for path in module_context["module_contract"]["output_files"]
            ],
        )

    monkeypatch.setattr(runtime_app_agent, "run_module_agent", fake_run_module_agent)

    result = await runtime_app_agent.run_runtime_app_agent(
        {
            "job_id": "job_runtime_geometry_writer_replacement",
            "g4_model_ir_subset": {
                "global_units": {"length": "mm"},
                "components": [
                    {
                        "component_id": "silicon_detector",
                        "display_name": "Silicon detector",
                        "component_type": "substrate",
                        "geometry_type": "box",
                        "dimensions": {"dx": 20.0, "dy": 20.0, "dz": 0.5},
                        "material_id": "G4_Si",
                        "placement": {"position": [0.0, 0.0, 0.0]},
                    },
                ],
            },
            "module_contract": {
                "output_files": [
                    *runtime_app_agent.RUNTIME_APP_FILE_GROUPS[0][1],
                    "main.cc",
                    "CMakeLists.txt",
                    *runtime_app_agent.RUNTIME_APP_FILE_GROUPS[1][1],
                ]
            },
        }
    )

    output_manager = {file.path: file.new_content for file in result.generated_files}[
        "src/OutputManager.cc"
    ]
    assert "_RadAgentIrGeometryComponents" in output_manager
    assert '"silicon_detector"' in output_manager
    assert "fGeometryComponents" not in output_manager
    assert 'std::string path = std::string(fOutputDir) + "/geometry_view.json";' in output_manager
    assert 'ofs << "{\\n  \\"components\\": [\\n";' in output_manager


def test_runtime_geometry_view_hardening_replaces_existing_helper_without_geometry_member() -> None:
    files = {
        "include/OutputManager.hh": GeneratedModuleFile(
            path="include/OutputManager.hh",
            new_content="#pragma once\nclass OutputManager { void WriteGeometryViewJson(); };\n",
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
        "src/OutputManager.cc": GeneratedModuleFile(
            path="src/OutputManager.cc",
            new_content=(
                '#include "OutputManager.hh"\n'
                "#include <fstream>\n"
                "namespace {\n"
                "const char* _RadAgentIrGeometryComponents()\n"
                "{\n"
                "    return R\"RADGEOM(    {\"id\": \"silicon_detector\", "
                "\"name\": \"Silicon detector\", \"shape\": \"box\", "
                "\"material\": \"G4_Si\", \"role\": \"\", "
                "\"size_mm\": [20.0, 20.0, 0.5], "
                "\"position_mm\": [0.0, 0.0, 0.0], "
                "\"rotation_deg\": [0.0, 0.0, 0.0], \"opacity\": 0.44}\n"
                ")RADGEOM\";\n"
                "}\n"
                "}\n"
                "void OutputManager::WriteGeometryViewJson()\n"
                "{\n"
                "  std::ofstream ofs(\"geometry_view.json\");\n"
                "  if (fGeometryComponents.empty()) {\n"
                "    ofs << _RadAgentIrGeometryComponents();\n"
                "  }\n"
                "}\n"
            ),
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
    }

    runtime_app_agent._harden_runtime_geometry_view(
        files,
        {
            "g4_model_ir_subset": {
                "global_units": {"length": "mm"},
                "components": [
                    {
                        "component_id": "silicon_detector",
                        "display_name": "Silicon detector",
                        "component_type": "substrate",
                        "geometry_type": "box",
                        "dimensions": {"dx": 20.0, "dy": 20.0, "dz": 0.5},
                        "material_id": "G4_Si",
                        "placement": {"position": [0.0, 0.0, 0.0]},
                    },
                ],
            }
        },
    )

    content = files["src/OutputManager.cc"].new_content
    assert "fGeometryComponents" not in content
    assert "_RadAgentIrGeometryComponents" in content
    assert 'ofs << "{\\n  \\"components\\": [\\n";' in content


def test_runtime_geometry_view_hardening_replaces_inline_writer_from_write_all() -> None:
    files = {
        "include/OutputManager.hh": GeneratedModuleFile(
            path="include/OutputManager.hh",
            new_content="#pragma once\nclass OutputManager { void WriteAll() const; };\n",
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
        "src/OutputManager.cc": GeneratedModuleFile(
            path="src/OutputManager.cc",
            new_content=(
                '#include "OutputManager.hh"\n'
                "#include <fstream>\n"
                "void OutputManager::WriteAll() const\n"
                "{\n"
                "  {\n"
                "    std::ofstream out(pathJoin(fOutputDirectory, \"g4_summary.json\"));\n"
                "    out << \"{}\\n\";\n"
                "  }\n"
                "  {\n"
                "    std::ofstream out(pathJoin(fOutputDirectory, \"geometry_view.json\"));\n"
                "    out << \"{\\n  \\\"components\\\": [\\n\";\n"
                "    out << \"    {\\\"id\\\": \\\"hpge_crystal\\\", \\\"shape\\\": \\\"box\\\"}\";\n"
                "    out << \"\\n  ]\\n}\\n\";\n"
                "  }\n"
                "}\n"
            ),
            generated_by="test",
            module_name="runtime_app",
            rationale="test",
        ),
    }

    runtime_app_agent._harden_runtime_geometry_view(
        files,
        {
            "g4_model_ir_subset": {
                "global_units": {"length": "um"},
                "components": [
                    {
                        "component_id": "hpge_crystal",
                        "display_name": "HPGe Coaxial Crystal",
                        "component_type": "volume",
                        "geometry_type": "cylinder",
                        "dimensions": {"r": 30000.0, "dz": 50000.0},
                        "material_id": "G4_Ge",
                        "placement": {"position": [0.0, 0.0, 0.0]},
                    }
                ],
            }
        },
    )

    content = files["src/OutputManager.cc"].new_content
    assert "_RadAgentIrGeometryComponents" in content
    assert '"hpge_crystal"' in content
    assert '"shape": "cylinder"' in content
    assert '"size_mm": [60.0, 60.0, 50.0]' in content
    assert '\\"shape\\": \\"box\\"' not in content
