"""Regenerate docs/API.md from the application's routes: python scripts/api_doc.py"""
from pathlib import Path

from stackloom.api.app import create_app

GROUPS = [("/api/auth", "Sign-in"), ("/api/overview", "Workspace"), ("/api/projects", "Projects and runtime"),
          ("/api/discovery", "Discovery"), ("/api/groups", "Workspace"), ("/api/services", "Projects and runtime"),
          ("/api/ports", "Ports"), ("/api/docker", "Docker"), ("/api/db", "Databases"), ("/api/codecortex", "CodeCortex"),
          ("/api/graph", "CodeCortex"), ("/api/git", "Git"), ("/api/env", "Environment"), ("/api/diagnostics", "Diagnostics"),
          ("/api/backups", "Backups"), ("/api/notifications", "Notifications"), ("/api/tasks", "Tasks"),
          ("/api/activity", "Workspace"), ("/api/settings", "Settings"), ("/api/system", "Settings"), ("/api/health", "Health")]


def main() -> None:
    app = create_app(background=False)
    sections: dict[str, list[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        group = next((g for prefix, g in GROUPS if path.startswith(prefix)), "Other")
        for method in sorted(getattr(route, "methods", []) - {"HEAD"}):
            sections.setdefault(group, []).append(f"| `{method}` | `{path}` |")
    lines = ["# STACKLOOM HTTP API", "",
             "The dashboard's own API, on 127.0.0.1 only. Generated from the code by `scripts/api_doc.py`; do not edit by hand.", "",
             "Every route except `GET /api/health` and `POST /api/auth/login` needs the session cookie set at sign-in.",
             "Requests that change something must send the session's CSRF token (returned by sign-in and `GET /api/auth/me`)",
             "in `X-CSRF-Token`. While the first-run password is unchanged, only the `/api/auth/*` routes answer.", "",
             "Errors come back as `{\"detail\": \"<plain-language message>\"}`. `409` means the action needs confirmation:",
             "repeat it with `\"confirm\": true` (or `\"approve\": true` for a start command) after showing the message to the user.",
             "Long operations return a task (`{\"id\", \"status\", \"message\"}`); poll `GET /api/tasks/{id}` until it is `done` or `failed`.", ""]
    for _, group in dict.fromkeys((g, g) for _, g in GROUPS):
        if group in sections:
            lines += [f"## {group}", "", "| Method | Path |", "|---|---|", *sorted(set(sections.pop(group)), key=lambda r: r.split("`")[3]), ""]
    Path("docs/API.md").write_text("\n".join(lines))
    print("wrote docs/API.md")


if __name__ == "__main__":
    main()
