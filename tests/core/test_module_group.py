"""Exercise the registered module lifecycle through the existing Runtime."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import (
    DependencyUnavailableError, LifecyclePhase, ModuleGroupFailure, ModuleKind,
    ModuleSpec, RegistryStateError, RuntimeFailure, RuntimeState,
)
from nymph_toolkit.core import ModuleGroup, Runtime
from tests.doubles.module import Module


async def entered(module, phase):
    await asyncio.wait_for(module.entered[phase].wait(), 5)


def failures(error):
    return [
        failure
        for lifecycle in error.failures
        if isinstance(lifecycle.exception, ModuleGroupFailure)
        for failure in lifecycle.exception.failures
    ]


class ModuleGroupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.trace = []
        self.group = ModuleGroup()

    async def asyncTearDown(self):
        remaining = asyncio.all_tasks() - {asyncio.current_task()}
        for task in remaining:
            task.cancel()
        if remaining:
            await asyncio.gather(*remaining, return_exceptions=True)
        self.assertEqual(remaining, set(), "Group or dummy tasks leaked past completion")

    def add(self, module_id, *requires, kind=ModuleKind.SUBSYSTEM, **kwargs):
        module = Module(module_id, self.trace, **kwargs)
        self.group.register(ModuleSpec(module_id, kind, frozenset(requires)), module)
        return module

    async def test_dependency_order_results_and_reverse_cleanup(self):
        consumer = self.add("a-consumer", "z-provider", kind=ModuleKind.ADAPTER, child=True)
        provider = self.add("z-provider", child=True)
        runtime = Runtime(self.group)
        await runtime.start()
        self.assertEqual(await runtime.wait(), {"a-consumer": "a-consumer", "z-provider": "z-provider"})
        self.assertEqual([x for x in self.trace if x[1] == "start"], [("z-provider", "start"), ("a-consumer", "start")])
        self.assertEqual([x for x in self.trace if x[1] == "stop"], [("a-consumer", "stop"), ("z-provider", "stop")])
        self.assertTrue(provider.child.done() and consumer.child.done())
        await runtime.stop()
        self.assertEqual(len(self.group.entries()), 2)
        self.group.unregister("z-provider")
        self.assertFalse(self.group.get("a-consumer").available)

    async def test_empty_group_completes(self):
        runtime = Runtime(self.group)
        await runtime.start()
        self.assertEqual(await runtime.wait(), {})
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_independent_initialization_order_is_stable(self):
        for module_id in ("c", "a", "b"):
            self.add(module_id)
        runtime = Runtime(self.group)
        await runtime.start()
        await runtime.wait()
        self.assertEqual([key for key, phase in self.trace if phase == "start"], ["a", "b", "c"])

    async def test_missing_dependencies_prevent_all_initialization(self):
        self.add("a", "missing", child=True)
        self.add("b")
        runtime = Runtime(self.group)
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.start()
        error = raised.exception.failures[0].exception
        self.assertIsInstance(error, DependencyUnavailableError)
        self.assertEqual(error.missing_dependencies, frozenset({"missing"}))
        self.assertEqual(self.trace, [])
        self.group.unregister("a")

    async def test_prerun_detach_can_make_dependencies_unavailable(self):
        self.add("a", "b")
        self.add("b")
        update = self.group.unregister("b")
        self.assertEqual([c.module_id for c in update.changes], ["a", "b"])
        self.assertFalse(self.group.get("a").available)
        self.add("b")
        runtime = Runtime(self.group)
        await runtime.start()
        await runtime.wait()

    async def test_invalid_service_does_not_register(self):
        with self.assertRaises(TypeError):
            self.group.register(ModuleSpec("a", ModuleKind.SUBSYSTEM), object())
        self.assertEqual(self.group.revision, 0)
        self.assertEqual(self.group.entries(), ())

    async def test_partial_start_failure_cleans_entered_modules_only(self):
        first = self.add("a", child=True)
        original = ValueError("partial start")
        second = self.add("b", "a", errors={"start": original}, child=True)
        third = self.add("c", "b")
        runtime = Runtime(self.group)
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.start()
        found = failures(raised.exception)
        self.assertEqual([(f.module_id, f.phase) for f in found], [("b", LifecyclePhase.START)])
        self.assertIs(found[0].exception, original)
        self.assertEqual(self.trace, [("a", "start"), ("b", "start"), ("b", "stop"), ("a", "stop")])
        self.assertEqual(third.events, [])
        self.assertTrue(first.child.done() and second.child.done())

    async def test_start_and_cleanup_failures_are_both_retained(self):
        self.add("a", errors={"stop": ValueError("cleanup a")})
        self.add("b", "a", errors={"start": ValueError("start b"), "stop": TypeError("cleanup b")})
        runtime = Runtime(self.group)
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.start()
        self.assertEqual([(f.module_id, f.phase) for f in failures(raised.exception)], [
            ("b", LifecyclePhase.START), ("b", LifecyclePhase.STOP), ("a", LifecyclePhase.STOP)
        ])

    async def test_runtime_stop_cancels_owned_runs_and_keeps_unrelated_task(self):
        first = self.add("a", run_gate=asyncio.Event(), child=True)
        second = self.add("b", "a", run_gate=asyncio.Event(), child=True)
        unrelated = asyncio.create_task(asyncio.Event().wait())
        runtime = Runtime(self.group)
        await runtime.start()
        await entered(first, "run")
        await entered(second, "run")
        await runtime.stop()
        self.assertIsNone(await runtime.wait())
        self.assertFalse(unrelated.done())
        unrelated.cancel()
        await asyncio.gather(unrelated, return_exceptions=True)
        self.assertTrue(first.child.done() and second.child.done())

    async def test_run_failure_stops_other_runs(self):
        gate = asyncio.Event()
        first = self.add("a", run_gate=gate, errors={"run": ValueError("run a")})
        second = self.add("b", run_gate=asyncio.Event(), child=True)
        runtime = Runtime(self.group)
        await runtime.start()
        await entered(second, "run")
        gate.set()
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.wait()
        self.assertEqual([(f.module_id, f.phase) for f in failures(raised.exception)], [("a", LifecyclePhase.RUN)])
        self.assertEqual(first.events, ["start", "run", "stop"])
        self.assertTrue(second.child.done())

    async def test_simultaneous_run_failures_are_not_duplicated(self):
        gate = asyncio.Event()
        a = self.add("a", run_gate=gate, errors={"run": ValueError("a")})
        b = self.add("b", run_gate=gate, errors={"run": TypeError("b")})
        runtime = Runtime(self.group)
        await runtime.start()
        await entered(a, "run")
        await entered(b, "run")
        gate.set()
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.wait()
        self.assertEqual([(f.module_id, f.phase) for f in failures(raised.exception)], [
            ("a", LifecyclePhase.RUN), ("b", LifecyclePhase.RUN)
        ])

    async def test_run_failure_during_cancellation_is_retained(self):
        trigger = asyncio.Event()
        ready = asyncio.Event()
        self.add("a", run_gate=trigger, errors={"run": ValueError("first")})
        module = self.add("b")

        async def failing_during_cancel():
            ready.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise TypeError("late run failure")

        module.run = failing_during_cancel
        runtime = Runtime(self.group)
        await runtime.start()
        await asyncio.wait_for(ready.wait(), 5)
        trigger.set()
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.wait()
        self.assertEqual([(f.module_id, f.phase) for f in failures(raised.exception)], [
            ("a", LifecyclePhase.RUN), ("b", LifecyclePhase.RUN)
        ])

    async def test_unrequested_run_cancellation_is_a_failure(self):
        self.add("a", errors={"run": asyncio.CancelledError("unexpected")})
        self.add("b", run_gate=asyncio.Event())
        runtime = Runtime(self.group)
        await runtime.start()
        with self.assertRaises(RuntimeFailure) as raised:
            await asyncio.wait_for(runtime.wait(), 5)
        found = failures(raised.exception)
        self.assertEqual(found[0].module_id, "a")
        self.assertIsInstance(found[0].exception, asyncio.CancelledError)

    async def test_start_cancellation_keeps_module_context(self):
        self.add("a", errors={"start": asyncio.CancelledError("unexpected")})
        runtime = Runtime(self.group)
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.start()
        error = raised.exception.failures[0].exception
        self.assertIsInstance(error, asyncio.CancelledError)
        self.assertTrue(any("initializing a" in note for note in error.__notes__))
        self.assertEqual(self.trace, [("a", "start"), ("a", "stop")])

    async def test_all_cleanup_failures_are_retained_and_cleanup_continues(self):
        self.add("a", errors={"stop": ValueError("a")})
        self.add("b", errors={"stop": asyncio.CancelledError("b")})
        runtime = Runtime(self.group)
        await runtime.start()
        with self.assertRaises(RuntimeFailure) as raised:
            await runtime.wait()
        self.assertEqual([(f.module_id, f.phase) for f in failures(raised.exception)], [
            ("b", LifecyclePhase.STOP), ("a", LifecyclePhase.STOP)
        ])
        self.group.unregister("a")

    async def test_configuration_is_frozen_through_start_run_and_stop(self):
        start_gate, run_gate, stop_gate = (asyncio.Event() for _ in range(3))
        a = self.add("a", start_gate=start_gate, run_gate=run_gate, stop_gate=stop_gate)
        runtime = Runtime(self.group)
        starting = asyncio.create_task(runtime.start())
        await entered(a, "start")
        for phase in ("start", "run", "stop"):
            with self.assertRaises(RegistryStateError):
                self.group.unregister("a")
            with self.assertRaises(RegistryStateError):
                self.add("b")
            self.assertEqual(self.group.revision, 1)
            if phase == "start":
                start_gate.set()
                await starting
                await entered(a, "run")
            elif phase == "run":
                stopping = asyncio.create_task(runtime.stop())
                await entered(a, "stop")
        stop_gate.set()
        await stopping
        self.group.unregister("a")
        self.assertEqual(self.group.entries(), ())
        with self.assertRaises(RegistryStateError):
            self.add("b")

    async def test_cancelled_start_waiter_leaves_cleanup_owned_by_runtime(self):
        a = self.add("a", start_gate=asyncio.Event(), stop_gate=asyncio.Event(), child=True)
        runtime = Runtime(self.group)
        starting = asyncio.create_task(runtime.start())
        await entered(a, "start")
        starting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await starting
        await entered(a, "stop")
        with self.assertRaises(RegistryStateError):
            self.group.unregister("a")
        a.gates["stop"].set()
        await runtime.stop()
        self.assertTrue(a.child.done())
        self.group.unregister("a")

    async def test_cancelled_stop_waiter_and_repeated_stop_do_not_repeat_cleanup(self):
        a = self.add("a", run_gate=asyncio.Event(), stop_gate=asyncio.Event())
        runtime = Runtime(self.group)
        await runtime.start()
        await entered(a, "run")
        stopping = asyncio.create_task(runtime.stop())
        await entered(a, "stop")
        stopping.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await stopping
        second = asyncio.create_task(runtime.stop())
        a.gates["stop"].set()
        await second
        await runtime.stop()
        self.assertEqual(a.events.count("stop"), 1)

    async def test_sharing_with_another_runtime_cannot_stop_original_group(self):
        a = self.add("a", run_gate=asyncio.Event())
        first, second = Runtime(self.group), Runtime(self.group)
        await first.start()
        await entered(a, "run")
        with self.assertRaises(RuntimeFailure):
            await second.start()
        self.assertEqual(first.state, RuntimeState.RUNNING)
        self.assertNotIn("stop", a.events)
        await first.stop()

    async def test_new_runtime_cannot_restart_a_used_group(self):
        a = self.add("a")
        first = Runtime(self.group)
        await first.start()
        await first.wait()
        second = Runtime(self.group)
        with self.assertRaises(RuntimeFailure):
            await second.start()
        self.assertEqual(a.events, ["start", "run", "stop"])

    async def test_eager_task_factory_preserves_lifecycle_and_results(self):
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        self.add("a", "b", child=True)
        self.add("b", child=True)
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            runtime = Runtime(self.group)
            await runtime.start()
            self.assertEqual(await runtime.wait(), {"a": "a", "b": "b"})
        finally:
            loop.set_task_factory(previous)
        self.assertEqual([key for key, phase in self.trace if phase == "stop"], ["a", "b"])

    async def test_partial_task_creation_failure_cleans_all_started_modules(self):
        self.add("a", child=True)
        self.add("b", child=True)
        original = asyncio.create_task

        def create(coro, *, name=None, **kwargs):
            if name == "ntk-module:b":
                raise RuntimeError("task creation failed")
            return original(coro, name=name, **kwargs)

        runtime = Runtime(self.group)
        with patch("asyncio.create_task", create):
            await runtime.start()
            with self.assertRaises(RuntimeFailure) as raised:
                await runtime.wait()
        self.assertEqual([(f.module_id, f.phase) for f in failures(raised.exception)], [("b", LifecyclePhase.RUN)])
        self.assertEqual([key for key, phase in self.trace if phase == "stop"], ["b", "a"])
