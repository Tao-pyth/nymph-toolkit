"""Activity controls retain resource ownership across real storage and link faults."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import (
    ActivityChange, ActivityFinishReason, ActivityKey, ActivityRequest, ActivityState,
    OperatingState, RuntimeFailure, RuntimeState, StorageFailure, Usage,
)
from nymph_toolkit.core import FileStore, Runtime
from nymph_toolkit.core import _storage_io
from tests.core import test_activity_group as group_tests, test_task_manager as baseline


class ActivityV06FaultTests(unittest.IsolatedAsyncioTestCase):
    configure = group_tests.ActivityGroupTests.configure
    asyncTearDown = group_tests.ActivityGroupTests.asyncTearDown

    def command(self, manager, key, operation, identity):
        return getattr(manager, "request_" + operation)(key, command_id=identity,
                    expected_revision=manager.snapshot(key).revision)

    async def test_all_waiting_states_are_collected_before_module_resources_on_repeated_stop(self):
        ready, cleanup_gate = asyncio.Event(), asyncio.Event()
        keys, cleaned = {}, set()
        async def nymph(manager, links, trace, closed):
            async def work(context):
                name = context.request.key.activity_id
                try:
                    while True:
                        await context.wait_for_control()
                        if name == "pausing":
                            await asyncio.Event().wait()
                        if await context.checkpoint() is not None:
                            break
                finally:
                    await cleanup_gate.wait()
                    self.assertEqual(closed, set())
                    cleaned.add(name)
            for name in ("paused", "resuming", "pausing", "busy"):
                key = keys[name] = ActivityKey("nymph", name)
                manager.submit(ActivityRequest(key, name, None, timedelta(hours=1)), work, supports_pause=True)
                await baseline.eventually(lambda: manager.snapshot(key).state == ActivityState.RUNNING)
                if name != "busy":
                    self.command(manager, key, "pause", "pause")
                    if name != "pausing":
                        await manager.wait_command(key, "pause")
            self.command(manager, keys["resuming"], "resume", "resume")
            future = keys["future"] = ActivityKey("nymph", "future")
            manager.submit(ActivityRequest(future, "future", datetime.now(timezone.utc) + timedelta(hours=1),
                                           timedelta(hours=1)), work)
            ready.set()
            await asyncio.Event().wait()
        group, manager, links, store, trace, closed = self.configure(nymph, max_running=2)
        runtime = Runtime(group)
        await runtime.start()
        await asyncio.wait_for(ready.wait(), 2)
        self.assertEqual(manager.snapshot(keys["resuming"]).state, ActivityState.RESUME_PENDING)
        stopping = asyncio.create_task(runtime.stop())
        for _ in range(5):
            await asyncio.sleep(0)
        stopping.cancel()
        await asyncio.sleep(0)
        stopping.cancel()
        cleanup_gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await stopping
        await asyncio.wait_for(runtime.wait(), 3)
        self.assertEqual(cleaned, {"paused", "resuming", "pausing", "busy"})
        self.assertTrue(all(manager.snapshot(k).state == ActivityState.STOPPED for k in keys.values()))
        self.assertEqual(manager._running_slots, 0)
        self.assertEqual(manager._ready, {})
        self.assertEqual(closed, {"nymph", "provider"})

    async def test_real_storage_rescue_refuses_new_changes_and_resume_but_allows_pause_and_pending_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            store = FileStore(base / "primary", base / "archive", retention=timedelta(days=7), batch_size=1000, flush_interval=10)
            entered, release = threading.Event(), threading.Event()
            original, archive = _storage_io._append, store._disk.archive_old
            writes = 0
            def append(*args):
                nonlocal writes
                writes += 1
                if writes == 1:
                    raise OSError("transient write failure")
                return original(*args)
            def rescue(*args):
                entered.set()
                if not release.wait(5):
                    raise AssertionError("rescue was not released")
                return archive(*args)
            async def nymph(manager, links, trace, closed):
                async def work(context):
                    while True:
                        await context.wait_for_control()
                        if await context.checkpoint() is not None:
                            return "cleaned"
                first, busy = ActivityKey("nymph", "first"), ActivityKey("nymph", "busy")
                for key in (first, busy):
                    manager.submit(ActivityRequest(key, "work", None, timedelta(hours=1)), work, supports_pause=True)
                    await baseline.eventually(lambda: manager.snapshot(key).state == ActivityState.RUNNING)
                    if key == first:
                        self.command(manager, key, "pause", "pause")
                        await manager.wait_command(key, "pause")
                self.command(manager, first, "resume", "accepted-before-failure")
                with patch.object(_storage_io, "_append", side_effect=append), patch.object(store._disk, "archive_old", side_effect=rescue):
                    flushing = asyncio.create_task(store.flush())
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        result = manager.change(first, ActivityChange(priority=3), command_id="edit",
                                                expected_revision=manager.snapshot(first).revision)
                        self.assertEqual(result.reason, "storage_unavailable")
                        self.command(manager, busy, "pause", "pause-during-rescue")
                        await manager.wait_command(busy, "pause-during-rescue")
                        self.assertEqual(self.command(manager, busy, "resume", "rejected").reason, "storage_unavailable")
                        self.assertEqual(manager.snapshot(first).state, ActivityState.RESUME_PENDING)
                    finally:
                        release.set()
                        await flushing
                await manager.wait_command(first, "accepted-before-failure")
                self.assertEqual(manager.snapshot(first).state, ActivityState.RUNNING)
                self.assertEqual(manager.snapshot(busy).state, ActivityState.PAUSED)
                for key in (first, busy):
                    manager.request_finish(key)
                    await manager.wait(key)
            group, *_ = self.configure(nymph, store=store, max_running=1)
            runtime = Runtime(group)
            await runtime.start()
            await asyncio.wait_for(runtime.wait(), 6)
            self.assertEqual(store.unsaved_events, 0)
            reader = FileStore(base / "primary", base / "archive", retention=timedelta(days=7), batch_size=100, flush_interval=10)
            await reader.start()
            try:
                self.assertFalse((await reader.read_activity_history("nymph")).issues)
            finally:
                await reader.stop()

    async def test_unrecoverable_storage_ends_paused_work_and_reports_final_control_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            store = FileStore(base / "primary", base / "archive", retention=timedelta(days=7), batch_size=1000, flush_interval=10)
            ready, cleaned = asyncio.Event(), asyncio.Event()
            key = ActivityKey("nymph", "paused")
            async def nymph(manager, links, trace, closed):
                async def work(context):
                    try:
                        await context.wait_for_control()
                        await context.checkpoint()
                    finally:
                        self.assertEqual(closed, set())
                        cleaned.set()
                manager.submit(ActivityRequest(key, "work", None, timedelta(hours=1)), work, supports_pause=True)
                await baseline.eventually(lambda: manager.snapshot(key).state == ActivityState.RUNNING)
                self.command(manager, key, "pause", "pause")
                await manager.wait_command(key, "pause")
                ready.set()
                await asyncio.Event().wait()
            group, manager, *_ = self.configure(nymph, store=store)
            runtime = Runtime(group)
            await runtime.start()
            await asyncio.wait_for(ready.wait(), 2)
            with patch.object(_storage_io, "_append", side_effect=OSError("persistent")):
                with self.assertRaises(StorageFailure):
                    await store.flush()
                with self.assertRaises(RuntimeFailure):
                    await asyncio.wait_for(runtime.wait(), 3)
            self.assertTrue(cleaned.is_set())
            self.assertEqual(manager.snapshot(key).state, ActivityState.STOPPED)
            self.assertEqual(store.failure.unsaved_events, store.unsaved_events)
            self.assertTrue(any(r["kind"] == "activity_v06_command" for r in store._buffer))

    async def test_connection_interruption_ends_paused_requester_only_without_automatic_resume(self):
        async def nymph(manager, links, trace, closed):
            binding = await links.bind("nymph", group_tests.CONTRACT, "provider", wait_timeout=1)
            counts = []
            async def work(context):
                counts.append(context.request.key)
                while True:
                    await context.wait_for_control()
                    if await context.checkpoint() is not None:
                        return "cleaned"
            owner, other = ActivityKey("nymph", "a"), ActivityKey("provider", "b")
            for key in (owner, other):
                manager.submit(ActivityRequest(key, "work", None, timedelta(hours=1)), work, supports_pause=True)
            await baseline.eventually(lambda: len(counts) == 2)
            self.command(manager, owner, "pause", "pause")
            await manager.wait_command(owner, "pause")
            notice_id = links.report_link_error(binding.key, OSError("link failure"))
            self.assertEqual(self.command(manager, owner, "resume", "blocked").reason, "requester_unavailable")
            manager.request_finish(owner, reason=ActivityFinishReason.CONNECTION_INTERRUPTION)
            await manager.wait(owner)
            links.acknowledge_interruption("nymph", notice_id)
            await links.health_check(module_ids=("provider",))
            self.assertEqual(manager.snapshot(owner).state, ActivityState.STOPPED)
            self.assertEqual(manager.snapshot(other).state, ActivityState.RUNNING)
            self.assertEqual(len(counts), 2)
            manager.request_finish(other)
            await manager.wait(other)
        group, *_ = self.configure(nymph)
        runtime = Runtime(group)
        await runtime.start()
        await asyncio.wait_for(runtime.wait(), 3)
