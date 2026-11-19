"""API routes for phases 2-7: runtime, Docker, databases, graph, Git, environment,
diagnostics, backups, notifications and desktop actions.

Every route needs a signed-in session; every change needs the CSRF token
(enforced by the `user` dependency) and is written to the activity log.
Long operations return a task at once and run in the background.
"""
from __future__ import annotations

import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from stackloom import activity, backups, diagnostics, docker, envfiles, gitops, graph, maps, notify, registry, runtime, tasks
from stackloom.databases import connections as dbc
from stackloom.databases.base import DbError, NeedsConfirmation


class Confirm(BaseModel):
    confirm: bool = False


class StartBody(BaseModel):
    approve: bool = False


class LaunchBody(BaseModel):
    enabled: bool
    confirm: bool = False


class PortBody(BaseModel):
    port: int


class PoolBody(BaseModel):
    start: int
    end: int


class OpenBody(BaseModel):
    target: str


class ContainerAction(BaseModel):
    action: str
    confirm: bool = False


class ExecBody(BaseModel):
    command: str = Field(max_length=2000)
    confirm: bool = False


class NameBody(BaseModel):
    name: str
    confirm: bool = False


class TagBody(BaseModel):
    source: str
    target: str


class ComposeBody(BaseModel):
    action: str
    working_dir: str = ""
    config_files: list[str] = []
    service: str | None = None
    confirm: bool = False
    remove_volumes: bool = False
    confirm_volumes: bool = False


class NetConnect(BaseModel):
    container: str
    connect: bool = True


class ConnBody(BaseModel):
    id: str | None = None
    name: str = ""
    engine: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    path: str = ""
    project_id: str | None = None
    container: str = ""
    read_only: bool = True
    password_source: str = "none"
    password: str | None = Field(default=None, max_length=1000)
    source: str = "manual"


class PasswordBody(BaseModel):
    password: str = Field(max_length=1000)


class QueryBody(BaseModel):
    database: str = ""
    sql: str = Field(max_length=200_000)
    confirm: bool = False
    limit: int = 500


class RowBody(BaseModel):
    database: str = ""
    table: str
    key: dict[str, Any] = {}
    values: dict[str, Any] = {}
    confirm: bool = False


class DbNameBody(BaseModel):
    name: str
    confirm: bool = False


class FindBody(BaseModel):
    database: str
    collection: str
    filter: str = "{}"
    limit: int = 50
    skip: int = 0


class GitWrite(BaseModel):
    action: str
    confirm: bool = False
    message: str = ""
    files: list[str] = []
    branch: str = ""
    create: bool = False


class EnvSet(BaseModel):
    file: str
    key: str
    value: str = Field(max_length=10_000)
    confirm: bool = False


class BackupSettings(BaseModel):
    daily_stackloom: bool = True
    keep_per_kind: int = 10


