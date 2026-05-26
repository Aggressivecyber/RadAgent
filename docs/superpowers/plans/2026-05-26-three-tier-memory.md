# Three-Tier Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-tier memory system (L1 state / L2 session / L3 persistent) with multi-user project management, git-like branching, and full LangGraph checkpoint persistence.

**Architecture:** All L2+L3 data stored in a single SQLite database (`memory/store.db`). LangGraph checkpoints stored separately via `SqliteSaver` (`memory/checkpoints.db`). Nodes interact with memory through a `MemoryStore` class, writing attempt records on gate/QC completion and reading history in revise nodes. CLI gains project list/restore/branch workflow.

**Tech Stack:** SQLite (stdlib `sqlite3`), `langgraph-checkpoint-sqlite`, frozen dataclasses, existing log system.

---

## File Structure

```
radagent/
├── memory/                      # NEW package
│   ├── __init__.py              # MemoryStore re-export
│   ├── models.py                # frozen dataclasses (User, Project, Branch, Simulation, Attempt)
│   ├── schema.sql               # DDL
│   └── store.py                 # SQLite CRUD + logging
├── config.py                    # MODIFY: add MEMORY_DB, CHECKPOINT_DB paths
├── graph.py                     # MODIFY: MemorySaver → SqliteSaver
├── main.py                      # MODIFY: project list/restore/branch CLI
├── log.py                       # MODIFY: add node order entries for new nodes
├── nodes/gates.py               # MODIFY: append_attempt on gate pass/fail
├── nodes/revise.py              # MODIFY: query attempts before revising
├── subgraphs/research/research_qc.py  # MODIFY: append_attempt on QC pass/fail
├── subgraphs/research/revise.py       # MODIFY: query attempts before revising
└── state.py                     # MODIFY: add simulation_id field
```

---

### Task 1: Memory Models

**Files:**
- Create: `radagent/memory/models.py`

- [ ] **Step 1: Write models.py with all frozen dataclasses**

```python
"""三级记忆数据模型"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class User:
    id: str
    display_name: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class Project:
    id: str
    user_id: str
    title: str = ""
    user_input: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Branch:
    id: str
    project_id: str
    parent_branch_id: str = ""
    parent_sim_id: str = ""
    label: str = "main"
    created_at: str = ""


@dataclass(frozen=True)
class Simulation:
    id: str
    branch_id: str
    session_dir: str = ""
    sim_plan_json: str = ""
    build_json: str = ""
    results_json: str = ""
    report: str = ""
    status: str = "running"
    created_at: str = ""
    finished_at: str = ""


@dataclass(frozen=True)
class Attempt:
    id: int
    simulation_id: str
    node: str
    scores_json: str = ""
    issues_json: str = ""
    suggestions_json: str = ""
    user_action: str = ""
    user_feedback: str = ""
    revised_params_json: str = ""
    created_at: str = ""
```

- [ ] **Step 2: Commit**

```bash
git add radagent/memory/models.py
git commit -m "feat(memory): add frozen dataclass models for three-tier memory"
```

---

### Task 2: Schema SQL

**Files:**
- Create: `radagent/memory/schema.sql`

- [ ] **Step 1: Write schema.sql**

```sql
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    title       TEXT NOT NULL DEFAULT '',
    user_input  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS branches (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(id),
    parent_branch_id  TEXT REFERENCES branches(id),
    parent_sim_id     TEXT,
    label             TEXT NOT NULL DEFAULT 'main',
    created_at        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS simulations (
    id          TEXT PRIMARY KEY,
    branch_id   TEXT NOT NULL REFERENCES branches(id),
    session_dir TEXT NOT NULL DEFAULT '',
    sim_plan    TEXT NOT NULL DEFAULT '',
    build       TEXT NOT NULL DEFAULT '',
    results     TEXT NOT NULL DEFAULT '',
    report      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',
    created_at  TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS attempts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id     TEXT NOT NULL REFERENCES simulations(id),
    node              TEXT NOT NULL,
    scores            TEXT NOT NULL DEFAULT '',
    issues            TEXT NOT NULL DEFAULT '',
    suggestions       TEXT NOT NULL DEFAULT '',
    user_action       TEXT NOT NULL DEFAULT '',
    user_feedback     TEXT NOT NULL DEFAULT '',
    revised_params    TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_branches_project ON branches(project_id);
CREATE INDEX IF NOT EXISTS idx_simulations_branch ON simulations(branch_id);
CREATE INDEX IF NOT EXISTS idx_attempts_simulation ON attempts(simulation_id);
CREATE INDEX IF NOT EXISTS idx_attempts_node ON attempts(simulation_id, node);
```

