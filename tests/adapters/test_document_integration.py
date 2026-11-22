"""B02 real Document/Memory lifecycle and four placements."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from contextlib import closing
from datetime import timedelta
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from nymph_toolkit.adapters import document
from nymph_toolkit.contracts import (
    BindingKey, HybridSettings, LinkFailure, ModuleAdvertisement, ModuleKind, ModuleSpec,
    OperationFailure, Placement, RuntimeFailure, TemporaryUnavailable,
)
from nymph_toolkit.contracts.document import DOCUMENT_CONTRACT, DOCUMENT_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from examples.document_requester import CONTROL_CONTRACT, CONTROL_KEY
from tests.adapters.test_document import request


def group_at(root, adapter=Placement.LOCAL, memory=Placement.LOCAL, config=None):
    store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4), store)
    group.register_module(ModuleSpec("memory", ModuleKind.SUBSYSTEM),
                          ModuleAdvertisement("memory", "1.1.0", (MEMORY_CONTRACT,)),
                          "nymph_toolkit.subsystems.memory:factory", {"path": str(root / "memory.db")}, memory)
    group.register_module(ModuleSpec("document", ModuleKind.ADAPTER, ("memory",)),
                          ModuleAdvertisement("document", "1.2.0", (DOCUMENT_CONTRACT,)),
                          "nymph_toolkit.adapters.document:factory",
                          {"root": str(root), "memory_module_id": "memory"} if config is None else config, adapter)
    group.register_module(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, ("document",)),
                          ModuleAdvertisement("nymph", "dummy-1", (CONTROL_CONTRACT,)),
                          "examples.document_requester:factory", {}, Placement.LOCAL)
    return group


class DocumentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_placements_restart_and_both_entry_routes(self):
        for adapter in Placement:
            for memory in Placement:
                with self.subTest(adapter=adapter, memory=memory), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    raw = "# 文書\r\n出典を保存する。\n".encode()
                    (root / "note.md").write_bytes(raw)
                    first = None
                    for restored in (False, True):
                        group = group_at(root, adapter, memory)
                        runtime = Runtime(group)
                        await runtime.start()
                        try:
                            await group.connections.bind("memory", CONTROL_KEY, "nymph", wait_timeout=5)
                            call = await group.connections.prepare(BindingKey("memory", CONTROL_KEY), wait_timeout=5)
                            result = await asyncio.wait_for(call.acall("exercise", restored), 45)
                            self.assertIsInstance(result, dict, repr(result))
                            self.assertEqual(result["saved"]["content"], raw.decode())
                            self.assertTrue(result["saved"]["source"].endswith(hashlib.sha256(raw).hexdigest()))
                            if restored:
                                self.assertEqual(result["saved"], first)
                            first = result["saved"]
                        finally:
                            await runtime.stop()
                        self.assertTrue(all(group.process(name).cleanup_confirmed for name in ("memory", "document", "nymph")))
                    await asyncio.sleep(0)
                    self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    async def test_memory_lock_capacity_storage_failure_and_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "note.md").write_text("text", encoding="utf-8")
            group = group_at(root)
            runtime = Runtime(group)
            await runtime.start()
            lock = sqlite3.connect(root / "memory.db", isolation_level=None)
            try:
                client = group.client("nymph")
                await client.bind(DOCUMENT_KEY, "document", timeout=5)
                call = await client.prepare(DOCUMENT_KEY, timeout=5)
                lock.execute("BEGIN IMMEDIATE")
                active = asyncio.create_task(call.acall("ingest", request(), timeout=5))
                async with asyncio.timeout(3):
                    while not (await client.candidates(DOCUMENT_KEY))[0].contract_usage.active:
                        await asyncio.sleep(.001)
                self.assertIsInstance(await call.acall("ingest", request(), timeout=5), TemporaryUnavailable)
                failure = await active
                self.assertIsInstance(failure, OperationFailure)
                self.assertEqual(failure.code, "memory.storage")
                lock.rollback()
                saved = await call.acall("ingest", request(), timeout=5)
                self.assertIsInstance(saved, dict, repr(saved))
                self.assertEqual(saved["sequence"], 1)
                await call.close()
            finally:
                lock.close()
                await runtime.stop()

    async def test_memory_link_failure_health_recovery_does_not_replay(self):
        for placement in Placement:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / "note.md").write_text("text", encoding="utf-8")
                group = group_at(root, placement)
                runtime = Runtime(group)
                await runtime.start()
                calls = []
                handlers = group.local_nodes["memory"].context.handlers
                original = handlers[MEMORY_KEY, "put"]
                async def fail(value):
                    calls.append(value)
                    raise RuntimeError("injected link failure")
                handlers[MEMORY_KEY, "put"] = fail
                try:
                    client = group.client("nymph")
                    await client.bind(DOCUMENT_KEY, "document", timeout=5)
                    call = await client.prepare(DOCUMENT_KEY, timeout=5)
                    result = await call.acall("ingest", request(), timeout=10)
                    self.assertIsInstance(result, LinkFailure, repr(result))
                    self.assertEqual(len(calls), 1)
                    handlers[MEMORY_KEY, "put"] = original
                    # The Adapter's cooperative interruption also invalidated this
                    # incoming handle. A subsequent caller explicitly prepares again.
                    await call.close()
                    call = await client.prepare(DOCUMENT_KEY, timeout=5)
                    result = await call.acall("ingest", request(), timeout=10)
                    self.assertIsInstance(result, dict, repr(result))
                    self.assertEqual(result["sequence"], 1)
                    await call.close()
                finally:
                    await runtime.stop()

    async def test_partial_start_failure_cleans_memory_and_adapter(self):
        for placement in Placement:
            with self.subTest(placement=placement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                group = group_at(root, placement, Placement.PROCESS,
                                 {"root": str(root / "missing"), "memory_module_id": "memory"})
                runtime = Runtime(group)
                with self.assertRaises(RuntimeFailure):
                    await runtime.start()
                with self.assertRaises(RuntimeFailure):
                    await runtime.stop()
                self.assertTrue(group.process("memory").cleanup_confirmed)
                snapshot = group.process("document")
                if placement == Placement.LOCAL:
                    self.assertTrue(snapshot.cleanup_confirmed)
                else:
                    # A failed bootstrap may exit before the parent's stop ACK.
                    # Exit and confirmed cleanup are deliberately distinct.
                    self.assertEqual(snapshot.returncode, 0, repr(snapshot))
                await asyncio.sleep(0)
                self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    async def test_cancel_during_memory_write_and_runtime_stop_drain(self):
        for placement in Placement:
            for stopping in (False, True):
                with self.subTest(placement=placement, stopping=stopping), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    (root / "note.md").write_text("text", encoding="utf-8")
                    group = group_at(root, placement, Placement.PROCESS)
                    runtime = Runtime(group)
                    await runtime.start()
                    lock = sqlite3.connect(root / "memory.db", isolation_level=None)
                    stop = None
                    try:
                        client = group.client("nymph")
                        await client.bind(DOCUMENT_KEY, "document", timeout=5)
                        call = await client.prepare(DOCUMENT_KEY, timeout=5)
                        lock.execute("BEGIN IMMEDIATE")
                        pending = asyncio.create_task(call.acall("ingest", request(), timeout=5))
                        async with asyncio.timeout(3):
                            while not (await client.candidates(MEMORY_KEY))[0].contract_usage.active:
                                await asyncio.sleep(.001)
                        if stopping:
                            stop = asyncio.create_task(runtime.stop())
                        else:
                            pending.cancel()
                        await asyncio.sleep(.03)
                        lock.rollback()
                        await asyncio.gather(pending, return_exceptions=True)
                        if not stopping:
                            async with asyncio.timeout(3):
                                while (await client.candidates(DOCUMENT_KEY))[0].contract_usage.active:
                                    await asyncio.sleep(.001)
                            await call.close()
                    finally:
                        lock.close()
                        if stop is not None:
                            await stop
                        else:
                            await runtime.stop()
                    self.assertTrue(all(group.process(n).cleanup_confirmed for n in ("memory", "document", "nymph")))
                    # Cancellation/stop does not claim rollback of an admitted put.
                    with closing(sqlite3.connect(root / "memory.db")) as db:
                        self.assertEqual(db.execute("SELECT record_id FROM records").fetchall(), [("doc-1",)])

    def test_document_imports_only_public_contracts(self):
        for path in Path(document.__file__).parent.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse(any(n.startswith(("nymph_toolkit.core", "nymph_toolkit.subsystems")) for n in names), path)
