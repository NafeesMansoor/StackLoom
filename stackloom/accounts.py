"""Accounts and sessions.

The first run creates one administrator. The brief asks for `admin` /
`1234567890@`; STACKLOOM_ADMIN_PASSWORD replaces that password. Either way the
account is flagged so the password must be changed at the first sign-in, and
the API refuses everything else until it is.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from stackloom import activity, security
from stackloom.db import now

BOOTSTRAP_USER = "admin"
_BOOTSTRAP_DEFAULT = "1234567890@"  # brief §13.4; must be changed at first sign-in
SESSION_HOURS = 12


class AuthError(Exception):
    pass


def bootstrap(conn: sqlite3.Connection) -> bool:
    """Create the first administrator if no account exists. Returns True if one was created.

    Runs in an IMMEDIATE transaction so two processes cannot both create it, and
    does nothing once any account exists, so it cannot be used to add accounts later.
    """
    password = os.environ.get("STACKLOOM_ADMIN_PASSWORD") or _BOOTSTRAP_DEFAULT
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            conn.execute("ROLLBACK")
            return False
        ts = now()
        conn.execute(
            "INSERT INTO users (username, password_hash, must_change_password, created_at, updated_at)"
            " VALUES (?,?,1,?,?)",
            (BOOTSTRAP_USER, security.hash_password(password), ts, ts),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    activity.record(conn, "system", "account.bootstrap", BOOTSTRAP_USER)
    return True


class _Throttle:
    """Slows repeated failed sign-ins per username: 5 free tries, then a growing wait."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fails: dict[str, list[float]] = {}

    def wait_needed(self, key: str) -> float:
        with self._lock:
            fails = [t for t in self._fails.get(key, []) if time.monotonic() - t < 900]
            self._fails[key] = fails
            if len(fails) < 5:
                return 0.0
            delay = min(300.0, 2.0 ** (len(fails) - 4))
            return max(0.0, fails[-1] + delay - time.monotonic())

    def fail(self, key: str) -> None:
        with self._lock:
            self._fails.setdefault(key, []).append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


throttle = _Throttle()


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict:
    key = username.lower()
    wait = throttle.wait_needed(key)
    if wait:
        raise AuthError(f"Too many failed attempts. Try again in {int(wait) + 1} seconds.")
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not security.verify_password(row["password_hash"], password):
        throttle.fail(key)
        activity.record(conn, username or "?", "auth.login", result="failed")
        raise AuthError("Wrong username or password.")
    throttle.clear(key)
    if security.needs_rehash(row["password_hash"]):
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (security.hash_password(password), row["id"]))
    activity.record(conn, username, "auth.login")
    return dict(row)


def create_session(conn: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    token, csrf = security.new_token(), security.new_token()
    created = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, csrf, created_at, expires_at) VALUES (?,?,?,?,?)",
        (security.token_hash(token), user_id, csrf, created.isoformat(timespec="seconds"),
         (created + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")),
    )
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
    return token, csrf


def session_user(conn: sqlite3.Connection, token: str | None) -> dict | None:
    if not token:
        return None
    row = conn.execute(
        "SELECT u.id, u.username, u.must_change_password, s.csrf, s.expires_at"
        " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (security.token_hash(token),),
    ).fetchone()
    if row is None or row["expires_at"] < now():
        return None
    return dict(row)


def end_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (security.token_hash(token),))


def change_password(conn: sqlite3.Connection, user_id: int, current: str, new: str) -> None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or not security.verify_password(row["password_hash"], current):
        raise AuthError("The current password is wrong.")
    problems = security.password_problems(new, row["username"])
    if new == current:
        problems.append("The new password must differ from the current one.")
    if problems:
        raise AuthError(" ".join(problems))
    conn.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?",
        (security.hash_password(new), now(), user_id),
    )
    activity.record(conn, row["username"], "auth.password_changed")


def reset_password(conn: sqlite3.Connection, username: str, new: str) -> None:
    """CLI-only recovery (`stackloom admin reset-password`). Ends that user's sessions."""
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise AuthError(f"No account named {username!r}.")
    problems = security.password_problems(new, username)
    if problems:
        raise AuthError(" ".join(problems))
    conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?",
                 (security.hash_password(new), now(), row["id"]))
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
    activity.record(conn, "cli", "auth.password_reset", username)
