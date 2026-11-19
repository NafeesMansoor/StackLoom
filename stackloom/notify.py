"""Notifications shown under the bell in the dashboard."""
from __future__ import annotations

import sqlite3

from stackloom.db import now
from stackloom.security import redact


def add(conn: sqlite3.Connection, title: str, body: str = "", level: str = "info", link: str = "") -> None:
    conn.execute("INSERT INTO notifications (at, level, title, body, link) VALUES (?,?,?,?,?)",
                 (now(), level, redact(title)[:200], redact(body)[:2000], link))
    conn.execute("DELETE FROM notifications WHERE id NOT IN (SELECT id FROM notifications ORDER BY id DESC LIMIT 500)")


def recent(conn: sqlite3.Connection, limit: int = 50) -> dict:
    rows = [dict(r) for r in conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))]
    unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE read = 0").fetchone()[0]
    return {"unread": unread, "items": rows}


def mark_all_read(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
