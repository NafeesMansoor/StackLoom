import json
from pathlib import Path

import pytest

from stackloom import accounts, discovery, hooks, maps, registry, security


def test_bootstrap_once_and_must_change(conn):
    assert accounts.bootstrap(conn) is True
    assert accounts.bootstrap(conn) is False  # never a second account
    user = accounts.authenticate(conn, "admin", "1234567890@")
    assert user["must_change_password"] == 1
    row = conn.execute("SELECT password_hash FROM users").fetchone()
    assert row[0].startswith("$argon2id$") and "1234567890" not in row[0]


def test_env_password_override(conn, monkeypatch):
    monkeypatch.setenv("STACKLOOM_ADMIN_PASSWORD", "a-much-better-secret")
    accounts.bootstrap(conn)
    with pytest.raises(accounts.AuthError):
        accounts.authenticate(conn, "admin", "1234567890@")
    assert accounts.authenticate(conn, "admin", "a-much-better-secret")


def test_password_change_rules(conn):
    accounts.bootstrap(conn)
    uid = conn.execute("SELECT id FROM users").fetchone()[0]
    with pytest.raises(accounts.AuthError):
        accounts.change_password(conn, uid, "1234567890@", "short")
    with pytest.raises(accounts.AuthError):
        accounts.change_password(conn, uid, "wrong-current", "long-enough-pass")
    accounts.change_password(conn, uid, "1234567890@", "long-enough-pass")
    assert accounts.authenticate(conn, "admin", "long-enough-pass")["must_change_password"] == 0


def test_throttle_after_failures(conn):
    accounts.bootstrap(conn)
    accounts.throttle.clear("admin")
    for _ in range(5):
        with pytest.raises(accounts.AuthError, match="Wrong"):
            accounts.authenticate(conn, "admin", "nope")
    with pytest.raises(accounts.AuthError, match="Too many"):
        accounts.authenticate(conn, "admin", "1234567890@")
    accounts.throttle.clear("admin")


@pytest.mark.parametrize("bad", [
    {"services": [{"name": "web", "port": 3000}]},
    {"services": [{"name": "web", "host": "0.0.0.0"}]},
    {"launch": {"type": "process", "command": "npm run dev"}},
    {"launch": {"type": "process", "command": ["x", "--url", "http://localhost:3000"]}},
    {"env": {"DATABASE_URL": "postgres://user:hunter2@db/app"}},
    {"launch": {"type": "process", "command": ["x", "${PORT:api}"]}},
])
def test_registry_rejects_unsafe(bad):
    project = {"id": "demo", "path": "/tmp/demo", **bad}
    with pytest.raises(registry.RegistryError):
        registry.validate(project)


def test_registry_accepts_placeholders():
    registry.validate({"id": "demo", "path": "/tmp/demo", "services": [{"name": "web"}],
                       "launch": {"type": "process", "command": ["vite", "--port", "${PORT:web}"]}})


def test_redact():
    text = "DATABASE_PASSWORD=abc postgres://u:p@h/db Authorization: Bearer abcdefghijkl ghp_abcdefghijklmnop"
    out = security.redact(text)
    assert "abc " not in out and "u:p@" not in out and "abcdefghijkl" not in out and "ghp_abcdefghij" not in out


def _make(tmp: Path, rel: str, files: dict[str, str]) -> Path:
    root = tmp / rel
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)
    return root


def test_discovery_components_nested_repos_and_registered(tmp_path):
    ws = tmp_path / "ws"
    _make(ws, "Web/shop", {"package.json": json.dumps({"dependencies": {"next": "15", "react": "19"}}),
                           "backend/pyproject.toml": "[project]\nname='api'\ndependencies=['fastapi']\n",
                           "frontend/package.json": "{}"})
    (ws / "Web/shop/vendor-lib/.git").mkdir(parents=True)
    (ws / "Web/shop/vendor-lib/go.mod").write_text("module x")
    _make(ws, "Tools/known", {"pyproject.toml": "[project]\nname='k'\n"})
    _make(ws, "Notes/plain", {"notes.txt": "hi"})
    _make(ws, "Umbrella", {"CLAUDE.md": "", "inner/go.mod": "module y"})
    _make(ws, "Docs/guide", {"CLAUDE.md": "rules"})
    _make(ws, "Web/shop/node_modules/junk", {"package.json": "{}"})
    found = {Path(f["path"]).name: f for f in discovery.scan([ws], registered=[ws / "Tools/known"])}
    assert set(found) == {"shop", "vendor-lib", "inner", "guide"}
    shop = found["shop"]
    assert shop["group"] == "web" and shop["kind"] == "service" and "Next.js" in shop["stack"]
    assert {c["name"] for c in shop["components"]} == {"backend", "frontend"}
    assert "FastAPI" in next(c for c in shop["components"] if c["name"] == "backend")["stack"]
    assert shop["launch"]["command"][0].endswith("next") and shop["safe_to_launch"] is False
    assert found["vendor-lib"]["parent"] == shop["path"]


