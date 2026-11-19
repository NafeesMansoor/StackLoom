"""Run the dashboard once, find it again, stop it.

`stackloom` reuses a running dashboard (same PID and kernel start time, and
/api/health answers) instead of starting a second one.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from stackloom import paths, procs
from stackloom.config import Config

HOST = "127.0.0.1"


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # Same option uvicorn binds with, so a port in TIME_WAIT after a restart
        # still counts as free and the dashboard keeps its address.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    try:
        with socket.create_connection((HOST, port), timeout=0.2):
            return False
    except OSError:
        return True


def choose_port(cfg: Config, requested: int | None, taken: set[int]) -> int:
    if requested:
        return requested
    env = os.environ.get("STACKLOOM_PORT")
    if env:
        return int(env)
    if cfg.dashboard_port and port_free(cfg.dashboard_port):
        return cfg.dashboard_port
    # Top of the pool, so app ports (allocated from the bottom) rarely meet it.
    for port in range(cfg.port_pool[1], cfg.port_pool[0] - 1, -1):
        if port not in taken and port_free(port):
            return port
    raise RuntimeError(f"No free port in {cfg.port_pool[0]}–{cfg.port_pool[1]}. Pass --port.")


def _healthy(port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=timeout) as response:
            return json.load(response).get("app") == "stackloom"
    except (OSError, ValueError):
        return False


def running(base: Path | None = None) -> dict | None:
    """The live dashboard's record, or None. Clears a stale record."""
    state_file = paths.server_state(base)
    if not state_file.exists():
        return None
    try:
        state = json.loads(state_file.read_text())
    except ValueError:
        state_file.unlink(missing_ok=True)
        return None
    if procs.alive(state.get("pid"), state.get("pid_start")) and _healthy(state["port"]):
        state["url"] = f"http://{HOST}:{state['port']}/"
        return state
    if not procs.alive(state.get("pid"), state.get("pid_start")):
        state_file.unlink(missing_ok=True)
    return None


def write_state(port: int, base: Path | None = None) -> None:
    path = paths.server_state(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": os.getpid(), "pid_start": procs.start_time(os.getpid()), "port": port}))


def clear_state(base: Path | None = None) -> None:
    path = paths.server_state(base)
    try:
        if json.loads(path.read_text()).get("pid") == os.getpid():
            path.unlink()
    except (OSError, ValueError):
        pass


def serve(port: int) -> None:
    """Foreground server (used by `stackloom serve` and by the background launcher)."""
    import uvicorn

    from stackloom.api.app import create_app

    write_state(port)
    try:
        uvicorn.run(create_app(), host=HOST, port=port, log_level="warning", access_log=False,
                    proxy_headers=False, server_header=False)
    finally:
        clear_state()


def start_background(port: int, wait: float = 15.0) -> dict:
    log = paths.log_dir() / "dashboard.log"
    with log.open("ab") as fh:
        subprocess.Popen([sys.executable, "-m", "stackloom.cli", "serve", "--port", str(port)],
                         stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        state = running()
        if state:
            return state
        time.sleep(0.15)
    raise RuntimeError(f"The dashboard did not start within {wait:.0f}s. See {log}")


def stop(base: Path | None = None, timeout: float = 10.0) -> bool:
    state = running(base)
    if not state:
        return False
    os.kill(state["pid"], signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not procs.alive(state["pid"], state["pid_start"]):
            return True
        time.sleep(0.1)
    if procs.alive(state["pid"], state["pid_start"]):
        os.kill(state["pid"], signal.SIGKILL)
    return True
