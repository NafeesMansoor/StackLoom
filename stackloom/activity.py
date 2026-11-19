"""Audit and activity log. Every administrative action writes one row."""
from __future__ import annotations

import logging
import sqlite3

from stackloom.db import now
from stackloom.security import redact

log = logging.getLogger("stackloom")


def record(conn: sqlite3.Connection, actor: str, action: str, target: str = "",
           result: str = "ok", detail: str = "") -> None:
    detail = redact(detail)[:4000]
    conn.execute(
        "INSERT INTO activity (at, actor, action, target, result, detail) VALUES (?,?,?,?,?,?)",
        (now(), actor, action, target, result, detail),
    )
    log.info("%s %s %s -> %s", actor, action, target, result)


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
