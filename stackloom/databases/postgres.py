from __future__ import annotations

from stackloom.databases.base import Adapter, DbError, rows_out


def _driver():
    try:
        import psycopg
    except ImportError:
        raise DbError("The PostgreSQL driver is not installed. Run: pipx inject stackloom 'psycopg[binary]' "
                      "(or pip install 'stackloom[postgres]').")
    return psycopg


class PostgresAdapter(Adapter):
    engine = "postgres"

    def __init__(self, info, password):
        super().__init__(info, password)
        self.psycopg = _driver()
        self._conns: dict = {}

    def _conn(self, database: str | None = None):
        db = database or self.info.database or "postgres"
        if db not in self._conns:
            try:
                conn = self.psycopg.connect(host=self.info.host or "127.0.0.1", port=self.info.port or 5432, dbname=db,
                                            user=self.info.username or None, password=self.password or None,
                                            connect_timeout=5, autocommit=True, application_name="stackloom")
            except self.psycopg.Error as exc:
                raise DbError(str(exc).strip())
            if self.info.read_only:
                conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            self._conns[db] = conn
        return self._conns[db]

    def _placeholder(self):
        return "%s"

    def close(self):
        for c in self._conns.values():
            c.close()

    def execute(self, database, sql, params=None, limit=1000):
        try:
            with self._conn(database).cursor() as cur:
                cur.execute(sql, params or None)
                return rows_out(cur, limit)
        except self.psycopg.Error as exc:
            raise DbError(str(exc).strip())

    def server(self):
        r = self.execute("", "SELECT version(), current_user, pg_database_size(current_database())")["rows"][0]
        return {"version": r[0], "user": r[1], "size_bytes": r[2], "databases": len(self.databases())}

    def databases(self):
        rows = self.execute("", "SELECT datname, pg_database_size(datname) FROM pg_database WHERE NOT datistemplate ORDER BY 1")["rows"]
        return [{"name": r[0], "size_bytes": r[1]} for r in rows]

    def tables(self, database):
        rows = self.execute(database, "SELECT table_name, table_type, table_schema FROM information_schema.tables"
                                      " WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 3, 1")["rows"]
        return [{"name": r[0] if r[2] == "public" else f"{r[2]}.{r[0]}", "type": r[1].lower(), "rows": None} for r in rows]

    def q(self, name):
        return ".".join('"' + p.replace('"', '""') + '"' for p in name.split(".", 1))

    def _split(self, table):
        return table.split(".", 1) if "." in table else ("public", table)

    def columns(self, database, table):
        schema, name = self._split(table)
        rows = self.execute(database, """
            SELECT c.column_name, c.data_type, c.is_nullable = 'YES', c.column_default,
                   EXISTS (SELECT 1 FROM information_schema.table_constraints t
                           JOIN information_schema.key_column_usage k USING (constraint_schema, constraint_name)
                           WHERE t.constraint_type = 'PRIMARY KEY' AND k.table_schema = c.table_schema
                             AND k.table_name = c.table_name AND k.column_name = c.column_name)
            FROM information_schema.columns c WHERE c.table_schema = %s AND c.table_name = %s ORDER BY c.ordinal_position""",
                            [schema, name])["rows"]
        if not rows:
            raise DbError(f"No table named {table!r}.")
        return [{"name": r[0], "type": r[1], "nullable": r[2], "default": r[3], "pk": r[4]} for r in rows]

    def indexes(self, database, table):
        schema, name = self._split(table)
        return [{"name": r[0], "definition": r[1]} for r in
                self.execute(database, "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s",
                             [schema, name])["rows"]]

    def foreign_keys(self, database, table):
        schema, name = self._split(table)
        rows = self.execute(database, """
            SELECT kcu.column_name, ccu.table_name || '(' || ccu.column_name || ')'
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name)
            JOIN information_schema.constraint_column_usage ccu USING (constraint_schema, constraint_name)
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s AND tc.table_name = %s""", [schema, name])["rows"]
        return [{"column": r[0], "references": r[1]} for r in rows]

    def variables(self):
        return [{"name": r[0], "value": r[1]} for r in self.execute("", "SELECT name, setting FROM pg_settings ORDER BY name", None, 2000)["rows"]]

    def processes(self):
        rows = self.execute("", "SELECT pid, usename, datname, state, left(query, 200), backend_start::text FROM pg_stat_activity"
                                " WHERE datname IS NOT NULL ORDER BY backend_start")["rows"]
        return [{"pid": r[0], "user": r[1], "database": r[2], "state": r[3], "query": r[4], "since": r[5]} for r in rows]

    def users(self):
        rows = self.execute("", "SELECT rolname, rolsuper, rolcreatedb, rolcanlogin FROM pg_roles WHERE rolname NOT LIKE 'pg\\_%' ORDER BY 1")["rows"]
        return [{"name": r[0], "superuser": r[1], "create_db": r[2], "login": r[3]} for r in rows]

    def create_database(self, name):
        self._writable()
        self.execute("", f"CREATE DATABASE {self.q(name)}")

    def drop_database(self, name):
        self._writable()
        if name not in {d["name"] for d in self.databases()}:
            raise DbError(f"No database named {name!r}.")
        self.execute("", f"DROP DATABASE {self.q(name)}")
