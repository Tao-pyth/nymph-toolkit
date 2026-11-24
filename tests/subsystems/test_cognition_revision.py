"""B04: revisions change independent model expectations without changing evidence."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import (HybridSettings, ModuleAdvertisement, ModuleKind,
                                   ModuleSpec, OperationFailure, OperatingState, Placement, Usage)
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT, COGNITION_KEY
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT, COGNITION_REVISION_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from nymph_toolkit.subsystems.cognition import factory
from nymph_toolkit.subsystems.cognition._model import annotations, dump, observation
from nymph_toolkit.subsystems.cognition._store import MAX_CORRECTIONS, Store
from tests.subsystems.test_cognition import FakeCore, record


def evidence(tokens, labels):
    return observation(record(content="猫は眠る"), *annotations("one", tokens, labels))


class _Requester:
    def __init__(self, context):
        self.context = context

    async def start(self):
        await self.context.core.publish_usage(Usage(OperatingState.RUNNING, True, 0, 1))

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass


def requester_factory(context, config):
    return _Requester(context)


class RevisionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name).resolve()/"model.db")
        self.old = evidence(["猫は", "眠る"], ["wrong"])
        self.new = evidence(["猫", "は", "眠る"], ["animal", "sleep"])
        self.store = Store(self.path, "memory", True); self.store.open()
        self.addCleanup(self.store.close)
        self.store.execute("learn", self.old)

    def inspect(self, token):
        return self.store.execute("inspect", token, None, 0, 8)

    def test_correction_changes_counts_segmentation_labels_and_survives_restart(self):
        original = self.store.execute("get_revision", "one")
        self.assertEqual(original["revision"], 0)
        self.assertFalse(self.inspect("猫")["known"])
        result = self.store.execute("correct", self.new, "fix-1", 0)
        self.assertEqual(result, dict(record_id="one", command_id="fix-1", revision=1, status="applied"))
        self.assertFalse(self.inspect("猫は")["known"])
        state = self.inspect("猫")
        self.assertEqual((state["count"], state["documents"]), (1, 1))
        self.assertEqual(state["successors"], [{"token": "は", "count": 1, "probability": 1.0}])
        self.assertEqual([x["label"] for x in state["concepts"]], ["animal", "sleep"])
        self.assertEqual(state["evidence"][0]["fingerprint"], original["fingerprint"])
        self.assertEqual(self.store.execute("learn", self.old).code, "cognition.conflict")
        self.store.close(); self.store.open()
        self.assertEqual(self.inspect("猫"), state)
        self.assertEqual(self.store.execute("correct", self.new, "fix-1", 0), result)
        current = self.store.execute("get_revision", "one")
        current["tokens"].clear()
        self.assertEqual(self.store.execute("get_revision", "one")["tokens"], ["猫", "は", "眠る"])

    def test_stale_revision_command_collision_and_replay_after_later_correction(self):
        first = self.store.execute("correct", self.new, "fix-1", 0)
        self.assertEqual(self.store.execute("correct", self.old, "fix-1", 0).code, "cognition.command_conflict")
        self.assertEqual(self.store.execute("correct", self.old, "fix-2", 0).code, "cognition.revision_conflict")
        self.assertEqual(self.store.execute("correct", self.old, "fix-2", 1)["revision"], 2)
        self.assertEqual(self.store.execute("correct", self.new, "fix-1", 0), first)
        self.assertEqual(self.store.execute("get_revision", "one")["tokens"], self.old["tokens"])

    def test_no_change_missing_record_and_changed_provenance(self):
        result = self.store.execute("correct", self.old, "noop", 0)
        self.assertEqual((result["status"], result["revision"]), ("no_change", 0))
        self.assertEqual(self.store.execute("correct", dict(self.new, fingerprint="f"*64), "bad", 0).code, "cognition.conflict")
        self.assertEqual(self.store.execute("correct", dict(self.new, record_id="missing"), "new", 0).code, "cognition.not_found")
        self.assertEqual(self.store.execute("get_revision", "missing").code, "cognition.not_found")
        self.store.close(); self.store.open()
        self.assertEqual(self.store.execute("correct", self.old, "noop", 0), result)

    def test_failure_after_state_update_rolls_back_state_and_command(self):
        self.store.connection.execute("CREATE TRIGGER reject_correction BEFORE INSERT ON corrections BEGIN SELECT RAISE(ABORT, 'fixture failure'); END")
        self.assertEqual(self.store.execute("correct", self.new, "fix", 0).code, "cognition.storage")
        self.assertEqual(self.store.execute("get_revision", "one")["revision"], 0)
        self.assertEqual(self.inspect("猫は")["count"], 1)
        self.assertEqual(self.store.connection.execute("SELECT count(*) FROM corrections").fetchone()[0], 0)
        self.store.connection.execute("DROP TRIGGER reject_correction")
        self.assertEqual(self.store.execute("correct", self.new, "fix", 0)["revision"], 1)

    def test_exact_history_limit_retains_replay_without_erasing_old_history(self):
        first = self.store.execute("correct", self.old, "noop", 0)
        rows = [(str(i), "one", 0, dump(self.old), dump(self.old),
                 dump(dict(record_id="one", command_id=str(i), revision=0, status="no_change"))) for i in range(MAX_CORRECTIONS-1)]
        self.store.connection.execute("BEGIN IMMEDIATE")
        self.store.connection.executemany("INSERT INTO corrections VALUES (?, ?, ?, ?, ?, ?)", rows)
        self.store.connection.commit()
        self.assertEqual(self.store.execute("correct", self.new, "overflow", 0).code, "cognition.history_full")
        self.assertEqual(self.store.execute("correct", self.old, "noop", 0), first)
        self.store.close(); self.store.open()
        self.assertEqual(self.inspect("猫は")["count"], 1)

    def test_corrupt_revision_and_history_are_rejected_without_overwriting(self):
        self.store.execute("correct", self.new, "fix", 0)
        self.store.connection.execute("UPDATE revisions SET revision=12")
        self.store.close(); before = Path(self.path).read_bytes()
        with self.assertRaises(sqlite3.DatabaseError): self.store.open()
        self.assertEqual(Path(self.path).read_bytes(), before)


class MigrationTests(unittest.TestCase):
    def test_opt_in_migration_keeps_sequences_provenance_and_old_contract_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory).resolve()/"old.db")
            old = Store(path, "memory"); old.open()
            sample = evidence(["猫", "は", "眠る"], ["sleep"])
            receipt = old.execute("learn", sample)
            self.assertEqual(old.connection.execute("PRAGMA user_version").fetchone()[0], 1)
            old.close()
            new = Store(path, "memory", True); new.open()
            try:
                self.assertEqual(new.connection.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(new.execute("learn", sample), receipt)
                self.assertEqual(new.execute("get_revision", "one"), dict(sample, revision=0))
            finally: new.close()
            compatible = Store(path, "memory"); compatible.open()
            try: self.assertEqual(compatible.execute("learn", sample), receipt)
            finally: compatible.close()

    def test_migration_failure_leaves_v1_and_samples_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory).resolve()/"old.db")
            old = Store(path, "memory"); old.open()
            receipt = old.execute("learn", evidence(["猫", "は", "眠る"], [])); old.close()
            connection = sqlite3.connect(path, isolation_level=None)
            connection.set_authorizer(lambda action, name, *args: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and name == "corrections" else sqlite3.SQLITE_OK)
            new = Store(path, "memory", True)
            with patch("nymph_toolkit.subsystems.cognition._store.sqlite3.connect", return_value=connection):
                with self.assertRaises(sqlite3.DatabaseError): new.open()
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT sequence FROM samples").fetchone()[0], receipt["sequence"])
                self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name IN ('revisions','corrections')").fetchall())


class RevisionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_and_stop_drain_admitted_revision_and_reopen_its_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            core = FakeCore()
            context = SimpleNamespace(core=core, settings=SimpleNamespace(max_frame_bytes=65536), provide=lambda k,h: None)
            path = str(Path(directory).resolve()/"db")
            model = factory(context, dict(path=path, memory_module_id="memory", enable_revision=True))
            await model.start()
            release, entered = threading.Event(), threading.Event()
            original = model.store.execute
            def blocked(operation, *args):
                if operation == "correct":
                    entered.set()
                    if not release.wait(5): raise TimeoutError("test fixture not released")
                return original(operation, *args)
            try:
                await model.learn("one", tokens=["猫", "は", "眠る"], concepts=["wrong"])
                with patch.object(model.store,"execute",side_effect=blocked):
                    task = asyncio.create_task(model.correct("one",command_id="fix",expected_revision=0,tokens=["猫","は","眠る"],concepts=["sleep"]))
                    async with asyncio.timeout(3):
                        while not entered.is_set(): await asyncio.sleep(.001)
                    task.cancel()
                    stopping = asyncio.create_task(model.stop())
                    await asyncio.sleep(0)
                    self.assertFalse(task.done()); self.assertFalse(stopping.done())
                    release.set()
                    with self.assertRaises(asyncio.CancelledError): await task
                    await stopping
            finally:
                release.set(); await model.stop()
            store = Store(path,"memory",True); store.open()
            try:
                state = store.execute("get_revision","one")
                self.assertEqual((state["revision"],state["concepts"]),(1,["sleep"]))
                sample = {k:v for k,v in state.items() if k != "revision"}
                self.assertEqual(store.execute("correct",sample,"fix",0)["revision"],1)
            finally: store.close()

    async def test_validation_and_memory_evidence_leave_existing_learning_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            core = FakeCore(); provided = []
            context = SimpleNamespace(core=core, settings=SimpleNamespace(max_frame_bytes=65536), provide=lambda k,h: provided.append(k))
            model = factory(context, dict(path=str(Path(directory).resolve()/"db"), memory_module_id="memory", enable_revision=True))
            await model.start()
            try:
                self.assertEqual(provided, [COGNITION_KEY, COGNITION_REVISION_KEY])
                await model.learn("one", tokens=["猫", "は", "眠る"], concepts=["wrong"])
                for revision in (True, -1, 2**63-1):
                    result = await model.correct("one", command_id="fix", expected_revision=revision, tokens=["猫", "は", "眠る"], concepts=["sleep"])
                    self.assertEqual(result.code, "cognition.invalid")
                core.record = dict(core.record, content="other content")
                result = await model.correct("one", command_id="fix", expected_revision=0, tokens=["猫", "は", "眠る"], concepts=["sleep"])
                self.assertEqual(result.code, "cognition.invalid")
                self.assertEqual((await model.get_revision("one"))["concepts"], ["wrong"])
                self.assertEqual((await model.get_revision("one"))["revision"], 0)
            finally: await model.stop()


class RevisionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_placements_both_routes_restart_and_original_memory_unchanged(self):
        for placement in Placement:
            for memory_placement in Placement:
                with self.subTest(cognition=placement, memory=memory_placement), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    for restored in (False, True):
                        store = FileStore(root/"core", root/"archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
                        group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4), store)
                        group.register_module(ModuleSpec("memory", ModuleKind.SUBSYSTEM), ModuleAdvertisement("memory", "1.1", (MEMORY_CONTRACT,)),
                                              "nymph_toolkit.subsystems.memory:factory", {"path":str(root/"memory.db")}, memory_placement)
                        group.register_module(ModuleSpec("cognition", ModuleKind.SUBSYSTEM, ("memory",)), ModuleAdvertisement("cognition", "1.4", (COGNITION_CONTRACT, COGNITION_REVISION_CONTRACT)),
                                              "nymph_toolkit.subsystems.cognition:factory", {"path":str(root/"model.db"),"memory_module_id":"memory","enable_revision":True}, placement)
                        group.register_module(ModuleSpec("requester", ModuleKind.SUBSYSTEM, ("cognition",)), ModuleAdvertisement("requester", "1", ()),
                                              "tests.subsystems.test_cognition_revision:requester_factory", {}, Placement.LOCAL)
                        runtime = Runtime(group); await runtime.start()
                        try:
                            client = group.client("requester")
                            for key, provider in ((MEMORY_KEY,"memory"),(COGNITION_KEY,"cognition"),(COGNITION_REVISION_KEY,"cognition")):
                                await client.bind(key, provider, timeout=5)
                            original = {k:v for k,v in record().items() if k not in ("stored_at","sequence")}
                            await client.invoke(MEMORY_KEY,"put",original,timeout=5)
                            if not restored:
                                await client.invoke(COGNITION_KEY,"learn","one",tokens=["猫","は","眠る"],concepts=["wrong"],timeout=5)
                            link = await client.prepare(COGNITION_REVISION_KEY,timeout=5)
                            result = await link.acall("correct","one",command_id="fix",expected_revision=0,tokens=["猫","は","眠る"],concepts=["sleep"],timeout=10)
                            self.assertEqual(result["revision"],1)
                            state = await client.invoke(COGNITION_REVISION_KEY,"get_revision","one",timeout=5)
                            self.assertEqual(state["concepts"],["sleep"])
                            memory = await client.invoke(MEMORY_KEY,"get","one",timeout=5)
                            self.assertEqual({k:memory[k] for k in original},original)
                            await link.close()
                        finally: await runtime.stop()
                        self.assertTrue(all(group.process(n).cleanup_confirmed for n in ("memory","cognition","requester")))
                    await asyncio.sleep(0)
                    self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])
