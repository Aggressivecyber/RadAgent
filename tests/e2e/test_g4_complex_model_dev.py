"""E2E test — G4 complex model dev mode.

Runs a simulated complex model through the full pipeline in dev mode
(no Geant4 environment required). Validates:
1. Model IR construction with multiple components
2. Code module planning
3. Gate execution (base + G4 modeling)
4. Review artifact generation
5. Final report with no-simplification disclosure
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agent_core.artifacts.nodes import (
    collect_artifacts,
    generate_artifact_manifest,
    generate_artifact_readme,
)
from agent_core.config.workspace import ensure_job_dirs
from agent_core.reports.nodes import generate_final_report


def _build_complex_model_ir() -> dict[str, Any]:
    """Build a complex Geant4 model IR for E2E testing."""
    return {
        "model_ir_id": "complex_dev_e2e",
        "job_id": "complex_dev",
        "modeling_mode": "realistic",
        "target_system": "Proton Therapy Beamline Detector",
        "simplification_policy": {
            "allow_simplification": False,
            "requires_user_approval": True,
            "approved_simplifications": [],
        },
        "components": [
            {
                "component_id": "world",
                "display_name": "World Volume",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 5000, "dy": 5000, "dz": 5000},
                "material_id": "G4_AIR",
                "roles": [],
                "open_issues": [],
                "source_evidence": ["default"],
            },
            {
                "component_id": "target_scatterer",
                "display_name": "Target Scatterer",
                "component_type": "volume",
                "geometry_type": "cylinder",
                "dimensions": {"rmin": 0, "rmax": 25, "dz": 2},
                "material_id": "G4_Pb",
                "mother_volume": "world",
                "roles": ["scatterer"],
                "open_issues": [],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "silicon_detector_1",
                "display_name": "Silicon Detector Layer 1",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 50, "dy": 50, "dz": 0.3},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "roles": ["edep_region"],
                "open_issues": [],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "silicon_detector_2",
                "display_name": "Silicon Detector Layer 2",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 50, "dy": 50, "dz": 0.3},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "roles": ["edep_region"],
                "open_issues": [],
                "source_evidence": ["user_specification"],
            },
        ],
        "materials": [
            {
                "material_id": "G4_AIR",
                "name": "G4_AIR",
                "classification": "nist",
                "nist_name": "G4_AIR",
                "density_g_cm3": 0.001214,
                "custom": False,
                "source_evidence": ["NIST"],
            },
            {
                "material_id": "G4_Pb",
                "name": "G4_Pb",
                "classification": "nist",
                "nist_name": "G4_Pb",
                "density_g_cm3": 11.35,
                "custom": False,
                "source_evidence": ["NIST"],
            },
            {
                "material_id": "G4_Si",
                "name": "G4_Si",
                "classification": "nist",
                "nist_name": "G4_Si",
                "density_g_cm3": 2.329,
                "custom": False,
                "source_evidence": ["NIST"],
            },
        ],
        "sources": [
            {
                "source_id": "proton_beam",
                "particle_type": "proton",
                "energy": {"value": 150.0, "unit": "MeV", "distribution": "gaussian", "sigma": 1.5},
                "beam": {
                    "position": [0, 0, 4000],
                    "direction": [0, 0, -1],
                    "sigma_position_um": 5.0,
                    "surface_shape": "circle",
                    "surface_size": [5.0],
                },
                "generator_type": "gps",
                "source_evidence": ["user_specification"],
            },
        ],
        "physics": {
            "physics_list": "QGSP_BIC_HP",
            "selection_reasoning": "QGSP_BIC_HP chosen for proton therapy: binary cascade for p < 10 GeV, high-precision neutron, standard EM.",
            "source_evidence": ["geant4_physics_guide"],
        },
        "scoring": [
            {
                "scoring_id": "edep_det1",
                "scoring_type": "region",
                "quantities": ["edep_MeV", "dose_Gy"],
                "target_component_id": "silicon_detector_1",
                "output_format": "csv",
                "source_evidence": ["user_specification"],
            },
            {
                "scoring_id": "edep_det2",
                "scoring_type": "region",
                "quantities": ["edep_MeV", "dose_Gy"],
                "target_component_id": "silicon_detector_2",
                "output_format": "csv",
                "source_evidence": ["user_specification"],
            },
        ],
        "interfaces": [
            {"parent_component": "world", "child_component": "target_scatterer", "interface_type": "daughter"},
            {"parent_component": "world", "child_component": "silicon_detector_1", "interface_type": "daughter"},
            {"parent_component": "world", "child_component": "silicon_detector_2", "interface_type": "daughter"},
        ],
        "open_issues": [],
        "evidence": {
            "evidence_decision": "allow_rag",
            "geometry": [{"source": "user_specification", "desc": "beamline layout"}],
            "materials": [
                {"source": "NIST", "desc": "G4_AIR"},
                {"source": "NIST", "desc": "G4_Pb"},
                {"source": "NIST", "desc": "G4_Si"},
            ],
            "source": [{"source": "user_specification", "desc": "150 MeV proton with Gaussian spread"}],
            "physics": [{"source": "geant4_physics_guide", "desc": "QGSP_BIC_HP for proton therapy"}],
            "scoring": [{"source": "user_specification", "desc": "edep in both silicon layers"}],
        },
        "ledger": {"entries": [], "version": "1.0"},
    }


class TestG4ComplexModelDev:
    """E2E test for complex G4 model in dev mode."""

    async def test_complex_model_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full pipeline with a complex multi-component model."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        job_id = "complex_dev"
        job_dir = ensure_job_dirs(job_id)

        # 1. Create model IR
        model_ir = _build_complex_model_ir()
        ir_dir = job_dir / "03_model_ir"
        ir_dir.mkdir(parents=True, exist_ok=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(json.dumps(model_ir, indent=2, ensure_ascii=False))

        # Verify model IR complexity
        assert len(model_ir["components"]) == 4
        assert len(model_ir["materials"]) == 3
        assert len(model_ir["sources"]) == 1
        assert len(model_ir["scoring"]) == 2
        assert model_ir["simplification_policy"]["allow_simplification"] is False

        # 2. Test code module planner
        from agent_core.g4_codegen.nodes.code_module_planner import code_module_planner

        plan_result = await code_module_planner({"g4_model_ir": model_ir})
        modules = plan_result["code_modules"]
        module_ids = [m["module_id"] for m in modules]
        assert len(modules) >= 8
        assert "geometry_silicon_detector_1" in module_ids
        assert "geometry_silicon_detector_2" in module_ids
        assert "sd_edep_det1" in module_ids
        assert "sd_edep_det2" in module_ids

        # 3. Test failure classifier
        from agent_core.gates.failure_classifier import (
            classify_failure,
            get_failure_summary,
        )

        # Context failure → context_subgraph
        assert classify_failure([0]) == "context_subgraph"
        # Modeling failure → g4_modeling_subgraph
        assert classify_failure([12, 13]) == "g4_modeling_subgraph"
        # Codegen failure → g4_codegen_subgraph
        assert classify_failure([5]) == "g4_codegen_subgraph"
        # Mixed → highest priority (lowest gate ID)
        assert classify_failure([5, 12, 17]) == "g4_codegen_subgraph"

        # Failure summary
        summary = get_failure_summary([12, 15, 18])
        assert summary["total"] == 3
        assert summary["retry_target"] == "g4_modeling_subgraph"

        # 4. Test gate codegen validators
        from agent_core.g4_codegen.validators.code_module_boundary import (
            validate_all_module_boundaries,
        )

        test_modules = [
            {"module_id": "test", "code": '#include "test.hh"\nvoid f() {}\n', "header": "test.hh"},
        ]
        valid, issues = validate_all_module_boundaries(test_modules)
        assert valid, f"Unexpected issues: {issues}"

        # 5. Collect artifacts
        gate_results = [
            {"gate_id": gid, "gate_name": f"Gate {gid}", "severity": "pass", "message": "OK"}
            for gid in range(19)
        ]
        gate_dir = job_dir / "09_validation"
        gate_dir.mkdir(parents=True, exist_ok=True)
        gate_path = gate_dir / "gate_results.json"
        gate_path.write_text(json.dumps(gate_results, indent=2))

        artifact_state = {
            "job_id": job_id,
            "gate_results_path": str(gate_path),
            "g4_model_ir_path": str(ir_path),
            "model_review_report_path": "",
            "construction_ledger_path": "",
            "code_module_plan_path": "",
            "proposed_patch_path": "",
            "validation_status": "VERIFIED",
            "errors": [],
        }

        collected = await collect_artifacts(artifact_state)
        artifact_dir = Path(collected["review_artifact_dir"])
        output_dir = artifact_dir / "output"

        # Verify all expected artifacts
        assert (output_dir / "g4_model_ir.json").exists()
        assert (output_dir / "gate_results.json").exists()
        assert (output_dir / "component_specs_summary.json").exists()
        assert (output_dir / "no_simplification_report.json").exists()
        assert (output_dir / "geometry_interface_report.json").exists()
        assert (output_dir / "evidence_traceability_report.json").exists()

        # Verify no_simplification report
        no_simp = json.loads((output_dir / "no_simplification_report.json").read_text())
        assert no_simp["status"] == "NO_SIMPLIFICATION"

        # Verify component summary reflects complex model
        comp_summary = json.loads(
            (output_dir / "component_specs_summary.json").read_text()
        )
        assert comp_summary["total_components"] == 4
        assert comp_summary["materials_count"] == 3
        assert "target_scatterer" in comp_summary["component_ids"]

        # Generate manifest and README
        artifact_state.update(collected)
        await generate_artifact_manifest(artifact_state)
        await generate_artifact_readme(artifact_state)

        assert (artifact_dir / "README.md").exists()
        assert (artifact_dir / "artifact_manifest.json").exists()

        # 6. Generate report
        report_result = await generate_final_report({
            "job_id": job_id,
            "user_query": "Simulate 150 MeV proton beam through Pb scatterer into 2-layer silicon detector",
            "execution_mode": "dev_no_geant4_env",
            "validation_status": "VERIFIED",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": [],
            "errors": [],
            "g4_model_ir_path": str(ir_path),
            "gate_results_path": str(gate_path),
        })

        assert report_result["verified"] is True
        report_text = Path(report_result["final_report_path"]).read_text()
        assert "target_scatterer" in report_text
        assert "silicon_detector" in report_text
        assert "G4_Pb" in report_text
        assert "Allow simplification" in report_text
        assert "`False`" in report_text
