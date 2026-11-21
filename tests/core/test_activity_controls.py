"""Only executor safe points acknowledge pauses; resume retains the continuation."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import unittest

from nymph_toolkit.contracts import (
    ActivityChange, ActivityCommandStatus as Status, ActivityControlKind, ActivityFinishReason,
    ActivityState, ActivityStateError,
)
from tests.core import test_task_manager as baseline


class ActivityControlsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.TaskManagerTests.asyncSetUp
    asyncTearDown = baseline.TaskManagerTests.asyncTearDown
    request = baseline.TaskManagerTests.request
    hold = baseline.TaskManagerTests.hold

    def control(self, key, operation, command_id):
        return getattr(self.manager, "request_" + operation)(key, command_id=command_id,
                    expected_revision=self.manager.snapshot(key).revision)

    async def start_worker(self, *, safe=None, cleanup=None):
        contexts, steps, cancelled = [], [], []
        async def execute(context):
            contexts.append(context)
            local = 0
            try:
                while True:
                    signal = await context.wait_for_control()
                    steps.append((local, signal))
                    if safe is not None:
                        await safe.wait()
                    reason = await context.checkpoint()
                    if reason is not None:
                        break
                    local += 1
                    steps.append((local, None))
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
            finally:
                if cleanup is not None:
                    await cleanup.wait()
            return local
        plan = self.request()
        self.manager.submit(plan, execute, supports_pause=True)
        await baseline.eventually(lambda: bool(contexts))
        return plan.key, contexts, steps, cancelled

    async def test_pause_waits_for_safe_point_and_resume_keeps_the_same_executor(self):
        safe = asyncio.Event()
        key, contexts, steps, cancelled = await self.start_worker(safe=safe)
        first = self.control(key, "pause", "pause")
        self.assertEqual(first.status, Status.ACCEPTED)
        await baseline.eventually(lambda: bool(steps))
        self.assertEqual(self.manager.snapshot(key).state, ActivityState.PAUSING)
        self.assertEqual(cancelled, [])
        safe.set()
        done = await self.manager.wait_command(key, "pause")
        self.assertEqual(done.status, Status.APPLIED)
        self.assertEqual(done.snapshot.state, ActivityState.PAUSED)
        resume = self.control(key, "resume", "resume")
        self.assertEqual(resume.status, Status.ACCEPTED)
        await self.manager.wait_command(key, "resume")
        await baseline.eventually(lambda: (1, None) in steps)
        self.manager.request_finish(key)
        terminal = await self.manager.wait(key)
        self.assertEqual(terminal.result, 1)
        self.assertEqual(len(contexts), 1)
        self.assertEqual(cancelled, [])

    async def test_pause_and_resume_wait_are_excluded_but_preparation_and_cleanup_count(self):
        safe, cleanup = asyncio.Event(), asyncio.Event()
        key, _, _, _ = await self.start_worker(safe=safe, cleanup=cleanup)
        self.clock.advance(3)
        self.control(key, "pause", "pause")
        self.clock.advance(2)
        safe.set()
        await self.manager.wait_command(key, "pause")
        self.clock.advance(10, wall_seconds=-100)
        paused = self.manager.snapshot(key)
        self.assertEqual((paused.elapsed_seconds, paused.execution_seconds), (15, 5))
        self.manager.request_finish(key)
        self.clock.advance(4)
        cleanup.set()
        ended = await self.manager.wait(key)
        self.assertEqual((ended.elapsed_seconds, ended.execution_seconds), (19, 9))
        self.assertEqual(ended.finish_reason, ActivityFinishReason.NYMPH)

    async def test_paused_duration_reaches_end_without_resuming(self):
        key, _, _, _ = await self.start_worker()
        self.control(key, "pause", "pause")
        await self.manager.wait_command(key, "pause")
        self.manager.change(key, ActivityChange(duration=timedelta(seconds=5)), command_id="short",
                            expected_revision=self.manager.snapshot(key).revision)
        self.clock.advance(6)
        await baseline.eventually(lambda: self.manager.snapshot(key).planned_end_notified)
        self.assertEqual(self.manager.snapshot(key).state, ActivityState.PAUSED)

    async def test_non_supporting_executor_rejects_without_becoming_failed(self):
        plan = self.request()
        self.manager.submit(plan, self.hold)
        await baseline.eventually(lambda: self.manager.snapshot(plan.key).state == ActivityState.RUNNING)
        result = self.control(plan.key, "pause", "pause")
        self.assertEqual(result.reason, "unsupported_operation")
        self.assertEqual(result.snapshot.state, ActivityState.RUNNING)

    async def test_pending_duplicate_alias_and_wait_cancellation_do_not_cancel_control(self):
        safe = asyncio.Event()
        key, _, _, _ = await self.start_worker(safe=safe)
        result = self.control(key, "pause", "one")
        joined = self.control(key, "pause", "two")
        waiter = asyncio.create_task(self.manager.wait_command(key, "one"))
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertEqual(joined.status, Status.ACCEPTED)
        self.assertEqual(self.manager.command_result(key, "one"), result)
        safe.set()
        self.assertEqual((await self.manager.wait_command(key, "one")).status, Status.APPLIED)
        self.assertEqual((await self.manager.wait_command(key, "two")).status, Status.APPLIED)
        self.assertEqual(result.status, Status.ACCEPTED)

    async def test_finish_supersedes_incomplete_pause_and_wins_control_signal(self):
        safe = asyncio.Event()
        key, contexts, _, _ = await self.start_worker(safe=safe)
        self.control(key, "pause", "pause")
        self.manager.request_finish(key)
        self.assertEqual((await self.manager.wait_command(key, "pause")).status, Status.SUPERSEDED)
        self.assertEqual(await contexts[0].wait_for_control(), ActivityControlKind.FINISH)
        safe.set()
        self.assertEqual((await self.manager.wait(key)).state, ActivityState.STOPPED)

    async def test_natural_completion_and_executor_failure_resolve_pending_pause_honestly(self):
        for fail in (False, True):
            gate = asyncio.Event()
            error = ValueError("safe-point preparation failed")
            async def execute(context):
                await gate.wait()
                if fail:
                    raise error
            plan = self.request(str(fail))
            self.manager.submit(plan, execute, supports_pause=True)
            await baseline.eventually(lambda: self.manager.snapshot(plan.key).state == ActivityState.RUNNING)
            self.control(plan.key, "pause", "pause")
            gate.set()
            ended = await self.manager.wait(plan.key)
            result = await self.manager.wait_command(plan.key, "pause")
            self.assertEqual(result.status, Status.FAILED if fail else Status.SUPERSEDED)
            self.assertEqual(ended.state, ActivityState.FAILED if fail else ActivityState.COMPLETED)
            if fail:
                self.assertIs(ended.failures[0].exception, error)

    async def test_resume_can_be_withdrawn_before_it_runs(self):
        key, _, _, _ = await self.start_worker()
        self.control(key, "pause", "pause")
        await self.manager.wait_command(key, "pause")
        self.control(key, "resume", "resume")
        withdrawn = self.control(key, "pause", "withdraw")
        self.assertEqual(withdrawn.snapshot.state, ActivityState.PAUSED)
        self.assertEqual((await self.manager.wait_command(key, "resume")).status, Status.SUPERSEDED)
        for _ in range(10):
            await asyncio.sleep(0)
        self.assertEqual(self.manager.snapshot(key).state, ActivityState.PAUSED)

    async def test_only_executor_can_acknowledge_its_pause(self):
        key, contexts, _, _ = await self.start_worker()
        with self.assertRaises(ActivityStateError):
            await contexts[0].checkpoint()

    async def test_runtime_shutdown_cancels_paused_executor_and_collects_cleanup(self):
        key, _, _, cancelled = await self.start_worker()
        self.control(key, "pause", "pause")
        await self.manager.wait_command(key, "pause")
        await self.manager.stop()
        self.assertEqual(cancelled, [True])
        self.assertEqual(self.manager.snapshot(key).finish_reason, ActivityFinishReason.RUNTIME)

    async def test_eager_factory_preserves_safe_point_ownership_and_control_results(self):
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            key, _, steps, _ = await self.start_worker()
            self.control(key, "pause", "pause")
            await self.manager.wait_command(key, "pause")
            self.control(key, "resume", "resume")
            await self.manager.wait_command(key, "resume")
            await baseline.eventually(lambda: (1, None) in steps)
            self.manager.request_finish(key)
            self.assertEqual((await self.manager.wait(key)).result, 1)
        finally:
            loop.set_task_factory(previous)
