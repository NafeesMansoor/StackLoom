"""Workspace discovery.

Walks the configured workspace folders and returns candidate projects. A
folder with a code marker becomes one project; folders with markers inside it
become its components (frontend/, backend/ ...), not separate projects, unless
they hold their own Git repository. Runs only when asked, never in the background.
Reads files; writes nothing in the workspace.
"""
from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any, Iterable

MARKERS = (
    ".git", "package.json", "pnpm-workspace.yaml", "yarn.lock", "pyproject.toml", "requirements.txt",
    "Pipfile", "setup.py", "Cargo.toml", "go.mod", "composer.json", "Gemfile", "pom.xml", "build.gradle",
    "build.gradle.kts", "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml",
    "compose.yml", ".devcontainer", "index.html", "Makefile", "deno.json", "CLAUDE.md",
)
# A folder whose only markers are among these and that holds code folders is a
# container (a workspace or umbrella folder), not a project.
WEAK_MARKERS = {"CLAUDE.md", "Makefile", "index.html"}
SKIP_DIRS = {
    "node_modules", ".venv", "venv", "env", "vendor", "dist", "build", "out", "target", "__pycache__",
    ".git", ".next", ".nuxt", ".svelte-kit", ".turbo", ".cache", ".codecortex", "backups", "coverage",
    "site-packages", "Pods", "DerivedData",
}
COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _python_deps(path: Path) -> str:
    text = ""
    for name in ("requirements.txt", "Pipfile", "setup.py"):
        text += _read_text(path / name).lower()
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(_read_text(pyproject))
            project = data.get("project", {})
            text += " ".join(project.get("dependencies", [])).lower()
            for extra in project.get("optional-dependencies", {}).values():
                text += " " + " ".join(extra).lower()
            text += " ".join(data.get("tool", {}).get("poetry", {}).get("dependencies", {})).lower()
        except (tomllib.TOMLDecodeError, AttributeError):
            text += _read_text(pyproject).lower()
    return text


