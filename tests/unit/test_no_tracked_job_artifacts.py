"""No tracked job artifacts tests.

Ensures that simulation workspace job directories and generated
output files are not committed to the repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _git_ls_files(pattern: str) -> list[str]:
    """List tracked files matching a pattern."""
    result = subprocess.run(
        ["git", "ls-files", pattern],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


class TestNoTrackedJobArtifacts:
    """Job output directories must not be tracked in git."""

    def test_no_tracked_job_directories(self):
        """No files under simulation_workspace/jobs/*/ should be tracked."""
        tracked = _git_ls_files("simulation_workspace/jobs/*/")
        # Filter out .gitkeep
        real_files = [
            f for f in tracked
            if not f.endswith(".gitkeep") and f.strip() != ""
        ]
        assert len(real_files) == 0, (
            "Found tracked job artifacts:\n" + "\n".join(real_files)
        )

    def test_no_tracked_output_csv(self):
        """No edep_3d.csv, dose_3d.csv, event_table.csv in tracked files."""
        for pattern in ("**/edep_3d.csv", "**/dose_3d.csv", "**/event_table.csv"):
            tracked = _git_ls_files(pattern)
            assert len(tracked) == 0, (
                f"Found tracked simulation output: {tracked}"
            )

    def test_no_tracked_g4_summary_json(self):
        """No g4_summary.json in simulation_workspace/ (review_artifacts/ stubs OK)."""
        tracked = _git_ls_files("**/g4_summary.json")
        # Allowed: tests/ fixtures, review_artifacts/ lightweight stubs
        disallowed = [
            f for f in tracked
            if "tests/" not in f and "review_artifacts/" not in f
        ]
        assert len(disallowed) == 0, (
            "Found tracked g4_summary.json outside tests/ and review_artifacts/:\n"
            + "\n".join(disallowed)
        )

    def test_no_tracked_provenance_json(self):
        """No provenance.json in simulation_workspace/ (review_artifacts/ stubs OK)."""
        tracked = _git_ls_files("**/provenance.json")
        # Allowed: tests/ fixtures, review_artifacts/ lightweight stubs
        disallowed = [
            f for f in tracked
            if "tests/" not in f and "review_artifacts/" not in f
        ]
        assert len(disallowed) == 0, (
            "Found tracked provenance.json outside tests/ and review_artifacts/:\n"
            + "\n".join(disallowed)
        )

    def test_no_tracked_run_log(self):
        """No run_log.txt files should be tracked."""
        tracked = _git_ls_files("**/run_log.txt")
        outside_tests = [f for f in tracked if "tests/" not in f]
        assert len(outside_tests) == 0, (
            "Found tracked run_log.txt:\n" + "\n".join(outside_tests)
        )

    def test_no_nested_simulation_workspace(self):
        """No simulation_workspace/simulation_workspace/** should be tracked."""
        tracked = _git_ls_files("simulation_workspace/simulation_workspace/")
        assert len(tracked) == 0, (
            "Found tracked nested simulation_workspace:\n" + "\n".join(tracked)
        )

    def test_gitignore_covers_jobs(self):
        """simulation_workspace/jobs/*/ is in .gitignore."""
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "simulation_workspace/jobs/*/" in gitignore

    def test_gitignore_covers_nested_workspace(self):
        """simulation_workspace/simulation_workspace/ is in .gitignore."""
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "simulation_workspace/simulation_workspace/" in gitignore

    def test_gitignore_keeps_gitkeep(self):
        """Exception for .gitkeep is in .gitignore."""
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "!simulation_workspace/jobs/.gitkeep" in gitignore
