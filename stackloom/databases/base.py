"""Common adapter interface and SQL safety helpers."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

MAX_ROWS = 1000

READ_KEYWORDS = {"select", "with", "show", "explain", "describe", "desc", "values", "table"}


class DbError(RuntimeError):
    """Message is shown to the user."""


class NeedsConfirmation(DbError):
    pass


@dataclass
class ConnInfo:
    id: str
    engine: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    path: str = ""
    read_only: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


def first_keyword(sql: str) -> str:
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S).strip().lower()
    match = re.match(r"[a-z]+", text)
    return match.group(0) if match else ""


def statements(sql: str) -> int:
    """Rough count of statements (semicolons outside quotes)."""
    count, quote = 0, None
    for ch in sql:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == ";":
            count += 1
    return count + (0 if sql.strip().endswith(";") else 1)


def is_read(sql: str) -> bool:
    kw = first_keyword(sql)
    if kw == "with":
        return not re.search(r"\b(insert|update|delete|merge|create|drop|alter|truncate)\b", sql, re.I)
    return kw in READ_KEYWORDS or kw == "pragma" and "=" not in sql


def guard(sql: str, read_only: bool, confirm: bool) -> None:
    if not sql.strip():
        raise DbError("Write a query first.")
    if statements(sql) > 1:
        raise DbError("Run one statement at a time.")
    if is_read(sql):
        return
    if read_only:
        raise DbError("This connection is read-only. Use an administrative connection to change data.")
    if not confirm:
        raise NeedsConfirmation(f"This {first_keyword(sql).upper() or 'statement'} changes the database. Confirm to run it.")


class Adapter:
    engine = ""
    kind = "sql"  # sql | document | keyvalue
    quote = '"'

    def __init__(self, info: ConnInfo, password: str | None) -> None:
        self.info = info
        self.password = password

    # identifiers are checked against the live schema before use, then quoted
    def q(self, name: str) -> str:
        return self.quote + name.replace(self.quote, self.quote * 2) + self.quote

    def ensure_table(self, database: str, table: str) -> None:
        if table not in {t["name"] for t in self.tables(database)}:
            raise DbError(f"No table named {table!r}.")

    def ensure_columns(self, database: str, table: str, names) -> None:
        known = {c["name"] for c in self.columns(database, table)}
        for name in names:
            if name not in known:
                raise DbError(f"{table} has no column {name!r}.")

    # interface ---------------------------------------------------------------
    def close(self) -> None: ...
    def server(self) -> dict[str, Any]: raise NotImplementedError
    def databases(self) -> list[dict[str, Any]]: raise NotImplementedError
    def tables(self, database: str) -> list[dict[str, Any]]: raise NotImplementedError
    def columns(self, database: str, table: str) -> list[dict[str, Any]]: raise NotImplementedError
    def indexes(self, database: str, table: str) -> list[dict[str, Any]]: return []
    def foreign_keys(self, database: str, table: str) -> list[dict[str, Any]]: return []
    def execute(self, database: str, sql: str, params: list | None = None, limit: int = MAX_ROWS) -> dict[str, Any]:
        raise NotImplementedError
    def variables(self) -> list[dict[str, Any]]: return []
    def processes(self) -> list[dict[str, Any]]: return []
    def users(self) -> list[dict[str, Any]]: return []
    def create_database(self, name: str) -> None: raise DbError(f"{self.engine} cannot create databases here.")
    def drop_database(self, name: str) -> None: raise DbError(f"{self.engine} cannot drop databases here.")

    # shared ------------------------------------------------------------------
    def query(self, database: str, sql: str, confirm: bool = False, limit: int = MAX_ROWS) -> dict[str, Any]:
        guard(sql, self.info.read_only, confirm)
        started = time.monotonic()
        result = self.execute(database, sql, None, limit)
        result["ms"] = int((time.monotonic() - started) * 1000)
        return result

    def primary_key(self, database: str, table: str) -> list[str]:
        return [c["name"] for c in self.columns(database, table) if c.get("pk")]

    def browse(self, database: str, table: str, limit: int = 50, offset: int = 0, order: str | None = None) -> dict[str, Any]:
        self.ensure_table(database, table)
        limit = max(1, min(limit, 500))
        sql = f"SELECT * FROM {self.q(table)}"
        if order:
            self.ensure_columns(database, table, [order])
            sql += f" ORDER BY {self.q(order)}"
        sql += f" LIMIT {int(limit)} OFFSET {int(max(0, offset))}"
        result = self.execute(database, sql, None, limit)
        total = self.execute(database, f"SELECT COUNT(*) AS n FROM {self.q(table)}", None, 1)["rows"][0][0]
        return {**result, "total": total, "limit": limit, "offset": offset}

    def _placeholder(self) -> str:
        return "?"

    def _writable(self) -> None:
        if self.info.read_only:
            raise DbError("This connection is read-only.")

    def insert_row(self, database: str, table: str, values: dict[str, Any]) -> int:
        self._writable()
        self.ensure_columns(database, table, values)
        cols = ", ".join(self.q(c) for c in values)
        marks = ", ".join(self._placeholder() for _ in values)
        return self.execute(database, f"INSERT INTO {self.q(table)} ({cols}) VALUES ({marks})", list(values.values()))["rowcount"]

    def update_row(self, database: str, table: str, key: dict[str, Any], values: dict[str, Any]) -> int:
        self._writable()
        self._key_ok(database, table, key)
        self.ensure_columns(database, table, values)
        sets = ", ".join(f"{self.q(c)} = {self._placeholder()}" for c in values)
        where = " AND ".join(f"{self.q(c)} = {self._placeholder()}" for c in key)
        return self.execute(database, f"UPDATE {self.q(table)} SET {sets} WHERE {where}",
                            list(values.values()) + list(key.values()))["rowcount"]

    def delete_row(self, database: str, table: str, key: dict[str, Any]) -> int:
        self._writable()
        self._key_ok(database, table, key)
        where = " AND ".join(f"{self.q(c)} = {self._placeholder()}" for c in key)
        return self.execute(database, f"DELETE FROM {self.q(table)} WHERE {where}", list(key.values()))["rowcount"]

    def _key_ok(self, database: str, table: str, key: dict[str, Any]) -> None:
        pk = self.primary_key(database, table)
        if not pk:
            raise DbError(f"{table} has no primary key, so a single row cannot be addressed safely. Use the query editor.")
        if set(key) != set(pk):
            raise DbError(f"Identify the row by its primary key ({', '.join(pk)}).")

    def drop_table(self, database: str, table: str) -> None:
        self._writable()
        self.ensure_table(database, table)
        self.execute(database, f"DROP TABLE {self.q(table)}")


def rows_out(cursor, limit: int) -> dict[str, Any]:
    if cursor.description is None:
        return {"columns": [], "rows": [], "rowcount": cursor.rowcount, "truncated": False}
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchmany(limit + 1)
    truncated = len(rows) > limit
    return {"columns": columns, "rows": [[_cell(v) for v in r] for r in rows[:limit]], "rowcount": cursor.rowcount,
            "truncated": truncated}


def _cell(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return f"<{len(data)} bytes>"
    return str(value)
