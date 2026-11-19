"""Phases 2-6: runtime, Docker (mocked engine), databases, graph, Git, env files, backups, diagnostics."""
import json
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from stackloom import backups, diagnostics, docker, envfiles, gitops, graph, registry, runtime
from stackloom.config import Config
from stackloom.databases import connections as dbc
from stackloom.databases.base import DbError, NeedsConfirmation, guard


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def pool(home):
    port = _free_port()
    cfg = Config(port_pool=(port, port + 20))
    cfg.save(home)
    return port


def _web_project(conn, tmp_path, pid="web"):
    root = tmp_path / pid
    root.mkdir()
    (root / "index.html").write_text("<p>hi</p>")
    return registry.save(conn, {
        "id": pid, "path": str(root), "group": "web", "safe_to_launch": True,
        "services": [{"name": "web", "url": "http://localhost:${PORT:web}",
                      "health": {"type": "http", "url": "http://127.0.0.1:${PORT:web}"}}],
        "launch": {"type": "process", "command": [sys.executable, "-m", "http.server", "${PORT:web}", "--bind", "127.0.0.1"]},
    }, source="manual")


# --------------------------------------------------------------------------- runtime

def test_start_needs_approval_then_runs_and_stops(conn, tmp_path, pool):
    project = _web_project(conn, tmp_path)
    with pytest.raises(runtime.Refused, match="approved"):
        runtime.start(conn, project, "t")
    runtime.approve(conn, project, "t")
    result = runtime.start(conn, project, "t")
    assert "assigned port" in result["notes"][0]
    port = runtime.ports_of(conn, "web")["web"]
    assert port >= pool
    for _ in range(30):
        if runtime.health(conn, project)["web"] == "healthy":
            break
        time.sleep(0.2)
    assert runtime.status(conn, project)["state"] == "running"
    assert runtime.health(conn, project)["web"] == "healthy"
    with pytest.raises(runtime.Refused, match="already running"):
        runtime.start(conn, project, "t")
    with pytest.raises(runtime.Refused, match="stop it before"):
        runtime.set_port(conn, project, "web", port + 5, "t")
    assert runtime.stop(conn, project, "t")["stopped"]
    assert runtime.status(conn, project)["state"] == "stopped"
    # same port is reused on the next start
    runtime.start(conn, project, "t")
    assert runtime.ports_of(conn, "web")["web"] == port
    runtime.stop(conn, project, "t")


def test_changed_command_needs_new_approval(conn, tmp_path, pool):
    project = _web_project(conn, tmp_path)
    runtime.approve(conn, project, "t")
    project["launch"]["command"] = project["launch"]["command"] + ["--directory", "."]
    project = registry.save(conn, project, source="manual")
    assert not runtime.approved(conn, project)


def test_pinned_busy_port_refuses_and_kills_nothing(conn, tmp_path, pool):
    project = _web_project(conn, tmp_path)
    runtime.approve(conn, project, "t")
    holder = socket.socket()
    holder.bind(("127.0.0.1", pool + 3))
    holder.listen()
    try:
        runtime.set_port(conn, project, "web", pool + 3, "t")
        with pytest.raises(runtime.Refused, match="Nothing was stopped"):
            runtime.start(conn, project, "t")
        # an unrelated listener on an auto port makes the port move, never a kill
        runtime.auto_port(conn, project, "web", "t")
        assert runtime.ports_of(conn, "web")["web"] != pool + 3
    finally:
        holder.close()


def test_external_app_is_shown_not_stopped(conn, tmp_path, pool):
    project = _web_project(conn, tmp_path)
    runtime.ensure_ports(conn, project)
    port = runtime.ports_of(conn, "web")["web"]
    other = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # wait until the stand-in app answers, not merely binds; cold CI runners are slow
        for _ in range(150):
            if all(runtime.check_health(s) == "healthy" for s in runtime.resolved_services(conn, project)):
                break
            time.sleep(0.1)
        assert runtime.status(conn, project)["state"] == "external"
        with pytest.raises(runtime.Refused, match="outside STACKLOOM"):
            runtime.stop(conn, project, "t")
        assert other.poll() is None
    finally:
        other.terminate()
        other.wait()


