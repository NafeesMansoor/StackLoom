"""Runtime: ports, start, stop, health and logs for registered projects.

Adapted from the ResearchOS admin (ResearchOS/admin/project_registry.py):

- Ports are never written in the registry. Services use ${PORT:<service>};
  real ports live in the `ports` table. First start takes the first free port
  in the pool, later starts reuse it, a busy unpinned port moves, a busy pinned
  port blocks the start and names the holder. Nothing is ever killed to free a port.
- Start commands are argument lists. The exact command is shown and must be
  approved once; a change in its shape needs approval again.
- A recorded PID is ours only while its kernel start time matches. Stop sends
  SIGTERM to the process group, then SIGKILL after a timeout.
- Compose apps get a generated override in ~/.stackloom/state/compose that
  publishes the assigned ports on 127.0.0.1. The project's compose file is
  never edited, and stop never removes containers or volumes.
- An app that answers on its port but was not started by STACKLOOM is
  reported as "external" and is never stopped.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from stackloom import activity, paths, procs
from stackloom.config import Config
from stackloom.registry import PORT_PLACEHOLDER
from stackloom.security import redact

LOG_LIMIT = 5_000_000


class RuntimeError_(RuntimeError):
    """An action was refused or failed; the message is for the user."""


Refused = RuntimeError_


# --------------------------------------------------------------------------- probes

def port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        pass
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return True
    return False


def port_owners(port: int) -> list[dict[str, Any]]:
    """Who listens on a port (via lsof): [{"pid": n, "command": name}]."""
    try:
        result = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"],
                                capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    owners: list[dict[str, Any]] = []
    pid = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("c") and pid and not any(o["pid"] == pid for o in owners):
            owners.append({"pid": pid, "command": line[1:]})
    return owners


def owners_text(port: int) -> str:
    return ", ".join(f"{o['command']} (pid {o['pid']})" for o in port_owners(port))


def check_health(service: dict[str, Any], timeout: float = 2.0) -> str:
    """'healthy', 'down', 'http 5xx' or 'n/a'. `service` must be resolved (real port, rendered URLs)."""
    health = service.get("health") or {}
    if service.get("port") is None:
        return "n/a"
    kind = health.get("type")
    if kind == "http" and health.get("url"):
        try:
            with urllib.request.urlopen(health["url"], timeout=timeout) as response:
                return "healthy" if response.status < 500 else f"http {response.status}"
        except urllib.error.HTTPError as exc:
            return "healthy" if exc.code < 500 else f"http {exc.code}"
        except (urllib.error.URLError, OSError, ValueError):
            return "down"
    if kind in ("tcp", None):
        try:
            with socket.create_connection((service.get("host", "127.0.0.1"), int(service["port"])), timeout=timeout):
                return "healthy"
        except OSError:
            return "down"
    return "n/a"


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE parser for .env files. Values are used at start, never stored or printed."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def with_port(url: str, port: int, host: str | None = None) -> str:
    parts = urlsplit(url)
    userinfo, _, hostport = parts.netloc.rpartition("@")
    current_host = hostport.rsplit(":", 1)[0] if ":" in hostport else hostport
    return urlunsplit(parts._replace(netloc=f"{userinfo + '@' if userinfo else ''}{host or current_host}:{port}"))


_docker_cache: dict[str, Any] = {"at": 0.0, "ok": False}


def docker_available(max_age: float = 10.0) -> bool:
    if time.monotonic() - _docker_cache["at"] < max_age:
        return _docker_cache["ok"]
    try:
        ok = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True,
                            timeout=8, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    _docker_cache.update(at=time.monotonic(), ok=ok)
    return ok


# --------------------------------------------------------------------------- ports

def pool(cfg: Config | None = None) -> tuple[int, int]:
    return (cfg or Config.load()).port_pool


def ports_of(conn: sqlite3.Connection, project_id: str) -> dict[str, int]:
    return {r["service"]: r["port"] for r in conn.execute("SELECT service, port FROM ports WHERE project_id = ?",
                                                          (project_id,))}


def _service(project: dict[str, Any], name: str) -> dict[str, Any]:
    for svc in project.get("services", []):
        if svc["name"] == name:
            return svc
    names = ", ".join(s["name"] for s in project.get("services", [])) or "none"
    raise Refused(f"{project['id']} has no service {name!r} (services: {names})")


def _allocate(conn: sqlite3.Connection, avoid: set[int], cfg: Config | None = None) -> int:
    start, end = pool(cfg)
    taken = {r[0] for r in conn.execute("SELECT port FROM ports")} | avoid
    dashboard = (cfg or Config.load()).dashboard_port
    for port in range(start, end + 1):
        if port not in taken and port != dashboard and not port_in_use(port):
            return port
    raise Refused(f"No free port left in {start}–{end}. Widen the range in Settings.")


def ensure_ports(conn: sqlite3.Connection, project: dict[str, Any]) -> list[str]:
    """Give every service a usable port before a start. Returns notes on what changed."""
    notes: list[str] = []
    for svc in project.get("services", []):
        name, host = svc["name"], svc.get("host", "127.0.0.1")
        row = conn.execute("SELECT port, pinned FROM ports WHERE project_id = ? AND service = ?",
                           (project["id"], name)).fetchone()
        old = None
        if row:
            if not port_in_use(row["port"], host):
                continue
            if row["pinned"]:
                raise Refused(
                    f"{project['id']}/{name}: pinned port {row['port']} is in use by "
                    f"{owners_text(row['port']) or 'another program'}. Nothing was stopped. Pick another port "
                    f"or let STACKLOOM choose one.")
            old = row["port"]
        new = _allocate(conn, {old} if old else set())
        conn.execute("INSERT INTO ports (project_id, service, port, pinned) VALUES (?,?,?,0)"
                     " ON CONFLICT(project_id, service) DO UPDATE SET port = excluded.port, pinned = 0",
                     (project["id"], name, new))
        notes.append(f"{name}: port {old} was busy, moved to {new}" if old else f"{name}: assigned port {new}")
    return notes


def set_port(conn: sqlite3.Connection, project: dict[str, Any], service: str, port: int, actor: str) -> list[str]:
    _service(project, service)
    require_stopped(conn, project, "change its ports")
    if not 1024 <= port <= 65535:
        raise Refused("A port must be between 1024 and 65535.")
    holder = conn.execute("SELECT project_id, service FROM ports WHERE port = ? AND NOT (project_id = ? AND service = ?)",
                          (port, project["id"], service)).fetchone()
    if holder:
        raise Refused(f"Port {port} is already assigned to {holder['project_id']}/{holder['service']}.")
    conn.execute("INSERT INTO ports (project_id, service, port, pinned) VALUES (?,?,?,1)"
                 " ON CONFLICT(project_id, service) DO UPDATE SET port = excluded.port, pinned = 1",
                 (project["id"], service, port))
    activity.record(conn, actor, "port.pin", f"{project['id']}/{service}", detail=str(port))
    if port_in_use(port):
        return [f"Port {port} is in use now by {owners_text(port) or 'another program'}; "
                "starting will be refused until it is free."]
    return []


def auto_port(conn: sqlite3.Connection, project: dict[str, Any], service: str | None, actor: str) -> list[str]:
    require_stopped(conn, project, "change its ports")
    names = [service] if service else [s["name"] for s in project.get("services", [])]
    for name in names:
        _service(project, name)
        conn.execute("DELETE FROM ports WHERE project_id = ? AND service = ?", (project["id"], name))
    activity.record(conn, actor, "port.auto", f"{project['id']}/{service or '*'}")
    return ensure_ports(conn, project)


def port_table(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every assignment with whether it is in use now and by whom."""
    rows = []
    for r in conn.execute("SELECT p.project_id, p.service, p.port, p.pinned, j.data FROM ports p"
                          " JOIN projects j ON j.id = p.project_id ORDER BY p.port"):
        busy = port_in_use(r["port"])
        rows.append({"project": r["project_id"], "service": r["service"], "port": r["port"], "pinned": bool(r["pinned"]),
                     "in_use": busy, "owners": port_owners(r["port"]) if busy else []})
    return rows


