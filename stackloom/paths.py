"""Where STACKLOOM keeps its own data. Never inside the package or a managed project."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def home() -> Path:
    override = os.environ.get("STACKLOOM_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "stackloom"
    return Path.home() / ".stackloom"


def ensure(base: Path | None = None) -> Path:
    base = base or home()
    for sub in ("logs", "state", "state/compose", "backups"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    try:
        base.chmod(0o700)
    except OSError:
        pass
    return base


def db_path(base: Path | None = None) -> Path:
    return (base or home()) / "stackloom.db"


def config_path(base: Path | None = None) -> Path:
    return (base or home()) / "config.toml"


def server_state(base: Path | None = None) -> Path:
    return (base or home()) / "state" / "server.json"


def log_dir(base: Path | None = None) -> Path:
    return (base or home()) / "logs"
