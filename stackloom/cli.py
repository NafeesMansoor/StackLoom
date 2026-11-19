"""The `stackloom` command. Same services and database as the dashboard.

Heavy modules (FastAPI, argon2, CodeCortex) are imported inside the commands
that need them, so `stackloom status` and the agent hook stay fast.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

from stackloom import COPYRIGHT, COPYRIGHT_URL, __version__

LOGO = r"""
  ▚▚  STACKLOOM {version}
  ▚▚  one workspace, every project
  {copyright}
"""


def _conn():
    from stackloom import db, paths

    paths.ensure()
    return db.connect()


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)] if rows else [len(h) for h in headers]
    line = lambda r: "  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip()  # noqa: E731
    return "\n".join([line(headers), line(["-" * w for w in widths]), *(line(r) for r in rows)])


def _ago(iso: str | None) -> str:
    if not iso:
        return "-"
    from datetime import datetime, timezone

    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    seconds = (datetime.now(timezone.utc) - then).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"


# --------------------------------------------------------------------------- setup

def ensure_setup(workspaces: list[str] | None = None, interactive: bool = True) -> None:
    """First run: home folder, database, first administrator, workspace folder."""
    from stackloom import accounts
    from stackloom.config import Config

    conn = _conn()
    created = accounts.bootstrap(conn)
    cfg = Config.load()
    changed = False
    for ws in workspaces or []:
        path = str(Path(ws).expanduser().resolve())
        if path not in cfg.workspaces:
            cfg.workspaces.append(path)
            changed = True
    if not cfg.workspaces and interactive and sys.stdin.isatty():
        default = str(Path.cwd())
        answer = input(f"Workspace folder to manage [{default}]: ").strip() or default
        path = Path(answer).expanduser().resolve()
        if path.is_dir():
            cfg.workspaces.append(str(path))
            changed = True
        else:
            print(f"{path} is not a folder; add one later in Settings.")
    from stackloom import paths

    if changed or not paths.config_path().exists():
        cfg.save()
    if created:
        print("Created the first administrator account 'admin'.")
        if os.environ.get("STACKLOOM_ADMIN_PASSWORD"):
            print("Its password is the one in STACKLOOM_ADMIN_PASSWORD. You will be asked to change it.")
        else:
            print("Sign in with the first-run password from the installation guide; you will be asked to change it.")
    conn.close()


def cmd_init(args: argparse.Namespace) -> int:
    ensure_setup(args.workspace, interactive=True)
    if args.import_researchos:
        return cmd_import(argparse.Namespace(source="researchos", path=args.import_researchos))
    print("Ready. Run `stackloom` to open the dashboard.")
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    from stackloom import server
    from stackloom.config import Config

    ensure_setup(interactive=True)
    state = server.running()
    if state:
        print(f"STACKLOOM is already running at {state['url']}")
    else:
        cfg = Config.load()
        conn = _conn()
        taken = {r[0] for r in conn.execute("SELECT port FROM ports")}
        conn.close()
        port = server.choose_port(cfg, args.port, taken)
        if args.foreground:
            print(LOGO.format(version=__version__, copyright=COPYRIGHT))
            print(f"Dashboard: http://127.0.0.1:{port}/  (Ctrl+C stops it)")
            _remember_port(port)
            server.serve(port)
            return 0
        state = server.start_background(port)
        _remember_port(port)
        print(LOGO.format(version=__version__, copyright=COPYRIGHT))
        print(f"Dashboard: {state['url']}")
    if not args.no_browser:
        webbrowser.open(state["url"])
    return 0


def _remember_port(port: int) -> None:
    from stackloom.config import Config

    cfg = Config.load()
    if cfg.dashboard_port != port:
        cfg.dashboard_port = port
        cfg.save()


def cmd_serve(args: argparse.Namespace) -> int:
    from stackloom import server

    server.serve(args.port)
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    from stackloom import server

    if args.stop:
        print("Stopped the dashboard." if server.stop() else "The dashboard was not running.")
        return 0
    state = server.running()
    if not state:
        print("The dashboard is not running. Start it with `stackloom`.")
        return 1
    print(state["url"])
    return 0


# --------------------------------------------------------------------------- workspace

def cmd_status(args: argparse.Namespace) -> int:
    from stackloom import maps, registry, server, tasks
    from stackloom.config import Config

    conn = _conn()
    cfg = Config.load()
    projects = registry.list_projects(conn)
    rows = maps.all_maps(conn)
    state = server.running()
    running = [t for t in tasks.recent(conn, 20) if t["status"] in tasks.ACTIVE]
    print(LOGO.format(version=__version__, copyright=COPYRIGHT).rstrip())
    print(f"\n  Dashboard     {state['url'] if state else 'not running (run `stackloom`)'}")
    print(f"  Workspaces    {', '.join(cfg.workspaces) or 'none (stackloom init --workspace DIR)'}")
    print(f"  Projects      {len(projects)} in {len({p['group'] for p in projects})} groups")
    print(f"  Code maps     {sum(m['status'] == 'ready' for m in rows)} ready, "
          f"{sum(m['status'] == 'refreshing' for m in rows)} refreshing, "
          f"{sum(m['status'] in ('none', 'error') for m in rows)} missing")
    print(f"  Tasks         {len(running)} running")
    recent = maps.recently_opened(cfg.recent_window_hours)[:5]
    if recent:
        print("\n  Recently opened in Claude Code")
        for item in recent:
            project = registry.containing(conn, item["path"])
            label = project["id"] if project else "(not registered)"
            print(f"    {_ago(item['last_opened']):>9}  {label:<22} {item['path']}")
    return 0


def cmd_projects(args: argparse.Namespace) -> int:
    from stackloom import maps, registry

    conn = _conn()
    if args.id:
        try:
            p = registry.get(conn, args.id)
        except registry.RegistryError as exc:
            print(exc, file=sys.stderr)
            return 1
        p["map"] = maps.sync(conn, p)
        print(json.dumps(p, indent=2))
        return 0
    projects = registry.list_projects(conn, args.group)
    if args.json:
        print(json.dumps(projects, indent=2))
        return 0
    if not projects:
        print("No projects yet. Run `stackloom discover`, or `stackloom import researchos`.")
        return 0
    rows = []
    for p in projects:
        m = maps.get(conn, p["id"])
        stack = ", ".join(p.get("stack") or ([p["runtime"]] if p.get("runtime") else []))
        rows.append([p["id"], p["group"], p.get("kind", "-"), stack[:38], m["status"], _ago(m.get("last_refresh"))])
    print(_table(["ID", "Group", "Kind", "Stack", "Map", "Refreshed"], rows))
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from stackloom.api.app import adopt_candidate, run_scan
    from stackloom.config import Config

    conn = _conn()
    cfg = Config.load()
    if not cfg.workspaces:
        print("No workspace folder set. Run `stackloom init --workspace DIR`.", file=sys.stderr)
        return 1
    print(run_scan(conn, cfg))
    rows = [json.loads(r["data"]) for r in conn.execute("SELECT data FROM candidates ORDER BY path")]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if rows:
        print(_table(["Path", "Group", "Kind", "Stack"],
                     [[r["path"], r["group"], r["kind"], ", ".join(r["stack"])[:40]] for r in rows]))
    for path in args.adopt or []:
        try:
            project = adopt_candidate(conn, str(Path(path).expanduser().resolve()), None, "cli")
            print(f"Registered {project['id']} ({project['path']})")
        except Exception as exc:
            print(f"Could not register {path}: {exc}", file=sys.stderr)
            return 1
    if args.adopt_all:
        for r in rows:
            project = adopt_candidate(conn, r["path"], None, "cli")
            print(f"Registered {project['id']}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    from stackloom import maps, registry

    root = Path(args.path).expanduser() if args.path else None
    if root is None:
        guess = Path.cwd()
        for candidate in (guess, *guess.parents):
            if (candidate / "ResearchOS" / "registry" / "projects.json").exists():
                root = candidate / "ResearchOS"
                break
            if (candidate / "registry" / "projects.json").exists() and (candidate / "admin").is_dir():
                root = candidate
                break
    if root is None:
        print("Pass the ResearchOS folder: stackloom import researchos /path/to/ResearchOS", file=sys.stderr)
        return 1
    conn = _conn()
    try:
        result = registry.import_researchos(conn, root)
    except registry.RegistryError as exc:
        print(exc, file=sys.stderr)
        return 1
    for pid in result["imported"]:
        maps.sync(conn, registry.get(conn, pid))
    print(f"Imported {len(result['imported'])} projects and {result['ports']} port assignments from {root}.")
    if result["skipped"]:
        print("Skipped: " + "; ".join(result["skipped"]))
    print("ResearchOS was only read. Use one of the two admins to start and stop a given app, not both.")
    return 0


def cmd_workspace(args: argparse.Namespace) -> int:
    from stackloom.config import Config

    cfg = Config.load()
    if args.action == "add":
        path = Path(args.path).expanduser().resolve()
        if not path.is_dir():
            print(f"{path} is not a folder.", file=sys.stderr)
            return 1
        if str(path) not in cfg.workspaces:
            cfg.workspaces.append(str(path))
            cfg.save()
    elif args.action == "remove":
        cfg.workspaces = [w for w in cfg.workspaces if w != str(Path(args.path).expanduser().resolve())]
        cfg.save()
    print("\n".join(cfg.workspaces) or "No workspace folders.")
    return 0


# --------------------------------------------------------------------------- codecortex and agents

def cmd_codecortex(args: argparse.Namespace) -> int:
    from stackloom import maps, registry, tasks

    conn = _conn()
    if args.action in (None, "list"):
        rows = [[m["project_id"], m["status"], str(m["stats"].get("nodes", "-")), str(m["stats"].get("files", "-")),
                 _ago(m.get("last_refresh")), _ago(m.get("last_opened"))] for m in maps.all_maps(conn)]
        print(_table(["Project", "Map", "Symbols", "Files", "Refreshed", "Opened"], rows))
        return 0
    if args.action == "recent":
        cfg = __import__("stackloom.config", fromlist=["Config"]).Config.load()
        for item in maps.recently_opened(cfg.recent_window_hours):
            project = registry.containing(conn, item["path"])
            print(f"{_ago(item['last_opened']):>9}  {(project or {}).get('id', '(not registered)'):<22} {item['path']}")
        return 0
    if not args.project:
        print("Name a project: stackloom codecortex map <project>", file=sys.stderr)
        return 1
    try:
        project = registry.get(conn, args.project)
    except registry.RegistryError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.action == "map":
        print(json.dumps(maps.sync(conn, project), indent=2))
        return 0
    if args.action in ("refresh", "rebuild"):
        try:
            task = maps.refresh(conn, project, "cli", rebuild=args.action == "rebuild")
        except registry.RegistryError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Task {task['id']}: {task.get('message') or task['status']}")
        if args.wait:
            import time

            while True:
                current = tasks.get(conn, task["id"])
                tasks.reconcile(conn)
                if current["status"] not in tasks.ACTIVE:
                    print(f"{current['status']}: {current['message']}")
                    return 0 if current["status"] == "done" else 1
                time.sleep(1)
        return 0
    return 1


def cmd_agent(args: argparse.Namespace) -> int:
    if args.action == "open":
        return agent_open(args)
    from stackloom import hooks

    if args.action == "hook":
        if args.hook_action == "install":
            print(hooks.install(Path(sys.argv[0]).resolve() if Path(sys.argv[0]).name == "stackloom" else None))
        elif args.hook_action == "uninstall":
            print(hooks.uninstall())
        else:
            print(hooks.show())
        return 0
    return 1


def agent_open(args: argparse.Namespace) -> int:
    """Called by a Claude Code SessionStart hook (or by hand): make sure the opened
    project has a fresh map. Must return fast and must never fail the session."""
    from stackloom import maps

    folder = args.dir
    if args.hook or (not folder and not sys.stdin.isatty()):
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            folder = folder or payload.get("cwd")
        except ValueError:
            pass
    folder = folder or os.getcwd()
    try:
        conn = _conn()
        result = maps.note_opened(conn, folder, "agent", register_new=True)
    except Exception as exc:  # a hook must not break the coding session
        if not args.hook:
            print(f"stackloom: {exc}", file=sys.stderr)
        return 0
    if not args.hook:
        print(json.dumps(result))
    return 0


# --------------------------------------------------------------------------- admin

def cmd_admin(args: argparse.Namespace) -> int:
    import getpass

    from stackloom import accounts

    conn = _conn()
    if args.action == "reset-password":
        new = getpass.getpass(f"New password for {args.username}: ")
        if new != getpass.getpass("Again: "):
            print("The passwords differ.", file=sys.stderr)
            return 1
        try:
            accounts.reset_password(conn, args.username, new)
        except accounts.AuthError as exc:
            print(exc, file=sys.stderr)
            return 1
        print("Password changed; that account's sessions were ended.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import platform
    import shutil
    import subprocess

    from stackloom import paths
    from stackloom.config import Config

    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python", sys.version_info >= (3, 11), platform.python_version()))
    checks.append(("Home folder", paths.home().exists(), str(paths.home())))
    try:
        import codecortex.version as ccv

        checks.append(("CodeCortex engine", True, ccv.__version__))
    except Exception as exc:
        checks.append(("CodeCortex engine", False, f"not importable: {exc}"))
    for tool in ("git", "docker", "lsof"):
        checks.append((tool, shutil.which(tool) is not None, shutil.which(tool) or "not found"))
    if shutil.which("docker"):
        try:
            r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True,
                               timeout=8, check=False)
            checks.append(("Docker engine", r.returncode == 0,
                           r.stdout.strip() if r.returncode == 0 else "not running; start Docker Desktop"))
        except subprocess.TimeoutExpired:
            checks.append(("Docker engine", False, "did not answer within 8s"))
    cfg = Config.load()
    checks.append(("Workspace folders", bool(cfg.workspaces), ", ".join(cfg.workspaces) or "none set"))
    from stackloom import hooks

    checks.append(("Claude Code hook", hooks.installed(), "installed" if hooks.installed()
                   else "not installed (stackloom agent hook install)"))
    for name, ok, detail in checks:
        print(f"  {'ok ' if ok else '!! '} {name:<20} {detail}")
    return 0 if all(ok for name, ok, _ in checks if name in ("Python", "CodeCortex engine")) else 1


# --------------------------------------------------------------------------- runtime (phase 2)

def _project(conn, project_id: str | None):
    from stackloom import registry

    if not project_id:
        found = registry.containing(conn, os.getcwd())
        if found:
            return found
        print("Name a project (or run this inside its folder).", file=sys.stderr)
        raise SystemExit(1)
    try:
        return registry.get(conn, project_id)
    except registry.RegistryError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)


def cmd_start(args: argparse.Namespace) -> int:
    from stackloom import runtime

    conn = _conn()
    project = _project(conn, args.project)
    try:
        if not project.get("safe_to_launch"):
            print(f"Starting {project['id']} is turned off. Turn it on with `stackloom launch {project['id']} on` after "
                  "reviewing its command.", file=sys.stderr)
            return 1
        if not runtime.approved(conn, project):
            print(f"{project['id']} will run:")
            for step in runtime.start_commands(conn, project, rendered=False):
                print(f"  [{step['name']}] {' '.join(step['command'])}\n      in {step['cwd']}")
            if not (args.yes or (sys.stdin.isatty() and input("Approve this command? [y/N] ").strip().lower() == "y")):
                print("Not started.")
                return 1
            runtime.approve(conn, project, "cli")
        if args.command == "restart":
            runtime.stop(conn, project, "cli")
        result = runtime.start(conn, project, "cli")
    except runtime.Refused as exc:
        print(exc, file=sys.stderr)
        return 1
    for note in result.get("notes") or []:
        print(f"  {note}")
    for svc in runtime.resolved_services(conn, project):
        print(f"  {svc['name']:<10} {svc.get('url') or svc['port']}")
    print(f"{project['id']} started.")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    from stackloom import runtime

    conn = _conn()
    project = _project(conn, args.project)
    try:
        result = runtime.stop(conn, project, "cli")
    except runtime.Refused as exc:
        print(exc, file=sys.stderr)
        return 1
    print("Stopped." if result.get("stopped") else f"{project['id']} was not running.")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    from stackloom import runtime

    conn = _conn()
    print(runtime.logs(_project(conn, args.project), args.lines))
    return 0


def cmd_launch_toggle(args: argparse.Namespace) -> int:
    from stackloom import runtime

    conn = _conn()
    project = _project(conn, args.project)
    try:
        runtime.set_launch(conn, project, args.state == "on", "cli")
    except runtime.Refused as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Launching {project['id']} is now {args.state}.")
    return 0


def cmd_ports(args: argparse.Namespace) -> int:
    from stackloom import runtime

    conn = _conn()
    if args.action == "set":
        try:
            for w in runtime.set_port(conn, _project(conn, args.project), args.service, int(args.port), "cli"):
                print(w)
        except (runtime.Refused, ValueError, TypeError) as exc:
            print(exc, file=sys.stderr)
            return 1
    elif args.action == "auto":
        try:
            for n in runtime.auto_port(conn, _project(conn, args.project), args.service, "cli"):
                print(n)
        except runtime.Refused as exc:
            print(exc, file=sys.stderr)
            return 1
    rows = [[str(r["port"]), r["project"], r["service"], "pinned" if r["pinned"] else "auto",
             ", ".join(f"{o['command']} ({o['pid']})" for o in r["owners"]) if r["in_use"] else "free"]
            for r in runtime.port_table(conn)]
    print(_table(["Port", "Project", "Service", "Mode", "Now"], rows))
    return 0


# --------------------------------------------------------------------------- docker (phase 3)

def cmd_docker(args: argparse.Namespace) -> int:
    from stackloom import docker

    state = docker.info()
    if not state["available"]:
        print(state["reason"])
        return 1
    try:
        if args.what in (None, "status"):
            o = docker.overview()
            print(f"Docker {state['server_version']} ({state.get('context') or 'default'}): {o['running']} running, "
                  f"{o['stopped']} stopped, {o['images']} images, {o['volumes']} volumes, {o['networks']} networks, "
                  f"{o['compose_projects']} Compose projects")
        if args.what in (None, "ps"):
            print(_table(["Name", "Image", "State", "Health", "Compose", "Ports"],
                         [[c["name"], c["image"][:40], c["state"], c["health"] or "-", c["compose_project"] or "-", c["ports"][:40]]
                          for c in docker.containers()]))
        if args.what == "images":
            print(_table(["Repository", "Tag", "Size", "In use"],
                         [[i["repository"], i["tag"], i["size"], "yes" if i["in_use"] else ""] for i in docker.images()]))
        if args.what == "volumes":
            print(_table(["Volume", "Driver", "Containers"],
                         [[v["name"], v["driver"], ", ".join(v["containers"]) or "-"] for v in docker.volumes()]))
        if args.what == "networks":
            print(_table(["Network", "Driver", "Containers"],
                         [[n["name"], n["driver"], ", ".join(n["containers"]) or "-"] for n in docker.networks()]))
        if args.what == "compose":
            print(_table(["Project", "Status", "Folder"],
                         [[c["name"], c["status"], c["working_dir"] or "-"] for c in docker.compose_projects()]))
    except docker.DockerError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------- databases (phase 4)

def cmd_databases(args: argparse.Namespace) -> int:
    from stackloom.databases import connections as dbc
    from stackloom.databases.base import DbError

    conn = _conn()
    try:
        if args.action in (None, "list"):
            rows = [[c["id"], c["engine"], c["path"] or f"{c['host']}:{c['port']}", c["database"] or "-",
                     "read-only" if c["read_only"] else "admin", c["project_id"] or "-"] for c in dbc.list_connections(conn)]
            print(_table(["ID", "Engine", "Where", "Database", "Access", "Project"], rows) if rows
                  else "No connections. Try `stackloom databases discover`.")
        elif args.action == "discover":
            found = dbc.discover(conn)
            print(_table(["Engine", "Where", "Project", "Evidence"],
                         [[f["engine"], f.get("path") or f"{f.get('host')}:{f.get('port')}", f.get("project_id") or "-",
                           f["evidence"]] for f in found]) if found else "Nothing new found.")
        elif args.action == "test":
            print(json.dumps(dbc.test(conn, args.target), indent=2, default=str))
        elif args.action == "query":
            ad = dbc.adapter(conn, args.target)
            result = ad.query(args.database or "", args.sql, confirm=args.yes)
            print(_table([str(c) for c in result["columns"]], [["" if v is None else str(v)[:60] for v in r] for r in result["rows"]])
                  if result["columns"] else f"{result['rowcount']} rows affected.")
            print(f"({len(result['rows'])} rows, {result['ms']} ms{', truncated' if result.get('truncated') else ''})")
        elif args.action == "backup":
            item = dbc.backup(conn, args.target, args.database or "", "cli")
            print(f"Saved {item['path']}")
    except DbError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------- git, backups, reports (phase 6)

def cmd_git(args: argparse.Namespace) -> int:
    from stackloom import gitops, registry

    conn = _conn()
    rows, seen = [], set()
    for p in registry.list_projects(conn):
        s = gitops.summary(p.get("repo_root") or p["path"])
        if not s.get("repo") or s["repo"] in seen:
            continue
        seen.add(s["repo"])
        flags = [f"{s['changed']} changed" if s.get("changed") else "clean"]
        if s.get("ahead"):
            flags.append(f"ahead {s['ahead']}")
        if s.get("behind"):
            flags.append(f"behind {s['behind']}")
        if s.get("conflicts"):
            flags.append(f"{s['conflicts']} CONFLICTS")
        if not s.get("remotes"):
            flags.append("no remote")
        rows.append([p["id"], s.get("branch") or "?", ", ".join(flags)])
    print(_table(["Project", "Branch", "State"], rows))
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    from stackloom import backups, server

    if args.action == "restore":
        if server.running():
            print("Stop the dashboard first: stackloom dashboard --stop", file=sys.stderr)
            return 1
        try:
            print(backups.restore_stackloom(Path(args.target)))
        except backups.BackupError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0
    conn = _conn()
    if args.action == "now":
        item = backups.backup_stackloom(conn, "cli", "manual")
        print(f"Saved {item['path']}")
    elif args.action == "verify":
        print(json.dumps(backups.verify(conn, int(args.target))))
    else:
        print(_table(["ID", "Kind", "Target", "Created", "Size", "File"],
                     [[str(b["id"]), b["kind"], b["target"][:30], b["created_at"][:16], f"{b['size'] // 1024} KB",
                       b["path"] if b["exists"] else "(missing)"] for b in backups.history(conn)]))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from stackloom import diagnostics

    conn = _conn()
    project = _project(conn, args.project)
    if args.kind == "diagnose":
        for c in diagnostics.diagnose(conn, project):
            mark = {"ok": "ok ", "problem": "!! ", "unknown": " ? "}[c["status"]]
            print(f"  {mark} {c['check']:<28} {c['detail']}" + (f"\n       fix: {c['fix']}" if c["fix"] and c["status"] != "ok" else ""))
        return 0
    text, path = diagnostics.handover(conn, project)
    print(text)
    print(f"(saved to {path})")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    import urllib.request

    try:
        with urllib.request.urlopen("https://pypi.org/pypi/stackloom/json", timeout=8) as response:
            latest = json.load(response)["info"]["version"]
    except Exception as exc:
        print(f"Could not check PyPI: {exc}", file=sys.stderr)
        return 1

    def key(v: str):
        return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))

    if key(latest) <= key(__version__):
        print(f"stackloom {__version__} is the latest version.")
        return 0
    exe = sys.executable
    how = ("brew upgrade stackloom" if "/Cellar/" in exe or "/homebrew/" in exe.lower()
           else "pipx upgrade stackloom" if "/pipx/" in exe else f"{exe} -m pip install --upgrade stackloom")
    print(f"stackloom {latest} is available (you have {__version__}). Update with:\n  {how}\n"
          "Then restart the dashboard: stackloom dashboard --stop && stackloom")
    return 0


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stackloom", description="One workspace. Every project. Complete control.")
    parser.add_argument("--version", action="version", version=f"stackloom {__version__}\n{COPYRIGHT} ({COPYRIGHT_URL})")
    parser.add_argument("--port", type=int, help="dashboard port (default: last used, else a free one)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--foreground", action="store_true", help="run the dashboard in this terminal")
    parser.set_defaults(func=cmd_launch)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="set up the home folder, database and first account")
    p.add_argument("--workspace", action="append", help="workspace folder to manage (repeatable)")
    p.add_argument("--import-researchos", metavar="DIR", help="also import a ResearchOS admin registry")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("serve", help="run the dashboard server in the foreground")
    p.add_argument("--port", type=int, required=True)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("dashboard", help="print the dashboard address, or stop it")
    p.add_argument("--stop", action="store_true")
    p.set_defaults(func=cmd_dashboard)

    sub.add_parser("status", help="workspace summary").set_defaults(func=cmd_status)

    p = sub.add_parser("projects", help="list projects, or show one")
    p.add_argument("id", nargs="?")
    p.add_argument("--group")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("discover", help="scan the workspace for unregistered projects")
    p.add_argument("--adopt", action="append", metavar="PATH", help="register this discovered folder")
    p.add_argument("--adopt-all", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("import", help="import projects from another admin")
    p.add_argument("source", choices=["researchos"])
    p.add_argument("path", nargs="?")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("workspace", help="list, add or remove workspace folders")
    p.add_argument("action", nargs="?", choices=["list", "add", "remove"], default="list")
    p.add_argument("path", nargs="?")
    p.set_defaults(func=cmd_workspace)

    p = sub.add_parser("codecortex", help="CodeCortex maps: list, map, refresh, rebuild, recent")
    p.add_argument("action", nargs="?", choices=["list", "map", "refresh", "rebuild", "recent"])
    p.add_argument("project", nargs="?")
    p.add_argument("--wait", action="store_true", help="wait for a refresh to finish")
    p.set_defaults(func=cmd_codecortex)

    p = sub.add_parser("agent", help="coding-agent integration")
    agent_sub = p.add_subparsers(dest="action", required=True)
    o = agent_sub.add_parser("open", help="a coding agent opened a folder: refresh its map")
    o.add_argument("dir", nargs="?")
    o.add_argument("--hook", action="store_true", help="read Claude Code hook JSON from stdin; stay silent")
    h = agent_sub.add_parser("hook", help="the Claude Code SessionStart hook")
    h.add_argument("hook_action", nargs="?", choices=["show", "install", "uninstall"], default="show")
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("admin", help="account recovery")
    admin_sub = p.add_subparsers(dest="action", required=True)
    r = admin_sub.add_parser("reset-password")
    r.add_argument("username")
    p.set_defaults(func=cmd_admin)

    sub.add_parser("doctor", help="check the environment").set_defaults(func=cmd_doctor)

    for name, fn in (("start", cmd_start), ("restart", cmd_start), ("stop", cmd_stop)):
        q = sub.add_parser(name, help=f"{name} a project (default: the one in this folder)")
        q.add_argument("project", nargs="?")
        q.add_argument("-y", "--yes", action="store_true", help="approve a new start command without asking")
        q.set_defaults(func=fn)
    q = sub.add_parser("logs", help="a project's log")
    q.add_argument("project", nargs="?")
    q.add_argument("-n", "--lines", type=int, default=200)
    q.set_defaults(func=cmd_logs)
    q = sub.add_parser("launch", help="turn starting a project from STACKLOOM on or off")
    q.add_argument("project")
    q.add_argument("state", choices=["on", "off"])
    q.set_defaults(func=cmd_launch_toggle)
    q = sub.add_parser("ports", help="port registry: list, set PROJECT SERVICE PORT, auto PROJECT [SERVICE]")
    q.add_argument("action", nargs="?", choices=["list", "set", "auto"], default="list")
    q.add_argument("project", nargs="?")
    q.add_argument("service", nargs="?")
    q.add_argument("port", nargs="?")
    q.set_defaults(func=cmd_ports)
    q = sub.add_parser("docker", help="Docker status and resources")
    q.add_argument("what", nargs="?", choices=["status", "ps", "images", "volumes", "networks", "compose"])
    q.set_defaults(func=cmd_docker)
    q = sub.add_parser("databases", help="database connections: list, discover, test ID, query ID SQL, backup ID")
    q.add_argument("action", nargs="?", choices=["list", "discover", "test", "query", "backup"])
    q.add_argument("target", nargs="?")
    q.add_argument("sql", nargs="?")
    q.add_argument("--database", "-d")
    q.add_argument("-y", "--yes", action="store_true", help="confirm a statement that changes data")
    q.set_defaults(func=cmd_databases)
    sub.add_parser("git", help="Git state of every repository").set_defaults(func=cmd_git)
    q = sub.add_parser("backup", help="STACKLOOM backups: list, now, verify ID, restore FILE")
    q.add_argument("action", nargs="?", choices=["list", "now", "verify", "restore"], default="list")
    q.add_argument("target", nargs="?")
    q.set_defaults(func=cmd_backup)
    q = sub.add_parser("report", help="diagnose PROJECT, or handover PROJECT")
    q.add_argument("kind", choices=["diagnose", "handover"])
    q.add_argument("project", nargs="?")
    q.set_defaults(func=cmd_report)
    sub.add_parser("update", help="check PyPI for a newer STACKLOOM").set_defaults(func=cmd_update)
    return parser


def main(argv: list[str] | None = None) -> int:
    from stackloom.logs import setup

    args = build_parser().parse_args(argv)
    setup()
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
