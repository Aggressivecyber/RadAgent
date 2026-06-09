"""Repository layer for RadAgent workspace metadata.

The database is a control plane: it stores searchable metadata, project/job
state and resume snapshots. Large artifacts remain on disk and are referenced
by path.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_core.storage.database import connect, database_path, initialize
from agent_core.workspace.manager import WorkspaceManager

DEFAULT_PROJECT_NAME = "Default Project"
DEFAULT_PROJECT_SLUG = "default"


def _row_to_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or DEFAULT_PROJECT_SLUG


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class RadAgentStore:
    """SQLite-backed repository for projects, jobs and resume snapshots."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = workspace_root or WorkspaceManager().root
        self.db_path = database_path(self.workspace_root)
        self.conn = connect(self.db_path)
        initialize(self.conn)
        self.ensure_default_project()

    def close(self) -> None:
        self.conn.close()

    # ── Settings ────────────────────────────────────────────────────

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings(key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (key, value),
        )
        self.conn.commit()

    # ── Projects ────────────────────────────────────────────────────

    def ensure_default_project(self) -> dict[str, Any]:
        project = self.get_project_by_slug(DEFAULT_PROJECT_SLUG)
        if project:
            if not self.get_setting("current_project_id"):
                self.set_setting("current_project_id", str(project["id"]))
            return project
        project = self.create_project(
            DEFAULT_PROJECT_NAME,
            slug=DEFAULT_PROJECT_SLUG,
            description="Default RadAgent workspace project",
        )
        self.set_setting("current_project_id", str(project["id"]))
        return project

    def create_project(
        self,
        name: str,
        *,
        slug: str | None = None,
        description: str = "",
        root_path: str = "",
    ) -> dict[str, Any]:
        project_id = uuid4().hex
        base_slug = _slugify(slug or name)
        unique_slug = self._unique_project_slug(base_slug)
        self.conn.execute(
            """
            INSERT INTO projects(id, name, slug, description, root_path, last_opened_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (project_id, name.strip() or DEFAULT_PROJECT_NAME, unique_slug, description, root_path),
        )
        self.conn.commit()
        return self.get_project_by_id(project_id) or {}

    def get_project_by_id(self, project_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _row_to_dict(row)

    def get_project_by_slug(self, slug: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        return _row_to_dict(row)

    def get_project(self, value: str) -> dict[str, Any] | None:
        return self.get_project_by_id(value) or self.get_project_by_slug(value)

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM projects
            ORDER BY COALESCE(last_opened_at, '') DESC, updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def current_project(self) -> dict[str, Any]:
        project_id = self.get_setting("current_project_id")
        project = self.get_project_by_id(project_id or "") if project_id else None
        return project or self.ensure_default_project()

    def set_current_project(self, value: str) -> dict[str, Any] | None:
        project = self.get_project(value)
        if not project:
            return None
        self.set_setting("current_project_id", str(project["id"]))
        self.conn.execute(
            "UPDATE projects SET last_opened_at = datetime('now') WHERE id = ?",
            (project["id"],),
        )
        self.conn.commit()
        return self.get_project_by_id(str(project["id"]))

    def _unique_project_slug(self, base_slug: str) -> str:
        slug = base_slug
        i = 2
        while self.get_project_by_slug(slug):
            slug = f"{base_slug}-{i}"
            i += 1
        return slug

    # ── Jobs ────────────────────────────────────────────────────────

    def upsert_job(
        self,
        *,
        job_id: str,
        user_query: str = "",
        project_id: str | None = None,
        status: str = "created",
        current_phase: str = "",
        current_phase_idx: int = 0,
        execution_mode: str = "strict",
        run_mode: str = "strict",
        job_workspace: str = "",
        error_summary: str = "",
    ) -> dict[str, Any]:
        project = self.get_project_by_id(project_id or "") if project_id else self.current_project()
        project_id = str(project["id"])
        row = self.get_job(job_id)
        internal_id = str(row["id"]) if row else uuid4().hex
        self.conn.execute(
            """
            INSERT INTO jobs(
                id, project_id, job_id, user_query, status, current_phase,
                current_phase_idx, execution_mode, run_mode, job_workspace,
                error_summary, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
                project_id = excluded.project_id,
                user_query = COALESCE(NULLIF(excluded.user_query, ''), jobs.user_query),
                status = excluded.status,
                current_phase = excluded.current_phase,
                current_phase_idx = excluded.current_phase_idx,
                execution_mode = excluded.execution_mode,
                run_mode = excluded.run_mode,
                job_workspace = COALESCE(NULLIF(excluded.job_workspace, ''), jobs.job_workspace),
                error_summary = excluded.error_summary,
                updated_at = datetime('now'),
                completed_at = CASE
                    WHEN excluded.status = 'completed' THEN datetime('now')
                    ELSE jobs.completed_at
                END
            """,
            (
                internal_id,
                project_id,
                job_id,
                user_query,
                status,
                current_phase,
                int(current_phase_idx),
                execution_mode,
                run_mode,
                job_workspace,
                error_summary,
            ),
        )
        self.conn.commit()
        return self.get_job(job_id) or {}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _row_to_dict(row)

    def list_jobs(
        self,
        *,
        project_id: str | None = None,
        limit: int | None = None,
        include_all_projects: bool = False,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if not include_all_projects:
            pid = project_id or str(self.current_project()["id"])
            where = "WHERE jobs.project_id = ?"
            params.append(pid)
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(int(limit))
        rows = self.conn.execute(
            f"""
            SELECT jobs.*, projects.slug AS project_slug, projects.name AS project_name
            FROM jobs
            JOIN projects ON projects.id = jobs.project_id
            {where}
            ORDER BY jobs.updated_at DESC, jobs.created_at DESC
            {limit_sql}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def import_existing_jobs(self, *, project_id: str | None = None) -> int:
        """Index existing ``jobs/<job_id>`` directories into the database.

        This is intentionally conservative: it only creates or refreshes job
        metadata and leaves files untouched.
        """
        jobs_dir = self.workspace_root / "jobs"
        if not jobs_dir.exists():
            return 0
        project = self.get_project_by_id(project_id or "") if project_id else self.current_project()
        count = 0
        for job_dir in sorted(jobs_dir.iterdir()):
            if not job_dir.is_dir():
                continue
            query = ""
            query_file = job_dir / "00_input" / "user_query.md"
            if query_file.exists():
                raw = query_file.read_text(encoding="utf-8", errors="replace").strip()
                lines = [line.strip() for line in raw.splitlines() if line.strip()]
                query = lines[-1] if lines else raw[:200]
            report_exists = (job_dir / "10_report" / "final_report.md").exists()
            status = "completed" if report_exists else "paused"
            self.upsert_job(
                job_id=job_dir.name,
                user_query=query,
                project_id=str(project["id"]),
                status=status,
                current_phase="report" if status == "completed" else "",
                current_phase_idx=10 if status == "completed" else 0,
                job_workspace=str(job_dir),
            )
            count += 1
        return count

    def save_state_snapshot(
        self,
        *,
        job_id: str,
        state: dict[str, Any],
        completed_phases: list[str],
        phase: str,
        current_phase_idx: int,
        status: str = "running",
    ) -> None:
        if not self.get_job(job_id):
            self.upsert_job(job_id=job_id, user_query=str(state.get("user_query", "")))
        self.conn.execute(
            """
            INSERT INTO job_state_snapshots(
                job_id, phase, status, current_phase_idx, state_json, completed_phases_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                phase,
                status,
                int(current_phase_idx),
                _json_dumps(state),
                _json_dumps(completed_phases),
            ),
        )
        self.upsert_job(
            job_id=job_id,
            user_query=str(state.get("user_query", "")),
            project_id=str(state.get("project_id", "")) or None,
            status=status,
            current_phase=phase,
            current_phase_idx=current_phase_idx,
            execution_mode=str(state.get("execution_mode", "strict")),
            run_mode=str(state.get("run_mode", "strict")),
            job_workspace=str(state.get("job_workspace", "")),
            error_summary="; ".join(str(e) for e in state.get("errors", [])[-3:]),
        )
        self.conn.commit()

    def latest_state_snapshot(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM job_state_snapshots
            WHERE job_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["state"] = json.loads(data.pop("state_json"))
        data["completed_phases"] = json.loads(data.pop("completed_phases_json"))
        return data

    # ── Artifacts and events ────────────────────────────────────────

    def record_artifact(
        self,
        *,
        job_id: str,
        path: str,
        stage: str = "",
        kind: str = "",
        mime_type: str = "",
    ) -> None:
        p = Path(path)
        size = p.stat().st_size if p.is_file() else 0
        digest = self._sha256_file(p) if p.is_file() else ""
        self.conn.execute(
            """
            INSERT INTO artifacts(job_id, stage, kind, path, sha256, size_bytes, mime_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, path) DO UPDATE SET
                stage = excluded.stage,
                kind = excluded.kind,
                sha256 = excluded.sha256,
                size_bytes = excluded.size_bytes,
                mime_type = excluded.mime_type
            """,
            (job_id, stage, kind, path, digest, size, mime_type),
        )
        self.conn.commit()

    def record_event(
        self,
        *,
        job_id: str,
        event_type: str,
        status: str = "info",
        phase: str = "",
        summary: str = "",
        payload: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO events(job_id, run_id, event_type, status, phase, summary, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, run_id, event_type, status, phase, summary, _json_dumps(payload or {})),
        )
        self.conn.commit()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
