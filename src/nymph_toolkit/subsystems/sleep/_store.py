"""Atomic Sleep state, cycle audit and one-time experience evaluation ledger."""

# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sqlite3

from nymph_toolkit.contracts import OperationFailure
from ._model import ActiveFull, MAX_CYCLES, dump, initial, inspect, page, request, snapshot, transition

APPLICATION_ID = 0x4E544B53
SCHEMA = {
    "metadata": [("singleton", "INTEGER"), ("identity", "TEXT"), ("state", "TEXT")],
    "cycles": [("sequence", "INTEGER"), ("cycle_id", "TEXT"), ("input", "TEXT"), ("evidence", "TEXT"), ("persona", "TEXT"), ("receipt", "TEXT")],
    "credited": [("record_id", "TEXT")],
}


class Store:
    def __init__(self, path, identity):
        if type(path) is not str or not path or not Path(path).is_absolute():
            raise ValueError("Sleep path must be an absolute file path")
        self.path, self.identity = path, snapshot(identity, 8192)
        self.connection = None
        self.current, self.credited = initial(), set()

    def open(self):
        connection = sqlite3.connect(self.path, timeout=1.0, isolation_level=None)
        try:
            app = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            objects = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if app == version == 0 and not objects:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), identity TEXT NOT NULL, state TEXT NOT NULL)")
                connection.execute("CREATE TABLE cycles (sequence INTEGER PRIMARY KEY, cycle_id TEXT NOT NULL UNIQUE, input TEXT NOT NULL, evidence TEXT NOT NULL, persona TEXT NOT NULL, receipt TEXT NOT NULL)")
                connection.execute("CREATE TABLE credited (record_id TEXT PRIMARY KEY)")
                connection.execute("INSERT INTO metadata VALUES (1,?,?)", (dump(self.identity), dump(initial())))
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            elif app != APPLICATION_ID or version != 1:
                raise ValueError("Unsupported Sleep database identity/version; file left intact")
            objects = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if set(objects) != {(name,) for name in SCHEMA} or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("Invalid Sleep database objects or integrity")
            for table, expected in SCHEMA.items():
                if [(r[1], r[2]) for r in connection.execute(f"PRAGMA table_info({table})")] != expected:
                    raise ValueError("Invalid Sleep table shape")
            metadata = connection.execute("SELECT * FROM metadata").fetchall()
            if len(metadata) != 1 or metadata[0][:2] != (1, dump(self.identity)):
                raise ValueError("Different Sleep configuration; database left intact")
            current, credited, seen = initial(), set(), set()
            rows = connection.execute("SELECT * FROM cycles ORDER BY sequence LIMIT ?", (MAX_CYCLES + 1,)).fetchall()
            if len(rows) > MAX_CYCLES:
                raise ValueError("Sleep history limit exceeded")
            for number, (sequence, key, raw_input, raw_evidence, raw_persona, raw_receipt) in enumerate(rows, 1):
                value = request(json.loads(raw_input))
                if sequence != number or key != value["cycle_id"] or key in seen or dump(value) != raw_input:
                    raise ValueError("Invalid Sleep cycle identity or order")
                current, expected, added = transition(current, credited, value, json.loads(raw_evidence), json.loads(raw_persona), self.identity)
                if dump(expected) != raw_receipt:
                    raise ValueError("Sleep receipt does not match its evidence")
                credited.update(added); seen.add(key)
            saved_credits = connection.execute("SELECT record_id FROM credited").fetchall()
            if dump(current) != metadata[0][2] or len(saved_credits) != len(credited) or {r[0] for r in saved_credits} != credited:
                raise ValueError("Sleep current state or credited ledger disagrees with its history")
            self.connection, self.current, self.credited = connection, current, credited
        except BaseException:
            connection.close()
            raise

    def execute(self, operation, *args):
        try:
            return getattr(self, "_" + operation)(*args)
        except sqlite3.Error:
            return OperationFailure("sleep.storage", "Sleep database operation failed; inspect before retrying")

    def _get(self, key):
        row = self.connection.execute("SELECT receipt FROM cycles WHERE cycle_id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else OperationFailure("sleep.not_found", "Unknown cycle_id")

    def _preflight(self, value):
        row = self.connection.execute("SELECT input,receipt FROM cycles WHERE cycle_id=?", (value["cycle_id"],)).fetchone()
        if row:
            if row[0] != dump(value):
                return OperationFailure("sleep.cycle_conflict", "cycle_id already has different input")
            return json.loads(row[1])
        if self.current["revision"] >= MAX_CYCLES:
            return OperationFailure("sleep.history_full", "Sleep cycle history is full; existing state retained")
        if value["expected_revision"] != self.current["revision"]:
            return OperationFailure("sleep.revision_conflict", "Inspect the current revision before a new cycle")
        return None

    def _save(self, value, evidence, traits):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            replay = self._preflight(value)
            if replay is not None:
                connection.commit()
                return replay
            try:
                current, receipt, added = transition(self.current, self.credited, value, evidence, traits, self.identity)
            except ActiveFull as error:
                connection.rollback()
                return OperationFailure("sleep.active_full", str(error))
            connection.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?)", (current["revision"], value["cycle_id"], dump(value), dump(evidence), dump(traits), dump(receipt)))
            connection.executemany("INSERT INTO credited VALUES (?)", ((key,) for key in added))
            connection.execute("UPDATE metadata SET state=? WHERE singleton=1", (dump(current),))
            connection.commit()
            self.current = current
            self.credited.update(added)
            return receipt
        except BaseException:
            connection.rollback()
            raise

    def _state(self, after, limit):
        return page(self.current, after, limit)

    def _inspect(self, concept, source_kind):
        return inspect(self.current, concept, source_kind)

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
