"""The dashboard API. Bound to 127.0.0.1; every route except health and sign-in needs a session."""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from stackloom import COPYRIGHT, COPYRIGHT_URL, __version__, accounts, activity, backups, db, discovery, maps, paths, registry, tasks
from stackloom.config import Config

log = logging.getLogger("stackloom")
COOKIE = "stackloom_session"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
OPEN_WHILE_MUST_CHANGE = {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}


class LoginBody(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=500)


class PasswordBody(BaseModel):
    current: str = Field(max_length=500)
    new: str = Field(max_length=500)


class AdoptBody(BaseModel):
    path: str
    group: str | None = None


class WorkspaceBody(BaseModel):
    path: str


class RefreshBody(BaseModel):
    rebuild: bool = False


def create_app(base: Path | None = None, background: bool = True) -> FastAPI:
    base = base or paths.home()
    db_file = paths.db_path(base)
    stop_event = threading.Event()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if background:
            threading.Thread(target=watch_recent, name="stackloom-recent", daemon=True).start()
        yield
        stop_event.set()

    app = FastAPI(title="STACKLOOM", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = db.connect(db_file)
        try:
            yield conn
        finally:
            conn.close()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if host_of(request.headers.get("host", "")) not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "Host not allowed."}, status_code=421)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def user(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        found = accounts.session_user(conn, request.cookies.get(COOKIE))
        if found is None:
            raise HTTPException(401, "Sign in first.")
        if request.method not in ("GET", "HEAD") and request.headers.get("x-csrf-token") != found["csrf"]:
            raise HTTPException(403, "The request is missing its security token. Reload the page and try again.")
        if found["must_change_password"] and request.url.path not in OPEN_WHILE_MUST_CHANGE:
            raise HTTPException(403, "Change the first-run password before continuing.")
        return found

    def cfg() -> Config:
        return Config.load(base)

    # ------------------------------------------------------------------ auth

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "app": "stackloom", "version": __version__, "copyright": COPYRIGHT,
                "copyright_url": COPYRIGHT_URL}

    @app.post("/api/auth/login")
    def login(body: LoginBody, response: Response, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        try:
            account = accounts.authenticate(conn, body.username.strip(), body.password)
        except accounts.AuthError as exc:
            raise HTTPException(401, str(exc))
        token, csrf = accounts.create_session(conn, account["id"])
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=False, path="/",
                            max_age=accounts.SESSION_HOURS * 3600)
        return {"username": account["username"], "must_change_password": bool(account["must_change_password"]),
                "csrf": csrf}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, me: dict = Depends(user),
               conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        accounts.end_session(conn, request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")
        activity.record(conn, me["username"], "auth.logout")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me_(me: dict = Depends(user)) -> dict[str, Any]:
        return {"username": me["username"], "must_change_password": bool(me["must_change_password"]),
                "csrf": me["csrf"]}

    @app.post("/api/auth/password")
    def password(body: PasswordBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            accounts.change_password(conn, me["id"], body.current, body.new)
        except accounts.AuthError as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True}

    # ------------------------------------------------------------------ workspace

    @app.get("/api/overview")
    def overview(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        projects = registry.list_projects(conn)
        by_kind: dict[str, int] = {}
        for p in projects:
            by_kind[p.get("kind", "workspace")] = by_kind.get(p.get("kind", "workspace"), 0) + 1
        map_rows = maps.all_maps(conn)
        recent = []
        for item in maps.recently_opened(cfg().recent_window_hours)[:8]:
            project = registry.containing(conn, item["path"])
            recent.append({**item, "project": project["id"] if project else None,
                           "name": project.get("name", project["id"]) if project else Path(item["path"]).name})
        return {
            "version": __version__,
            "workspaces": cfg().workspaces,
            "projects": len(projects),
            "groups": len({p["group"] for p in projects}),
            "by_kind": by_kind,
            "maps": {"ready": sum(1 for m in map_rows if m["status"] == "ready"),
                     "refreshing": sum(1 for m in map_rows if m["status"] == "refreshing"),
                     "missing": sum(1 for m in map_rows if m["status"] in ("none", "error"))},
            "candidates": conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0],
            "tasks_running": conn.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0],
            "recently_opened": recent,
            "activity": activity.recent(conn, 12),
        }

    @app.get("/api/projects")
    def projects(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
        out = []
        for p in registry.list_projects(conn):
            m = maps.get(conn, p["id"])
            out.append({"id": p["id"], "name": p.get("name", p["id"]), "group": p["group"], "kind": p.get("kind"),
                        "stack": p.get("stack") or ([p["runtime"]] if p.get("runtime") else []), "path": p["path"],
                        "source": p["source"], "map_status": m["status"], "map_refreshed": m.get("last_refresh"),
                        "last_opened": m.get("last_opened")})
        return out

    @app.get("/api/projects/{project_id}")
    def project(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            p = registry.get(conn, project_id)
        except registry.RegistryError as exc:
            raise HTTPException(404, str(exc))
        ports = [dict(r) for r in conn.execute("SELECT service, port, pinned FROM ports WHERE project_id = ?", (project_id,))]
        root = Path(p["path"])
        deps = discovery.dependencies(root) if root.is_dir() else {}
        return {**p, "map": maps.sync(conn, p), "ports": ports, "dependencies": deps}

    @app.delete("/api/projects/{project_id}")
    def unregister(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            registry.remove(conn, project_id, me["username"])
        except registry.RegistryError as exc:
            raise HTTPException(404, str(exc))
        return {"ok": True}

    @app.post("/api/projects/{project_id}/group")
    def move_group(project_id: str, body: WorkspaceBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            p = registry.get(conn, project_id)
        except registry.RegistryError as exc:
            raise HTTPException(404, str(exc))
        group = registry.slug(body.path)
        activity.record(conn, me["username"], "project.group", project_id, detail=group)
        return registry.save(conn, {**p, "group": group}, source=p["source"], actor=me["username"])

    @app.get("/api/groups")
    def groups(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return registry.groups(conn)

    @app.post("/api/discovery/scan")
    def scan(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        running = tasks.active_for(conn, "discovery.scan", "workspace")
        if running:
            return running
        settings = cfg()
        if not settings.workspaces:
            raise HTTPException(400, "Add a workspace folder in Settings first.")
        task_id = tasks.create(conn, "discovery.scan", "workspace", me["username"])

        def job(c: sqlite3.Connection, _tid: int) -> str:
            return run_scan(c, settings)

        tasks.run_in_thread(db_file, task_id, job)
        activity.record(conn, me["username"], "discovery.scan")
        return tasks.get(conn, task_id)

    @app.get("/api/discovery/candidates")
    def candidates(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        import json as _json
        return [_json.loads(r["data"]) | {"found_at": r["found_at"]}
                for r in conn.execute("SELECT * FROM candidates ORDER BY path")]

    @app.post("/api/discovery/adopt")
    def adopt(body: AdoptBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            return adopt_candidate(conn, body.path, body.group, me["username"])
        except registry.RegistryError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/tasks")
    def task_list(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return tasks.recent(conn, 100)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: int, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        found = tasks.get(conn, task_id)
        if not found:
            raise HTTPException(404, "No such task.")
        return found

    @app.get("/api/activity")
    def activity_list(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return activity.recent(conn, 200)

    # ------------------------------------------------------------------ codecortex

    @app.get("/api/codecortex/maps")
    def map_list(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return maps.all_maps(conn)

    @app.get("/api/codecortex/recent")
    def recent(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        out = []
        for item in maps.recently_opened(cfg().recent_window_hours):
            project = registry.containing(conn, item["path"])
            out.append({**item, "project": project["id"] if project else None})
        return out

    @app.post("/api/codecortex/{project_id}/refresh")
    def refresh(project_id: str, body: RefreshBody, me: dict = Depends(user),
                conn: sqlite3.Connection = Depends(get_conn)):
        try:
            return maps.refresh(conn, registry.get(conn, project_id), me["username"], rebuild=body.rebuild)
        except registry.RegistryError as exc:
            raise HTTPException(400, str(exc))

    # ------------------------------------------------------------------ settings

    @app.get("/api/settings")
    def settings(me: dict = Depends(user)):
        c = cfg()
        return {"workspaces": c.workspaces, "port_pool": list(c.port_pool), "auto_refresh_maps": c.auto_refresh_maps,
                "recent_window_hours": c.recent_window_hours, "home": str(base)}

    @app.post("/api/settings/workspaces")
    def add_workspace(body: WorkspaceBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        path = Path(body.path).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise HTTPException(400, "Enter the full path of an existing folder, for example /Users/you/Code.")
        c = cfg()
        resolved = str(path.resolve())
        if resolved not in c.workspaces:
            c.workspaces.append(resolved)
            c.save(base)
            activity.record(conn, me["username"], "settings.workspace_add", resolved)
        return {"workspaces": c.workspaces}

    @app.delete("/api/settings/workspaces")
    def remove_workspace(body: WorkspaceBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        c = cfg()
        c.workspaces = [w for w in c.workspaces if w != body.path]
        c.save(base)
        activity.record(conn, me["username"], "settings.workspace_remove", body.path)
        return {"workspaces": c.workspaces}

    # ------------------------------------------------------------------ phases 2-7

    from types import SimpleNamespace

    from stackloom.api import routes

    routes.register(app, SimpleNamespace(get_conn=get_conn, user=user, cfg=cfg, db_file=db_file, base=base))

    # ------------------------------------------------------------------ static dashboard (registered last)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        if not WEB_DIR.exists():
            return JSONResponse({"detail": "The dashboard files are missing from this installation."}, status_code=500)
        candidate = (WEB_DIR / full_path).resolve()
        if full_path and WEB_DIR in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    # ------------------------------------------------------------------ background check

    def watch_recent() -> None:
        """Once a minute: refresh maps of projects opened in Claude Code, notice apps that
        stopped by themselves, and make the daily STACKLOOM backup. Cheap checks only."""
        was_running: set[str] = set()
        while not stop_event.wait(60):
            try:
                c = cfg()
                conn = db.connect(db_file)
                try:
                    if c.auto_refresh_maps:
                        maps.refresh_recent(conn, c.recent_window_hours)
                    was_running = watch_processes(conn, was_running)
                    backups.scheduled(conn)
                finally:
                    conn.close()
            except Exception:
                log.exception("background check failed")

    def watch_processes(conn: sqlite3.Connection, before: set[str]) -> set[str]:
        from stackloom import notify, runtime

        state_dir = paths.home() / "state" / "proc"
        now_running = {f.stem for f in state_dir.glob("*.json")} if state_dir.exists() else set()
        alive = set()
        for pid in now_running:
            if runtime._process_state(pid):
                alive.add(pid)
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(timespec="seconds")
        for gone in before - alive:
            if not tasks.active_for(conn, "runtime.stop", gone) and not conn.execute(
                    "SELECT 1 FROM activity WHERE action IN ('runtime.stop', 'runtime.restart') AND target = ? AND at > ?",
                    (gone, cutoff)).fetchone():
                notify.add(conn, f"{gone} stopped unexpectedly", "Its process is no longer running. Check its log.", "error",
                           f"#/projects/{gone}")
                activity.record(conn, "system", "runtime.exited", gone, result="failed")
        return alive

    return app


def host_of(header: str) -> str:
    """Host without the port: '127.0.0.1:4100' -> '127.0.0.1', '[::1]:4100' -> '[::1]'."""
    if header.startswith("["):
        return header.split("]")[0] + "]"
    return header.rsplit(":", 1)[0]


def run_scan(conn: sqlite3.Connection, settings: Config) -> str:
    import json

    registered = [p["path"] for p in registry.list_projects(conn)]
    found = discovery.scan(settings.workspaces, registered, settings.discovery_depth)
    conn.execute("DELETE FROM candidates")
    ts = db.now()
    for entry in found:
        conn.execute("INSERT OR REPLACE INTO candidates (path, data, found_at) VALUES (?,?,?)",
                     (entry["path"], json.dumps(entry), ts))
    return f"Found {len(found)} unregistered project{'s' if len(found) != 1 else ''}."


def adopt_candidate(conn: sqlite3.Connection, path: str, group: str | None, actor: str) -> dict[str, Any]:
    import json

    row = conn.execute("SELECT data FROM candidates WHERE path = ?", (path,)).fetchone()
    if row is None:
        raise registry.RegistryError("That folder is not in the latest discovery results. Run discovery again.")
    entry = json.loads(row["data"])
    entry["id"] = registry.unique_id(conn, entry["name"])
    if group:
        entry["group"] = registry.slug(group)
    project = registry.save(conn, entry, source="discovered", actor=actor)
    conn.execute("DELETE FROM candidates WHERE path = ?", (path,))
    maps.sync(conn, project)
    return project