def test_indexable_guards(tmp_path):
    assert discovery.looks_indexable(Path.home()) is not None
    plain = tmp_path / "plain"
    plain.mkdir()
    assert "no code markers" in discovery.looks_indexable(plain)
    ws = _make(tmp_path, "ws", {"a/pyproject.toml": "", "CLAUDE.md": ""})
    assert "other projects" in discovery.looks_indexable(ws, [ws / "a"])
    assert "other projects" in discovery.looks_indexable(ws)  # umbrella folder, even when nothing is registered
    assert discovery.looks_indexable(ws / "a") is None


def test_recently_opened_reads_cwd_only(tmp_path):
    folder = tmp_path / "projects" / "-x-proj"
    folder.mkdir(parents=True)
    (folder / "s.jsonl").write_text(json.dumps({"type": "x"}) + "\n" +
                                    json.dumps({"cwd": "/x/proj", "message": "secret"}) + "\n")
    out = maps.recently_opened(24, base=tmp_path / "projects")
    assert out[0]["path"] == "/x/proj"


def test_note_opened_registers_and_queues(conn, tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr("stackloom.tasks.spawn", lambda c, tid, m, a: spawned.append(a))
    proj = _make(tmp_path, "code/app", {"pyproject.toml": "[project]\nname='app'\n", "app.py": "def f(): pass\n"})
    result = maps.note_opened(conn, proj, "agent", register_new=True)
    assert result["action"] == "refresh queued" and spawned
    again = maps.note_opened(conn, proj / "sub", "agent", register_new=True)
    assert again["action"] == "already refreshing"
    home_result = maps.note_opened(conn, Path.home(), "agent", register_new=True)
    assert home_result["action"] == "skipped"


def test_hook_install_uninstall_keeps_others(tmp_path):
    settings = tmp_path / "settings.json"
    other = {"hooks": [{"type": "command", "command": "echo hi"}]}
    settings.write_text(json.dumps({"model": "x", "hooks": {"SessionStart": [other]}}))
    hooks.install(Path("/usr/local/bin/stackloom"), settings)
    hooks.install(Path("/usr/local/bin/stackloom"), settings)  # idempotent
    data = json.loads(settings.read_text())
    assert data["model"] == "x" and len(data["hooks"]["SessionStart"]) == 2
    assert hooks.installed(settings)
    hooks.uninstall(settings)
    assert json.loads(settings.read_text())["hooks"]["SessionStart"] == [other]
    assert (tmp_path / "settings.json.stackloom-backup").exists()


def test_researchos_import(conn, tmp_path):
    ros = tmp_path / "ws" / "ResearchOS"
    (ros / "registry").mkdir(parents=True)
    (ros / "admin" / ".state").mkdir(parents=True)
    (tmp_path / "ws" / "Web" / "site").mkdir(parents=True)
    (ros / "registry" / "projects.json").write_text(json.dumps({
        "base": "..", "groups": {"web": "Websites"},
        "projects": [{"id": "site", "display_name": "Site", "group": "web", "path": "Web/site",
                      "services": [{"name": "web", "url": "http://localhost:${PORT:web}"}],
                      "launch": {"type": "process", "command": ["python3", "-m", "http.server", "${PORT:web}"]}}]}))
    (ros / "admin" / ".state" / "ports.json").write_text(json.dumps(
        {"assignments": {"site": {"web": {"port": 4321, "pinned": True}}}}))
    result = registry.import_researchos(conn, ros)
    assert result["imported"] == ["site"] and result["ports"] == 1
    site = registry.get(conn, "site")
    assert site["path"] == str((tmp_path / "ws" / "Web" / "site").resolve()) and site["name"] == "Site"
    assert registry.import_researchos(conn, ros)["skipped"] == ["site"]


def test_upgrade_from_first_schema(tmp_path):
    """A 1.0.1 database (schema 1) gains the phase 2-7 tables and keeps its data."""
    import sqlite3

    from stackloom import db as dbmod

    path = tmp_path / "old.db"
    old = sqlite3.connect(path, isolation_level=None)
    for statement in dbmod.MIGRATIONS[0].split(";"):
        if statement.strip():
            old.execute(statement)
    old.execute("PRAGMA user_version = 1")
    old.execute("INSERT INTO groups (name) VALUES ('kept')")
    old.close()
    conn = dbmod.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(dbmod.MIGRATIONS)
    assert conn.execute("SELECT name FROM groups").fetchone()[0] == "kept"
    conn.execute("SELECT * FROM db_connections, backups, notifications, query_history LIMIT 1")


def test_dependencies_listed(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "^19"}, "devDependencies": {"vite": "5"}}')
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=["fastapi>=0.110", "uvicorn"]\n')
    deps = discovery.dependencies(tmp_path)
    assert deps["package.json dependencies"] == [{"name": "react", "version": "^19"}]
    assert {"name": "fastapi", "version": ">=0.110"} in deps["pyproject.toml"]
