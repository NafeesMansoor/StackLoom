"""Docker: workspace-wide inventory and operations through the `docker` CLI.

Uses `--format json` output, so no Docker SDK is needed and Docker Desktop,
Colima and OrbStack all work. Nothing here runs unless the engine answers.
Containers are matched to projects through Compose labels
(com.docker.compose.project.working_dir), never by guessing names.

Safety: removing a container never removes its volumes; `compose down` never
passes -v unless the caller sets remove_volumes and confirm; removing an image
in use or a volume attached to a container is refused.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from stackloom import paths
from stackloom.security import is_secret_name, redact

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,250}$")
_info_cache: dict[str, Any] = {"at": 0.0, "value": None}


class DockerError(RuntimeError):
    pass


def _check(name: str, what: str = "name") -> str:
    if not NAME_RE.match(name or ""):
        raise DockerError(f"Invalid {what}: {name!r}")
    return name


def run(args: list[str], timeout: float = 60, cwd: str | Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    if not shutil.which("docker"):
        raise DockerError("The docker command is not installed.")
    try:
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)
    except subprocess.TimeoutExpired:
        raise DockerError(f"docker {args[0]} did not answer within {timeout:.0f}s.")
    if check and result.returncode != 0:
        raise DockerError(redact(result.stderr.strip() or result.stdout.strip() or f"docker {args[0]} failed"))
    return result


def _lines(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def info(max_age: float = 10.0) -> dict[str, Any]:
    """Engine status. {'available': False, 'reason': ...} when it does not answer."""
    if _info_cache["value"] is not None and time.monotonic() - _info_cache["at"] < max_age:
        return _info_cache["value"]
    if not shutil.which("docker"):
        value = {"available": False, "reason": "Docker is not installed."}
    else:
        try:
            data = json.loads(run(["info", "--format", "{{json .}}"], timeout=8).stdout or "{}")
            value = {"available": True, "server_version": data.get("ServerVersion"), "os": data.get("OperatingSystem"),
                     "cpus": data.get("NCPU"), "memory": data.get("MemTotal"), "containers": data.get("Containers"),
                     "running": data.get("ContainersRunning"), "paused": data.get("ContainersPaused"),
                     "stopped": data.get("ContainersStopped"), "images": data.get("Images"),
                     "context": run(["context", "show"], timeout=5, check=False).stdout.strip()}
        except (DockerError, ValueError) as exc:
            value = {"available": False, "reason": "Docker is installed but the engine is not running. Start Docker Desktop."
                     if "connect" in str(exc).lower() or "daemon" in str(exc).lower() else str(exc)}
    _info_cache.update(at=time.monotonic(), value=value)
    return value


def require() -> None:
    state = info()
    if not state["available"]:
        raise DockerError(state["reason"])


def _labels(text: str) -> dict[str, str]:
    out = {}
    for part in (text or "").split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k] = v
    return out


# --------------------------------------------------------------------------- inventory

def containers() -> list[dict[str, Any]]:
    require()
    rows = _lines(run(["ps", "--all", "--no-trunc", "--format", "{{json .}}"]).stdout)
    out = []
    for r in rows:
        labels = _labels(r.get("Labels", ""))
        state = r.get("State", "")
        status = r.get("Status", "")
        health = "unhealthy" if "(unhealthy)" in status else "healthy" if "(healthy)" in status else \
            "starting" if "(health: starting)" in status else ""
        out.append({
            "id": r.get("ID", "")[:12], "name": r.get("Names", ""), "image": r.get("Image", ""), "state": state,
            "status": status, "health": health, "ports": r.get("Ports", ""), "created": r.get("CreatedAt", ""),
            "compose_project": labels.get("com.docker.compose.project", ""),
            "compose_service": labels.get("com.docker.compose.service", ""),
            "working_dir": labels.get("com.docker.compose.project.working_dir", ""),
            "mounts": r.get("Mounts", ""), "networks": r.get("Networks", ""),
        })
    return out


def stats() -> dict[str, dict[str, str]]:
    """CPU and memory per running container (one sample, no streaming)."""
    require()
    rows = _lines(run(["stats", "--no-stream", "--format", "{{json .}}"], timeout=20).stdout)
    return {r.get("Name", ""): {"cpu": r.get("CPUPerc", ""), "memory": r.get("MemUsage", ""), "mem_pct": r.get("MemPerc", ""),
                                "net": r.get("NetIO", ""), "block": r.get("BlockIO", "")} for r in rows}


def images() -> list[dict[str, Any]]:
    require()
    rows = _lines(run(["image", "ls", "--all", "--format", "{{json .}}"]).stdout)
    used = {c["image"] for c in containers()}
    out = []
    for r in rows:
        ref = f"{r.get('Repository')}:{r.get('Tag')}"
        out.append({"id": r.get("ID", ""), "repository": r.get("Repository", ""), "tag": r.get("Tag", ""),
                    "size": r.get("Size", ""), "created": r.get("CreatedSince", ""),
                    "dangling": r.get("Repository") == "<none>",
                    "in_use": ref in used or r.get("Repository") in used or r.get("ID", "") in used})
    return out


def volumes() -> list[dict[str, Any]]:
    require()
    rows = _lines(run(["volume", "ls", "--format", "{{json .}}"]).stdout)
    users: dict[str, list[str]] = {}
    for c in containers():
        for mount in (c["mounts"] or "").split(","):
            if mount:
                users.setdefault(mount.strip(), []).append(c["name"])
    return [{"name": r.get("Name", ""), "driver": r.get("Driver", ""), "mountpoint": r.get("Mountpoint", ""),
             "labels": _labels(r.get("Labels", "")).get("com.docker.compose.project", ""),
             "containers": users.get(r.get("Name", ""), [])} for r in rows]


def networks() -> list[dict[str, Any]]:
    require()
    rows = _lines(run(["network", "ls", "--format", "{{json .}}"]).stdout)
    attached: dict[str, list[str]] = {}
    for c in containers():
        for net in (c["networks"] or "").split(","):
            if net:
                attached.setdefault(net.strip(), []).append(c["name"])
    return [{"id": r.get("ID", ""), "name": r.get("Name", ""), "driver": r.get("Driver", ""), "scope": r.get("Scope", ""),
             "builtin": r.get("Name") in ("bridge", "host", "none"), "containers": attached.get(r.get("Name", ""), [])}
            for r in rows]


def compose_projects() -> list[dict[str, Any]]:
    """Every Compose project the engine knows, started by STACKLOOM or not."""
    require()
    rows = _lines(run(["compose", "ls", "--all", "--format", "json"]).stdout)
    by_project: dict[str, list[dict[str, Any]]] = {}
    for c in containers():
        if c["compose_project"]:
            by_project.setdefault(c["compose_project"], []).append(c)
    out = []
    for r in rows:
        name = r.get("Name", "")
        members = by_project.get(name, [])
        out.append({"name": name, "status": r.get("Status", ""), "config_files": r.get("ConfigFiles", "").split(","),
                    "working_dir": next((m["working_dir"] for m in members if m["working_dir"]), ""),
                    "services": sorted({m["compose_service"] for m in members}),
                    "containers": [{"name": m["name"], "service": m["compose_service"], "state": m["state"],
                                    "health": m["health"], "ports": m["ports"]} for m in members]})
    return out


def overview() -> dict[str, Any]:
    state = info()
    if not state["available"]:
        return {"engine": state}
    cs = containers()
    return {"engine": state, "containers": len(cs), "running": sum(c["state"] == "running" for c in cs),
            "stopped": sum(c["state"] in ("exited", "created", "dead") for c in cs),
            "paused": sum(c["state"] == "paused" for c in cs), "unhealthy": sum(c["health"] == "unhealthy" for c in cs),
            "images": len(_lines(run(["image", "ls", "--format", "{{json .}}"]).stdout)),
            "volumes": len(_lines(run(["volume", "ls", "--format", "{{json .}}"]).stdout)),
            "networks": len(_lines(run(["network", "ls", "--format", "{{json .}}"]).stdout)),
            "compose_projects": len(_lines(run(["compose", "ls", "--all", "--format", "json"]).stdout))}


def for_project(project_path: str) -> list[dict[str, Any]]:
    root = str(Path(project_path).resolve())
    return [c for c in containers() if c["working_dir"] and (c["working_dir"] == root or c["working_dir"].startswith(root + "/"))]


# --------------------------------------------------------------------------- containers

CONTAINER_ACTIONS = {"start", "stop", "restart", "pause", "unpause"}


def container_action(name: str, action: str) -> str:
    require()
    if action not in CONTAINER_ACTIONS:
        raise DockerError(f"Unknown action {action!r}.")
    run([action, _check(name, "container")], timeout=120)
    return f"{action} {name}: done"


def remove_container(name: str, confirm: bool) -> str:
    """Removes the container only. Its volumes stay (no -v)."""
    require()
    if not confirm:
        raise DockerError("Removing a container needs confirmation. Its volumes are kept either way.")
    run(["rm", _check(name, "container")], timeout=60)
    return f"Removed {name}. Its volumes were kept."


def inspect_container(name: str) -> dict[str, Any]:
    require()
    data = json.loads(run(["inspect", _check(name, "container")]).stdout)[0]
    config = data.get("Config", {})
    env = []
    for item in config.get("Env") or []:
        key, _, value = item.partition("=")
        env.append({"key": key, "value": "••••••" if is_secret_name(key) or "://" in value and "@" in value else value})
    return {
        "id": data.get("Id", "")[:12], "name": data.get("Name", "").lstrip("/"), "image": config.get("Image"),
        "created": data.get("Created"), "state": data.get("State", {}), "restart_policy": data.get("HostConfig", {}).get("RestartPolicy"),
        "command": redact(" ".join((config.get("Entrypoint") or []) + (config.get("Cmd") or []))),
        "env": env, "ports": data.get("NetworkSettings", {}).get("Ports"),
        "mounts": [{"type": m.get("Type"), "name": m.get("Name"), "source": m.get("Source"), "destination": m.get("Destination"),
                    "rw": m.get("RW")} for m in data.get("Mounts", [])],
        "networks": list((data.get("NetworkSettings", {}).get("Networks") or {}).keys()),
        "labels": {k: v for k, v in (config.get("Labels") or {}).items() if k.startswith("com.docker.compose")},
        "health": (data.get("State", {}).get("Health") or {}).get("Status"),
    }


def container_logs(name: str, lines: int = 300) -> str:
    require()
    result = run(["logs", "--tail", str(max(1, min(lines, 5000))), "--timestamps", _check(name, "container")], check=False)
    return redact((result.stdout + result.stderr).strip()) or "No log lines."


def exec_command(name: str, command: list[str], confirm: bool, timeout: float = 60) -> dict[str, Any]:
    """Run one command inside a container (no shell, no TTY). Audited by the caller."""
    require()
    if not confirm:
        raise DockerError("Running a command inside a container needs confirmation.")
    if not command or not all(isinstance(a, str) for a in command):
        raise DockerError("Give the command as a list of arguments.")
    started = time.monotonic()
    result = run(["exec", _check(name, "container"), *command], timeout=timeout, check=False)
    return {"exit_code": result.returncode, "output": redact((result.stdout + result.stderr)[-50_000:]),
            "seconds": round(time.monotonic() - started, 2)}


# --------------------------------------------------------------------------- images, volumes, networks

def pull_image(ref: str) -> str:
    require()
    run(["pull", _check(ref, "image")], timeout=1800)
    return f"Pulled {ref}."


def tag_image(source: str, target: str) -> str:
    require()
    run(["tag", _check(source, "image"), _check(target, "tag")])
    return f"Tagged {source} as {target}."


def remove_image(ref: str, confirm: bool) -> str:
    require()
    if not confirm:
        raise DockerError("Removing an image needs confirmation.")
    if any(i["in_use"] and (ref in (i["id"], f"{i['repository']}:{i['tag']}")) for i in images()):
        raise DockerError(f"{ref} is used by a container. Remove the container first.")
    run(["image", "rm", _check(ref, "image")])
    return f"Removed image {ref}."


def prune_dangling(confirm: bool) -> str:
    require()
    if not confirm:
        raise DockerError("Removing dangling images needs confirmation.")
    out = run(["image", "prune", "--force"], timeout=600).stdout.strip()
    return out.splitlines()[-1] if out else "Nothing to remove."


def image_history(ref: str) -> list[dict[str, Any]]:
    require()
    return [{"created_by": redact(r.get("CreatedBy", ""))[:300], "size": r.get("Size", ""), "created": r.get("CreatedSince", "")}
            for r in _lines(run(["history", "--no-trunc", "--format", "{{json .}}", _check(ref, "image")]).stdout)]


def build_image(context: str, tag: str) -> str:
    require()
    ctx = Path(context).resolve()
    if not (ctx / "Dockerfile").exists():
        raise DockerError(f"No Dockerfile in {ctx}.")
    out = run(["build", "-t", _check(tag, "tag"), str(ctx)], timeout=3600)
    return redact((out.stdout + out.stderr)[-20_000:])


def create_volume(name: str) -> str:
    require()
    run(["volume", "create", _check(name, "volume")])
    return f"Created volume {name}."


def remove_volume(name: str, confirm: bool) -> str:
    require()
    vol = next((v for v in volumes() if v["name"] == name), None)
    if vol is None:
        raise DockerError(f"No volume named {name}.")
    if vol["containers"]:
        raise DockerError(f"{name} is attached to {', '.join(vol['containers'])}. Remove those containers first.")
    if not confirm:
        raise DockerError(f"Removing {name} deletes its data permanently. Confirm to continue.")
    run(["volume", "rm", _check(name, "volume")])
    return f"Removed volume {name}."


def backup_volume(name: str) -> Path:
    """Copy a volume's files into ~/.stackloom/backups/volumes/<name>-<time>.tar.gz using a busybox container."""
    require()
    out_dir = paths.home() / "backups" / "volumes"
    out_dir.mkdir(parents=True, exist_ok=True)
    from stackloom.backups import stamp, unique

    archive = unique(out_dir / f"{_check(name, 'volume')}-{stamp()}.tar.gz").name
    run(["run", "--rm", "-v", f"{name}:/volume:ro", "-v", f"{out_dir}:/backup", "busybox:1.36",
         "tar", "czf", f"/backup/{archive}", "-C", "/volume", "."], timeout=3600)
    return out_dir / archive