def test_process_that_dies_immediately_is_reported(conn, tmp_path, pool):
    root = tmp_path / "bad"
    root.mkdir()
    project = registry.save(conn, {"id": "bad", "path": str(root), "safe_to_launch": True,
                                   "launch": {"type": "process", "command": [sys.executable, "-c", "raise SystemExit(3)"]}},
                            source="manual")
    runtime.approve(conn, project, "t")
    with pytest.raises(runtime.Refused, match="exited straight away"):
        runtime.start(conn, project, "t")


def test_compose_override_is_outside_project(conn, tmp_path, home, pool):
    root = tmp_path / "app"
    root.mkdir()
    project = registry.save(conn, {"id": "app", "path": str(root),
                                   "services": [{"name": "web", "compose_service": "web", "container_port": 3000}],
                                   "launch": {"type": "docker-compose", "compose_project": "app",
                                              "compose_files": [str(root / "compose.yaml")],
                                              "compose_env": {"web": {"ORIGIN": "http://localhost:${PORT:web}"}}}},
                            source="manual")
    runtime.ensure_ports(conn, project)
    path = runtime.write_compose_override(conn, project)
    assert home in path.parents and root not in path.parents
    text = path.read_text()
    port = runtime.ports_of(conn, "app")["web"]
    assert f'"127.0.0.1:{port}:3000"' in text and f"http://localhost:{port}" in text
    assert runtime.stop_command(project)[-3:] == ["stop", "--timeout", "20"] and "down" not in runtime.stop_command(project)


# --------------------------------------------------------------------------- docker (engine mocked)

class FakeDocker:
    def __init__(self):
        self.calls = []

    def __call__(self, args, timeout=60, cwd=None, check=True):
        self.calls.append(args)
        out = ""
        if args[:2] == ["info", "--format"]:
            out = json.dumps({"ServerVersion": "27.0", "Containers": 2, "ContainersRunning": 1})
        elif args[0] == "ps":
            out = "\n".join(json.dumps(x) for x in [
                {"ID": "abc123456789xyz", "Names": "app-db-1", "Image": "postgres:16", "State": "running",
                 "Status": "Up 2 hours (healthy)", "Ports": "127.0.0.1:5544->5432/tcp", "Mounts": "app_pgdata",
                 "Networks": "app_default", "Labels": "com.docker.compose.project=app,com.docker.compose.service=db,"
                 "com.docker.compose.project.working_dir=/w/app"},
                {"ID": "def", "Names": "loose", "Image": "redis:7", "State": "exited", "Status": "Exited (0)", "Ports": "",
                 "Mounts": "", "Networks": "bridge", "Labels": ""}])
        elif args[:2] == ["volume", "ls"]:
            out = "\n".join(json.dumps(x) for x in [{"Name": "app_pgdata", "Driver": "local"}, {"Name": "spare", "Driver": "local"}])
        elif args[:2] == ["network", "ls"]:
            out = "\n".join(json.dumps(x) for x in [{"Name": "bridge", "Driver": "bridge"}, {"Name": "app_default", "Driver": "bridge"}])
        elif args[:2] == ["image", "ls"]:
            out = json.dumps({"ID": "img1", "Repository": "postgres", "Tag": "16", "Size": "400MB"})
        elif args[:2] == ["compose", "ls"]:
            out = json.dumps([{"Name": "app", "Status": "running(1)", "ConfigFiles": "/w/app/compose.yaml"}])
        return subprocess.CompletedProcess(args, 0, out, "")