def register(app: FastAPI, ctx: SimpleNamespace) -> None:
    get_conn: Callable = ctx.get_conn
    user: Callable = ctx.user

    def project_or_404(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
        try:
            return registry.get(conn, project_id)
        except registry.RegistryError as exc:
            raise HTTPException(404, str(exc))

    def task(conn: sqlite3.Connection, kind: str, target: str, actor: str, fn: Callable[[sqlite3.Connection], str]) -> dict:
        running = tasks.active_for(conn, kind, target)
        if running:
            raise HTTPException(409, f"That is already running (task {running['id']}).")
        task_id = tasks.create(conn, kind, target, actor)
        tasks.run_in_thread(ctx.db_file, task_id, lambda c, _tid: fn(c))
        return tasks.get(conn, task_id) or {"id": task_id}

    def fail(exc: Exception, code: int = 400):
        raise HTTPException(code, str(exc))

    # ------------------------------------------------------------------ runtime (phase 2)

    @app.get("/api/services")
    def services(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        out = []
        for p in registry.list_projects(conn):
            if not p.get("launch"):
                continue
            st = runtime.status(conn, p)
            out.append({"id": p["id"], "name": p.get("name", p["id"]), "group": p["group"], "state": st["state"],
                        "launch_enabled": bool(p.get("safe_to_launch")), "type": p["launch"]["type"],
                        "services": [{"name": s["name"], "port": s["port"], "url": s.get("url")}
                                     for s in runtime.resolved_services(conn, p)]})
        return out

    @app.get("/api/projects/{project_id}/runtime")
    def project_runtime(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        st = runtime.status(conn, p)
        try:
            commands = runtime.start_commands(conn, p, rendered=False) if p.get("launch") else []
            is_approved = runtime.approved(conn, p) if p.get("launch") else False
        except runtime.Refused as exc:
            commands, is_approved = [], False
            st["detail"] = str(exc)
        return {"status": st, "services": runtime.resolved_services(conn, p),
                "health": runtime.health(conn, p) if st["state"] in ("running", "partial", "external") else {},
                "commands": commands, "approved": is_approved, "launch_enabled": bool(p.get("safe_to_launch")),
                "task": tasks.active_for(conn, "runtime.start", project_id) or tasks.active_for(conn, "runtime.stop", project_id)}

    @app.post("/api/projects/{project_id}/start")
    def start(project_id: str, body: StartBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        try:
            if not runtime.approved(conn, p):
                if not body.approve:
                    raise HTTPException(409, "Review and approve the start command first.")
                runtime.approve(conn, p, me["username"])
        except runtime.Refused as exc:
            fail(exc)
        return task(conn, "runtime.start", project_id, me["username"],
                    lambda c: "; ".join(runtime.start(c, registry.get(c, project_id), me["username"]).get("notes") or []) or "Started.")

    @app.post("/api/projects/{project_id}/stop")
    def stop(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        project_or_404(conn, project_id)
        return task(conn, "runtime.stop", project_id, me["username"],
                    lambda c: "Stopped." if runtime.stop(c, registry.get(c, project_id), me["username"]).get("stopped") else "It was not running.")

    @app.post("/api/projects/{project_id}/restart")
    def restart(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        project_or_404(conn, project_id)
        return task(conn, "runtime.restart", project_id, me["username"],
                    lambda c: (runtime.restart(c, registry.get(c, project_id), me["username"]), "Restarted.")[1])

    @app.post("/api/projects/{project_id}/launch")
    def launch(project_id: str, body: LaunchBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        if body.enabled and not body.confirm:
            raise HTTPException(400, "Turning launching on lets this dashboard run the start command. Confirm to continue.")
        try:
            return runtime.set_launch(conn, p, body.enabled, me["username"])
        except (runtime.Refused, registry.RegistryError) as exc:
            fail(exc)

    @app.get("/api/projects/{project_id}/logs", response_class=PlainTextResponse)
    def project_logs(project_id: str, lines: int = Query(300, ge=10, le=5000), service: str | None = None,
                     me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return runtime.logs(project_or_404(conn, project_id), lines, service)

    @app.get("/api/ports")
    def ports(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        c = ctx.cfg()
        return {"pool": list(c.port_pool), "dashboard": c.dashboard_port, "assignments": runtime.port_table(conn)}

    @app.post("/api/ports/{project_id}/{service}")
    def pin_port(project_id: str, service: str, body: PortBody, me: dict = Depends(user),
                 conn: sqlite3.Connection = Depends(get_conn)):
        try:
            return {"warnings": runtime.set_port(conn, project_or_404(conn, project_id), service, body.port, me["username"])}
        except runtime.Refused as exc:
            fail(exc)

    @app.post("/api/ports/{project_id}/{service}/auto")
    def auto_port(project_id: str, service: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            return {"notes": runtime.auto_port(conn, project_or_404(conn, project_id), service, me["username"])}
        except runtime.Refused as exc:
            fail(exc)

    @app.post("/api/ports/pool")
    def set_pool(body: PoolBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        if not 1024 <= body.start < body.end <= 65535:
            raise HTTPException(400, "The range must satisfy 1024 ≤ start < end ≤ 65535.")
        c = ctx.cfg()
        c.port_pool = (body.start, body.end)
        c.save(ctx.base)
        activity.record(conn, me["username"], "port.pool", detail=f"{body.start}-{body.end}")
        return {"pool": [body.start, body.end]}

    @app.post("/api/projects/{project_id}/open")
    def open_project(project_id: str, body: OpenBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        path = p["path"]
        if sys.platform != "darwin":
            raise HTTPException(400, "Opening apps from the dashboard works on macOS for now.")
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731  AppleScript string
        commands = {
            "folder": ["open", path],
            "terminal": ["open", "-a", "Terminal", path],
            "vscode": ["open", "-a", "Visual Studio Code", path],
            "claude": ["osascript", "-e", f'tell application "Terminal" to do script "cd {esc(shlex.quote(path))} && claude"',
                       "-e", 'tell application "Terminal" to activate'],
        }
        if body.target not in commands:
            raise HTTPException(400, "Unknown target.")
        result = subprocess.run(commands[body.target], capture_output=True, text=True, timeout=15, check=False)
        if result.returncode != 0:
            raise HTTPException(400, (result.stderr.strip() or "Could not open it.") +
                                (" Is Visual Studio Code installed?" if body.target == "vscode" else ""))
        activity.record(conn, me["username"], f"project.open_{body.target}", project_id)
        return {"ok": True}

    # ------------------------------------------------------------------ docker (phase 3)

    def dk(fn: Callable, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except docker.DockerError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/docker")
    def docker_overview(me: dict = Depends(user)):
        return dk(docker.overview)

    @app.get("/api/docker/containers")
    def docker_containers(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        items = dk(docker.containers)
        try:
            usage = docker.stats() if any(c["state"] == "running" for c in items) else {}
        except docker.DockerError:
            usage = {}
        for c in items:
            c["stats"] = usage.get(c["name"])
            project = registry.containing(conn, c["working_dir"]) if c["working_dir"] else None
            c["project"] = project["id"] if project else None
        return items

    @app.get("/api/docker/containers/{name}")
    def docker_inspect(name: str, me: dict = Depends(user)):
        return dk(docker.inspect_container, name)

    @app.get("/api/docker/containers/{name}/logs", response_class=PlainTextResponse)
    def docker_logs(name: str, lines: int = Query(300, ge=10, le=5000), me: dict = Depends(user)):
        return dk(docker.container_logs, name, lines)

    @app.post("/api/docker/containers/{name}")
    def docker_action(name: str, body: ContainerAction, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        if body.action == "remove":
            msg = dk(docker.remove_container, name, body.confirm)
        else:
            msg = dk(docker.container_action, name, body.action)
        activity.record(conn, me["username"], f"docker.container_{body.action}", name)
        return {"message": msg}

    @app.post("/api/docker/containers/{name}/exec")
    def docker_exec(name: str, body: ExecBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            argv = shlex.split(body.command)
        except ValueError as exc:
            raise HTTPException(400, f"Could not read the command: {exc}")
        result = dk(docker.exec_command, name, argv, body.confirm)
        activity.record(conn, me["username"], "docker.exec", name, result="ok" if result["exit_code"] == 0 else "failed",
                        detail=body.command[:300])
        return result

    @app.get("/api/docker/images")
    def docker_images(me: dict = Depends(user)):
        return dk(docker.images)

    @app.get("/api/docker/images/history")
    def docker_image_history(ref: str, me: dict = Depends(user)):
        return dk(docker.image_history, ref)

    @app.post("/api/docker/images/pull")
    def docker_pull(body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return task(conn, "docker.pull", body.name, me["username"], lambda c: dk(docker.pull_image, body.name))

    @app.post("/api/docker/images/tag")
    def docker_tag(body: TagBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        activity.record(conn, me["username"], "docker.image_tag", body.source, detail=body.target)
        return {"message": dk(docker.tag_image, body.source, body.target)}

    @app.post("/api/docker/images/remove")
    def docker_rmi(body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        msg = dk(docker.remove_image, body.name, body.confirm)
        activity.record(conn, me["username"], "docker.image_remove", body.name)
        return {"message": msg}

    @app.post("/api/docker/images/prune")
    def docker_prune(body: Confirm, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        msg = dk(docker.prune_dangling, body.confirm)
        activity.record(conn, me["username"], "docker.image_prune")
        return {"message": msg}

    @app.post("/api/docker/build/{project_id}")
    def docker_build(project_id: str, body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        return task(conn, "docker.build", project_id, me["username"], lambda c: dk(docker.build_image, p["path"], body.name)[-2000:])

    @app.get("/api/docker/volumes")
    def docker_volumes(me: dict = Depends(user)):
        return dk(docker.volumes)

    @app.post("/api/docker/volumes")
    def docker_volume_create(body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        activity.record(conn, me["username"], "docker.volume_create", body.name)
        return {"message": dk(docker.create_volume, body.name)}

    @app.post("/api/docker/volumes/remove")
    def docker_volume_remove(body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        msg = dk(docker.remove_volume, body.name, body.confirm)
        activity.record(conn, me["username"], "docker.volume_remove", body.name)
        return {"message": msg}

    @app.post("/api/docker/volumes/backup")
    def docker_volume_backup(body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        def job(c):
            path = dk(docker.backup_volume, body.name)
            backups.register(c, "volume", body.name, path, me["username"])
            return f"Saved {path.name}."
        return task(conn, "docker.volume_backup", body.name, me["username"], job)

    @app.get("/api/docker/networks")
    def docker_networks(me: dict = Depends(user)):
        return dk(docker.networks)

    @app.post("/api/docker/networks")
    def docker_network_create(body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        activity.record(conn, me["username"], "docker.network_create", body.name)
        return {"message": dk(docker.create_network, body.name)}

    @app.post("/api/docker/networks/remove")
    def docker_network_remove(body: NameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        msg = dk(docker.remove_network, body.name, body.confirm)
        activity.record(conn, me["username"], "docker.network_remove", body.name)
        return {"message": msg}

    @app.post("/api/docker/networks/{name}/connect")
    def docker_network_connect(name: str, body: NetConnect, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        activity.record(conn, me["username"], "docker.network_connect" if body.connect else "docker.network_disconnect", name,
                        detail=body.container)
        return {"message": dk(docker.network_connect, name, body.container, body.connect)}

    @app.get("/api/docker/compose")
    def docker_compose_list(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        items = dk(docker.compose_projects)
        for item in items:
            project = registry.containing(conn, item["working_dir"]) if item["working_dir"] else None
            item["project"] = project["id"] if project else None
        return items

    @app.post("/api/docker/compose/{name}")
    def docker_compose(name: str, body: ComposeBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        run = lambda c=None: dk(docker.compose, name, body.action, working_dir=body.working_dir,  # noqa: E731
                                config_files=body.config_files, service=body.service, remove_volumes=body.remove_volumes,
                                confirm=body.confirm, confirm_volumes=body.confirm_volumes)
        activity.record(conn, me["username"], f"docker.compose_{body.action}", name,
                        detail="with volumes" if body.remove_volumes else (body.service or ""))
        if body.action in ("up", "build", "pull", "restart", "down", "stop", "start"):
            if body.action == "down" and not body.confirm:
                raise HTTPException(409, "`down` removes the project's containers and networks. Confirm to continue; volumes are kept.")
            if body.action == "down" and body.remove_volumes and not body.confirm_volumes:
                raise HTTPException(409, "Deleting the project's volumes destroys their data. Confirm that separately.")
            return task(conn, f"docker.compose_{body.action}", name, me["username"], lambda c: run(c)[-2000:])
        return {"output": run()}

    @app.get("/api/projects/{project_id}/containers")
    def project_containers(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        if not docker.info()["available"]:
            return {"available": False, "reason": docker.info()["reason"], "containers": []}
        return {"available": True, "containers": dk(docker.for_project, p["path"])}

    # ------------------------------------------------------------------ databases (phase 4)

    def db(fn: Callable, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NeedsConfirmation as exc:
            raise HTTPException(409, str(exc))
        except DbError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/db/connections")
    def db_list(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return dbc.list_connections(conn)

    @app.post("/api/db/connections")
    def db_save(body: ConnBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        data = body.model_dump(exclude={"password"})
        return db(dbc.save, conn, data, me["username"], body.password)

    @app.delete("/api/db/connections/{conn_id}")
    def db_remove(conn_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        db(dbc.remove, conn, conn_id, me["username"])
        return {"ok": True}

    @app.post("/api/db/connections/{conn_id}/password")
    def db_password(conn_id: str, body: PasswordBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        item = db(dbc.get, conn, conn_id)
        db(dbc.set_password, conn_id, item["password_source"], body.password)
        dbc.forget(conn_id)
        activity.record(conn, me["username"], "db.password_set", conn_id)
        return {"ok": True}

    @app.post("/api/db/connections/{conn_id}/test")
    def db_test(conn_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return db(dbc.test, conn, conn_id)

    @app.get("/api/db/discover")
    def db_discover(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return dbc.discover(conn)

    @app.get("/api/db/{conn_id}/databases")
    def db_databases(conn_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        return {"engine": ad.engine, "kind": ad.kind, "read_only": ad.info.read_only, "server": db(ad.server),
                "databases": db(ad.databases)}

    @app.get("/api/db/{conn_id}/tables")
    def db_tables(conn_id: str, database: str = "", me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return db(db(dbc.adapter, conn, conn_id).tables, database)

    @app.get("/api/db/{conn_id}/table")
    def db_table(conn_id: str, table: str, database: str = "", me: dict = Depends(user),
                 conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        return {"columns": db(ad.columns, database, table), "indexes": db(ad.indexes, database, table),
                "foreign_keys": db(ad.foreign_keys, database, table)}

    @app.get("/api/db/{conn_id}/browse")
    def db_browse(conn_id: str, table: str, database: str = "", limit: int = Query(50, ge=1, le=500),
                  offset: int = Query(0, ge=0), order: str | None = None, me: dict = Depends(user),
                  conn: sqlite3.Connection = Depends(get_conn)):
        return db(db(dbc.adapter, conn, conn_id).browse, database, table, limit, offset, order)

    @app.post("/api/db/{conn_id}/query")
    def db_query(conn_id: str, body: QueryBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        try:
            result = ad.query(body.database, body.sql, body.confirm, max(1, min(body.limit, 5000)))
        except NeedsConfirmation as exc:
            raise HTTPException(409, str(exc))
        except DbError as exc:
            dbc.record_query(conn, conn_id, body.database, body.sql, me["username"], None, None, str(exc))
            raise HTTPException(400, str(exc))
        dbc.record_query(conn, conn_id, body.database, body.sql, me["username"], result.get("ms"), len(result["rows"]))
        if not result["columns"]:
            activity.record(conn, me["username"], "db.statement", conn_id, detail=body.sql[:300])
        return result

    @app.post("/api/db/{conn_id}/export", response_class=PlainTextResponse)
    def db_export(conn_id: str, body: QueryBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        result = db(ad.query, body.database, body.sql, False, 100_000)
        return Response(dbc.export_csv(result), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="query.csv"'})

    @app.get("/api/db/{conn_id}/history")
    def db_history(conn_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return dbc.history(conn, conn_id)

    @app.post("/api/db/{conn_id}/rows")
    def db_row(conn_id: str, body: RowBody, op: str = Query(..., pattern="^(insert|update|delete)$"),
               me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        if op != "insert" and not body.confirm:
            raise HTTPException(409, f"Confirm to {op} this row.")
        if op == "insert":
            n = db(ad.insert_row, body.database, body.table, body.values)
        elif op == "update":
            n = db(ad.update_row, body.database, body.table, body.key, body.values)
        else:
            n = db(ad.delete_row, body.database, body.table, body.key)
        activity.record(conn, me["username"], f"db.row_{op}", f"{conn_id}/{body.table}", detail=str(n))
        return {"rows": n}

    @app.post("/api/db/{conn_id}/drop-table")
    def db_drop_table(conn_id: str, body: RowBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        if not body.confirm:
            raise HTTPException(409, f"Dropping {body.table} deletes it and its data. Confirm to continue.")
        ad = db(dbc.adapter, conn, conn_id)
        def job(c):
            dbc.backup(c, conn_id, body.database, me["username"]) if ad.engine in ("sqlite", "postgres", "mysql", "mariadb") else None
            db(ad.drop_table, body.database, body.table)
            activity.record(c, me["username"], "db.drop_table", f"{conn_id}/{body.table}")
            return f"Backed up, then dropped {body.table}."
        return task(conn, "db.drop_table", f"{conn_id}/{body.table}", me["username"], job)

    @app.post("/api/db/{conn_id}/databases")
    def db_create(conn_id: str, body: DbNameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        db(db(dbc.adapter, conn, conn_id).create_database, body.name)
        activity.record(conn, me["username"], "db.create_database", f"{conn_id}/{body.name}")
        return {"ok": True}

    @app.post("/api/db/{conn_id}/databases/drop")
    def db_drop(conn_id: str, body: DbNameBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        if not body.confirm:
            raise HTTPException(409, f"Dropping {body.name} deletes it permanently. Confirm to continue.")
        ad = db(dbc.adapter, conn, conn_id)
        def job(c):
            dbc.backup(c, conn_id, body.name, me["username"])
            db(ad.drop_database, body.name)
            activity.record(c, me["username"], "db.drop_database", f"{conn_id}/{body.name}")
            return f"Backed up, then dropped {body.name}."
        return task(conn, "db.drop_database", f"{conn_id}/{body.name}", me["username"], job)

    @app.get("/api/db/{conn_id}/admin")
    def db_admin(conn_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        return {"variables": db(ad.variables)[:500], "processes": db(ad.processes), "users": db(ad.users)}

    @app.post("/api/db/{conn_id}/find")
    def db_find(conn_id: str, body: FindBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        if not hasattr(ad, "find"):
            raise HTTPException(400, "Only MongoDB collections take filters.")
        return db(ad.find, body.database, body.collection, body.filter, body.limit, body.skip)

    @app.get("/api/db/{conn_id}/keys")
    def db_keys(conn_id: str, pattern: str = "*", me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        if not hasattr(ad, "scan"):
            raise HTTPException(400, "Only Redis has keys.")
        return db(ad.scan, pattern)

    @app.get("/api/db/{conn_id}/key")
    def db_key(conn_id: str, key: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        ad = db(dbc.adapter, conn, conn_id)
        if not hasattr(ad, "get"):
            raise HTTPException(400, "Only Redis has keys.")
        return db(ad.get, key)

    @app.post("/api/db/{conn_id}/backup")
    def db_backup(conn_id: str, body: QueryBody, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        db(dbc.get, conn, conn_id)
        return task(conn, "db.backup", conn_id, me["username"],
                    lambda c: f"Saved {Path(db(dbc.backup, c, conn_id, body.database, me['username'])['path']).name}.")

    # ------------------------------------------------------------------ codecortex graph (phase 5)

    def gr(fn: Callable, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except graph.GraphError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/graph/{project_id}/summary")
    def graph_summary(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return gr(graph.summary, project_or_404(conn, project_id)["path"])

    @app.get("/api/graph/{project_id}")
    def graph_load(project_id: str, node_kinds: str = "", edge_kinds: str = "", limit: int = Query(400, ge=10, le=3000),
                   focus: str | None = None, depth: int = Query(1, ge=1, le=3), me: dict = Depends(user),
                   conn: sqlite3.Connection = Depends(get_conn)):
        split = lambda s: [x for x in s.split(",") if x] or None  # noqa: E731
        return gr(graph.load, project_or_404(conn, project_id)["path"], split(node_kinds), split(edge_kinds), limit, focus, depth)

    @app.get("/api/graph/{project_id}/search")
    def graph_search(project_id: str, q: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return gr(graph.search, project_or_404(conn, project_id)["path"], q)

    @app.get("/api/graph/{project_id}/node")
    def graph_node(project_id: str, id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return gr(graph.node, project_or_404(conn, project_id)["path"], id)

    @app.get("/api/graph/{project_id}/export")
    def graph_export(project_id: str, fmt: str = Query("json", pattern="^(json|graphml)$"), node_kinds: str = "",
                     edge_kinds: str = "", limit: int = Query(3000, ge=10, le=3000), me: dict = Depends(user),
                     conn: sqlite3.Connection = Depends(get_conn)):
        split = lambda s: [x for x in s.split(",") if x] or None  # noqa: E731
        data = gr(graph.load, project_or_404(conn, project_id)["path"], split(node_kinds), split(edge_kinds), limit)
        if fmt == "graphml":
            return Response(graph.to_graphml(data), media_type="application/xml",
                            headers={"Content-Disposition": f'attachment; filename="{project_id}.graphml"'})
        import json
        return Response(json.dumps(data), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{project_id}-graph.json"'})

    @app.get("/api/codecortex/{project_id}/validate")
    def map_validate(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return graph.validate(project_or_404(conn, project_id)["path"])

    @app.post("/api/codecortex/{project_id}/delete")
    def map_delete(project_id: str, body: Confirm, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        msg = gr(graph.delete_map, p["path"], body.confirm)
        maps.sync(conn, p)
        activity.record(conn, me["username"], "codecortex.delete", project_id)
        return {"message": msg}

    @app.post("/api/codecortex/{project_id}/connect-agent")
    def map_connect(project_id: str, body: Confirm, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        msg = gr(graph.connect_agent, project_or_404(conn, project_id)["path"], body.confirm)
        activity.record(conn, me["username"], "codecortex.connect_agent", project_id)
        return {"message": msg}

    @app.post("/api/codecortex/{project_id}/backup")
    def map_backup(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            return backups.backup_map(conn, project_or_404(conn, project_id), me["username"])
        except backups.BackupError as exc:
            fail(exc)

    # ------------------------------------------------------------------ git, env, diagnostics (phase 6)

    def repo_of(conn: sqlite3.Connection, project_id: str) -> Path:
        p = project_or_404(conn, project_id)
        repo = gitops.repo_root(Path(p.get("repo_root") or p["path"]))
        if repo is None:
            raise HTTPException(404, "This project is not in a Git repository.")
        return repo

    def gt(fn: Callable, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except gitops.GitError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/git")
    def git_list(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        seen, out = set(), []
        for p in registry.list_projects(conn):
            s = gitops.summary(p.get("repo_root") or p["path"])
            if s.get("repo") and s["repo"] not in seen:
                seen.add(s["repo"])
                out.append({**s, "project": p["id"], "name": p.get("name", p["id"])})
        return out

    @app.get("/api/git/{project_id}")
    def git_detail(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        repo = repo_of(conn, project_id)
        return {"repo": str(repo), "status": gt(gitops.status, repo), "log": gitops.log(repo, 30),
                "branches": gt(gitops.branches, repo), "stashes": gt(gitops.stashes, repo)}

    @app.get("/api/git/{project_id}/diff", response_class=PlainTextResponse)
    def git_diff(project_id: str, path: str | None = None, staged: bool = False, me: dict = Depends(user),
                 conn: sqlite3.Connection = Depends(get_conn)):
        return gt(gitops.diff, repo_of(conn, project_id), path, staged)

    @app.post("/api/git/{project_id}")
    def git_write(project_id: str, body: GitWrite, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        repo = repo_of(conn, project_id)
        actions = {
            "fetch": lambda: gitops.fetch(repo, body.confirm),
            "pull": lambda: gitops.pull(repo, body.confirm),
            "push": lambda: gitops.push(repo, body.confirm),
            "commit": lambda: gitops.commit(repo, body.message, body.files, body.confirm),
            "switch": lambda: gitops.switch(repo, body.branch, body.create, body.confirm),
            "stash_push": lambda: gitops.stash(repo, "push", body.confirm),
            "stash_pop": lambda: gitops.stash(repo, "pop", body.confirm),
            "abort": lambda: gitops.abort(repo, gitops.status(repo)["operation"] or "", body.confirm),
        }
        if body.action not in actions:
            raise HTTPException(400, "Unknown Git action.")
        if not body.confirm:
            raise HTTPException(409, f"Confirm to run git {body.action.replace('_', ' ')}.")
        output = gt(actions[body.action])
        activity.record(conn, me["username"], f"git.{body.action}", project_id, detail=body.message[:200] or body.branch)
        return {"output": output}

    def ev(fn: Callable, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except envfiles.EnvError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/env/{project_id}")
    def env_files(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        return {"files": envfiles.files(p["path"]), "missing": envfiles.missing(p["path"])}

    @app.get("/api/env/{project_id}/file")
    def env_file(project_id: str, path: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return ev(envfiles.read, project_or_404(conn, project_id)["path"], path)

    @app.get("/api/env/{project_id}/compare")
    def env_compare(project_id: str, a: str, b: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return ev(envfiles.compare, project_or_404(conn, project_id)["path"], a, b)

    @app.post("/api/env/{project_id}")
    def env_set(project_id: str, body: EnvSet, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        p = project_or_404(conn, project_id)
        result = ev(envfiles.set_value, p["path"], body.file, body.key, body.value, body.confirm)
        if result.get("backup"):
            backups.register(conn, "config", f"{project_id}/{body.file}", Path(result["backup"]), me["username"], "before edit")
        activity.record(conn, me["username"], "env.set", f"{project_id}/{body.file}", detail=body.key)
        return result

    @app.get("/api/diagnostics/{project_id}")
    def diagnose(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return diagnostics.diagnose(conn, project_or_404(conn, project_id))

    @app.get("/api/diagnostics")
    def diagnose_all(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        out = []
        for p in registry.list_projects(conn):
            checks = diagnostics.diagnose(conn, p)
            out.append({"project": p["id"], "name": p.get("name", p["id"]),
                        "problems": [c for c in checks if c["status"] == "problem"]})
        return out

    @app.post("/api/projects/{project_id}/handover")
    def handover(project_id: str, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        text, path = diagnostics.handover(conn, project_or_404(conn, project_id))
        activity.record(conn, me["username"], "report.handover", project_id, detail=path.name)
        return {"markdown": text, "file": str(path)}

    # ------------------------------------------------------------------ backups, notifications

    @app.get("/api/backups")
    def backup_list(kind: str | None = None, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return {"items": backups.history(conn, kind), "settings": backups.settings(conn)}

    @app.post("/api/backups/stackloom")
    def backup_now(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return backups.backup_stackloom(conn, me["username"], "manual")

    @app.post("/api/backups/settings")
    def backup_settings(body: BackupSettings, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return backups.save_settings(conn, body.daily_stackloom, body.keep_per_kind, me["username"])

    @app.post("/api/backups/{backup_id}/verify")
    def backup_verify(backup_id: int, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            return backups.verify(conn, backup_id)
        except backups.BackupError as exc:
            fail(exc, 404)

    @app.post("/api/backups/{backup_id}/delete")
    def backup_delete(backup_id: int, body: Confirm, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            backups.delete(conn, backup_id, me["username"], body.confirm)
        except backups.BackupError as exc:
            fail(exc, 409)
        return {"ok": True}

    @app.get("/api/backups/{backup_id}/download")
    def backup_download(backup_id: int, me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        try:
            item = backups.get(conn, backup_id)
            path = backups.checked_path(item["path"])
        except backups.BackupError as exc:
            raise HTTPException(404, str(exc))
        activity.record(conn, me["username"], "backup.download", item["target"], detail=path.name)
        return FileResponse(path, filename=path.name)

    @app.post("/api/db/{conn_id}/restore/{backup_id}")
    def db_restore(conn_id: str, backup_id: int, body: Confirm, me: dict = Depends(user),
                   conn: sqlite3.Connection = Depends(get_conn)):
        if not body.confirm:
            raise HTTPException(409, "Restoring replaces the database file. The current file is backed up first. Confirm to continue.")
        try:
            item = backups.get(conn, backup_id)
        except backups.BackupError as exc:
            raise HTTPException(404, str(exc))
        return {"message": db(dbc.restore_sqlite, conn, conn_id, Path(item["path"]), me["username"])}

    @app.get("/api/notifications")
    def notifications(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        return notify.recent(conn)

    @app.post("/api/notifications/read")
    def notifications_read(me: dict = Depends(user), conn: sqlite3.Connection = Depends(get_conn)):
        notify.mark_all_read(conn)
        return {"ok": True}

    @app.get("/api/system")
    def system(me: dict = Depends(user)):
        import platform

        from stackloom import COPYRIGHT, COPYRIGHT_URL, __version__, hooks, paths
        try:
            import codecortex.version as ccv
            cc = ccv.__version__
        except Exception:
            cc = None
        drivers = {}
        for engine, module in (("postgres", "psycopg"), ("mysql", "pymysql"), ("mongodb", "pymongo"), ("redis", "redis"),
                               ("keychain", "keyring")):
            try:
                __import__(module)
                drivers[engine] = True
            except ImportError:
                drivers[engine] = False
        return {"version": __version__, "copyright": COPYRIGHT, "copyright_url": COPYRIGHT_URL,
                "python": platform.python_version(), "platform": platform.platform(), "codecortex": cc,
                "home": str(paths.home()), "drivers": drivers, "hook_installed": hooks.installed(),
                "docker": docker.info()}
