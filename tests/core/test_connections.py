"""Behavioral connection tests with independently controlled persistence and providers."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import unittest

from nymph_toolkit.contracts import (
    BindingKey, BindingRecord, BindingState, ConnectionConflictError,
    ConnectionNotReadyError, ConnectionsStateError, ConnectionUnavailableError,
    ContractDeclarationError, ContractKey, ContractSpec, LinkFailure,
    ModuleAdvertisement, ModuleExecutionState, ModuleKind, ModuleSpec, NoticeKind,
    OperatingState, OperationFailure, OperationMode, OperationSpec,
    PreparationTimeoutError, RuntimeState, TemporaryUnavailable, Usage,
)
from nymph_toolkit.core import Registry, Runtime
from nymph_toolkit.core.connections import Connections
from tests.doubles.connection_store import MemoryStore


READ = ContractKey("memory.read", "1")
READ_SPEC = ContractSpec(READ, (OperationSpec("get", OperationMode.SYNC),))
ASYNC = ContractKey("memory.async", "1")
ASYNC_SPEC = ContractSpec(ASYNC, (OperationSpec("get", OperationMode.ASYNC),))
READY = Usage(OperatingState.RUNNING, True, 0, 4)
FAILED = Usage(OperatingState.FAILED, False, 0, 4)


class ConnectionsTests(unittest.IsolatedAsyncioTestCase):
    def make(self, store=None):
        registry = Registry()
        store = store or MemoryStore()
        connections = Connections(registry, store)
        self.calls = 0
        self.mode = "normal"
        self.async_gate = None

        def read(value):
            self.calls += 1
            if self.mode == "error":
                connections.publish_usage("b", READY, contracts={READ: FAILED})
                raise OSError("link broken")
            if self.mode == "full":
                return TemporaryUnavailable("full")
            if self.mode == "missing":
                return OperationFailure("not_found", value)
            if self.mode == "wrong_mode":
                return asyncio.sleep(0)
            if self.mode == "cancel_sync":
                raise asyncio.CancelledError
            return "stored:" + value

        async def read_async(value):
            if self.async_gate is not None:
                await self.async_gate.wait()
            return "async:" + value

        for module_id in ("a", "b", "c", "d", "e", "f"):
            registry.register(ModuleSpec(module_id, ModuleKind.SUBSYSTEM))
            provides = module_id in ("b", "f")
            ad = ModuleAdvertisement(module_id, "7" if module_id == "f" else "1", (READ_SPEC, ASYNC_SPEC) if provides else (),
                                     tags={module_id}, attributes={"cost": 1 if module_id == "b" else 2})
            connections.declare(ad, {READ: {"get": read}, ASYNC: {"get": read_async}} if provides else None)
            connections.publish_usage(module_id, READY, contracts={READ: READY, ASYNC: READY} if provides else None)
        self.registry, self.store, self.connections = registry, store, connections
        self.runtime = Runtime(connections)

    async def asyncSetUp(self):
        self.make()

    async def asyncTearDown(self):
        if self.runtime.state != RuntimeState.NEW:
            await self.runtime.stop()
        leaked = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()
                  and not t.done() and t.get_name().startswith("ntk-")]
        self.assertEqual(leaked, [])

    async def start_and_bind(self, requester="a", provider="b", contract=READ):
        if self.runtime.state == RuntimeState.NEW:
            await self.runtime.start()
        snapshot = await self.connections.bind(requester, contract, provider, wait_timeout=5)
        return snapshot.key

    async def test_candidate_list_keeps_attributes_and_unavailable_providers(self):
        before = self.connections.candidates(READ)
        self.connections.publish_usage("b", FAILED, contracts={READ: FAILED})
        after = self.connections.candidates(READ)
        self.assertEqual([c.advertisement.module_id for c in after], ["b", "f"])
        self.assertEqual(before[0].module_usage, READY)
        self.assertEqual(after[0].module_usage, FAILED)
        self.assertEqual(after[1].advertisement.attributes["cost"], 2)
        self.assertEqual(self.connections.candidates(ContractKey("memory.read", "1.0")), ())
        await self.runtime.start()
        chosen = min((c for c in after if c.module_usage.state == OperatingState.RUNNING),
                     key=lambda c: c.advertisement.attributes["cost"])
        bound = await self.connections.bind("a", READ, chosen.advertisement.module_id, wait_timeout=5)
        self.assertEqual(bound.provider_id, "f")

    async def test_direct_and_mediated_calls_do_not_repeat_catalog_queries(self):
        key = await self.start_and_bind()
        handle = await self.connections.prepare(key, wait_timeout=0)
        def forbidden(*args):
            self.fail("normal calls must not rediscover the provider")
        self.registry.get = forbidden
        self.assertEqual(handle.call("get", "x"), "stored:x")
        self.assertEqual(handle.call("get", "y"), "stored:y")
        self.assertEqual(await self.connections.invoke(key, "get", wait_timeout=0, args=("z",)), "stored:z")
        self.assertEqual(self.calls, 3)

    async def test_fixed_binding_is_idempotent_and_conflicts_are_not_overwritten(self):
        key = await self.start_and_bind()
        self.assertEqual((await self.connections.bind("a", READ, "b", wait_timeout=5)).key, key)
        with self.assertRaises(ConnectionConflictError):
            await self.connections.bind("a", READ, "f", wait_timeout=5)
        self.assertEqual(self.store.bindings, (BindingRecord(key, "b"),))
        other = await self.connections.bind("c", READ, "f", wait_timeout=5)
        self.assertEqual(other.provider_id, "f")

    async def test_failed_initial_target_is_not_saved_and_can_be_reselected(self):
        await self.runtime.start()
        self.connections.publish_usage("b", FAILED)
        with self.assertRaises(ConnectionUnavailableError):
            await self.connections.bind("a", READ, "b", wait_timeout=5)
        self.assertEqual(self.store.bindings, ())
        self.assertEqual((await self.connections.bind("a", READ, "f", wait_timeout=5)).provider_id, "f")

    async def test_concurrent_initial_requests_have_one_durable_winner(self):
        await self.runtime.start()
        self.store.save_gate = asyncio.Event()
        first = asyncio.create_task(self.connections.bind("a", READ, "b", wait_timeout=5))
        await self.store.save_entered.wait()
        second = asyncio.create_task(self.connections.bind("a", READ, "f", wait_timeout=5))
        await asyncio.sleep(0)
        self.assertFalse(first.done())
        self.assertFalse(second.done())
        self.store.save_gate.set()
        await first
        with self.assertRaises(ConnectionConflictError):
            await second
        self.assertEqual(self.store.bindings[0].provider_id, "b")

    async def test_repeated_cancellation_does_not_split_commit_or_unlock_early(self):
        await self.runtime.start()
        self.store.save_gate = asyncio.Event()
        bind = asyncio.create_task(self.connections.bind("a", READ, "b", wait_timeout=5))
        await self.store.save_entered.wait()
        bind.cancel()
        await asyncio.sleep(0)
        bind.cancel()
        await asyncio.sleep(0)
        self.assertFalse(bind.done())
        self.store.save_gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await bind
        self.assertEqual(self.connections.connection(BindingKey("a", READ)).provider_id, "b")
        self.assertEqual(self.store.bindings[0].provider_id, "b")

    async def test_startup_reuses_valid_and_discards_invalid_saved_connections(self):
        valid = BindingRecord(BindingKey("a", READ), "f")
        invalid = BindingRecord(BindingKey("c", READ), "absent")
        self.make(MemoryStore((valid, invalid)))
        await self.runtime.start()
        self.assertEqual(self.connections.connection(valid.key).provider_id, "f")
        self.assertEqual(self.store.bindings, (valid,))
        self.assertEqual((await self.connections.bind("c", READ, "b", wait_timeout=5)).provider_id, "b")

    async def test_expected_failure_and_capacity_result_do_not_interrupt(self):
        key = await self.start_and_bind()
        handle = await self.connections.prepare(key, wait_timeout=0)
        self.mode = "full"
        self.assertIsInstance(handle.call("get", "x"), TemporaryUnavailable)
        self.mode = "missing"
        self.assertIsInstance(handle.call("get", "x"), OperationFailure)
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.RUNNING)
        self.assertFalse(any(kind == "health_requested" for kind, data in self.store.records))

    async def test_link_error_cooperatively_interrupts_a_and_invalidates_only_affected_contract(self):
        key = await self.start_and_bind()
        c = (await self.connections.bind("c", READ, "b", wait_timeout=5)).key
        d = (await self.connections.bind("d", ASYNC, "b", wait_timeout=5)).key
        handle = await self.connections.prepare(key, wait_timeout=0)
        self.mode = "error"
        result = handle.call("get", "x")
        self.assertIsInstance(result, LinkFailure)
        notice = await self.connections.next_notice("a")
        self.assertEqual(notice.kind, NoticeKind.INTERRUPT)
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.INTERRUPTING)
        await self.connections.health_check(module_ids=("b",))
        self.assertEqual(self.connections.connection(c).state, BindingState.INVALID)
        self.assertEqual(self.connections.connection(d).state, BindingState.VALID)
        self.assertEqual((await self.connections.next_notice("c")).kind, NoticeKind.INVALIDATED)
        for module_id in ("b", "c", "d", "e"):
            self.assertEqual(self.connections.module_state(module_id), ModuleExecutionState.RUNNING)
        with self.assertRaises(ConnectionNotReadyError):
            handle.call("get", "x")
        self.assertEqual(self.calls, 1)

    async def test_negative_check_keeps_new_request_waiting_then_resumes_without_replay(self):
        key = await self.start_and_bind()
        handle = await self.connections.prepare(key, wait_timeout=0)
        self.mode = "error"
        failure = handle.call("get", "x")
        self.assertTrue(self.connections.acknowledge_interruption("a", failure.interruption_id))
        waiting = asyncio.create_task(self.connections.prepare(key, wait_timeout=5))
        await self.connections.health_check(module_ids=("b",))
        self.assertFalse(waiting.done())
        with self.assertRaises(PreparationTimeoutError):
            await self.connections.prepare(key, wait_timeout=0)
        self.mode = "normal"
        self.connections.publish_usage("b", READY, contracts={READ: READY})
        self.assertFalse(waiting.done())
        await self.connections.health_check(module_ids=("b",))
        resumed = await waiting
        self.assertEqual(self.calls, 1)
        self.assertEqual(resumed.call("get", "new"), "stored:new")
        self.assertEqual(self.calls, 2)

    async def test_health_alone_and_stale_ack_do_not_resume_a(self):
        key = await self.start_and_bind()
        first = self.connections.report_link_error(key, OSError("one"))
        second = self.connections.report_link_error(key, OSError("two"))
        self.assertFalse(self.connections.acknowledge_interruption("a", first))
        await self.connections.health_check(bindings=(key,))
        with self.assertRaises(PreparationTimeoutError):
            await self.connections.prepare(key, wait_timeout=0)
        self.assertTrue(self.connections.acknowledge_interruption("a", second))
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.SUSPENDED)
        await self.connections.prepare(key, wait_timeout=0)
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.RUNNING)

    async def test_every_health_request_is_completed_independently(self):
        key = await self.start_and_bind()
        results = await asyncio.gather(*(self.connections.health_check(bindings=(key,)) for _ in range(8)))
        self.assertEqual(len({r.request_id for r in results}), 8)
        self.assertTrue(all(r.connections[0].healthy for r in results))
        self.assertEqual(sum(kind == "health_completed" for kind, data in self.store.records), 8)
        self.assertEqual(self.connections.connection(key).state, BindingState.VALID)

    async def test_registration_replacement_invalidates_old_instance(self):
        key = await self.start_and_bind()
        self.registry.unregister("b")
        self.registry.register(ModuleSpec("b", ModuleKind.SUBSYSTEM))
        await self.connections.health_check()
        self.assertEqual(self.connections.connection(key).state, BindingState.INVALID)
        self.assertEqual([c.advertisement.module_id for c in self.connections.candidates(READ)], ["f"])
        with self.assertRaises(ContractDeclarationError):
            self.connections.publish_usage("b", READY)

    async def test_async_operation_and_caller_cancellation(self):
        key = await self.start_and_bind(contract=ASYNC)
        handle = await self.connections.prepare(key, wait_timeout=0)
        self.assertEqual(await handle.acall("get", "x"), "async:x")
        self.async_gate = asyncio.Event()
        call = asyncio.create_task(handle.acall("get", "wait"))
        await asyncio.sleep(0)
        call.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await call
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.RUNNING)
        self.assertFalse(any(kind == "health_requested" for kind, data in self.store.records))

    async def test_bad_client_operation_is_distinct_from_bad_provider_mode(self):
        key = await self.start_and_bind()
        handle = await self.connections.prepare(key, wait_timeout=0)
        with self.assertRaises(ContractDeclarationError):
            handle.call("missing", "x")
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.RUNNING)
        self.mode = "wrong_mode"
        self.assertIsInstance(handle.call("get", "x"), LinkFailure)
        self.assertEqual(self.connections.module_state("a"), ModuleExecutionState.INTERRUPTING)

    async def test_wait_cancellation_is_local_and_shutdown_wakes_waiters(self):
        key = await self.start_and_bind()
        self.connections.publish_usage("b", FAILED)
        await self.connections.health_check()
        one = asyncio.create_task(self.connections.prepare(key, wait_timeout=5))
        two = asyncio.create_task(self.connections.prepare(key, wait_timeout=5))
        await asyncio.sleep(0)
        one.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await one
        self.assertFalse(two.done())
        await self.runtime.stop()
        with self.assertRaises(ConnectionsStateError):
            await two

    async def test_unexpected_sync_cancellation_is_a_link_failure(self):
        key = await self.start_and_bind()
        handle = await self.connections.prepare(key, wait_timeout=0)
        self.mode = "cancel_sync"
        result = handle.call("get", "x")
        self.assertIsInstance(result, LinkFailure)
        self.assertIsInstance(result.exception.__cause__, asyncio.CancelledError)
        self.assertEqual(self.runtime.state, RuntimeState.RUNNING)

    async def test_new_binding_wait_has_deadline_and_closing_wakes_it(self):
        await self.runtime.start()
        self.store.admitting = False
        with self.assertRaises(PreparationTimeoutError):
            await self.connections.bind("a", READ, "b", wait_timeout=0)
        waiting = asyncio.create_task(self.connections.bind("a", READ, "b", wait_timeout=5))
        await asyncio.sleep(0)
        await self.runtime.stop()
        with self.assertRaises(ConnectionsStateError):
            await waiting
        self.assertEqual(self.store.bindings, ())

    async def test_cancelling_health_request_does_not_cancel_its_check(self):
        key = await self.start_and_bind()
        health = asyncio.create_task(self.connections.health_check(bindings=(key,)))
        await asyncio.sleep(0)
        health.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await health
        result = await self.connections.health_check(bindings=(key,))
        self.assertTrue(result.connections[0].healthy)
        self.assertEqual(sum(kind == "health_requested" for kind, data in self.store.records), 2)
        self.assertEqual(sum(kind == "health_completed" for kind, data in self.store.records), 2)


if __name__ == "__main__":
    unittest.main()
