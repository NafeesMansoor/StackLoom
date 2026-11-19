"""Background tasks.

Short jobs (discovery) run on a small in-process thread pool. Heavy jobs
(CodeCortex refreshes) run as detached child processes that update their own
row, so they survive a dashboard restart and can be started by the CLI
without the dashboard running. Either way the row in `tasks` is the record.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from stackloom import db, paths, procs
from stackloom.security import redact

ACTIVE = ("queued", "running")
_pool: ThreadPoolExecutor | None = None


def create(conn: sqlite3.Connection, kind: str, target: str = "", actor: str = "system") -> int:
    cur = conn.execute("INSERT INTO tasks (kind, target, status, actor, created_at) VALUES (?,?,?,?,?)",
                       (kind, target, "queued", actor, db.now()))
    return int(cur.lastrowid)


def update(conn: sqlite3.Connection, task_id: int, **fields) -> None:
    if "status" in fields:
        if fields["status"] == "running":
            fields.setdefault("started_at", db.now())
        elif fields["status"] in ("done", "failed", "cancelled"):
            fields.setdefault("finished_at", db.now())
    for key in ("message", "log"):
        if key in fields:
            fields[key] = redact(str(fields[key]))[-20000:]
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*fields.values(), task_id))


def get(conn: sqlite3.Connection, task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    reconcile(conn)
    return [dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,))]


def active_for(conn: sqlite3.Connection, kind: str, target: str) -> dict | None:
    reconcile(conn)
    row = conn.execute("SELECT * FROM tasks WHERE kind = ? AND target = ? AND status IN ('queued','running')"
                       " ORDER BY id DESC LIMIT 1", (kind, target)).fetchone()
    return dict(row) if row else None


def reconcile(conn: sqlite3.Connection) -> None:
    """Mark tasks whose child process is gone as failed (crash, reboot, kill)."""
    for row in conn.execute("SELECT id, pid, pid_start, status FROM tasks WHERE status IN ('queued','running')"
                            " AND pid IS NOT NULL").fetchall():
        if not procs.alive(row["pid"], row["pid_start"]):
            update(conn, row["id"], status="failed", message="The task process ended without reporting a result.")


def run_in_thread(db_file: Path, task_id: int, fn: Callable[[sqlite3.Connection, int], str]) -> None:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stackloom-task")

    def runner() -> None:
        conn = db.connect(db_file)
        update(conn, task_id, status="running")
        try:
            message = fn(conn, task_id)
            update(conn, task_id, status="done", message=message or "Done.")
        except Exception as exc:  # the task row is the error report
            message = getattr(exc, "detail", None) or str(exc)
            update(conn, task_id, status="failed", message=str(message), log=traceback.format_exc())
            _notify(conn, task_id, "error")
        else:
            _notify(conn, task_id, "info")
        finally:
            conn.close()

    _pool.submit(runner)


TASK_TITLES = {"runtime.start": "Start", "runtime.stop": "Stop", "runtime.restart": "Restart", "docker.pull": "Image pull",
               "docker.build": "Image build", "docker.volume_backup": "Volume backup", "db.backup": "Database backup",
               "db.drop_table": "Drop table", "db.drop_database": "Drop database", "discovery.scan": "Discovery",
               "codecortex.refresh": "Map refresh"}


def _notify(conn: sqlite3.Connection, task_id: int, level: str) -> None:
    from stackloom import notify

    t = get(conn, task_id) or {}
    title = TASK_TITLES.get(t.get("kind", ""), t.get("kind", "Task").replace("docker.compose_", "Compose "))
    verb = "failed" if level == "error" else "finished"
    notify.add(conn, f"{title} {verb}: {t.get('target', '')}".strip(": "), t.get("message", ""), level, "#/tasks")


def spawn(conn: sqlite3.Connection, task_id: int, module: str, args: list[str]) -> None:
    """Start `python -m module --task ID args...` detached, at low priority."""
    log_file = paths.log_dir() / f"task-{task_id}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", module, "--task", str(task_id), *args],
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, env=os.environ.copy(),
        )
    update(conn, task_id, pid=proc.pid, pid_start=procs.start_time(proc.pid))