# --------------------------------------------------------------------------- rendering

def render(conn: sqlite3.Connection, project: dict[str, Any], value: str) -> str:
    ports = ports_of(conn, project["id"])

    def sub(match: re.Match) -> str:
        if match.group(1) not in ports:
            raise Refused(f"{project['id']}/{match.group(1)} has no port yet; it is assigned at the first start.")
        return str(ports[match.group(1)])

    return PORT_PLACEHOLDER.sub(sub, value)


def resolved_services(conn: sqlite3.Connection, project: dict[str, Any]) -> list[dict[str, Any]]:
    rows = {r["service"]: r for r in conn.execute("SELECT service, port, pinned FROM ports WHERE project_id = ?",
                                                  (project["id"],))}
    out = []
    for svc in project.get("services", []):
        item = json.loads(json.dumps(svc))
        row = rows.get(svc["name"])
        item["port"] = row["port"] if row else None
        item["pinned"] = bool(row["pinned"]) if row else False
        if item["port"] is None:
            item["url"] = None
        else:
            if svc.get("url"):
                item["url"] = render(conn, project, svc["url"])
            if (svc.get("health") or {}).get("url"):
                item["health"]["url"] = render(conn, project, svc["health"]["url"])
        out.append(item)
    return out


def compose_spec(project: dict[str, Any]) -> dict[str, Any] | None:
    launch = project.get("launch") or {}
    if launch.get("type") == "docker-compose":
        return launch
    return launch.get("compose")


