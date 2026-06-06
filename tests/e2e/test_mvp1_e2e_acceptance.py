"""MVP-1 E2E test — acceptance mode (requires Geant4 environment).

Runs the full LangGraph pipeline with REAL LLM, RAG, and Geant4.
Only executes on self-hosted runners with Geant4 installed and OPENAI_API_KEY set.

Validates that:
- Pipeline completes (may take several minutes)
- Report contains "**MVP-1: PASSED**" or "**MVP-1: FAILED**" (never "NOT VERIFIED")
- Critical gates (6, 8, 9, 11) are never skipped
- All 5 required Geant4 output files are present
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from agent_core.graph.graph_builder import compile_graph
from agent_core.tools.geant4_runner import Geant4Runner

pytestmark = [pytest.mark.e2e, pytest.mark.requires_geant4, pytest.mark.slow]


def _geant4_available() -> bool:
    """Check if Geant4 is installed on this machine."""
    try:
        return Geant4Runner().geant4_available
    except Exception:
        return False


def _api_key_set() -> bool:
    """Check if OPENAI_API_KEY is configured."""
    return bool(os.environ.get("OPENAI_API_KEY"))


# Skip entire module if prerequisites not met
pytestmark.append(
    pytest.mark.skipif(
        not _geant4_available(),
        reason="Geant4 not available -- run on self-hosted runner",
    )
)
pytestmark.append(
    pytest.mark.skipif(not _api_key_set(), reason="OPENAI_API_KEY not set")
)

E2E_QUERY = "模拟 10 MeV 质子垂直入射 300 微米硅片，输出能量沉积和剂量分布。"

_REQUIRED_G4_OUTPUT_FILES = [
    "g4_summary.json",
    "edep_3d.csv",
    "dose_3d.csv",
    "event_table.csv",
    "provenance.json",
]


class TestMvp1E2EAcceptance:
    """Acceptance-mode E2E tests — full pipeline with real Geant4."""

    async def test_full_pipeline_acceptance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Run the complete pipeline with real Geant4/LLM/RAG infrastructure.

        The pipeline is invoked with execution_mode=mvp1_acceptance. The
        prepare_local_rag_workspace node will detect Geant4 and set the mode
        correctly. All critical gates must pass (no skips allowed).
        """
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        (tmp_path / "jobs").mkdir()

        initial_state = {
            "user_query": E2E_QUERY,
            "job_id": "",
            "errors": [],
            "retry_count": 0,
            "max_retries_reached": False,
            "execution_mode": "mvp1_acceptance",
            "skipped_gates": [],
        }

        graph = compile_graph()
        result = await graph.ainvoke(initial_state, config={"recursion_limit": 50})

        assert result is not None, "Pipeline returned None"

        report = result.get("final_report", "")
        assert isinstance(report, str) and len(report) > 0, "final_report is empty"

        # Must have a clear verification status (NOT "NOT VERIFIED")
        has_passed = "**MVP-1: PASSED**" in report
        has_failed = "**MVP-1: FAILED**" in report
        assert has_passed or has_failed, (
            "Report must contain either '**MVP-1: PASSED**' or '**MVP-1: FAILED**'"
        )
        assert "**MVP-1: NOT VERIFIED**" not in report, (
            "Report must NOT contain 'NOT VERIFIED' in acceptance mode"
        )

        # Gate results must have 12 entries
        gate_results = result.get("gate_results", [])
        assert isinstance(gate_results, list) and len(gate_results) == 12, (
            f"Expected 12 gate results, got {len(gate_results)}"
        )

        # Job directory must exist
        job_id = result.get("job_id", "")
        job_dir = tmp_path / "jobs" / job_id
        assert job_dir.is_dir(), f"Job directory {job_dir} should exist"

        # Report file must exist on disk
        report_file = job_dir / "10_report" / "final_report.md"
        assert report_file.is_file(), "Report file should be saved to disk"

    async def test_acceptance_no_critical_gates_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Critical gates 6/8/9/11 must never be skipped in acceptance mode."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        (tmp_path / "jobs").mkdir()

        initial_state = {
            "user_query": E2E_QUERY,
            "job_id": "",
            "errors": [],
            "retry_count": 0,
            "max_retries_reached": False,
            "execution_mode": "mvp1_acceptance",
            "skipped_gates": [],
        }

        graph = compile_graph()
        result = await graph.ainvoke(initial_state, config={"recursion_limit": 50})

        gate_results = result.get("gate_results", [])
        critical_skipped = [
            g for g in gate_results
            if g.get("severity") == "skipped" and g.get("gate_id") in (6, 8, 9, 11)
        ]
        assert len(critical_skipped) == 0, (
            f"Critical gates should not be skipped in acceptance mode. "
            f"Skipped: {[g.get('gate_id') for g in critical_skipped]}"
        )

    async def test_acceptance_g4_output_complete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All 5 required Geant4 output files must be present."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        (tmp_path / "jobs").mkdir()

        initial_state = {
            "user_query": E2E_QUERY,
            "job_id": "",
            "errors": [],
            "retry_count": 0,
            "max_retries_reached": False,
            "execution_mode": "mvp1_acceptance",
            "skipped_gates": [],
        }

        graph = compile_graph()
        result = await graph.ainvoke(initial_state, config={"recursion_limit": 50})

        # Only check output files if pipeline reached the point of generating them
        g4_output = result.get("g4_output_package", {})
        if g4_output:
            for fname in _REQUIRED_G4_OUTPUT_FILES:
                info = g4_output.get(fname, {})
                assert info.get("exists", False), (
                    f"Required output file {fname} must exist"
                )
        else:
            # If no output package, report must explain why
            report = result.get("final_report", "")
            assert "**MVP-1: FAILED**" in report, (
                "If no g4_output_package, report must explain failure"
            )

    async def test_acceptance_report_has_clear_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Report must have exactly one clear MVP-1 status (PASSED or FAILED)."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        (tmp_path / "jobs").mkdir()

        initial_state = {
            "user_query": E2E_QUERY,
            "job_id": "",
            "errors": [],
            "retry_count": 0,
            "max_retries_reached": False,
            "execution_mode": "mvp1_acceptance",
            "skipped_gates": [],
        }

        graph = compile_graph()
        result = await graph.ainvoke(initial_state, config={"recursion_limit": 50})

        report = result.get("final_report", "")
        statuses = [
            s for s in ["**MVP-1: PASSED**", "**MVP-1: FAILED**", "**MVP-1: NOT VERIFIED**"]
            if s in report
        ]
        assert len(statuses) == 1, (
            f"Report must have exactly one MVP-1 status, found: {statuses}"
        )
        assert "**MVP-1: NOT VERIFIED**" not in statuses, (
            "Acceptance mode must never produce NOT VERIFIED"
        )
