from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from agent_core.g4_codegen.physics_quality_reviewer import run_physics_quality_reviewer
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


@pytest.mark.asyncio
async def test_physics_quality_reviewer_uses_lite_flash_tier(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []

    class Gateway:
        profiles = {ModelTier.LITE: SimpleNamespace(provider=ModelProvider.OPENAI_COMPATIBLE)}

        async def call(self, **kwargs: Any) -> ModelCallResult:
            calls.append(kwargs)
            payload = {
                "status": "pass",
                "overall_score": 95,
                "physics_model_score": 95,
                "source_fidelity_score": 95,
                "geometry_fidelity_score": 95,
                "transport_precision_score": 90,
                "output_validity_score": 95,
                "findings": [],
                "required_fixes": [],
                "reviewer_notes": "parameter consistency reviewed",
            }
            return ModelCallResult(
                task=kwargs["task"],
                tier=kwargs["tier"],
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="flash-test",
                content=json.dumps(payload),
                parsed_json=payload,
            )

    monkeypatch.setattr(
        "agent_core.g4_codegen.physics_quality_reviewer.get_model_gateway",
        lambda: Gateway(),
    )

    review = await run_physics_quality_reviewer(
        proposed_patch={"changed_files": []},
        g4_model_ir={"sources": [], "physics": {}},
        module_contracts={},
        module_contexts={},
        global_integration_report={"status": "passed"},
        job_id="physics_review_lite",
    )

    assert review["status"] == "pass"
    assert calls
    assert calls[0]["task"] == ModelTask.CONTEXT_SUMMARY
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[0]["metadata"]["module_name"] == "physics_quality_reviewer"
    assert calls[0]["metadata"]["enable_thinking"] is False
    assert review["summary_model"]["tier"] == str(ModelTier.LITE)
    assert review["summary_model"]["model_name"] == "flash-test"


@pytest.mark.asyncio
async def test_physics_quality_reviewer_prompt_prioritizes_latest_runtime_pass(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []

    class Gateway:
        profiles = {ModelTier.LITE: SimpleNamespace(provider=ModelProvider.OPENAI_COMPATIBLE)}

        async def call(self, **kwargs: Any) -> ModelCallResult:
            calls.append(kwargs)
            payload = {
                "status": "pass",
                "overall_score": 95,
                "physics_model_score": 95,
                "source_fidelity_score": 95,
                "geometry_fidelity_score": 95,
                "transport_precision_score": 90,
                "output_validity_score": 95,
                "findings": [],
                "required_fixes": [],
                "reviewer_notes": "latest runtime facts reviewed",
            }
            return ModelCallResult(
                task=kwargs["task"],
                tier=kwargs["tier"],
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="flash-test",
                content=json.dumps(payload),
                parsed_json=payload,
            )

    monkeypatch.setattr(
        "agent_core.g4_codegen.physics_quality_reviewer.get_model_gateway",
        lambda: Gateway(),
    )

    await run_physics_quality_reviewer(
        proposed_patch={"changed_files": []},
        g4_model_ir={"sources": [{"events": 5}], "physics": {}},
        module_contracts={},
        module_contexts={},
        global_integration_report={
            "status": "passed",
            "runtime_gate_attempts": [
                {
                    "attempt": 1,
                    "status": "fail",
                    "errors": ["old compile failed"],
                    "missing_outputs": ["g4_summary.json"],
                },
                {
                    "attempt": 2,
                    "status": "pass",
                    "expected_events": 5,
                    "missing_outputs": [],
                    "errors": [],
                    "output_quality": {
                        "status": "pass",
                        "errors": [],
                        "metrics": {
                            "events_requested": 5,
                            "expected_events": 5,
                            "event_table_rows": 5,
                            "event_table_nonzero_rows": 5,
                        },
                    },
                },
            ],
        },
        job_id="physics_review_runtime_priority",
    )

    context = json.loads(calls[0]["user_prompt"])
    summary = context["runtime_verification_summary"]
    assert summary["latest_attempt"] == 2
    assert summary["latest_runtime_gate_status"] == "pass"
    assert summary["latest_runtime_gate_passed"] is True
    assert summary["missing_outputs"] == []
    assert summary["output_quality_status"] == "pass"
    assert summary["event_table_rows"] == 5
    assert summary["prior_failed_attempt_count"] == 1
    assert "latest passing runtime gate" in context["review_instruction"]


@pytest.mark.asyncio
async def test_physics_quality_reviewer_builds_bounded_parseable_evidence_prompt(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []

    class Gateway:
        profiles = {ModelTier.LITE: SimpleNamespace(provider=ModelProvider.OPENAI_COMPATIBLE)}

        async def call(self, **kwargs: Any) -> ModelCallResult:
            calls.append(kwargs)
            payload = {
                "status": "pass",
                "overall_score": 91,
                "physics_model_score": 91,
                "source_fidelity_score": 92,
                "geometry_fidelity_score": 90,
                "transport_precision_score": 88,
                "output_validity_score": 94,
                "findings": [],
                "required_fixes": [],
                "reviewer_notes": "bounded evidence reviewed",
            }
            return ModelCallResult(
                task=kwargs["task"],
                tier=kwargs["tier"],
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="flash-test",
                content=json.dumps(payload),
                parsed_json=payload,
            )

    monkeypatch.setattr(
        "agent_core.g4_codegen.physics_quality_reviewer.get_model_gateway",
        lambda: Gateway(),
    )

    large_comment = "\n".join(f"// filler line {idx}" for idx in range(900))
    proposed_patch = {
        "changed_files": [
            {
                "path": "src/PrimaryGeneratorAction.cc",
                "module_name": "beam_physics",
                "generated_by": "beam_physics_module_agent",
                "new_content": (
                    "#include \"PrimaryGeneratorAction.hh\"\n"
                    "void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event) {\n"
                    "  fParticleGun->SetParticleDefinition("
                    "G4ParticleTable::GetParticleTable()->FindParticle(\"proton\"));\n"
                    "  fParticleGun->SetParticleEnergy(10.0 * MeV);\n"
                    "  fParticleGun->SetParticlePosition(G4ThreeVector(0,0,-80*mm));\n"
                    "  fParticleGun->SetParticleMomentumDirection(G4ThreeVector(0,0,1));\n"
                    "  fParticleGun->GeneratePrimaryVertex(event);\n"
                    "}\n"
                    + large_comment
                ),
            },
            {
                "path": "src/OutputManager.cc",
                "module_name": "runtime_app",
                "generated_by": "runtime_app_module_agent",
                "new_content": (
                    "void OutputManager::WriteEventTableCSV() {\n"
                    "  out << \"EventID,edep_MeV,dose_Gy\\n\";\n"
                    "}\n"
                    "void OutputManager::WriteGeometryViewJson() {}\n"
                    "void OutputManager::WriteParticleTracksJson() {}\n"
                    "void OutputManager::WriteEnergyDepositsJson() {}\n"
                    "void OutputManager::AddEnergyDepositPoint("
                    "G4int eventID, G4int trackID, const G4String& volume, "
                    "const G4ThreeVector& position, G4double edepMeV) {}\n"
                    + large_comment
                ),
            },
            {
                "path": "src/DetectorConstruction.cc",
                "module_name": "simulation_core",
                "generated_by": "simulation_core_module_agent",
                "new_content": (
                    "auto silicon = nist->FindOrBuildMaterial(\"G4_Si\");\n"
                    "new G4Box(\"silicon_detector\", 10*mm, 10*mm, 0.25*mm);\n"
                    "new G4PVPlacement(nullptr, G4ThreeVector(0,0,0), "
                    "logicSilicon, \"silicon_detector\", logicWorld, false, 0, true);\n"
                    "auto aluminum = nist->FindOrBuildMaterial(\"G4_Al\");\n"
                    + large_comment
                ),
            },
        ]
    }
    module_contexts = {
        name: {
            "module_name": name,
            "g4_model_ir_subset": {
                "components": [{"component_id": f"{name}_{idx}"} for idx in range(200)],
                "sources": [{"source_id": "proton_source", "events": 1000}],
                "scoring": [{"quantities": ["edep_MeV", "dose_Gy"]}],
            },
            "geant4_api_rules": [f"rule {idx}" for idx in range(80)],
            "geant4_example_lookup_results": [{"content": large_comment}],
        }
        for name in ("simulation_core", "beam_physics", "runtime_app")
    }
    global_integration_report = {
        "status": "passed",
        "runtime_gate_attempts": [
            {
                "attempt": 0,
                "status": "fail",
                "errors": [f"compile error {idx}" for idx in range(120)],
            },
            {
                "attempt": 1,
                "status": "pass",
                "expected_events": 1000,
                "missing_outputs": [],
                "errors": [],
                "output_quality": {
                    "status": "pass",
                    "errors": [],
                    "metrics": {
                        "events_requested": 1000,
                        "expected_events": 1000,
                        "event_table_rows": 1000,
                        "event_table_nonzero_rows": 100,
                        "edep_3d_nonzero_rows": 7,
                        "dose_3d_nonzero_rows": 7,
                    },
                },
            },
        ],
        "debug_payload": large_comment,
    }

    await run_physics_quality_reviewer(
        proposed_patch=proposed_patch,
        g4_model_ir={
            "schema_version": "g4_model_ir_v1",
            "target_system": "Layered silicon detector with shield and proton source",
            "materials": [{"material_id": "G4_Si"}, {"material_id": "G4_Al"}],
            "components": [
                {"component_id": "silicon_detector", "dimensions": {"dz": 0.5}},
                {"component_id": "aluminum_shield", "placement": {"position": [0, 0, -10]}},
            ],
            "sources": [
                {
                    "source_id": "proton_source",
                    "particle_type": "proton",
                    "energy": {"value": 10.0, "unit": "MeV"},
                    "beam": {"position": [0, 0, -80], "direction": [0, 0, 1]},
                    "events": 1000,
                }
            ],
            "physics": {"physics_list": "FTFP_BERT"},
            "scoring": [{"quantities": ["edep_MeV", "dose_Gy"]}],
            "debug_payload": large_comment,
        },
        module_contracts={},
        module_contexts=module_contexts,
        global_integration_report=global_integration_report,
        job_id="physics_review_bounded_prompt",
    )

    assert calls
    prompt = calls[0]["user_prompt"]
    assert len(prompt) <= 45_000
    assert "[truncated review context]" not in prompt
    context = json.loads(prompt)
    assert context["runtime_verification_summary"]["latest_runtime_gate_passed"] is True
    assert context["runtime_verification_summary"]["event_table_rows"] == 1000
    assert context["g4_model_ir"]["sources"][0]["particle_type"] == "proton"
    prompt_text = json.dumps(context, ensure_ascii=False)
    assert "SetParticleEnergy(10.0 * MeV)" in prompt_text
    assert "WriteEnergyDepositsJson" in prompt_text
    assert "debug_payload" not in prompt_text
    assert "review_instruction" in context


def test_physics_quality_reviewer_prompt_audits_composite_source_parameters() -> None:
    from agent_core.g4_codegen.physics_quality_reviewer import PHYSICS_REVIEW_SYSTEM_PROMPT

    prompt = PHYSICS_REVIEW_SYSTEM_PROMPT.lower()
    assert "all g4modelir sources" in prompt
    assert "spectrum" in prompt
    assert "angular_distribution" in prompt
    assert "relative_weight" in prompt


def test_physics_review_treats_unconfirmed_model_parameters_as_advisory() -> None:
    from agent_core.g4_codegen.physics_quality_reviewer import _normalize_review

    review = _normalize_review(
        {
            "status": "needs_user_input",
            "routing_recommendation": "request_user_input",
            "overall_score": 65,
            "needs_user_input": [
                {
                    "target": "components.polyethylene_layer.dimensions",
                    "message": (
                        "requires_confirmation=true and confirmed_by_user=false; "
                        "exact shielding layer thickness is not specified."
                    ),
                }
            ],
        }
    )

    assert review["status"] == "pass"
    assert review["routing_recommendation"] == "accept"
    assert review["required_fixes"] == []
    assert review["needs_user_input"] == []
    assert review["advisory_findings"]


def test_physics_review_keeps_overlap_as_code_repairable() -> None:
    from agent_core.g4_codegen.physics_quality_reviewer import _normalize_review

    review = _normalize_review(
        {
            "status": "revise",
            "required_fixes": [
                {
                    "target": "src/DetectorConstruction.cc",
                    "message": (
                        "Two sibling G4PVPlacement volumes overlap because z centers "
                        "use full thickness instead of half-length offsets; fix "
                        "placement math and keep CheckOverlaps enabled."
                    ),
                }
            ],
        }
    )

    assert review["status"] == "revise"
    assert review["routing_recommendation"] == "repair_code"
    assert review["required_fixes"]
    assert review["needs_user_input"] == []


def test_project_file_review_prioritizes_behavior_sources_over_headers() -> None:
    from agent_core.g4_codegen.physics_quality_reviewer import _project_files_for_review

    filler = "\n".join(f"// filler {idx}" for idx in range(500))
    proposed_patch = {
        "changed_files": [
            {
                "path": "include/PrimaryGeneratorAction.hh",
                "new_content": "class PrimaryGeneratorAction {};\n" + filler,
            },
            {
                "path": "include/OutputManager.hh",
                "new_content": (
                    "class OutputManager { void WriteEnergyDepositsJson(); };\n"
                    + filler
                ),
            },
            {
                "path": "src/PrimaryGeneratorAction.cc",
                "new_content": (
                    "void PrimaryGeneratorAction::GeneratePrimaries(G4Event*) {\n"
                    "  fParticleGun->SetParticleEnergy(10.0 * MeV);\n"
                    "}\n"
                    + filler
                ),
            },
            {
                "path": "src/OutputManager.cc",
                "new_content": (
                    "void OutputManager::WriteEnergyDepositsJson() {}\n"
                    "void OutputManager::WriteParticleTracksJson() {}\n"
                    + filler
                ),
            },
        ]
    }

    files = _project_files_for_review(
        proposed_patch,
        max_total_chars=2_600,
        max_chars_per_file=1_200,
    )
    paths = [file["path"] for file in files]
    prompt_text = json.dumps(files, ensure_ascii=False)

    assert "src/PrimaryGeneratorAction.cc" in paths
    assert "src/OutputManager.cc" in paths
    assert paths.index("src/PrimaryGeneratorAction.cc") < paths.index(
        "include/PrimaryGeneratorAction.hh"
    )
    assert paths.index("src/OutputManager.cc") < paths.index("include/OutputManager.hh")
    assert "SetParticleEnergy(10.0 * MeV)" in prompt_text
    assert "WriteEnergyDepositsJson" in prompt_text


def test_project_file_review_keeps_output_artifact_writers_in_long_files() -> None:
    from agent_core.g4_codegen.physics_quality_reviewer import _project_files_for_review

    geometry_blob = "\n".join(
        f'    {{"id": "component_{idx}", "material": "G4_Si"}},'
        for idx in range(80)
    )
    proposed_patch = {
        "changed_files": [
            {
                "path": "src/OutputManager.cc",
                "new_content": (
                    "#include \"OutputManager.hh\"\n"
                    "const char* _RadAgentIrGeometryComponents() {\n"
                    "  return R\"RADGEOM(\n"
                    f"{geometry_blob}\n"
                    ")RADGEOM\";\n"
                    "}\n"
                    "void OutputManager::AddTrackPoint() {}\n"
                    "void OutputManager::AddEnergyDepositPoint() {}\n"
                    "void OutputManager::WriteGeometryViewJson() {}\n"
                    "void OutputManager::WriteParticleTracksJson() {}\n"
                    "void OutputManager::WriteEnergyDepositsJson() {}\n"
                ),
            }
        ]
    }

    files = _project_files_for_review(
        proposed_patch,
        max_total_chars=1_200,
        max_chars_per_file=1_200,
    )
    prompt_text = json.dumps(files, ensure_ascii=False)

    assert "WriteGeometryViewJson" in prompt_text
    assert "WriteParticleTracksJson" in prompt_text
    assert "WriteEnergyDepositsJson" in prompt_text
    assert "AddEnergyDepositPoint" in prompt_text
