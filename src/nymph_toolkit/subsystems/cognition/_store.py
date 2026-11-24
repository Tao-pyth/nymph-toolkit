"""Cognition-owned SQLite evidence; worker calls are serialized by the service."""

# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sqlite3

from nymph_toolkit.contracts import OperationFailure
from ._model import MAX_SAMPLES, dump, identifier, inspect_samples, validate_sample

APPLICATION_ID = 0x4E544B43
SCHEMA = "CREATE TABLE samples (sequence INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)"
MAX_CORRECTIONS = 4096


class Store:
    def __init__(self, path, provider, enable_revision=False):
        if type(path) is not str or not path or not Path(path).is_absolute():
            raise ValueError("Cognition path must be an absolute file path")
        self.path, self.provider = path, provider
        self.connection = None
        self.enable_revision = enable_revision
        self.version = None

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
                version = 1
            elif identity != APPLICATION_ID or version not in (1, 2):
                raise ValueError("Unsupported Cognition database identity/version; file left intact")
            expected = [("sequence", "INTEGER"), ("record_id", "TEXT"), ("payload", "TEXT")]
            if ([(r[1], r[2]) for r in connection.execute("PRAGMA table_info(samples)")] != expected
                    or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]
                    or connection.execute("SELECT provider FROM metadata").fetchall() != [(self.provider,)]):
                raise ValueError("Invalid Cognition database or different Memory provider")
            self.connection = connection
            self._samples()
            if version == 1 and self.enable_revision:
                self._upgrade()
                version = 2
            if version == 2:
                self._validate_revisions()
            self.version = version
        except BaseException:
            connection.close()
            self.connection = None
            raise

    def _upgrade(self):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute("CREATE TABLE revisions (record_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)")
            connection.execute("INSERT INTO revisions SELECT record_id, 0 FROM samples")
            connection.execute("CREATE TABLE corrections (command_id TEXT PRIMARY KEY, record_id TEXT NOT NULL, expected_revision INTEGER NOT NULL, before_payload TEXT NOT NULL, after_payload TEXT NOT NULL, result TEXT NOT NULL)")
            connection.execute("PRAGMA user_version=2")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def _validate_revisions(self):
        samples = {s["record_id"]: s for _, s in self._samples()}
        revisions = dict(self.connection.execute("SELECT record_id, revision FROM revisions"))
        commands = self.connection.execute("SELECT * FROM corrections ORDER BY rowid LIMIT ?", (MAX_CORRECTIONS + 1,)).fetchall()
        if (set(revisions) != set(samples) or len(commands) > MAX_CORRECTIONS
                or any(type(r) is not int or not 0 <= r <= 2**63-1 for r in revisions.values())):
            raise sqlite3.DatabaseError("Invalid annotation revisions")
        counts, last = {}, {}
        try:
            for command, key, expected, before, after, encoded_result in commands:
                identifier(command)
                before, after, result = json.loads(before), json.loads(after), json.loads(encoded_result)
                validate_sample(before); validate_sample(after)
                if (key not in samples or before["record_id"] != key or after["record_id"] != key
                        or before["fingerprint"] != after["fingerprint"] or before["source_kind"] != after["source_kind"]
                        or type(expected) is not int or expected != counts.get(key, 0)
                        or (key in last and before != last[key])):
                    raise ValueError("Broken correction history")
                changed = before != after
                wanted = {"command_id": command, "record_id": key, "revision": expected + int(changed),
                          "status": "applied" if changed else "no_change"}
                if result != wanted:
                    raise ValueError("Invalid correction receipt")
                counts[key], last[key] = wanted["revision"], after
            if any(revisions[key] != counts.get(key, 0) or (key in last and samples[key] != last[key]) for key in samples):
                raise ValueError("Current annotations disagree with correction history")
        except (ValueError, TypeError, KeyError) as error:
            raise sqlite3.DatabaseError("Invalid saved correction history") from error

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
                if self.version == 2:
                    connection.execute("INSERT INTO revisions VALUES (?, 0)", (sample["record_id"],))
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

    def _get_revision(self, record_id):
        row = self.connection.execute("SELECT * FROM samples WHERE record_id=?", (record_id,)).fetchone()
        if row is None:
            return OperationFailure("cognition.not_found", "Record has not been learned")
        _, sample = self._row(row)
        revision = self.connection.execute("SELECT revision FROM revisions WHERE record_id=?", (record_id,)).fetchone()
        if revision is None:
            raise sqlite3.DatabaseError("Missing annotation revision")
        return dict(sample, revision=revision[0])

    def _correct(self, sample, command_id, expected_revision):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            previous = connection.execute("SELECT * FROM corrections WHERE command_id=?", (command_id,)).fetchone()
            if previous is not None:
                _, key, expected, _, after, encoded_result = previous
                if key == sample["record_id"] and expected == expected_revision and json.loads(after) == sample:
                    result = json.loads(encoded_result)
                else:
                    result = OperationFailure("cognition.command_conflict", "command_id has different correction content")
            else:
                current = self._get_revision(sample["record_id"])
                if isinstance(current, OperationFailure):
                    result = current
                elif current["fingerprint"] != sample["fingerprint"] or current["source_kind"] != sample["source_kind"]:
                    result = OperationFailure("cognition.conflict", "Memory evidence changed")
                elif current["revision"] != expected_revision:
                    result = OperationFailure("cognition.revision_conflict", "Expected revision is stale; inspect before retrying")
                elif connection.execute("SELECT count(*) FROM corrections").fetchone()[0] >= MAX_CORRECTIONS:
                    result = OperationFailure("cognition.history_full", "Correction history is full; existing evidence retained")
                else:
                    before = {k: v for k, v in current.items() if k != "revision"}
                    changed = before != sample
                    result = {"command_id": command_id, "record_id": sample["record_id"],
                              "revision": expected_revision + int(changed), "status": "applied" if changed else "no_change"}
                    connection.execute("UPDATE samples SET payload=? WHERE record_id=?", (dump(sample), sample["record_id"]))
                    connection.execute("UPDATE revisions SET revision=? WHERE record_id=?", (result["revision"], sample["record_id"]))
                    connection.execute("INSERT INTO corrections VALUES (?, ?, ?, ?, ?, ?)",
                                       (command_id, sample["record_id"], expected_revision, dump(before), dump(sample), dump(result)))
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