def _override_path(project: dict[str, Any]) -> Path:
    path = paths.home() / "state" / "compose"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{project['id']}.override.yml"


def write_compose_override(conn: sqlite3.Connection, project: dict[str, Any]) -> Path:
    ports = ports_of(conn, project["id"])
    spec = compose_spec(project) or {}
    by_service: dict[str, dict[str, Any]] = {}
    for svc in project.get("services", []):
        if not svc.get("compose_service") or svc["name"] not in ports:
            continue
        entry = by_service.setdefault(svc["compose_service"], {"ports": [], "env": {}})
        entry["ports"].append(f"{svc.get('host', '127.0.0.1')}:{ports[svc['name']]}:{svc['container_port']}")
    for compose_service, env in (spec.get("compose_env") or {}).items():
        by_service.setdefault(compose_service, {"ports": [], "env": {}})["env"].update(
            {k: render(conn, project, v) for k, v in env.items()})
    lines = [f"# Generated by STACKLOOM for {project['id']} at {datetime.now().isoformat(timespec='seconds')}. "
             "Do not edit; change ports in STACKLOOM.", "services:"]
    for name, entry in by_service.items():
        lines.append(f"  {name}:")
        if entry["ports"]:
            lines.append("    ports: !override")
            lines += [f"      - {json.dumps(p)}" for p in entry["ports"]]
        if entry["env"]:
            lines.append("    environment:")
            lines += [f"      {k}: {json.dumps(v)}" for k, v in entry["env"].items()]
    path = _override_path(project)
    path.write_text("\n".join(lines) + "\n")
    return path


def launch_cwd(project: dict[str, Any]) -> Path:
    cwd = (project.get("launch") or {}).get("cwd")
    return Path(cwd) if cwd else Path(project["path"])


def compose_base(project: dict[str, Any]) -> list[str]:
    spec = compose_spec(project) or {}
    args = ["docker", "compose", "-p", spec["compose_project"]]
    for compose_file in spec.get("compose_files", []):
        args += ["-f", compose_file]
    override = _override_path(project)
    if project.get("services") and override.exists():
        args += ["-f", str(override)]
    return args


