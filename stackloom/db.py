"""The internal SQLite database and its migrations."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from stackloom import paths

MIGRATIONS: list[str] = [
    # 1: core
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        csrf TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        group_name TEXT NOT NULL DEFAULT 'inbox',
        source TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE groups (
        name TEXT PRIMARY KEY,
        description TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE ports (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        service TEXT NOT NULL,
        port INTEGER NOT NULL UNIQUE,
        pinned INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (project_id, service)
    );
    CREATE TABLE candidates (
        path TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        found_at TEXT NOT NULL
    );
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        target TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        message TEXT NOT NULL DEFAULT '',
        log TEXT NOT NULL DEFAULT '',
        pid INTEGER,
        pid_start TEXT,
        actor TEXT NOT NULL DEFAULT 'system',
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    );
    CREATE INDEX idx_tasks_status ON tasks(status);
    CREATE TABLE activity (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT NOT NULL DEFAULT '',
        result TEXT NOT NULL DEFAULT 'ok',
        detail TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_activity_at ON activity(at);
    CREATE TABLE maps (
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        map_dir TEXT NOT NULL,
        last_refresh TEXT,
        last_opened TEXT,
        status TEXT NOT NULL DEFAULT 'none',
        stats TEXT NOT NULL DEFAULT '{}',
        error TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 2: databases, backups, notifications
    """
    CREATE TABLE db_connections (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        engine TEXT NOT NULL,
        host TEXT NOT NULL DEFAULT '',
        port INTEGER,
        database TEXT NOT NULL DEFAULT '',
        username TEXT NOT NULL DEFAULT '',
        path TEXT NOT NULL DEFAULT '',
        project_id TEXT,
        container TEXT NOT NULL DEFAULT '',
        read_only INTEGER NOT NULL DEFAULT 1,
        password_source TEXT NOT NULL DEFAULT 'none',
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL
    );
    CREATE TABLE query_history (
        id INTEGER PRIMARY KEY,
        connection_id TEXT NOT NULL,
        database TEXT NOT NULL DEFAULT '',
        sql TEXT NOT NULL,
        at TEXT NOT NULL,
        ms INTEGER,
        rows INTEGER,
        error TEXT NOT NULL DEFAULT '',
        actor TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE backups (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        target TEXT NOT NULL,
        path TEXT NOT NULL,
        size INTEGER NOT NULL DEFAULT 0,
        sha256 TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        verified_at TEXT,
        note TEXT NOT NULL DEFAULT '',
        actor TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE notifications (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'info',
        title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        link TEXT NOT NULL DEFAULT '',
        read INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_notifications_read ON notifications(read);
    """,
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or paths.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    migrate(conn)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Another process may have migrated while we waited for the lock.
            if conn.execute("PRAGMA user_version").fetchone()[0] >= number:
                conn.execute("ROLLBACK")
                continue
            for statement in script.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {number}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
