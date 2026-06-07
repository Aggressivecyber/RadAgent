"""Centralized workspace path management for RadAgent.

Backward-compatible re-export from agent_core.workspace.io.
All new code should import from ``agent_core.workspace`` directly.
"""

# Re-export all public functions from the new workspace module
from agent_core.workspace.io import (  # noqa: F401
    ensure_job_dirs,
    get_job_dir,
    get_output_dir,
    get_stage_dir,
    get_workspace_root,
    read_stage_json,
    write_stage_json,
)

__all__ = [
    "get_workspace_root",
    "get_job_dir",
    "get_stage_dir",
    "get_output_dir",
    "ensure_job_dirs",
    "write_stage_json",
    "read_stage_json",
]
