"""MongoDB (documents) and Redis (keys): native views, no SQL."""
from __future__ import annotations

import json
from typing import Any

from stackloom.databases.base import Adapter, DbError


class MongoAdapter(Adapter):
    engine = "mongodb"
    kind = "document"

    def __init__(self, info, password):
        super().__init__(info, password)
        try:
            import pymongo
        except ImportError:
            raise DbError("The MongoDB driver is not installed. Run: pipx inject stackloom pymongo (or pip install 'stackloom[mongodb]').")
        self.pymongo = pymongo
        self.client = pymongo.MongoClient(host=info.host or "127.0.0.1", port=info.port or 27017,
                                          username=info.username or None, password=password or None,
                                          serverSelectionTimeoutMS=5000, appname="stackloom")

    def close(self):
        self.client.close()

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except self.pymongo.errors.PyMongoError as exc:
            raise DbError(str(exc))

    def server(self):
        info = self._call(self.client.server_info)
        return {"version": "MongoDB " + info.get("version", "?"), "databases": len(self.databases())}

    def databases(self):
        return [{"name": d["name"], "size_bytes": d.get("sizeOnDisk")} for d in self._call(self.client.list_databases)]

    def tables(self, database):
        db = self.client[database]
        return [{"name": n, "type": "collection", "rows": self._call(db[n].estimated_document_count)}
                for n in sorted(self._call(db.list_collection_names))]

    def columns(self, database, table):
        doc = self._call(self.client[database][table].find_one) or {}
        return [{"name": k, "type": type(v).__name__, "pk": k == "_id"} for k, v in doc.items()]

    def find(self, database: str, collection: str, filter_json: str = "{}", limit: int = 50, skip: int = 0) -> dict[str, Any]:
        try:
            flt = json.loads(filter_json or "{}")
        except ValueError:
            raise DbError("The filter must be JSON, for example {\"status\": \"active\"}.")
        if not isinstance(flt, dict) or any(k.startswith("$where") for k in json.dumps(flt).split('"')):
            raise DbError("Use a plain JSON filter ($where is not allowed).")
        coll = self.client[database][collection]
        docs = list(self._call(lambda: coll.find(flt).skip(max(0, skip)).limit(max(1, min(limit, 500)))))
        return {"documents": [json.loads(json.dumps(d, default=str)) for d in docs],
                "total": self._call(coll.count_documents, flt)}

    def execute(self, database, sql, params=None, limit=1000):
        raise DbError("MongoDB uses filters, not SQL. Use the collection browser.")

    def browse(self, database, table, limit=50, offset=0, order=None):
        data = self.find(database, table, "{}", limit, offset)
        cols = sorted({k for d in data["documents"] for k in d})
        return {"columns": cols, "rows": [[json.dumps(d.get(c), default=str) if isinstance(d.get(c), (dict, list)) else d.get(c)
                                           for c in cols] for d in data["documents"]],
                "total": data["total"], "limit": limit, "offset": offset, "documents": data["documents"]}


class RedisAdapter(Adapter):
    engine = "redis"
    kind = "keyvalue"

    def __init__(self, info, password):
        super().__init__(info, password)
        try:
            import redis
        except ImportError:
            raise DbError("The Redis driver is not installed. Run: pipx inject stackloom redis (or pip install 'stackloom[redis]').")
        self.redis = redis
        self.client = redis.Redis(host=info.host or "127.0.0.1", port=info.port or 6379, username=info.username or None,
                                  password=password or None, db=int(info.database or 0), socket_timeout=5, decode_responses=True)

    def _call(self, fn, *args):
        try:
            return fn(*args)
        except self.redis.RedisError as exc:
            raise DbError(str(exc))

    def close(self):
        self.client.close()

    def server(self):
        info = self._call(self.client.info)
        return {"version": "Redis " + str(info.get("redis_version")), "memory": info.get("used_memory_human"),
                "clients": info.get("connected_clients"), "keys": self._call(self.client.dbsize)}

    def databases(self):
        info = self._call(self.client.info, "keyspace")
        return [{"name": k.replace("db", ""), "keys": v.get("keys")} for k, v in info.items()] or [{"name": "0", "keys": 0}]

    def tables(self, database):
        return [{"name": "keys", "type": "keyspace", "rows": self._call(self.client.dbsize)}]

    def columns(self, database, table):
        return [{"name": "key"}, {"name": "type"}, {"name": "ttl"}]

    def scan(self, pattern: str = "*", count: int = 200) -> list[dict[str, Any]]:
        keys = []
        for key in self.client.scan_iter(match=pattern or "*", count=100):
            keys.append({"key": key, "type": self._call(self.client.type, key), "ttl": self._call(self.client.ttl, key)})
            if len(keys) >= count:
                break
        return keys

    def get(self, key: str) -> Any:
        kind = self._call(self.client.type, key)
        fetch = {"string": self.client.get, "hash": self.client.hgetall, "list": lambda k: self.client.lrange(k, 0, 199),
                 "set": lambda k: sorted(self.client.smembers(k))[:200], "zset": lambda k: self.client.zrange(k, 0, 199, withscores=True)}
        if kind not in fetch:
            return {"type": kind, "value": None}
        return {"type": kind, "value": self._call(fetch[kind], key)}

    def browse(self, database, table, limit=50, offset=0, order=None):
        keys = self.scan("*", limit + offset)[offset:]
        return {"columns": ["key", "type", "ttl"], "rows": [[k["key"], k["type"], k["ttl"]] for k in keys],
                "total": self._call(self.client.dbsize), "limit": limit, "offset": offset}

    def variables(self):
        return [{"name": k, "value": str(v)} for k, v in self._call(self.client.info).items()]

    def execute(self, database, sql, params=None, limit=1000):
        raise DbError("Redis has no SQL. Use the key browser.")
