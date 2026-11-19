"""Connection manager, password handling, discovery and backups.

Passwords are never stored in STACKLOOM's database. A connection names where
its password comes from:

  none              no password
  keychain          the OS credential store (needs `keyring`, extra `secrets`)
  env:<file>|<KEY>  read from the project's own env file at connect time; if the
                    value is a URL, its password part is used
  session           typed in the dashboard, kept in memory until it stops
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from stackloom import activity, paths, registry
from stackloom.databases.base import Adapter, ConnInfo, DbError
from stackloom.db import now
from stackloom.runtime import port_in_use, read_env_file

ENGINES = {"sqlite", "postgres", "mysql", "mariadb", "mongodb", "redis"}
DEFAULT_PORTS = {"postgres": 5432, "mysql": 3306, "mariadb": 3306, "mongodb": 27017, "redis": 6379}
SCHEMES = {"postgres": "postgres", "postgresql": "postgres", "postgresql+psycopg": "postgres",
           "postgresql+psycopg2": "postgres", "postgresql+asyncpg": "postgres", "mysql": "mysql",
           "mysql+pymysql": "mysql", "mariadb": "mariadb", "mongodb": "mongodb", "mongodb+srv": "mongodb",
           "redis": "redis", "rediss": "redis", "sqlite": "sqlite"}
IMAGE_ENGINES = {"postgres": "postgres", "postgis": "postgres", "mysql": "mysql", "mariadb": "mariadb",
                 "mongo": "mongodb", "redis": "redis", "valkey": "redis"}
SERVICE = "stackloom-db"

_session_passwords: dict[str, str] = {}
_cache: dict[str, tuple[Adapter, float]] = {}
_lock = threading.Lock()


# --------------------------------------------------------------------------- registry

def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["read_only"] = bool(d["read_only"])
    d["has_session_password"] = d["id"] in _session_passwords
    return d


def list_connections(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_row(r) for r in conn.execute("SELECT * FROM db_connections ORDER BY name")]


def get(conn: sqlite3.Connection, conn_id: str) -> dict[str, Any]:
    r = conn.execute("SELECT * FROM db_connections WHERE id = ?", (conn_id,)).fetchone()
    if r is None:
        raise DbError(f"No connection {conn_id!r}.")
    return _row(r)


def save(conn: sqlite3.Connection, data: dict[str, Any], actor: str, password: str | None = None) -> dict[str, Any]:
    engine = data.get("engine")
    if engine not in ENGINES:
        raise DbError(f"Unknown engine {engine!r}. Choose one of: {', '.join(sorted(ENGINES))}.")
    if engine == "sqlite":
        if not data.get("path") or not Path(data["path"]).expanduser().is_absolute():
            raise DbError("Give the full path of the SQLite file.")
    elif not data.get("host"):
        raise DbError("Give the host, for example 127.0.0.1.")
    source = data.get("password_source") or "none"
    if not (source in ("none", "keychain", "session") or source.startswith("env:")):
        raise DbError("Unknown password source.")
    conn_id = data.get("id") or registry.unique_db_id(conn, data.get("name") or engine)
    conn.execute(
        "INSERT INTO db_connections (id, name, engine, host, port, database, username, path, project_id, container, read_only,"
        " password_source, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
        " name=excluded.name, engine=excluded.engine, host=excluded.host, port=excluded.port, database=excluded.database,"
        " username=excluded.username, path=excluded.path, project_id=excluded.project_id, container=excluded.container,"
        " read_only=excluded.read_only, password_source=excluded.password_source",
        (conn_id, data.get("name") or conn_id, engine, data.get("host", ""), data.get("port") or DEFAULT_PORTS.get(engine),
         data.get("database", ""), data.get("username", ""), str(Path(data["path"]).expanduser()) if data.get("path") else "",
         data.get("project_id"), data.get("container", ""), int(bool(data.get("read_only", True))), source,
         data.get("source", "manual"), now()))
    if password:
        set_password(conn_id, source, password)
    forget(conn_id)
    activity.record(conn, actor, "db.connection_save", conn_id)
    return get(conn, conn_id)


def remove(conn: sqlite3.Connection, conn_id: str, actor: str) -> None:
    item = get(conn, conn_id)
    conn.execute("DELETE FROM db_connections WHERE id = ?", (conn_id,))
    _session_passwords.pop(conn_id, None)
    if item["password_source"] == "keychain":
        try:
            import keyring

            keyring.delete_password(SERVICE, conn_id)
        except Exception:
            pass
    forget(conn_id)
    activity.record(conn, actor, "db.connection_remove", conn_id)


# --------------------------------------------------------------------------- passwords

def set_password(conn_id: str, source: str, password: str) -> None:
    if source == "keychain":
        try:
            import keyring

            keyring.set_password(SERVICE, conn_id, password)
        except ImportError:
            raise DbError("The OS credential store needs the 'keyring' package: pipx inject stackloom keyring.")
    elif source == "session":
        _session_passwords[conn_id] = password
    else:
        raise DbError("This connection does not take a typed password.")


def password_for(item: dict[str, Any]) -> str | None:
    source = item["password_source"]
    if source == "none":
        return None
    if source == "session":
        if item["id"] not in _session_passwords:
            raise DbError("Enter this connection's password (kept in memory until STACKLOOM stops).")
        return _session_passwords[item["id"]]
    if source == "keychain":
        try:
            import keyring
        except ImportError:
            raise DbError("The OS credential store needs the 'keyring' package: pipx inject stackloom keyring.")
        value = keyring.get_password(SERVICE, item["id"])
        if value is None:
            raise DbError("No password saved in the credential store for this connection yet.")
        return value
    _, _, spec = source.partition(":")
    file, _, key = spec.rpartition("|")
    value = read_env_file(Path(file)).get(key)
    if value is None:
        raise DbError(f"{key} is not set in {file}.")
    if "://" in value:
        return unquote(urlsplit(value).password or "") or None
    return value


# --------------------------------------------------------------------------- adapters

def _make(item: dict[str, Any]) -> Adapter:
    info = ConnInfo(id=item["id"], engine=item["engine"], host=item["host"], port=item["port"], database=item["database"],
                    username=item["username"], path=item["path"], read_only=item["read_only"])
    engine = item["engine"]
    if engine == "sqlite":
        from stackloom.databases.sqlite import SqliteAdapter
        return SqliteAdapter(info, None)
    password = password_for(item)
    if engine == "postgres":
        from stackloom.databases.postgres import PostgresAdapter
        return PostgresAdapter(info, password)
    if engine in ("mysql", "mariadb"):
        from stackloom.databases.mysql import MysqlAdapter
        return MysqlAdapter(info, password)
    from stackloom.databases.nosql import MongoAdapter, RedisAdapter
    return MongoAdapter(info, password) if engine == "mongodb" else RedisAdapter(info, password)


def adapter(conn: sqlite3.Connection, conn_id: str) -> Adapter:
    """An open adapter, reused for a few minutes, then closed."""
    with _lock:
        for key, (ad, used) in list(_cache.items()):
            if time.monotonic() - used > 300:
                try:
                    ad.close()
                except Exception:
                    pass
                _cache.pop(key, None)
        if conn_id in _cache:
            ad = _cache[conn_id][0]
        else:
            ad = _make(get(conn, conn_id))
        _cache[conn_id] = (ad, time.monotonic())
        return ad


def forget(conn_id: str) -> None:
    with _lock:
        entry = _cache.pop(conn_id, None)
    if entry:
        try:
            entry[0].close()
        except Exception:
            pass


def test(conn: sqlite3.Connection, conn_id: str) -> dict[str, Any]:
    forget(conn_id)
    started = time.monotonic()
    info = adapter(conn, conn_id).server()
    return {**info, "ms": int((time.monotonic() - started) * 1000)}


def record_query(conn: sqlite3.Connection, conn_id: str, database: str, sql: str, actor: str,
                 ms: int | None, rows: int | None, error: str = "") -> None:
    conn.execute("INSERT INTO query_history (connection_id, database, sql, at, ms, rows, error, actor) VALUES (?,?,?,?,?,?,?,?)",
                 (conn_id, database, sql[:20000], now(), ms, rows, error[:2000], actor))
    conn.execute("DELETE FROM query_history WHERE id NOT IN (SELECT id FROM query_history ORDER BY id DESC LIMIT 2000)")


def history(conn: sqlite3.Connection, conn_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM query_history WHERE connection_id = ? ORDER BY id DESC LIMIT ?",
                                          (conn_id, limit))]


# --------------------------------------------------------------------------- discovery

def parse_url(value: str) -> dict[str, Any] | None:
    """Engine, host, port, database and user of a connection URL. The password is not returned."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    engine = SCHEMES.get(parts.scheme.lower())
    if not engine:
        return None
    if engine == "sqlite":
        return {"engine": "sqlite", "path": parts.path[1:]}  # sqlite:///rel.db -> rel.db, sqlite:////abs.db -> /abs.db
    try:
        port = parts.port
    except ValueError:
        port = None
    return {"engine": engine, "host": parts.hostname or "", "port": port or DEFAULT_PORTS.get(engine),
            "database": parts.path.lstrip("/").split("?")[0] if engine != "redis" else (parts.path.lstrip("/") or "0"),
            "username": unquote(parts.username or ""), "has_password": bool(parts.password)}


