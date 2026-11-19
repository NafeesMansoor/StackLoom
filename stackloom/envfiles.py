"""Environment and configuration files of a project.

Shows key names, whether each is set, and values only for keys that do not
look secret. Comparing two files compares values by hash, so secrets are
never shown. Every edit backs the file up first."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from stackloom import paths
from stackloom.security import LOOKS_LIKE_CREDENTIAL, is_secret_name

ENV_GLOBS = (".env", ".env.*", "*.env")
CONFIG_NAMES = ("config.json", "config.yaml", "config.yml", "settings.json", "appsettings.json", "config.toml",
                "docker-compose.yml", "compose.yaml", "pyproject.toml", "package.json", "codecortex.yaml")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


class EnvError(RuntimeError):
    pass


def _inside(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if root.resolve() not in path.parents:
        raise EnvError("That file is outside the project.")
    return path


def files(project_path: str) -> list[dict[str, Any]]:
    root = Path(project_path)
    found: dict[str, dict[str, Any]] = {}
    for base in [root, *[d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name not in
                        ("node_modules", ".venv", "venv", "vendor", "dist", "build")]] if root.is_dir() else []:
        for pattern in ENV_GLOBS:
            for f in base.glob(pattern):
                if f.is_file():
                    found[str(f)] = {"path": str(f.relative_to(root)), "type": "env", "example": f.name.endswith(
                        (".example", ".sample", ".template", ".dist"))}
        for name in CONFIG_NAMES:
            f = base / name
            if f.is_file() and base == root:
                found[str(f)] = {"path": name, "type": f.suffix.lstrip(".") or "config", "example": False}
    return sorted(found.values(), key=lambda x: (x["type"] != "env", x["path"]))


def _parse(path: Path) -> list[tuple[str, str]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out.append((key.strip(), value))
    return out


def secret(key: str, value: str) -> bool:
    return is_secret_name(key) or bool(LOOKS_LIKE_CREDENTIAL.search(value)) or len(value) >= 32 and " " not in value


def read(project_path: str, rel: str) -> dict[str, Any]:
    path = _inside(Path(project_path), rel)
    if not path.is_file():
        raise EnvError(f"No file {rel}.")
    if not (path.name.startswith(".env") or path.name.endswith(".env")):
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {"path": rel, "type": "json", "keys": [{"key": k, "set": v not in (None, ""), "secret": secret(k, str(v)),
                        "value": None if secret(k, str(v)) or isinstance(v, (dict, list)) else v}
                        for k, v in (data.items() if isinstance(data, dict) else [])]}
            except ValueError:
                pass
        return {"path": rel, "type": path.suffix.lstrip("."), "keys": [], "note": "Shown by name only; open it in your editor."}
    keys = []
    for key, value in _parse(path):
        hidden = secret(key, value)
        keys.append({"key": key, "set": value != "", "secret": hidden, "value": None if hidden else value})
    return {"path": rel, "type": "env", "keys": keys}


def compare(project_path: str, a: str, b: str) -> dict[str, Any]:
    pa, pb = _inside(Path(project_path), a), _inside(Path(project_path), b)
    va, vb = dict(_parse(pa)), dict(_parse(pb))
    h = lambda v: hashlib.sha256(v.encode()).hexdigest()  # noqa: E731
    return {"only_in_a": sorted(set(va) - set(vb)), "only_in_b": sorted(set(vb) - set(va)),
            "different": sorted(k for k in set(va) & set(vb) if h(va[k]) != h(vb[k])),
            "same": sorted(k for k in set(va) & set(vb) if h(va[k]) == h(vb[k]))}


def missing(project_path: str) -> list[dict[str, Any]]:
    """Keys an example file declares that the real env file lacks or leaves empty."""
    root = Path(project_path)
    out = []
    for f in files(project_path):
        if f["type"] != "env" or not f["example"]:
            continue
        example = _inside(root, f["path"])
        real = example.with_name(re.sub(r"\.(example|sample|template|dist)$", "", example.name))
        if not real.exists():
            out.append({"file": str(real.relative_to(root)), "missing_file": True, "keys": [k for k, _ in _parse(example)]})
            continue
        have = dict(_parse(real))
        gaps = [k for k, _ in _parse(example) if not have.get(k)]
        if gaps:
            out.append({"file": str(real.relative_to(root)), "missing_file": False, "keys": gaps})
    return out


def backup_file(path: Path) -> Path:
    target_dir = paths.home() / "backups" / "config"
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(path).strip("/"))
    from stackloom.backups import stamp, unique

    target = unique(target_dir / f"{safe}.{stamp()}")
    shutil.copy2(path, target)
    target.chmod(0o600)
    return target


def set_value(project_path: str, rel: str, key: str, value: str, confirm: bool) -> dict[str, Any]:
    """Set or add KEY=value in an env file, keeping comments and order. Backs up first."""
    if not confirm:
        raise EnvError("Editing a configuration file needs confirmation. A backup is made first.")
    if not KEY_RE.match(key):
        raise EnvError("Keys use letters, digits and underscores.")
    if "\n" in value:
        raise EnvError("Values must be on one line.")
    path = _inside(Path(project_path), rel)
    if not (path.name.startswith(".env") or path.name.endswith(".env")):
        raise EnvError("Only env files can be edited here.")
    backup = backup_file(path) if path.exists() else None
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    rendered = f'{key}="{value}"' if re.search(r"[\s#'\"]", value) else f"{key}={value}"
    for i, line in enumerate(lines):
        if re.match(rf"^\s*(export\s+)?{re.escape(key)}\s*=", line):
            lines[i] = rendered
            break
    else:
        lines.append(rendered)
    tmp = path.with_name(path.name + ".stackloom-tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if path.exists():
        shutil.copymode(path, tmp)
    tmp.replace(path)
    return {"backup": str(backup) if backup else None}
