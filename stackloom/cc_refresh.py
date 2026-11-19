"""Child process that refreshes one project's CodeCortex map.

    python -m stackloom.cc_refresh --task ID --project ID PATH [--rebuild]

Loads the saved map and re-parses only changed files, or builds the map when
there is none (CodeCortex's open_pipeline). Runs at low priority and reports
through its row in the tasks table.
"""
from __future__ import annotations

import argparse
import os
import time
import traceback
from pathlib import Path

from stackloom import db, maps, registry, tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stackloom.cc_refresh")
    parser.add_argument("--task", type=int, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
    conn = db.connect()
    root = Path(args.path).resolve()
    started = time.monotonic()
    tasks.update(conn, args.task, status="running", message="Loading CodeCortex…")
    last = [0.0]

    def progress(done: int, total: int, path: Path) -> None:
        if time.monotonic() - last[0] > 1.5:
            last[0] = time.monotonic()
            tasks.update(conn, args.task, message=f"Parsed {done} of {total} files")

    try:
        from codecortex.pipeline.state import has_saved_index, open_pipeline

        had_map = has_saved_index(root)
        tasks.update(conn, args.task, message="Refreshing the saved map" if had_map and not args.rebuild
                     else "Building the map (first time; later refreshes only re-parse changed files)")
        result = open_pipeline(root, on_progress=progress, rebuild=args.rebuild, save=True)
        detail = ""
        if isinstance(result, tuple) and len(result) == 2:
            info = result[1]
            detail = f" ({getattr(info, 'source', '')}, {getattr(info, 'reparsed', 0)} re-parsed)"
        project = registry.get(conn, args.project)
        record = maps.sync(conn, project)
        stats = record.get("stats", {})
        tasks.update(conn, args.task, status="done",
                     message=f"{stats.get('nodes', 0)} symbols, {stats.get('edges', 0)} relations in "
                             f"{time.monotonic() - started:.1f}s{detail}")
        # The map is current as of now even when nothing changed (CodeCortex then skips saving).
        conn.execute("UPDATE maps SET error = '', last_refresh = ? WHERE project_id = ?", (db.now(), args.project))
        return 0
    except Exception as exc:
        tasks.update(conn, args.task, status="failed", message=f"{type(exc).__name__}: {exc}",
                     log=traceback.format_exc())
        conn.execute("UPDATE maps SET status = 'error', error = ? WHERE project_id = ?", (str(exc)[:500], args.project))
        from stackloom import notify

        notify.add(conn, f"Map refresh failed: {args.project}", f"{type(exc).__name__}: {exc}", "error", "#/codecortex")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