- [ ] **Step 2: Commit**

```bash
git add radagent/memory/schema.sql
git commit -m "feat(memory): add SQLite schema for memory store"
```

---

### Task 3: MemoryStore Implementation

**Files:**
- Create: `radagent/memory/store.py`
- Create: `radagent/memory/__init__.py`

- [ ] **Step 1: Write store.py**

```python
"""MemoryStore: SQLite-backed L2+L3 memory with structured logging"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

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
```

- [ ] **Step 2: Write __init__.py**

```python
"""三级记忆系统"""
from radagent.memory.store import MemoryStore

__all__ = ["MemoryStore"]
```

- [ ] **Step 3: Verify import**

Run: `python -c "from radagent.memory import MemoryStore; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add radagent/memory/__init__.py radagent/memory/store.py
git commit -m "feat(memory): add MemoryStore with SQLite CRUD + logging"
```

---

### Task 4: Config Paths + State Field

**Files:**
- Modify: `radagent/config.py`
- Modify: `radagent/state.py`

- [ ] **Step 1: Add memory paths to config.py**

Add after `LOG_LEVEL = "DEBUG"` line:

```python
# Memory (L2+L3)
MEMORY_DIR = Path(__file__).parent / "memory"
MEMORY_DB = MEMORY_DIR / "store.db"
CHECKPOINT_DB = MEMORY_DIR / "checkpoints.db"

# Default user
DEFAULT_USER = os.environ.get("RADAGENT_USER", "default")
```

- [ ] **Step 2: Add simulation_id to RadAgentState**

In `radagent/state.py`, add `simulation_id` field:

```python
    gate_feedback: str
    gate_feedback_source: str
    simulation_id: str        # L3 simulation record ID
```

- [ ] **Step 3: Verify import**

Run: `python -c "from radagent.config import MEMORY_DB, CHECKPOINT_DB; print(f'{MEMORY_DB} {CHECKPOINT_DB}')"`
Expected: path output

- [ ] **Step 4: Commit**

```bash
git add radagent/config.py radagent/state.py
git commit -m "feat(memory): add MEMORY_DB/CHECKPOINT_DB paths and simulation_id state field"
```

---

### Task 5: Swap MemorySaver to SqliteSaver

**Files:**
- Modify: `radagent/graph.py`

- [ ] **Step 1: Update graph.py checkpointer**

Replace the MemorySaver import and usage in `build_graph()`:

Replace:
```python
from langgraph.checkpoint.memory import MemorySaver
```
With:
```python
from langgraph.checkpoint.sqlite import SqliteSaver
```

Replace the checkpointer creation:
```python
    checkpointer = MemorySaver(serde=serde)
```
With:
```python
    from radagent.config import CHECKPOINT_DB
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    checkpointer = SqliteSaver.from_conn_string(str(CHECKPOINT_DB))
```

Remove the `serde` variable (SqliteSaver handles serialization internally).

- [ ] **Step 2: Remove _SCHEMA_ALLOWLIST if unused**

Since SqliteSaver doesn't use `JsonPlusSerializer`, remove the `_SCHEMA_ALLOWLIST` dict and the `JsonPlusSerializer` import.

- [ ] **Step 3: Verify graph compiles**

Run: `python -c "from radagent.graph import build_graph; g = build_graph(); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add radagent/graph.py
git commit -m "feat(memory): swap MemorySaver to SqliteSaver for checkpoint persistence"
```

---

### Task 6: Integrate memory into main.py

**Files:**
- Modify: `radagent/main.py`

- [ ] **Step 1: Add memory integration to main()**

Add memory initialization at the start of `main()`, project selection loop, and simulation tracking. Key changes:

