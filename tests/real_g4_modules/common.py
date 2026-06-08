from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from agent_core.config.environment import load_environment
from agent_core.g4_codegen.graph_nodes import _get_agent_function, _get_hard_gate_function
from agent_core.g4_codegen.module_agents.base import save_module_result
from agent_core.g4_codegen.module_agents.module_context_builder import build_module_context
from agent_core.g4_codegen.module_gates.llm_gate_base import run_llm_gate
from agent_core.g4_codegen.planners.code_architecture_planner import plan_code_architecture
from agent_core.g4_codegen.planners.codegen_plan_builder import build_codegen_plan
from agent_core.g4_codegen.planners.geometry_strategy_planner import plan_geometry_strategy
from agent_core.g4_codegen.planners.module_contract_builder import build_module_contracts
from agent_core.g4_codegen.repair.module_repair_loop import repair_module
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult, ModuleGateResult
from agent_core.models.gateway import reset_model_gateway


def require_real_model_provider() -> None:
    env = load_environment()
    provider = env.model_provider.value.lower()
    assert provider != "mock", "mock provider is not allowed for real G4 acceptance tests"
    os.environ["RADAGENT_MODEL_PROVIDER"] = provider
    pro = env.models[next(t for t in env.models if t.value == "pro")]
    assert pro.base_url, "real G4 acceptance tests require a configured model base URL"
    assert pro.api_key_configured, (
        f"real G4 acceptance tests require API key env: {pro.api_key_env}"
    )
    reset_model_gateway()


def build_real_g4_model_ir(job_id: str) -> dict[str, Any]:
    evidence = ["user:real_g4_acceptance_case"]
    return {
        "schema_version": "g4_model_ir_v1",
        "model_ir_id": f"{job_id}_ir",
        "job_id": job_id,
        "modeling_mode": "realistic",
        "target_system": "Layered silicon detector with shield and proton source",
        "simplification_policy": {
            "allow_simplification": False,
            "requires_user_approval": True,
            "approved_simplifications": [],
        },
        "global_units": {"length": "mm", "energy": "MeV", "dose": "Gy", "time": "s"},
        "evidence": {
            "evidence_decision": "allow_rag",
            "geometry": [{"source": evidence[0]}],
            "materials": [{"source": evidence[0]}],
            "source": [{"source": evidence[0]}],
            "physics": [{"source": evidence[0]}],
            "scoring": [{"source": evidence[0]}],
        },
        "materials": [
            {
                "material_id": "G4_AIR",
                "name": "Air",
                "classification": "nist",
                "nist_name": "G4_AIR",
                "density_g_cm3": 0.0012,
                "state": "gas",
                "source_evidence": evidence,
            },
            {
                "material_id": "G4_Si",
                "name": "Silicon",
                "classification": "nist",
                "nist_name": "G4_Si",
                "density_g_cm3": 2.33,
                "state": "solid",
                "source_evidence": evidence,
            },
            {
                "material_id": "G4_SILICON_DIOXIDE",
                "name": "Silicon dioxide",
                "classification": "nist",
                "nist_name": "G4_SILICON_DIOXIDE",
                "density_g_cm3": 2.2,
                "state": "solid",
                "source_evidence": evidence,
            },
            {
                "material_id": "G4_Al",
                "name": "Aluminum",
                "classification": "nist",
                "nist_name": "G4_Al",
                "density_g_cm3": 2.7,
                "state": "solid",
                "source_evidence": evidence,
            },
        ],
        "components": [
            {
                "component_id": "world",
                "display_name": "World",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 200.0, "dy": 200.0, "dz": 200.0},
                "material_id": "G4_AIR",
                "placement": {"position": [0.0, 0.0, 0.0]},
                "mother_volume": None,
                "source_evidence": evidence,
            },
            {
                "component_id": "silicon_detector",
                "display_name": "Silicon detector",
                "component_type": "substrate",
                "geometry_type": "box",
                "dimensions": {"dx": 20.0, "dy": 20.0, "dz": 0.5},
                "material_id": "G4_Si",
                "placement": {"position": [0.0, 0.0, 0.0]},
                "mother_volume": "world",
                "sensitive": True,
                "roles": ["edep_region"],
                "source_evidence": evidence,
            },
            {
                "component_id": "oxide_layer",
                "display_name": "Oxide layer",
                "component_type": "layer",
                "geometry_type": "box",
                "dimensions": {"dx": 20.0, "dy": 20.0, "dz": 0.02},
                "material_id": "G4_SILICON_DIOXIDE",
                "placement": {"position": [0.0, 0.0, 0.27]},
                "mother_volume": "world",
                "source_evidence": evidence,
            },
            {
                "component_id": "aluminum_shield",
                "display_name": "Aluminum shield",
                "component_type": "shielding",
                "geometry_type": "box",
                "dimensions": {"dx": 30.0, "dy": 30.0, "dz": 1.0},
                "material_id": "G4_Al",
                "placement": {"position": [0.0, 0.0, -10.0]},
                "mother_volume": "world",
                "roles": ["shield"],
                "source_evidence": evidence,
            },
        ],
        "sources": [
            {
                "source_id": "proton_source",
                "particle_type": "proton",
                "energy": {"value": 10.0, "unit": "MeV", "distribution": "mono"},
                "beam": {
                    "position": [0.0, 0.0, -80.0],
                    "direction": [0.0, 0.0, 1.0],
                    "surface_shape": "point",
                },
                "generator_type": "gun",
                "events": 1000,
                "source_evidence": evidence,
            }
        ],
        "physics": {
            "physics_list": "FTFP_BERT",
            "selection_reasoning": (
                "FTFP_BERT covers 10 MeV protons, electromagnetic energy deposition, "
                "and detector dose scoring."
            ),
            "em_physics": "standard",
            "hadronic": "bertini",
            "source_evidence": evidence,
        },
        "sensitive_detectors": [
            {
                "sd_id": "silicon_sd",
                "name": "SensitiveDetector",
                "linked_component_ids": ["silicon_detector"],
                "scoring_ids": ["edep_scoring"],
                "collection_name": "SiliconHits",
                "hit_fields": [{"name": "edep_MeV", "dtype": "double", "unit": "MeV"}],
            }
        ],
        "scoring": [
            {
                "scoring_id": "edep_scoring",
                "scoring_type": "region",
                "quantities": ["edep_MeV", "dose_Gy"],
                "region_scores": [
                    {"region_component_id": "silicon_detector", "quantity": "edep_MeV"}
                ],
                "output_format": "csv",
                "source_evidence": evidence,
            }
        ],
        "human_confirmation": {"status": "approved"},
        "assumptions_confirmed": True,
        "confirmed_fields": ["geometry", "materials", "source", "physics", "scoring"],
        "unconfirmed_fields": [],
    }


