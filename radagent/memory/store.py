"""MemoryStore: SQLite-backed L2+L3 memory with structured logging"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from radagent.memory.models import Attempt, Branch, Project, Simulation, User

logger = logging.getLogger("radagent.node.tools")


class MemoryStore:
    """三级记忆统一接口"""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        schema_path = Path(__file__).parent / "schema.sql"
        self._conn.executescript(schema_path.read_text(encoding="utf-8"))
        self._conn.commit()

    def close(self):
        self._conn.close()

    # ── 内部工具 ──────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _log(self, action: str, detail: str = ""):
        msg = f"[MemoryStore] {action}"
        if detail:
            msg += f" {detail}"
        logger.info(msg)

    # ── 用户 ──────────────────────────────────────────────────

    def get_or_create_user(self, user_id: str, display_name: str = "") -> User:
        row = self._conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row:
            self._log("get_user", user_id)
            return User(**dict(row))
        now = self._now()
        self._conn.execute(
            "INSERT INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
            (user_id, display_name or user_id, now),
        )
        self._conn.commit()
        self._log("create_user", user_id)
        return User(id=user_id, display_name=display_name or user_id, created_at=now)

    def list_users(self) -> list[User]:
        rows = self._conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [User(**dict(r)) for r in rows]

    # ── 项目 ──────────────────────────────────────────────────

    def create_project(self, user_id: str, user_input: str) -> Project:
        import uuid
        pid = str(uuid.uuid4())[:8]
        now = self._now()
        title = user_input[:80].replace("\n", " ")
        self._conn.execute(
            "INSERT INTO projects (id, user_id, title, user_input, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (pid, user_id, title, user_input, now, now),
        )
        self._conn.commit()
        self._log("create_project", f"id={pid} title={title[:50]}")
        # 自动创建主分支
        self.create_branch(project_id=pid, label="main")
        return self.get_project(pid)

    def list_projects(self, user_id: str) -> list[Project]:
        rows = self._conn.execute(
            "SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def get_project(self, project_id: str) -> Project:
        row = self._conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise ValueError(f"Project {project_id} not found")
        return Project(**dict(row))

    def update_project_status(self, project_id: str, status: str):
        now = self._now()
        self._conn.execute(
            "UPDATE projects SET status=?, updated_at=? WHERE id=?",
            (status, now, project_id),
        )
        self._conn.commit()
        self._log("update_project_status", f"id={project_id} status={status}")

    # ── 分支 ──────────────────────────────────────────────────

    def get_main_branch(self, project_id: str) -> Branch:
        row = self._conn.execute(
            "SELECT * FROM branches WHERE project_id=? AND label='main'",
            (project_id,),
        ).fetchone()
        if row:
            return Branch(**dict(row))
        return self.create_branch(project_id=project_id, label="main")

    def list_branches(self, project_id: str) -> list[Branch]:
        rows = self._conn.execute(
            "SELECT * FROM branches WHERE project_id=? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [Branch(**dict(r)) for r in rows]

    def create_branch(
        self,
        project_id: str,
        label: str,
        parent_branch_id: str | None = None,
        parent_sim_id: str | None = None,
    ) -> Branch:
        import uuid
        bid = str(uuid.uuid4())[:8]
        now = self._now()
        self._conn.execute(
            "INSERT INTO branches (id, project_id, parent_branch_id, parent_sim_id, label, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (bid, project_id, parent_branch_id or "", parent_sim_id or "", label, now),
        )
        self._conn.commit()
        self._log("create_branch", f"id={bid} project={project_id} label={label}")
        return Branch(
            id=bid, project_id=project_id,
            parent_branch_id=parent_branch_id or "",
            parent_sim_id=parent_sim_id or "",
            label=label, created_at=now,
        )

    # ── 仿真记录 ──────────────────────────────────────────────

    def create_simulation(self, branch_id: str, session_dir: str = "") -> Simulation:
        import uuid
        sid = str(uuid.uuid4())[:8]
        now = self._now()
        self._conn.execute(
            "INSERT INTO simulations (id, branch_id, session_dir, status, created_at) "
            "VALUES (?, ?, ?, 'running', ?)",
            (sid, branch_id, session_dir, now),
        )
        self._conn.commit()
        self._log("create_simulation", f"id={sid} branch={branch_id}")
        return Simulation(id=sid, branch_id=branch_id, session_dir=session_dir, created_at=now)

    def get_simulation(self, sim_id: str) -> Simulation:
        row = self._conn.execute("SELECT * FROM simulations WHERE id=?", (sim_id,)).fetchone()
        if not row:
            raise ValueError(f"Simulation {sim_id} not found")
        return Simulation(**dict(row))

    def update_simulation(self, sim_id: str, **fields) -> None:
        allowed = {"sim_plan", "build", "results", "report", "status", "finished_at"}
        sets = []
        vals = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            vals.append(json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v)
            sets.append(f"{k}=?")
        if not sets:
            return
        vals.append(sim_id)
        self._conn.execute(
            f"UPDATE simulations SET {', '.join(sets)} WHERE id=?",
            vals,
        )
        self._conn.commit()
        self._log("update_simulation", f"id={sim_id} fields={list(fields.keys())}")

    def get_latest_simulation(self, branch_id: str) -> Simulation | None:
        row = self._conn.execute(
            "SELECT * FROM simulations WHERE branch_id=? ORDER BY created_at DESC LIMIT 1",
            (branch_id,),
        ).fetchone()
        return Simulation(**dict(row)) if row else None

    # ── L2 会话记忆 (attempts) ────────────────────────────────

    def append_attempt(
        self,
        simulation_id: str,
        node: str,
        scores: dict | None = None,
        issues: list | None = None,
        suggestions: list | None = None,
        user_action: str = "",
        user_feedback: str = "",
        revised_params: dict | None = None,
    ) -> int:
        now = self._now()
        cur = self._conn.execute(
            "INSERT INTO attempts "
            "(simulation_id, node, scores, issues, suggestions, user_action, "
            "user_feedback, revised_params, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                simulation_id, node,
                json.dumps(scores or {}, ensure_ascii=False),
                json.dumps(issues or [], ensure_ascii=False),
                json.dumps(suggestions or [], ensure_ascii=False),
                user_action, user_feedback,
                json.dumps(revised_params or {}, ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()
        aid = cur.lastrowid
        self._log("append_attempt", f"id={aid} sim={simulation_id} node={node}")
        return aid

    def get_attempts(self, simulation_id: str) -> list[Attempt]:
        rows = self._conn.execute(
            "SELECT * FROM attempts WHERE simulation_id=? ORDER BY id",
            (simulation_id,),
        ).fetchall()
        return [Attempt(**dict(r)) for r in rows]

    def get_attempts_by_node(self, simulation_id: str, node: str) -> list[Attempt]:
        rows = self._conn.execute(
            "SELECT * FROM attempts WHERE simulation_id=? AND node=? ORDER BY id",
            (simulation_id, node),
        ).fetchall()
        return [Attempt(**dict(r)) for r in rows]
