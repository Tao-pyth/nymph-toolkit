"""Revisioned schedule edits and commands preserve Nymph's effective intent."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import unittest

from nymph_toolkit.contracts import (
    ActivityChange, ActivityCommandStatus as Status, ActivityNoticeKind, ActivityState,
)
from tests.core import test_task_manager as baseline


class ActivityChangesTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.TaskManagerTests.asyncSetUp
    asyncTearDown = baseline.TaskManagerTests.asyncTearDown
    request = baseline.TaskManagerTests.request
    hold = baseline.TaskManagerTests.hold

    def change(self, key, values, command_id="edit", revision=None):
        return self.manager.change(key, ActivityChange(**values), command_id=command_id,
                                   expected_revision=self.manager.snapshot(key).revision if revision is None else revision)

    async def test_pending_schedule_moves_in_both_directions_and_preserves_original(self):
        plan = self.request(start_at=self.clock.now() + timedelta(seconds=20))
        self.manager.submit(plan, self.hold)
        first = self.change(plan.key, {"start_at": self.clock.now() + timedelta(seconds=40)})
        self.assertEqual(first.status, Status.APPLIED)
        self.assertEqual(first.snapshot.request, plan)
        self.clock.advance(25)
        await asyncio.sleep(0)
        self.assertEqual(self.manager.snapshot(plan.key).state, ActivityState.PENDING)
        second = self.change(plan.key, {"start_at": None}, "earlier")
        self.assertEqual(second.snapshot.planned_start_at, self.clock.now())
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).state == ActivityState.RUNNING)
        rejected = self.change(plan.key, {"start_at": None}, "too-late")
        self.assertEqual(rejected.reason, "invalid_state")

    async def test_past_start_rejects_entire_change_without_resetting_notification(self):
        plan = self.request(start_at=self.clock.now() + timedelta(seconds=20))
        original = self.manager.submit(plan, self.hold)
        rejected = self.change(plan.key, {"start_at": self.clock.now() - timedelta(seconds=1),
                                          "duration": timedelta(seconds=1), "priority": 9})
        self.assertEqual(rejected.reason, "start_in_past")
        self.assertEqual(rejected.snapshot, original)

    async def test_duration_change_is_total_not_delta_and_old_deadline_is_invalidated(self):
        plan = self.request(duration=timedelta(seconds=10))
        self.manager.submit(plan, self.hold)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).state == ActivityState.RUNNING)
        changed = self.change(plan.key, {"duration": timedelta(seconds=30)})
        self.assertEqual(changed.snapshot.planned_end_at, changed.snapshot.planned_start_at + timedelta(seconds=30))
        self.clock.advance(11)
        for _ in range(20):
            await asyncio.sleep(0)
        self.assertFalse(self.manager.snapshot(plan.key).planned_end_notified)
        self.clock.advance(19)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).planned_end_notified)
        self.assertEqual(self.manager.snapshot(plan.key).state, ActivityState.RUNNING)

    async def test_shortening_to_past_notifies_immediately_and_extension_notifies_again(self):
        plan = self.request(duration=timedelta(seconds=30))
        self.manager.submit(plan, self.hold)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).state == ActivityState.RUNNING)
        self.clock.advance(10)
        short = self.change(plan.key, {"duration": timedelta(seconds=5)})
        self.assertTrue(short.snapshot.planned_end_notified)
        self.assertEqual(short.snapshot.state, ActivityState.RUNNING)
        extended = self.change(plan.key, {"duration": timedelta(seconds=20)}, "extend")
        self.assertFalse(extended.snapshot.planned_end_notified)
        self.clock.advance(10)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).planned_end_notified)
        notices = list(self.manager._notices["nymph"]._queue)
        ends = [n for n in notices if n.kind == ActivityNoticeKind.PLANNED_END]
        self.assertEqual([n.snapshot.scheduled_revision for n in ends], [1, 2])
        self.assertTrue(ends[0].snapshot.planned_end_notified)

    async def test_same_values_and_priority_only_do_not_renotify(self):
        plan = self.request(duration=timedelta(seconds=1))
        self.manager.submit(plan, self.hold)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).state == ActivityState.RUNNING)
        self.clock.advance(2)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).planned_end_notified)
        original = self.manager.snapshot(plan.key)
        noop = self.change(plan.key, {"duration": plan.duration})
        self.assertEqual(noop.status, Status.NO_CHANGE)
        self.assertEqual(noop.snapshot.revision, original.revision)
        priority = self.change(plan.key, {"priority": 5}, "priority")
        self.assertEqual(priority.snapshot.scheduled_revision, original.scheduled_revision)
        self.assertTrue(priority.snapshot.planned_end_notified)

    async def test_duplicate_id_precedes_revision_check_and_conflict_keeps_original_result(self):
        plan = self.request(start_at=self.clock.now() + timedelta(seconds=10))
        first = self.manager.submit(plan, self.hold)
        changed = self.change(plan.key, {"priority": 4}, revision=first.revision)
        count = len(self.store.records)
        repeated = self.change(plan.key, {"priority": 4}, revision=first.revision)
        self.assertIs(repeated, changed)
        self.assertEqual(len(self.store.records), count)
        conflict = self.change(plan.key, {"priority": 6}, revision=first.revision)
        self.assertEqual(conflict.reason, "command_id_conflict")
        self.assertIs(self.manager.command_result(plan.key, "edit"), changed)
        stale = self.change(plan.key, {"priority": 7}, "stale", revision=first.revision)
        self.assertEqual(stale.reason, "revision_conflict")
        self.assertEqual((await self.manager.wait_command(plan.key, "edit")), changed)

    async def test_finishing_and_terminal_states_reject_changes(self):
        plan = self.request()
        self.manager.submit(plan, self.hold)
        self.manager.request_finish(plan.key)
        result = self.change(plan.key, {"priority": 1})
        self.assertEqual(result.reason, "invalid_state")
        await self.manager.wait(plan.key)
        result = self.change(plan.key, {"duration": timedelta(seconds=1)}, "after")
        self.assertEqual(result.reason, "invalid_state")

    async def test_context_current_values_change_but_initial_request_does_not(self):
        contexts = []
        async def execute(context):
            contexts.append(context)
            await context.wait_for_finish()
        plan = self.request()
        self.manager.submit(plan, execute)
        await baseline.eventually(lambda: bool(contexts))
        changed = self.change(plan.key, {"duration": timedelta(seconds=60), "priority": -3})
        self.assertIs(contexts[0].request, plan)
        self.assertEqual(contexts[0].current_request, changed.snapshot.current_request)
        self.assertEqual(contexts[0].planned_end_at, changed.snapshot.planned_end_at)

    async def test_schedule_range_error_is_atomic_and_does_not_reserve_command_id(self):
        plan = self.request()
        original = self.manager.submit(plan, self.hold)
        with self.assertRaises(ValueError):
            self.change(plan.key, {"duration": timedelta.max, "priority": 8})
        self.assertEqual(self.manager.snapshot(plan.key), original)
        self.assertEqual(self.change(plan.key, {"priority": 8}).status, Status.APPLIED)
