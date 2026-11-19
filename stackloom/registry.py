"""The project registry, stored in SQLite.

Rules carried over from the ResearchOS admin: no credentials, no hard-coded
host:port (services use ${PORT:<service>}), loopback hosts only, and start
commands are argument lists, never shell strings. Registering a project never
writes anything into the project folder.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from stackloom import activity
from stackloom.db import now
from stackloom.security import LOOKS_LIKE_CREDENTIAL

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LAUNCH_TYPES = {"process", "docker-compose"}
PORT_PLACEHOLDER = re.compile(r"\$\{PORT:([a-z0-9_-]+)\}")
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


class RegistryError(ValueError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "project"


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def validate(project: dict[str, Any]) -> None:
    pid = project.get("id")
    if not isinstance(pid, str) or not ID_RE.fullmatch(pid):
        raise RegistryError(f"invalid project id: {pid!r}")
    path = project.get("path")
    if not path or not Path(path).is_absolute():
        raise RegistryError(f"{pid}: 'path' must be an absolute path")
    if LOOKS_LIKE_CREDENTIAL.search(json.dumps(project)):
        raise RegistryError(f"{pid}: entry appears to contain a credential; keep secrets in the project's env files")
    names = set()
    for service in project.get("services", []):
        name = service.get("name")
        if not name or not re.fullmatch(r"[a-z0-9_-]+", name):
            raise RegistryError(f"{pid}: invalid service name {name!r}")
        names.add(name)
        if "port" in service:
            raise RegistryError(f"{pid}/{name}: hard-coded 'port' is not allowed; STACKLOOM assigns ports")
        host = service.get("host", "127.0.0.1")
        if host not in LOOPBACK and not service.get("allow_non_loopback"):
            raise RegistryError(f"{pid}/{name}: host {host} is not loopback")
    for ref in PORT_PLACEHOLDER.findall(json.dumps(project)):
        if ref not in names:
            raise RegistryError(f"{pid}: ${{PORT:{ref}}} refers to an undeclared service")
    for text in _strings({k: v for k, v in project.items() if k not in ("notes", "description")}):
        if re.search(r"(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}", text):
            raise RegistryError(f"{pid}: hard-coded host:port in {text!r}; use ${{PORT:<service>}}")
    launch = project.get("launch")
    if launch:
        kind = launch.get("type")
        if kind not in LAUNCH_TYPES:
            raise RegistryError(f"{pid}: unknown launch type {kind!r}")
        if kind == "process":
            comps = launch["processes"] if "processes" in launch else [launch]
            for comp in comps:
                cmd = comp.get("command")
                if not (isinstance(cmd, list) and cmd and all(isinstance(a, str) for a in cmd)):
                    raise RegistryError(f"{pid}: a start command must be a list of arguments (no shell strings)")
        if kind == "docker-compose" and not launch.get("compose_project"):
            raise RegistryError(f"{pid}: docker-compose launch needs 'compose_project'")
    if project.get("safe_to_launch") and not launch:
        raise RegistryError(f"{pid}: safe_to_launch requires a 'launch' block")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    data = json.loads(row["data"])
    data.update(id=row["id"], path=row["path"], group=row["group_name"], source=row["source"],
                created_at=row["created_at"], updated_at=row["updated_at"])
    return data


def list_projects(conn: sqlite3.Connection, group: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM projects" + (" WHERE group_name = ?" if group else "") + " ORDER BY group_name, id"
    return [_row(r) for r in conn.execute(sql, (group,) if group else ())]


def get(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise RegistryError(f"No project with id {project_id!r}. `stackloom projects` lists them.")
    return _row(row)


def find_by_path(conn: sqlite3.Connection, path: str | Path) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM projects WHERE path = ?", (str(Path(path).resolve()),)).fetchone()
    return _row(row) if row else None


def containing(conn: sqlite3.Connection, path: str | Path) -> dict[str, Any] | None:
    """The registered project whose folder holds `path` (deepest match)."""
    target = Path(path).resolve()
    best = None
    for row in conn.execute("SELECT * FROM projects"):
        root = Path(row["path"])
        if target == root or root in target.parents:
            if best is None or len(str(root)) > len(best["path"]):
                best = _row(row)
    return best


def unique_id(conn: sqlite3.Connection, wanted: str) -> str:
    base, n, candidate = slug(wanted), 2, slug(wanted)
    while conn.execute("SELECT 1 FROM projects WHERE id = ?", (candidate,)).fetchone():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def unique_db_id(conn: sqlite3.Connection, wanted: str) -> str:
    base, n, candidate = slug(wanted), 2, slug(wanted)
    while conn.execute("SELECT 1 FROM db_connections WHERE id = ?", (candidate,)).fetchone():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


_COLUMNS = {"id", "path", "group", "source", "created_at", "updated_at"}


def save(conn: sqlite3.Connection, project: dict[str, Any], source: str, actor: str = "system") -> dict[str, Any]:
    project = dict(project)
    project["path"] = str(Path(project["path"]).resolve())
    validate(project)
    data = {k: v for k, v in project.items() if k not in _COLUMNS}
    group = project.get("group") or "inbox"
    ts = now()
    conn.execute(
        "INSERT INTO projects (id, path, group_name, source, data, created_at, updated_at) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(id) DO UPDATE SET path=excluded.path, group_name=excluded.group_name,"
        " data=excluded.data, updated_at=excluded.updated_at",
        (project["id"], project["path"], group, source, json.dumps(data), ts, ts),
    )
    conn.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (group,))
    activity.record(conn, actor, "project.save", project["id"], detail=project["path"])
    return get(conn, project["id"])


def remove(conn: sqlite3.Connection, project_id: str, actor: str) -> None:
    """Forget a project. Its folder, files and CodeCortex map are left alone."""
    get(conn, project_id)
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    activity.record(conn, actor, "project.unregister", project_id)


def groups(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT g.name, g.description, COUNT(p.id) AS projects FROM groups g"
        " LEFT JOIN projects p ON p.group_name = g.name GROUP BY g.name ORDER BY g.name"
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- ResearchOS import

def import_researchos(conn: sqlite3.Connection, researchos_root: Path, actor: str = "cli") -> dict[str, Any]:
    """Copy the ResearchOS admin registry and its port assignments into STACKLOOM.

    Reads ResearchOS/registry/projects.json and admin/.state/ports.json; writes
    nothing back. Existing STACKLOOM entries with the same path are kept.
    """
    researchos_root = researchos_root.resolve()
    reg_path = researchos_root / "registry" / "projects.json"
    if not reg_path.exists():
        raise RegistryError(f"No ResearchOS registry at {reg_path}")
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    base = (researchos_root / data.get("base", ".")).resolve()

    def expand(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("${RESEARCHOS}", str(researchos_root)).replace("${WORKSPACE}", str(base))
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value

    def absolute(rel: str) -> str:
        return str((base / expand(rel)).resolve())

    for name, desc in data.get("groups", {}).items():
        conn.execute("INSERT INTO groups (name, description) VALUES (?,?)"
                     " ON CONFLICT(name) DO UPDATE SET description=excluded.description", (name, desc))

    imported, skipped = [], []
    for entry in data.get("projects", []):
        entry = expand(entry)
        path = absolute(entry["path"])
        if find_by_path(conn, path):
            skipped.append(entry["id"])
            continue
        project = {k: v for k, v in entry.items() if k not in ("display_name", "repo_root", "docs")}
        project.update(
            id=entry["id"] if not conn.execute("SELECT 1 FROM projects WHERE id=?", (entry["id"],)).fetchone()
            else unique_id(conn, entry["id"]),
            name=entry.get("display_name", entry["id"]),
            path=path,
            group=entry.get("group", "inbox"),
        )
        if entry.get("repo_root"):
            project["repo_root"] = absolute(entry["repo_root"])
        if entry.get("docs"):
            project["docs"] = [absolute(d) for d in entry["docs"]]
        launch = project.get("launch") or {}
        for key in ("cwd",):
            if launch.get(key):
                launch[key] = absolute(launch[key])
        for proc in launch.get("processes", []):
            if proc.get("cwd"):
                proc["cwd"] = absolute(proc["cwd"])
        if launch.get("compose_files"):
            launch["compose_files"] = [absolute(f) if not Path(f).is_absolute() else f for f in launch["compose_files"]]
        for proc in launch.get("processes", []) + [launch]:
            for value in (proc.get("env") or {}).values():
                if isinstance(value, dict) and value.get("from_env_file"):
                    value["from_env_file"] = absolute(value["from_env_file"])
        try:
            save(conn, project, source="researchos", actor=actor)
            imported.append(project["id"])
        except RegistryError as exc:
            skipped.append(f"{entry['id']} ({exc})")

    ports_path = researchos_root / "admin" / ".state" / "ports.json"
    ports_copied = 0
    if ports_path.exists():
        book = json.loads(ports_path.read_text(encoding="utf-8"))
        for pid, services in book.get("assignments", {}).items():
            if pid not in imported:
                continue
            for service, a in services.items():
                try:
                    conn.execute("INSERT INTO ports (project_id, service, port, pinned) VALUES (?,?,?,?)",
                                 (pid, service, int(a["port"]), int(bool(a.get("pinned")))))
                    ports_copied += 1
                except sqlite3.IntegrityError:
                    pass
    activity.record(conn, actor, "registry.import_researchos", str(reg_path),
                    detail=f"{len(imported)} imported, {len(skipped)} skipped, {ports_copied} ports")
    return {"imported": imported, "skipped": skipped, "ports": ports_copied}
