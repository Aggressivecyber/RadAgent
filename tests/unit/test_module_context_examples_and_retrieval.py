"""Module context examples, interfaces, and RAG/web policy injection."""

from __future__ import annotations

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
