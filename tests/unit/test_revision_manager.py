from __future__ import annotations

import json
from pathlib import Path

from agent_core.revision import RevisionManager, check_accept_preconditions
from agent_core.workspace.paths import GEANT4_PROJECT_DIRNAME, STAGE_PATCH


def test_run_revision_applies_patch_without_touching_main_generated_code(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    job_id = "job-001"
    main_dir = workspace / "jobs" / job_id / STAGE_PATCH / GEANT4_PROJECT_DIRNAME
    (main_dir / "src").mkdir(parents=True)
    (main_dir / "include").mkdir()
    (main_dir / "src" / "main.cc").write_text("int main() { return 0; }\n", encoding="utf-8")
    (main_dir / "include" / "Detector.hh").write_text("// detector\n", encoding="utf-8")
    main_snapshot = _snapshot(main_dir)

    manager = RevisionManager(workspace_root=workspace)
    request = manager.create_revision(
        job_id,
        "Revise main without changing the accepted project",
        base_generated_code_dir=main_dir,
    )
    patch_path = Path(request.revision_dir) / "proposed_patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "patch_id": "revision-patch-1",
                "job_id": job_id,
                "description": "change candidate main",
                "change_type": "modify",
                "risk_level": "low",
                "changed_files": [
                    {
                        "path": "src/main.cc",
                        "new_content": "int main() { return 42; }\n",
                        "zone": "green",
                    },
                ],
                "test_plan": "compile candidate",
                "expected_outputs": {},
            }
        ),
        encoding="utf-8",
    )

    status = manager.run_revision(request.revision_id)

    assert status.status == "completed"
    assert status.patch_status == "applied"
    assert _snapshot(main_dir) == main_snapshot
    assert (Path(request.baseline_dir) / "src" / "main.cc").read_text(encoding="utf-8") == (
        "int main() { return 0; }\n"
    )
    assert (Path(request.candidate_project_dir) / "src" / "main.cc").read_text(
        encoding="utf-8"
    ) == "int main() { return 42; }\n"


def test_multiple_revisions_have_isolated_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    job_id = "job-002"
    main_dir = workspace / "jobs" / job_id / STAGE_PATCH / GEANT4_PROJECT_DIRNAME
    (main_dir / "src").mkdir(parents=True)
    (main_dir / "src" / "main.cc").write_text("original\n", encoding="utf-8")

    manager = RevisionManager(workspace_root=workspace)
    first = manager.create_revision(job_id, "first", base_generated_code_dir=main_dir)
    second = manager.create_revision(job_id, "second", base_generated_code_dir=main_dir)

    manager.run_revision(first.revision_id)
    manager.run_revision(second.revision_id)

    assert first.revision_id != second.revision_id
    assert first.revision_dir != second.revision_dir
    assert first.candidate_project_dir != second.candidate_project_dir

    first_candidate = Path(first.candidate_project_dir) / "src" / "main.cc"
    second_candidate = Path(second.candidate_project_dir) / "src" / "main.cc"
    first_candidate.write_text("changed first only\n", encoding="utf-8")

    assert second_candidate.read_text(encoding="utf-8") == "original\n"
    assert (main_dir / "src" / "main.cc").read_text(encoding="utf-8") == "original\n"


def test_accept_precondition_rejects_failed_gate20() -> None:
    allowed, errors = check_accept_preconditions(
        {
            "validation_status": "passed",
            "gate_results": [
                {"gate_id": 20, "name": "Gate 20 candidate validation", "status": "fail"},
            ],
        }
    )

    assert allowed is False
    assert any("Gate 20" in error for error in errors)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
