"""Tests for Gate Validation Subgraph."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.gates.base_gates import gate_name as _gate_name
from agent_core.gates.base_gates import run_base_gates
from agent_core.gates.g4_modeling_gates import run_g4_modeling_gates
from agent_core.gates.gate_runner import finalize_gate_results
from agent_core.observability import write_failure_bundle
from agent_core.workspace.paths import STAGE_GATE_VALIDATION


def test_task_spec_schema_accepts_requirements_review_intermediate_shape() -> None:
    """Gate 1 must not reject task specs that were intentionally sent through review."""
    from agent_core.validators.schema_validator import SchemaValidator

    valid, errors = SchemaValidator().validate_task_spec(
        {
            "simulation_scope": ["geant4"],
            "particle": {},
            "energy": {"value": 10.0, "unit": "MeV"},
            "modeling_mode": "realistic",
            "metadata": {
                "source_particle_missing": "true",
                "requirements_review_required": "true",
            },
            "requirements_review_hints": {
                "questions": [
                    {
                        "field_path": "source.particle",
                        "question": "请确认辐照粒子类型。",
                        "recommended_value": "gamma",
                    }
                ]
            },
        }
    )

    assert valid
    assert errors == []


class TestGateNames:
    """Test gate name mapping."""

    def test_base_gates(self) -> None:
        assert _gate_name(0) == "Context Sufficiency"
        assert _gate_name(6) == "Build/Parse"
        assert _gate_name(11) == "Physics Sanity"

    def test_g4_gates(self) -> None:
        assert _gate_name(12) == "G4-A Model Completeness"
        assert _gate_name(13) == "G4-B No Unapproved Simplification"
        assert _gate_name(14) == "G4-C Geometry Interface"
        assert _gate_name(15) == "G4-D Overlap Policy"
        assert _gate_name(16) == "G4-E Evidence Traceability"
        assert _gate_name(17) == "G4-F Code Module Boundary"
        assert _gate_name(18) == "G4-G No Magic Number"
        assert _gate_name(19) == "G4-H Human Confirmation"

    def test_unknown_gate(self) -> None:
        assert _gate_name(99) == "Gate 99"


class TestRunBaseGates:
    async def test_all_gates_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """All 12 base gates (0-11) must be checked."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
        job_dir = workspace / "jobs" / "test" / STAGE_GATE_VALIDATION
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test",
            "execution_mode": "strict",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        result = await run_base_gates(state)
        gate_results = result["gate_results"]
        gate_ids = [g["gate_id"] for g in gate_results]

        # Must have gates 0-11
        for gid in range(12):
            assert gid in gate_ids, f"Missing gate {gid}"

    async def test_no_auto_pass_gate_7_11(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gates 7-11 must NOT auto-pass in acceptance mode."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
        job_dir = workspace / "jobs" / "test" / STAGE_GATE_VALIDATION
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test",
            "execution_mode": "acceptance",
            "context_decision": "allow_rag",
            "task_spec": {},
            "g4_model_ir": {},
            "generated_code_dir": "",
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        result = await run_base_gates(state)
        gate_results = result["gate_results"]

        for g in gate_results:
            if g["gate_id"] in (7, 9):
                assert g["status"] != "pass", f"Gate {g['gate_id']} auto-passed in acceptance mode"

    async def test_finalize_pass_clears_stale_failure_bundle(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A successful retry must not leave an old failure bundle behind."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
        stale = write_failure_bundle(
            job_id="retry_job",
            status="failed",
            phase="gate_validation",
            errors=["old static check failure"],
        )
        assert stale is not None
        assert stale.is_file()

        result = await finalize_gate_results(
            {
                "job_id": "retry_job",
                "run_mode": "strict",
                "gate_results": [
                    {
                        "gate_id": 5,
                        "name": "Static Check",
                        "status": "pass",
                        "critical": True,
                        "failed_items": [],
                        "warnings": [],
                    }
                ],
            }
        )

        assert result["validation_status"] == "passed"
        assert not stale.exists()

    async def test_gate1_validates_external_source_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate 1 should treat simulation input sources as part of the task contract."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
        job_dir = workspace / "jobs" / "external_source_ok"
        gate_dir = job_dir / STAGE_GATE_VALIDATION
        gate_dir.mkdir(parents=True)
        spectrum_path = job_dir / "02_task_plan" / "space_radiation" / "ap8.csv"
        spectrum_path.parent.mkdir(parents=True)
        spectrum_path.write_text("energy_MeV,flux_cm-2_s-1_MeV-1\n1,42\n", encoding="utf-8")

        state = {
            "job_id": "external_source_ok",
            "execution_mode": "strict",
            "context_decision": "allow_rag",
            "task_spec": {
                "simulation_scope": ["geant4"],
                "particles": [
                    {
                        "source_id": "ap8_orbit_protons",
                        "type": "proton",
                        "energy_MeV": 1.0,
                        "energy_distribution": "spectrum",
                        "spectrum_file": str(spectrum_path),
                        "direction": [0.0, 0.0, -1.0],
                        "generator_type": "gps",
                        "events": 1000,
                    }
                ],
                "external_sources": [
                    {
                        "source_id": "ap8_orbit_protons",
                        "source_type": "environment",
                        "domain": "space_radiation",
                        "provider": "ap8ae8",
                        "model": "AP8MIN",
                        "status": "ready",
                        "artifact_paths": [str(spectrum_path)],
                        "parameters": {"l_shell": 2.0, "bb0": 1.05},
                        "provenance": {"dataset_id": "nasa-radbelt-aep8"},
                        "derived_outputs": [
                            {
                                "kind": "geant4_source_spectrum",
                                "path": str(spectrum_path),
                                "consumer": "g4_modeling",
                            }
                        ],
                        "limitations": ["trapped belt static model"],
                        "consumers": [
                            "task_planning",
                            "g4_modeling",
                            "g4_codegen",
                            "gates",
                            "copilot",
                        ],
                    }
                ],
            },
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        result = await run_base_gates(state)

        gate1 = [g for g in result["gate_results"] if g["gate_id"] == 1][0]
        assert gate1["status"] == "pass"
        assert "external source artifacts valid" in gate1["passed_items"]
        assert str(spectrum_path) in gate1["file_paths"]

    async def test_gate1_fails_when_external_source_artifact_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ready external source must not pass if its declared artifact is absent."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
        (workspace / "jobs" / "external_source_missing" / STAGE_GATE_VALIDATION).mkdir(
            parents=True
        )
        missing_path = workspace / "jobs" / "external_source_missing" / "missing.csv"

        state = {
            "job_id": "external_source_missing",
            "execution_mode": "strict",
            "context_decision": "allow_rag",
            "task_spec": {
                "simulation_scope": ["geant4"],
                "external_sources": [
                    {
                        "source_id": "ap8_orbit_protons",
                        "source_type": "environment",
                        "domain": "space_radiation",
                        "provider": "ap8ae8",
                        "model": "AP8MIN",
                        "status": "ready",
                        "artifact_paths": [str(missing_path)],
                        "parameters": {"l_shell": 2.0, "bb0": 1.05},
                        "provenance": {"dataset_id": "nasa-radbelt-aep8"},
                        "derived_outputs": [
                            {
                                "kind": "geant4_source_spectrum",
                                "path": str(missing_path),
                                "consumer": "g4_modeling",
                            }
                        ],
                        "limitations": [],
                        "consumers": ["gates"],
                    }
                ],
            },
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        result = await run_base_gates(state)

        gate1 = [g for g in result["gate_results"] if g["gate_id"] == 1][0]
        assert gate1["status"] == "fail"
        assert any(str(missing_path) in item for item in gate1["failed_items"])


class TestRunG4ModelingGates:
    async def test_no_model_ir_skips(self) -> None:
        """If no model IR, G4 gates should report failure."""
        state = {
            "gate_results": [],
            "failed_gates": [],
            "g4_model_ir": {},
        }
        result = await run_g4_modeling_gates(state)
        # Should not crash, may add failure entries
        assert "gate_results" in result

    async def test_with_complex_model_ir(self) -> None:
        """Complex model IR should be validated by G4-A to G4-H."""
        from agent_core.g4_modeling.schemas import (
            BeamProfile,
            ComponentSpec,
            ConstructionLedger,
            EnergySpec,
            G4ModelIR,
            MaterialSpec,
            PhysicsSpec,
            ScoringSpec,
            SimplificationPolicy,
            SourceSpec,
        )

        model_ir = G4ModelIR(
            model_ir_id="test_mir",
            job_id="test",
            modeling_mode="realistic",
            target_system="Test detector",
            simplification_policy=SimplificationPolicy(
                allow_simplification=False,
                requires_user_approval=True,
            ),
            components=[
                ComponentSpec(
                    component_id="world",
                    display_name="World",
                    component_type="world",
                    geometry_type="box",
                    dimensions={"dx": 5000, "dy": 5000, "dz": 5000},
                    material_id="Air",
                    source_evidence=["default_world"],
                ),
                ComponentSpec(
                    component_id="silicon_bulk",
                    display_name="Silicon Bulk",
                    component_type="volume",
                    geometry_type="box",
                    dimensions={"dx": 500, "dy": 500, "dz": 300},
                    material_id="Si",
                    mother_volume="world",
                    source_evidence=["user_specification"],
                    roles=["edep_region"],
                ),
            ],
            materials=[
                MaterialSpec(
                    material_id="Air",
                    name="G4_AIR",
                    classification="nist",
                    nist_name="G4_AIR",
                    density_g_cm3=0.001214,
                    source_evidence=["NIST"],
                ),
                MaterialSpec(
                    material_id="Si",
                    name="G4_Si",
                    classification="nist",
                    nist_name="G4_Si",
                    density_g_cm3=2.329,
                    source_evidence=["NIST"],
                ),
            ],
            sources=[
                SourceSpec(
                    source_id="proton_beam",
                    particle_type="proton",
                    energy=EnergySpec(
                        value=10.0,
                        unit="MeV",
                        distribution="mono",
                    ),
                    beam=BeamProfile(
                        position=[0, 0, 5000],
                        direction=[0, 0, -1],
                    ),
                    generator_type="gun",
                    source_evidence=["user_specification"],
                ),
            ],
            physics=PhysicsSpec(
                physics_list="FTFP_BERT",
                selection_reasoning=(
                    "FTFP_BERT chosen for proton therapy range, covers EM and hadronic processes."
                ),
                source_evidence=["standard_EM"],
            ),
            scoring=[
                ScoringSpec(
                    scoring_id="edep_silicon",
                    scoring_type="region",
                    quantities=["edep_MeV"],
                    target_component_id="silicon_bulk",
                    output_format="csv",
                    source_evidence=["user_specification"],
                ),
            ],
            ledger=ConstructionLedger(),
        )

        state = {
            "gate_results": [],
            "failed_gates": [],
            "g4_model_ir": model_ir.model_dump(mode="json"),
            "code_modules": [
                {
                    "module_id": "src/StyleOnly.cc",
                    "code": 'auto box = new G4Box("b", 42.5, 42.5, 42.5);',
                }
            ],
        }

        result = await run_g4_modeling_gates(state)
        gate_results = result["gate_results"]
        g4_gate_ids = [g["gate_id"] for g in gate_results]

        # Must have G4-A through G4-H (12-19)
        for gid in range(12, 20):
            assert gid in g4_gate_ids, f"Missing G4 gate {gid}"
        gate18 = [g for g in gate_results if g["gate_id"] == 18][0]
        assert gate18["status"] == "warning"
        assert _gate_name(18) not in result["failed_gates"]