1. Import MemoryStore and config
2. On startup: `memory = MemoryStore(MEMORY_DB)`, get/create user
3. Show recent projects if any exist
4. If user picks a project → load state from checkpoint (LangGraph handles this via thread_id)
5. If new input → create project + main branch + simulation record
6. After graph run completes → update simulation status + attempt records

The full updated `main.py`:

```python
"""RadG4-Agent CLI 入口"""

import sys

from langgraph.types import Command

from radagent.graph import build_graph
from radagent.log import init_session_log, log_info, get_session_dir
from radagent.memory import MemoryStore
from radagent.config import MEMORY_DB, DEFAULT_USER
from radagent.schemas import BuildResult, ControlState

_IS_PIPE = not sys.stdin.isatty()


def _read_user_input() -> str:
    """读取用户输入（支持多行）"""
    if _IS_PIPE:
        return sys.stdin.read().strip()

    print("  （多行输入，以空行结束）")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "" and lines:
            break
        if line.strip():
            lines.append(line.strip())

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("  RadG4-Agent — 航天辐照仿真智能体")
    print("  输入自然语言，自动完成 Geant4 仿真与报告生成")
    print("=" * 60)

    session_dir = init_session_log()
    memory = MemoryStore(MEMORY_DB)
    user = memory.get_or_create_user(DEFAULT_USER)
    graph = build_graph()

    # ── 项目选择 ──────────────────────────────────────────────
    projects = memory.list_projects(user.id)
    project = None
    branch = None
    sim = None
    initial_state = None

    if projects and not _IS_PIPE:
        print(f"\n欢迎, {user.display_name}! 近期项目:")
        for i, p in enumerate(projects[:10], 1):
            print(f"  {i}. [{p.status}] {p.title}  ({p.created_at[:10]})")
        print(f"\n输入编号继续, 或输入新需求开始新项目")

    user_input_raw = _read_user_input()
    if not user_input_raw:
        print("再见！")
        memory.close()
        return

    # 判断是选择已有项目还是新需求
    if projects and not _IS_PIPE and user_input_raw.isdigit():
        idx = int(user_input_raw) - 1
        if 0 <= idx < len(projects):
            project = projects[idx]
            branch = memory.get_main_branch(project.id)
            sim = memory.get_latest_simulation(branch.id)
            # 恢复已有项目：让用户输入修改指令
            print(f"\n项目: {project.title}")
            branches = memory.list_branches(project.id)
            for b in branches:
                latest = memory.get_latest_simulation(b.id)
                status = latest.status if latest else "none"
                print(f"  分支 [{b.label}] → {status}")

            print("\n输入修改指令创建新分支, 或输入新需求")
            mod_input = _read_user_input()
            if not mod_input:
                print("再见！")
                memory.close()
                return

            # 创建新分支
            parent_sim_id = sim.id if sim else ""
            branch = memory.create_branch(
                project_id=project.id,
                label=mod_input[:40],
                parent_branch_id=branch.id,
                parent_sim_id=parent_sim_id,
            )
            user_input = mod_input
            # TODO: 从 parent sim 继承 sim_plan + 应用 delta
            initial_state = None  # 将在下方构建
        else:
            print("无效编号")
            memory.close()
            return
    else:
        user_input = user_input_raw

    # ── 创建项目/仿真记录 ────────────────────────────────────
    log_info("main", f"用户输入: {user_input}")

    if project is None:
        project = memory.create_project(user.id, user_input)
        branch = memory.get_main_branch(project.id)

    sim = memory.create_simulation(branch.id, str(session_dir))

    if initial_state is None:
        initial_state = {
            "messages": [],
            "user_input": user_input,
            "sim_plan": None,
            "build": BuildResult(),
            "results": [],
            "anomaly": [],
            "figure_paths": {},
            "analysis_data": {},
            "report": "",
            "control": ControlState(),
            "parse_error": "",
            "gate_feedback": "",
            "gate_feedback_source": "",
            "simulation_id": sim.id,
        }
    else:
        initial_state["user_input"] = user_input
        initial_state["simulation_id"] = sim.id

    config = {"configurable": {"thread_id": f"radagent-{project.id}-{branch.id}"}}

    print(f"\n--- 开始处理 (日志: {session_dir}, 项目: {project.title}) ---\n")

    # ── 执行管线 ──────────────────────────────────────────────
    _run_stream(graph, initial_state, config)

    # 处理 interrupt
    state_snapshot = graph.get_state(config)
    while state_snapshot.next:
        if not _handle_interrupt(graph, config, state_snapshot, memory, sim.id):
            break
        state_snapshot = graph.get_state(config)

    # ── 更新仿真记录 ──────────────────────────────────────────
    final = graph.get_state(config)
    final_results = final.values.get("results", [])
    final_report = final.values.get("report", "")
    final_plan = final.values.get("sim_plan")

    import json
    memory.update_simulation(
        sim.id,
        sim_plan=json.dumps(json.loads(_safe_serialize(final_plan)), ensure_ascii=False) if final_plan else "",
        results=json.dumps([json.loads(_safe_serialize(r)) for r in final_results], ensure_ascii=False) if final_results else "",
        report=final_report,
        status="completed",
        finished_at=memory._now(),
    )
    memory.update_project_status(project.id, "completed")

    memory.close()
    print("\n完成！")


def _run_stream(graph, initial_state, config):
    """流式执行主图，实时打印节点进展"""
    try:
        for event in graph.stream(initial_state, config=config, stream_mode="updates"):
            for node_name, output in event.items():
                _print_node_update(node_name, output)
    except Exception as e:
        log_info("main", f"流执行错误: {e}")
        print(f"\n错误: {e}")


def _print_node_update(node_name: str, output: dict):
    """根据节点类型打印进展信息"""
    if node_name == "research":
        plan = output.get("sim_plan")
        if plan:
            geo = plan.geometry
            print(f"  [调研完成] 结构: {geo.name}, {len(geo.layers)} 层")
            for s in plan.scenarios:
                print(f"    场景: {s.name} ({s.source.particle} {s.source.energy_MeV} MeV, {s.num_events} events)")
        err = output.get("parse_error")
        if err:
            print(f"  [调研错误] {err[:200]}")

    elif node_name == "parameterize":
        build = output.get("build")
        if build and build.source_dir:
            print(f"  [模板渲染] {build.source_dir}")

    elif node_name == "build_and_run":
        build = output.get("build")
        results = output.get("results", [])
        if build:
            if build.compile_ok:
                print(f"  [编译] 成功")
            if build.run_ok and results:
                for r in results:
                    print(f"  [场景] {r.scenario_name}: "
                          f"剂量={r.total_dose_Gy:.4e} Gy, "
                          f"峰值层={r.peak_layer or 'N/A'}")
            err = build.compile_error
            if err:
                print(f"  [编译失败] {err[:200]}")

    elif node_name == "sim_gate":
        err = output.get("parse_error", "")
        if err:
            print(f"  [门禁 ✗] 仿真结果不达标")
            print(f"    {err[:300]}")
        else:
            print(f"  [门禁 ✓] 仿真结果通过")

    elif node_name == "analyze":
        fig_paths = output.get("figure_paths", {})
        anomaly = output.get("anomaly", [])
        if fig_paths:
            print(f"  [可视化] 生成 {len(fig_paths)} 张图:")
            for key, path in fig_paths.items():
                print(f"    {key}: {path}")
        for a in anomaly:
            if a.status != "normal":
                print(f"  [异常] {a.status}: {a.details}")

    elif node_name == "report_gate":
        err = output.get("parse_error", "")
        if err:
            print(f"  [门禁 ✗] 报告质量不达标")
            print(f"    {err[:300]}")
        else:
            print(f"  [门禁 ✓] 报告质量通过")

    elif node_name == "generate_report":
        report = output.get("report", "")
        print(f"\n  [报告] 已生成 ({len(report)} 字)")

    elif node_name == "human_review":
        pass

    elif node_name == "revise":
        print(f"  [修订] 分析中...")


def _handle_interrupt(graph, config, snapshot, memory, sim_id) -> bool:
    """处理 interrupt，返回 True 表示继续"""
    if not snapshot.tasks:
        return False

    for task in snapshot.tasks:
        if not hasattr(task, "interrupts") or not task.interrupts:
            continue

        info = task.interrupts[0].value

        if info.get("type") == "plan_confirmation":
            print("\n" + "=" * 50)
            print("仿真计划确认")
            print("=" * 50)
            message = info.get("message", "")
            if isinstance(message, str):
                print(message[:1500])
            else:
                print(str(message)[:1500])

            if _IS_PIPE:
                print("\n[pipe 模式] 自动确认")
                decision = "yes"
            else:
                decision = input("\n输入 'yes' 确认，或输入修改意见: ").strip()

            if decision.lower() == "yes" or not decision:
                resume_value = {"action": "confirm"}
            else:
                resume_value = {"action": "modify", "feedback": decision}

        elif info.get("type") == "gate_warning":
            gate_name = info.get("gate_name", "unknown")
            print(f"\n{'=' * 50}")
            print(f"门禁警告 [{gate_name}]")
            print("=" * 50)
            message = info.get("message", "")
            print(message[:2000])

            if _IS_PIPE:
                print("\n[pipe 模式] 自动继续")
                decision = "continue"
            else:
                decision = input("\n输入 'continue' 继续，或输入修改意见回退: ").strip().lower()

            if decision == "continue" or decision == "yes" or not decision:
                resume_value = {"action": "continue"}
            else:
                resume_value = {"action": "modify", "feedback": decision}

        else:
            print("\n" + "=" * 50)
            print("报告审核")
            print("=" * 50)
            preview = info.get("report_preview", "")
            print(f"\n{preview}...\n")

            if _IS_PIPE:
                print("[pipe 模式] 自动批准")
                decision = "yes"
            else:
                decision = input("输入 'yes' 批准，或输入反馈意见: ").strip()

            if decision.lower() == "yes" or not decision:
                resume_value = {"approved": True, "feedback": ""}
            else:
                resume_value = {"approved": False, "feedback": decision}

        log_info("main", f"用户决定: {decision}")

        # 记录用户决策到 L2
        memory.append_attempt(
            simulation_id=sim_id,
            node="interrupt",
            user_action=resume_value.get("action", resume_value.get("approved", "")),
            user_feedback=resume_value.get("feedback", ""),
        )

        try:
            graph.invoke(Command(resume=resume_value), config=config)
        except Exception as e:
            log_info("main", f"恢复执行错误: {e}")
            print(f"错误: {e}")
            return False

        return True

    return False


def _safe_serialize(obj) -> str:
    """序列化 frozen dataclass 为 JSON 字符串"""
    import json
    if obj is None:
        return "null"
    if hasattr(obj, "__dataclass_fields__"):
        fields = {}
        for k in obj.__dataclass_fields__:
            fields[k] = _to_json_safe(getattr(obj, k))
        return json.dumps(fields, ensure_ascii=False)
    return str(obj)


def _to_json_safe(obj):
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(i) for i in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_json_safe(getattr(obj, k)) for k in obj.__dataclass_fields__}
    return str(obj)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify graph still compiles**

Run: `python -c "from radagent.main import main; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add radagent/main.py
git commit -m "feat(memory): integrate MemoryStore into CLI with project list/restore/branch"
```

---

### Task 7: Integrate append_attempt into gate/QC/revise nodes

**Files:**
- Modify: `radagent/nodes/gates.py`
- Modify: `radagent/subgraphs/research/research_qc.py`
- Modify: `radagent/nodes/revise.py`
- Modify: `radagent/subgraphs/research/revise.py`

- [ ] **Step 1: Add append_attempt to sim_gate (gates.py)**

At the end of `sim_gate()`, before the return, add attempt recording. After the `_evaluate()` call:

```python
    # L2 记忆：记录门禁评估
    sim_id = state.get("simulation_id", "")
    if sim_id:
        from radagent.memory import MemoryStore
        from radagent.config import MEMORY_DB
        try:
            _mem = MemoryStore(MEMORY_DB)
            _mem.append_attempt(
                simulation_id=sim_id, node="sim_gate",
                scores=result.scores, issues=list(result.issues),
                suggestions=list(result.suggestions),
            )
            _mem.close()
        except Exception as e:
            logger.warning("记忆写入失败: %s", e)
