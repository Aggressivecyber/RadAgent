"""Tests for Report Subgraph."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_core.reports.nodes import generate_final_report


@pytest.fixture
def temp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    return workspace


class TestGenerateFinalReport:
    async def test_verified_report(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test_job",
            "user_query": "test query",
            "execution_mode": "strict",
            "validation_status": "passed",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": [],
            "errors": [],
            "g4_model_ir_path": "",
            "gate_results_path": "",
        }
        result = await generate_final_report(state)
        assert result["verified"] is True
        assert result["termination_reason"] == "completed_passed"
        assert Path(result["final_report_path"]).exists()

        report = Path(result["final_report_path"]).read_text()
        assert "passed" in report
        assert "test query" in report

    async def test_failed_report(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test_job",
            "user_query": "test query",
            "execution_mode": "strict",
            "validation_status": "failed",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": ["Gate 5"],
            "errors": [],
            "g4_model_ir_path": "",
            "gate_results_path": "",
        }
        result = await generate_final_report(state)
        assert result["verified"] is False
        assert "failed_gates" in result["termination_reason"]

    async def test_reserved_scope_note(self, temp_workspace: Path) -> None:
        """Report must mention TCAD/SPICE reserved scopes."""
        state = {
            "job_id": "test_job",
            "user_query": "geant4 + tcad + spice",
            "execution_mode": "strict",
            "validation_status": "passed",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4", "tcad", "spice"],
            "failed_gates": [],
            "errors": [],
            "g4_model_ir_path": "",
            "gate_results_path": "",
        }
        result = await generate_final_report(state)
        report = Path(result["final_report_path"]).read_text()
        assert "reserved" in report.lower()

    async def test_report_with_model_ir(self, temp_workspace: Path) -> None:
        """Report with model IR should list components and materials."""
        # Create a mock model IR file
        ir_dir = temp_workspace / "jobs" / "test_job" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "component_id": "world",
                            "component_type": "world",
                            "material_id": "Air",
                            "roles": [],
                            "open_issues": [],
                        },
                        {
                            "component_id": "silicon",
                            "component_type": "volume",
                            "material_id": "Si",
                            "roles": ["edep_region"],
                            "open_issues": [],
                        },
                    ],
                    "materials": [
                        {
                            "material_id": "Air",
                            "name": "G4_AIR",
                            "density_g_cm3": 0.001214,
                            "custom": False,
                        },
                        {
                            "material_id": "Si",
                            "name": "G4_Si",
                            "density_g_cm3": 2.329,
                            "custom": False,
                        },
                    ],
                    "sources": [{"particle_type": "proton", "energy_MeV": 10}],
                    "scoring": [{"scoring_id": "edep", "scoring_type": "edep"}],
                    "simplification_policy": {
                        "allow_simplification": False,
                        "requires_user_approval": True,
                        "approved_simplifications": [],
                    },
                    "open_issues": [],
                    "evidence": {
                        "evidence_decision": "allow_rag",
                        "geometry": [],
                        "materials": [],
                        "source": [],
                        "physics": [],
                        "scoring": [],
                    },
                }
            )
        )

        state = {
            "job_id": "test_job",
            "user_query": "test",
            "execution_mode": "strict",
            "validation_status": "passed",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": [],
            "errors": [],
            "g4_model_ir_path": str(ir_path),
            "gate_results_path": "",
        }
        result = await generate_final_report(state)
        report = Path(result["final_report_path"]).read_text()
        assert "silicon" in report
        assert "Si" in report
        assert "Air" in report
        # Report uses "Allow simplification" (human-readable label)
        assert "Allow simplification" in report

    async def test_report_reads_gate_schema_correctly(self, temp_workspace: Path) -> None:
        """Report must read 'name' and 'status' fields from gate results."""
        # Create gate results with correct schema
        val_dir = temp_workspace / "jobs" / "test_job" / "09_validation"
        val_dir.mkdir(parents=True)
        gate_path = val_dir / "gate_results.json"
        gate_path.write_text(
            json.dumps(
                [
                    {
                        "gate_id": 0,
                        "name": "Context Sufficiency",
                        "status": "pass",
                        "checked_items": [{"item": "context_decision", "result": "pass"}],
                        "passed_items": ["context_decision"],
                        "failed_items": [],
                        "warnings": [],
                        "evidence": ["context_decision: allow_rag"],
                        "file_paths": [],
                        "message": "Context sufficient",
                    },
                    {
                        "gate_id": 5,
                        "name": "Static Check",
                        "status": "fail",
                        "checked_items": [{"item": "code structure", "result": "fail"}],
                        "passed_items": [],
                        "failed_items": ["Missing CMakeLists.txt"],
                        "warnings": [],
                        "evidence": [],
                        "file_paths": [],
                        "message": "Missing CMakeLists.txt",
                    },
                ]
            )
        )

        state = {
            "job_id": "test_job",
            "user_query": "test",
            "execution_mode": "strict",
            "validation_status": "failed",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": ["Static Check"],
            "errors": [],
            "g4_model_ir_path": "",
            "gate_results_path": str(gate_path),
        }
        result = await generate_final_report(state)
        report = Path(result["final_report_path"]).read_text()

        # Must use correct field names: 'name' not 'gate_name', 'status' not 'severity'
        assert "Context Sufficiency" in report, "Report must show gate name from 'name' field"
        assert "Static Check" in report, "Report must show failed gate name"
        # Must show status, not '?'
        assert "❌ fail" in report, "Report must show gate status from 'status' field"
        assert "✅ pass" in report, "Report must show passed gate status"
        # Must show passed/failed counts in the table
        assert "Missing CMakeLists.txt" in report

    async def test_report_failed_status(self, temp_workspace: Path) -> None:
        """failed validation status should not be marked as verified."""
        state = {
            "job_id": "test_job",
            "user_query": "test",
            "execution_mode": "strict",
            "validation_status": "failed",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": [],
            "errors": [],
            "g4_model_ir_path": "",
            "gate_results_path": "",
        }
        result = await generate_final_report(state)
        assert result["verified"] is False
        report = Path(result["final_report_path"]).read_text()
        assert "failed" in report
        assert "passed" not in report or "failed" in report
