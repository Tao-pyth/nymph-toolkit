"""B03: real Memory/Document contracts, four placements and lifecycle failures."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from contextlib import closing
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from nymph_toolkit.contracts import (
    BindingKey, HybridSettings, LinkFailure, ModuleAdvertisement, ModuleKind, ModuleSpec,
    OperationFailure, Placement, RuntimeFailure, TemporaryUnavailable,
)
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT, COGNITION_KEY
from nymph_toolkit.contracts.document import DOCUMENT_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from nymph_toolkit.subsystems import cognition
from examples.cognition_requester import CONTROL_CONTRACT, CONTROL_KEY
from tests.subsystems.test_cognition import record


def group_at(root, learner=Placement.LOCAL, memory=Placement.LOCAL, config=None, *, probe=False):
    store = FileStore(root/"core", root/"archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    group = HybridGroup(HybridSettings(10, 3, 60, 65536, 32, 4), store)
    for spec, version, contract, entry, settings, placement in (
        (ModuleSpec("memory", ModuleKind.SUBSYSTEM), "1.1.0", MEMORY_CONTRACT, "subsystems.memory", {"path": str(root/"memory.db")}, memory),
        (ModuleSpec("document", ModuleKind.ADAPTER, ("memory",)), "1.2.0", DOCUMENT_CONTRACT, "adapters.document", {"root": str(root), "memory_module_id": "memory"}, Placement.LOCAL),
        (ModuleSpec("cognition", ModuleKind.SUBSYSTEM, ("memory",)), "1.3.0", COGNITION_CONTRACT, "subsystems.cognition", {"path": str(root/"cognition.db"), "memory_module_id": "memory"} if config is None else config, learner),
    ):
        entrypoint = "tests.doubles.cognition_probe:factory" if probe and spec.module_id == "cognition" else "nymph_toolkit."+entry+":factory"
        group.register_module(spec, ModuleAdvertisement(spec.module_id, version, (contract,)), entrypoint, settings, placement)
    group.register_module(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, ("document", "cognition")),
                          ModuleAdvertisement("nymph", "dummy-1", (CONTROL_CONTRACT,)), "examples.cognition_requester:factory", {}, Placement.LOCAL)
    return group


async def connect(group):
    client = group.client("nymph")
    await client.bind(MEMORY_KEY, "memory", timeout=5)
    value = record()
    del value["sequence"], value["stored_at"]
    saved = await client.invoke(MEMORY_KEY, "put", value, timeout=5)
    assert isinstance(saved, dict), repr(saved)
    await client.bind(COGNITION_KEY, "cognition", timeout=5)
    return client, await client.prepare(COGNITION_KEY, timeout=5)


class CognitionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_placements_document_memory_learning_and_restart(self):
        for learner in Placement:
            for memory in Placement:
                with self.subTest(learner=learner, memory=memory), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    (root/"note.md").write_text("猫 は 眠る", encoding="utf-8")
                    first = None
                    for restored in (False, True):
                        group = group_at(root, learner, memory)
                        runtime = Runtime(group)
                        await runtime.start()
                        try:
                            await group.connections.bind("memory", CONTROL_KEY, "nymph", wait_timeout=5)
                            call = await group.connections.prepare(BindingKey("memory", CONTROL_KEY), wait_timeout=5)
                            result = await asyncio.wait_for(call.acall("exercise", restored), 70)
                            self.assertIsInstance(result, dict, repr(result))
                            current = result["receipt"], result["profile"]
                            if restored: self.assertEqual(current, first)
                            first = current
                        finally:
                            await runtime.stop()
                        self.assertTrue(all(group.process(n).cleanup_confirmed for n in ("memory", "document", "cognition", "nymph")))
                    await asyncio.sleep(0)
                    self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    async def test_locked_model_storage_capacity_and_explicit_retry(self):
        for learner in Placement:
            with self.subTest(learner=learner), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                group = group_at(root, learner)
                runtime = Runtime(group)
                await runtime.start()
                lock = sqlite3.connect(root/"cognition.db", isolation_level=None)
                try:
                    client, call = await connect(group)
                    lock.execute("BEGIN IMMEDIATE")
                    pending = asyncio.create_task(call.acall("learn", "one", tokens=["猫", "は", "眠る"], concepts=["sleep"], timeout=10))
                    async with asyncio.timeout(3):
                        while not (await client.candidates(COGNITION_KEY))[0].contract_usage.active:
                            await asyncio.sleep(.001)
                    self.assertIsInstance(await call.acall("inspect", "猫", timeout=5), TemporaryUnavailable)
                    result = await pending
                    self.assertIsInstance(result, OperationFailure, repr(result))
                    self.assertEqual(result.code, "cognition.storage")
                    lock.rollback()
                    self.assertFalse((await call.acall("inspect", "猫", timeout=5))["known"])
                    learned = await call.acall("learn", "one", tokens=["猫", "は", "眠る"], concepts=["sleep"], timeout=10)
                    self.assertEqual(learned["sequence"], 1)
                    await call.close()
                finally:
                    lock.close()
                    await runtime.stop()

    async def test_memory_link_failure_health_and_later_explicit_request(self):
        for learner in Placement:
            with self.subTest(learner=learner), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                group = group_at(root, learner)
                runtime = Runtime(group)
                await runtime.start()
                try:
                    client, call = await connect(group)
                    handlers = group.local_nodes["memory"].context.handlers
                    original = handlers[MEMORY_KEY, "get"]
                    calls = []
                    async def failed(key):
                        calls.append(key)
                        raise RuntimeError("injected get transport failure")
                    handlers[MEMORY_KEY, "get"] = failed
                    result = await call.acall("learn", "one", tokens=["猫", "は", "眠る"], concepts=[], timeout=10)
                    self.assertIsInstance(result, LinkFailure, repr(result))
                    self.assertEqual(calls, ["one"])
                    handlers[MEMORY_KEY, "get"] = original
                    await call.close()
                    call = await client.prepare(COGNITION_KEY, timeout=5)
                    self.assertFalse((await call.acall("inspect", "猫", timeout=5))["known"])
                    result = await call.acall("learn", "one", tokens=["猫", "は", "眠る"], concepts=[], timeout=10)
                    self.assertEqual(result["sequence"], 1)
                    await call.close()
                finally:
                    await runtime.stop()

    async def test_cancel_and_runtime_stop_drain_admitted_learning(self):
        for learner in Placement:
            for stopping in (False, True):
                with self.subTest(learner=learner, stopping=stopping), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    group = group_at(root, learner, Placement.PROCESS, probe=True)
                    runtime = Runtime(group)
                    await runtime.start()
                    lock = sqlite3.connect(root/"cognition.db", isolation_level=None)
                    stop = None
                    try:
                        client, call = await connect(group)
                        lock.execute("BEGIN IMMEDIATE")
                        pending = asyncio.create_task(call.acall("learn", "one", tokens=["猫", "は", "眠る"], concepts=["sleep"], timeout=10))
                        async with asyncio.timeout(3):
                            while not (root/"cognition.entered").exists():
                                await asyncio.sleep(.001)
                        if stopping: stop = asyncio.create_task(runtime.stop())
                        else: pending.cancel()
                        await asyncio.sleep(.03)
                        lock.rollback()
                        await asyncio.gather(pending, return_exceptions=True)
                        if not stopping:
                            async with asyncio.timeout(3):
                                while (await client.candidates(COGNITION_KEY))[0].contract_usage.active:
                                    await asyncio.sleep(.001)
                            await call.close()
                    finally:
                        lock.close()
                        if stop is not None: await stop
                        else: await runtime.stop()
                    snapshots = {n: group.process(n) for n in ("memory", "document", "cognition", "nymph")}
                    self.assertTrue(all(s.cleanup_confirmed for s in snapshots.values()), repr(snapshots))
                    with closing(sqlite3.connect(root/"cognition.db")) as db:
                        rows = db.execute("SELECT payload FROM samples").fetchall()
                    self.assertEqual([json.loads(r[0])["record_id"] for r in rows], ["one"])

    async def test_partial_start_failure_releases_resources(self):
        for learner in Placement:
            with self.subTest(learner=learner), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                group = group_at(root, learner, Placement.PROCESS, {"path": str(root/"absent"/"model.db"), "memory_module_id": "memory"})
                runtime = Runtime(group)
                with self.assertRaises(RuntimeFailure): await runtime.start()
                with self.assertRaises(RuntimeFailure): await runtime.stop()
                self.assertTrue(group.process("memory").cleanup_confirmed)
                snapshot = group.process("cognition")
                if learner == Placement.LOCAL: self.assertTrue(snapshot.cleanup_confirmed)
                else: self.assertEqual(snapshot.returncode, 0, repr(snapshot))
                await asyncio.sleep(0)
                self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    def test_cognition_imports_only_public_contracts(self):
        for path in Path(cognition.__file__).parent.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse(any(n.startswith(("nymph_toolkit.core", "nymph_toolkit.subsystems", "nymph_toolkit.adapters")) for n in names), path)
