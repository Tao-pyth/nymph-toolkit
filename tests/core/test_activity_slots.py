"""Finite slots order only waiting work, never preempt an executing activity."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import replace
from datetime import timedelta
import unittest

from nymph_toolkit.contracts import ActivityChange, ActivityCommandStatus as Status, ActivityState
from nymph_toolkit.core import TaskManager
from tests.core import test_activity_controls as controls, test_task_manager as baseline


class ActivitySlotsTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown = baseline.TaskManagerTests.asyncTearDown
    request = baseline.TaskManagerTests.request
    hold = baseline.TaskManagerTests.hold
    control = controls.ActivityControlsTests.control
    start_worker = controls.ActivityControlsTests.start_worker

    async def asyncSetUp(self):
        await baseline.TaskManagerTests.asyncSetUp(self)
        await self.manager.stop()
        self.manager = TaskManager(self.connections, clock_check_interval=1, clock=self.clock, max_running=1)
        await self.manager.start()

    async def occupy(self, identity="busy"):
        plan = self.request(identity)
        self.manager.submit(plan, self.hold)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).state == ActivityState.RUNNING)
        return plan.key

    async def finish(self, key):
        self.manager.request_finish(key)
        await self.manager.wait(key)

    async def test_priority_and_fifo_with_no_preemption(self):
        busy = await self.occupy()
        order = []
        async def work(context):
            order.append(context.request.key.activity_id)
        plans = [replace(self.request(name), priority=priority)
                 for name, priority in (("low", -1), ("first", 4), ("second", 4))]
        for plan in plans:
            self.manager.submit(plan, work)
        await baseline.eventually(lambda: len(self.manager._ready) == 3)
        self.assertEqual(order, [])
        self.assertEqual(self.manager.snapshot(busy).state, ActivityState.RUNNING)
        await self.finish(busy)
        for plan in plans:
            await self.manager.wait(plan.key)
        self.assertEqual(order, ["first", "second", "low"])
        self.assertEqual(self.manager._running_slots, 0)

    async def test_priority_change_preserves_fifo_ticket(self):
        busy = await self.occupy()
        order = []
        async def work(context):
            order.append(context.request.key.activity_id)
        first, second = self.request("first"), replace(self.request("second"), priority=2)
        self.manager.submit(first, work)
        self.manager.submit(second, work)
        await baseline.eventually(lambda: len(self.manager._ready) == 2)
        self.manager.change(first.key, ActivityChange(priority=2), command_id="raise", expected_revision=0)
        await self.finish(busy)
        await self.manager.wait(second.key)
        self.assertEqual(order, ["first", "second"])

    async def test_postponed_waiter_loses_old_fifo_position_and_does_not_reserve_slot(self):
        busy = await self.occupy()
        order = []
        async def work(context):
            order.append(context.request.key.activity_id)
        first, second = self.request("first"), self.request("second")
        self.manager.submit(first, work)
        self.manager.submit(second, work)
        await baseline.eventually(lambda: len(self.manager._ready) == 2)
        self.manager.change(first.key, ActivityChange(start_at=self.clock.now() + timedelta(seconds=10)),
                            command_id="delay", expected_revision=0)
        await baseline.eventually(lambda: len(self.manager._ready) == 1)
        self.clock.advance(10)
        await baseline.eventually(lambda: len(self.manager._ready) == 2)
        await self.finish(busy)
        await self.manager.wait(first.key)
        self.assertEqual(order, ["second", "first"])

    async def test_pausing_holds_slot_until_ack_and_start_and_resume_share_queue(self):
        safe = asyncio.Event()
        key, _, steps, _ = await self.start_worker(safe=safe)
        other = replace(self.request("other"), priority=2)
        self.manager.submit(other, self.hold)
        await baseline.eventually(lambda: len(self.manager._ready) == 1)
        self.control(key, "pause", "pause")
        await baseline.eventually(lambda: bool(steps))
        self.assertEqual(self.manager.snapshot(other.key).state, ActivityState.PENDING)
        safe.set()
        await self.manager.wait_command(key, "pause")
        await baseline.eventually(lambda: self.manager.snapshot(other.key).state == ActivityState.RUNNING)
        self.control(key, "resume", "resume")
        self.clock.advance(9)
        self.assertEqual(self.manager.snapshot(key).state, ActivityState.RESUME_PENDING)
        self.assertEqual(self.manager.snapshot(key).execution_seconds, 0)
        await self.finish(other.key)
        self.assertEqual((await self.manager.wait_command(key, "resume")).status, Status.APPLIED)
        await self.finish(key)

    async def test_paused_finish_bypasses_full_cap_and_counts_cleanup(self):
        cleanup = asyncio.Event()
        key, _, _, _ = await self.start_worker(cleanup=cleanup)
        self.control(key, "pause", "pause")
        await self.manager.wait_command(key, "pause")
        busy = await self.occupy()
        self.control(key, "resume", "resume")
        self.clock.advance(5)
        self.manager.request_finish(key)
        self.assertEqual((await self.manager.wait_command(key, "resume")).status, Status.SUPERSEDED)
        self.clock.advance(3)
        cleanup.set()
        ended = await self.manager.wait(key)
        self.assertEqual((ended.elapsed_seconds, ended.execution_seconds), (8, 3))
        self.assertEqual(self.manager.snapshot(busy).state, ActivityState.RUNNING)
        self.assertEqual(self.manager._running_slots, 1)

    async def test_resume_wait_withdrawal_and_retry_gets_new_fifo_position(self):
        key, _, _, _ = await self.start_worker()
        self.control(key, "pause", "pause")
        await self.manager.wait_command(key, "pause")
        busy = await self.occupy()
        self.control(key, "resume", "resume")
        old = self.manager._activities[key].ticket
        self.control(key, "pause", "withdraw")
        self.assertNotIn(key, self.manager._ready)
        self.control(key, "resume", "again")
        self.assertGreater(self.manager._activities[key].ticket, old)
        await self.finish(busy)
        await self.manager.wait_command(key, "again")

    async def test_finish_holds_existing_slot_until_cleanup_completes(self):
        cleanup = asyncio.Event()
        key, _, _, _ = await self.start_worker(cleanup=cleanup)
        other = self.request("other")
        self.manager.submit(other, self.hold)
        self.manager.request_finish(key)
        for _ in range(10):
            await asyncio.sleep(0)
        self.assertEqual(self.manager.snapshot(other.key).state, ActivityState.PENDING)
        cleanup.set()
        await self.manager.wait(key)
        await baseline.eventually(lambda: self.manager.snapshot(other.key).state == ActivityState.RUNNING)

    async def test_default_unlimited_and_invalid_caps(self):
        for cap in (True, 0, -1, 1.5, "2"):
            with self.assertRaises(ValueError):
                TaskManager(self.connections, clock_check_interval=1, max_running=cap)
        await self.manager.stop()
        self.manager = TaskManager(self.connections, clock_check_interval=1, clock=self.clock)
        await self.manager.start()
        for index in range(5):
            await self.occupy(str(index))
        self.assertEqual(self.manager._running_slots, 5)

    async def test_later_high_priority_resume_precedes_lower_priority_pending_start(self):
        key, _, _, _ = await self.start_worker()
        self.control(key, "pause", "pause")
        await self.manager.wait_command(key, "pause")
        self.manager.change(key, ActivityChange(priority=10), command_id="priority",
                            expected_revision=self.manager.snapshot(key).revision)
        busy = await self.occupy()
        waiting = self.request("waiting")
        self.manager.submit(waiting, self.hold)
        await baseline.eventually(lambda: len(self.manager._ready) == 1)
        self.control(key, "resume", "resume")
        await self.finish(busy)
        await self.manager.wait_command(key, "resume")
        self.assertEqual(self.manager.snapshot(waiting.key).state, ActivityState.PENDING)
        await self.finish(key)
        await baseline.eventually(lambda: self.manager.snapshot(waiting.key).state == ActivityState.RUNNING)

    async def test_pending_slot_wait_reaches_deadline_without_rescheduling_or_dropping_work(self):
        busy = await self.occupy()
        waiting = self.request("waiting", duration=timedelta(seconds=2))
        original = self.manager.submit(waiting, self.hold)
        await baseline.eventually(lambda: len(self.manager._ready) == 1)
        self.clock.advance(3)
        await baseline.eventually(lambda: self.manager.snapshot(waiting.key).planned_end_notified)
        self.assertEqual(self.manager.snapshot(waiting.key).state, ActivityState.PENDING)
        await self.finish(busy)
        await baseline.eventually(lambda: self.manager.snapshot(waiting.key).state == ActivityState.RUNNING)
        self.assertEqual(self.manager.snapshot(waiting.key).planned_end_at, original.planned_end_at)
