"""Commit external-operation intent before sending; never infer non-execution."""

# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json
import sqlite3

from nymph_toolkit.contracts import OperationFailure
from ._model import copy, cycle_id, dump, record

APPLICATION_ID = 0x4E544B41
SCHEMA = {"metadata": [("singleton", "INTEGER"), ("identity", "TEXT")],
          "requests": [("sequence", "INTEGER"), ("request_id", "TEXT"), ("record", "TEXT")]}
TRANSITIONS = {"prepared": {"cycle_sent", "failed"}, "cycle_sent": {"cycle_sent", "cycle_saved", "completed", "failed"},
               "cycle_saved": {"apply_sent", "completed", "failed"}, "apply_sent": {"apply_sent", "completed", "failed"},
               "completed": set(), "failed": set()}


class Store:
    def __init__(self, path, identity):
        if type(path) is not str or not path or not Path(path).is_absolute():
            raise ValueError("Sleep activity path must be absolute")
        self.path, self.identity, self.connection = path, copy(identity, 4096), None

    def open(self):
        connection = sqlite3.connect(self.path, timeout=1, isolation_level=None)
        try:
            app, version = (connection.execute("PRAGMA " + name).fetchone()[0] for name in ("application_id", "user_version"))
            objects = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if app == version == 0 and not objects:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), identity TEXT NOT NULL)")
                connection.execute("CREATE TABLE requests (sequence INTEGER PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, record TEXT NOT NULL)")
                connection.execute("INSERT INTO metadata VALUES (1,?)", (dump(self.identity),))
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            elif app != APPLICATION_ID or version != 1:
                raise ValueError("Unsupported Sleep activity database")
            objects = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if set(objects) != {(name,) for name in SCHEMA} or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("Invalid Sleep activity database structure")
            for table, columns in SCHEMA.items():
                if [(row[1], row[2]) for row in connection.execute(f"PRAGMA table_info({table})")] != columns:
                    raise ValueError("Invalid Sleep activity table")
            if connection.execute("SELECT * FROM metadata").fetchall() != [(1, dump(self.identity))]:
                raise ValueError("Different Sleep activity configuration")
            rows = connection.execute("SELECT * FROM requests ORDER BY sequence LIMIT 4097").fetchall()
            if len(rows) > 4096:
                raise ValueError("Sleep activity history exceeds its limit")
            for expected, (sequence, key, raw) in enumerate(rows, 1):
                value = record(json.loads(raw), self.identity)
                if sequence != expected or key != value["request"]["request_id"] or raw != dump(value):
                    raise ValueError("Sleep activity history is inconsistent")
            self.connection = connection
        except BaseException:
            connection.close()
            raise

    def get(self, key):
        row = self.connection.execute("SELECT record FROM requests WHERE request_id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else OperationFailure("sleep_activity.not_found", "Unknown request_id")

    def begin(self, value, activity):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.get(value["request_id"])
            if isinstance(existing, dict):
                connection.commit()
                if existing["request"] != value:
                    return OperationFailure("sleep_activity.conflict", "request_id has different input"), False
                return existing, False
            count = connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            if count >= 4096:
                connection.rollback()
                return OperationFailure("sleep_activity.history_full", "History is full; existing records retained"), False
            result = record(dict(request=value, cycle_id=cycle_id(self.identity["module_id"], value), activity=activity,
                                 phase="prepared", cycle=None, persona=None, error=None), self.identity)
            connection.execute("INSERT INTO requests VALUES (?,?,?)", (count + 1, value["request_id"], dump(result)))
            connection.commit()
            return result, True
        except BaseException:
            connection.rollback()
            raise

    def save(self, previous, current):
        current = record(current, self.identity)
        if (current["phase"] not in TRANSITIONS[previous["phase"]]
                or any(previous[k] != current[k] for k in ("request", "cycle_id", "activity"))):
            raise ValueError("Invalid Sleep activity transition")
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            result = connection.execute("UPDATE requests SET record=? WHERE request_id=? AND record=?",
                                        (dump(current), current["request"]["request_id"], dump(previous)))
            if result.rowcount != 1:
                raise ValueError("Sleep activity record changed")
            connection.commit()
            return current
        except BaseException:
            connection.rollback()
            raise

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
