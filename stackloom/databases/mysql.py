from __future__ import annotations

from stackloom.databases.base import Adapter, DbError, rows_out


def _driver():
    try:
        import pymysql
    except ImportError:
        raise DbError("The MySQL driver is not installed. Run: pipx inject stackloom PyMySQL (or pip install 'stackloom[mysql]').")
    return pymysql


class MysqlAdapter(Adapter):
    engine = "mysql"
    quote = "`"

    def __init__(self, info, password):
        super().__init__(info, password)
        self.pymysql = _driver()
        try:
            self.conn = self.pymysql.connect(host=info.host or "127.0.0.1", port=info.port or 3306, user=info.username or None,
                                             password=password or "", database=info.database or None, connect_timeout=5,
                                             autocommit=True, charset="utf8mb4")
        except self.pymysql.Error as exc:
            raise DbError(str(exc))
        if info.read_only:
            self.execute("", "SET SESSION TRANSACTION READ ONLY")

    def _placeholder(self):
        return "%s"

    def close(self):
        self.conn.close()

    def execute(self, database, sql, params=None, limit=1000):
        try:
            if database:
                self.conn.select_db(database)
            with self.conn.cursor() as cur:
                cur.execute(sql, params or None)
                return rows_out(cur, limit)
        except self.pymysql.Error as exc:
            raise DbError(str(exc))

    def server(self):
        r = self.execute("", "SELECT VERSION(), CURRENT_USER()")["rows"][0]
        return {"version": r[0], "user": r[1], "databases": len(self.databases())}

    def databases(self):
        rows = self.execute("", "SELECT s.schema_name, COALESCE(SUM(t.data_length + t.index_length), 0)"
                                " FROM information_schema.schemata s LEFT JOIN information_schema.tables t"
                                " ON t.table_schema = s.schema_name GROUP BY s.schema_name ORDER BY 1")["rows"]
        return [{"name": r[0], "size_bytes": int(r[1])} for r in rows]

    def tables(self, database):
        rows = self.execute(database, "SELECT table_name, table_type, table_rows FROM information_schema.tables"
                                      " WHERE table_schema = %s ORDER BY 1", [database])["rows"]
        return [{"name": r[0], "type": r[1].lower(), "rows": r[2]} for r in rows]

    def columns(self, database, table):
        rows = self.execute(database, "SELECT column_name, column_type, is_nullable = 'YES', column_default, column_key = 'PRI'"
                                      " FROM information_schema.columns WHERE table_schema = %s AND table_name = %s"
                                      " ORDER BY ordinal_position", [database, table])["rows"]
        if not rows:
            raise DbError(f"No table named {table!r}.")
        return [{"name": r[0], "type": r[1], "nullable": bool(r[2]), "default": r[3], "pk": bool(r[4])} for r in rows]

    def indexes(self, database, table):
        self.ensure_table(database, table)
        rows = self.execute(database, f"SHOW INDEX FROM {self.q(table)}")["rows"]
        out: dict = {}
        for r in rows:
            out.setdefault(r[2], {"name": r[2], "unique": not r[1], "columns": []})["columns"].append(r[4])
        return list(out.values())

    def foreign_keys(self, database, table):
        rows = self.execute(database, "SELECT column_name, CONCAT(referenced_table_name, '(', referenced_column_name, ')')"
                                      " FROM information_schema.key_column_usage WHERE table_schema = %s AND table_name = %s"
                                      " AND referenced_table_name IS NOT NULL", [database, table])["rows"]
        return [{"column": r[0], "references": r[1]} for r in rows]

    def variables(self):
        return [{"name": r[0], "value": r[1]} for r in self.execute("", "SHOW GLOBAL VARIABLES", None, 2000)["rows"]]

    def processes(self):
        rows = self.execute("", "SHOW FULL PROCESSLIST")["rows"]
        return [{"pid": r[0], "user": r[1], "database": r[3], "state": r[4], "query": (r[7] or "")[:200], "since": f"{r[5]}s"}
                for r in rows]

    def users(self):
        try:
            rows = self.execute("", "SELECT user, host FROM mysql.user ORDER BY 1")["rows"]
        except DbError:
            return []
        return [{"name": f"{r[0]}@{r[1]}"} for r in rows]

    def create_database(self, name):
        self._writable()
        self.execute("", f"CREATE DATABASE {self.q(name)}")

    def drop_database(self, name):
        self._writable()
        if name not in {d["name"] for d in self.databases()}:
            raise DbError(f"No database named {name!r}.")
        self.execute("", f"DROP DATABASE {self.q(name)}")
