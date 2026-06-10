"""Revision sandbox workflow manager.

Revision sandboxes are job-scoped copies of generated code. The manager copies
the main generated project into a baseline and a candidate project, then applies
optional JSON replacement patches only to the candidate.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_core.patching.nodes import apply_patch, load_proposed_patch, review_patch
from agent_core.revision.models import RevisionRequest, RevisionStatus, RevisionSummary
from agent_core.workspace.manager import WorkspaceManager
from agent_core.workspace.paths import (
    GEANT4_PROJECT_DIRNAME,
    REVISION_BASELINE_DIRNAME,
    REVISION_CANDIDATE_PROJECT_DIRNAME,
    REVISION_DIRNAME,
    STAGE_PATCH,
)

REQUEST_FILENAME = "revision_request.json"
STATUS_FILENAME = "revision_status.json"
SUMMARY_FILENAME = "revision_summary.json"
PATCH_STATE_FILENAME = "patch_state.json"
DEFAULT_PATCH_FILENAME = "proposed_patch.json"
_GATE20_REJECT_STATUSES = {"fail", "failed", "block", "blocked"}


class RevisionManager:
    """Create and run isolated revision sandboxes."""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = (
            Path(workspace_root) if workspace_root is not None else WorkspaceManager().root
        )

    def create_revision(
        self,
        job_id: str,
        user_request: str,
        workspace_root: str | Path | None = None,
        base_generated_code_dir: str | Path | None = None,
    ) -> RevisionRequest:
        """Persist a new revision request under jobs/<job_id>/revisions/<revision_id>."""
        root = Path(workspace_root) if workspace_root is not None else self.workspace_root
        self.workspace_root = root
        revision_id = f"rev_{uuid.uuid4().hex[:12]}"
        revision_dir = _revision_dir(root, job_id, revision_id)
        baseline_dir = revision_dir / REVISION_BASELINE_DIRNAME
        candidate_dir = revision_dir / REVISION_CANDIDATE_PROJECT_DIRNAME
        base_dir = (
            Path(base_generated_code_dir)
            if base_generated_code_dir is not None
            else root / "jobs" / job_id / STAGE_PATCH / GEANT4_PROJECT_DIRNAME
        )

        revision_dir.mkdir(parents=True, exist_ok=False)

        request = RevisionRequest(
            revision_id=revision_id,
            job_id=job_id,
            user_request=user_request,
            workspace_root=str(root),
            base_generated_code_dir=str(base_dir),
            revision_dir=str(revision_dir),
            baseline_dir=str(baseline_dir),
            candidate_project_dir=str(candidate_dir),
        )
        status = RevisionStatus(
            revision_id=revision_id,
            job_id=job_id,
            revision_dir=str(revision_dir),
            baseline_dir=str(baseline_dir),
            candidate_project_dir=str(candidate_dir),
        )
        _write_model(revision_dir / REQUEST_FILENAME, request)
        _write_model(revision_dir / STATUS_FILENAME, status)
        _write_summary(request, status)
        return request

    def run_revision(
        self,
        revision_id: str,
        proposed_patch_path: str | Path | None = None,
    ) -> RevisionStatus:
        """Run a revision synchronously.

        Use ``arun_revision`` when calling from an existing event loop.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun_revision(revision_id, proposed_patch_path))
        raise RuntimeError("run_revision cannot be called from a running event loop")

    async def arun_revision(
        self,
        revision_id: str,
        proposed_patch_path: str | Path | None = None,
    ) -> RevisionStatus:
        """Create sandbox copies and optionally apply a JSON patch to the candidate."""
        request = self._load_request(revision_id)
        revision_dir = Path(request.revision_dir)
        baseline_dir = Path(request.baseline_dir)
        candidate_dir = Path(request.candidate_project_dir)
        base_dir = Path(request.base_generated_code_dir)

        status = RevisionStatus(
            revision_id=request.revision_id,
            job_id=request.job_id,
            status="running",
            revision_dir=request.revision_dir,
            baseline_dir=request.baseline_dir,
            candidate_project_dir=request.candidate_project_dir,
            updated_at=datetime.now(UTC),
        )
        _write_model(revision_dir / STATUS_FILENAME, status)

        errors: list[str] = []
        patch_status = "not_requested"
        patch_review_path = ""
        applied_patch_path = ""
        patch_path = _resolve_patch_path(request, proposed_patch_path)

        try:
            _reset_revision_subdir(baseline_dir, revision_dir)
            _reset_revision_subdir(candidate_dir, revision_dir)

            if base_dir.exists():
                _copy_project(base_dir, baseline_dir)
                _copy_project(baseline_dir, candidate_dir)
            else:
                errors.append(f"Base generated code directory not found: {base_dir}")

            if patch_path is not None:
                patch_result = await self._apply_patch_in_sandbox(
                    request=request,
                    patch_path=patch_path,
                    candidate_dir=candidate_dir,
                )
                patch_status = str(patch_result.get("patch_status", "failed"))
                patch_review_path = str(patch_result.get("patch_review_path", ""))
                applied_patch_path = str(patch_result.get("applied_patch_path", ""))
                errors.extend(str(error) for error in patch_result.get("errors", []))
                if patch_status != "applied":
                    errors.append(f"Revision patch was not applied: {patch_status}")
        except Exception as exc:
            errors.append(str(exc))

        final_status = "failed" if errors else "completed"
        status = RevisionStatus(
            revision_id=request.revision_id,
            job_id=request.job_id,
            status=final_status,
            revision_dir=request.revision_dir,
            baseline_dir=request.baseline_dir,
            candidate_project_dir=request.candidate_project_dir,
            proposed_patch_path=str(patch_path or ""),
            patch_status=patch_status,
            patch_review_path=patch_review_path,
            applied_patch_path=applied_patch_path,
            errors=errors,
            updated_at=datetime.now(UTC),
        )
        _write_model(revision_dir / STATUS_FILENAME, status)
        _write_summary(request, status)
        return status

    def get_summary(self, revision_id: str) -> RevisionSummary:
        """Load the persisted summary for a revision."""
        revision_dir = self._find_revision_dir(revision_id)
        data = json.loads((revision_dir / SUMMARY_FILENAME).read_text(encoding="utf-8"))
        return RevisionSummary.model_validate(data)

    def _load_request(self, revision_id: str) -> RevisionRequest:
        revision_dir = self._find_revision_dir(revision_id)
        data = json.loads((revision_dir / REQUEST_FILENAME).read_text(encoding="utf-8"))
        return RevisionRequest.model_validate(data)

    def _find_revision_dir(self, revision_id: str) -> Path:
        jobs_dir = self.workspace_root / "jobs"
        matches = sorted(jobs_dir.glob(f"*/{REVISION_DIRNAME}/{revision_id}"))
        if not matches:
            raise FileNotFoundError(f"Revision not found: {revision_id}")
        if len(matches) > 1:
            raise ValueError(f"Revision ID is not unique: {revision_id}")
        return matches[0]

    async def _apply_patch_in_sandbox(
        self,
        request: RevisionRequest,
        patch_path: Path,
        candidate_dir: Path,
    ) -> dict[str, Any]:
        patch_workspace = Path(request.revision_dir) / "_patching_workspace"
        patch_workspace.mkdir(parents=True, exist_ok=True)

        state: dict[str, Any] = {
            "job_id": request.job_id,
            "proposed_patch_path": str(patch_path),
            "generated_code_dir": str(candidate_dir),
            "errors": [],
        }
        with _temporary_workspace_root(patch_workspace):
            state.update(await load_proposed_patch(state))
            state.update(await review_patch(state))
            state.update(await apply_patch(state))

        patch_state_path = Path(request.revision_dir) / PATCH_STATE_FILENAME
        patch_state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return state