def restore_volume(name: str, archive: Path, confirm: bool) -> str:
    require()
    if not confirm:
        raise DockerError(f"Restoring replaces the files in {name}. Confirm to continue.")
    archive = archive.resolve()
    backups = (paths.home() / "backups" / "volumes").resolve()
    if backups not in archive.parents or not archive.exists():
        raise DockerError("Pick a backup made by STACKLOOM.")
    run(["run", "--rm", "-v", f"{_check(name, 'volume')}:/volume", "-v", f"{backups}:/backup:ro", "busybox:1.36",
         "sh", "-c", f"cd /volume && tar xzf /backup/{archive.name}"], timeout=3600)
    return f"Restored {name} from {archive.name}."


def create_network(name: str) -> str:
    require()
    run(["network", "create", _check(name, "network")])
    return f"Created network {name}."


def remove_network(name: str, confirm: bool) -> str:
    require()
    net = next((n for n in networks() if n["name"] == name), None)
    if net is None:
        raise DockerError(f"No network named {name}.")
    if net["builtin"]:
        raise DockerError(f"{name} is a built-in network.")
    if net["containers"]:
        raise DockerError(f"{name} still has containers: {', '.join(net['containers'])}.")
    if not confirm:
        raise DockerError("Removing a network needs confirmation.")
    run(["network", "rm", name])
    return f"Removed network {name}."


