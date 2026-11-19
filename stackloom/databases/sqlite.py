from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from stackloom.databases.base import Adapter, DbError, rows_out


class SqliteAdapter(Adapter):
    engine = "sqlite"

    def __init__(self, info, password):
        super().__init__(info, password)
        path = Path(info.path).expanduser()
        if not path.is_file():
            raise DbError(f"No SQLite file at {path}.")
        with path.open("rb") as fh:
            if fh.read(16) != b"SQLite format 3\x00":
                raise DbError(f"{path.name} is not a SQLite database.")
        mode = "ro" if info.read_only else "rw"
        self.conn = sqlite3.connect(f"file:{path}?mode={mode}", uri=True, timeout=5, isolation_level=None,
                                    check_same_thread=False)

    def close(self):
        self.conn.close()

    def server(self):
        size = Path(self.info.path).stat().st_size
        return {"version": "SQLite " + sqlite3.sqlite_version, "size_bytes": size, "databases": 1}

    def databases(self):
        return [{"name": "main"}]

    def tables(self, database):
        rows = self.conn.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view')"
                                 " AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        out = []
        for name, kind in rows:
            try:
                n = self.conn.execute(f"SELECT COUNT(*) FROM {self.q(name)}").fetchone()[0]
            except sqlite3.Error:
                n = None
            out.append({"name": name, "type": kind, "rows": n})
        return out

    def columns(self, database, table):
        self._known(table)
        return [{"name": r[1], "type": r[2], "nullable": not r[3], "default": r[4], "pk": bool(r[5])}
                for r in self.conn.execute(f"PRAGMA table_info({self.q(table)})")]

    def _known(self, table):
        if not self.conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone():
            raise DbError(f"No table named {table!r}.")

    def indexes(self, database, table):
        self._known(table)
        out = []
        for r in self.conn.execute(f"PRAGMA index_list({self.q(table)})"):
            cols = [c[2] for c in self.conn.execute(f"PRAGMA index_info({self.q(r[1])})")]
            out.append({"name": r[1], "unique": bool(r[2]), "columns": cols})
        return out

    def foreign_keys(self, database, table):
        self._known(table)
        return [{"column": r[3], "references": f"{r[2]}({r[4]})"} for r in self.conn.execute(f"PRAGMA foreign_key_list({self.q(table)})")]

    def execute(self, database, sql, params=None, limit=1000):
        try:
            cur = self.conn.execute(sql, params or [])
            return rows_out(cur, limit)
        except sqlite3.Error as exc:
            raise DbError(str(exc))

    def variables(self):
        out = []
        for name in ("journal_mode", "page_size", "page_count", "foreign_keys", "user_version", "encoding"):
            out.append({"name": name, "value": str(self.conn.execute(f"PRAGMA {name}").fetchone()[0])})
        return out

    def backup_to(self, target: Path) -> None:
        dest = sqlite3.connect(target)
        try:
            self.conn.backup(dest)
        finally:
            dest.close()
