"""Single-worker persistence of Persona state and its atomic update journal."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from nymph_toolkit.contracts import OperationFailure, TemporaryUnavailable
from ._model import apply, dump, integer, request, text, traits

APPLICATION_ID = 0x4E544B50
MAX_UPDATES = 4096


async def settled(future):
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        if not future.cancelled():
            future.exception()
        raise asyncio.CancelledError
    return future.result()


def utc():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if type(value) is not str:
        raise ValueError("Invalid saved Persona timestamp")
    at = datetime.fromisoformat(value)
    if at.tzinfo is None or at.utcoffset().total_seconds() != 0:
        raise ValueError("Saved Persona timestamp must have a UTC offset")
    return value


class Store:
    def __init__(self, path, module_id, initial, changed=None):
        if type(path) is not str or not path or not Path(path).is_absolute():
            raise ValueError("Persona path must be an absolute file path")
        self.identity = dict(module_id=text(module_id, 128), initial_traits=traits(initial))
        self.path, self.changed = path, changed
        self.pool = self.connection = self.stop_task = None
        self.ready = self.busy = self.closing = False
        self.lock = asyncio.Lock()

    async def _work(self, function, *args):
        return await settled(asyncio.get_running_loop().run_in_executor(self.pool, function, *args))

    async def start(self):
        if self.pool is not None or self.closing:
            raise RuntimeError("Persona cannot be started twice")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-persona")
        try:
            async with self.lock:
                await self._work(self._open)
                self.ready = True
        except BaseException:
            await self.stop()
            raise

    def _initial(self, at):
        return dict(module_id=self.identity["module_id"], revision=0,
                    traits=self.identity["initial_traits"], updated_at=at)

    def _open(self):
        connection = sqlite3.connect(self.path, timeout=1.0, isolation_level=None)
        try:
            app = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            objects = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if app == version == 0 and not objects:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), identity TEXT NOT NULL, initial_at TEXT NOT NULL, state TEXT NOT NULL)")
                connection.execute("CREATE TABLE updates (sequence INTEGER PRIMARY KEY, command_id TEXT NOT NULL UNIQUE, request TEXT NOT NULL, receipt TEXT NOT NULL)")
                at = utc()
                connection.execute("INSERT INTO metadata VALUES (1,?,?,?)", (dump(self.identity), at, dump(self._initial(at))))
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            elif app != APPLICATION_ID or version != 1:
                raise ValueError("Unsupported Persona database identity/version; file left intact")
            expected = {
                "metadata": [("singleton", "INTEGER"), ("identity", "TEXT"), ("initial_at", "TEXT"), ("state", "TEXT")],
                "updates": [("sequence", "INTEGER"), ("command_id", "TEXT"), ("request", "TEXT"), ("receipt", "TEXT")],
            }
            names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if names != set(expected) or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("Invalid Persona database")
            for table, columns in expected.items():
                if [(r[1], r[2]) for r in connection.execute(f"PRAGMA table_info({table})")] != columns:
                    raise ValueError("Invalid Persona schema")
            metadata = connection.execute("SELECT * FROM metadata").fetchall()
            if len(metadata) != 1 or metadata[0][0] != 1 or metadata[0][1] != dump(self.identity):
                raise ValueError("Persona configuration differs from saved identity")
            state = self._initial(timestamp(metadata[0][2]))
            rows = connection.execute("SELECT * FROM updates ORDER BY sequence LIMIT ?", (MAX_UPDATES + 1,)).fetchall()
            if len(rows) > MAX_UPDATES:
                raise ValueError("Persona update history limit exceeded")
            seen = set()
            for expected_sequence, (sequence, key, raw_request, raw_receipt) in enumerate(rows, 1):
                value = request(json.loads(raw_request), self.identity["initial_traits"])
                receipt = json.loads(raw_receipt)
                if (type(sequence) is not int or sequence != expected_sequence or key != value["command_id"]
                        or key in seen or type(receipt) is not dict):
                    raise ValueError("Invalid Persona update index")
                result = apply(state, value, sequence, timestamp(receipt.get("stored_at")))
                if isinstance(result, OperationFailure) or dump(result[1]) != dump(receipt):
                    raise ValueError("Invalid saved Persona update")
                state = result[0]
                seen.add(key)
            if dump(state) != dump(json.loads(metadata[0][3])):
                raise ValueError("Persona current state differs from its history")
            self.connection = connection
        except BaseException:
            connection.close()
            raise

    async def execute(self, operation, *args):
        try:
            if operation == "apply":
                args = (request(args[0], self.identity["initial_traits"]),)
            elif operation == "get_update":
                args = (text(args[0], 128),)
            elif operation == "history":
                integer(args[0], 0, MAX_UPDATES); integer(args[1], 1, 4)
            elif operation != "get":
                raise ValueError("Unknown Persona operation")
        except (ValueError, TypeError, OverflowError, RecursionError) as error:
            return OperationFailure("persona.invalid", str(error))
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Persona is stopped or processing another operation")
        self.busy = True
        try:
            async with self.lock:
                try:
                    if self.changed is not None:
                        await self.changed(1)
                    return await self._work(self._execute, operation, *args)
                finally:
                    if self.changed is not None and not self.closing:
                        await self.changed(0)
        finally:
            self.busy = False

    def _execute(self, operation, *args):
        try:
            return getattr(self, "_" + operation)(*args)
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return OperationFailure("persona.storage", "Persona storage failed; inspect before retrying")

    def _get(self):
        return json.loads(self.connection.execute("SELECT state FROM metadata WHERE singleton=1").fetchone()[0])

    def _get_update(self, key):
        row = self.connection.execute("SELECT receipt FROM updates WHERE command_id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else OperationFailure("persona.not_found", "Unknown command_id")

    def _history(self, after, limit):
        rows = self.connection.execute("SELECT receipt FROM updates WHERE sequence>? ORDER BY sequence LIMIT ?", (after, limit)).fetchall()
        updates = [json.loads(row[0]) for row in rows]
        return dict(updates=updates, next_after=updates[-1]["sequence"] if updates else after,
                    current_revision=self._get()["revision"])

    def _apply(self, value):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT request,receipt FROM updates WHERE command_id=?", (value["command_id"],)).fetchone()
            if row is not None:
                result = (json.loads(row[1]) if row[0] == dump(value) else
                          OperationFailure("persona.command_conflict", "command_id has different input"))
            else:
                count = connection.execute("SELECT count(*) FROM updates").fetchone()[0]
                if count >= MAX_UPDATES:
                    result = OperationFailure("persona.history_full", "Persona update history is full; existing state retained")
                else:
                    result = apply(self._get(), value, count + 1, utc())
                    if not isinstance(result, OperationFailure):
                        state, result = result
                        connection.execute("UPDATE metadata SET state=? WHERE singleton=1", (dump(state),))
                        connection.execute("INSERT INTO updates VALUES (?,?,?,?)",
                                           (result["sequence"], value["command_id"], dump(value), dump(result)))
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise

    async def stop(self):
        self.ready = False
        self.closing = True
        if self.stop_task is None:
            self.stop_task = asyncio.create_task(self._close())
        await settled(self.stop_task)

    async def _close(self):
        async with self.lock:
            if self.pool is not None:
                try:
                    if self.connection is not None:
                        await self._work(self.connection.close)
                finally:
                    self.pool.shutdown(wait=True)
                    self.pool = self.connection = None