@pytest.fixture()
def fake_docker(monkeypatch):
    fake = FakeDocker()
    monkeypatch.setattr(docker, "run", fake)
    monkeypatch.setattr(docker.shutil, "which", lambda name: "/usr/bin/docker")
    docker._info_cache.update(at=0.0, value=None)
    yield fake
    docker._info_cache.update(at=0.0, value=None)


def test_docker_inventory_and_compose_labels(fake_docker):
    cs = docker.containers()
    assert cs[0]["compose_project"] == "app" and cs[0]["health"] == "healthy" and cs[0]["working_dir"] == "/w/app"
    assert docker.compose_projects()[0]["services"] == ["db"]
    assert next(v for v in docker.volumes() if v["name"] == "app_pgdata")["containers"] == ["app-db-1"]
    assert docker.for_project("/w/app")[0]["name"] == "app-db-1"


def test_docker_destructive_guards(fake_docker):
    with pytest.raises(docker.DockerError, match="confirmation"):
        docker.remove_container("loose", confirm=False)
    docker.remove_container("loose", confirm=True)
    assert ["rm", "loose"] in fake_docker.calls and not any("-v" in c for c in fake_docker.calls)
    with pytest.raises(docker.DockerError, match="attached"):
        docker.remove_volume("app_pgdata", confirm=True)
    with pytest.raises(docker.DockerError, match="built-in"):
        docker.remove_network("bridge", confirm=True)
    with pytest.raises(docker.DockerError, match="Confirm"):
        docker.compose("app", "down")
    with pytest.raises(docker.DockerError, match="separately"):
        docker.compose("app", "down", confirm=True, remove_volumes=True)
    docker.compose("app", "down", confirm=True)
    assert fake_docker.calls[-1] == ["compose", "-p", "app", "down"]
    with pytest.raises(docker.DockerError, match="Invalid"):
        docker.container_action("--privileged", "start")


def test_docker_inspect_masks_secrets(fake_docker, monkeypatch):
    def fake(args, timeout=60, cwd=None, check=True):
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, json.dumps([{"Id": "x", "Name": "/db", "Config": {
                "Env": ["POSTGRES_PASSWORD=hunter2", "PGDATA=/var/lib/pg", "DATABASE_URL=postgres://u:p@h/d"]}}]), "")
        return FakeDocker()(args)
    monkeypatch.setattr(docker, "run", fake)
    env = {e["key"]: e["value"] for e in docker.inspect_container("db")["env"]}
    assert env["POSTGRES_PASSWORD"] == "••••••" and env["DATABASE_URL"] == "••••••" and env["PGDATA"] == "/var/lib/pg"


# --------------------------------------------------------------------------- databases

@pytest.fixture()
def sqlite_conn(conn, tmp_path):
    path = tmp_path / "app.db"
    with sqlite3.connect(path) as s:
        s.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        s.executemany("INSERT INTO users (name, email) VALUES (?, ?)", [(f"u{i}", f"u{i}@x") for i in range(30)])
        s.execute("CREATE TABLE logs (msg TEXT)")
    ro = dbc.save(conn, {"name": "app ro", "engine": "sqlite", "path": str(path), "read_only": True}, "t")
    rw = dbc.save(conn, {"name": "app rw", "engine": "sqlite", "path": str(path), "read_only": False}, "t")
    return conn, ro["id"], rw["id"], path


def test_sql_guard():
    guard("select 1", True, False)
    guard("-- note\nWITH x AS (SELECT 1) SELECT * FROM x", True, False)
    with pytest.raises(DbError, match="read-only"):
        guard("delete from t", True, True)
    with pytest.raises(NeedsConfirmation):
        guard("UPDATE t SET a = 1", False, False)
    with pytest.raises(DbError, match="one statement"):
        guard("select 1; drop table t", False, True)
    with pytest.raises(NeedsConfirmation):
        guard("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x", False, False)


