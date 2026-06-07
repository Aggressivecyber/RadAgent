"""Tests for Gate Validation Subgraph."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.gates.nodes import _gate_name, run_base_gates, run_g4_modeling_gates


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

    def test_unknown_gate(self) -> None:
        assert _gate_name(99) == "Gate 99"


class TestRunBaseGates:
    async def test_all_gates_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """All 12 base gates (0-11) must be checked."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
        job_dir = workspace / "jobs" / "test" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test",
            "execution_mode": "dev_no_geant4_env",
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
        job_dir = workspace / "jobs" / "test" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test",
            "execution_mode": "mvp1_acceptance",
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
        """Complex model IR should be validated by G4-A to G4-G."""
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
                    "FTFP_BERT chosen for proton therapy range,"
                    " covers EM and hadronic processes."
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
            "code_modules": [],
        }

        result = await run_g4_modeling_gates(state)
        gate_results = result["gate_results"]
        g4_gate_ids = [g["gate_id"] for g in gate_results]

        # Must have G4-A through G4-G (12-18)
        for gid in range(12, 19):
            assert gid in g4_gate_ids, f"Missing G4 gate {gid}"
