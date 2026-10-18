"""Storage for CareLoop.

Two interchangeable backends with the same interface:
  * DynamoStore  - Amazon DynamoDB single-table design (production, set CARELOOP_TABLE)
  * SQLiteStore  - local file, zero setup (development and offline demos)

Records are plain dicts so the server logic never cares which backend is live.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class Store(ABC):
    backend = "abstract"

    @abstractmethod
    def put_medication(self, user: str, med: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_medications(self, user: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete_medication(self, user: str, med_id: str) -> None: ...

    @abstractmethod
    def add_event(self, user: str, kind: str, when_iso: str, data: dict[str, Any]) -> None: ...

    @abstractmethod
    def events_between(self, user: str, kind: str, start_iso: str, end_iso: str) -> list[dict[str, Any]]: ...


class SQLiteStore(Store):
    backend = "sqlite"

    def __init__(self, path: str = "careloop.db"):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS medications (
                user TEXT, id TEXT, data TEXT, PRIMARY KEY (user, id));
            CREATE TABLE IF NOT EXISTS events (
                user TEXT, kind TEXT, at TEXT, data TEXT);
            CREATE INDEX IF NOT EXISTS ev_idx ON events (user, kind, at);
            """
        )

    def put_medication(self, user, med):
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO medications VALUES (?,?,?)", (user, med["id"], json.dumps(med))
            )
            self._db.commit()

    def list_medications(self, user):
        rows = self._db.execute("SELECT data FROM medications WHERE user=?", (user,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete_medication(self, user, med_id):
        with self._lock:
            self._db.execute("DELETE FROM medications WHERE user=? AND id=?", (user, med_id))
            self._db.commit()

    def add_event(self, user, kind, when_iso, data):
        with self._lock:
            self._db.execute(
                "INSERT INTO events VALUES (?,?,?,?)", (user, kind, when_iso, json.dumps(data))
            )
            self._db.commit()

    def events_between(self, user, kind, start_iso, end_iso):
        rows = self._db.execute(
            "SELECT data FROM events WHERE user=? AND kind=? AND at>=? AND at<? ORDER BY at",
            (user, kind, start_iso, end_iso),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    return value


def _to_dynamo(value: Any) -> Any:
    return json.loads(json.dumps(value), parse_float=Decimal)


class DynamoStore(Store):
    """Single table. PK = USER#<id>; SK = MED#<id> | DOSE#<iso> | SYMPTOM#<iso>."""

    backend = "dynamodb"

    def __init__(self, table_name: str, region: str | None = None):
        import boto3
        from boto3.dynamodb.conditions import Key

        self._key = Key
        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def put_medication(self, user, med):
        self._table.put_item(Item={"pk": f"USER#{user}", "sk": f"MED#{med['id']}", **_to_dynamo(med)})

    def list_medications(self, user):
        resp = self._table.query(
            KeyConditionExpression=self._key("pk").eq(f"USER#{user}") & self._key("sk").begins_with("MED#")
        )
        return [_strip(_from_dynamo(i)) for i in resp.get("Items", [])]

    def delete_medication(self, user, med_id):
        self._table.delete_item(Key={"pk": f"USER#{user}", "sk": f"MED#{med_id}"})

    def add_event(self, user, kind, when_iso, data):
        # Suffix keeps two events logged in the same second from colliding.
        sk = f"{kind.upper()}#{when_iso}#{data.get('id', '')}"
        self._table.put_item(Item={"pk": f"USER#{user}", "sk": sk, **_to_dynamo(data)})

    def events_between(self, user, kind, start_iso, end_iso):
        prefix = kind.upper()
        resp = self._table.query(
            KeyConditionExpression=self._key("pk").eq(f"USER#{user}")
            & self._key("sk").between(f"{prefix}#{start_iso}", f"{prefix}#{end_iso}")
        )
        return [_strip(_from_dynamo(i)) for i in resp.get("Items", [])]


def _strip(item: dict[str, Any]) -> dict[str, Any]:
    item.pop("pk", None)
    item.pop("sk", None)
    return item


def make_store() -> Store:
    table = os.getenv("CARELOOP_TABLE")
    if table:
        return DynamoStore(table, os.getenv("AWS_REGION"))
    return SQLiteStore(os.getenv("CARELOOP_DB", "careloop.db"))
