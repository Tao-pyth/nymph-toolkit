"""Actual saved activity evidence is returned to Nymph without automatic replay."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import (
    ActivityKey, ActivityRequest, ModuleAdvertisement, ModuleKind, ModuleSpec,
    OperatingState, RuntimeState, Usage,
)
from nymph_toolkit.core import Connections, FileStore, ModuleGroup, Runtime, TaskManager
from nymph_toolkit.core._activity_history import read_activity_history


class ActivityHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "primary"
        self.archive = self.base / "archive"

    def store(self):
        return FileStore(self.root, self.archive, retention=timedelta(days=7), batch_size=1000, flush_interval=10)

    async def asyncTearDown(self):
        remaining = [task.get_name() for task in asyncio.all_tasks()
                     if task is not asyncio.current_task() and task.get_name().startswith("ntk-")]
        self.assertEqual(remaining, [])
        self.temporary.cleanup()

    async def run_nymph(self, run):
        group = ModuleGroup()
        store = self.store()
        links = Connections(group, store)
        manager = TaskManager(links, clock_check_interval=0.01)
        class Nymph:
            async def start(self):
                links.publish_usage("nymph", Usage(OperatingState.RUNNING, True, 0, 1))
            async def run(self):
                return await run(manager)
            async def stop(self):
                links.publish_usage("nymph", Usage(OperatingState.STOPPED, False, 0, 1))
        group.register(ModuleSpec("nymph", ModuleKind.SUBSYSTEM), Nymph())
        links.declare(ModuleAdvertisement("nymph", "1", ()))
        group.attach_connections(links)
        group.attach_task_manager(manager)
        runtime = Runtime(group)
        await runtime.start()
        result = await asyncio.wait_for(runtime.wait(), 3)
        self.assertEqual(runtime.state, RuntimeState.STOPPED)
        return result["nymph"]

    async def save_completed(self):
        async def nymph(manager):
            async def execute(context):
                return {"observed": [1, 2]}
            request = ActivityRequest(ActivityKey("nymph", "a"), "調査", None, timedelta(hours=2))
            manager.submit(request, execute)
            return await manager.wait(request.key)
        return await self.run_nymph(nymph)

    async def read(self, requester="nymph"):
        store = self.store()
        await store.start()
        try:
            return await store.read_activity_history(requester)
        finally:
            await store.stop()

    async def test_restart_delivers_saved_history_and_only_nymph_registers_new_work(self):
        await self.save_completed()
        invoked = []
        async def nymph(manager):
            history = await manager.history("nymph")
            self.assertFalse(history.issues)
            self.assertEqual([record.data["state"] for record in history.records], ["pending", "running", "completed"])
            self.assertEqual(manager.activities(), ())
            await asyncio.sleep(0)
            self.assertEqual(invoked, [])
            async def execute(context):
                invoked.append(context.request.key)
                return "new decision"
            request = ActivityRequest(ActivityKey("nymph", "a"), "再調査", None, timedelta(minutes=1))
            manager.submit(request, execute)
            result = await manager.wait(request.key)
            self.assertEqual(result.result, "new decision")
            return len(history.records)
        self.assertEqual(await self.run_nymph(nymph), 3)
        self.assertEqual(len(invoked), 1)

    async def test_current_run_and_other_requester_records_are_excluded(self):
        await self.save_completed()
        async def nymph(manager):
            before = await manager.history("nymph")
            async def execute(context):
                return None
            request = ActivityRequest(ActivityKey("nymph", "new"), "今回", None, timedelta(minutes=1))
            manager.submit(request, execute)
            await manager.wait(request.key)
            await manager.store.flush()
            after = await manager.history("nymph")
            self.assertEqual(before, after)
        await self.run_nymph(nymph)
        self.assertEqual((await self.read("another")).records, ())

    async def test_unfinished_historical_activity_is_evidence_not_a_current_task(self):
        await self.save_completed()
        path = next(self.root.glob("history-*.jsonl"))
        # Simulate an abrupt exit: only persisted records up to RUNNING survived.
        lines = path.read_bytes().splitlines(keepends=True)
        through_running = next(i for i, line in enumerate(lines)
                               if json.loads(line)["kind"] == "activity_state_changed"
                               and json.loads(line)["data"]["state"] == "running")
        path.write_bytes(b"".join(lines[:through_running + 1]))
        async def nymph(manager):
            history = await manager.history("nymph")
            self.assertFalse(history.issues)
            self.assertEqual(history.records[-1].data["state"], "running")
            self.assertEqual(manager.activities(), ())
        await self.run_nymph(nymph)

    async def test_archive_copies_are_deduplicated_and_conflicts_are_not_silently_chosen(self):
        await self.save_completed()
        path = next(self.root.glob("history-*.jsonl"))
        self.archive.mkdir()
        archived = self.archive / path.name
        shutil.copyfile(path, archived)
        original = path.read_bytes()
        history = await self.read()
        self.assertEqual(len(history.records), 3)
        self.assertFalse(history.issues)
        lines = [json.loads(line) for line in original.splitlines()]
        terminal = next(record for record in lines if record["kind"] == "activity_state_changed" and record["data"]["state"] == "completed")
        terminal["data"]["result"] = "conflict"
        archived.write_text("".join(json.dumps(record) + "\n" for record in lines), encoding="utf-8")
        conflict_bytes = archived.read_bytes()
        history = await self.read()
        self.assertEqual(len(history.records), 2)
        self.assertTrue(any("Conflicting" in issue.message for issue in history.issues))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(archived.read_bytes(), conflict_bytes)

    async def test_broken_and_partial_lines_are_reported_and_never_repaired(self):
        await self.save_completed()
        path = next(self.root.glob("history-*.jsonl"))
        original = path.read_bytes() + b'{"format":"unknown"}\n' + b'{"unfinished":'
        path.write_bytes(original)
        history = await self.read()
        self.assertEqual(len(history.records), 3)
        self.assertEqual(len(history.issues), 2)
        self.assertTrue(any("Incomplete" in issue.message for issue in history.issues))
        self.assertEqual(path.read_bytes(), original)

    async def test_invalid_state_evidence_and_unknown_activity_kind_are_reported(self):
        await self.save_completed()
        path = next(self.root.glob("history-*.jsonl"))
        original = path.read_bytes()
        lines = [json.loads(line) for line in original.splitlines()]
        terminal = next(record for record in lines if record["kind"] == "activity_state_changed" and record["data"]["state"] == "completed")
        terminal["data"]["started_at"] = None
        path.write_text("".join(json.dumps(record) + "\n" for record in lines), encoding="utf-8")
        history = await self.read()
        self.assertEqual(len(history.records), 2)
        self.assertTrue(any("inconsistent" in issue.message for issue in history.issues))
        terminal["kind"] = "activity_future_v2"
        path.write_text("".join(json.dumps(record) + "\n" for record in lines), encoding="utf-8")
        history = await self.read()
        self.assertTrue(any("Unknown activity" in issue.message for issue in history.issues))

    async def test_history_read_failure_reports_a_problem_without_running_write_rescue(self):
        await self.save_completed()
        path = next(self.root.glob("history-*.jsonl"))
        store = self.store()
        await store.start()
        original_open = Path.open
        def open_path(candidate, *args, **kwargs):
            if candidate == path:
                raise PermissionError("history unavailable")
            return original_open(candidate, *args, **kwargs)
        try:
            with patch.object(Path, "open", open_path), patch.object(store._disk, "archive_old") as rescue:
                history = await store.read_activity_history("nymph")
                self.assertEqual(len(history.issues), 1)
                self.assertIn("unavailable", history.issues[0].message)
                rescue.assert_not_called()
                self.assertTrue(store.admitting)
                self.assertIsNone(store.failure)
        finally:
            await store.stop()

    async def test_read_cancellation_keeps_disk_work_owned_until_stop_can_finish(self):
        await self.save_completed()
        store = self.store()
        await store.start()
        entered, gate = threading.Event(), threading.Event()
        def delayed(*args):
            entered.set()
            if not gate.wait(5):
                raise AssertionError("test did not release history read")
            return read_activity_history(*args)
        with patch("nymph_toolkit.core.storage.read_activity_history", delayed):
            reading = asyncio.create_task(store.read_activity_history("nymph"))
            stopping = None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                reading.cancel()
                await asyncio.sleep(0)
                reading.cancel()
                stopping = asyncio.create_task(store.stop())
                await asyncio.sleep(0)
                self.assertFalse(reading.done())
                self.assertFalse(stopping.done())
            finally:
                gate.set()
                with self.assertRaises(asyncio.CancelledError):
                    await reading
                if stopping is not None:
                    await stopping
                else:
                    await store.stop()

    async def test_history_observations_are_immutable_and_do_not_share_mutable_containers(self):
        await self.save_completed()
        history = await self.read()
        with self.assertRaises(TypeError):
            history.records[-1].data["result"]["observed"] = [9]
        self.assertEqual(history.records[-1].data["result"]["observed"], (1, 2))

    async def test_bad_envelopes_are_reported_without_discarding_other_saved_activity(self):
        await self.save_completed()
        path = next(self.root.glob("history-*.jsonl"))
        original = path.read_bytes()
        rows = [json.loads(line) for line in original.splitlines()]
        sample = next(row for row in rows if row["kind"] == "activity_state_changed")
        cases = [dict(sample, format="ntk.history.future"), dict(sample, run_id="mismatch"),
                 dict(sample, sequence=True), dict(sample, at="2000-01-01T00:00:00+00:00")]
        extra = [json.dumps(row).encode() + b"\n" for row in cases]
        extra.extend([b'{"kind":"activity_state_changed","kind":"duplicate"}\n',
                      b'{"value":NaN}\n'])
        damaged = original + b"".join(extra)
        path.write_bytes(damaged)
        history = await self.read()
        self.assertEqual(len(history.records), 3)
        self.assertEqual(len(history.issues), len(extra))
        self.assertEqual(path.read_bytes(), damaged)
