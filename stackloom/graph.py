"""Read a project's saved CodeCortex graph for the explorer.

Reads <project>/.codecortex/graph.db and state.json with sqlite3 and json.
Never imports the engine and never re-indexes: viewing a graph is read-only.
Node and edge kinds, centrality and clusters are CodeCortex's own; nothing
here adds analysis of its own.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from stackloom.maps import map_dir

# Low-level kinds hidden by default, as in CodeCortex's own explorer.
DETAIL_KINDS = {"Variable", "Parameter", "Callsite"}
DETAIL_EDGES = {"READS", "WRITES", "CONTROLS", "FLOWS_TO", "DEFINES"}


class GraphError(RuntimeError):
    pass


def _open(project_path: str) -> sqlite3.Connection:
    db = map_dir(project_path) / "graph.db"
    if not db.exists():
        raise GraphError("This project has no map yet. Build it first.")
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)


def _state(project_path: str) -> dict[str, Any]:
    try:
        return json.loads((map_dir(project_path) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _rel(project_path: str, file_path: str) -> str:
    root = str(Path(project_path).resolve())
    return file_path[len(root) + 1:] if file_path.startswith(root + "/") else file_path


def summary(project_path: str) -> dict[str, Any]:
    con = _open(project_path)
    try:
        kinds = dict(con.execute("SELECT kind, COUNT(*) FROM nodes GROUP BY kind ORDER BY 2 DESC").fetchall())
        edge_kinds = dict(con.execute("SELECT kind, COUNT(*) FROM edges GROUP BY kind ORDER BY 2 DESC").fetchall())
        languages = [r[0] for r in con.execute("SELECT DISTINCT language FROM nodes WHERE language != ''")]
    finally:
        con.close()
    state = _state(project_path)
    return {"node_kinds": kinds, "edge_kinds": edge_kinds, "languages": languages,
            "nodes": sum(kinds.values()), "edges": sum(edge_kinds.values()),
            "saved_at": state.get("saved_at"), "derived_stale": bool(state.get("derived_stale")),
            "codecortex_version": state.get("codecortex_version"),
            "default_node_kinds": [k for k in kinds if k not in DETAIL_KINDS],
            "default_edge_kinds": [k for k in edge_kinds if k not in DETAIL_EDGES]}


def load(project_path: str, node_kinds: list[str] | None = None, edge_kinds: list[str] | None = None,
         limit: int = 400, focus: str | None = None, depth: int = 1) -> dict[str, Any]:
    """A bounded subgraph: the most central nodes, or the neighbourhood of `focus`."""
    limit = max(10, min(limit, 3000))
    info = summary(project_path)
    node_kinds = node_kinds or info["default_node_kinds"]
    edge_kinds = edge_kinds or info["default_edge_kinds"]
    state = _state(project_path)
    centrality = state.get("centrality") or {}
    clusters = state.get("clusters") or {}
    con = _open(project_path)
    try:
        nk = ",".join("?" * len(node_kinds))
        ek = ",".join("?" * len(edge_kinds))
        if focus:
            selected = {focus}
            frontier = {focus}
            for _ in range(max(1, min(depth, 3))):
                if not frontier:
                    break
                marks = ",".join("?" * len(frontier))
                rows = con.execute(f"SELECT source, target FROM edges WHERE kind IN ({ek}) AND (source IN ({marks}) OR target IN ({marks}))",
                                   [*edge_kinds, *frontier, *frontier]).fetchall()
                nxt = {n for r in rows for n in r} - selected
                selected |= nxt
                frontier = nxt
                if len(selected) >= limit:
                    break
            marks = ",".join("?" * len(selected))
            node_rows = con.execute(f"SELECT qualified_name, kind, name, file_path, language, range_start, is_test FROM nodes"
                                    f" WHERE qualified_name IN ({marks}) AND (kind IN ({nk}) OR qualified_name = ?)",
                                    [*selected, *node_kinds, focus]).fetchall()
        else:
            node_rows = con.execute(f"SELECT qualified_name, kind, name, file_path, language, range_start, is_test FROM nodes"
                                    f" WHERE kind IN ({nk})", node_kinds).fetchall()
        total = len(node_rows)

        def score(qname: str) -> float:
            c = centrality.get(qname) or {}
            return float(c.get("composite_score") or 0.0)

        node_rows.sort(key=lambda r: (r[0] != focus, -score(r[0])))
        node_rows = node_rows[:limit]
        ids = {r[0] for r in node_rows}
        scores = sorted((score(q) for q in ids), reverse=True)
        threshold = scores[max(0, len(scores) // 10 - 1)] if scores and scores[0] > 0 else float("inf")
        edges = []
        if ids:
            marks = ",".join("?" * len(ids))
            for i, (kind, source, target, conf) in enumerate(con.execute(
                    f"SELECT kind, source, target, confidence FROM edges WHERE kind IN ({ek})"
                    f" AND source IN ({marks}) AND target IN ({marks})", [*edge_kinds, *ids, *ids])):
                edges.append({"id": f"e{i}", "source": source, "target": target, "kind": kind, "confidence": round(conf or 1, 3)})
    finally:
        con.close()
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1
    nodes = []
    for qname, kind, name, file_path, language, line, is_test in node_rows:
        c = centrality.get(qname) or {}
        s = score(qname)
        nodes.append({"id": qname, "name": name, "kind": kind, "file": _rel(project_path, file_path), "language": language,
                      "line": line, "is_test": bool(is_test), "centrality": round(s, 6), "fan_in": c.get("fan_in", 0),
                      "fan_out": c.get("fan_out", 0), "cluster": clusters.get(qname, -1), "degree": degree.get(qname, 0),
                      "hotspot": s >= threshold})
    return {"nodes": nodes, "edges": edges, "total_matching": total, "truncated": total > len(nodes),
            "node_kinds": node_kinds, "edge_kinds": edge_kinds, "summary": info}


def search(project_path: str, text: str, limit: int = 30) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    con = _open(project_path)
    try:
        like = f"%{text.replace('%', '').replace('_', '')}%"
        rows = con.execute("SELECT qualified_name, kind, name, file_path, range_start FROM nodes"
                           " WHERE (name LIKE ? OR qualified_name LIKE ?) AND kind NOT IN ('Variable','Parameter','Callsite')"
                           " ORDER BY (name = ?) DESC, length(name) LIMIT ?", (like, like, text, limit)).fetchall()
    finally:
        con.close()
    return [{"id": r[0], "kind": r[1], "name": r[2], "file": _rel(project_path, r[3]), "line": r[4]} for r in rows]


def node(project_path: str, qname: str) -> dict[str, Any]:
    con = _open(project_path)
    try:
        row = con.execute("SELECT qualified_name, kind, name, file_path, language, range_start, range_end, parent_qualified,"
                          " is_test, extra FROM nodes WHERE qualified_name = ?", (qname,)).fetchone()
        if row is None:
            raise GraphError("That symbol is not in the map. It may have been renamed since the last refresh.")
        incoming = con.execute("SELECT e.kind, e.source, n.kind, n.name FROM edges e LEFT JOIN nodes n ON n.qualified_name = e.source"
                               " WHERE e.target = ? LIMIT 200", (qname,)).fetchall()
        outgoing = con.execute("SELECT e.kind, e.target, n.kind, n.name FROM edges e LEFT JOIN nodes n ON n.qualified_name = e.target"
                               " WHERE e.source = ? LIMIT 200", (qname,)).fetchall()
    finally:
        con.close()
    c = (_state(project_path).get("centrality") or {}).get(qname) or {}
    file_path = row[3]
    return {
        "id": row[0], "kind": row[1], "name": row[2], "file": _rel(project_path, file_path), "abs_file": file_path,
        "language": row[4], "line": row[5], "end_line": row[6], "parent": row[7], "is_test": bool(row[8]),
        "centrality": {k: c.get(k) for k in ("composite_score", "fan_in", "fan_out", "bridge_score", "influence_score")},
        "incoming": [{"kind": r[0], "id": r[1], "node_kind": r[2], "name": r[3]} for r in incoming],
        "outgoing": [{"kind": r[0], "id": r[1], "node_kind": r[2], "name": r[3]} for r in outgoing],
        "source": snippet(project_path, file_path, row[5], row[6]),
    }


def snippet(project_path: str, file_path: str, start: int, end: int, max_lines: int = 60) -> str:
    """Source lines of a symbol. Only files inside the project are read."""
    root = Path(project_path).resolve()
    path = Path(file_path).resolve()
    if root not in path.parents or not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if not start and not end:
        return "\n".join(lines[:max_lines])
    first = max(0, (start or 1) - 1)
    last = min(len(lines), max(first + 1, end or first + 1), first + max_lines)
    from stackloom.security import redact

    return redact("\n".join(lines[first:last]))


def to_graphml(graph: dict[str, Any]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
           '<key id="kind" for="all" attr.name="kind" attr.type="string"/>',
           '<key id="name" for="node" attr.name="name" attr.type="string"/>',
           '<key id="file" for="node" attr.name="file" attr.type="string"/>',
           '<key id="centrality" for="node" attr.name="centrality" attr.type="double"/>',
           '<graph edgedefault="directed">']
    for n in graph["nodes"]:
        out.append(f'<node id="{escape(n["id"], {chr(34): "&quot;"})}"><data key="kind">{escape(n["kind"])}</data>'
                   f'<data key="name">{escape(n["name"])}</data><data key="file">{escape(n["file"])}</data>'
                   f'<data key="centrality">{n["centrality"]}</data></node>')
    for e in graph["edges"]:
        out.append(f'<edge source="{escape(e["source"], {chr(34): "&quot;"})}" target="{escape(e["target"], {chr(34): "&quot;"})}">'
                   f'<data key="kind">{escape(e["kind"])}</data></edge>')
    out += ["</graph>", "</graphml>"]
    return "\n".join(out)


# --------------------------------------------------------------------------- map management

def validate(project_path: str) -> dict[str, Any]:
    problems, notes = [], []
    directory = map_dir(project_path)
    if not (directory / "state.json").exists():
        problems.append("state.json is missing.")
    if not (directory / "graph.db").exists():
        problems.append("graph.db is missing.")
    else:
        con = sqlite3.connect(f"file:{directory / 'graph.db'}?mode=ro", uri=True)
        try:
            check = con.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                problems.append(f"graph.db failed its integrity check: {check}")
            dangling = con.execute("SELECT COUNT(*) FROM edges WHERE source NOT IN (SELECT qualified_name FROM nodes)").fetchone()[0]
            if dangling:
                notes.append(f"{dangling} relations start at symbols outside the map (external calls); this is normal.")
        finally:
            con.close()
    state = _state(project_path)
    if state.get("derived_stale"):
        notes.append("Centrality and clusters describe an earlier version of the graph. Rebuild to recompute them.")
    missing = [f for f in (state.get("files") or {}) if not Path(f).exists()]
    if missing:
        notes.append(f"{len(missing)} indexed files no longer exist; the next refresh removes them.")
    return {"ok": not problems, "problems": problems, "notes": notes}


def delete_map(project_path: str, confirm: bool) -> str:
    directory = map_dir(project_path).resolve()
    if directory.name != ".codecortex" or directory.parent != Path(project_path).resolve():
        raise GraphError("Refusing to delete an unexpected folder.")
    if not directory.exists():
        return "There was no map to delete."
    if not confirm:
        raise GraphError("Deleting the map means coding agents lose it until it is rebuilt. Confirm to continue.")
    shutil.rmtree(directory)
    return "Deleted the map. Source files were not touched."


def connect_agent(project_path: str, confirm: bool) -> str:
    """Run `codecortex install` for Claude Code in the project (edits its CLAUDE.md and .claude/settings.json)."""
    if not confirm:
        raise GraphError("This adds a CodeCortex section to the project's CLAUDE.md and a hook to its .claude/settings.json. "
                         "Confirm to continue.")
    exe = Path(sys.executable).parent / "codecortex"
    command = [str(exe)] if exe.exists() else [sys.executable, "-m", "codecortex"]
    result = subprocess.run([*command, "install", "--platform", "claude", "--dir", str(Path(project_path).resolve())],
                            capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        raise GraphError((result.stderr or result.stdout).strip() or "codecortex install failed.")
    return result.stdout.strip() or "Connected."
