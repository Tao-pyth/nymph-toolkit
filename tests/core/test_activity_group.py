"""Activity ownership must preserve module resources and the connection lifecycle."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import unittest

from nymph_toolkit.contracts import (
    ActivityKey, ActivityRequest, ActivityState, ContractKey, ContractSpec,
    ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, OperationMode,
    OperationSpec, RegistryStateError, RuntimeFailure, RuntimeState, RuntimeStateError,
    TaskManagerLifecycleFailure, Usage,
)
from nymph_toolkit.core import Connections, ModuleGroup, Runtime, TaskManager
from tests.doubles.connection_store import MemoryStore


CONTRACT = ContractKey("echo", "1")
SPEC = ContractSpec(CONTRACT, (OperationSpec("echo", OperationMode.ASYNC),))


class ActivityGroupTests(unittest.IsolatedAsyncioTestCase):
    def configure(self, nymph_run, *, store=None, provider_run=None, max_running=None):
        group = ModuleGroup()
        store = MemoryStore() if store is None else store
        links = Connections(group, store)
        manager = TaskManager(links, clock_check_interval=0.01, max_running=max_running)
        trace = []
        closed = set()
        class Module:
            def __init__(self, module_id):
                self.module_id = module_id
            async def start(self):
                trace.append((self.module_id, "start"))
                usage = Usage(OperatingState.RUNNING, True, 0, 1)
                links.publish_usage(self.module_id, usage,
                                    contracts={CONTRACT: usage} if self.module_id == "provider" else {})
            async def run(self):
                if self.module_id == "nymph":
                    return await nymph_run(manager, links, trace, closed)
                if provider_run is not None:
                    return await provider_run()
            async def stop(self):
                trace.append((self.module_id, "stop"))
                closed.add(self.module_id)
                links.publish_usage(self.module_id, Usage(OperatingState.STOPPED, False, 0, 1))
        async def echo(value):
            self.assertNotIn("provider", closed)
            return value
        group.register(ModuleSpec("provider", ModuleKind.SUBSYSTEM), Module("provider"))
        group.register(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, frozenset({"provider"})), Module("nymph"))
        links.declare(ModuleAdvertisement("provider", "1", (SPEC,)), {CONTRACT: {"echo": echo}})
        links.declare(ModuleAdvertisement("nymph", "1", ()))
        group.attach_connections(links)
        group.attach_task_manager(manager)
        return group, manager, links, store, trace, closed

    async def asyncTearDown(self):
        await asyncio.sleep(0)
        remaining = [task.get_name() for task in asyncio.all_tasks()
                     if task is not asyncio.current_task() and task.get_name().startswith("ntk-")]
        self.assertEqual(remaining, [])

    async def test_activity_uses_existing_allowed_connection_and_normal_group_completion(self):
        async def nymph(manager, links, trace, closed):
            binding = await links.bind("nymph", CONTRACT, "provider", wait_timeout=1)
            async def execute(context):
                prepared = await links.prepare(binding.key, wait_timeout=1)
                return await prepared.acall("echo", {"result": context.request.content})
            request = ActivityRequest(ActivityKey("nymph", "a"), "調査", None, timedelta(hours=2))
            manager.submit(request, execute)
            result = await manager.wait(request.key)
            self.assertEqual(result.state, ActivityState.COMPLETED)
            self.assertEqual(result.result["result"], "調査")
            return "nymph complete"
        group, manager, links, store, trace, closed = self.configure(nymph)
        runtime = Runtime(group)
        await runtime.start()
        result = await asyncio.wait_for(runtime.wait(), 2)
        self.assertEqual(result["nymph"], "nymph complete")
        self.assertEqual(runtime.state, RuntimeState.STOPPED)
        self.assertEqual(manager.state, RuntimeState.STOPPED)
        self.assertEqual(closed, {"nymph", "provider"})
        self.assertTrue(any(kind == "activity_v06_state_changed" for kind, _ in store.records))

    async def test_shutdown_runs_activity_cleanup_before_destroying_provider_resources(self):
        entered = asyncio.Event()
        async def nymph(manager, links, trace, closed):
            async def execute(context):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    self.assertNotIn("provider", closed)
                    self.assertNotIn("nymph", closed)
                    trace.append(("activity", "cleanup"))
                    await asyncio.sleep(0)
            request = ActivityRequest(ActivityKey("nymph", "a"), "調査", None, timedelta(hours=2))
            manager.submit(request, execute)
            try:
                await asyncio.Event().wait()
            finally:
                result = await manager.wait(request.key)
                self.assertEqual(result.state, ActivityState.STOPPED)
                trace.append(("nymph", "run cleanup"))
        group, manager, links, store, trace, closed = self.configure(nymph)
        runtime = Runtime(group)
        await runtime.start()
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(runtime.stop(), 2)
        self.assertLess(trace.index(("activity", "cleanup")), trace.index(("provider", "stop")))
        self.assertLess(trace.index(("nymph", "run cleanup")), trace.index(("nymph", "stop")))
        terminal = [record for kind, record in store.records if kind == "activity_v06_state_changed"][-1]
        self.assertEqual(terminal["state"], "stopped")
        self.assertEqual(terminal["finish_reason"], "runtime")

    async def test_task_manager_start_failure_cleans_initialized_modules_and_storage(self):
        async def nymph(*args):
            self.fail("run must not begin")
        group, manager, links, store, trace, closed = self.configure(nymph)
        original_start = manager.start
        failure = ValueError("partial activity initialization")
        async def fail_start():
            await original_start()
            raise failure
        manager.start = fail_start
        runtime = Runtime(group)
        with self.assertRaises(RuntimeFailure) as caught:
            await runtime.start()
        self.assertIsInstance(caught.exception.failures[0].exception, TaskManagerLifecycleFailure)
        self.assertIs(caught.exception.failures[0].exception.failures[0].exception, failure)
        self.assertEqual(closed, {"nymph", "provider"})
        self.assertFalse(store.admitting)
        self.assertEqual(manager.state, RuntimeState.STOPPED)

    async def test_internal_record_failure_is_reported_as_core_failure_and_does_not_leak(self):
        failure = OSError("history owner unavailable")
        class BrokenStore(MemoryStore):
            def append(self, kind, data):
                if kind.startswith("activity_"):
                    raise failure
                super().append(kind, data)
        async def nymph(manager, links, trace, closed):
            request = ActivityRequest(ActivityKey("nymph", "a"), "調査", None, timedelta(seconds=1))
            async def execute(context):
                self.fail("unrecorded activity must not execute")
            with self.assertRaises(OSError):
                manager.submit(request, execute)
            await asyncio.Event().wait()
        group, manager, links, store, trace, closed = self.configure(nymph, store=BrokenStore())
        runtime = Runtime(group)
        await runtime.start()
        with self.assertRaises(RuntimeFailure) as caught:
            await asyncio.wait_for(runtime.wait(), 2)
        self.assertIsInstance(caught.exception.failures[0].exception, TaskManagerLifecycleFailure)
        self.assertEqual(closed, {"nymph", "provider"})
        self.assertFalse(store.admitting)

    async def test_attachment_must_match_configured_connections_and_precede_start(self):
        async def nymph(*args):
            return None
        group, manager, links, store, trace, closed = self.configure(nymph)
        with self.assertRaises(RegistryStateError):
            group.attach_task_manager(manager)
        other = ModuleGroup()
        with self.assertRaises(TypeError):
            other.attach_task_manager(manager)
        runtime = Runtime(group)
        await runtime.start()
        await runtime.wait()
        with self.assertRaises(RegistryStateError):
            group.attach_task_manager(manager)

    async def test_normal_activity_failure_is_visible_without_failing_the_runtime(self):
        failure = ValueError("business execution failed")
        async def nymph(manager, links, trace, closed):
            async def execute(context):
                raise failure
            request = ActivityRequest(ActivityKey("nymph", "a"), "調査", None, timedelta(hours=1))
            manager.submit(request, execute)
            result = await manager.wait(request.key)
            self.assertIs(result.failures[0].exception, failure)
            return result.state.value
        group, manager, links, store, trace, closed = self.configure(nymph)
        runtime = Runtime(group)
        await runtime.start()
        results = await asyncio.wait_for(runtime.wait(), 2)
        self.assertEqual(results["nymph"], "failed")
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    async def test_requested_runtime_stop_during_activity_initialization_is_not_a_failure(self):
        entered = asyncio.Event()
        async def nymph(*args):
            self.fail("run must not begin")
        group, manager, links, store, trace, closed = self.configure(nymph)
        original_start = manager.start
        async def start():
            await original_start()
            entered.set()
            await asyncio.Event().wait()
        manager.start = start
        runtime = Runtime(group)
        starting = asyncio.create_task(runtime.start())
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(runtime.stop(), 1)
        with self.assertRaises(RuntimeStateError):
            await starting
        self.assertEqual(runtime.state, RuntimeState.STOPPED)
        self.assertEqual(manager.state, RuntimeState.STOPPED)
        self.assertEqual(closed, {"nymph", "provider"})

    async def test_failed_stop_task_factory_still_runs_both_cleanup_paths_concurrently(self):
        entered, module_cleanup = asyncio.Event(), asyncio.Event()
        async def nymph(manager, links, trace, closed):
            async def execute(context):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    await module_cleanup.wait()
            request = ActivityRequest(ActivityKey("nymph", "a"), "調査", None, timedelta(hours=1))
            manager.submit(request, execute)
            try:
                await asyncio.Event().wait()
            finally:
                module_cleanup.set()
                await manager.wait(request.key)
        group, manager, links, store, trace, closed = self.configure(nymph)
        runtime = Runtime(group)
        await runtime.start()
        await asyncio.wait_for(entered.wait(), 1)
        failure = ValueError("factory failed before activity stop task was created")
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        def factory(loop, coroutine, **kwargs):
            if coroutine.cr_code is TaskManager.stop.__code__:
                raise failure
            return asyncio.Task(coroutine, loop=loop, **kwargs)
        loop.set_task_factory(factory)
        try:
            with self.assertRaises(RuntimeFailure) as caught:
                await asyncio.wait_for(runtime.stop(), 2)
            reported = caught.exception.failures[-1].exception
            self.assertIsInstance(reported, TaskManagerLifecycleFailure)
            self.assertIs(reported.failures[0].exception, failure)
            self.assertTrue(module_cleanup.is_set())
            self.assertEqual(manager.state, RuntimeState.STOPPED)
            self.assertEqual(closed, {"nymph", "provider"})
        finally:
            loop.set_task_factory(previous)
