"""Agency journal: committed decisions can be inspected without re-deciding."""

# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sqlite3

from nymph_toolkit.contracts import OperationFailure
from ._model import decide, dump, request

APPLICATION_ID = 0x4E544B41
MAX_DECISIONS = 4096
SCHEMA = "CREATE TABLE decisions (sequence INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT NOT NULL UNIQUE, input TEXT NOT NULL, evidence TEXT NOT NULL, result TEXT NOT NULL)"


class Store:
    def __init__(self, path, identity):
        if type(path) is not str or not Path(path).is_absolute():
            raise ValueError("Agency path must be an absolute file path")
        self.path, self.identity = path, json.loads(dump(identity))
        self.connection = None

    def open(self):
        connection = sqlite3.connect(self.path, timeout=1.0, isolation_level=None)
        try:
            app = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if app == version == 0 and not tables:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(SCHEMA)
                connection.execute("CREATE TABLE metadata (identity TEXT NOT NULL)")
                connection.execute("INSERT INTO metadata VALUES (?)", (dump(self.identity),))
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            elif app != APPLICATION_ID or version != 1:
                raise ValueError("Unsupported Agency database identity/version; file left intact")
            expected = [("sequence", "INTEGER"), ("decision_id", "TEXT"), ("input", "TEXT"), ("evidence", "TEXT"), ("result", "TEXT")]
            if ([(r[1],r[2]) for r in connection.execute("PRAGMA table_info(decisions)")] != expected
                    or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]
                    or connection.execute("SELECT identity FROM metadata").fetchall() != [(dump(self.identity),)]):
                raise ValueError("Invalid Agency database or changed configuration")
            rows = connection.execute("SELECT * FROM decisions ORDER BY sequence LIMIT ?", (MAX_DECISIONS+1,)).fetchall()
            if len(rows) > MAX_DECISIONS:
                raise ValueError("Agency decision limit exceeded")
            history = {}
            for position, (sequence, key, raw_input, raw_evidence, raw_result) in enumerate(rows, 1):
                value = request(json.loads(raw_input), self.identity["catalog"])
                previous = history.get(value["current"]["decision_id"]) if value["current"] else None
                expected_result = decide(value, json.loads(raw_evidence), self.identity["catalog"], self.identity["module_id"], previous)
                expected_result["sequence"] = sequence
                if (type(sequence) is not int or sequence != position or key != value["decision_id"] or key in history
                        or dump(expected_result) != dump(json.loads(raw_result))):
                    raise ValueError("Invalid saved Agency decision")
                history[key] = expected_result
            self.connection = connection
        except BaseException:
            connection.close()
            raise

    def execute(self, operation, *args):
        try:
            return getattr(self, "_"+operation)(*args)
        except sqlite3.Error:
            return OperationFailure("agency.storage", "Agency journal failed; inspect before retrying")

    def _get(self, key):
        row = self.connection.execute("SELECT result FROM decisions WHERE decision_id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else OperationFailure("agency.not_found", "Unknown decision_id")

    def _replay(self, value):
        row = self.connection.execute("SELECT input,result FROM decisions WHERE decision_id=?", (value["decision_id"],)).fetchone()
        if row:
            if row[0] != dump(value):
                return OperationFailure("agency.decision_conflict", "decision_id has different input")
            return json.loads(row[1])
        if self.connection.execute("SELECT count(*) FROM decisions").fetchone()[0] >= MAX_DECISIONS:
            return OperationFailure("agency.history_full", "Decision journal is full; earlier decisions retained")
        return None

    def _save(self, value, evidence, result):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            replay = self._replay(value)
            if replay is not None:
                connection.commit()
                return replay
            cursor = connection.execute("INSERT INTO decisions(decision_id,input,evidence,result) VALUES(?,?,?,?)",
                                        (value["decision_id"], dump(value), dump(evidence), dump(result)))
            result = dict(result, sequence=cursor.lastrowid)
            connection.execute("UPDATE decisions SET result=? WHERE decision_id=?", (dump(result),value["decision_id"]))
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
