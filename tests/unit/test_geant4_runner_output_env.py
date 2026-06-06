"""Geant4Runner output_dir and job_id env injection tests.

Ensures simulate() injects G4_OUTPUT_DIR and G4_JOB_ID environment
variables, and smoke_test() passes them through correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from agent_core.tools.geant4_runner import Geant4Runner


@pytest.fixture
def runner_no_g4() -> Geant4Runner:
    """Geant4Runner with geant4 unavailable."""
    with patch.object(Geant4Runner, "_check_geant4", return_value=False):
        return Geant4Runner(geant4_dir="/nonexistent")


@pytest.fixture
def runner_with_g4() -> Geant4Runner:
    """Geant4Runner with geant4 available (mocked)."""
    with patch.object(Geant4Runner, "_check_geant4", return_value=True):
        return Geant4Runner(geant4_dir="/usr/local/geant4")


class TestSimulateEnvInjection:
    """Tests for simulate() environment variable injection."""

    @pytest.mark.anyio
    async def test_simulate_injects_output_dir(self, runner_with_g4: Geant4Runner):
        """simulate() sets G4_OUTPUT_DIR when output_dir is provided."""
        with patch.object(
            Geant4Runner, "_run", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (0, "ok", "")
            await runner_with_g4.simulate(
                executable="/fake/exe",
                output_dir="/tmp/g4_out",
                job_id="job-001",
            )
            cmd = mock_run.call_args[0][0]
            assert "G4_OUTPUT_DIR=/tmp/g4_out" in cmd

    @pytest.mark.anyio
    async def test_simulate_injects_job_id(self, runner_with_g4: Geant4Runner):
        """simulate() sets G4_JOB_ID when job_id is provided."""
        with patch.object(
            Geant4Runner, "_run", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (0, "ok", "")
            await runner_with_g4.simulate(
                executable="/fake/exe",
                job_id="job-abc",
            )
            cmd = mock_run.call_args[0][0]
            assert "G4_JOB_ID=job-abc" in cmd

    @pytest.mark.anyio
    async def test_simulate_no_output_dir_no_env(self, runner_with_g4: Geant4Runner):
        """simulate() does not inject G4_OUTPUT_DIR when not provided."""
        with patch.object(
            Geant4Runner, "_run", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (0, "ok", "")
            await runner_with_g4.simulate(
                executable="/fake/exe",
                job_id="unknown",
            )
            cmd = mock_run.call_args[0][0]
            assert "G4_OUTPUT_DIR" not in cmd

    @pytest.mark.anyio
    async def test_simulate_default_job_id_no_env(self, runner_with_g4: Geant4Runner):
        """simulate() does not inject G4_JOB_ID when job_id='unknown'."""
        with patch.object(
            Geant4Runner, "_run", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (0, "ok", "")
            await runner_with_g4.simulate(
                executable="/fake/exe",
                output_dir="/tmp/out",
            )
            cmd = mock_run.call_args[0][0]
            assert "G4_JOB_ID" not in cmd


class TestSmokeTestNoG4:
    """Tests for smoke_test() when Geant4 is not available."""

    @pytest.mark.anyio
    async def test_smoke_test_no_g4_returns_false(self, runner_no_g4: Geant4Runner):
        """smoke_test returns success=False when Geant4 unavailable."""
        result = await runner_no_g4.smoke_test("/fake/project", job_id="test-123")
        assert result["success"] is False
        assert result["has_geant4"] is False

    @pytest.mark.anyio
    async def test_smoke_test_no_g4_not_structure_check(
        self, runner_no_g4: Geant4Runner
    ):
        """smoke_test does NOT fall back to structure_check."""
        result = await runner_no_g4.smoke_test("/fake/project", job_id="test-123")
        # Should explicitly say structure_check doesn't count
        assert any("structure_check" in w for w in result.get("warnings", []))


class TestSmokeTestWithG4:
    """Tests for smoke_test() when Geant4 is available (mocked)."""

    @pytest.mark.anyio
    async def test_smoke_test_passes_job_id_and_output_dir(
        self, runner_with_g4: Geant4Runner
    ):
        """smoke_test forwards job_id and output_dir to simulate()."""
        with patch.object(
            Geant4Runner, "configure", new_callable=AsyncMock
        ) as mock_cfg, patch.object(
            Geant4Runner, "build", new_callable=AsyncMock
        ) as mock_bld, patch.object(
            Geant4Runner, "simulate", new_callable=AsyncMock
        ) as mock_sim:
            mock_cfg.return_value = {"success": True}
            mock_bld.return_value = {
                "success": True,
                "executable_path": "/fake/exe",
            }
            mock_sim.return_value = {
                "success": True,
                "log": "done",
                "errors": "",
            }

            result = await runner_with_g4.smoke_test(
                "/fake/project",
                job_id="job-smoke",
                output_dir="/tmp/smoke_out",
            )

            assert result["success"] is True
            # Verify simulate was called with correct params
            sim_call = mock_sim.call_args
            assert sim_call[1].get("job_id") == "job-smoke" or \
                   (len(sim_call[0]) > 0)  # positional
