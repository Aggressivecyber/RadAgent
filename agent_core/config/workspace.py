"""Centralized workspace path management for RadAgent.

All workspace path construction MUST go through this module.
Never hardcode "simulation_workspace" in node or tool code.
"""

from __future__ import annotations

import os
from pathlib import Path

# Default workspace root (relative to CWD or absolute)
_DEFAULT_WORKSPACE = "simulation_workspace"

# Standard job subdirectories created by ensure_job_dirs
_JOB_STAGES = (
    "00_request",
    "01_context",
    "02_task_spec",
    "03_model_ir",
    "03_model_ir/component_specs",
    "05_geant4/src",
    "05_geant4/include",
    "05_geant4/config",
    "05_geant4/macros",
    "09_validation",
    "10_report",
)


def get_workspace_root() -> Path:
    """Return the workspace root directory.

    Reads ``RADAGENT_WORKSPACE_ROOT`` env var, defaulting to
    ``simulation_workspace``.  Validates that the resolved path does not
    contain a nested ``simulation_workspace/simulation_workspace`` pattern
    which would indicate a double-prefix bug.
    """
    root = Path(os.environ.get("RADAGENT_WORKSPACE_ROOT", _DEFAULT_WORKSPACE))
    resolved = root.resolve()

    # Guard against nested workspace bug
    parts = resolved.parts
    count = parts.count("simulation_workspace")
    if count > 1:
        raise ValueError(
            f"Nested workspace detected: {resolved}. "
            f"Set RADAGENT_WORKSPACE_ROOT to a non-nested path."
        )

    return root


def get_job_dir(job_id: str) -> Path:
    """Return the job directory: ``<workspace_root>/jobs/<job_id>``."""
    return get_workspace_root() / "jobs" / job_id


def get_stage_dir(job_id: str, stage: str) -> Path:
    """Return a specific stage directory inside a job.

    Example: ``get_stage_dir("job_123", "05_geant4")``
    → ``simulation_workspace/jobs/job_123/05_geant4``
    """
    return get_job_dir(job_id) / stage


def get_output_dir(job_id: str) -> Path:
    """Return the canonical G4 output package directory.

    ``simulation_workspace/jobs/<job_id>/08_data_packages/g4_output_package``
    """
    return get_job_dir(job_id) / "08_data_packages" / "g4_output_package"


def ensure_job_dirs(job_id: str) -> Path:
    """Create the standard job directory structure and return the job dir.

    Creates all stage subdirectories under ``<workspace>/jobs/<job_id>/``.
    """
    job_dir = get_job_dir(job_id)
    for stage in _JOB_STAGES:
        (job_dir / stage).mkdir(parents=True, exist_ok=True)
    return job_dir