def assert_generated_files(
    module_name: str, result: ModuleAgentResult, required_symbols: tuple[str, ...]
) -> None:
    assert result.status in {"generated", "repaired"}
    assert result.generated_files
    joined = "\n".join(f.new_content for f in result.generated_files)
    paths = {f.path for f in result.generated_files}
    for file_entry in result.generated_files:
        assert file_entry.new_content
        assert file_entry.generated_by == f"{module_name}_module_agent"
        assert file_entry.module_name == module_name
        assert "```" not in file_entry.new_content
        assert "TODO" not in file_entry.new_content
        assert "NotImplemented" not in file_entry.new_content
    for symbol in required_symbols:
        assert symbol in joined or symbol in paths


async def run_real_module_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    required_symbols: tuple[str, ...],
) -> tuple[ModuleAgentResult, ModuleGateResult, ModuleGateResult]:
    require_real_model_provider()
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    job_id = f"real_{module_name}_module"
    g4_model_ir = build_real_g4_model_ir(job_id)
    codegen_plan = build_codegen_plan(g4_model_ir, job_id, "strict")
    geometry_strategy_plan = plan_geometry_strategy(g4_model_ir, job_id)
    code_architecture_plan = plan_code_architecture(g4_model_ir, codegen_plan, job_id)
    module_contract = build_module_contracts(g4_model_ir, codegen_plan, job_id)[module_name]
    module_context = build_module_context(
        module_name=module_name,
        module_contract=module_contract,
        g4_model_ir=g4_model_ir,
        codegen_plan=codegen_plan,
        geometry_strategy_plan=geometry_strategy_plan,
        code_architecture_plan=code_architecture_plan,
        job_id=job_id,
        run_mode="strict",
    )

    result = await _get_agent_function(module_name)(module_context)
    save_module_result(result, job_id)
    assert_generated_files(module_name, result, required_symbols)
    files = [GeneratedModuleFile(**f.model_dump()) for f in result.generated_files]
    hard_gate = _get_hard_gate_function(module_name)(files, module_status=result.status)
    llm_gate = await run_llm_gate(
        module_name, module_context, [f.model_dump() for f in files], hard_gate.model_dump()
    )

    for _ in range(3):
        if hard_gate.status == "pass" and llm_gate.status == "pass":
            break
        failed_gate = hard_gate if hard_gate.status != "pass" else llm_gate
        result = await repair_module(module_name, module_context, result, failed_gate)
        save_module_result(result, job_id)
        assert_generated_files(module_name, result, required_symbols)
        files = [GeneratedModuleFile(**f.model_dump()) for f in result.generated_files]
        hard_gate = _get_hard_gate_function(module_name)(files, module_status=result.status)
        llm_gate = await run_llm_gate(
            module_name, module_context, [f.model_dump() for f in files], hard_gate.model_dump()
        )

    assert hard_gate.status == "pass", hard_gate.errors
    assert llm_gate.status == "pass", llm_gate.errors
    return result, hard_gate, llm_gate
