"""MVP-1 E2E test — dev mode (no Geant4 environment).

Runs the full LangGraph pipeline with mocked LLM, RAG, and Geant4 dependencies.
Validates that:
- Pipeline completes without unhandled exceptions
- Report contains "**MVP-1: NOT VERIFIED**"
- Report does NOT contain "MVP-1: PASSED" or "MVP-1: FAILED"
- Critical gates (6, 8, 9, 11) are properly skipped
- Workspace stays isolated in tmp_path
- No real Geant4 output files are produced
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest
from agent_core.graph.graph_builder import compile_graph

from .conftest import get_e2e_patches

pytestmark = pytest.mark.e2e


async def _run_dev_pipeline(e2e_workspace: Path, e2e_initial_state: dict) -> dict:
    """Run the full pipeline with dev-mode mocks and return the result.

    Handles all patch context managers so each test method stays clean.
    """
    patches = get_e2e_patches(e2e_workspace)
    with ExitStack() as stack:
        for target, mock_obj in patches:
            stack.enter_context(patch(target, mock_obj))
        graph = compile_graph()
        result = await graph.ainvoke(
            e2e_initial_state,
            config={"recursion_limit": 50},
        )
    return result


class TestMvp1E2EDev:
    """Dev-mode E2E tests — full pipeline with mocked dependencies."""

    async def test_full_pipeline_dev_mode(
        self,
        e2e_workspace: Path,
        e2e_initial_state: dict,
    ) -> None:
        """Run the complete LangGraph pipeline in dev mode with mocks.

        This is the primary E2E test: compile the graph, invoke it with
        mocked LLM/RAG/Geant4, and verify the full pipeline produces the
        expected report with NOT VERIFIED status.
        """
        result = await _run_dev_pipeline(e2e_workspace, e2e_initial_state)

        # --- Core assertions ---
        assert result is not None, "Pipeline returned None"

        job_id = result.get("job_id", "")
        assert isinstance(job_id, str) and job_id.startswith("job_"), (
            f"job_id should start with 'job_', got: {job_id!r}"
        )

        # Report must exist and contain NOT VERIFIED
        report = result.get("final_report", "")
        assert isinstance(report, str) and len(report) > 0, "final_report is empty"
        assert "**MVP-1: NOT VERIFIED**" in report, (
            "Report must contain '**MVP-1: NOT VERIFIED**' in dev mode"
        )
        assert "**MVP-1: PASSED**" not in report, (
            "Report must NOT contain '**MVP-1: PASSED**' in dev mode"
        )
        assert "**MVP-1: FAILED**" not in report, (
            "Report must NOT contain '**MVP-1: FAILED**' in dev mode"
        )

        # Execution mode must be dev
        assert result.get("execution_mode") == "dev_no_geant4_env", (
            f"execution_mode should be 'dev_no_geant4_env', "
            f"got: {result.get('execution_mode')!r}"
        )

        # Task spec must have geant4 scope
        task_spec = result.get("task_spec", {})
        scope = task_spec.get("simulation_scope", [])
        assert "geant4" in scope, f"simulation_scope should include 'geant4', got: {scope}"

        # Simulation IR must have g4_config
        sim_ir = result.get("simulation_ir", {})
        assert sim_ir.get("g4_config") is not None, "simulation_ir should have g4_config"

        # Gate results must have 12 entries
        gate_results = result.get("gate_results", [])
        assert isinstance(gate_results, list) and len(gate_results) == 12, (
            f"Expected 12 gate results, got {len(gate_results)}"
        )

        # Job directory must exist with proper structure
        job_dir = e2e_workspace / "jobs" / job_id
        assert job_dir.is_dir(), f"Job directory {job_dir} should exist"

        expected_stages = [
            "00_request", "01_context", "02_task_spec", "03_simulation_ir",
            "04_generated_code", "05_geant4", "09_validation", "10_report",
        ]
        for stage in expected_stages:
            assert (job_dir / stage).is_dir(), f"Stage directory {stage} should exist"

        # Report file must exist on disk
        report_file = job_dir / "10_report" / "final_report.md"
        assert report_file.is_file(), "Report file should be saved to disk"

    async def test_dev_report_contains_not_verified(
        self,
        e2e_workspace: Path,
        e2e_initial_state: dict,
    ) -> None:
        """Verify the report file on disk has the NOT VERIFIED marker."""
        result = await _run_dev_pipeline(e2e_workspace, e2e_initial_state)

        job_id = result.get("job_id", "")
        report_file = e2e_workspace / "jobs" / job_id / "10_report" / "final_report.md"
        assert report_file.is_file()
        content = report_file.read_text()
        assert "NOT VERIFIED" in content
        assert "NOT MVP-1 VERIFIED" in content

    async def test_dev_skipped_gates_are_critical(
        self,
        e2e_workspace: Path,
        e2e_initial_state: dict,
    ) -> None:
        """Verify that skipped gates are the critical ones (6, 8, 9, 11)."""
        result = await _run_dev_pipeline(e2e_workspace, e2e_initial_state)

        gate_results = result.get("gate_results", [])
        skipped_ids = {
            g.get("gate_id") for g in gate_results if g.get("severity") == "skipped"
        }
        critical_ids = {6, 8, 9, 11}

        # All skipped gates should be in the critical set (may also include 7)
        assert skipped_ids.issubset(critical_ids | {7}), (
            f"Skipped gate IDs should be subset of critical gates {{6,8,9,11,7}}, "
            f"got: {skipped_ids}"
        )

        # At least gates 6 and 9 (Geant4-dependent) should be skipped
        assert {6, 9}.issubset(skipped_ids), (
            f"Gates 6 and 9 (Geant4-dependent) should be skipped, "
            f"skipped IDs: {skipped_ids}"
        )

    async def test_dev_no_real_g4_output(
        self,
        e2e_workspace: Path,
        e2e_initial_state: dict,
    ) -> None:
        """Verify no real Geant4 output files in the output directory."""
        result = await _run_dev_pipeline(e2e_workspace, e2e_initial_state)

        job_id = result.get("job_id", "")
        output_dir = (
            e2e_workspace / "jobs" / job_id / "08_data_packages" / "g4_output_package"
        )

        # These files should NOT exist (no real Geant4 run)
        real_output_files = ["edep_3d.csv", "dose_3d.csv", "event_table.csv"]
        for fname in real_output_files:
            if output_dir.is_dir():
                assert not (output_dir / fname).is_file(), (
                    f"Real Geant4 output file {fname} should not exist in dev mode"
                )

    async def test_dev_workspace_stays_in_tmp(
        self,
        e2e_workspace: Path,
        e2e_initial_state: dict,
    ) -> None:
        """Verify workspace stays in tmp_path and does not leak to project dir."""
        result = await _run_dev_pipeline(e2e_workspace, e2e_initial_state)

        job_id = result.get("job_id", "")
        job_dir = e2e_workspace / "jobs" / job_id

        # Job dir must be under tmp_path (e2e_workspace)
        assert str(job_dir).startswith(str(e2e_workspace)), (
            f"Job directory {job_dir} must be under tmp_path {e2e_workspace}"
        )

        # Project workspace should not have this job
        project_ws = Path(__file__).resolve().parents[2] / "simulation_workspace"
        project_job = project_ws / "jobs" / job_id
        assert not project_job.is_dir(), (
            f"Job directory leaked to project workspace: {project_job}"
        )