def check_accept_preconditions(gate_state: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Return whether a revision candidate may be accepted.

    Acceptance requires overall gate validation to have passed and a Gate 20
    result, when present, to be neither fail nor block.
    """
    errors: list[str] = []
    validation_status = gate_state.get("validation_status")
    if validation_status != "passed":
        errors.append(f"Gate validation status must be passed, got {validation_status!r}")

    for gate in _iter_gate_results(gate_state):
        if not _is_gate20(gate):
            continue
        status = str(gate.get("status", "")).strip().lower()
        if status in _GATE20_REJECT_STATUSES:
            errors.append(f"Gate 20 must not fail or block, got {status!r}")

    return len(errors) == 0, errors


def _revision_dir(root: Path, job_id: str, revision_id: str) -> Path:
    return root / "jobs" / job_id / REVISION_DIRNAME / revision_id


def _write_model(path: Path, model: RevisionRequest | RevisionStatus | RevisionSummary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.model_dump(mode="json"), indent=2), encoding="utf-8")


def _write_summary(request: RevisionRequest, status: RevisionStatus) -> None:
    _write_model(
        Path(request.revision_dir) / SUMMARY_FILENAME,
        RevisionSummary.from_request_status(request, status),
    )


def _resolve_patch_path(
    request: RevisionRequest,
    proposed_patch_path: str | Path | None,
) -> Path | None:
    if proposed_patch_path is not None:
        return Path(proposed_patch_path)
    if request.proposed_patch_path:
        return Path(request.proposed_patch_path)
    default_path = Path(request.revision_dir) / DEFAULT_PATCH_FILENAME
    if default_path.exists():
        return default_path
    return None


def _reset_revision_subdir(path: Path, revision_dir: Path) -> None:
    resolved_path = path.resolve()
    resolved_revision = revision_dir.resolve()
    if not resolved_path.is_relative_to(resolved_revision):
        raise ValueError(f"Refusing to reset path outside revision dir: {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_project(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise NotADirectoryError(f"Project source is not a directory: {source}")
    shutil.copytree(source, destination, dirs_exist_ok=True)


def _iter_gate_results(gate_state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_results = gate_state.get("gate_results", [])
    if not isinstance(raw_results, list):
        return []
    return [result for result in raw_results if isinstance(result, Mapping)]


def _is_gate20(gate: Mapping[str, Any]) -> bool:
    gate_id = gate.get("gate_id")
    if gate_id == 20:
        return True

    gate_id_text = str(gate_id or "").strip().lower().replace("-", "_").replace(" ", "_")
    if gate_id_text in {"20", "gate20", "gate_20"}:
        return True

    gate_name = str(gate.get("name", "")).strip().lower().replace("-", " ")
    return gate_name.startswith("gate 20") or gate_name.startswith("gate20")


@contextmanager
def _temporary_workspace_root(workspace_root: Path) -> Any:
    old_value = os.environ.get("RADAGENT_WORKSPACE_ROOT")
    os.environ["RADAGENT_WORKSPACE_ROOT"] = str(workspace_root)
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("RADAGENT_WORKSPACE_ROOT", None)
        else:
            os.environ["RADAGENT_WORKSPACE_ROOT"] = old_value