```

Do the same for `report_gate()` (same pattern, change `node="report_gate"`).

- [ ] **Step 2: Add append_attempt to research_qc.py**

After `_evaluate()` call in `research_qc()`, add:

```python
    # L2 记忆：记录 QC 评估
    sim_id = state.get("simulation_id", "")
    if sim_id:
        from radagent.memory import MemoryStore
        from radagent.config import MEMORY_DB
        try:
            _mem = MemoryStore(MEMORY_DB)
            _mem.append_attempt(
                simulation_id=sim_id, node="research_qc",
                scores=result.scores, issues=list(result.issues),
                suggestions=list(result.suggestions),
            )
            _mem.close()
        except Exception as e:
            logger.warning("记忆写入失败: %s", e)
```

- [ ] **Step 3: Add get_attempts query to main revise node (nodes/revise.py)**

At the start of the `revise()` function, after `log_node_entry`, add:

```python
    # L2 记忆：查询历史尝试
    sim_id = state.get("simulation_id", "")
    prev_attempts = []
    if sim_id:
        from radagent.memory import MemoryStore
        from radagent.config import MEMORY_DB
        try:
            _mem = MemoryStore(MEMORY_DB)
            prev_attempts = _mem.get_attempts(sim_id)
            _mem.close()
            if prev_attempts:
                log_info(_NODE, f"查询到 {len(prev_attempts)} 条历史尝试记录")
        except Exception as e:
            logger.warning("记忆读取失败: %s", e)
