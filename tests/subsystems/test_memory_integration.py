"""B01 public factory, Core integration and process placement matrix."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from datetime import timedelta
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import (
    BindingKey, HybridSettings, LinkFailure, ModuleAdvertisement, ModuleKind, ModuleSpec,
    OutcomeUnknown, Placement, RuntimeFailure, TemporaryUnavailable,
)
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from nymph_toolkit.subsystems import memory
from examples.memory_requester import CONTROL_CONTRACT, CONTROL_KEY


def group_at(root, requester, provider, config=None, *, scenario_timeout=30):
    store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    # The host's exercise RPC includes many individual Memory RPCs (each 5s).
    group = HybridGroup(HybridSettings(10, 3, scenario_timeout, 65536, 32, 4), store)
    group.register_module(ModuleSpec("memory", ModuleKind.SUBSYSTEM),
                          ModuleAdvertisement("memory", "1.1.0", (MEMORY_CONTRACT,)),
                          "nymph_toolkit.subsystems.memory:factory",
                          {"path": str(root / "memory.db")} if config is None else config, provider)
    group.register_module(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, ("memory",)),
                          ModuleAdvertisement("nymph", "dummy-1", (CONTROL_CONTRACT,)),
                          "examples.memory_requester:factory", {}, requester)
    return group


class MemoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_placements_and_restart_preserve_contract(self):
        for requester in Placement:
            for provider in Placement:
                with self.subTest(requester=requester, provider=provider), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    first = None
                    for restored in (False, True):
                        group = group_at(root, requester, provider)
                        runtime = Runtime(group)
                        await runtime.start()
                        try:
                            await group.connections.bind("memory", CONTROL_KEY, "nymph", wait_timeout=5)
                            call = await group.connections.prepare(BindingKey("memory", CONTROL_KEY), wait_timeout=5)
                            result = await asyncio.wait_for(call.acall("exercise", "memory", restored), 45)
                            self.assertIsInstance(result, dict, repr(result))
                            self.assertEqual(result["page_count"], 8)
                            self.assertEqual(result["restored"], restored)
                            if restored:
                                self.assertEqual(result["saved"], first)
                            first = result["saved"]
                        finally:
                            await runtime.stop()
                        for name in ("memory", "nymph"):
                            self.assertTrue(group.process(name).cleanup_confirmed)
                    await asyncio.sleep(0)
                    self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    async def test_busy_is_capacity_response_and_does_not_break_binding(self):
        import sqlite3
        from tests.subsystems.test_memory import record
        for provider in Placement:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                group = group_at(root, Placement.LOCAL, provider)
                runtime = Runtime(group)
                await runtime.start()
                connection = sqlite3.connect(root / "memory.db", isolation_level=None)
                try:
                    await group.connections.bind("nymph", MEMORY_KEY, "memory", wait_timeout=5)
                    call = await group.connections.prepare(BindingKey("nymph", MEMORY_KEY), wait_timeout=5)
                    connection.execute("BEGIN IMMEDIATE")
                    pending = asyncio.create_task(call.acall("put", record()))
                    # Wait for the provider's explicit active usage notification.
                    async with asyncio.timeout(3):
                        while not (await group.client("nymph").candidates(MEMORY_KEY))[0].contract_usage.active:
                            await asyncio.sleep(.005)
                    self.assertIsInstance(await call.acall("get", "event-1"), TemporaryUnavailable)
                    connection.rollback()
                    self.assertEqual((await pending)["record_id"], "event-1")
                    self.assertEqual((await call.acall("get", "event-1"))["record_id"], "event-1")
                finally:
                    connection.close()
                    await runtime.stop()

    async def test_scenario_budget_covers_multiple_individually_timely_writes(self):
        from nymph_toolkit.subsystems.memory._store import Store
        original = Store._put
        def slow_write(store, value):
            # Each operation is below its 5s RPC budget; the aggregate is not.
            time.sleep(.6)
            return original(store, value)
        for timeout in (5, 30):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as directory:
                group = group_at(Path(directory), Placement.PROCESS, Placement.LOCAL, scenario_timeout=timeout)
                runtime = Runtime(group)
                with patch.object(Store, "_put", slow_write):
                    await runtime.start()
                    try:
                        await group.connections.bind("memory", CONTROL_KEY, "nymph", wait_timeout=5)
                        call = await group.connections.prepare(BindingKey("memory", CONTROL_KEY), wait_timeout=5)
                        result = await asyncio.wait_for(call.acall("exercise", "memory"), 45)
                        if timeout == 5:
                            self.assertIsInstance(result, LinkFailure, repr(result))
                            self.assertIsInstance(result.exception, OutcomeUnknown, repr(result))
                        else:
                            self.assertIsInstance(result, dict, repr(result))
                            self.assertEqual(result["page_count"], 8)
                    finally:
                        await runtime.stop()
                self.assertTrue(group.process("nymph").cleanup_confirmed)

    async def test_invalid_factory_config_fails_without_creating_database(self):
        for config in ({"path": "relative"}, {}, {"path": "/unused", "unknown": True}):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = Runtime(group_at(root, Placement.LOCAL, Placement.LOCAL, config))
                with self.assertRaises(RuntimeFailure):
                    await runtime.start()
                with self.assertRaises(RuntimeFailure):
                    await runtime.stop()
                self.assertFalse((root / "memory.db").exists())

    def test_memory_does_not_import_core_or_other_subsystems(self):
        for path in Path(memory.__file__).parent.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(n.startswith("nymph_toolkit.core") for n in names), path)
