"""Backup manager: one history for every kind of backup.

Kinds: stackloom (database + config), config (a project file), database,
volume, map (a CodeCortex map). Each backup is a file under
~/.stackloom/backups with its SHA-256 recorded, so it can be verified later.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from stackloom import activity, paths
from stackloom.db import now


class BackupError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stamp() -> str:
    """Time stamp for backup file names, to the millisecond."""
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]


def unique(path: Path) -> Path:
    """`path`, or path-2, path-3 ... if a backup with that name already exists. Never overwrites."""
    if not path.exists():
        return path
    name, suffix = (path.name[:-7], ".tar.gz") if path.name.endswith(".tar.gz") else (path.stem, path.suffix)
    n = 2
    while (candidate := path.with_name(f"{name}-{n}{suffix}")).exists():
        n += 1
    return candidate


def root() -> Path:
    path = paths.home() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def checked_path(path: Path | str) -> Path:
    path = Path(path).resolve()
    if root().resolve() not in path.parents:
        raise BackupError("Pick a backup from STACKLOOM's backup folder.")
    if not path.exists():
        raise BackupError("That backup file no longer exists.")
    return path


def register(conn: sqlite3.Connection, kind: str, target: str, path: Path, actor: str, note: str = "") -> dict[str, Any]:
    path.chmod(0o600)
    cur = conn.execute("INSERT INTO backups (kind, target, path, size, sha256, created_at, note, actor) VALUES (?,?,?,?,?,?,?,?)",
                       (kind, target, str(path), path.stat().st_size, _sha(path), now(), note, actor))
    activity.record(conn, actor, f"backup.{kind}", target, detail=path.name)
    apply_retention(conn)
    return get(conn, int(cur.lastrowid))


def get(conn: sqlite3.Connection, backup_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM backups WHERE id = ?", (backup_id,)).fetchone()
    if row is None:
        raise BackupError("No such backup.")
    out = dict(row)
    out["exists"] = Path(out["path"]).exists()
    return out


def history(conn: sqlite3.Connection, kind: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    sql = "SELECT * FROM backups" + (" WHERE kind = ?" if kind else "") + " ORDER BY id DESC LIMIT ?"
    rows = conn.execute(sql, (kind, limit) if kind else (limit,)).fetchall()
    return [{**dict(r), "exists": Path(r["path"]).exists()} for r in rows]


def verify(conn: sqlite3.Connection, backup_id: int) -> dict[str, Any]:
    item = get(conn, backup_id)
    path = Path(item["path"])
    if not path.exists():
        return {"ok": False, "detail": "The file is missing."}
    if _sha(path) != item["sha256"]:
        return {"ok": False, "detail": "The file changed since it was made (checksum differs)."}
    detail = "Checksum matches."
    try:
        if path.suffix in (".sqlite", ".db"):
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                result = con.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                con.close()
            if result != "ok":
                return {"ok": False, "detail": f"SQLite integrity check: {result}"}
            detail += " SQLite integrity check passed."
        elif path.name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(path) as tar:
                detail += f" Archive lists {len(tar.getmembers())} entries."
    except (sqlite3.Error, tarfile.TarError) as exc:
        return {"ok": False, "detail": str(exc)}
    conn.execute("UPDATE backups SET verified_at = ? WHERE id = ?", (now(), backup_id))
    return {"ok": True, "detail": detail}


def delete(conn: sqlite3.Connection, backup_id: int, actor: str, confirm: bool) -> None:
    if not confirm:
        raise BackupError("Deleting a backup cannot be undone. Confirm to continue.")
    item = get(conn, backup_id)
    Path(item["path"]).unlink(missing_ok=True)
    conn.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
    activity.record(conn, actor, "backup.delete", item["target"], detail=Path(item["path"]).name)


# --------------------------------------------------------------------------- STACKLOOM's own state

def backup_stackloom(conn: sqlite3.Connection, actor: str, note: str = "") -> dict[str, Any]:
    """Consistent copy of stackloom.db (SQLite backup API) plus config.toml, in one tar.gz."""
    out_dir = root() / "stackloom"
    out_dir.mkdir(parents=True, exist_ok=True)
    when = stamp()
    snapshot = unique(out_dir / f"stackloom-{when}.db")
    dest = sqlite3.connect(snapshot)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    archive = unique(out_dir / f"stackloom-{when}.tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(snapshot, arcname="stackloom.db")
        if paths.config_path().exists():
            tar.add(paths.config_path(), arcname="config.toml")
    snapshot.unlink()
    return register(conn, "stackloom", "STACKLOOM registry and settings", archive, actor, note)


def restore_stackloom(archive: Path, base: Path | None = None) -> str:
    """CLI only, with the dashboard stopped. Current state is archived next to the backup first."""
    base = base or paths.home()
    archive = checked_path(archive)
    current = paths.db_path(base)
    when = stamp()
    keep = unique(root() / "stackloom" / f"before-restore-{when}.db")
    if current.exists():
        src = sqlite3.connect(current)
        dst = sqlite3.connect(keep)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
        if "stackloom.db" not in names:
            raise BackupError("This archive is not a STACKLOOM backup.")
        member = tar.extractfile("stackloom.db")
        assert member is not None
        tmp = current.with_suffix(".restore")
        tmp.write_bytes(member.read())
        for suffix in ("-wal", "-shm"):
            Path(str(current) + suffix).unlink(missing_ok=True)
        tmp.replace(current)
        if "config.toml" in names:
            cfg = tar.extractfile("config.toml")
            assert cfg is not None
            paths.config_path(base).write_bytes(cfg.read())
    return f"Restored from {archive.name}. The previous database was kept as {keep.name}."


def backup_map(conn: sqlite3.Connection, project: dict[str, Any], actor: str) -> dict[str, Any]:
    from stackloom.maps import map_dir

    directory = map_dir(project["path"])
    if not (directory / "graph.db").exists():
        raise BackupError("This project has no map to back up.")
    out_dir = root() / "maps"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = unique(out_dir / f"{project['id']}-{stamp()}.tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(directory, arcname=".codecortex")
    return register(conn, "map", project["id"], archive, actor)


def backup_config_file(conn: sqlite3.Connection, project: dict[str, Any], rel: str, actor: str) -> dict[str, Any]:
    from stackloom.envfiles import _inside, backup_file

    path = _inside(Path(project["path"]), rel)
    if not path.is_file():
        raise BackupError(f"No file {rel}.")
    return register(conn, "config", f"{project['id']}/{rel}", backup_file(path), actor)


# --------------------------------------------------------------------------- schedule and retention

def settings(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM settings WHERE key = 'backups'").fetchone()
    defaults = {"daily_stackloom": True, "keep_per_kind": 10}
    return {**defaults, **(json.loads(row["value"]) if row else {})}


def save_settings(conn: sqlite3.Connection, daily: bool, keep: int, actor: str) -> dict[str, Any]:
    value = {"daily_stackloom": bool(daily), "keep_per_kind": max(1, min(int(keep), 500))}
    conn.execute("INSERT INTO settings (key, value) VALUES ('backups', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (json.dumps(value),))
    activity.record(conn, actor, "backup.settings", detail=json.dumps(value))
    return value


def apply_retention(conn: sqlite3.Connection) -> int:
    keep = settings(conn)["keep_per_kind"]
    removed = 0
    for (kind, target) in conn.execute("SELECT DISTINCT kind, target FROM backups").fetchall():
        old = conn.execute("SELECT id, path FROM backups WHERE kind = ? AND target = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                           (kind, target, keep)).fetchall()
        for row in old:
            Path(row["path"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM backups WHERE id = ?", (row["id"],))
            removed += 1
    return removed


def scheduled(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Called by the dashboard's background check: one STACKLOOM backup a day when enabled."""
    if not settings(conn)["daily_stackloom"]:
        return None
    last = conn.execute("SELECT created_at FROM backups WHERE kind = 'stackloom' ORDER BY id DESC LIMIT 1").fetchone()
    if last and datetime.fromisoformat(last[0]) > datetime.now(timezone.utc) - timedelta(days=1):
        return None
    return backup_stackloom(conn, "system", "daily")
