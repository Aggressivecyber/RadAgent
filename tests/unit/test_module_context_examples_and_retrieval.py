"""Module context examples, interfaces, and RAG/web policy injection."""

from __future__ import annotations

import json

from agent_core.g4_codegen.module_agents.module_context_builder import build_module_context
from agent_core.g4_codegen.module_agents.module_context_examples import (
    get_module_code_example,
    get_module_interface_context,
)
from agent_core.graph.subgraphs.g4_codegen_graph import MODULE_LAYERS

MODULE_NAMES = [module_name for _, modules in MODULE_LAYERS for module_name in modules]


def _contract(module_name: str) -> dict:
    return {
        "module_name": module_name,
        "module_type": module_name,
        "responsibilities": ["generate"],
        "input_ir_paths": [],
        "output_files": get_module_code_example(module_name).get("owned_files", []),
        "required_symbols": get_module_code_example(module_name).get("primary_symbols", []),
        "dependencies": get_module_interface_context(module_name).get("upstream_modules", []),
        "forbidden_patterns": [],
    }


def test_all_required_modules_have_code_examples_and_interfaces() -> None:
    for module_name in MODULE_NAMES:
        example = get_module_code_example(module_name)
        interface = get_module_interface_context(module_name)

        assert example["owned_files"]
        assert example["primary_symbols"]
        assert example["example"]
        assert "upstream_modules" in interface
        assert "downstream_modules" in interface
        assert interface["provides"]


def test_module_context_includes_examples_interfaces_and_retrieval_policy() -> None:
    ctx = build_module_context(
        module_name="beam_physics",
        module_contract=_contract("beam_physics"),
        g4_model_ir={
            "model_ir_id": "test",
            "job_id": "job_001",
            "physics": {"physics_list": "FTFP_BERT"},
            "sources": [{"particle_type": "proton"}],
        },
        codegen_plan={"required_modules": MODULE_NAMES},
        geometry_strategy_plan={"global_strategy": "agent_generated_geometry"},
        code_architecture_plan={"classes": []},
        job_id="job_001",
        rag_context=[
            {
                "title": "Physics list factory",
                "content": "G4PhysListFactory GetReferencePhysList physics list",
                "score": 0.91,
            }
        ],
        rag_score=0.91,
        web_context=[
            {
                "title": "Geant4 physics docs",
                "snippet": "G4PhysListFactory reference physics lists",
                "url": "https://geant4.web.cern.ch/",
            }
        ],
        context_decision="allow_with_web_supplement",
        web_search_available=True,
    )

    assert ctx["module_code_example"]["primary_symbols"] == [
        "PrimaryGeneratorAction",
        "PhysicsListFactoryWrapper",
    ]
    assert "PrimaryGeneratorAction.hh" in ctx["module_code_example"]["owned_files"][0]
    assert "runtime_app" in ctx["interface_context"]["downstream_modules"]
    assert ctx["rag_snippets"]
    assert ctx["web_context"]
    assert ctx["context_retrieval_policy"]["rag_score"] == 0.91
    assert ctx["context_retrieval_policy"]["web_search_available"] is True


