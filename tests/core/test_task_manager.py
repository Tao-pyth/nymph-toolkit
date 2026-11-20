"""Observe requested work, time notifications and cooperative activity ownership."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from nymph_toolkit.contracts import (
    ActivityAdmissionError, ActivityFinishReason, ActivityKey, ActivityNoticeKind,
    ActivityRequest, ActivityStartInPastError, ActivityState, ActivityStateError,
    DuplicateActivityError, ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState,
    RuntimeState, Usage,
)
from nymph_toolkit.core import Connections, Registry, TaskManager
from tests.doubles.activity_clock import ActivityClock
from tests.doubles.connection_store import MemoryStore


async def eventually(predicate):
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("Expected state was not reached")


class TaskManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = ActivityClock(datetime(2026, 11, 21, 21, 59, tzinfo=timezone.utc))
        self.store = MemoryStore()
        self.registry = Registry()
        self.registry.register(ModuleSpec("nymph", ModuleKind.SUBSYSTEM))
        self.connections = Connections(self.registry, self.store)
        self.connections.declare(ModuleAdvertisement("nymph", "1", ()))
        self.connections.publish_usage("nymph", Usage(OperatingState.RUNNING, True, 0, 1))
        await self.connections.start()
        self.manager = TaskManager(self.connections, clock_check_interval=1, clock=self.clock)
        await self.manager.start()

    async def asyncTearDown(self):
        await self.manager.stop()
        await self.connections.stop()
        remaining = [task.get_name() for task in asyncio.all_tasks()
                     if task is not asyncio.current_task() and task.get_name().startswith("ntk-")]
        self.assertEqual(remaining, [])

    def request(self, activity_id="one", *, start_at=None, duration=timedelta(hours=2), content="調査"):
        return ActivityRequest(ActivityKey("nymph", activity_id), content, start_at, duration)

    async def hold(self, context):
        await context.wait_for_finish()
        return {"finished": True}

    async def test_late_acceptance_is_returned_to_nymph_without_reserving_the_key(self):
        invoked = []
        async def execute(context):
            invoked.append(context)
        request = self.request(start_at=self.clock.now() - timedelta(minutes=10))
        with self.assertRaises(ActivityStartInPastError) as caught:
            self.manager.submit(request, execute)
        self.assertIs(caught.exception.request, request)
        self.assertEqual(self.manager.activities(), ())
        self.assertEqual(invoked, [])
        self.assertEqual(self.store.records[-1][0], "activity_rejected")
        revised = replace(request, start_at=self.clock.now() + timedelta(minutes=1))
        self.manager.submit(revised, execute)
        await eventually(lambda: len(self.clock.waiters) == 2)
        self.clock.advance(60)
        result = await asyncio.wait_for(self.manager.wait(revised.key), 1)
        self.assertEqual(result.state, ActivityState.COMPLETED)
        self.assertEqual(len(invoked), 1)

    async def test_delayed_actual_start_does_not_extend_or_stop_at_planned_end(self):
        request = self.request(start_at=self.clock.now() + timedelta(minutes=1))
        self.manager.submit(request, self.hold)
        await eventually(lambda: len(self.clock.waiters) == 2)
        self.clock.advance(11 * 60)
        await eventually(lambda: self.manager.snapshot(request.key).state == ActivityState.RUNNING)
        observed = self.manager.snapshot(request.key)
        self.assertEqual((observed.started_at.hour, observed.started_at.minute), (22, 10))
        self.assertEqual(observed.planned_end_at.hour, 0)
        self.clock.advance(110 * 60)
        await eventually(lambda: self.manager.snapshot(request.key).planned_end_notified)
        observed = self.manager.snapshot(request.key)
        self.assertEqual(observed.state, ActivityState.RUNNING)
        self.assertEqual(observed.elapsed_seconds, 110 * 60)
        self.assertIsNone(observed.finish_reason)
        notices = []
        while not self.manager._notices["nymph"].empty():
            notices.append(await self.manager.next_notice("nymph"))
        self.assertEqual(sum(n.kind == ActivityNoticeKind.PLANNED_END for n in notices), 1)
        self.manager.request_finish(request.key)
        ended = await asyncio.wait_for(self.manager.wait(request.key), 1)
        self.assertEqual(ended.state, ActivityState.STOPPED)
        self.assertEqual(ended.finish_reason, ActivityFinishReason.NYMPH)

    async def test_finish_signal_waits_for_safe_point_and_cleanup_without_cancelling_executor(self):
        request = self.request()
        finish_seen, safe_point, cleanup, returned = [asyncio.Event() for _ in range(4)]
        cancelled = []
        async def execute(context):
            try:
                await context.wait_for_finish()
                finish_seen.set()
                await safe_point.wait()
                await cleanup.wait()
                returned.set()
                return 7
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        self.manager.submit(request, execute)
        await eventually(lambda: self.manager.snapshot(request.key).state == ActivityState.RUNNING)
        first = self.manager.request_finish(request.key)
        await asyncio.wait_for(finish_seen.wait(), 1)
        self.assertEqual(first.state, ActivityState.FINISHING)
        self.assertEqual(self.manager.request_finish(request.key).finish_requested_at, first.finish_requested_at)
        waiting = asyncio.create_task(self.manager.wait(request.key))
        await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.assertFalse(returned.is_set())
        self.assertEqual(cancelled, [])
        self.clock.advance(3)
        safe_point.set()
        await asyncio.sleep(0)
        self.assertEqual(self.manager.snapshot(request.key).state, ActivityState.FINISHING)
        cleanup.set()
        result = await asyncio.wait_for(self.manager.wait(request.key), 1)
        self.assertEqual(result.result, 7)
        self.assertEqual(result.elapsed_seconds, 3)

    async def test_pending_finish_prevents_execution_and_completed_ids_remain_unique(self):
        invoked = []
        async def execute(context):
            invoked.append(context)
        request = self.request(start_at=self.clock.now() + timedelta(hours=1))
        self.manager.submit(request, execute)
        self.manager.request_finish(request.key)
        result = await asyncio.wait_for(self.manager.wait(request.key), 1)
        self.assertEqual(result.state, ActivityState.STOPPED)
        self.assertIsNone(result.started_at)
        self.assertEqual(invoked, [])
        with self.assertRaises(DuplicateActivityError):
            self.manager.submit(request, execute)

    async def test_early_completion_retains_result_and_has_no_later_time_notification(self):
        value = {"items": [1, 2]}
        async def execute(context):
            return value
        request = self.request()
        self.manager.submit(request, execute)
        result = await asyncio.wait_for(self.manager.wait(request.key), 1)
        value["items"].append(3)
        self.assertEqual(result.result["items"], (1, 2))
        self.assertEqual(result.state, ActivityState.COMPLETED)
        self.clock.advance(3 * 3600)
        await asyncio.sleep(0)
        self.assertFalse(self.manager.snapshot(request.key).planned_end_notified)
        self.assertEqual(self.manager.request_finish(request.key).state, ActivityState.COMPLETED)

    async def test_executor_failure_does_not_fail_core_or_restart_activity(self):
        original = ValueError("activity failure")
        calls = []
        async def fail(context):
            calls.append(context)
            raise original
        request = self.request()
        self.manager.submit(request, fail)
        result = await asyncio.wait_for(self.manager.wait(request.key), 1)
        self.assertEqual(result.state, ActivityState.FAILED)
        self.assertIs(result.failures[0].exception, original)
        self.assertFalse(self.manager._fatal.done())
        self.assertEqual(len(calls), 1)
        other = self.request("other")
        self.manager.submit(other, self.hold)
        await eventually(lambda: self.manager.snapshot(other.key).state == ActivityState.RUNNING)
        self.assertEqual(self.manager.state, RuntimeState.RUNNING)

    async def test_invalid_result_and_unrequested_cancellation_are_observable_activity_failures(self):
        async def invalid(context):
            return object()
        async def cancelled(context):
            raise asyncio.CancelledError("executor cancelled itself")
        for number, execute in enumerate((invalid, cancelled, lambda context: 1)):
            request = self.request(str(number))
            self.manager.submit(request, execute)
            result = await asyncio.wait_for(self.manager.wait(request.key), 1)
            self.assertEqual(result.state, ActivityState.FAILED)
            self.assertEqual(len(result.failures), 1)
        self.assertFalse(self.manager._fatal.done())

    async def test_storage_pause_blocks_new_execution_but_not_the_planned_end_notice(self):
        request = self.request(start_at=self.clock.now() + timedelta(seconds=1), duration=timedelta(seconds=2))
        self.manager.submit(request, self.hold)
        await eventually(lambda: len(self.clock.waiters) == 2)
        self.store.admitting = False
        with self.assertRaises(ActivityAdmissionError):
            self.manager.submit(self.request("rejected"), self.hold)
        self.clock.advance(3)
        await eventually(lambda: self.manager.snapshot(request.key).planned_end_notified)
        self.assertEqual(self.manager.snapshot(request.key).state, ActivityState.PENDING)
        self.store.admitting = True
        self.store.pulse()
        await eventually(lambda: self.manager.snapshot(request.key).state == ActivityState.RUNNING)
        self.assertEqual(self.manager.snapshot(request.key).elapsed_seconds, 0)

    async def test_clock_corrections_do_not_repeat_notice_or_change_monotonic_elapsed(self):
        request = self.request(duration=timedelta(seconds=5))
        self.manager.submit(request, self.hold)
        await eventually(lambda: self.manager.snapshot(request.key).state == ActivityState.RUNNING)
        self.clock.advance(2, wall_seconds=-100)
        await asyncio.sleep(0)
        self.assertFalse(self.manager.snapshot(request.key).planned_end_notified)
        self.clock.advance(1, wall_seconds=110)
        await eventually(lambda: self.manager.snapshot(request.key).planned_end_notified)
        self.assertEqual(self.manager.snapshot(request.key).elapsed_seconds, 3)
        self.clock.advance(100)
        await asyncio.sleep(0)
        records = [r for kind, r in self.store.records if kind == "activity_planned_end"]
        self.assertEqual(len(records), 1)

    async def test_stop_before_driver_entry_does_not_execute_and_unblocks_notice_waiters(self):
        invoked = []
        async def execute(context):
            invoked.append(context)
        request = self.request()
        self.manager.submit(request, execute)
        await self.manager.stop()
        self.assertEqual(invoked, [])
        self.assertEqual(self.manager.snapshot(request.key).state, ActivityState.STOPPED)
        with self.assertRaises(ActivityStateError):
            for _ in range(10):
                await self.manager.next_notice("nymph")

    async def test_repeated_cancellation_of_stop_waits_for_executor_cleanup(self):
        entered, cleanup, gate = [asyncio.Event() for _ in range(3)]
        async def execute(context):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup.set()
                await gate.wait()
        request = self.request()
        self.manager.submit(request, execute)
        await asyncio.wait_for(entered.wait(), 1)
        stopping = asyncio.create_task(self.manager.stop())
        await asyncio.wait_for(cleanup.wait(), 1)
        stopping.cancel()
        await asyncio.sleep(0)
        stopping.cancel()
        await asyncio.sleep(0)
        self.assertFalse(stopping.done())
        self.assertEqual(self.manager.snapshot(request.key).state, ActivityState.FINISHING)
        gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await stopping
        self.assertEqual(self.manager.snapshot(request.key).state, ActivityState.STOPPED)
        self.assertEqual(self.manager.snapshot(request.key).finish_reason, ActivityFinishReason.RUNTIME)

    async def test_requester_disappearing_before_start_is_an_activity_failure(self):
        request = self.request(start_at=self.clock.now() + timedelta(seconds=2))
        self.manager.submit(request, self.hold)
        await eventually(lambda: len(self.clock.waiters) == 2)
        self.registry.unregister("nymph")
        self.clock.advance(2)
        result = await asyncio.wait_for(self.manager.wait(request.key), 1)
        self.assertEqual(result.state, ActivityState.FAILED)
        self.assertIsInstance(result.failures[0].exception, ActivityAdmissionError)
        self.assertFalse(self.manager._fatal.done())

    async def test_owner_thread_restart_and_self_wait_guards(self):
        with self.assertRaises(ActivityStateError):
            await self.manager.start()
        with self.assertRaises(ActivityStateError):
            await asyncio.to_thread(self.manager.activities)
        async def execute(context):
            with self.assertRaises(ActivityStateError):
                await self.manager.wait(context.request.key)
            with self.assertRaises(ActivityStateError):
                await self.manager.stop()
            return "guarded"
        request = self.request()
        self.manager.submit(request, execute)
        with self.assertRaises(ValueError):
            self.manager.request_finish(request.key, reason="nymph")
        result = await asyncio.wait_for(self.manager.wait(request.key), 1)
        self.assertEqual(result.result, "guarded")

    async def test_runtime_shutdown_is_distinct_from_an_earlier_nymph_finish_request(self):
        entered, signalled = asyncio.Event(), asyncio.Event()
        async def execute(context):
            entered.set()
            await context.wait_for_finish()
            signalled.set()
            await asyncio.Event().wait()
        request = self.request()
        self.manager.submit(request, execute)
        await asyncio.wait_for(entered.wait(), 1)
        self.manager.request_finish(request.key)
        await asyncio.wait_for(signalled.wait(), 1)
        await self.manager.stop()
        result = self.manager.snapshot(request.key)
        self.assertEqual(result.state, ActivityState.STOPPED)
        self.assertEqual(result.finish_reason, ActivityFinishReason.RUNTIME)
        reasons = [data["finish_reason"] for kind, data in self.store.records if kind == "activity_state_changed"]
        self.assertIn("nymph", reasons)
        self.assertEqual(reasons[-1], "runtime")

    async def test_eager_factory_establishes_activity_ownership_before_executor_entry(self):
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        async def execute(context):
            with self.assertRaises(ActivityStateError):
                await self.manager.wait(context.request.key)
            await context.wait_for_finish()
            return "finished"
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            request = self.request()
            self.manager.submit(request, execute)
            await eventually(lambda: self.manager.snapshot(request.key).state == ActivityState.RUNNING)
            self.manager.request_finish(request.key)
            result = await asyncio.wait_for(self.manager.wait(request.key), 1)
            self.assertEqual(result.result, "finished")
        finally:
            loop.set_task_factory(previous)

    async def test_real_clock_notifies_and_allows_nymph_to_finish(self):
        manager = TaskManager(self.connections, clock_check_interval=0.005)
        await manager.start()
        try:
            request = self.request(duration=timedelta(milliseconds=10))
            manager.submit(request, self.hold)
            async def until_notice():
                while True:
                    notice = await manager.next_notice("nymph")
                    if notice.kind == ActivityNoticeKind.PLANNED_END:
                        return notice
            notice = await asyncio.wait_for(until_notice(), 2)
            self.assertEqual(notice.snapshot.state, ActivityState.RUNNING)
            self.assertIsNone(notice.snapshot.finish_reason)
            manager.request_finish(request.key)
            result = await asyncio.wait_for(manager.wait(request.key), 1)
            self.assertEqual(result.state, ActivityState.STOPPED)
        finally:
            await manager.stop()

    async def test_failed_shutdown_task_factory_still_reclaims_existing_activity(self):
        manager = TaskManager(self.connections, clock_check_interval=1, clock=self.clock)
        await manager.start()
        entered, cleaned = asyncio.Event(), asyncio.Event()
        async def execute(context):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        request = self.request()
        manager.submit(request, execute)
        await asyncio.wait_for(entered.wait(), 1)
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        error = ValueError("task factory unavailable")
        def fail_factory(loop, coroutine, **kwargs):
            raise error
        loop.set_task_factory(fail_factory)
        try:
            with self.assertRaises(ValueError) as caught:
                await manager.stop()
            self.assertIs(caught.exception, error)
        finally:
            loop.set_task_factory(previous)
        self.assertTrue(cleaned.is_set())
        self.assertEqual(manager.state, RuntimeState.FAILED)
        self.assertEqual(manager.snapshot(request.key).state, ActivityState.STOPPED)
