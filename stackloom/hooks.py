"""The Claude Code SessionStart hook that tells STACKLOOM a project was opened.

`stackloom agent hook install` adds one entry to ~/.claude/settings.json:

    SessionStart → "<stackloom> agent open --hook"

Claude Code passes the session's working folder on stdin. STACKLOOM queues an
incremental CodeCortex refresh in a background process and returns at once,
so the session never waits. A backup of settings.json is written first, and
uninstall removes only this entry.
"""
from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path

MARK = "agent open --hook"


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _command(executable: Path | None) -> str:
    if executable:
        return f"{shlex.quote(str(executable))} {MARK}"
    return f"{shlex.quote(sys.executable)} -m stackloom {MARK}"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if text.strip() else {}


def _ours(entry: dict) -> bool:
    return any(MARK in (h.get("command") or "") for h in entry.get("hooks", []))


def installed(path: Path | None = None) -> bool:
    try:
        data = _load(path or settings_path())
    except (OSError, ValueError):
        return False
    return any(_ours(e) for e in data.get("hooks", {}).get("SessionStart", []))


def install(executable: Path | None = None, path: Path | None = None) -> str:
    path = path or settings_path()
    data = _load(path)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".stackloom-backup"))
    session = [e for e in data.setdefault("hooks", {}).setdefault("SessionStart", []) if not _ours(e)]
    session.append({"hooks": [{"type": "command", "command": _command(executable), "timeout": 10}]})
    data["hooks"]["SessionStart"] = session
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return (f"Added the SessionStart hook to {path} (backup: {path.name}.stackloom-backup).\n"
            "New Claude Code sessions now queue a CodeCortex refresh for the project they open.")


def uninstall(path: Path | None = None) -> str:
    path = path or settings_path()
    data = _load(path)
    session = data.get("hooks", {}).get("SessionStart", [])
    kept = [e for e in session if not _ours(e)]
    if len(kept) == len(session):
        return "The STACKLOOM hook was not installed."
    shutil.copy2(path, path.with_name(path.name + ".stackloom-backup"))
    if kept:
        data["hooks"]["SessionStart"] = kept
    else:
        data["hooks"].pop("SessionStart")
        if not data["hooks"]:
            data.pop("hooks")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f"Removed the STACKLOOM hook from {path}."


def show() -> str:
    state = "installed" if installed() else "not installed"
    return (f"Claude Code SessionStart hook: {state} ({settings_path()}).\n"
            f"Command: {_command(None)}\n"
            "Install with `stackloom agent hook install`; remove with `stackloom agent hook uninstall`.")