def test_sqlite_browse_query_and_read_only(sqlite_conn):
    conn, ro, rw, path = sqlite_conn
    ad = dbc.adapter(conn, ro)
    assert {t["name"] for t in ad.tables("main")} == {"users", "logs"}
    page = ad.browse("main", "users", limit=10, offset=20, order="id")
    assert page["total"] == 30 and len(page["rows"]) == 10 and page["rows"][0][1] == "u20"
    assert ad.query("main", "SELECT COUNT(*) FROM users")["rows"] == [[30]]
    with pytest.raises(DbError, match="read-only"):
        ad.query("main", "DELETE FROM users", confirm=True)
    with pytest.raises(DbError):
        ad.insert_row("main", "users", {"name": "x"})
    with pytest.raises(DbError, match="No table"):
        ad.browse("main", "users; DROP TABLE users", 10, 0)
    with pytest.raises(DbError, match="no column"):
        ad.browse("main", "users", 10, 0, order="id; DROP TABLE users")


def test_sqlite_row_edits_are_parameterised(sqlite_conn):
    conn, ro, rw, path = sqlite_conn
    ad = dbc.adapter(conn, rw)
    assert ad.insert_row("main", "users", {"name": "Robert'); DROP TABLE users;--", "email": "b@x"}) == 1
    assert ad.query("main", "SELECT COUNT(*) FROM users")["rows"] == [[31]]
    assert ad.update_row("main", "users", {"id": 1}, {"email": "new@x"}) == 1
    with pytest.raises(DbError, match="primary key"):
        ad.update_row("main", "users", {"name": "u2"}, {"email": "z"})
    with pytest.raises(DbError, match="no primary key"):
        ad.delete_row("main", "logs", {"msg": "x"})
    assert ad.delete_row("main", "users", {"id": 2}) == 1


def test_db_backup_verify_and_restore(sqlite_conn):
    conn, ro, rw, path = sqlite_conn
    item = dbc.backup(conn, rw, "main", "t")
    assert backups.verify(conn, item["id"])["ok"]
    dbc.adapter(conn, rw).query("main", "DELETE FROM users", confirm=True)
    msg = dbc.restore_sqlite(conn, rw, Path(item["path"]), "t")
    assert "backed up first" in msg
    assert dbc.adapter(conn, rw).query("main", "SELECT COUNT(*) FROM users")["rows"] == [[30]]
    Path(item["path"]).write_bytes(b"tampered")
    assert not backups.verify(conn, item["id"])["ok"]


def test_db_discovery_reads_env_without_keeping_password(conn, tmp_path):
    root = tmp_path / "svc"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='svc'\n")
    (root / ".env").write_text("DATABASE_URL=postgresql://app:s3cret@127.0.0.1:5433/appdb\nREDIS_URL=redis://localhost:6380/1\n")
    registry.save(conn, {"id": "svc", "path": str(root)}, source="manual")
    found = {f["engine"]: f for f in dbc.discover(conn) if f.get("project_id") == "svc"}
    pg = found["postgres"]
    assert (pg["host"], pg["port"], pg["database"], pg["username"]) == ("127.0.0.1", 5433, "appdb", "app")
    assert "s3cret" not in json.dumps(found) and pg["password_source"].startswith("env:")
    saved = dbc.save(conn, pg, "t")
    assert dbc.password_for(saved) == "s3cret"
    assert "s3cret" not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM db_connections")])
    assert found["redis"]["port"] == 6380


# --------------------------------------------------------------------------- graph