def network_connect(network: str, container: str, connect: bool) -> str:
    require()
    run(["network", "connect" if connect else "disconnect", _check(network, "network"), _check(container, "container")])
    return f"{'Connected' if connect else 'Disconnected'} {container} {'to' if connect else 'from'} {network}."


# --------------------------------------------------------------------------- compose

COMPOSE_ACTIONS = {"up", "down", "start", "stop", "restart", "build", "pull", "ps", "config", "logs"}


def compose(project_name: str, action: str, *, working_dir: str = "", config_files: list[str] | None = None,
            service: str | None = None, remove_volumes: bool = False, confirm: bool = False,
            confirm_volumes: bool = False) -> str:
    """Run a Compose command for a project the engine knows (or one with its files given).

    `down` removes the project's containers and networks and needs confirm;
    with remove_volumes it also deletes its volumes and needs confirm too.
    """
    require()
    if action not in COMPOSE_ACTIONS:
        raise DockerError(f"Unknown Compose action {action!r}.")
    args = ["compose", "-p", _check(project_name, "Compose project")]
    for f in config_files or []:
        if f:
            args += ["-f", f]
    if action == "up":
        args += ["up", "--detach"]
    elif action == "down":
        if not confirm:
            raise DockerError("`down` removes the project's containers and networks. Confirm to continue; volumes are kept.")
        if remove_volumes and not confirm_volumes:
            raise DockerError("Deleting the project's volumes destroys their data. Confirm that separately to continue.")
        args += ["down"] + (["--volumes"] if remove_volumes else [])
    elif action == "logs":
        args += ["logs", "--no-color", "--tail", "300"]
    elif action == "ps":
        args += ["ps", "--all"]
    elif action == "config":
        args += ["config"]
    else:
        args += [action]
    if service:
        args.append(_check(service, "service"))
    timeout = 3600 if action in ("up", "build", "pull") else 300
    result = run(args, timeout=timeout, cwd=working_dir or None)
    return redact((result.stdout + result.stderr).strip()[-40_000:]) or "Done."