def detect_stack(path: Path) -> list[str]:
    """Technologies used directly in this folder, most specific first."""
    stack: list[str] = []
    pkg = _read_json(path / "package.json") if (path / "package.json").exists() else {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for dep, label in (("next", "Next.js"), ("nuxt", "Nuxt"), ("@angular/core", "Angular"), ("@sveltejs/kit", "SvelteKit"),
                       ("vue", "Vue"), ("react", "React"), ("vite", "Vite"), ("express", "Express"),
                       ("@nestjs/core", "NestJS"), ("electron", "Electron"), ("typescript", "TypeScript")):
        if dep in deps:
            stack.append(label)
    if pkg:
        stack.append("Node.js")
    py = _python_deps(path)
    if py or (path / "pyproject.toml").exists():
        for dep, label in (("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask"), ("streamlit", "Streamlit")):
            if re.search(rf"(^|[^a-z]){dep}([^a-z]|$)", py):
                stack.append(label)
        stack.append("Python")
    if (path / "composer.json").exists():
        composer = _read_json(path / "composer.json")
        if "laravel/framework" in composer.get("require", {}) or (path / "artisan").exists():
            stack.append("Laravel")
        stack.append("PHP")
    if (path / "go.mod").exists():
        stack.append("Go")
    if (path / "Cargo.toml").exists():
        stack.append("Rust")
    if (path / "Gemfile").exists():
        stack.append("Rails" if "rails" in _read_text(path / "Gemfile") else "Ruby")
    if any((path / f).exists() for f in ("pom.xml", "build.gradle", "build.gradle.kts")):
        stack.append("Java")
    if any((path / f).exists() for f in COMPOSE_FILES):
        stack.append("Docker Compose")
    elif (path / "Dockerfile").exists():
        stack.append("Docker")
    if not stack and (path / "index.html").exists():
        stack.append("Static site")
    return list(dict.fromkeys(stack))


def is_monorepo(path: Path) -> bool:
    if (path / "pnpm-workspace.yaml").exists() or (path / "lerna.json").exists() or (path / "turbo.json").exists():
        return True
    pkg = _read_json(path / "package.json") if (path / "package.json").exists() else {}
    if pkg.get("workspaces"):
        return True
    return "[workspace]" in _read_text(path / "Cargo.toml") or (path / "go.work").exists()


def has_marker(path: Path) -> bool:
    return any((path / m).exists() for m in MARKERS)


def _children(directory: Path) -> list[Path]:
    try:
        return sorted(c for c in directory.iterdir()
                      if c.is_dir() and not c.is_symlink() and not c.name.startswith(".") and c.name not in SKIP_DIRS)
    except OSError:
        return []


def classify(path: Path, stack: list[str], components: list[dict[str, Any]]) -> str:
    all_stack = set(stack) | {s for c in components for s in c["stack"]}
    if all_stack & {"Next.js", "Nuxt", "Vite", "Angular", "SvelteKit", "FastAPI", "Django", "Flask", "Laravel",
                    "Rails", "Express", "NestJS", "Docker Compose", "Static site", "Streamlit"}:
        return "service"
    pkg = _read_json(path / "package.json") if (path / "package.json").exists() else {}
    if pkg.get("bin") or "[project.scripts]" in _read_text(path / "pyproject.toml"):
        return "cli"
    if all_stack:
        return "library"
    return "docs" if (path / "README.md").exists() or (path / "CLAUDE.md").exists() else "workspace"


def suggest_launch(path: Path, stack: list[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """An inferred start command (argv, loopback, ${PORT:...}). Never enabled automatically."""
    web = [{"name": "web", "url": "http://localhost:${PORT:web}",
            "health": {"type": "http", "url": "http://127.0.0.1:${PORT:web}"}}]
    venv = next((v for v in (".venv", "venv") if (path / v / "bin" / "python").exists()), None)
    if "Next.js" in stack:
        return {"type": "process", "command": ["./node_modules/.bin/next", "dev", "-H", "127.0.0.1", "-p", "${PORT:web}"]}, web
    if "Vite" in stack:
        return {"type": "process", "command": ["./node_modules/.bin/vite", "--host", "127.0.0.1", "--port", "${PORT:web}", "--strictPort"]}, web
    if "Laravel" in stack:
        return {"type": "process", "command": ["php", "artisan", "serve", "--host=127.0.0.1", "--port=${PORT:web}"]}, web
    if "Django" in stack and (path / "manage.py").exists():
        py = f"{venv}/bin/python" if venv else "python3"
        return {"type": "process", "command": [py, "manage.py", "runserver", "127.0.0.1:${PORT:web}"]}, web
    if "FastAPI" in stack and venv:
        for module in ("app.main", "main", "src.main", "api.main"):
            if (path / (module.replace(".", "/") + ".py")).exists():
                api = [{"name": "api", "url": "http://localhost:${PORT:api}/docs",
                        "health": {"type": "http", "url": "http://127.0.0.1:${PORT:api}/docs"}}]
                return {"type": "process", "command": [f"{venv}/bin/uvicorn", f"{module}:app", "--host", "127.0.0.1",
                                                       "--port", "${PORT:api}"]}, api
    if "Static site" in stack:
        return {"type": "process", "command": ["python3", "-m", "http.server", "${PORT:web}", "--bind", "127.0.0.1"]}, web
    return None, []


def describe(path: Path, workspace: Path) -> dict[str, Any]:
    stack = detect_stack(path)
    components: list[dict[str, Any]] = []
    nested_repos: list[str] = []

    def inner(directory: Path, depth: int) -> None:
        for child in _children(directory):
            if (child / ".git").exists():
                nested_repos.append(str(child))
                continue
            if has_marker(child):
                components.append({"name": child.relative_to(path).as_posix(), "stack": detect_stack(child)})
            if depth < 2:
                inner(child, depth + 1)

    inner(path, 1)
    rel = path.relative_to(workspace)
    group = rel.parts[0].lower() if len(rel.parts) > 1 else "inbox"
    launch, services = suggest_launch(path, stack)
    compose = [f for f in COMPOSE_FILES if (path / f).exists()]
    readme = next((n for n in ("README.md", "readme.md", "CLAUDE.md", "Claude.md") if (path / n).exists()), None)
    entry: dict[str, Any] = {
        "name": path.name,
        "path": str(path),
        "group": re.sub(r"[^a-z0-9]+", "-", group).strip("-") or "inbox",
        "kind": classify(path, stack, components),
        "stack": stack,
        "monorepo": is_monorepo(path),
        "components": components,
        "nested_repos": nested_repos,
        "git": (path / ".git").exists(),
        "compose_files": compose,
        "env_files": sorted(p.name for p in path.glob(".env*") if p.is_file()),
        "markers": [m for m in MARKERS if (path / m).exists()],
    }
    if readme:
        entry["docs"] = [str(path / readme)]
    if launch:
        entry["launch"] = launch
        entry["services"] = services
        entry["safe_to_launch"] = False
    return entry


def scan(workspaces: Iterable[str | Path], registered: Iterable[str | Path] = (), depth: int = 5) -> list[dict[str, Any]]:
    """Unregistered projects under the workspace folders.

    A registered project's folder is not entered (its sub-repositories are
    reported on its own page). Independent Git repositories nested inside an
    unregistered project are returned as projects of their own.
    """
    known = {Path(p).resolve() for p in registered}
    found: list[dict[str, Any]] = []

    for ws in workspaces:
        workspace = Path(ws).expanduser().resolve()
        if not workspace.is_dir():
            continue

        def walk(directory: Path, level: int) -> None:
            for child in _children(directory):
                if child in known:
                    continue
                if has_marker(child) and not _is_container(child, known) and not _is_umbrella(child):
                    entry = describe(child, workspace)
                    found.append(entry)
                    for repo in entry["nested_repos"]:
                        if Path(repo) not in known:
                            found.append({**describe(Path(repo), workspace), "parent": str(child)})
                elif level < depth:
                    walk(child, level + 1)

        walk(workspace, 1)
    return found


def _is_umbrella(path: Path) -> bool:
    if any((path / m).exists() for m in MARKERS if m not in WEAK_MARKERS):
        return False
    return any(has_marker(c) for c in _children(path))


def _is_container(path: Path, known: set[Path]) -> bool:
    """A folder that holds registered projects is a workspace folder, not a project."""
    return any(path in k.parents for k in known)


def looks_indexable(path: Path, known_projects: Iterable[str | Path] = ()) -> str | None:
    """Why a folder should not get a CodeCortex map, or None if it may.

    Guards `stackloom agent open`: Claude Code can be opened anywhere, and
    indexing a home folder or a whole workspace would be slow and useless.
    """
    path = path.resolve()
    if path == Path.home().resolve() or path == Path(path.anchor):
        return "this is the home or root folder"
    if not path.is_dir():
        return "the folder does not exist"
    if not has_marker(path):
        return "the folder has no code markers"
    if _is_container(path, {Path(p).resolve() for p in known_projects}) or _is_umbrella(path):
        return "the folder holds other projects (a workspace, not a project)"
    count = 0
    for _root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        count += len(files)
        if count > 50_000:
            return "the folder holds more than 50,000 files"
    return None


def dependencies(path: Path) -> dict[str, list[dict[str, str]]]:
    """Declared dependencies by manifest (names and version ranges as written). Read-only."""
    out: dict[str, list[dict[str, str]]] = {}
    pkg = _read_json(path / "package.json") if (path / "package.json").exists() else {}
    for section in ("dependencies", "devDependencies"):
        items = pkg.get(section) or {}
        if items:
            out[f"package.json {section}"] = [{"name": k, "version": str(v)} for k, v in sorted(items.items())]
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(_read_text(pyproject))
            deps = data.get("project", {}).get("dependencies", [])
            if deps:
                out["pyproject.toml"] = [_split_req(d) for d in deps]
            for extra, items in (data.get("project", {}).get("optional-dependencies") or {}).items():
                out[f"pyproject.toml [{extra}]"] = [_split_req(d) for d in items]
        except tomllib.TOMLDecodeError:
            pass
    req = path / "requirements.txt"
    if req.exists():
        lines = [l.split("#")[0].strip() for l in _read_text(req).splitlines()]
        items = [_split_req(l) for l in lines if l and not l.startswith(("-", "git+", "http"))]
        if items:
            out["requirements.txt"] = items
    composer = _read_json(path / "composer.json") if (path / "composer.json").exists() else {}
    if composer.get("require"):
        out["composer.json"] = [{"name": k, "version": str(v)} for k, v in sorted(composer["require"].items())]
    gomod = _read_text(path / "go.mod")
    if gomod:
        items = re.findall(r"^\s*([\w.\-/]+\.[\w.\-/]+)\s+(v[\w.\-+]+)", gomod, re.M)
        if items:
            out["go.mod"] = [{"name": n, "version": v} for n, v in items]
    cargo = path / "Cargo.toml"
    if cargo.exists():
        try:
            deps = tomllib.loads(_read_text(cargo)).get("dependencies", {})
            if deps:
                out["Cargo.toml"] = [{"name": k, "version": v if isinstance(v, str) else str(v.get("version", ""))} for k, v in deps.items()]
        except tomllib.TOMLDecodeError:
            pass
    return out


def _split_req(spec: str) -> dict[str, str]:
    match = re.match(r"^\s*([A-Za-z0-9_.\-\[\],]+)\s*(.*)$", spec)
    return {"name": match.group(1), "version": match.group(2).strip()} if match else {"name": spec, "version": ""}