@pytest.fixture()
def mapped(tmp_path):
    root = tmp_path / "proj"
    (root / ".codecortex").mkdir(parents=True)
    (root / "a.py").write_text("def main():\n    helper()\n\ndef helper():\n    return 1\n")
    db = sqlite3.connect(root / ".codecortex" / "graph.db")
    db.executescript("""
        CREATE TABLE nodes (qualified_name TEXT PRIMARY KEY, kind TEXT, name TEXT, file_path TEXT, language TEXT,
            range_start INTEGER, range_end INTEGER, parent_qualified TEXT, is_test INTEGER DEFAULT 0, extra TEXT DEFAULT '{}');
        CREATE TABLE edges (id INTEGER PRIMARY KEY, kind TEXT, source TEXT, target TEXT, file_path TEXT, confidence REAL, extra TEXT);""")
    f = str(root / "a.py")
    db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,0,'{}')", [
        ("a.main", "Function", "main", f, "python", 1, 2, None), ("a.helper", "Function", "helper", f, "python", 4, 5, None),
        ("a.x", "Variable", "x", f, "python", 2, 2, None), ("evil", "Function", "evil", "/etc/passwd", "python", 1, 3, None)])
    db.executemany("INSERT INTO edges (kind, source, target, confidence) VALUES (?,?,?,1)",
                   [("CALLS", "a.main", "a.helper"), ("READS", "a.main", "a.x")])
    db.commit()
    db.close()
    (root / ".codecortex" / "state.json").write_text(json.dumps({"centrality": {"a.helper": {"composite_score": 0.9, "fan_in": 1},
                                                                                 "a.main": {"composite_score": 0.1}},
                                                                  "clusters": {"a.main": 0, "a.helper": 0}, "files": {f: [1, 1]}}))
    return root


def test_graph_load_hides_detail_and_reads_no_engine(mapped):
    data = graph.load(str(mapped))
    ids = {n["id"] for n in data["nodes"]}
    assert "a.x" not in ids and {"a.main", "a.helper"} <= ids
    assert [e["kind"] for e in data["edges"]] == ["CALLS"]
    assert next(n for n in data["nodes"] if n["id"] == "a.helper")["hotspot"]
    full = graph.load(str(mapped), node_kinds=["Function", "Variable"], edge_kinds=["CALLS", "READS"])
    assert len(full["edges"]) == 2
    focus = graph.load(str(mapped), focus="a.helper")
    assert {n["id"] for n in focus["nodes"]} == {"a.helper", "a.main"}
    assert "codecortex.pipeline" not in sys.modules


def test_graph_node_snippet_stays_inside_project(mapped):
    node = graph.node(str(mapped), "a.helper")
    assert "def helper" in node["source"] and node["incoming"][0]["id"] == "a.main"
    assert graph.node(str(mapped), "evil")["source"] == ""
    assert graph.search(str(mapped), "help")[0]["id"] == "a.helper"
    assert "<graphml" in graph.to_graphml(graph.load(str(mapped)))
    assert graph.validate(str(mapped))["ok"]


def test_delete_map_needs_confirm_and_only_removes_map(mapped):
    with pytest.raises(graph.GraphError):
        graph.delete_map(str(mapped), confirm=False)
    graph.delete_map(str(mapped), confirm=True)
    assert not (mapped / ".codecortex").exists() and (mapped / "a.py").exists()


# --------------------------------------------------------------------------- git

@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "T")
    (root / "a.txt").write_text("one\n")
    run("add", ".")
    run("commit", "-qm", "first")
    return root


def test_git_status_diff_and_guarded_commit(repo):
    (repo / "a.txt").write_text("two\nTOKEN=abcdefghijk\n")
    (repo / "new.txt").write_text("x")
    st = gitops.status(repo)
    assert st["branch"] == "main" and st["changed"][0]["path"] == "a.txt" and st["untracked"] == ["new.txt"]
    d = gitops.diff(repo, "a.txt")
    assert "+two" in d and "abcdefghijk" not in d
    with pytest.raises(gitops.GitError, match="Confirm"):
        gitops.commit(repo, "msg", ["a.txt"], confirm=False)
    with pytest.raises(gitops.GitError, match="outside"):
        gitops.commit(repo, "msg", ["../escape.txt"], confirm=True)
    gitops.commit(repo, "second", ["a.txt"], confirm=True)
    assert gitops.log(repo, 1)[0]["subject"] == "second"
    assert gitops.status(repo)["untracked"] == ["new.txt"]
    with pytest.raises(gitops.GitError, match="Invalid"):
        gitops.switch(repo, "--orphan", False, confirm=True)
    assert gitops.summary(repo / "sub" if False else repo)["branch"] == "main"