def _components(project: dict[str, Any]) -> list[dict[str, Any]]:
    launch = project["launch"]
    if "processes" in launch:
        return launch["processes"]
    return [{"name": "main", "command": launch.get("command"), "cwd": launch.get("cwd"), "env": launch.get("env", {})}]


def start_commands(conn: sqlite3.Connection, project: dict[str, Any], rendered: bool = True) -> list[dict[str, Any]]:
    """Everything a start runs: [{name, command, cwd, env}]. rendered=False keeps ${PORT:...}
    (used for approval, so a port change does not need approval again but a new command does)."""
    launch = project.get("launch")
    if not launch:
        raise Refused(f"{project['id']} has no start command. Add one to its registry entry first.")
    fill = (lambda v: render(conn, project, v)) if rendered else (lambda v: v)

    def env_value(value: Any) -> str:
        if isinstance(value, str):
            return fill(value)
        if not rendered:
            return f"<{value['key']} from {value['from_env_file']}, port {value.get('port', 'unchanged')}>"
        source = read_env_file(Path(value["from_env_file"])).get(value["key"])
        if source is None:
            raise Refused(f"{project['id']}: {value['key']} is not in {value['from_env_file']}")
        return with_port(source, int(fill(value["port"])), value.get("host")) if value.get("port") else source

    if launch["type"] == "process":
        steps = [{"name": c.get("name", "main"), "command": [fill(a) for a in c["command"]],
                  "cwd": str(Path(c["cwd"]) if c.get("cwd") else Path(project["path"])),
                  "env": {k: env_value(v) for k, v in (c.get("env") or {}).items()}} for c in _components(project)]
        spec = launch.get("compose")
        if spec:
            steps.insert(0, {"name": "compose", "command": compose_base(project) + ["up", "--detach", "--wait",
                                                                                   *spec.get("services", [])],
                             "cwd": str(launch_cwd(project)), "env": {}})
        return steps
    return [{"name": "compose", "command": compose_base(project) + ["up", *launch.get("up_args", ["--detach"])],
             "cwd": str(launch_cwd(project)), "env": {}}]


def stop_command(project: dict[str, Any]) -> list[str]:
    spec = compose_spec(project) or {}
    return compose_base(project) + ["stop", "--timeout", str(spec.get("stop_timeout", 20))] + list(spec.get("services", []))


# --------------------------------------------------------------------------- approval

def fingerprint(conn: sqlite3.Connection, project: dict[str, Any]) -> str:
    spec = start_commands(conn, project, rendered=False)
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def approved(conn: sqlite3.Connection, project: dict[str, Any]) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (f"approval:{project['id']}",)).fetchone()
    return bool(row) and row["value"] == fingerprint(conn, project)


def approve(conn: sqlite3.Connection, project: dict[str, Any], actor: str) -> None:
    conn.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (f"approval:{project['id']}", fingerprint(conn, project)))
    activity.record(conn, actor, "runtime.approve_command", project["id"])


# --------------------------------------------------------------------------- state

def _state_path(project_id: str) -> Path:
    path = paths.home() / "state" / "proc"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{project_id}.json"


def log_path(project_id: str) -> Path:
    path = paths.log_dir() / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{project_id}.log"


