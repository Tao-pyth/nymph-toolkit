"""Real-file tests for unlimited buffering, owned I/O, and admission during rescue."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import BindingKey, BindingRecord, ContractKey, RuntimeState, StorageCorruptionError, StorageError, StorageFailure
from nymph_toolkit.core import FileStore, _storage_io, storage


class FileStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ntk-store-test-")
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.store = FileStore(base / "primary", base / "archive", retention=timedelta(days=2),
                               batch_size=100, flush_interval=60)
        self.record = BindingRecord(BindingKey("a", ContractKey("read", "1")), "b")
        self.now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)

    async def asyncTearDown(self):
        try:
            await self.store.stop()
        except StorageFailure:
            pass
        leaked = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()
                  and not t.done() and t.get_name().startswith("ntk-")]
        self.assertEqual(leaked, [])

    async def entered(self, event):
        self.assertTrue(await asyncio.to_thread(event.wait, 5), "disk operation did not start")

    def history(self):
        return [json.loads(line) for path in sorted(self.store._disk.root.glob("history-*.jsonl"))
                for line in path.read_text(encoding="utf-8").splitlines()]

    def old_history(self):
        self.store._disk.initialize()
        event = {"format": "ntk.history.v1", "run_id": "a" * 32, "sequence": 1,
                 "at": (self.now - timedelta(days=10)).isoformat(), "kind": "old", "data": {}}
        batch = self.store._disk.history_batch((event,))
        batch.write()
        return next(iter(batch.protected))

    async def test_startup_buffer_snapshots_all_changes_and_stop_drains(self):
        data = {"nested": [1]}
        self.store.append("before_start", data)
        data["nested"].append(2)
        await self.store.start()
        for i in range(7):
            self.store.append("usage", {"active": i})
        await self.store.save_bindings((self.record,))
        await self.store.stop()
        events = self.history()
        self.assertEqual([event["sequence"] for event in events], list(range(1, 9)))
        self.assertEqual(events[0]["data"], {"nested": [1]})
        self.assertEqual(self.store._disk.load_bindings(), (self.record,))
        self.assertEqual(self.store.unsaved_events, 0)
        self.assertEqual(self.store.state, RuntimeState.STOPPED)
        with self.assertRaises(StorageError):
            self.store.append("late", {})
        with self.assertRaises(StorageError):
            await self.store.start()

    async def test_backlog_does_not_pause_admission_or_block_event_loop(self):
        self.store._batch_size = 1
        started, release = threading.Event(), threading.Event()
        original = _storage_io._append
        def slow(path, baseline, content):
            started.set()
            if not release.wait(5):
                raise OSError("test gate timed out")
            original(path, baseline, content)
        await self.store.start()
        with patch.object(_storage_io, "_append", side_effect=slow):
            try:
                self.store.append("first", {})
                await self.entered(started)
                for i in range(250):
                    self.store.append("usage", {"active": i})
                # Much larger than a disk batch, yet admission and loop activity continue.
                self.assertEqual(self.store.unsaved_events, 251)
                self.assertTrue(self.store.admitting)
                await asyncio.wait_for(asyncio.sleep(0), 1)
                await self.store.wait_ready()
            finally:
                release.set()
            await self.store.flush()
        self.assertEqual(len(self.history()), 251)

    async def test_low_volume_is_written_by_interval_without_an_explicit_flush(self):
        self.store._interval = 0.01
        written = threading.Event()
        original = _storage_io._append
        def observe(*args):
            original(*args)
            written.set()
        await self.store.start()
        with patch.object(_storage_io, "_append", side_effect=observe):
            self.store.append("one", {})
            await self.entered(written)
            await self.store.stop()
        self.assertEqual(len(self.history()), 1)

    async def test_periods_are_utc_and_flush_preserves_sequence(self):
        await self.store.start()
        with patch.object(storage, "_utcnow", return_value=self.now):
            self.store.append("today", {})
        with patch.object(storage, "_utcnow", return_value=self.now + timedelta(days=1)):
            self.store.append("tomorrow", {})
        await self.store.flush()
        self.assertEqual(len(list(self.store._disk.root.glob("history-*.jsonl"))), 2)
        self.assertEqual([e["sequence"] for e in self.history()], [1, 2])

    async def test_settings_failure_pauses_all_admission_and_rescues_once(self):
        old = self.old_history()
        content = old.read_bytes()
        original_save = self.store._disk.save_bindings
        original_archive = self.store._disk.archive_old
        rescue_entered, release = threading.Event(), threading.Event()
        def full_until_archived(records):
            if old.exists():
                raise OSError("primary full")
            original_save(records)
        def hold_rescue(*args):
            rescue_entered.set()
            if not release.wait(5):
                raise OSError("test gate timed out")
            return original_archive(*args)
        await self.store.start()
        with patch.object(storage, "_utcnow", return_value=self.now), \
             patch.object(self.store._disk, "save_bindings", side_effect=full_until_archived) as saves, \
             patch.object(self.store._disk, "archive_old", side_effect=hold_rescue) as rescues:
            task = asyncio.create_task(self.store.save_bindings((self.record,)))
            try:
                await self.entered(rescue_entered)
                self.assertFalse(self.store.admitting)
                self.store.append("in_flight_change", {"active": 0})
                ready = asyncio.create_task(self.store.wait_ready())
                await asyncio.sleep(0)
                self.assertFalse(ready.done())
            finally:
                release.set()
            await task
            await asyncio.wait_for(ready, 5)
            self.assertEqual(saves.call_count, 2)
            self.assertEqual(rescues.call_count, 1)
        self.assertTrue(self.store.admitting)
        self.assertFalse(old.exists())
        self.assertEqual((self.store._disk.archive / old.name).read_bytes(), content)
        self.assertEqual(await self.store.load_bindings(), (self.record,))
        await self.store.flush()
        self.assertEqual(len(self.history()), 1)

    async def test_history_failure_uses_same_rescue_and_protects_current_batch(self):
        old = self.old_history()
        original = _storage_io._append
        def fail_until_free(*args):
            if old.exists():
                raise OSError("full")
            original(*args)
        await self.store.start()
        # A backdated pending batch is protected even though it is old enough to archive.
        with patch.object(storage, "_utcnow", return_value=self.now - timedelta(days=6)):
            self.store.append("pending", {"value": 1})
        with patch.object(storage, "_utcnow", return_value=self.now), \
             patch.object(_storage_io, "_append", side_effect=fail_until_free) as writes:
            await self.store.flush()
            self.assertEqual(writes.call_count, 2)
        self.assertTrue(self.store.admitting)
        self.assertEqual([e["kind"] for e in self.history()], ["pending"])
        self.assertEqual(len(list(self.store._disk.archive.glob("history-*.jsonl"))), 1)

    async def test_unrecoverable_history_reports_late_changes_and_never_exports_buffer(self):
        self.store._batch_size = 1
        await self.store.start()
        with patch.object(_storage_io, "_append", side_effect=OSError("still full")) as writes:
            self.store.append("unsaved", {})
            failure = await asyncio.wait_for(self.store.wait_failure(), 5)
            self.assertIsInstance(failure, StorageFailure)
            self.assertEqual(writes.call_count, 2)
            self.assertFalse(self.store.admitting)
            self.store.append("final_module_state", {"active": 0})
            self.assertEqual(failure.unsaved_events, 2)
            self.assertIn("unsaved_events=2", str(failure))
            await self.store.stop()
            self.assertEqual(writes.call_count, 2)
        self.assertFalse(self.store._disk.archive.exists())
        self.assertEqual(self.store.state, RuntimeState.FAILED)

    async def test_failed_archive_preserves_source_and_reports_pending_configuration(self):
        old = self.old_history()
        content = old.read_bytes()
        await self.store.start()
        with patch.object(storage, "_utcnow", return_value=self.now), \
             patch.object(self.store._disk, "save_bindings", side_effect=OSError("full")) as saves, \
             patch.object(_storage_io.shutil, "copyfileobj", side_effect=OSError("reserve full")):
            with self.assertRaises(StorageFailure) as raised:
                await self.store.save_bindings((self.record,))
            self.assertEqual(saves.call_count, 1)
        self.assertTrue(raised.exception.pending_configuration)
        self.assertEqual(old.read_bytes(), content)
        self.assertFalse((self.store._disk.archive / old.name).exists())
        self.assertFalse(self.store._disk.settings.exists())

    async def test_corrupt_configuration_is_preserved_without_capacity_rescue(self):
        self.store._disk.initialize()
        self.store._disk.settings.write_bytes(b"{invalid")
        await self.store.start()
        with patch.object(self.store._disk, "archive_old") as rescue:
            with self.assertRaises(StorageFailure) as raised:
                await self.store.load_bindings()
        self.assertIsInstance(raised.exception.cause, StorageCorruptionError)
        rescue.assert_not_called()
        self.assertEqual(self.store._disk.settings.read_bytes(), b"{invalid")

    async def test_repeated_caller_cancellation_waits_for_configuration_io(self):
        started, release = threading.Event(), threading.Event()
        original = self.store._disk.save_bindings
        def slow(records):
            started.set()
            if not release.wait(5):
                raise OSError("test gate timed out")
            original(records)
        await self.store.start()
        with patch.object(self.store._disk, "save_bindings", side_effect=slow):
            task = asyncio.create_task(self.store.save_bindings((self.record,)))
            try:
                await self.entered(started)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(await self.store.load_bindings(), (self.record,))

    async def test_cancelled_stop_waits_for_final_disk_write(self):
        started, release = threading.Event(), threading.Event()
        original = _storage_io._append
        def slow(*args):
            started.set()
            if not release.wait(5):
                raise OSError("test gate timed out")
            original(*args)
        await self.store.start()
        self.store.append("pending", {})
        with patch.object(_storage_io, "_append", side_effect=slow):
            task = asyncio.create_task(self.store.stop())
            try:
                await self.entered(started)
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        await self.store.stop()
        self.assertEqual(self.store.state, RuntimeState.STOPPED)
        self.assertEqual(len(self.history()), 1)

    async def test_first_failure_during_stop_is_reported(self):
        await self.store.start()
        self.store.append("pending", {})
        with patch.object(_storage_io, "_append", side_effect=OSError("stop write failed")):
            with self.assertRaises(StorageFailure):
                await self.store.stop()
        self.assertEqual(self.store.failure.unsaved_events, 1)

    async def test_invalid_input_does_not_enqueue_or_poison_the_store(self):
        for bad in (0, -1, True):
            with self.assertRaises(ValueError):
                FileStore(self.store._disk.root, self.store._disk.archive, retention=timedelta(0),
                          batch_size=bad, flush_interval=1)
        for bad in (0, -1, True, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                FileStore(self.store._disk.root, self.store._disk.archive, retention=timedelta(0),
                          batch_size=1, flush_interval=bad)
        await self.store.start()
        with self.assertRaises(ValueError):
            self.store.append("usage", {"invalid": float("nan")})
        with self.assertRaises(TypeError):
            self.store.append("usage", {"invalid": object()})
        with self.assertRaises(ValueError):
            await self.store.save_bindings((self.record, self.record))
        self.assertEqual(self.store.unsaved_events, 0)
        self.assertTrue(self.store.admitting)


if __name__ == "__main__":
    unittest.main()
