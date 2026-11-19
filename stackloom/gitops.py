"""Git for every registered repository. Reads are free; anything that changes
a repository or talks to its remote needs confirm=True and is audited by the caller.
Always runs `git -C <repo>` with the project's own repository path."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from stackloom.security import redact

REF_RE = re.compile(r"^(?!-)[A-Za-z0-9._/-]{1,200}$")


class GitError(RuntimeError):
    pass


def _env() -> dict[str, str]:
    # Keep SSH_AUTH_SOCK and credential helpers working; never block on a password prompt.
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


def repo_root(path: str | Path) -> Path | None:
    path = Path(path)
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def git(repo: Path, *args: str, timeout: float = 30, check: bool = True) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout,
                                check=False, env=_env())
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} did not finish within {timeout:.0f}s.")
    if check and result.returncode != 0:
        raise GitError(redact((result.stderr or result.stdout).strip() or f"git {args[0]} failed"))
    return result.stdout


def _ref(name: str) -> str:
    if not REF_RE.match(name or "") or ".." in name:
        raise GitError(f"Invalid branch or ref name: {name!r}")
    return name


def status(repo: Path) -> dict[str, Any]:
    out = git(repo, "status", "--porcelain=v2", "--branch", "--untracked-files=normal")
    info: dict[str, Any] = {"branch": None, "upstream": None, "ahead": 0, "behind": 0, "changed": [], "untracked": [],
                            "conflicts": []}
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            info["branch"] = line.split(" ", 2)[2]
        elif line.startswith("# branch.upstream "):
            info["upstream"] = line.split(" ", 2)[2]
        elif line.startswith("# branch.ab "):
            m = re.match(r"# branch.ab \+(\d+) -(\d+)", line)
            if m:
                info["ahead"], info["behind"] = int(m.group(1)), int(m.group(2))
        elif line.startswith(("1 ", "2 ")):
            parts = line.split(" ")
            path = line.split("\t")[-1] if line.startswith("2 ") else " ".join(parts[8:])
            info["changed"].append({"path": path.split("\t")[0], "xy": parts[1],
                                    "staged": parts[1][0] != ".", "unstaged": parts[1][1] != "."})
        elif line.startswith("u "):
            info["conflicts"].append(" ".join(line.split(" ")[10:]))
        elif line.startswith("? "):
            info["untracked"].append(line[2:])
    git_dir = Path(git(repo, "rev-parse", "--git-dir").strip())
    git_dir = git_dir if git_dir.is_absolute() else repo / git_dir
    info["operation"] = next((name for name, marker in (("merge", "MERGE_HEAD"), ("rebase", "rebase-merge"), ("rebase", "rebase-apply"),
                                                         ("cherry-pick", "CHERRY_PICK_HEAD")) if (git_dir / marker).exists()), None)
    info["remotes"] = remotes(repo)
    info["clean"] = not (info["changed"] or info["untracked"] or info["conflicts"])
    return info


def remotes(repo: Path) -> list[dict[str, str]]:
    seen = {}
    for line in git(repo, "remote", "-v").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            seen[parts[0]] = redact(parts[1])
    return [{"name": k, "url": v} for k, v in seen.items()]


def log(repo: Path, limit: int = 30) -> list[dict[str, str]]:
    try:
        out = git(repo, "log", f"-n{max(1, min(limit, 200))}", "--date=iso-strict", "--pretty=format:%H%x1f%h%x1f%an%x1f%ad%x1f%s")
    except GitError:
        return []
    return [dict(zip(("hash", "short", "author", "date", "subject"), line.split("\x1f"))) for line in out.splitlines() if line]


def branches(repo: Path) -> list[dict[str, Any]]:
    out = git(repo, "branch", "--all", "--format=%(HEAD)%1f%(refname)%1f%(objectname:short)%1f%(upstream:short)")
    result = []
    for parts in (line.split("\x1f") for line in out.splitlines()):
        if len(parts) != 4 or parts[1].endswith("/HEAD") or not parts[1].startswith("refs/"):
            continue  # skip origin/HEAD and detached-HEAD lines
        remote = parts[1].startswith("refs/remotes/")
        name = parts[1].removeprefix("refs/remotes/" if remote else "refs/heads/")
        result.append({"current": parts[0] == "*", "name": name, "remote": remote, "commit": parts[2], "upstream": parts[3]})
    return result


def stashes(repo: Path) -> list[dict[str, str]]:
    return [{"ref": l.split(":", 1)[0], "message": l.split(":", 1)[1].strip()} for l in git(repo, "stash", "list").splitlines() if ":" in l]


def diff(repo: Path, path: str | None = None, staged: bool = False, max_bytes: int = 200_000) -> str:
    args = ["diff", "--no-color"] + (["--cached"] if staged else [])
    if path:
        target = (repo / path).resolve()
        if repo.resolve() not in target.parents and target != repo.resolve():
            raise GitError("That path is outside the repository.")
        args += ["--", path]
    out = git(repo, *args)
    return redact(out[:max_bytes]) + ("\n[diff truncated]" if len(out) > max_bytes else "")


def _confirm(confirm: bool, what: str) -> None:
    if not confirm:
        raise GitError(f"{what} Confirm to continue.")


def fetch(repo: Path, confirm: bool) -> str:
    _confirm(confirm, "Fetching contacts the remote.")
    return git(repo, "fetch", "--prune", timeout=120) or "Fetched."


def pull(repo: Path, confirm: bool) -> str:
    _confirm(confirm, "Pulling changes the working tree (fast-forward only).")
    return git(repo, "pull", "--ff-only", timeout=180) or "Up to date."


def push(repo: Path, confirm: bool) -> str:
    _confirm(confirm, "Pushing publishes your commits to the remote.")
    result = subprocess.run(["git", "-C", str(repo), "push"], capture_output=True, text=True, timeout=180, check=False,
                            env=_env())
    if result.returncode != 0:
        raise GitError(redact(result.stderr.strip() or "git push failed"))
    return redact((result.stdout + result.stderr).strip()) or "Pushed."


def commit(repo: Path, message: str, files: list[str], confirm: bool) -> str:
    _confirm(confirm, "Committing records the selected files.")
    if not message.strip():
        raise GitError("Write a commit message.")
    if not files:
        raise GitError("Choose at least one file.")
    for f in files:
        if (repo / f).resolve() != repo.resolve() and repo.resolve() not in (repo / f).resolve().parents:
            raise GitError(f"{f} is outside the repository.")
    git(repo, "add", "--", *files)
    return git(repo, "commit", "-m", message, "--", *files)


def switch(repo: Path, branch: str, create: bool, confirm: bool) -> str:
    _confirm(confirm, "Switching branches changes the working tree.")
    return git(repo, "switch", *(["-c"] if create else []), _ref(branch)) or f"On {branch}."


def stash(repo: Path, action: str, confirm: bool) -> str:
    _confirm(confirm, f"`stash {action}` changes the working tree.")
    if action not in ("push", "pop"):
        raise GitError("Use push or pop.")
    return git(repo, "stash", action) or "Done."


def abort(repo: Path, operation: str, confirm: bool) -> str:
    _confirm(confirm, f"Aborting the {operation} drops its progress.")
    if operation not in ("merge", "rebase", "cherry-pick"):
        raise GitError("Nothing to abort.")
    return git(repo, operation, "--abort") or f"Aborted the {operation}."


def summary(path: str | Path) -> dict[str, Any]:
    repo = repo_root(Path(path))
    if repo is None:
        return {"repo": None}
    try:
        st = status(repo)
    except GitError as exc:
        return {"repo": str(repo), "error": str(exc)}
    last = log(repo, 1)
    return {"repo": str(repo), "branch": st["branch"], "changed": len(st["changed"]) + len(st["untracked"]),
            "ahead": st["ahead"], "behind": st["behind"], "conflicts": len(st["conflicts"]), "operation": st["operation"],
            "remotes": st["remotes"], "last_commit": last[0] if last else None}
