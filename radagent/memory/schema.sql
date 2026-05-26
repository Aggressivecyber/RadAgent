-- RadAgent Memory Schema (L2 + L3)
-- SQLite DDL

CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    user_input  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS branches (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    parent_branch_id TEXT NOT NULL DEFAULT '',
    parent_sim_id   TEXT NOT NULL DEFAULT '',
    label           TEXT NOT NULL DEFAULT 'main',
    created_at      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS simulations (
    id          TEXT PRIMARY KEY,
    branch_id   TEXT NOT NULL,
    session_dir TEXT NOT NULL DEFAULT '',
    sim_plan    TEXT NOT NULL DEFAULT '',
    build       TEXT NOT NULL DEFAULT '',
    results     TEXT NOT NULL DEFAULT '',
    report      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',
    created_at  TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id   TEXT NOT NULL,
    node            TEXT NOT NULL DEFAULT '',
    scores          TEXT NOT NULL DEFAULT '{}',
    issues          TEXT NOT NULL DEFAULT '[]',
    suggestions     TEXT NOT NULL DEFAULT '[]',
    user_action     TEXT NOT NULL DEFAULT '',
    user_feedback   TEXT NOT NULL DEFAULT '',
    revised_params  TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

-- 索引：常用查询加速
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_branches_project ON branches(project_id);
CREATE INDEX IF NOT EXISTS idx_simulations_branch ON simulations(branch_id);
CREATE INDEX IF NOT EXISTS idx_attempts_sim ON attempts(simulation_id);
CREATE INDEX IF NOT EXISTS idx_attempts_sim_node ON attempts(simulation_id, node);
