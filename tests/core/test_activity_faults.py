"""Activity ownership across actual connection and file-storage failures."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import (
    ActivityAdmissionError, ActivityFinishReason, ActivityKey, ActivityRequest,
    ActivityState, ModuleExecutionState, NoticeKind, OperatingState, RuntimeFailure,
    RuntimeState, StorageFailure, Usage,
)
from nymph_toolkit.core import FileStore, Runtime
from nymph_toolkit.core import _storage_io
from tests.core import test_activity_group as group_tests

CONTRACT = group_tests.CONTRACT


class ActivityFaultTests(unittest.IsolatedAsyncioTestCase):
    configure = group_tests.ActivityGroupTests.configure
    asyncTearDown = group_tests.ActivityGroupTests.asyncTearDown

    async def test_requester_handles_interruption_without_stopping_unrelated_activity_or_replay(self):
        async def nymph(manager, links, trace, closed):
            binding = await links.bind("nymph", CONTRACT, "provider", wait_timeout=1)
            entered = [asyncio.Event() for _ in range(3)]
            counts = [0, 0, 0]
            keys = [ActivityKey("nymph", "one"), ActivityKey("nymph", "two"), ActivityKey("provider", "unrelated")]
            for index, key in enumerate(keys):
                async def execute(context, index=index):
                    counts[index] += 1
                    entered[index].set()
                    await context.wait_for_finish()
                    await asyncio.sleep(0)
                    trace.append((context.request.key.activity_id, "cleaned"))
                manager.submit(ActivityRequest(key, "作業", None, timedelta(hours=1)), execute)
            await asyncio.gather(*(event.wait() for event in entered))
            usage = Usage(OperatingState.STOPPED, False, 0, 1)
            links.publish_usage("provider", usage, contracts={CONTRACT: usage})
            notice_id = links.report_link_error(binding.key, OSError("provider stopped"))
            notice = await links.next_notice("nymph")
            self.assertEqual(notice.kind, NoticeKind.INTERRUPT)
            self.assertEqual(links.module_state("nymph"), ModuleExecutionState.INTERRUPTING)
            # The requester explicitly cleans all its activities before acknowledging.
            for snapshot in manager.activities(requester_id="nymph"):
                manager.request_finish(snapshot.request.key, reason=ActivityFinishReason.CONNECTION_INTERRUPTION)
            results = await asyncio.gather(*(manager.wait(key) for key in keys[:2]))
            self.assertTrue(all(result.state == ActivityState.STOPPED for result in results))
            self.assertEqual(manager.snapshot(keys[2]).state, ActivityState.RUNNING)
            self.assertTrue(links.acknowledge_interruption("nymph", notice_id))
            await links.health_check(module_ids=("provider",))
            self.assertEqual(counts, [1, 1, 1])
            ready = Usage(OperatingState.RUNNING, True, 0, 1)
            links.publish_usage("provider", ready, contracts={CONTRACT: ready})
            await links.health_check(module_ids=("provider",))
            prepared = await links.prepare(binding.key, wait_timeout=1)
            self.assertEqual(await prepared.acall("echo", "new request"), "new request")
            self.assertEqual(counts, [1, 1, 1])
            manager.request_finish(keys[2])
            await manager.wait(keys[2])
        group, *_ = self.configure(nymph)
        runtime = Runtime(group)
        await runtime.start()
        await asyncio.wait_for(runtime.wait(), 3)
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_recoverable_file_failure_pauses_admission_but_records_activity_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            store = FileStore(base / "primary", base / "archive", retention=timedelta(days=7),
                              batch_size=1000, flush_interval=10)
            entered, release = threading.Event(), threading.Event()
            original_append, original_archive = _storage_io._append, store._disk.archive_old
            writes = 0
            def write(*args):
                nonlocal writes
                writes += 1
                if writes == 1:
                    raise OSError("temporary storage failure")
                return original_append(*args)
            def rescue(*args):
                entered.set()
                if not release.wait(5):
                    raise AssertionError("rescue gate timed out")
                return original_archive(*args)
            async def nymph(manager, links, trace, closed):
                started = asyncio.Event()
                async def execute(context):
                    started.set()
                    await context.wait_for_finish()
                    return "cleaned"
                request = ActivityRequest(ActivityKey("nymph", "active"), "作業", None, timedelta(hours=1))
                manager.submit(request, execute)
                await started.wait()
                with patch.object(_storage_io, "_append", side_effect=write), \
                     patch.object(store._disk, "archive_old", side_effect=rescue) as rescues:
                    flushing = asyncio.create_task(store.flush())
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        self.assertFalse(store.admitting)
                        with self.assertRaises(ActivityAdmissionError):
                            manager.submit(ActivityRequest(ActivityKey("nymph", "rejected"), "新規", None,
                                                           timedelta(hours=1)), execute)
                        manager.request_finish(request.key)
                        result = await manager.wait(request.key)
                        self.assertEqual(result.state, ActivityState.STOPPED)
                    finally:
                        release.set()
                        await flushing
                    self.assertTrue(store.admitting)
                    self.assertEqual(rescues.call_count, 1)
            group, *_ = self.configure(nymph, store=store)
            runtime = Runtime(group)
            await runtime.start()
            await asyncio.wait_for(runtime.wait(), 5)
            records = [json.loads(line) for path in (base / "primary").glob("history-*.jsonl")
                       for line in path.read_text(encoding="utf-8").splitlines()]
            activity = [record["data"] for record in records if record["kind"] == "activity_v06_state_changed"]
            self.assertEqual(activity[-1]["state"], "stopped")
            self.assertEqual(activity[-1]["result"], "cleaned")
            self.assertEqual(store.unsaved_events, 0)

    async def test_unrecoverable_storage_stops_active_work_and_reports_final_unsaved_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            store = FileStore(base / "primary", base / "archive", retention=timedelta(days=7),
                              batch_size=1000, flush_interval=10)
            started, cleaned = asyncio.Event(), asyncio.Event()
            key = ActivityKey("nymph", "active")
            async def nymph(manager, links, trace, closed):
                async def execute(context):
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        self.assertNotIn("provider", closed)
                        cleaned.set()
                manager.submit(ActivityRequest(key, "作業", None, timedelta(hours=1)), execute)
                await asyncio.Event().wait()
            group, manager, links, _, trace, closed = self.configure(nymph, store=store)
            runtime = Runtime(group)
            await runtime.start()
            await asyncio.wait_for(started.wait(), 2)
            with patch.object(_storage_io, "_append", side_effect=OSError("persistent failure")) as writes:
                with self.assertRaises(StorageFailure):
                    await store.flush()
                with self.assertRaises(RuntimeFailure):
                    await asyncio.wait_for(runtime.wait(), 3)
                self.assertEqual(writes.call_count, 2)
            self.assertTrue(cleaned.is_set())
            self.assertEqual(manager.snapshot(key).state, ActivityState.STOPPED)
            self.assertEqual(closed, {"nymph", "provider"})
            self.assertEqual(store.failure.unsaved_events, store.unsaved_events)
            self.assertGreater(store.unsaved_events, 0)
            final = [record["data"] for record in store._buffer if record["kind"] == "activity_v06_state_changed"][-1]
            self.assertEqual(final["state"], "stopped")
            self.assertEqual(final["finish_reason"], "runtime")

