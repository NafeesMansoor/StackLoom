"""CodeCortex maps: one per project, kept where coding agents look for them.

CodeCortex (`codecortex-engine`, installed once with STACKLOOM) saves each
project's map in `<project>/.codecortex/`. Its agent tools (`codecortex
query`, `explain`, the Claude Code hook) read it from there, so STACKLOOM
does not move it. STACKLOOM keeps the central record: which projects have a
map, when it was refreshed, and its size.

Reading a map's statistics uses sqlite3 on graph.db and never imports the
engine. Refreshing runs in a detached child process (stackloom.cc_refresh),
so the engine's memory is released when it finishes.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stackloom import activity, discovery, registry, tasks
from stackloom.db import now

MAP_DIR = ".codecortex"
TASK_KIND = "codecortex.refresh"


def map_dir(project_path: str | Path) -> Path:
    return Path(project_path) / MAP_DIR


def read_stats(project_path: str | Path) -> dict[str, Any]:
    """What the saved map holds. Empty dict if there is no map."""
    directory = map_dir(project_path)
    state_file = directory / "state.json"
    if not state_file.exists():
        return {}
    stats: dict[str, Any] = {}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        stats.update(
            saved_at=state.get("saved_at"),
            codecortex_version=state.get("codecortex_version"),
            languages=state.get("languages") or [],
            files=len(state.get("files") or {}),
            derived_stale=bool(state.get("derived_stale")),
        )
    except (OSError, ValueError):
        stats["error"] = "state.json could not be read"
    graph = directory / "graph.db"
    if graph.exists():
        try:
            con = sqlite3.connect(f"file:{graph}?mode=ro", uri=True, timeout=2)
            try:
                stats["nodes"] = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                stats["edges"] = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            finally:
                con.close()
        except sqlite3.Error as exc:
            stats["error"] = f"graph.db: {exc}"
        stats["size_bytes"] = sum(f.stat().st_size for f in directory.iterdir() if f.is_file())
    return stats


def _saved_at(stats: dict[str, Any]) -> str | None:
    value = stats.get("saved_at")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    return value


def sync(conn: sqlite3.Connection, project: dict[str, Any]) -> dict[str, Any]:
    """Refresh STACKLOOM's record of a project's map from disk."""
    stats = read_stats(project["path"])
    status = "ready" if stats.get("nodes") is not None else ("error" if stats.get("error") else "none")
    conn.execute(
        "INSERT INTO maps (project_id, map_dir, last_refresh, status, stats) VALUES (?,?,?,?,?)"
        " ON CONFLICT(project_id) DO UPDATE SET map_dir=excluded.map_dir,"
        " last_refresh=MAX(COALESCE(maps.last_refresh,''), COALESCE(excluded.last_refresh,'')),"
        " status=excluded.status, stats=excluded.stats",
        (project["id"], str(map_dir(project["path"])), _saved_at(stats), status, json.dumps(stats)),
    )
    return get(conn, project["id"])


def get(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM maps WHERE project_id = ?", (project_id,)).fetchone()
    if row is None:
        return {"project_id": project_id, "status": "none", "stats": {}}
    out = dict(row)
    out["stats"] = json.loads(out["stats"] or "{}")
    running = tasks.active_for(conn, TASK_KIND, project_id)
    if running:
        out["status"] = "refreshing"
        out["task_id"] = running["id"]
    return out


def all_maps(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for project in registry.list_projects(conn):
        item = get(conn, project["id"])
        item.update(name=project.get("name", project["id"]), path=project["path"], group=project["group"])
        out.append(item)
    return out


def refresh(conn: sqlite3.Connection, project: dict[str, Any], actor: str, reason: str = "manual",
            rebuild: bool = False) -> dict[str, Any]:
    """Queue an incremental refresh (or a full rebuild). Returns the task.

    At most one refresh per project runs at a time; a second request returns
    the running task.
    """
    running = tasks.active_for(conn, TASK_KIND, project["id"])
    if running:
        return running
    problem = discovery.looks_indexable(Path(project["path"]))
    if problem:
        raise registry.RegistryError(f"{project['id']}: not indexed because {problem}.")
    task_id = tasks.create(conn, TASK_KIND, project["id"], actor)
    tasks.update(conn, task_id, message=f"Queued ({reason}).")
    args = ["--project", project["id"], project["path"]] + (["--rebuild"] if rebuild else [])
    tasks.spawn(conn, task_id, "stackloom.cc_refresh", args)
    activity.record(conn, actor, "codecortex.refresh" if not rebuild else "codecortex.rebuild", project["id"],
                    detail=reason)
    return tasks.get(conn, task_id) or {"id": task_id}


# --------------------------------------------------------------------------- recently opened projects

def claude_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _session_cwd(session_file: Path) -> str | None:
    """The working folder recorded in a Claude Code session file (only the `cwd` key is read)."""
    try:
        with session_file.open("r", encoding="utf-8", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    cwd = json.loads(line).get("cwd")
                except ValueError:
                    continue
                if cwd:
                    return cwd
    except OSError:
        return None
    return None


def recently_opened(window_hours: int = 72, base: Path | None = None) -> list[dict[str, Any]]:
    """Folders opened in Claude Code within the window, newest first."""
    base = base or claude_projects_dir()
    cutoff = time.time() - window_hours * 3600
    found: dict[str, float] = {}
    try:
        folders = [d for d in base.iterdir() if d.is_dir()]
    except OSError:
        return []
    for folder in folders:
        try:
            if folder.stat().st_mtime < cutoff:
                continue
            sessions = sorted((f for f in folder.glob("*.jsonl")), key=lambda f: f.stat().st_mtime, reverse=True)
        except OSError:
            continue
        if not sessions:
            continue
        newest = sessions[0].stat().st_mtime
        if newest < cutoff:
            continue
        cwd = _session_cwd(sessions[0])
        if cwd:
            found[cwd] = max(found.get(cwd, 0.0), newest)
    return [{"path": p, "last_opened": datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")}
            for p, t in sorted(found.items(), key=lambda kv: kv[1], reverse=True)]


def note_opened(conn: sqlite3.Connection, folder: str | Path, actor: str, register_new: bool,
                when: str | None = None) -> dict[str, Any]:
    """A coding agent opened `folder`: make sure its project has a fresh map.

    Finds the registered project that holds the folder. With register_new, an
    unregistered folder that looks like a project is registered in the inbox.
    Queues a refresh when the map is missing or older than the opening.
    """
    folder = Path(folder).expanduser().resolve()
    project = registry.containing(conn, folder)
    if project is None:
        if not register_new:
            return {"path": str(folder), "action": "skipped", "reason": "not a registered project"}
        known = [p["path"] for p in registry.list_projects(conn)]
        problem = discovery.looks_indexable(folder, known)
        if problem:
            return {"path": str(folder), "action": "skipped", "reason": problem}
        entry = discovery.describe(folder, folder.parent)
        entry.update(id=registry.unique_id(conn, folder.name), group="inbox",
                     notes="Registered automatically when a coding agent opened it.")
        entry.pop("launch", None), entry.pop("services", None), entry.pop("safe_to_launch", None)
        project = registry.save(conn, entry, source="agent", actor=actor)
    when = when or now()
    conn.execute("INSERT INTO maps (project_id, map_dir, last_opened) VALUES (?,?,?)"
                 " ON CONFLICT(project_id) DO UPDATE SET last_opened = MAX(COALESCE(maps.last_opened,''), excluded.last_opened)",
                 (project["id"], str(map_dir(project["path"])), when))
    record = sync(conn, project)
    fresh = record.get("last_refresh") and record["last_refresh"] >= (record.get("last_opened") or "")
    if record["status"] == "refreshing":
        return {"project": project["id"], "action": "already refreshing", "task": record.get("task_id")}
    if record["status"] == "ready" and fresh:
        return {"project": project["id"], "action": "up to date"}
    try:
        task = refresh(conn, project, actor, reason="opened by a coding agent")
    except registry.RegistryError as exc:
        return {"project": project["id"], "action": "skipped", "reason": str(exc)}
    return {"project": project["id"], "action": "refresh queued", "task": task["id"]}


def refresh_recent(conn: sqlite3.Connection, window_hours: int, actor: str = "system") -> list[dict[str, Any]]:
    """Check Claude Code's recent sessions once and queue refreshes where needed.

    Only registered projects are refreshed here; new folders are registered
    by `stackloom agent open` (the SessionStart hook) or by discovery.
    """
    results = []
    seen: set[str] = set()
    for item in recently_opened(window_hours):
        project = registry.containing(conn, item["path"])
        if project is None or project["id"] in seen:
            continue
        seen.add(project["id"])
        results.append(note_opened(conn, item["path"], actor, register_new=False, when=item["last_opened"]))
    return results