def _sqlite_files(root: Path, limit: int = 30) -> list[Path]:
    from stackloom.discovery import SKIP_DIRS

    found = []
    for path in sorted(root.rglob("*")):
        if len(found) >= limit:
            break
        if any(part in SKIP_DIRS or part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        if path.suffix.lower() in (".db", ".sqlite", ".sqlite3") and path.is_file():
            try:
                with path.open("rb") as fh:
                    if fh.read(16) == b"SQLite format 3\x00":
                        found.append(path)
            except OSError:
                pass
    return found


def discover(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Candidate connections. Each is unverified until a test connects with the engine's protocol."""
    known = {(c["engine"], c["host"], c["port"], c["database"], c["path"]) for c in list_connections(conn)}
    found: list[dict[str, Any]] = []

    def add(entry: dict[str, Any]) -> None:
        key = (entry["engine"], entry.get("host", ""), entry.get("port"), entry.get("database", ""), entry.get("path", ""))
        if key not in known:
            known.add(key)
            found.append(entry)

    for project in registry.list_projects(conn):
        root = Path(project["path"])
        if not root.is_dir():
            continue
        for env in sorted(root.glob(".env*")) + sorted(root.glob("*/.env*")):
            if not env.is_file() or env.name.endswith((".example", ".sample", ".template")):
                continue
            for key, value in read_env_file(env).items():
                if not re.search(r"(DATABASE|DB|POSTGRES|MYSQL|MONGO|REDIS|CACHE)[A-Z_]*_?(URL|URI|DSN)$", key):
                    continue
                parsed = parse_url(value)
                if not parsed or parsed["engine"] == "sqlite":
                    continue
                add({**{k: v for k, v in parsed.items() if k != "has_password"}, "name": f"{project['id']} {key.lower()}",
                     "project_id": project["id"], "evidence": f"{key} in {env.relative_to(root)}",
                     "password_source": f"env:{env}|{key}" if parsed["has_password"] else "none", "source": "env"})
        for db_file in _sqlite_files(root):
            add({"engine": "sqlite", "path": str(db_file), "name": f"{project['id']} {db_file.stem}", "project_id": project["id"],
                 "evidence": f"SQLite file {db_file.relative_to(root)}", "password_source": "none", "source": "file"})

    try:
        from stackloom import docker

        if docker.info()["available"]:
            for c in docker.containers():
                image = c["image"].split("/")[-1].split(":")[0]
                engine = next((e for prefix, e in IMAGE_ENGINES.items() if image.startswith(prefix)), None)
                if not engine:
                    continue
                match = re.search(r"(?:127\.0\.0\.1|0\.0\.0\.0|\[::\]|::):(\d+)->(\d+)/tcp", c["ports"])
                project = registry.containing(conn, c["working_dir"]) if c["working_dir"] else None
                add({"engine": engine, "host": "127.0.0.1", "port": int(match.group(1)) if match else None,
                     "database": "", "name": f"{c['name']} ({engine})", "container": c["name"],
                     "project_id": project["id"] if project else None, "password_source": "session", "source": "docker",
                     "evidence": f"container {c['name']} ({c['state']})" + ("" if match else ", no published port")})
    except Exception:
        pass

    for engine, port in (("postgres", 5432), ("mysql", 3306), ("mongodb", 27017), ("redis", 6379)):
        if port_in_use(port):
            add({"engine": engine, "host": "127.0.0.1", "port": port, "database": "", "name": f"local {engine} on {port}",
                 "password_source": "session", "source": "port",
                 "evidence": f"something listens on {port}; not verified until you test the connection"})
    return found


# --------------------------------------------------------------------------- backups

def backup(conn: sqlite3.Connection, conn_id: str, database: str, actor: str) -> dict[str, Any]:
    """Dump a database to ~/.stackloom/backups/databases with the engine's own tool."""
    from stackloom import backups

    item = get(conn, conn_id)
    out_dir = paths.home() / "backups" / "databases"
    out_dir.mkdir(parents=True, exist_ok=True)
    from stackloom.backups import stamp as make_stamp, unique

    stamp = make_stamp()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{conn_id}-{database or item['database'] or 'main'}")
    engine = item["engine"]
    if engine == "sqlite":
        from stackloom.databases.sqlite import SqliteAdapter

        target = unique(out_dir / f"{safe}-{stamp}.sqlite")
        ad = adapter(conn, conn_id)
        assert isinstance(ad, SqliteAdapter)
        ad.backup_to(target)
    elif engine == "postgres":
        tool = shutil.which("pg_dump")
        if not tool:
            raise DbError("pg_dump is not installed (brew install libpq).")
        target = unique(out_dir / f"{safe}-{stamp}.dump")
        env = {"PGPASSWORD": password_for(item) or ""}
        _dump([tool, "-Fc", "-h", item["host"], "-p", str(item["port"] or 5432), "-U", item["username"] or "postgres",
               "-f", str(target), database or item["database"] or "postgres"], env)
    elif engine in ("mysql", "mariadb"):
        tool = shutil.which("mysqldump") or shutil.which("mariadb-dump")
        if not tool:
            raise DbError("mysqldump is not installed (brew install mysql-client).")
        target = unique(out_dir / f"{safe}-{stamp}.sql")
        env = {"MYSQL_PWD": password_for(item) or ""}
        with target.open("wb") as fh:
            _dump([tool, "-h", item["host"], "-P", str(item["port"] or 3306), "-u", item["username"] or "root",
                   "--single-transaction", "--routines", database or item["database"]], env, stdout=fh)
    else:
        raise DbError(f"Backups for {engine} are not supported yet. Use the engine's own tools.")
    return backups.register(conn, "database", f"{conn_id}/{database or item['database'] or 'main'}", target, actor)


def _dump(command: list[str], env: dict[str, str], stdout=None) -> None:
    import os

    result = subprocess.run(command, env={**os.environ, **env}, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=3600, check=False)
    if result.returncode != 0:
        from stackloom.security import redact

        raise DbError(redact(result.stderr.decode(errors="replace").strip() or "The dump failed."))


def restore_sqlite(conn: sqlite3.Connection, conn_id: str, backup_path: Path, actor: str) -> str:
    """Replace a SQLite file with a backup, after backing up the current file first."""
    from stackloom import backups

    item = get(conn, conn_id)
    if item["engine"] != "sqlite":
        raise DbError("Restore from the dashboard is available for SQLite. For servers use pg_restore or mysql.")
    if item["read_only"]:
        raise DbError("This connection is read-only.")
    backup(conn, conn_id, "main", actor)
    forget(conn_id)
    src = sqlite3.connect(f"file:{backups.checked_path(backup_path)}?mode=ro", uri=True)
    dest = sqlite3.connect(item["path"])
    try:
        src.backup(dest)
    finally:
        src.close()
        dest.close()
    activity.record(conn, actor, "db.restore", conn_id, detail=backup_path.name)
    return f"Restored {Path(item['path']).name} from {backup_path.name}. The previous contents were backed up first."


def export_csv(result: dict[str, Any]) -> str:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(result.get("columns", []))
    for row in result.get("rows", []):
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue()


def to_json(value: Any) -> str:
    return json.dumps(value, default=str)
