"""Observe public lifecycle behavior and actual task ownership."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import unittest

from nymph_toolkit.core import Runtime
from nymph_toolkit.contracts import LifecyclePhase, RuntimeFailure, RuntimeState, RuntimeStateError
from tests.doubles.service import Service


async def entered(service, phase):
    await asyncio.wait_for(service.entered[phase].wait(), 5)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        remaining = asyncio.all_tasks() - {asyncio.current_task()}
        for task in remaining:
            task.cancel()
        if remaining:
            await asyncio.gather(*remaining, return_exceptions=True)
        self.assertEqual(remaining, set(), "Runtime or service tasks leaked past completion")

    async def test_natural_completion_returns_result_and_cleans_once(self):
        service = Service(child=True)
        runtime = Runtime(service)
        self.assertEqual(runtime.state, RuntimeState.NEW)
        await runtime.start()
        self.assertEqual(await runtime.wait(), "result")
        await runtime.stop()
        await runtime.stop()
        self.assertEqual(service.events, ["start", "run", "stop"])
        self.assertTrue(service.child.done())
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_states_and_stop_waits_for_cleanup(self):
        start_gate, run_gate, stop_gate = (asyncio.Event() for _ in range(3))
        service = Service(start_gate=start_gate, run_gate=run_gate, stop_gate=stop_gate)
        runtime = Runtime(service)
        starting = asyncio.create_task(runtime.start())
        await entered(service, "start")
        self.assertEqual(runtime.state, RuntimeState.STARTING)
        start_gate.set()
        await starting
        await entered(service, "run")
        self.assertEqual(runtime.state, RuntimeState.RUNNING)
        stopping = asyncio.create_task(runtime.stop())
        await entered(service, "stop")
        self.assertEqual(runtime.state, RuntimeState.STOPPING)
        self.assertFalse(stopping.done())
        stop_gate.set()
        await stopping
        self.assertIsNone(await runtime.wait())
        self.assertEqual(runtime.state, RuntimeState.STOPPED)
        self.assertEqual(service.events, ["start", "run", "stop"])

    async def test_stop_before_start_does_not_call_service(self):
        service = Service()
        runtime = Runtime(service)
        await runtime.stop()
        await runtime.stop()
        self.assertIsNone(await runtime.wait())
        with self.assertRaises(RuntimeStateError):
            await runtime.start()
        self.assertEqual(service.events, [])

    async def test_wait_before_start_is_rejected(self):
        with self.assertRaises(RuntimeStateError):
            await Runtime(Service()).wait()

    async def test_double_start_and_restart_are_rejected(self):
        service = Service(start_gate=asyncio.Event(), run_gate=asyncio.Event())
        runtime = Runtime(service)
        first = asyncio.create_task(runtime.start())
        await entered(service, "start")
        with self.assertRaises(RuntimeStateError):
            await runtime.start()
        service.gates["start"].set()
        await first
        with self.assertRaises(RuntimeStateError):
            await runtime.start()
        await runtime.stop()
        with self.assertRaises(RuntimeStateError):
            await runtime.start()

    async def test_new_instance_can_run_again(self):
        service = Service()
        for _ in range(2):
            runtime = Runtime(service)
            await runtime.start()
            self.assertEqual(await runtime.wait(), "result")
        self.assertEqual(service.events, ["start", "run", "stop"] * 2)

    async def test_start_failure_cleans_partial_initialization_before_notifying(self):
        error = ValueError("startup")
        service = Service(errors={"start": error}, child=True)
        runtime = Runtime(service)
        with self.assertRaises(RuntimeFailure) as caught:
            await runtime.start()
        self.assertEqual(service.events, ["start", "stop"])
        self.assertTrue(service.child.done())
        self.assertEqual(runtime.state, RuntimeState.FAILED)
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(caught.exception.failures[0].phase, LifecyclePhase.START)

    async def test_run_and_stop_failures_keep_both_exceptions(self):
        run_error, stop_error = ValueError("run"), OSError("stop")
        runtime = Runtime(Service(errors={"run": run_error, "stop": stop_error}))
        await runtime.start()
        for wait in (runtime.wait, runtime.stop):
            with self.assertRaises(RuntimeFailure) as caught:
                await wait()
            failures = caught.exception.failures
            self.assertEqual([f.phase for f in failures], [LifecyclePhase.RUN, LifecyclePhase.STOP])
            self.assertEqual([f.exception for f in failures], [run_error, stop_error])
        self.assertEqual(runtime.state, RuntimeState.FAILED)

    async def test_start_and_stop_failures_keep_both_exceptions(self):
        errors = {"start": ValueError("start"), "stop": ValueError("stop")}
        runtime = Runtime(Service(errors=errors))
        with self.assertRaises(RuntimeFailure) as caught:
            await runtime.start()
        self.assertEqual([f.exception for f in caught.exception.failures], list(errors.values()))
        self.assertEqual(runtime.state, RuntimeState.FAILED)

    async def test_single_run_or_cleanup_failure(self):
        for phase in ("run", "stop"):
            with self.subTest(phase=phase):
                error = ValueError(phase)
                service = Service(errors={phase: error})
                runtime = Runtime(service)
                await runtime.start()
                with self.assertRaises(RuntimeFailure) as caught:
                    await runtime.wait()
                self.assertEqual(len(caught.exception.failures), 1)
                self.assertEqual(caught.exception.failures[0].phase, phase)
                self.assertIs(caught.exception.failures[0].exception, error)
                self.assertEqual(service.events, ["start", "run", "stop"])

    async def test_unrequested_service_cancellation_is_failure(self):
        for phase in ("start", "run", "stop"):
            with self.subTest(phase=phase):
                service = Service(errors={phase: asyncio.CancelledError()})
                runtime = Runtime(service)
                with self.assertRaises(RuntimeFailure) as caught:
                    await runtime.start()
                    await runtime.wait()
                self.assertEqual(caught.exception.failures[0].phase, phase)
                self.assertEqual(runtime.state, RuntimeState.FAILED)
                self.assertEqual(service.events.count("stop"), 1)

    async def test_stop_during_initialization(self):
        service = Service(start_gate=asyncio.Event(), child=True)
        runtime = Runtime(service)
        starting = asyncio.create_task(runtime.start())
        await entered(service, "start")
        await runtime.stop()
        with self.assertRaises(RuntimeStateError):
            await starting
        self.assertEqual(service.events, ["start", "stop"])
        self.assertTrue(service.child.done())
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_stop_before_supervisor_enters(self):
        service = Service()
        runtime = Runtime(service)
        starting = asyncio.create_task(runtime.start())
        await asyncio.sleep(0)
        await runtime.stop()
        with self.assertRaises(RuntimeStateError):
            await starting
        self.assertEqual(service.events, [])
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_cancelled_start_requests_cleanup(self):
        service = Service(start_gate=asyncio.Event(), stop_gate=asyncio.Event())
        runtime = Runtime(service)
        starting = asyncio.create_task(runtime.start())
        await entered(service, "start")
        starting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await starting
        await entered(service, "stop")
        self.assertEqual(runtime.state, RuntimeState.STOPPING)
        service.gates["stop"].set()
        await runtime.stop()
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_cancelled_wait_does_not_cancel_execution(self):
        service = Service(run_gate=asyncio.Event())
        runtime = Runtime(service)
        await runtime.start()
        waiter = asyncio.create_task(runtime.wait())
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertEqual(runtime.state, RuntimeState.RUNNING)
        service.gates["run"].set()
        self.assertEqual(await runtime.wait(), "result")

    async def test_cancelled_stop_and_repeated_stop_do_not_interrupt_cleanup(self):
        service = Service(run_gate=asyncio.Event(), stop_gate=asyncio.Event())
        runtime = Runtime(service)
        await runtime.start()
        first = asyncio.create_task(runtime.stop())
        await entered(service, "stop")
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(runtime.stop())
        third = asyncio.create_task(runtime.stop())
        await asyncio.sleep(0)
        self.assertEqual(runtime.state, RuntimeState.STOPPING)
        self.assertFalse(second.done())
        service.gates["stop"].set()
        await asyncio.gather(second, third)
        self.assertEqual(service.events.count("stop"), 1)
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_unrelated_task_is_not_stopped(self):
        unrelated = asyncio.create_task(asyncio.Event().wait())
        runtime = Runtime(Service(run_gate=asyncio.Event()))
        await runtime.start()
        await runtime.stop()
        self.assertFalse(unrelated.done())
        unrelated.cancel()
        await asyncio.gather(unrelated, return_exceptions=True)

    async def test_stop_timeout_is_not_stop_completion(self):
        service = Service(run_gate=asyncio.Event(), stop_gate=asyncio.Event())
        runtime = Runtime(service)
        await runtime.start()
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(0):
                await runtime.stop()
        await entered(service, "stop")
        self.assertEqual(runtime.state, RuntimeState.STOPPING)
        service.gates["stop"].set()
        await runtime.stop()
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_control_from_another_loop_is_rejected(self):
        runtime = Runtime(Service(run_gate=asyncio.Event()))
        await runtime.start()
        with self.assertRaises(RuntimeStateError):
            await asyncio.to_thread(lambda: asyncio.run(runtime.stop()))
        self.assertEqual(runtime.state, RuntimeState.RUNNING)
        await runtime.stop()

    async def test_service_cannot_wait_for_itself(self):
        for operation in ("wait", "stop"):
            with self.subTest(operation=operation):
                service = Service()
                runtime = Runtime(service)
                async def run():
                    await getattr(runtime, operation)()
                service.run = run
                await runtime.start()
                with self.assertRaises(RuntimeFailure) as caught:
                    await runtime.wait()
                self.assertIsInstance(caught.exception.failures[0].exception, RuntimeStateError)
                self.assertEqual(service.events, ["start", "stop"])

    async def test_eager_task_factory_preserves_lifecycle(self):
        loop = asyncio.get_running_loop()
        original = loop.get_task_factory()
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            service = Service()
            runtime = Runtime(service)
            await runtime.start()
            self.assertEqual(await runtime.wait(), "result")
            self.assertEqual(service.events, ["start", "run", "stop"])
        finally:
            loop.set_task_factory(original)

    async def test_task_creation_failure_is_reported_without_running_hooks(self):
        loop = asyncio.get_running_loop()
        original = loop.get_task_factory()
        error = ValueError("task factory")
        def fail_factory(loop, coro, **kwargs):
            raise error
        runtime = Runtime(Service())
        loop.set_task_factory(fail_factory)
        try:
            with self.assertRaises(RuntimeFailure) as caught:
                await runtime.start()
            self.assertIs(caught.exception.__cause__, error)
            self.assertEqual(runtime.state, RuntimeState.FAILED)
        finally:
            loop.set_task_factory(original)

    async def test_eager_factory_also_rejects_self_wait(self):
        loop = asyncio.get_running_loop()
        original = loop.get_task_factory()
        service = Service()
        runtime = Runtime(service)
        async def run():
            await runtime.stop()
        service.run = run
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            await runtime.start()
            with self.assertRaises(RuntimeFailure) as caught:
                await runtime.wait()
            self.assertIsInstance(caught.exception.failures[0].exception, RuntimeStateError)
        finally:
            loop.set_task_factory(original)


if __name__ == "__main__":
    unittest.main()
