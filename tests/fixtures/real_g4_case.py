from __future__ import annotations

from typing import Any

from agent_core.config.environment import load_environment
from agent_core.models.gateway import reset_model_gateway


def require_real_model_api() -> None:
    env = load_environment()
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
        "interfaces": [
            {
                "interface_id": "world_contains_silicon",
                "component_a": "world",
                "component_b": "silicon_detector",
                "relationship": "contains",
                "expected_gap_um": 0.0,
                "overlap_allowed": False,
                "overlap_check_enabled": True,
                "source_evidence": evidence,
            },
            {
                "interface_id": "silicon_oxide_stack",
                "component_a": "silicon_detector",
                "component_b": "oxide_layer",
                "relationship": "stacked_above",
                "expected_gap_um": 10.0,
                "overlap_allowed": False,
                "overlap_check_enabled": True,
                "source_evidence": evidence,
            },
            {
                "interface_id": "world_contains_shield",
                "component_a": "world",
                "component_b": "aluminum_shield",
                "relationship": "contains",
                "expected_gap_um": 0.0,
                "overlap_allowed": False,
                "overlap_check_enabled": True,
                "source_evidence": evidence,
            },
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
