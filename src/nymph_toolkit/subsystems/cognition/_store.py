"""Cognition-owned SQLite evidence; worker calls are serialized by the service."""

# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sqlite3

from nymph_toolkit.contracts import OperationFailure
from ._model import MAX_SAMPLES, dump, inspect_samples, validate_sample

APPLICATION_ID = 0x4E544B43
SCHEMA = "CREATE TABLE samples (sequence INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)"


class Store:
    def __init__(self, path, provider):
        if type(path) is not str or not path or not Path(path).is_absolute():
            raise ValueError("Cognition path must be an absolute file path")
        self.path, self.provider = path, provider
        self.connection = None

    def open(self):
        connection = sqlite3.connect(self.path, timeout=1.0, isolation_level=None)
        try:
            identity = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if identity == 0 and version == 0 and not tables:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(SCHEMA)
                connection.execute("CREATE TABLE metadata (provider TEXT NOT NULL)")
                connection.execute("INSERT INTO metadata VALUES (?)", (self.provider,))
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            elif identity != APPLICATION_ID or version != 1:
                raise ValueError("Unsupported Cognition database identity/version; file left intact")
            expected = [("sequence", "INTEGER"), ("record_id", "TEXT"), ("payload", "TEXT")]
            if ([(r[1], r[2]) for r in connection.execute("PRAGMA table_info(samples)")] != expected
                    or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]
                    or connection.execute("SELECT provider FROM metadata").fetchall() != [(self.provider,)]):
                raise ValueError("Invalid Cognition database or different Memory provider")
            self.connection = connection
            self._samples()
        except BaseException:
            connection.close()
            self.connection = None
            raise

    @staticmethod
    def _row(row):
        try:
            sequence, key, payload = row
            sample = json.loads(payload)
            validate_sample(sample)
            if type(sequence) is not int or not 1 <= sequence <= 2**63 - 1 or key != sample["record_id"]:
                raise ValueError("Invalid saved identity")
        except (ValueError, TypeError, OverflowError) as error:
            raise sqlite3.DatabaseError("Invalid saved learning evidence") from error
        return sequence, sample

    def _samples(self):
        rows = self.connection.execute("SELECT * FROM samples ORDER BY sequence LIMIT ?", (MAX_SAMPLES + 1,)).fetchall()
        if len(rows) > MAX_SAMPLES:
            raise sqlite3.DatabaseError("Cognition sample limit exceeded")
        return [self._row(row) for row in rows]

    def execute(self, operation, *args):
        try:
            return getattr(self, "_" + operation)(*args)
        except sqlite3.Error:
            return OperationFailure("cognition.storage", "Cognition storage failed; inspect the database before retrying")

    def _learn(self, sample):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT * FROM samples WHERE record_id=?", (sample["record_id"],)).fetchone()
            if row is not None:
                sequence, stored = self._row(row)
                if stored != sample:
                    result = OperationFailure("cognition.conflict", "record_id already has different evidence or annotations")
                else:
                    result = self._receipt(sequence, stored)
            elif connection.execute("SELECT count(*) FROM samples").fetchone()[0] >= MAX_SAMPLES:
                result = OperationFailure("cognition.full", "The initial model supports at most 256 examples")
            else:
                connection.execute("INSERT INTO samples(record_id,payload) VALUES (?,?)", (sample["record_id"], dump(sample)))
                row = connection.execute("SELECT * FROM samples WHERE record_id=?", (sample["record_id"],)).fetchone()
                result = self._receipt(*self._row(row))
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _receipt(sequence, sample):
        return {"record_id": sample["record_id"], "sequence": sequence, "fingerprint": sample["fingerprint"]}

    def _inspect(self, *args):
        return inspect_samples(self._samples(), *args)

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