def _bound_log(path: Path) -> None:
    """Keep a project log under LOG_LIMIT by dropping its oldest part."""
    try:
        if path.stat().st_size > LOG_LIMIT:
            with path.open("rb") as fh:
                fh.seek(-LOG_LIMIT // 5, os.SEEK_END)
                tail = fh.read()
            path.write_bytes(b"[older lines removed]\n" + tail)
    except OSError:
        pass


def _process_state(project_id: str) -> dict[str, Any] | None:
    path = _state_path(project_id)
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
    except ValueError:
        path.unlink(missing_ok=True)
        return None
    alive = [p for p in state.get("processes", []) if procs.alive(p.get("pid"), p.get("start_time"))]
    if not alive:
        path.unlink(missing_ok=True)
        return None
    return {**state, "alive": alive, "total": len(state["processes"])}


def compose_containers(project: dict[str, Any]) -> list[dict[str, Any]]:
    result = subprocess.run(compose_base(project) + ["ps", "--all", "--format", "json"], cwd=launch_cwd(project),
                            capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise Refused(redact(result.stderr.strip() or "docker compose ps failed"))
    out = result.stdout.strip()
    if not out:
        return []
    return json.loads(out) if out.startswith("[") else [json.loads(line) for line in out.splitlines() if line.strip()]


def status(conn: sqlite3.Connection, project: dict[str, Any]) -> dict[str, Any]:
    """state: running | partial | stopped | external | docker-unavailable | not managed | error."""
    launch = project.get("launch")
    if not launch:
        return {"state": "not managed"}
    if launch["type"] == "process":
        state = _process_state(project["id"])
        result: dict[str, Any] = {"state": "stopped"}
        if state:
            pids = {p["name"]: p["pid"] for p in state["alive"]}
            result = {"state": "running" if len(state["alive"]) == state["total"] else "partial",
                      "processes": pids, "since": state.get("started_at")}
        spec = launch.get("compose")
        if spec and docker_available():
            try:
                wanted = set(spec.get("services", []))
                containers = {c.get("Service"): c.get("State", "?") for c in compose_containers(project)
                              if not wanted or c.get("Service") in wanted}
            except (Refused, subprocess.TimeoutExpired):
                containers = {}
            result["containers"] = containers
            up = [n for n, st in containers.items() if st == "running"]
            if result["state"] == "stopped" and up:
                result["state"] = "partial"
            elif result["state"] == "running" and len(up) < len(wanted):
                result["state"] = "partial"
        if result["state"] == "stopped":
            # "external" only when the app's own health check passes on its port; a
            # stranger merely holding the port is a conflict, reported at start.
            busy = [s for s in resolved_services(conn, project) if s["port"] and port_in_use(s["port"])]
            if busy and all(check_health(s) == "healthy" for s in busy):
                result = {"state": "external", "detail": "Something answers on its port, but STACKLOOM did not start "
                          "it. It is shown here and never stopped.",
                          "owners": {s["name"]: port_owners(s["port"]) for s in busy}}
        return result
    if not docker_available():
        return {"state": "docker-unavailable"}
    try:
        containers = compose_containers(project)
    except (Refused, subprocess.TimeoutExpired) as exc:
        return {"state": "error", "detail": str(exc)}
    services = {c.get("Service", c.get("Name")): c.get("State", "?") for c in containers}
    running = [n for n, st in services.items() if st == "running"]
    state = "stopped" if not running else "running" if len(running) == len(services) else "partial"
    return {"state": state, "containers": services}


def require_stopped(conn: sqlite3.Connection, project: dict[str, Any], action: str) -> None:
    if status(conn, project)["state"] in ("running", "partial"):
        raise Refused(f"{project['id']} is running; stop it before you {action}.")


def health(conn: sqlite3.Connection, project: dict[str, Any]) -> dict[str, str]:
    return {s["name"]: check_health(s) for s in resolved_services(conn, project)}


def conflicts(conn: sqlite3.Connection, project: dict[str, Any]) -> list[str]:
    out = []
    for svc in resolved_services(conn, project):
        if svc["port"] and port_in_use(svc["port"], svc.get("host", "127.0.0.1")):
            who = owners_text(svc["port"])
            out.append(f"{svc['name']} 127.0.0.1:{svc['port']}{' held by ' + who if who else ''}")
    return out


# --------------------------------------------------------------------------- actions

def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as log:
        log.write(text)


def _run_logged(command: list[str], cwd: str | Path, log: Path, label: str, timeout: float) -> None:
    _append(log, f"\n===== {datetime.now().isoformat(timespec='seconds')} {label}: {' '.join(command)}\n")
    with log.open("a", encoding="utf-8") as fh:
        try:
            result = subprocess.run(command, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise Refused(f"{label} did not finish within {timeout:.0f}s; see the log.")
        except OSError as exc:
            raise Refused(f"{label} could not run: {exc}")
    if result.returncode != 0:
        raise Refused(f"{label} failed (exit {result.returncode}). Last lines:\n" + redact(tail(log, 25)))


def start(conn: sqlite3.Connection, project: dict[str, Any], actor: str) -> dict[str, Any]:
    pid = project["id"]
    if not project.get("safe_to_launch"):
        raise Refused(f"Starting {pid} is turned off. Review its start command and turn launching on first.")
    if not approved(conn, project):
        raise Refused(f"The start command of {pid} has not been approved yet (or it changed since).")
    current = status(conn, project)
    if current["state"] in ("running", "partial"):
        raise Refused(f"{pid} is already {current['state']}; restart or stop it instead.")
    if current["state"] == "docker-unavailable":
        raise Refused("Docker is not running. Start Docker Desktop, then try again.")
    if current["state"] == "external":
        raise Refused(f"{pid} already answers on its port, started outside STACKLOOM. Nothing was changed.")
    notes = ensure_ports(conn, project)
    if compose_spec(project) and any(s.get("compose_service") for s in project.get("services", [])):
        write_compose_override(conn, project)
    steps = start_commands(conn, project)
    clash = conflicts(conn, project)
    if clash:
        raise Refused(f"Port conflict for {pid}: " + "; ".join(clash) + ". Nothing was stopped.")
    log = log_path(pid)
    _bound_log(log)
    launch = project["launch"]
    if launch["type"] == "docker-compose":
        _run_logged(steps[0]["command"], steps[0]["cwd"], log, "compose up", launch.get("start_timeout", 900))
        activity.record(conn, actor, "runtime.start", pid)
        return {"notes": notes}
    if launch.get("compose"):
        _run_logged(steps[0]["command"], steps[0]["cwd"], log, "compose up", launch["compose"].get("start_timeout", 300))
        steps = steps[1:]
    try:
        result = _start_processes(project, steps, log)
    except Refused:
        if launch.get("compose"):
            _run_logged(stop_command(project), launch_cwd(project), log, "compose stop", 120)
        activity.record(conn, actor, "runtime.start", pid, result="failed")
        raise
    activity.record(conn, actor, "runtime.start", pid, detail=f"pid {result['pids']}")
    return {**result, "notes": notes}


def _start_processes(project: dict[str, Any], steps: list[dict[str, Any]], log: Path) -> dict[str, Any]:
    started: list[dict[str, Any]] = []
    state_path = _state_path(project["id"])
    with log.open("a", encoding="utf-8") as fh:
        for step in steps:
            fh.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} start [{step['name']}]: "
                     f"{' '.join(step['command'])} (cwd {step['cwd']})\n")
            fh.flush()
            try:
                proc = subprocess.Popen(step["command"], cwd=step["cwd"], stdout=fh, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True, env={**os.environ, **step["env"]})
            except OSError as exc:
                _kill(started, 5)
                state_path.unlink(missing_ok=True)
                raise Refused(f"{project['id']}/{step['name']} could not be started: {exc}")
            started.append({"name": step["name"], "pid": proc.pid, "start_time": procs.start_time(proc.pid),
                            "command": step["command"], "_proc": proc})
            state_path.write_text(json.dumps({"started_at": datetime.now().isoformat(timespec="seconds"),
                                              "processes": [{k: v for k, v in s.items() if k != "_proc"} for s in started]},
                                             indent=2))
        time.sleep(1.0)
    dead = [s for s in started if s["_proc"].poll() is not None]
    if dead:
        _kill([s for s in started if s not in dead], 5)
        state_path.unlink(missing_ok=True)
        names = ", ".join(f"{s['name']} (exit {s['_proc'].returncode})" for s in dead)
        raise Refused(f"{project['id']} exited straight away: {names}. The others were stopped. Last lines:\n"
                      + redact(tail(log, 20)))
    return {"pids": ", ".join(str(s["pid"]) for s in started)}


def _kill(entries: list[dict[str, Any]], timeout: float) -> bool:
    """SIGTERM each process group we started, SIGKILL what is left. True if SIGKILL was needed."""
    forced, targets = False, []
    for entry in entries:
        pid = int(entry["pid"])
        if not procs.alive(pid, entry.get("start_time")):
            continue
        try:
            if os.getpgid(pid) != pid:
                continue  # no longer its own group leader: not something we started
            os.killpg(pid, signal.SIGTERM)
            targets.append(pid)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    for pid in targets:
        if not _wait_gone(pid, max(0.0, deadline - time.monotonic())):
            forced = True
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _wait_gone(pid, 5)
    return forced


def _wait_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done == pid:
                return True
        except ChildProcessError:
            pass
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def stop(conn: sqlite3.Connection, project: dict[str, Any], actor: str, timeout: float = 10.0) -> dict[str, Any]:
    """Graceful stop. Containers and volumes are kept (compose stop, never down)."""
    pid = project["id"]
    launch = project.get("launch")
    if not launch:
        raise Refused(f"{pid} has no start command, so there is nothing to stop.")
    log = log_path(pid)
    current = status(conn, project)
    if current["state"] == "external":
        raise Refused(f"{pid} was started outside STACKLOOM, so STACKLOOM will not stop it.")
    if launch["type"] == "docker-compose":
        if current["state"] not in ("running", "partial"):
            return {"stopped": False, "reason": "not running"}
        _run_logged(stop_command(project), launch_cwd(project), log, "compose stop", 300)
        activity.record(conn, actor, "runtime.stop", pid)
        return {"stopped": True}
    state = _process_state(pid)
    forced = False
    if state:
        forced = _kill(list(reversed(state["alive"])), timeout)
        _state_path(pid).unlink(missing_ok=True)
        _append(log, f"\n===== {datetime.now().isoformat(timespec='seconds')} stopped"
                     f"{' (SIGKILL after timeout)' if forced else ''}\n")
    if launch.get("compose") and any(st == "running" for st in current.get("containers", {}).values()):
        _run_logged(stop_command(project), launch_cwd(project), log, "compose stop", 300)
    elif not state:
        return {"stopped": False, "reason": "not running"}
    activity.record(conn, actor, "runtime.stop", pid, detail="forced" if forced else "")
    return {"stopped": True, "forced": forced}


def restart(conn: sqlite3.Connection, project: dict[str, Any], actor: str) -> dict[str, Any]:
    stop(conn, project, actor)
    return start(conn, project, actor)


def tail(path: Path, lines: int = 200) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - 400_000))
        content = fh.read().decode("utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def logs(project: dict[str, Any], lines: int = 200, service: str | None = None) -> str:
    parts = []
    own = tail(log_path(project["id"]), lines)
    if own:
        parts.append(own)
    if compose_spec(project) and docker_available():
        try:
            result = subprocess.run(compose_base(project) + ["logs", "--no-color", "--tail", str(lines)]
                                    + ([service] if service else []), cwd=launch_cwd(project), capture_output=True,
                                    text=True, timeout=30, check=False)
            if (result.stdout + result.stderr).strip():
                parts += ["----- container logs", (result.stdout + result.stderr).strip()]
        except (OSError, subprocess.TimeoutExpired):
            parts.append("(container logs did not answer)")
    return redact("\n".join(parts)) or "No log lines yet."


def set_launch(conn: sqlite3.Connection, project: dict[str, Any], enabled: bool, actor: str) -> dict[str, Any]:
    from stackloom import registry

    if enabled and not project.get("launch"):
        raise Refused(f"{project['id']} has no start command to enable.")
    updated = {**project, "safe_to_launch": bool(enabled)}
    activity.record(conn, actor, "runtime.launch_enabled" if enabled else "runtime.launch_disabled", project["id"])
    return registry.save(conn, updated, source=project["source"], actor=actor)