```

Do the same for `radagent/subgraphs/research/revise.py` (same pattern).

- [ ] **Step 4: Verify graph compiles**

Run: `python -c "from radagent.graph import build_graph; g = build_graph(); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add radagent/nodes/gates.py radagent/subgraphs/research/research_qc.py radagent/nodes/revise.py radagent/subgraphs/research/revise.py
git commit -m "feat(memory): integrate append_attempt into gates/QC/revise nodes"
```

---

### Task 8: Update log.py node order

**Files:**
- Modify: `radagent/log.py`

- [ ] **Step 1: Add new nodes to _NODE_ORDER**

In the `_NODE_ORDER` dict, add entries for the new nodes:

```python
_NODE_ORDER: dict[str, int] = {
    "parse_intent": 1,
    "design_schema": 2,
    "research_params": 3,
    "research_qc": 4,
    "revise": 5,
    "confirm_params": 6,
    "parameterize": 7,
    "build_and_run": 8,
    "sim_gate": 9,
    "analyze": 10,
    "report_gate": 11,
    "generate_report": 12,
    "human_review": 13,
}
```

- [ ] **Step 2: Commit**

```bash
git add radagent/log.py
git commit -m "chore: update log node order with new revise/QC/gate entries"
```

---

### Task 9: End-to-end smoke test

**Files:** None (testing only)

- [ ] **Step 1: Run graph compilation**

Run: `python -c "from radagent.graph import build_graph; g = build_graph(); print('Graph OK')"`

- [ ] **Step 2: Run memory store smoke test**

Run:
```python
python -c "
from radagent.memory import MemoryStore
from radagent.config import MEMORY_DB
import os

# 清理测试 DB
if os.path.exists(MEMORY_DB):
    os.remove(MEMORY_DB)

m = MemoryStore(MEMORY_DB)
u = m.get_or_create_user('test_user', 'Test')
p = m.create_project(u.id, '测试 LEO 仿真')
b = m.get_main_branch(p.id)
s = m.create_simulation(b.id, 'logs/test')

m.append_attempt(s.id, 'research_qc', scores={'完整性': 8}, issues=['测试'])
attempts = m.get_attempts(s.id)
assert len(attempts) == 1
assert attempts[0].node == 'research_qc'

m.update_simulation(s.id, status='completed')
m.close()
os.remove(MEMORY_DB)
print('Smoke test PASSED')
"
```
Expected: `Smoke test PASSED`

- [ ] **Step 3: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "feat(memory): complete three-tier memory system implementation"
```
