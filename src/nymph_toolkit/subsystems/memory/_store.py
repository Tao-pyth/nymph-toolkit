"""Single-worker SQLite ownership; cancellation never abandons an active write."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from nymph_toolkit.contracts import OperationFailure, TemporaryUnavailable
from ._records import canonical, filters, identifier

APPLICATION_ID = 0x4E544B4D
SCHEMA = """CREATE TABLE records (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    stored_at TEXT NOT NULL
)"""


async def settled(future):
    """Wait for ownership cleanup even if the awaiting task is repeatedly cancelled."""
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        # Retrieve a worker error as well; cancellation is not proof of rollback.
        if not future.cancelled():
            future.exception()
        raise asyncio.CancelledError
    return future.result()


class Store:
    def __init__(self, path, changed=None):
        if type(path) is not str or not path or not Path(path).is_absolute():
            raise ValueError("Memory path must be an absolute file path")
        self.path, self.changed = path, changed
        self.pool = self.connection = None
        self.ready = self.busy = self.closing = False
        self.lock = asyncio.Lock()
        self.stop_task = None

    async def _work(self, function, *args):
        return await settled(asyncio.get_running_loop().run_in_executor(self.pool, function, *args))

    async def start(self):
        if self.pool is not None or self.closing:
            raise RuntimeError("Memory cannot be started twice")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-memory")
        try:
            async with self.lock:
                await self._work(self._open)
                self.ready = True
        except BaseException:
            await self.stop()
            raise

    def _open(self):
        connection = sqlite3.connect(self.path, timeout=1.0, isolation_level=None)
        try:
            app_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if app_id == 0 and version == 0 and not tables:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(SCHEMA)
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                connection.execute("PRAGMA user_version = 1")
                connection.commit()
            elif app_id != APPLICATION_ID or version != 1:
                raise ValueError("Unsupported Memory database identity/version; file left intact")
            expected = [("sequence", "INTEGER"), ("record_id", "TEXT"), ("kind", "TEXT"),
                        ("source_kind", "TEXT"), ("payload", "TEXT"), ("stored_at", "TEXT")]
            actual = [(r[1], r[2]) for r in connection.execute("PRAGMA table_info(records)")]
            if actual != expected or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("Invalid Memory schema or damaged database")
        except BaseException:
            connection.close()
            raise
        self.connection = connection

    async def execute(self, operation, *args):
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Memory is stopped or processing another operation")
        if operation == "put" and type(args[0]) is dict:
            # Accepted fields are strings: a shallow copy snapshots all valid inputs
            # before any await lets the caller mutate its dictionary.
            args = (dict(args[0]),)
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
        except (ValueError, TypeError, OverflowError) as exc:
            return OperationFailure("memory.invalid", str(exc))
        except sqlite3.Error:
            return OperationFailure("memory.storage", "Memory storage operation failed; inspect the database before retrying")

    @staticmethod
    def _record(row):
        # Damaged payloads are storage failures, not bad caller input.
        try:
            result, _ = canonical(json.loads(row[4]))
            if result["record_id"] != row[1] or result["kind"] != row[2] or result["source_kind"] != row[3]:
                raise ValueError("Record index mismatch")
            if type(row[0]) is not int or row[0] <= 0:
                raise ValueError("Invalid sequence")
            timestamp = datetime.fromisoformat(row[5])
            if timestamp.tzinfo is None:
                raise ValueError("Invalid stored_at")
        except (ValueError, TypeError, OverflowError) as exc:
            raise sqlite3.DatabaseError("Invalid stored record") from exc
        return dict(result, sequence=row[0], stored_at=timestamp.astimezone(timezone.utc).isoformat())

    def _put(self, record):
        value, payload = canonical(record)
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT * FROM records WHERE record_id = ?", (value["record_id"],)).fetchone()
            if row is not None:
                result = self._record(row)
                if any(result[k] != v for k, v in value.items()):
                    result = OperationFailure("memory.conflict", "record_id already contains different content")
            else:
                connection.execute("INSERT INTO records(record_id,kind,source_kind,payload,stored_at) VALUES(?,?,?,?,?)",
                                   (value["record_id"], value["kind"], value["source_kind"], payload,
                                    datetime.now(timezone.utc).isoformat()))
                row = connection.execute("SELECT * FROM records WHERE record_id = ?", (value["record_id"],)).fetchone()
                result = self._record(row)
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise

    def _get(self, record_id):
        identifier(record_id)
        row = self.connection.execute("SELECT * FROM records WHERE record_id = ?", (record_id,)).fetchone()
        return self._record(row) if row is not None else OperationFailure("memory.not_found", "Unknown record_id")

    def _query(self, kind, source_kind, after, limit):
        filters(kind, source_kind, after, limit)
        rows = self.connection.execute("""SELECT * FROM records WHERE sequence > ?
            AND (? IS NULL OR kind = ?) AND (? IS NULL OR source_kind = ?)
            ORDER BY sequence LIMIT ?""", (after, kind, kind, source_kind, source_kind, limit + 1)).fetchall()
        records = [self._record(row) for row in rows[:limit]]
        return {"records": records, "after": records[-1]["sequence"] if records else after,
                "has_more": len(rows) > limit}

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
                    # All submitted work has settled before this nonblocking join.
                    self.pool.shutdown(wait=True)
                    self.pool = self.connection = None
