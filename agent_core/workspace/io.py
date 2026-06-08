"""Convenience I/O helpers that delegate to WorkspaceManager.

These module-level functions provide backward-compatible access for
code that has not yet been migrated to use WorkspaceManager directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_core.workspace.manager import WorkspaceManager

__all__ = [
    "get_workspace_root",
    "get_job_dir",
    "get_stage_dir",
    "get_output_dir",
    "ensure_job_dirs",
    "write_stage_json",
    "read_stage_json",
]


def _default_manager() -> WorkspaceManager:
    return WorkspaceManager()


def get_workspace_root() -> Path:
    """Return the workspace root directory (backward compat)."""
    return _default_manager().root


def get_job_dir(job_id: str) -> Path:
    """Return the job directory (backward compat)."""
    return _default_manager().job_dir(job_id)


def get_stage_dir(job_id: str, stage: str) -> Path:
    """Return a stage directory inside a job (backward compat)."""
    return _default_manager().get_job(job_id).stage_dir(stage)


def get_output_dir(job_id: str) -> Path:
    """Return the G4 output package directory (backward compat)."""
    return _default_manager().get_job(job_id).output_dir()


def ensure_job_dirs(job_id: str) -> Path:
    """Create standard job directories and return the job dir (backward compat)."""
    _default_manager().create_job(job_id)
    return _default_manager().job_dir(job_id)


def write_stage_json(job_id: str, stage: str, filename: str, data: dict[str, Any]) -> Path:
    """Write a JSON file to a job stage directory."""
    return _default_manager().get_job(job_id).write_json(stage, filename, data)


def read_stage_json(job_id: str, stage: str, filename: str) -> dict[str, Any] | None:
    """Read a JSON file from a job stage directory."""
    return _default_manager().get_job(job_id).read_json(stage, filename)
