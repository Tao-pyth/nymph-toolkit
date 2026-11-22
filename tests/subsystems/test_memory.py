"""B01 storage contracts, failure atomicity, cancellation, and ownership."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import OperationFailure, TemporaryUnavailable
from nymph_toolkit.subsystems.memory._store import APPLICATION_ID, Store


def record(record_id="event-1", **changes):
    value = dict(record_id=record_id, kind="experience", content="雨を観測した。",
                 source_kind="observed", source="dummy:weather", occurred_at="2026-11-23T09:30:00+09:00")
    value.update(changes)
    return value


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "memory.sqlite3")
        self.store = Store(self.path)
        await self.store.start()

    async def asyncTearDown(self):
        await self.store.stop()
        self.directory.cleanup()

    async def test_roundtrip_restart_and_stable_idempotence(self):
        original = record()
        saved = await self.store.execute("put", original)
        self.assertEqual(saved["occurred_at"], "2026-11-23T00:30:00+00:00")
        self.assertIsNotNone(datetime.fromisoformat(saved["stored_at"]).tzinfo)
        self.assertEqual(saved["sequence"], 1)
        original["content"] = "caller mutation"
        snapshot = dict(saved)
        saved["content"] = "result mutation"
        await self.store.stop()
        self.store = Store(self.path)
        await self.store.start()
        self.assertEqual(await self.store.execute("get", "event-1"), snapshot)
        self.assertEqual(await self.store.execute("put", record(occurred_at="2026-11-23T00:30:00Z")), snapshot)
        conflict = await self.store.execute("put", record(content="different"))
        self.assertEqual(conflict.code, "memory.conflict")
        self.assertEqual(await self.store.execute("get", "event-1"), snapshot)

    async def test_kinds_sources_filters_and_cursor_with_new_append(self):
        for i, source in enumerate(("observed", "reported", "inferred", "imagined", "dream")):
            await self.store.execute("put", record(str(i), kind="knowledge" if i % 2 else "experience", source_kind=source))
        page = await self.store.execute("query", None, None, 0, 2)
        self.assertEqual([r["record_id"] for r in page["records"]], ["0", "1"])
        self.assertTrue(page["has_more"])
        await self.store.execute("put", record("later", occurred_at="2000-01-01T00:00:00Z"))
        rest = await self.store.execute("query", None, None, page["after"], 8)
        self.assertEqual([r["record_id"] for r in rest["records"]], ["2", "3", "4", "later"])
        self.assertFalse(rest["has_more"])
        one = await self.store.execute("query", "experience", "dream", 0, 8)
        self.assertEqual([r["record_id"] for r in one["records"]], ["4"])
        empty = await self.store.execute("query", None, None, rest["after"], 8)
        self.assertEqual(empty, {"records": [], "after": 6, "has_more": False})
        self.assertEqual((await self.store.execute("get", "missing")).code, "memory.not_found")

    async def test_bad_records_rejected_without_writes(self):
        cases = [None, [], {}, record(extra=True), record(record_id=True), record(record_id=" "),
                 record(record_id="あ" * 43), record(content=""), record(content="a" * 4096),
                 record(content="\ud800"), record(source=" "), record(source_kind="fact"), record(kind="dream"),
                 record(occurred_at="2026-11-23T00:30:00"), record(occurred_at="2026-13-01T00:00:00Z"),
                 record(occurred_at="2026-11-23"), record(occurred_at="2026-11-23T00:30:00.1234567Z"),
                 record(occurred_at="2026-11-23T00:30:00+00:60")]
        for value in cases:
            with self.subTest(value=repr(value)[:100]):
                self.assertEqual((await self.store.execute("put", value)).code, "memory.invalid")
        self.assertEqual((await self.store.execute("query", None, None, 0, 8))["records"], [])

    async def test_query_and_id_bounds(self):
        for args in [(None, None, True, 1), (None, None, -1, 1), (None, None, 2**63, 1),
                     (None, None, 0, 0), (None, None, 0, 9), (None, None, 0, True),
                     ([], None, 0, 1), (None, "unknown", 0, 1)]:
            self.assertEqual((await self.store.execute("query", *args)).code, "memory.invalid")
        self.assertEqual((await self.store.execute("get", 1)).code, "memory.invalid")
        self.assertIsInstance(await self.store.execute("put", record("x' OR 1=1 --")), dict)
        self.assertEqual((await self.store.execute("get", "' OR 1=1 --")).code, "memory.not_found")

    async def test_record_size_exact_boundary(self):
        import json
        from nymph_toolkit.subsystems.memory._records import canonical
        value = record(content="a")
        _, payload = canonical(value)
        value["content"] += "a" * (4096 - len(payload))
        self.assertEqual(len(canonical(value)[1]), 4096)
        self.assertIsInstance(await self.store.execute("put", value), dict)
        value["content"] += "a"
        self.assertEqual((await self.store.execute("put", value)).code, "memory.invalid")
        self.assertLess(len(json.dumps(await self.store.execute("query", None, None, 0, 8))), 65536)

    async def test_database_lock_is_bounded_and_loop_remains_responsive(self):
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            pending = asyncio.create_task(self.store.execute("put", record()))
            await asyncio.sleep(.05)
            self.assertFalse(pending.done())
            self.assertIsInstance(await self.store.execute("get", "event-1"), TemporaryUnavailable)
            result = await asyncio.wait_for(pending, 3)
            self.assertEqual(result.code, "memory.storage")
        finally:
            connection.rollback()
            connection.close()
        self.assertEqual((await self.store.execute("get", "event-1")).code, "memory.not_found")
        self.assertIsInstance(await self.store.execute("put", record()), dict)

    async def test_failure_after_insert_rolls_back_without_success(self):
        with patch.object(Store, "_record", side_effect=sqlite3.OperationalError("simulated I/O")):
            result = await self.store.execute("put", record())
        self.assertEqual(result.code, "memory.storage")
        self.assertEqual((await self.store.execute("get", "event-1")).code, "memory.not_found")
        self.assertIsInstance(await self.store.execute("put", record()), dict)

    async def test_corrupted_record_is_storage_failure_not_invalid_input(self):
        await self.store.execute("put", record())
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("UPDATE records SET payload = '{}' WHERE record_id = 'event-1'")
            connection.commit()
        finally:
            connection.close()
        self.assertEqual((await self.store.execute("get", "event-1")).code, "memory.storage")

    async def test_cancel_and_stop_wait_for_worker_then_release_file(self):
        entered, release = threading.Event(), threading.Event()
        original = self.store._put
        def slow(value):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test failed to release worker")
            return original(value)
        with patch.object(self.store, "_put", slow):
            operation = asyncio.create_task(self.store.execute("put", record()))
            async with asyncio.timeout(3):
                while not entered.is_set():
                    await asyncio.sleep(.005)
            operation.cancel()
            await asyncio.sleep(.01)
            operation.cancel()
            stopping = asyncio.create_task(self.store.stop())
            await asyncio.sleep(.01)
            self.assertFalse(operation.done())
            self.assertFalse(stopping.done())
            self.assertIsInstance(await self.store.execute("get", "event-1"), TemporaryUnavailable)
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await operation
            await stopping
        self.assertIsNone(self.store.pool)
        self.store = Store(self.path)
        await self.store.start()
        self.assertEqual((await self.store.execute("get", "event-1"))["record_id"], "event-1")

    async def test_usage_notifications_and_stop_are_idempotent(self):
        values = []
        async def change(active):
            values.append(active)
        self.store.changed = change
        await self.store.execute("put", record())
        self.assertEqual(values, [1, 0])
        await self.store.stop()
        await self.store.stop()
        self.assertIsInstance(await self.store.execute("get", "event-1"), TemporaryUnavailable)

    async def test_input_is_copied_before_admission_notification_yields(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def change(active):
            if active:
                entered.set()
                await release.wait()
        self.store.changed = change
        value = record()
        task = asyncio.create_task(self.store.execute("put", value))
        await entered.wait()
        value["content"] = "mutated while awaiting"
        release.set()
        self.assertEqual((await task)["content"], record()["content"])


class MemoryStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreign_unknown_and_corrupt_database_unchanged(self):
        for variant in ("foreign", "version", "corrupt", "schema"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "memory.db"
                if variant == "corrupt":
                    path.write_bytes(b"not sqlite")
                else:
                    connection = sqlite3.connect(path)
                    try:
                        connection.execute("CREATE TABLE unrelated (x)")
                        if variant in ("version", "schema"):
                            connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                            connection.execute("PRAGMA user_version = " + ("99" if variant == "version" else "1"))
                        connection.commit()
                    finally:
                        connection.close()
                before = path.read_bytes()
                store = Store(str(path))
                with self.assertRaises((ValueError, sqlite3.Error)):
                    await store.start()
                await store.stop()
                self.assertIsNone(store.pool)
                self.assertEqual(path.read_bytes(), before)

    async def test_bad_path_and_partial_start_release_worker(self):
        with self.assertRaises(ValueError):
            Store("relative.sqlite")
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "missing" / "memory.db"))
            with self.assertRaises(sqlite3.OperationalError):
                await store.start()
            self.assertIsNone(store.pool)
            await store.stop()