def test_module_context_loads_agentic_repair_lessons_for_prompt(
    tmp_path, monkeypatch
) -> None:
    """Lessons learned by repair should feed the next module-agent prompt."""
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    lessons_path = (
        tmp_path
        / "jobs"
        / "job_lesson_context"
        / "05_codegen"
        / "integration"
        / "agentic_repair_lessons.json"
    )
    lessons_path.parent.mkdir(parents=True)
    lessons_path.write_text(
        json.dumps(
            {
                "schema_version": "agentic_repair_lessons_v1",
                "job_id": "job_lesson_context",
                "lessons": [
                    {
                        "id": "visual_workbench_artifact",
                        "title": "Keep workbench artifacts non-empty",
                        "prompt_instruction": (
                            "Write real geometry_view.json, particle_tracks.json, "
                            "and energy_deposits.json from runtime data."
                        ),
                        "count": 3,
                    },
                    {
                        "id": "broken",
                        "title": "invalid lesson without prompt instruction",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    ctx = build_module_context(
        module_name="runtime_app",
        module_contract=_contract("runtime_app"),
        g4_model_ir={"model_ir_id": "test_lessons"},
        codegen_plan={"required_modules": MODULE_NAMES},
        geometry_strategy_plan={},
        code_architecture_plan={},
        job_id="job_lesson_context",
    )

    lessons = ctx["agentic_repair_lessons"]
    assert lessons["source_path"] == str(lessons_path)
    assert lessons["lesson_count"] == 1
    assert lessons["lessons"][0]["id"] == "visual_workbench_artifact"
    assert "energy_deposits.json" in lessons["lessons"][0]["prompt_instruction"]

    persisted = json.loads(
        (
            tmp_path
            / "jobs"
            / "job_lesson_context"
            / "05_codegen"
            / "module_contexts"
            / "runtime_app.json"
        ).read_text(encoding="utf-8")
    )
    assert persisted["agentic_repair_lessons"]["lessons"][0]["id"] == (
        "visual_workbench_artifact"
    )


def test_simulation_core_context_exposes_stable_runtime_abi_contract() -> None:
    ctx = build_module_context(
        module_name="simulation_core",
        module_contract=_contract("simulation_core"),
        g4_model_ir={
            "model_ir_id": "test_abi",
            "job_id": "job_abi",
            "components": [{"component_id": "detector"}],
            "materials": [{"material_id": "silicon", "geant4_name": "G4_Si"}],
            "scoring": [{"scoring_id": "edep", "target_component_id": "detector"}],
        },
        codegen_plan={"required_modules": MODULE_NAMES},
        geometry_strategy_plan={"global_strategy": "agent_generated_geometry"},
        code_architecture_plan={"classes": []},
        job_id="job_abi",
    )

    abi_contract = ctx["module_code_example"]["runtime_abi_contract"]
    joined = json.dumps(abi_contract, ensure_ascii=False)

    assert (
        "SensitiveDetector(const G4String& name, const G4String& hitsCollectionName, "
        "ScoringManager* scoringManager)"
    ) in joined
    assert "using HitsCollection = G4THitsCollection<Hit>" in joined
    assert "new ::Hit()" in joined
    assert "GetCurrentEvent()->GetEventID()" in joined
    assert "step->GetTrack()->GetTrackID()" in joined
    assert "new SensitiveDetector(sdName, collectionName, fScoringManager)" in joined
    assert "ScoringManager::Instance()" in joined
    assert "RegisterRegion(" in joined
    assert "new ScoringManager" not in joined
    assert "RegisterRegionScoring" not in joined


def test_module_context_filters_rag_snippets_by_module_keywords() -> None:
    ctx = build_module_context(
        module_name="simulation_core",
        module_contract=_contract("simulation_core"),
        g4_model_ir={
            "model_ir_id": "test",
            "job_id": "job_001",
            "scoring": [{"scoring_id": "edep"}],
            "components": [{"component_id": "detector"}],
            "materials": [{"material_id": "G4_Si"}],
        },
        codegen_plan={"required_modules": MODULE_NAMES},
        geometry_strategy_plan={"global_strategy": "agent_generated_geometry"},
        code_architecture_plan={"classes": []},
        job_id="job_001",
        rag_context=[
            {"title": "Material", "content": "G4NistManager material lookup", "score": 0.9},
            {
                "title": "Scoring mesh",
                "content": "G4VScoringMesh GetScoreMap scoring mesh",
                "score": 0.88,
            },
        ],
    )

    joined = " ".join(item.get("content", "") for item in ctx["rag_snippets"])
    assert "GetScoreMap" in joined


def test_simulation_core_context_preserves_ir_units_and_coordinate_contract() -> None:
    ctx = build_module_context(
        module_name="simulation_core",
        module_contract=_contract("simulation_core"),
        g4_model_ir={
            "model_ir_id": "test_units",
            "job_id": "job_units",
            "global_units": {
                "length": "um",
                "energy": "MeV",
                "dose": "Gy",
                "time": "s",
            },
            "coordinate_system": {
                "system": "cartesian",
                "origin_definition": "world_center",
                "axis_definition": {
                    "x": "slab_width",
                    "y": "slab_height",
                    "z": "beam_direction",
                },
                "unit": "um",
            },
            "components": [
                {
                    "component_id": "silicon_slab",
                    "shape": "box",
                    "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 1000.0},
                }
            ],
            "materials": [{"material_id": "silicon", "geant4_name": "G4_Si"}],
            "scoring": [{"scoring_id": "edep", "target_component_id": "silicon_slab"}],
        },
        codegen_plan={"required_modules": MODULE_NAMES},
        geometry_strategy_plan={"global_strategy": "agent_generated_geometry"},
        code_architecture_plan={"classes": []},
        job_id="job_units",
    )

    ir_subset = ctx["g4_model_ir_subset"]
    assert ir_subset["global_units"]["length"] == "um"
    assert ir_subset["coordinate_system"]["unit"] == "um"
    assert ir_subset["unit_contract"]["length_unit"] == "um"
    assert "G4Box" in ir_subset["unit_contract"]["box_dimension_rule"]
