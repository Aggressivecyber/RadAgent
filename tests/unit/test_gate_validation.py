"""Tests for gate validation — Gate 0 tri-state, Gate 6 dev/MVP1, Gate 9 files."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from agent_core.nodes.run_gate_checks import (
    _check_execution_mode_gate,
    run_gate_checks,
)


def _valid_patch() -> dict:
    """Return a patch that passes PatchValidator (all required fields)."""
    return {
        "patch_id": "p1",
        "job_id": "test-gates",
        "description": "test patch",
        "change_type": "create",
        "risk_level": "low",
        "changed_files": [
            {
                "path": "05_geant4/src/main.cc",
                "new_content": "int main() { return 0; }",
                "zone": "green",
            },
        ],
        "test_plan": "compile check",
        "expected_outputs": {},
    }


def _make_state(
    job_id: str = "test-gates",
    context_decision: str = "allow_rag",
    rag_score: float = 0.95,
    execution_mode: str = "dev_no_geant4_env",
    patch_data: dict | None = None,
    task_spec: dict | None = None,
    sim_ir: dict | None = None,
    context_report: dict | None = None,
    web_search_available: bool = False,
) -> dict:
    """Build a minimal state for gate checking."""
    return {
        "job_id": job_id,
        "context_decision": context_decision,
        "rag_sufficiency_score": rag_score,
        "execution_mode": execution_mode,
        "proposed_patch": patch_data or _valid_patch(),
        "task_spec": task_spec or {
            "simulation_scope": ["geant4"],
            "particle": {"type": "proton", "energy_MeV": 10.0},
        },
        "simulation_ir": sim_ir or {
            "g4_config": {
                "particle_source": {"type": "proton", "energy": "10 MeV"},
                "geometry": {"detector": "silicon"},
            },
        },
        "context_sufficiency_report": context_report or {},
        "web_search_available": web_search_available,
    }


def _setup_job_dirs(tmp_path: Path) -> tuple[list, Path]:
    """Create job sub-directories and return (patches, job_dir).

    run_gate_checks writes to job_dir/09_validation/gate_results.json and
    needs job_dir/05_geant4 for Gate 5.  We pre-create all sub-dirs.
    """
    (tmp_path / "09_validation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "05_geant4" / "src").mkdir(parents=True, exist_ok=True)
    return (
        [
            patch(
                "agent_core.nodes.run_gate_checks.get_output_dir",
                return_value=tmp_path,
            ),
            patch(
                "agent_core.nodes.run_gate_checks.get_job_dir",
                return_value=tmp_path,
            ),
        ],
        tmp_path,
    )


class TestExecutionModeGate:
    """_check_execution_mode_gate enforces MVP-1 no-skip rule."""

    def test_dev_mode_skip_allowed(self) -> None:
        result = _check_execution_mode_gate(
            6, False, "skipped", "G4 not available", None, "dev_no_geant4_env",
        )
        assert result["severity"] == "skipped"
        assert result["passed"] is False

    def test_mvp1_mode_critical_skip_converted_to_fail(self) -> None:
        result = _check_execution_mode_gate(
            6, False, "skipped", "G4 not available", None, "mvp1_acceptance",
        )
        assert result["severity"] == "fail"
        assert result["passed"] is False
        assert "cannot be skipped" in result["message"]

    def test_mvp1_non_critical_skip_passes(self) -> None:
        result = _check_execution_mode_gate(
            7, True, "skipped", "No benchmark", None, "mvp1_acceptance",
        )
        assert result["severity"] == "skipped"
        assert result["passed"] is True

    def test_mvp1_fail_stays_fail(self) -> None:
        result = _check_execution_mode_gate(
            6, False, "fail", "Build error", "write_fix_patch", "mvp1_acceptance",
        )
        assert result["severity"] == "fail"


class TestGate0TriState:
    """Gate 0 respects context_decision tri-state."""

    @pytest.mark.asyncio
    async def test_allow_rag_passes(self, tmp_path: Path) -> None:
        state = _make_state(context_decision="allow_rag", rag_score=0.95)
        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with p1, p2:
            result = await run_gate_checks(state)

        gate0 = result["gate_results"][0]
        assert gate0["passed"] is True
        assert gate0["severity"] == "pass"

    @pytest.mark.asyncio
    async def test_allow_with_web_supplement_warns(self, tmp_path: Path) -> None:
        state = _make_state(
            context_decision="allow_with_web_supplement",
            rag_score=0.70,
            context_report={"web_urls": ["https://example.com"]},
        )
        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with p1, p2:
            result = await run_gate_checks(state)

        gate0 = result["gate_results"][0]
        assert gate0["passed"] is True
        assert gate0["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_block_no_context_blocks(self, tmp_path: Path) -> None:
        state = _make_state(
            context_decision="block_no_context",
            rag_score=0.20,
        )
        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with p1, p2:
            result = await run_gate_checks(state)

        gate0 = result["gate_results"][0]
        assert gate0["passed"] is False
        assert gate0["severity"] == "block"


class TestGate6BuildParse:
    """Gate 6: Build/Parse — dev mode skips, MVP1 fails without G4."""

    @pytest.mark.asyncio
    async def test_dev_mode_skips_when_no_g4(self, tmp_path: Path) -> None:
        state = _make_state(execution_mode="dev_no_geant4_env")
        mock_runner = MagicMock()
        mock_runner.geant4_available = False

        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with (
            patch(
                "agent_core.tools.geant4_runner.Geant4Runner",
                return_value=mock_runner,
                create=True,
            ),
            p1,
            p2,
        ):
            result = await run_gate_checks(state)

        gate6 = result["gate_results"][6]
        assert gate6["severity"] == "skipped"
        assert gate6["passed"] is False
        assert any(s["gate_id"] == 6 for s in result["skipped_gates"])

    @pytest.mark.asyncio
    async def test_mvp1_fails_when_no_g4(self, tmp_path: Path) -> None:
        state = _make_state(execution_mode="mvp1_acceptance")
        mock_runner = MagicMock()
        mock_runner.geant4_available = False

        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with (
            patch(
                "agent_core.tools.geant4_runner.Geant4Runner",
                return_value=mock_runner,
                create=True,
            ),
            p1,
            p2,
        ):
            result = await run_gate_checks(state)

        gate6 = result["gate_results"][6]
        assert gate6["severity"] == "fail"
        assert gate6["passed"] is False
        assert "MVP1" in gate6["message"]


class TestGate9FileChecks:
    """Gate 9: Smoke simulation — file existence and content validation."""

    @pytest.mark.asyncio
    async def test_dev_mode_skips_when_no_g4(self, tmp_path: Path) -> None:
        state = _make_state(
            execution_mode="dev_no_geant4_env",
            job_id="g9-test",
        )
        mock_runner = MagicMock()
        mock_runner.geant4_available = False

        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with (
            patch(
                "agent_core.tools.geant4_runner.Geant4Runner",
                return_value=mock_runner,
                create=True,
            ),
            p1,
            p2,
        ):
            result = await run_gate_checks(state)

        gate9 = result["gate_results"][9]
        assert gate9["severity"] == "skipped"

    @pytest.mark.asyncio
    async def test_mvp1_fails_when_no_g4(self, tmp_path: Path) -> None:
        state = _make_state(
            execution_mode="mvp1_acceptance",
            job_id="g9-mvp1",
        )
        mock_runner = MagicMock()
        mock_runner.geant4_available = False

        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with (
            patch(
                "agent_core.tools.geant4_runner.Geant4Runner",
                return_value=mock_runner,
                create=True,
            ),
            p1,
            p2,
        ):
            result = await run_gate_checks(state)

        gate9 = result["gate_results"][9]
        assert gate9["severity"] == "fail"
        assert gate9["passed"] is False

    @pytest.mark.asyncio
    async def test_passes_when_all_files_present(self, tmp_path: Path) -> None:
        """Gate 9 passes when all required files exist with valid content."""
        job_id = "g9-pass"
        state = _make_state(
            execution_mode="dev_no_geant4_env",
            job_id=job_id,
        )

        # Create required files
        (tmp_path / "g4_summary.json").write_text("{}")
        (tmp_path / "edep_3d.csv").write_text("x,y,z,edep\n1,2,3,0.5\n")
        (tmp_path / "dose_3d.csv").write_text("x,y,z,dose\n1,2,3,0.01\n")
        (tmp_path / "event_table.csv").write_text("event,edep\n1,0.5\n")
        (tmp_path / "provenance.json").write_text(
            json.dumps({"simulation_id": job_id})
        )

        mock_runner = MagicMock()
        mock_runner.geant4_available = True

        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with (
            patch(
                "agent_core.tools.geant4_runner.Geant4Runner",
                return_value=mock_runner,
                create=True,
            ),
            p1,
            p2,
        ):
            result = await run_gate_checks(state)

        gate9 = result["gate_results"][9]
        assert gate9["passed"] is True
        assert gate9["severity"] == "pass"

    @pytest.mark.asyncio
    async def test_fails_when_event_table_empty(self, tmp_path: Path) -> None:
        """Gate 9 fails when event_table.csv has no data rows."""
        job_id = "g9-empty"
        state = _make_state(job_id=job_id)

        (tmp_path / "g4_summary.json").write_text("{}")
        (tmp_path / "edep_3d.csv").write_text("x,y\n1,2\n")
        (tmp_path / "dose_3d.csv").write_text("x,y\n1,2\n")
        (tmp_path / "event_table.csv").write_text("event,edep\n")  # header only
        (tmp_path / "provenance.json").write_text(
            json.dumps({"simulation_id": job_id})
        )

        mock_runner = MagicMock()
        mock_runner.geant4_available = True

        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with (
            patch(
                "agent_core.tools.geant4_runner.Geant4Runner",
                return_value=mock_runner,
                create=True,
            ),
            p1,
            p2,
        ):
            result = await run_gate_checks(state)

        gate9 = result["gate_results"][9]
        assert gate9["passed"] is False
        assert "event_table" in gate9["message"]

    @pytest.mark.asyncio
    async def test_fails_when_provenance_id_mismatch(self, tmp_path: Path) -> None:
        """Gate 9 fails when provenance.simulation_id != job_id."""
        state = _make_state(job_id="correct-id")

        (tmp_path / "g4_summary.json").write_text("{}")
        (tmp_path / "edep_3d.csv").write_text("x\n1\n")
        (tmp_path / "dose_3d.csv").write_text("x\n1\n")
        (tmp_path / "event_table.csv").write_text("event\n1\n")
        (tmp_path / "provenance.json").write_text(
            json.dumps({"simulation_id": "wrong-id"})
        )

        mock_runner = MagicMock()
        mock_runner.geant4_available = True

        (p1, p2), _ = _setup_job_dirs(tmp_path)
        with (
            patch(
                "agent_core.tools.geant4_runner.Geant4Runner",
                return_value=mock_runner,
                create=True,
            ),
            p1,
            p2,
        ):
            result = await run_gate_checks(state)

        gate9 = result["gate_results"][9]
        assert gate9["passed"] is False
        assert (
            "provenance" in gate9["message"].lower()
            or "mismatch" in gate9["message"].lower()
        )
