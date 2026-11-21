"""Real child processes integrate with Registry, Connections and owned storage."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import tempfile
import unittest

from nymph_toolkit.contracts import (
    ContractSpec, HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, OperationMode,
    OperationSpec, Placement, RuntimeFailure, OperationFailure, TemporaryUnavailable,
)
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from tests.doubles.hybrid import KEY

CONTRACT = ContractSpec(KEY, tuple(OperationSpec(name, OperationMode.ASYNC) for name in
                                  ("echo", "request", "received", "failure", "crash", "stream", "activity")))


class HybridGroupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtimes = []

    def group(self):
        root = Path(self.temp.name) / str(len(self.runtimes))
        store = FileStore(root / "main", root / "archive", retention=timedelta(days=1), batch_size=10, flush_interval=.01)
        return HybridGroup(HybridSettings(5, .3, 2, 65536, 32, 8), store)

    def register(self, group, module_id, placement, **config):
        group.register_module(ModuleSpec(module_id, ModuleKind.SUBSYSTEM),
                              ModuleAdvertisement(module_id, "dummy-v1", (CONTRACT,)),
                              "tests.doubles.hybrid:factory", {"provider": True, **config}, placement)

    async def start(self, group):
        runtime = Runtime(group)
        self.runtimes.append(runtime)
        await asyncio.wait_for(runtime.start(), 8)
        return runtime

    async def asyncTearDown(self):
        for runtime in self.runtimes:
            try:
                await asyncio.wait_for(runtime.stop(), 5)
            except RuntimeFailure:
                pass

    async def test_four_placements_direct_calls_and_streams(self):
        for requester in Placement:
            for provider in Placement:
                with self.subTest(requester=requester, provider=provider):
                    group = self.group()
                    self.register(group, "requester", requester)
                    self.register(group, "provider", provider)
                    runtime = await self.start(group)
                    result = await group.modules["requester"].invoke("invoke", {
                        "contract": KEY, "operation": "request", "args": ["provider", True], "kwargs": {}})
                    self.assertEqual(result["value"], "from requester")
                    self.assertEqual(result["pid"] == os.getpid(), provider == Placement.LOCAL)
                    received = await group.modules["provider"].invoke("invoke", {
                        "contract": KEY, "operation": "received", "args": [], "kwargs": {}})
                    self.assertEqual(received, ["dummy bytes"])
                    # A reverse direction has a separate binding and stream.
                    reverse = await group.modules["provider"].invoke("invoke", {
                        "contract": KEY, "operation": "request", "args": ["requester", True], "kwargs": {}})
                    self.assertEqual(reverse["value"], "from requester")
                    await runtime.stop()
                    for service in group.modules.values():
                        self.assertTrue(service.snapshot.cleanup_confirmed)
                        if service.process:
                            self.assertIsNotNone(service.process.returncode)

    async def test_business_and_capacity_results_are_not_link_failures(self):
        group = self.group()
        self.register(group, "requester", Placement.LOCAL)
        self.register(group, "provider", Placement.PROCESS)
        await self.start(group)
        core = group.client("requester")
        await core.bind(KEY, "provider", timeout=2)
        link = await core.prepare(KEY, timeout=2)
        self.assertIsInstance(await link.acall("failure", "business", timeout=2), OperationFailure)
        self.assertIsInstance(await link.acall("failure", "capacity", timeout=2), TemporaryUnavailable)
        self.assertEqual(group.connections.module_state("requester").value, "running")

    async def test_initialization_failure_and_deadline_owned_child_cleanup(self):
        group = self.group()
        self.register(group, "bad", Placement.PROCESS, start_failure=True)
        with self.assertRaises(RuntimeFailure):
            await self.start(group)
        self.assertIsNotNone(group.modules["bad"].process.returncode)

    async def test_stop_deadline_forces_only_owned_child_and_marks_unknown_cleanup(self):
        group = self.group()
        self.register(group, "stuck", Placement.PROCESS, stuck_stop=True)
        runtime = await self.start(group)
        await asyncio.wait_for(runtime.stop(), 3)
        snapshot = group.process("stuck")
        self.assertFalse(snapshot.cleanup_confirmed)
        self.assertIsNotNone(snapshot.returncode)

    async def test_child_run_failure_stops_runtime(self):
        group = self.group()
        self.register(group, "bad", Placement.PROCESS, run_failure=True)
        runtime = await self.start(group)
        with self.assertRaises(RuntimeFailure):
            await asyncio.wait_for(runtime.wait(), 4)
        self.assertIsNotNone(group.modules["bad"].process.returncode)

    async def test_core_mediated_call_and_failure_updates_cached_route(self):
        from nymph_toolkit.contracts import ConnectionNotReadyError, LinkFailure
        group = self.group()
        self.register(group, "requester", Placement.LOCAL)
        self.register(group, "provider", Placement.PROCESS)
        await self.start(group)
        core = group.client("requester")
        await core.bind(KEY, "provider", timeout=2)
        link = await core.prepare(KEY, timeout=2)
        self.assertEqual((await core.invoke(KEY, "echo", "through core", timeout=2))["value"], "through core")
        failed = await link.acall("failure", "unexpected", timeout=2)
        self.assertIsInstance(failed, LinkFailure)
        with self.assertRaises(ConnectionNotReadyError):
            await link.acall("echo", "blocked", timeout=2)
        self.assertEqual(group.connections.module_state("provider").value, "running")
        await link.close()

    async def test_stream_failure_reports_link_error_but_abort_does_not(self):
        from nymph_toolkit.contracts import StreamOptions, OverflowPolicy
        group = self.group()
        self.register(group, "requester", Placement.LOCAL)
        self.register(group, "provider", Placement.PROCESS)
        await self.start(group)
        core = group.client("requester")
        await core.bind(KEY, "provider", timeout=2)
        link = await core.prepare(KEY, timeout=2)
        options = StreamOptions(16, 2, 16, 2, OverflowPolicy.WAIT)
        normal = await link.open_stream("stream", options, "wait", timeout=2)
        await normal.abort("owner cancelled")
        self.assertEqual(group.connections.module_state("requester").value, "running")
        failed = await link.open_stream("stream", options, "fail", timeout=2)
        async with asyncio.timeout(3):
            while group.connections.module_state("requester").value == "running":
                await asyncio.sleep(.005)
        self.assertEqual(failed.state.value, "failed")
        self.assertEqual(group.connections.module_state("provider").value, "running")

    async def test_start_timeout_and_lost_parent_channel_reap_owned_children(self):
        from dataclasses import replace
        group = self.group()
        group.settings = replace(group.settings, startup_timeout=.4)
        self.register(group, "slow", Placement.PROCESS, start_wait=True)
        with self.assertRaises(RuntimeFailure):
            await self.start(group)
        self.assertIsNotNone(group.modules["slow"].process.returncode)
        other = self.group()
        self.register(other, "child", Placement.PROCESS)
        runtime = await self.start(other)
        await other.modules["child"].peer.close()
        with self.assertRaises(RuntimeFailure):
            await asyncio.wait_for(runtime.wait(), 4)
        self.assertIsNotNone(other.modules["child"].process.returncode)

    async def test_dependency_order_partial_cleanup_and_contract_mismatch(self):
        trace = Path(self.temp.name) / "trace.txt"
        group = self.group()
        group.register_module(ModuleSpec("dependent", ModuleKind.ADAPTER, frozenset({"provider"})),
            ModuleAdvertisement("dependent", "v1", (CONTRACT,)), "tests.doubles.hybrid:factory",
            {"provider": True, "start_failure": True, "trace": str(trace)}, Placement.PROCESS)
        self.register(group, "provider", Placement.PROCESS, trace=str(trace))
        with self.assertRaises(RuntimeFailure):
            await self.start(group)
        self.assertEqual(trace.read_text(encoding="utf-8").splitlines(),
                         ["start:provider", "start:dependent", "stop:dependent", "stop:provider"])
        bad = self.group()
        self.register(bad, "bad", Placement.PROCESS, provider=False)
        with self.assertRaises(RuntimeFailure):
            await self.start(bad)
        self.assertFalse(bad.modules["bad"].ready.exception() is None)

    async def test_registration_boundary_and_restart_binding(self):
        from nymph_toolkit.contracts import RegistryStateError, BindingKey
        group = self.group()
        self.register(group, "removed", Placement.PROCESS)
        group.unregister("removed")
        self.assertNotIn("removed", group.modules)
        self.register(group, "requester", Placement.LOCAL)
        self.register(group, "provider", Placement.PROCESS)
        runtime = await self.start(group)
        with self.assertRaises(RegistryStateError):
            group.unregister("provider")
        await group.client("requester").bind(KEY, "provider", timeout=2)
        generation = group.process("provider").generation
        await runtime.stop()
        root = Path(self.temp.name) / "0"
        restored = HybridGroup(group.settings, FileStore(root / "main", root / "archive", retention=timedelta(days=1), batch_size=10, flush_interval=.01))
        self.register(restored, "requester", Placement.LOCAL)
        self.register(restored, "provider", Placement.PROCESS)
        await self.start(restored)
        self.assertNotEqual(restored.process("provider").generation, generation)
        self.assertEqual(restored.connections.connection(BindingKey("requester", KEY)).provider_id, "provider")

    async def test_stream_capacity_and_management_responsiveness_during_backpressure(self):
        from dataclasses import replace
        from nymph_toolkit.contracts import CapacityExceeded, StreamOptions, OverflowPolicy
        group = self.group()
        group.settings = replace(group.settings, max_streams=1)
        self.register(group, "requester", Placement.LOCAL)
        self.register(group, "provider", Placement.PROCESS)
        await self.start(group)
        core = group.client("requester")
        await core.bind(KEY, "provider", timeout=2)
        link = await core.prepare(KEY, timeout=2)
        sender = await link.open_stream("stream", StreamOptions(4, 1, 4, 1, OverflowPolicy.WAIT), "wait", timeout=2)
        with self.assertRaises(CapacityExceeded):
            await link.open_stream("stream", sender.options, "wait", timeout=2)
        await sender.send(b"aaaa", timeout=1)
        await asyncio.sleep(.03)
        await sender.send(b"bbbb", timeout=1)
        with self.assertRaises(TimeoutError):
            await sender.send(b"cccc", timeout=.02)
        self.assertEqual(len(await core.candidates(KEY, timeout=1)), 2)
        info = await group.diagnostics("provider")
        self.assertLessEqual(info["streams"][0]["buffered_bytes"], 4)
        await sender.abort("done")

    async def test_stop_exception_is_not_success(self):
        group = self.group()
        self.register(group, "bad", Placement.PROCESS, stop_failure=True)
        runtime = await self.start(group)
        with self.assertRaises(RuntimeFailure):
            await runtime.stop()
        self.assertFalse(group.process("bad").cleanup_confirmed)

    async def test_completed_run_child_still_monitored_while_other_runs(self):
        group = self.group()
        self.register(group, "returned", Placement.PROCESS, return_run=True)
        self.register(group, "waiting", Placement.LOCAL)
        runtime = await self.start(group)
        await asyncio.wait_for(asyncio.shield(group.modules["returned"].finished), 3)
        group.modules["returned"].process.kill()
        with self.assertRaises(RuntimeFailure):
            await asyncio.wait_for(runtime.wait(), 4)
