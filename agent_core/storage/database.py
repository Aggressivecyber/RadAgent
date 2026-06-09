"""SQLite schema and connection helpers for RadAgent workspace metadata."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_DB_FILENAME = "radagent.db"


def database_path(workspace_root: Path) -> Path:
    """Return the metadata database path for a workspace root."""
    return workspace_root / DEFAULT_DB_FILENAME


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with RadAgent defaults."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    """Create or migrate the metadata database schema."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            root_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_opened_at TEXT
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            job_id TEXT NOT NULL UNIQUE,
            user_query TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'created',
            current_phase TEXT NOT NULL DEFAULT '',
            current_phase_idx INTEGER NOT NULL DEFAULT 0,
            execution_mode TEXT NOT NULL DEFAULT 'strict',
            run_mode TEXT NOT NULL DEFAULT 'strict',
            job_workspace TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            error_summary TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_project_updated
            ON jobs(project_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_status
            ON jobs(status);

        CREATE TABLE IF NOT EXISTS job_state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            phase TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'running',
            current_phase_idx INTEGER NOT NULL DEFAULT 0,
            state_json TEXT NOT NULL,
            completed_phases_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_job_created
            ON job_state_snapshots(job_id, created_at DESC, id DESC);

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            stage TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            mime_type TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(job_id, path)
        );

        CREATE INDEX IF NOT EXISTS idx_artifacts_job
            ON artifacts(job_id, stage, kind);

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            run_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'info',
            phase TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_events_job_created
            ON events(job_id, created_at DESC, id DESC);

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            job_id TEXT REFERENCES jobs(job_id) ON DELETE SET NULL,
            title TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages(session_id, created_at ASC, id ASC);

        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT REFERENCES jobs(job_id) ON DELETE SET NULL,
            provider TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL DEFAULT '',
            task TEXT NOT NULL DEFAULT '',
            success INTEGER NOT NULL DEFAULT 1,
            latency_ms REAL NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_tool_calls_job
            ON tool_calls(job_id, created_at DESC, id DESC);
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
