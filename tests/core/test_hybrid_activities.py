"""Actual executor reports, not transport acceptance, drive remote activities."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
import unittest

from nymph_toolkit.contracts import ActivityChange, ActivityKey, ActivityRequest, ActivityState, Placement, RuntimeFailure
from tests.core import test_hybrid_group as baseline


async def until(predicate, timeout=3):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.005)


class HybridActivityTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.HybridGroupTests.asyncSetUp
    asyncTearDown = baseline.HybridGroupTests.asyncTearDown
    group = baseline.HybridGroupTests.group
    register = baseline.HybridGroupTests.register
    start = baseline.HybridGroupTests.start

    def request(self, activity_id="a", start=None):
        return ActivityRequest(ActivityKey("nymph", activity_id), "investigate", start, timedelta(seconds=10))

    async def setup_group(self):
        group = self.group()
        self.register(group, "nymph", Placement.LOCAL)
        self.register(group, "executor", Placement.PROCESS)
        manager = group.enable_activities(clock_check_interval=.02, max_running=1)
        runtime = await self.start(group)
        return group, manager, runtime

    async def test_pause_resume_and_finish_keep_child_continuation_and_confirmed_timing(self):
        group, manager, _ = await self.setup_group()
        request = self.request()
        manager.submit_remote(request, "executor", "work")
        await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
        first = manager.snapshot(request.key)
        self.assertFalse(first.timing_confirmed)
        self.assertIsNotNone(first.started_at)
        manager.request_pause(request.key, command_id="pause", expected_revision=first.revision)
        paused = await asyncio.wait_for(manager.wait_command(request.key, "pause"), 3)
        self.assertEqual(paused.snapshot.state, ActivityState.PAUSED)
        self.assertTrue(paused.snapshot.timing_confirmed)
        execution = paused.snapshot.execution_seconds
        await asyncio.sleep(.04)
        self.assertEqual(manager.snapshot(request.key).execution_seconds, execution)
        manager.request_resume(request.key, command_id="resume", expected_revision=paused.snapshot.revision)
        resumed = await asyncio.wait_for(manager.wait_command(request.key, "resume"), 3)
        self.assertEqual(resumed.snapshot.state, ActivityState.RUNNING)
        manager.request_finish(request.key)
        ended = await asyncio.wait_for(manager.wait(request.key), 3)
        self.assertEqual(ended.state, ActivityState.STOPPED)
        self.assertEqual(ended.result["steps"], 1)
        self.assertTrue(ended.cleanup_confirmed)
        self.assertGreaterEqual(ended.elapsed_seconds, ended.execution_seconds)

    async def test_changes_and_idempotency_preserve_nymph_authority(self):
        group, manager, _ = await self.setup_group()
        request = self.request(start=datetime.now(timezone.utc) + timedelta(seconds=60))
        initial = manager.submit_remote(request, "executor", "work")
        change = ActivityChange(start_at=None, duration=timedelta(seconds=.1), priority=4)
        applied = manager.change(request.key, change, command_id="change", expected_revision=initial.revision)
        self.assertEqual(manager.change(request.key, change, command_id="change", expected_revision=initial.revision), applied)
        await until(lambda: manager.snapshot(request.key).planned_end_notified)
        self.assertEqual(manager.snapshot(request.key).state, ActivityState.RUNNING)
        manager.request_finish(request.key)
        self.assertTrue((await asyncio.wait_for(manager.wait(request.key), 3)).cleanup_confirmed)

    async def test_executor_failure_is_activity_failure_not_child_failure(self):
        group, manager, runtime = await self.setup_group()
        request = self.request()
        manager.submit_remote(request, "executor", "work", {"fail": True})
        ended = await asyncio.wait_for(manager.wait(request.key), 3)
        self.assertEqual(ended.state, ActivityState.FAILED)
        self.assertTrue(ended.cleanup_confirmed)
        self.assertEqual(runtime.state.value, "running")

    async def test_child_loss_records_unknown_cleanup_and_releases_slot_after_exit(self):
        group, manager, runtime = await self.setup_group()
        request = self.request()
        manager.submit_remote(request, "executor", "work")
        await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
        group.modules["executor"].process.kill()
        with self.assertRaises(RuntimeFailure):
            await asyncio.wait_for(runtime.wait(), 4)
        ended = manager.snapshot(request.key)
        self.assertEqual(ended.state, ActivityState.FAILED)
        self.assertFalse(ended.cleanup_confirmed)
        self.assertIsNone(ended.ended_at)
        self.assertEqual(manager._running_slots, 0)

    async def test_repeated_shutdown_cancel_during_final_timer_cleanup_keeps_failure_record(self):
        group, manager, runtime = await self.setup_group()
        request = self.request()
        manager.submit_remote(request, "executor", "work")
        await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
        entry = manager._entry(request.key)
        entry.timer.cancel()
        await asyncio.gather(entry.timer, return_exceptions=True)
        cleaning, release = asyncio.Event(), asyncio.Event()
        async def timer():
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
        entry.timer = manager._spawn(timer(), "delayed-test-timer", fatal=False)
        await asyncio.sleep(0)
        group.modules["executor"].process.kill()
        await asyncio.wait_for(cleaning.wait(), 3)
        entry.driver.cancel()
        await asyncio.sleep(0)
        release.set()
        with self.assertRaises(RuntimeFailure):
            await asyncio.wait_for(runtime.wait(), 4)
        self.assertEqual(manager.snapshot(request.key).state, ActivityState.FAILED)
        self.assertFalse(manager.snapshot(request.key).cleanup_confirmed)
        self.assertEqual(manager._running_slots, 0)

    async def test_shutdown_guardian_breaks_unresponsive_child_cleanup_wait(self):
        group, manager, runtime = await self.setup_group()
        request = self.request()
        manager.submit_remote(request, "executor", "work", {"stuck_cleanup": True})
        await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
        try:
            await asyncio.wait_for(runtime.stop(), 4)
        except RuntimeFailure:
            pass
        self.assertIsNotNone(group.modules["executor"].process.returncode)
        self.assertFalse(manager.snapshot(request.key).cleanup_confirmed)

    async def test_four_placements_requester_owns_remote_activity_commands(self):
        for requester in Placement:
            for executor in Placement:
                with self.subTest(requester=requester, executor=executor):
                    group = self.group()
                    self.register(group, "requester", requester)
                    self.register(group, "executor", executor)
                    group.enable_activities(clock_check_interval=.02, max_running=1)
                    runtime = await self.start(group)
                    result = await group.modules["requester"].invoke("invoke", {
                        "contract": baseline.KEY, "operation": "activity", "args": ["executor"], "kwargs": {}}, timeout=6)
                    self.assertEqual(result["state"], "stopped")
                    self.assertTrue(result["cleanup"])
                    self.assertEqual(result["result"]["steps"], 1)
                    await runtime.stop()

    async def test_pause_while_resume_report_is_delayed_keeps_slot_until_safe_point(self):
        group, manager, _ = await self.setup_group()
        request = self.request()
        manager.submit_remote(request, "executor", "work")
        await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
        manager.request_pause(request.key, command_id="p1", expected_revision=manager.snapshot(request.key).revision)
        paused = await asyncio.wait_for(manager.wait_command(request.key, "p1"), 3)
        arrived, release = asyncio.Event(), asyncio.Event()
        original = manager._remote_event
        async def delayed(module_id, data):
            if data["phase"] == "resumed":
                arrived.set()
                await release.wait()
            return await original(module_id, data)
        manager._remote_event = delayed
        manager.request_resume(request.key, command_id="r1", expected_revision=paused.snapshot.revision)
        await asyncio.wait_for(arrived.wait(), 3)
        current = manager.snapshot(request.key)
        self.assertEqual(current.state, ActivityState.RESUME_PENDING)
        manager.request_pause(request.key, command_id="p2", expected_revision=current.revision)
        self.assertEqual(manager._running_slots, 1)
        self.assertEqual(manager.snapshot(request.key).state, ActivityState.PAUSING)
        release.set()
        second = await asyncio.wait_for(manager.wait_command(request.key, "p2"), 3)
        self.assertEqual(second.snapshot.state, ActivityState.PAUSED)
        self.assertEqual(manager._running_slots, 0)
        manager.request_finish(request.key)
        await asyncio.wait_for(manager.wait(request.key), 3)

    async def test_immediate_finish_and_runtime_stop_do_not_dispatch_unstarted_work(self):
        group, manager, runtime = await self.setup_group()
        request = self.request()
        manager.submit_remote(request, "executor", "work")
        manager.request_finish(request.key)
        ended = await asyncio.wait_for(manager.wait(request.key), 3)
        self.assertIsNone(ended.started_at)
        self.assertTrue(ended.cleanup_confirmed)
        manager.submit_remote(self.request("b"), "executor", "work")
        await asyncio.wait_for(runtime.stop(), 4)
        self.assertEqual(manager._running_slots, 0)

    async def test_remote_history_is_readable_and_new_runtime_does_not_restore_activity(self):
        group, manager, runtime = await self.setup_group()
        manager.submit_remote(self.request(), "executor", "work", {"complete": True})
        await asyncio.wait_for(manager.wait(self.request().key), 3)
        await runtime.stop()
        from nymph_toolkit.core import FileStore, HybridGroup
        from pathlib import Path
        root = Path(self.temp.name) / "0"
        restored = HybridGroup(group.settings, FileStore(root / "main", root / "archive", retention=timedelta(days=1), batch_size=10, flush_interval=.01))
        self.register(restored, "nymph", Placement.LOCAL)
        self.register(restored, "executor", Placement.PROCESS)
        next_manager = restored.enable_activities(clock_check_interval=.02)
        await self.start(restored)
        history = await next_manager.history("nymph")
        self.assertTrue(history.records)
        self.assertFalse(next_manager._activities)
