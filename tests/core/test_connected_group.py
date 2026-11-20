"""Real Runtime/ModuleGroup with cooperative modules and a controllable disk double."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import unittest

from nymph_toolkit.contracts import (
    BindingKey, BindingRecord, BindingState, ConnectionsLifecycleFailure,
    ConnectionsStateError, ContractKey, ContractSpec, LinkFailure,
    ModuleAdvertisement, ModuleExecutionState, ModuleKind, ModuleSpec,
    NoticeKind, OperatingState, OperationMode, OperationSpec,
    RegistryStateError, RuntimeFailure, RuntimeState, StorageFailure, Usage,
)
from nymph_toolkit.core import Connections, ModuleGroup, Runtime
from tests.doubles.connection_store import MemoryStore


KEY = ContractKey("test.echo", "1")
SPEC = ContractSpec(KEY, (OperationSpec("echo", OperationMode.SYNC),))
READY = Usage(OperatingState.RUNNING, True, 0, 1)
STOPPED = Usage(OperatingState.STOPPED, False, 0, 1)
BAD = Usage(OperatingState.FAILED, False, 0, 1)


class Module:
    def __init__(self, module_id, owner, *, provider=False):
        self.module_id = module_id
        self.owner = owner
        self.provider = provider
        self.stopped = False
        self.trigger = asyncio.Event()
        self.progressed = asyncio.Event()
        self.cleanup = asyncio.Event()
        self.interrupted = asyncio.Event()
        self.completed_cleanup = asyncio.Event()
        self.results = []
        self.run_error = None
        self.start_error = None
        self.bad_link = False

    def publish(self, usage=READY):
        self.owner.connections.publish_usage(self.module_id, usage, contracts={KEY: usage} if self.provider else None)

    async def start(self):
        self.publish()
        if self.start_error is not None:
            raise self.start_error

    def echo(self, value):
        if self.bad_link:
            self.owner.connections.publish_usage(self.module_id, READY, contracts={KEY: BAD})
            raise OSError("provider link failure")
        return value

    async def run(self):
        while True:
            await self.trigger.wait()
            self.trigger.clear()
            if self.run_error is not None:
                raise self.run_error
            if self.module_id == "a":
                result = await self.owner.connections.invoke(BindingKey("a", KEY), "echo", wait_timeout=5, args=("activity",))
                self.results.append(result)
                self.progressed.set()
                if isinstance(result, LinkFailure):
                    while True:
                        notice = await self.owner.connections.next_notice("a")
                        if notice.kind == NoticeKind.INTERRUPT:
                            break
                    self.interrupted.set()
                    await self.cleanup.wait()
                    self.owner.connections.acknowledge_interruption("a", notice.notice_id)
                    self.completed_cleanup.set()
            else:
                self.results.append("independent")
                self.progressed.set()

    async def stop(self):
        self.stopped = True
        if self.owner.store.failure is None:
            self.publish(STOPPED)


class ConnectedGroupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemoryStore((BindingRecord(BindingKey("a", KEY), "b"),))
        self.group = ModuleGroup()
        self.connections = Connections(self.group, self.store)
        self.modules = {name: Module(name, self, provider=name == "b") for name in ("a", "b", "e")}
        for name, module in self.modules.items():
            self.group.register(ModuleSpec(name, ModuleKind.SUBSYSTEM), module)
            self.connections.declare(ModuleAdvertisement(name, "1", (SPEC,) if name == "b" else ()),
                                     {KEY: {"echo": module.echo}} if name == "b" else None)
        self.group.attach_connections(self.connections)
        self.runtime = Runtime(self.group)

    async def asyncTearDown(self):
        try:
            await self.runtime.stop()
        except RuntimeFailure:
            pass
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()
                   and not t.done() and t.get_name().startswith("ntk-")]
        self.assertEqual(pending, [])

    async def wait(self, event):
        await asyncio.wait_for(event.wait(), 5)

    async def test_startup_validation_follows_module_state_initialization(self):
        await self.runtime.start()
        self.assertEqual(self.connections.connection(BindingKey("a", KEY)).state, BindingState.VALID)
        self.assertEqual(self.store.bindings, (BindingRecord(BindingKey("a", KEY), "b"),))
        with self.assertRaises(RegistryStateError):
            self.group.attach_connections(self.connections)
        self.modules["a"].trigger.set()
        await self.wait(self.modules["a"].progressed)
        self.assertEqual(self.modules["a"].results, ["activity"])
        await self.runtime.stop()
        self.assertTrue(all(m.stopped for m in self.modules.values()))

    async def test_requester_cooperates_while_unrelated_module_keeps_working(self):
        await self.runtime.start()
        a, b, e = (self.modules[name] for name in ("a", "b", "e"))
        b.bad_link = True
        a.trigger.set()
        await self.wait(a.interrupted)
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.INTERRUPTING)
        self.assertIsInstance(a.results[0], LinkFailure)
        self.assertEqual(self.runtime.state, RuntimeState.RUNNING)
        e.trigger.set()
        await self.wait(e.progressed)
        self.assertEqual(e.results, ["independent"])
        self.assertFalse(a.completed_cleanup.is_set())
        a.cleanup.set()
        await self.wait(a.completed_cleanup)
        b.bad_link = False
        b.publish()
        await self.connections.health_check(module_ids=("b",))
        self.assertEqual(len(a.results), 1)
        a.progressed.clear()
        a.trigger.set()
        await self.wait(a.progressed)
        self.assertEqual(a.results[1:], ["activity"])

    async def test_fatal_storage_error_terminates_runtime_and_cleans_modules(self):
        await self.runtime.start()
        self.store.failure = StorageFailure(OSError("rescue failed"), 3, False)
        self.store.admitting = False
        self.store.pulse()
        self.store.failed.set()
        with self.assertRaises(RuntimeFailure) as raised:
            await asyncio.wait_for(self.runtime.wait(), 5)
        infrastructure = raised.exception.failures[0].exception
        self.assertIsInstance(infrastructure, ConnectionsLifecycleFailure)
        self.assertIs(infrastructure.failures[0].exception, self.store.failure)
        self.assertTrue(all(m.stopped for m in self.modules.values()))

    async def test_ordinary_unhandled_module_failure_still_stops_group(self):
        await self.runtime.start()
        self.modules["e"].run_error = ValueError("ordinary service run failure")
        self.modules["e"].trigger.set()
        with self.assertRaises(RuntimeFailure):
            await self.runtime.wait()
        self.assertTrue(all(m.stopped for m in self.modules.values()))

    async def test_partial_module_start_failure_closes_connection_infrastructure(self):
        self.modules["b"].start_error = ValueError("partial initialization")
        with self.assertRaises(RuntimeFailure):
            await self.runtime.start()
        self.assertTrue(self.modules["a"].stopped)
        self.assertTrue(self.modules["b"].stopped)
        self.assertFalse(self.modules["e"].stopped)
        self.assertEqual(self.connections.state, RuntimeState.STOPPED)

    async def test_health_request_racing_runtime_stop_is_not_left_pending(self):
        await self.runtime.start()
        health = asyncio.create_task(self.connections.health_check())
        await asyncio.sleep(0)
        await self.runtime.stop()
        try:
            await asyncio.wait_for(health, 5)
        except ConnectionsStateError:
            pass
        self.assertTrue(health.done())

    async def test_eager_task_factory_preserves_ownership_and_cleanup(self):
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            await self.runtime.start()
            self.modules["a"].trigger.set()
            await self.wait(self.modules["a"].progressed)
            self.assertEqual(self.modules["a"].results, ["activity"])
            await self.connections.health_check()
            await self.runtime.stop()
        finally:
            loop.set_task_factory(previous)
        self.assertTrue(all(module.stopped for module in self.modules.values()))

    async def test_module_and_infrastructure_cleanup_failures_are_both_retained(self):
        module_error = ValueError("module cleanup")
        core_error = OSError("storage cleanup")
        async def module_stop():
            self.modules["b"].stopped = True
            raise module_error
        async def storage_stop():
            raise core_error
        self.modules["b"].stop = module_stop
        self.store.stop = storage_stop
        await self.runtime.start()
        with self.assertRaises(RuntimeFailure) as raised:
            await self.runtime.stop()
        combined = raised.exception.failures[0].exception
        self.assertIsInstance(combined, ExceptionGroup)
        self.assertIs(combined.exceptions[0].failures[0].exception, module_error)
        self.assertIs(combined.exceptions[1].failures[0].exception, core_error)
        self.assertTrue(all(module.stopped for module in self.modules.values()))


if __name__ == "__main__":
    unittest.main()
