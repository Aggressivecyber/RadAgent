"""Tests for centralized workspace path management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from agent_core.config.workspace import (
    ensure_job_dirs,
    get_job_dir,
    get_output_dir,
    get_stage_dir,
    get_workspace_root,
)


class TestGetWorkspaceRoot:
    """Test get_workspace_root() reads env and detects nesting."""

    def test_default_returns_simulation_workspace(self) -> None:
        root = get_workspace_root()
        assert root == Path("simulation_workspace")

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", "/tmp/test_workspace")
        root = get_workspace_root()
        assert root == Path("/tmp/test_workspace")

    def test_nested_detection_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "RADAGENT_WORKSPACE_ROOT", "/tmp/simulation_workspace/simulation_workspace"
        )
        with pytest.raises(ValueError, match="Nested workspace detected"):
            get_workspace_root()


class TestGetJobDir:
    """Test job directory path construction."""

    def test_returns_correct_path(self) -> None:
        job_dir = get_job_dir("job_123")
        assert job_dir == Path("simulation_workspace") / "jobs" / "job_123"

    def test_with_custom_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", "/data/ws")
        job_dir = get_job_dir("job_abc")
        assert job_dir == Path("/data/ws") / "jobs" / "job_abc"


class TestGetStageDir:
    """Test stage directory path construction."""

    def test_geant4_stage(self) -> None:
        stage = get_stage_dir("job_1", "05_geant4")
        assert stage == Path("simulation_workspace/jobs/job_1/05_geant4")

    def test_output_stage(self) -> None:
        stage = get_stage_dir("job_1", "08_data_packages")
        assert stage == Path("simulation_workspace/jobs/job_1/08_data_packages")


class TestGetOutputDir:
    """Test canonical G4 output directory."""

    def test_returns_g4_output_package_path(self) -> None:
        out = get_output_dir("job_1")
        expected = Path("simulation_workspace/jobs/job_1/08_data_packages/g4_output_package")
        assert out == expected


class TestEnsureJobDirs:
    """Test job directory creation."""

    def test_creates_all_stage_dirs(self, tmp_path: Path) -> None:
        with patch(
            "agent_core.config.workspace.get_workspace_root", return_value=tmp_path
        ):
            job_dir = ensure_job_dirs("test_job")

        assert job_dir == tmp_path / "jobs" / "test_job"
        assert (job_dir / "00_request").is_dir()
        assert (job_dir / "01_context").is_dir()
        assert (job_dir / "05_geant4/src").is_dir()
        assert (job_dir / "05_geant4/include").is_dir()
        assert (job_dir / "08_data_packages/g4_output_package").is_dir()
        assert (job_dir / "10_report").is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        with patch(
            "agent_core.config.workspace.get_workspace_root", return_value=tmp_path
        ):
            ensure_job_dirs("job_x")
            ensure_job_dirs("job_x")  # Second call should not raise