# --------------------------------------------------------------------------- env files, diagnostics, backups

def test_env_masking_compare_missing_and_edit(home, tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / ".env").write_text("# comment\nPORT=3000\nAPI_KEY=sk-abcdefghijklmnop\nDEBUG=\n")
    (root / ".env.example").write_text("PORT=\nAPI_KEY=\nDEBUG=\nNEW_FLAG=\n")
    data = {k["key"]: k for k in envfiles.read(str(root), ".env")["keys"]}
    assert data["PORT"]["value"] == "3000" and data["API_KEY"]["value"] is None and data["API_KEY"]["secret"]
    assert not data["DEBUG"]["set"]
    cmp = envfiles.compare(str(root), ".env", ".env.example")
    assert cmp["only_in_b"] == ["NEW_FLAG"] and "API_KEY" in cmp["different"] and "sk-" not in json.dumps(cmp)
    gaps = envfiles.missing(str(root))[0]
    assert set(gaps["keys"]) == {"DEBUG", "NEW_FLAG"}
    with pytest.raises(envfiles.EnvError):
        envfiles.read(str(root), "../../etc/passwd")
    (root / ".env").chmod(0o600)
    result = envfiles.set_value(str(root), ".env", "DEBUG", "true", confirm=True)
    text = (root / ".env").read_text()
    assert "DEBUG=true" in text and "# comment" in text and Path(result["backup"]).exists()
    assert oct((root / ".env").stat().st_mode)[-3:] == "600"


def test_stackloom_backup_and_restore(conn, home):
    registry.save(conn, {"id": "keep", "path": "/tmp/keep"}, source="manual")
    item = backups.backup_stackloom(conn, "t")
    assert backups.verify(conn, item["id"])["ok"]
    conn.execute("DELETE FROM projects")
    conn.close()
    msg = backups.restore_stackloom(Path(item["path"]))
    assert "before-restore" in msg
    from stackloom import db

    c2 = db.connect()
    assert registry.get(c2, "keep")
    c2.close()


def test_backups_in_the_same_second_never_overwrite(home):
    folder = home / "backups" / "x"
    folder.mkdir(parents=True)
    first = backups.unique(folder / "a-1.tar.gz")
    first.write_text("1")
    second = backups.unique(folder / "a-1.tar.gz")
    assert second.name == "a-1-2.tar.gz"


def test_retention_keeps_newest(conn, home):
    backups.save_settings(conn, True, 2, "t")
    for _ in range(4):
        backups.backup_stackloom(conn, "t")
    assert len(backups.history(conn, "stackloom")) == 2


def test_handover_has_no_secrets(conn, tmp_path):
    root = tmp_path / "h"
    root.mkdir()
    (root / ".env").write_text("SECRET_TOKEN=supersecretvalue123\nPORT=1\n")
    (root / "package.json").write_text("{}")
    with pytest.raises(registry.RegistryError, match="credential"):
        registry.save(conn, {"id": "h", "path": str(root), "notes": "Uses postgres://u:pw@db/x"}, source="manual")
    project = registry.save(conn, {"id": "h", "path": str(root), "notes": "Uses Postgres"}, source="manual")
    checks = {c["check"]: c for c in diagnostics.diagnose(conn, project)}
    assert checks["Node dependencies"]["status"] == "problem"
    text, path = diagnostics.handover(conn, project)
    assert "supersecretvalue123" not in text and "SECRET_TOKEN" in text and "u:pw@" not in text and path.exists()
