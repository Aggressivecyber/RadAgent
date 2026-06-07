"""WorkspaceManager — single source of truth for job paths.

Usage::

    from agent_core.workspace import WorkspaceManager

    ws = WorkspaceManager()
    job = ws.create_job("my-job-123")
    job.write_json("04_human_confirmation", "confirmation_record.json", record)
    data = job.read_json("04_human_confirmation", "confirmation_record.json")
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_core.workspace.paths import (
    ALL_STAGES,
    GEANT4_SUBDIRS,
    MODEL_IR_SUBDIRS,
)


class JobWorkspace:
    """Represents a single job's workspace on disk.

    All path resolution goes through this object so that nodes never
    hardcode directory names.
    """

    def __init__(self, job_id: str, root: Path) -> None:
        self.job_id = job_id
        self._root = root

    # ── Path helpers ──────────────────────────────────────────────────

    @property
    def dir(self) -> Path:
        """The job root directory: ``<workspace_root>/jobs/<job_id>``."""
        return self._root / "jobs" / self.job_id

    def stage_dir(self, stage: str) -> Path:
        """Return (and create if needed) a stage directory."""
        p = self.dir / stage
        p.mkdir(parents=True, exist_ok=True)
        return p

    def path(self, stage: str, filename: str) -> Path:
        """Resolve a file path inside a stage directory."""
        return self.stage_dir(stage) / filename

    def geant4_dir(self) -> Path:
        """Return the Geant4 project root (under 07_patch/geant4_project)."""
        base = self.stage_dir("07_patch") / "geant4_project"
        for sub in GEANT4_SUBDIRS:
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base

    def model_ir_dir(self) -> Path:
        """Return the model IR directory with component_specs sub-dir."""
        base = self.stage_dir("05_model_ir")
        for sub in MODEL_IR_SUBDIRS:
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base

    def output_dir(self) -> Path:
        """Return the G4 output package directory.

        ``jobs/<job_id>/08_gate_validation/g4_output_package``
        """
        p = self.stage_dir("08_gate_validation") / "g4_output_package"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── I/O helpers ───────────────────────────────────────────────────

    def write_json(self, stage: str, filename: str, data: dict[str, Any]) -> Path:
        """Write a JSON file to a stage directory and return the path."""
        p = self.path(stage, filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    def read_json(self, stage: str, filename: str) -> dict[str, Any] | None:
        """Read a JSON file from a stage directory.

        Returns ``None`` if the file does not exist.
        """
        p = self.path(stage, filename)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def read_json_path(self, path: Path) -> dict[str, Any] | None:
        """Read a JSON file from an absolute path.

        Returns ``None`` if the file does not exist.
        """
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_text(self, stage: str, filename: str, text: str) -> Path:
        """Write a text file to a stage directory and return the path."""
        p = self.path(stage, filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def exists(self, stage: str, filename: str) -> bool:
        """Check whether a file exists in a stage directory."""
        return self.path(stage, filename).exists()

    # ── Initialization ────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        """Create all standard stage directories for this job."""
        for stage in ALL_STAGES:
            self.stage_dir(stage)
        # Also create nested sub-dirs
        self.geant4_dir()
        self.model_ir_dir()


class WorkspaceManager:
    """Centralized workspace management.

    Reads ``RADAGENT_WORKSPACE_ROOT`` env var (default: ``simulation_workspace``).
    Validates against nested workspace bugs.
    """

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path(
                os.environ.get("RADAGENT_WORKSPACE_ROOT", "simulation_workspace"),
            )
        resolved = root.resolve()
        parts = resolved.parts
        if parts.count("simulation_workspace") > 1:
            raise ValueError(
                f"Nested workspace detected: {resolved}. "
                f"Set RADAGENT_WORKSPACE_ROOT to a non-nested path."
            )
        self._root = root

    @property
    def root(self) -> Path:
        """The workspace root directory."""
        return self._root

    def create_job(self, job_id: str) -> JobWorkspace:
        """Create a new job workspace with all standard directories."""
        job = JobWorkspace(job_id, self._root)
        job._ensure_dirs()
        return job

    def get_job(self, job_id: str) -> JobWorkspace:
        """Get an existing job workspace (does NOT auto-create dirs)."""
        return JobWorkspace(job_id, self._root)

    def job_dir(self, job_id: str) -> Path:
        """Return the job root directory path."""
        return self._root / "jobs" / job_id

    def job_exists(self, job_id: str) -> bool:
        """Check whether a job directory exists."""
        return (self._root / "jobs" / job_id).exists()
