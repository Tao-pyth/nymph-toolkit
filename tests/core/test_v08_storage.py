"""A08 storage rescue and executor reports retain distinct acceptance boundaries."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import ActivityAdmissionError, ActivityState, BindingKey, Placement, RuntimeFailure
from nymph_toolkit.core import _storage_io
from tests.core import test_v08_integration as baseline
from tests.doubles.scenario import KEY, invoke, make_group, until


class StorageIntegrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.IntegrationTests.asyncSetUp
    asyncTearDown = baseline.IntegrationTests.asyncTearDown
    create = baseline.IntegrationTests.create
    request = baseline.IntegrationTests.request

    def old_history(self, store):
        store._disk.initialize()
        record = {"format": "ntk.history.v1", "run_id": "a" * 32, "sequence": 1,
                  "at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                  "kind": "previous_run_marker", "data": {"preserve": True}}
        batch = store._disk.history_batch((record,))
        batch.write()
        path = next(iter(batch.protected))
        return path, path.read_bytes()

    async def prepare(self):
        group, runtime, root = self.create(requester=Placement.PROCESS, provider=Placement.PROCESS)
        store = group.connections.store
        store._interval, store._batch_size = 60, 10000
        old, contents = self.old_history(store)
        await runtime.start()
        await invoke(group, "requester", "connect", "provider")
        request = self.request()
        group.activities.submit_remote(request, "provider", "work")
        await until(lambda: group.activities.snapshot(request.key).state == ActivityState.RUNNING)
        await store.flush()
        return group, runtime, root, store, request, old, contents

    async def test_rescue_preserves_remote_final_report_and_blocks_only_new_admission(self):
        group, runtime, root, store, request, old, contents = await self.prepare()
        entered, release = threading.Event(), threading.Event()
        original_archive, original_append = store._disk.archive_old, _storage_io._append
        def full_until_archived(*args):
            if old.exists():
                raise OSError("injected primary full")
            return original_append(*args)
        def rescue(*args):
            entered.set()
            if not release.wait(5):
                raise OSError("test rescue gate timed out")
            return original_archive(*args)
        store.append("trigger", {})
        with patch.object(_storage_io, "_append", side_effect=full_until_archived), \
             patch.object(store._disk, "archive_old", side_effect=rescue) as rescues:
            flushing = asyncio.create_task(store.flush())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                self.assertFalse(store.admitting)
                with self.assertRaises(ActivityAdmissionError):
                    group.activities.submit_remote(self.request("rejected"), "provider", "work", {"complete": True})
                group.activities.request_finish(request.key)
                ended = await asyncio.wait_for(group.activities.wait(request.key), 3)
                self.assertEqual(ended.state, ActivityState.STOPPED)
                self.assertTrue(ended.cleanup_confirmed)
                self.assertGreater(store.unsaved_events, 1)
                self.assertEqual(runtime.state.value, "running")
            finally:
                release.set()
            await asyncio.wait_for(flushing, 5)
            await store.flush()
            self.assertEqual(rescues.call_count, 1)
        self.assertTrue(store.admitting)
        self.assertEqual(store.unsaved_events, 0)
        self.assertFalse(old.exists())
        self.assertEqual((store._disk.archive / old.name).read_bytes(), contents)
        events = [json.loads(line) for file in (root / "primary").glob("history-*.jsonl")
                  for line in file.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(e["kind"].startswith("activity_v07_") and e["data"].get("state") == "stopped" for e in events))

    async def test_unrecoverable_save_includes_final_reports_and_preserves_old_data(self):
        for archive_fails in (False, True):
            with self.subTest(archive_fails=archive_fails):
                group, runtime, _, store, request, old, contents = await self.prepare()
                entered, release = threading.Event(), threading.Event()
                original = store._disk.archive_old
                def rescue(*args):
                    entered.set()
                    if not release.wait(5):
                        raise OSError("test rescue gate timed out")
                    if archive_fails:
                        raise OSError("injected archive unavailable")
                    return original(*args)
                store.append("unsaved_trigger", {})
                with patch.object(_storage_io, "_append", side_effect=OSError("injected primary unavailable")), \
                     patch.object(store._disk, "archive_old", side_effect=rescue):
                    flushing = asyncio.create_task(store.flush())
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                        group.activities.request_finish(request.key)
                        ended = await asyncio.wait_for(group.activities.wait(request.key), 3)
                        self.assertTrue(ended.cleanup_confirmed)
                    finally:
                        release.set()
                    await asyncio.gather(flushing, return_exceptions=True)
                    with self.assertRaises(RuntimeFailure):
                        await asyncio.wait_for(runtime.wait(), 8)
                self.assertIsNotNone(store.failure)
                self.assertEqual(store.failure.unsaved_events, len(store._buffer))
                self.assertGreater(store.failure.unsaved_events, 1)
                self.assertTrue(any(r["kind"].startswith("activity_v07_") and r["data"].get("state") == "stopped"
                                    for r in store._buffer))
                preserved = old if archive_fails else store._disk.archive / old.name
                self.assertEqual(preserved.read_bytes(), contents)
                self.assertFalse(store.admitting)
                self.assertFalse(any(s.process.returncode is None for s in group.modules.values()))

    async def test_slow_healthy_save_keeps_accepting_and_does_not_lose_child_completion(self):
        group, _, _, store, request, _, _ = await self.prepare()
        entered, release = threading.Event(), threading.Event()
        original = _storage_io._append
        def slow(*args):
            entered.set()
            if not release.wait(5):
                raise OSError("test write gate timed out")
            return original(*args)
        store.append("slow_write", {})
        with patch.object(_storage_io, "_append", side_effect=slow):
            flushing = asyncio.create_task(store.flush())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                self.assertTrue(store.admitting)
                await invoke(group, "requester", "activity_cycle", "provider", "new-during-backlog")
                group.activities.request_finish(request.key)
                self.assertTrue((await asyncio.wait_for(group.activities.wait(request.key), 3)).cleanup_confirmed)
                self.assertGreater(store.unsaved_events, 1)
                self.assertTrue(store.admitting)
            finally:
                release.set()
            await asyncio.wait_for(flushing, 5)
        await store.flush()
        self.assertEqual(store.unsaved_events, 0)

    async def test_new_runtime_preserves_history_and_requires_nymph_reregistration(self):
        group, runtime, root = self.create(requester=Placement.PROCESS, provider=Placement.PROCESS)
        await runtime.start()
        await invoke(group, "requester", "connect", "provider")
        await invoke(group, "requester", "activity_cycle", "provider", "same-id", True)
        old_generation = group.process("provider").generation
        await runtime.stop()
        originals = {p: p.read_bytes() for p in (root / "primary").glob("history-*.jsonl")}
        next_group, next_runtime = make_group(root, Placement.PROCESS, Placement.PROCESS)
        self.runs.append((next_group, next_runtime))
        await next_runtime.start()
        self.assertNotEqual(next_group.process("provider").generation, old_generation)
        self.assertFalse(next_group.activities._activities)
        self.assertEqual((await invoke(next_group, "provider", "metrics"))["work_started"], 0)
        self.assertEqual(next_group.connections.connection(BindingKey("requester", KEY)).provider_id, "provider")
        history = await next_group.activities.history("requester")
        self.assertTrue(history.records)
        self.assertFalse(history.issues)
        await invoke(next_group, "requester", "activity_cycle", "provider", "same-id")
        self.assertEqual((await invoke(next_group, "provider", "metrics"))["work_started"], 1)
        for path, contents in originals.items():
            self.assertEqual(path.read_bytes(), contents)
