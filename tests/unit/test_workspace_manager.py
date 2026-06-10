"""Tests for agent_core.workspace module — WorkspaceManager, JobWorkspace, paths."""

from pathlib import Path

import pytest
from agent_core.workspace.manager import JobWorkspace, WorkspaceManager
from agent_core.workspace.paths import (
    ALL_STAGES,
    GEANT4_PROJECT_DIRNAME,
    GEANT4_SUBDIRS,
    HC_CONFIRMATION_RECORD,
    STAGE_CODEGEN,
    STAGE_HUMAN_CONFIRMATION,
    STAGE_INPUT,
    STAGE_PATCH,
)

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def ws(tmp_path: Path) -> WorkspaceManager:
    """Create a WorkspaceManager rooted in a temp directory."""
    return WorkspaceManager(root=tmp_path)


@pytest.fixture
def job(ws: WorkspaceManager) -> JobWorkspace:
    """Create a job workspace with all standard directories."""
    return ws.create_job("test-job-001")


# ── WorkspaceManager tests ───────────────────────────────────────────────


class TestWorkspaceManager:
    def test_create_job_returns_job_workspace(self, ws: WorkspaceManager) -> None:
        job = ws.create_job("abc")
        assert isinstance(job, JobWorkspace)
        assert job.job_id == "abc"

    def test_create_job_makes_directories(self, ws: WorkspaceManager) -> None:
        ws.create_job("abc")
        job_dir = ws.job_dir("abc")
        assert job_dir.exists()
        for stage in ALL_STAGES:
            assert (job_dir / stage).is_dir(), f"missing {stage}"

    def test_job_dir_path(self, ws: WorkspaceManager) -> None:
        expected = ws.root / "jobs" / "my-job"
        assert ws.job_dir("my-job") == expected

    def test_job_exists(self, ws: WorkspaceManager) -> None:
        assert not ws.job_exists("nope")
        ws.create_job("yep")
        assert ws.job_exists("yep")

    def test_nested_workspace_detection(self, tmp_path: Path) -> None:
        nested = tmp_path / "simulation_workspace" / "simulation_workspace"
        nested.mkdir(parents=True)
        with pytest.raises(ValueError, match="Nested workspace"):
            WorkspaceManager(root=nested)

    def test_get_job_without_create(self, ws: WorkspaceManager) -> None:
        job = ws.get_job("phantom")
        assert job.job_id == "phantom"
        # dir doesn't exist yet — no auto-creation
        assert not job.dir.exists()


# ── JobWorkspace tests ────────────────────────────────────────────────────


class TestJobWorkspace:
    def test_dir_property(self, job: JobWorkspace, ws: WorkspaceManager) -> None:
        assert job.dir == ws.root / "jobs" / "test-job-001"

    def test_stage_dir_creates(self, job: JobWorkspace) -> None:
        p = job.stage_dir(STAGE_CODEGEN)
        assert p.is_dir()
        assert p.name == STAGE_CODEGEN

    def test_path_resolves(self, job: JobWorkspace) -> None:
        p = job.path(STAGE_INPUT, "query.txt")
        assert p == job.dir / STAGE_INPUT / "query.txt"

    def test_write_and_read_json(self, job: JobWorkspace) -> None:
        data = {"key": "value", "num": 42}
        p = job.write_json(STAGE_HUMAN_CONFIRMATION, "test.json", data)
        assert p.exists()
        loaded = job.read_json(STAGE_HUMAN_CONFIRMATION, "test.json")
        assert loaded == data

    def test_read_json_missing_returns_none(self, job: JobWorkspace) -> None:
        result = job.read_json(STAGE_INPUT, "nonexistent.json")
        assert result is None

    def test_read_json_path(self, job: JobWorkspace) -> None:
        data = {"x": 1}
        p = job.write_json(STAGE_CODEGEN, "plan.json", data)
        loaded = job.read_json_path(p)
        assert loaded == data

    def test_read_json_path_missing(self, job: JobWorkspace) -> None:
        loaded = job.read_json_path(job.dir / "nope.json")
        assert loaded is None

    def test_write_text(self, job: JobWorkspace) -> None:
        p = job.write_text(STAGE_HUMAN_CONFIRMATION, HC_CONFIRMATION_RECORD, "# Report")
        assert p.exists()
        assert p.read_text() == "# Report"

    def test_exists(self, job: JobWorkspace) -> None:
        assert not job.exists(STAGE_INPUT, "q.txt")
        job.write_text(STAGE_INPUT, "q.txt", "hello")
        assert job.exists(STAGE_INPUT, "q.txt")

    def test_geant4_dir_structure(self, job: JobWorkspace) -> None:
        g4 = job.geant4_dir()
        assert g4.exists()
        assert g4 == job.dir / STAGE_PATCH / GEANT4_PROJECT_DIRNAME
        for sub in GEANT4_SUBDIRS:
            assert (g4 / sub).is_dir(), f"missing geant4/{sub}"

    def test_model_ir_dir_structure(self, job: JobWorkspace) -> None:
        mir = job.model_ir_dir()
        assert mir.exists()
        assert (mir / "component_specs").is_dir()

    def test_output_dir(self, job: JobWorkspace) -> None:
        out = job.output_dir()
        assert out.exists()
        assert "g4_output_package" in str(out)

    def test_overwrite_json(self, job: JobWorkspace) -> None:
        job.write_json(STAGE_INPUT, "data.json", {"v": 1})
        job.write_json(STAGE_INPUT, "data.json", {"v": 2})
        loaded = job.read_json(STAGE_INPUT, "data.json")
        assert loaded["v"] == 2


# ── Paths constants tests ────────────────────────────────────────────────


class TestPathsConstants:
    def test_all_stages_count(self) -> None:
        assert len(ALL_STAGES) == 11  # 00-09 + logs

    def test_stage_ordering(self) -> None:
        numbered = [stage for stage in ALL_STAGES if stage[:2].isdigit()]
        prefixes = [int(stage.split("_")[0]) for stage in numbered]
        assert prefixes == list(range(10))
        assert ALL_STAGES[-1] == "logs"

    def test_geant4_subdirs(self) -> None:
        assert "src" in GEANT4_SUBDIRS
        assert "include" in GEANT4_SUBDIRS

    def test_hc_filenames(self) -> None:
        assert HC_CONFIRMATION_RECORD == "confirmation_record.json"


# ── Module-level workspace I/O helper tests ───────────────────────────────


class TestWorkspaceIOHelpers:
    def test_workspace_io_helpers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        from agent_core.workspace.io import (
            ensure_job_dirs,
            get_job_dir,
            get_output_dir,
            get_stage_dir,
            get_workspace_root,
        )

        root = get_workspace_root()
        assert root == tmp_path

        job_id = "workspace-io-test"
        job_dir = ensure_job_dirs(job_id)
        assert job_dir.exists()
        assert get_job_dir(job_id) == job_dir

        stage = get_stage_dir(job_id, STAGE_CODEGEN)
        assert stage.is_dir()

        out = get_output_dir(job_id)
        assert out.exists()

    def test_workspace_io_json_helpers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        from agent_core.workspace.io import (
            read_stage_json,
            write_stage_json,
        )

        path = write_stage_json("io-test", STAGE_CODEGEN, "payload.json", {"ok": True})

        assert path.exists()
        assert read_stage_json("io-test", STAGE_CODEGEN, "payload.json") == {"ok": True}
