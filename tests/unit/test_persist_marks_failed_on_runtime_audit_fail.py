"""Runtime audit failures should block for repair continuation, not silently pass."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestPersistMarksFailedOnRuntimeAuditFail:
    """Verify persist_codegen_output does not finalize repairable audit failures."""

    @pytest.mark.asyncio
    async def test_failed_status_on_runtime_audit_fail(self, workspace: Path) -> None:
        """Runtime execution audit failures should request continuation approval."""
        state = {
            "job_id": "test_runtime_audit_fail",
            "run_mode": "strict",
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/Test.cc",
                        "new_content": "// test",
                        "module_name": "simulation_core",
                    },
                    {
                        "path": "src/Beam.cc",
                        "new_content": "// test",
                        "module_name": "beam_physics",
                    },
                    {
                        "path": "main.cc",
                        "new_content": "// test",
                        "module_name": "runtime_app",
                    },
                ],
            },
            "module_results": {
                "simulation_core": {"status": "generated"},
                "beam_physics": {"status": "generated"},
                "runtime_app": {"status": "generated"},
            },
            "global_integration_agent_report": {"status": "passed"},
            "runtime_execution_audit": {
                "status": "fail",
                "blocking_errors": ["missing event_table.csv"],
            },
            "runtime_audit_repair_attempts": 2,
        }

        result = await persist_codegen_output_node(state)

        assert result["g4_codegen_status"] == "needs_user_input"
        assert result["repair_continuation_status"] == "pending"
        assert result["repair_continuation_request"]["status"] == "pending"
        assert (
            result["repair_continuation_request"]["reason"]
            == "runtime_execution_audit_repair_budget_exhausted"
        )

    @pytest.mark.asyncio
    async def test_failed_status_when_module_coverage_missing(self, workspace: Path) -> None:
        """A patch is not enough without all coarse module agents."""
        state = {
            "job_id": "test_all_pass",
            "run_mode": "strict",
            "proposed_patch": {
                "changed_files": [
                    {"path": "src/Test.cc", "new_content": "// test"},
                ],
            },
        }

        result = await persist_codegen_output_node(state)

        assert result["g4_codegen_status"] == "failed"

    @pytest.mark.asyncio
    async def test_physics_review_user_input_does_not_write_post_codegen_confirmation(
        self,
        workspace: Path,
    ) -> None:
        """Post-codegen physics review must not reopen human confirmation."""
        state = {
            "job_id": "test_physics_user_input",
            "run_mode": "strict",
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/DetectorConstruction.cc",
                        "new_content": "// test",
                        "module_name": "simulation_core",
                    }
                ],
                "metadata": {"source": "geant4_project_agent"},
            },
            "global_integration_agent_report": {"status": "passed"},
            "runtime_execution_audit": {"status": "pass"},
            "physics_quality_review": {
                "status": "needs_user_input",
                "routing_recommendation": "request_user_input",
                "needs_user_input": [
                    {
                        "target": "materials[1]",
                        "message": (
                            "Get user confirmation on tracker material: "
                            "plastic scintillator or silicon."
                        ),
                    },
                    {
                        "target": "G4ModelIR",
                        "message": "Update G4ModelIR metadata after the user decides.",
                    },
                ],
                "required_fixes": [],
            },
        }

        result = await persist_codegen_output_node(state)

        assert result["g4_codegen_status"] == "failed"
        assert "human_confirmation_required" not in result
        assert "confirmation_status" not in result
        assert "confirmation_request_path" not in result
        assert result.get("repair_continuation_request", {}) == {}

        human_dir = workspace / "jobs" / "test_physics_user_input" / "04_human_confirmation"
        assert not human_dir.exists()
