"""B03: independent learning expectations, evidence, durable state and ownership."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import BindingKey, LinkFailure, OperationFailure, OperatingState, OutcomeUnknown, ProtocolError, TemporaryUnavailable, Usage
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.subsystems.cognition import factory
from nymph_toolkit.subsystems.cognition._model import annotations, dump, observation, query
from nymph_toolkit.subsystems.cognition._store import Store


def record(key="one", content="猫 は 眠る", source_kind="observed"):
    return {"record_id": key, "kind": "experience", "content": content,
            "source_kind": source_kind, "source": "fixture:" + key,
            "occurred_at": "2026-11-23T00:00:00+00:00", "sequence": 1,
            "stored_at": "2026-11-23T00:00:01+00:00"}


def sample(key="one", tokens=None, concepts=None, source_kind="observed"):
    tokens = ["猫", "は", "眠る"] if tokens is None else tokens
    return observation(record(key, " ".join(tokens), source_kind), *annotations(key, tokens, ["sleep"] if concepts is None else concepts))


class ModelStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name).resolve() / "cognition.db")
        self.store = Store(self.path, "memory")
        self.store.open()
        self.addCleanup(self.store.close)

    def inspect(self, token, source_kind=None, after=0, limit=8):
        return self.store.execute("inspect", *query(token, source_kind, after, limit))

    def test_learning_changes_from_unknown_with_independent_expected_counts(self):
        self.assertFalse(self.inspect("猫")["known"])
        for value in (sample("a", ["猫", "猫", "眠る"], ["sleep", "animal"]),
                      sample("b", ["猫", "遊ぶ"], ["animal"]),
                      sample("c", ["猫"], ["imaginary"], "dream")):
            self.store.execute("learn", value)
        result = self.inspect("猫")
        self.assertEqual((result["count"], result["documents"], result["end_count"]), (4, 3, 1))
        self.assertEqual(result["end_probability"], .25)
        self.assertEqual({x["token"]: x["probability"] for x in result["successors"]}, {"猫": .25, "眠る": .25, "遊ぶ": .25})
        self.assertEqual({x["label"]: x["support_ratio"] for x in result["concepts"]}, {"animal": 2/3, "sleep": 1/3, "imaginary": 1/3})
        self.assertEqual(result["source_counts"], {"dream": 1, "observed": 2})
        self.assertEqual(self.inspect("猫", "dream")["end_probability"], 1)
        self.assertEqual(self.inspect("猫", "reported")["count"], 0)
        self.assertEqual(self.inspect("眠る")["successors"], [])  # no cross-example bigram
        self.assertFalse(self.inspect("unknown")["known"])

    def test_paging_changes_evidence_only_and_ranking_is_bounded(self):
        for i in range(12):
            self.store.execute("learn", sample(str(i), ["word", "n" + str(i)], ["c" + str(i)]))
        first = self.inspect("word", limit=8)
        second = self.inspect("word", after=first["after"], limit=8)
        self.assertEqual((first["count"], second["count"]), (12, 12))
        self.assertEqual((len(first["evidence"]), len(second["evidence"])), (8, 4))
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertEqual([e["record_id"] for e in first["evidence"] + second["evidence"]], list(map(str, range(12))))
        self.assertEqual((first["successor_total"], first["concept_total"]), (12, 12))
        self.assertEqual([x["token"] for x in first["successors"]], sorted("n"+str(i) for i in range(12))[:8])
        self.assertEqual(len(first["concepts"]), 8)
        self.assertEqual(self.inspect("absent", after=200)["after"], 200)

    def test_idempotence_conflict_provenance_and_restart(self):
        item = sample(concepts=["sleep", "animal"])
        first = self.store.execute("learn", item)
        self.assertEqual(self.store.execute("learn", sample(concepts=["animal", "sleep"])), first)
        altered = sample(concepts=["wrong"])
        self.assertEqual(self.store.execute("learn", altered).code, "cognition.conflict")
        expected = self.inspect("猫")
        expected["evidence"][0]["record_id"] = "external mutation"
        self.assertEqual(self.inspect("猫")["evidence"][0]["record_id"], "one")
        expected = self.inspect("猫")
        self.store.close()
        self.store.open()
        self.assertEqual(self.inspect("猫"), expected)
        self.assertEqual(self.store.execute("learn", item), first)
        self.assertEqual(first["fingerprint"], hashlib.sha256(dump(record()).encode("ascii")).hexdigest())

    def test_annotation_and_query_boundaries(self):
        valid = annotations("x"*128, ["あ"*21]*32, ["x"*64])
        self.assertEqual(len(valid[1]), 32)
        invalid = [("", ["a"], []), (" x", ["a"], []), ("x"*129, ["a"], []),
                   ("x", [], []), ("x", ["a"]*33, []), ("x", ["a"*65], []),
                   ("x", ["a b"], []), ("x", ["a\x00"], []), ("x", ["\ud800"], []),
                   ("x", ("a",), []), ("x", ["a"], ["x", "x"]), ("x", ["a"], [str(i) for i in range(9)])]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                annotations(*args)
        for args in (("a", "bad", 0, 8), ("a", None, True, 1), ("a", None, 0, 9), ("a", None, -1, 1), ("a", None, 2**63, 1)):
            with self.assertRaises(ValueError):
                query(*args)

    def test_memory_content_match_and_malformed_records(self):
        value = observation(record(content="猫\r\nは\t眠る"), "one", ["猫", "は", "眠る"], [])
        self.assertEqual(value["tokens"], ["猫", "は", "眠る"])
        with self.assertRaises(ValueError):
            observation(record(), "one", ["犬", "は", "眠る"], [])
        for bad in (None, {}, dict(record(), record_id="other"), dict(record(), sequence=True), dict(record(), source_kind="truth"), dict(record(), content="x"*4097), dict(record(), occurred_at="2026-02-30T00:00:00Z"), dict(record(), stored_at="invalid")):
            with self.assertRaises(ProtocolError):
                observation(bad, "one", ["猫", "は", "眠る"], [])

    def test_capacity_preserves_existing_and_repeated_learning(self):
        first = self.store.execute("learn", sample("0"))
        for i in range(1, 256):
            self.store.execute("learn", sample(str(i)))
        self.assertEqual(self.store.execute("learn", sample("256")).code, "cognition.full")
        self.assertEqual(self.store.execute("learn", sample("0")), first)
        self.assertEqual(self.inspect("猫")["documents"], 256)

    def test_locked_storage_and_injected_post_insert_failure_rollback(self):
        with closing(sqlite3.connect(self.path, isolation_level=None)) as lock:
            lock.execute("BEGIN IMMEDIATE")
            self.assertEqual(self.store.execute("learn", sample()).code, "cognition.storage")
            lock.rollback()
        with patch.object(self.store, "_receipt", side_effect=sqlite3.OperationalError("post insert")):
            self.assertEqual(self.store.execute("learn", sample()).code, "cognition.storage")
        self.assertFalse(self.inspect("猫")["known"])
        self.assertEqual(self.store.execute("learn", sample())["sequence"], 1)

    def test_wrong_provider_unknown_identity_and_corrupt_payload_fail_closed(self):
        self.store.execute("learn", sample())
        before = Path(self.path).read_bytes()
        other = Store(self.path, "other")
        with self.assertRaises(ValueError):
            other.open()
        self.assertIsNone(other.connection)
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.store.connection.execute("UPDATE samples SET payload='{}'")
        self.assertEqual(self.inspect("猫").code, "cognition.storage")
        self.store.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.open()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(ValueError):
            self.store.open()


class FakeCore:
    def __init__(self):
        self.events = []
        self.record = record()
        self.failure = None
        self.provider = "memory"
        self.usage = Usage(OperatingState.RUNNING, True, 0, 1)

    async def publish_usage(self, usage, **kwargs): self.events.append(("usage", usage.active))
    async def candidates(self, *args, **kwargs):
        self.events.append(("candidates",))
        return [SimpleNamespace(advertisement=SimpleNamespace(module_id=self.provider, contracts=(MEMORY_CONTRACT,)), module_usage=self.usage, contract_usage=self.usage)]
    async def bind(self, key, provider, **kwargs): self.events.append(("bind", provider))
    async def prepare(self, *args, **kwargs): self.events.append(("prepare",)); return self
    async def acall(self, operation, key, **kwargs):
        self.events.append((operation, key))
        if isinstance(self.failure, Exception): raise self.failure
        return self.failure if self.failure is not None else dict(self.record)
    async def close(self): self.events.append(("close",))
    async def acknowledge_interruption(self, notice_id, **kwargs): self.events.append(("ack", notice_id))
    async def health_check(self, **kwargs): self.events.append(("health", kwargs["module_ids"]))


class CognitionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.core = FakeCore()
        self.context = SimpleNamespace(settings=SimpleNamespace(max_frame_bytes=65536), core=self.core, provide=lambda *args: None)
        self.config = {"path": str(self.root/"model.db"), "memory_module_id": "memory"}
        self.model = factory(self.context, self.config)
        await self.model.start()
        self.addAsyncCleanup(self.model.stop)

    async def learn(self): return await self.model.learn("one", tokens=["猫", "は", "眠る"], concepts=["sleep"])

    async def test_explicit_selection_capacity_and_cached_link(self):
        self.core.provider = "other"
        self.assertIsInstance(await self.learn(), TemporaryUnavailable)
        self.core.provider = "memory"
        self.core.usage = Usage(OperatingState.RUNNING, True, 1, 1)
        self.assertIsInstance(await self.learn(), TemporaryUnavailable)
        self.core.usage = Usage(OperatingState.RUNNING, True, 0, 1)
        first = await self.learn()
        self.core.provider = "other"
        self.assertEqual(await self.learn(), first)
        self.assertEqual(self.core.events.count(("bind", "memory")), 1)
        self.assertEqual(self.core.events.count(("prepare",)), 1)

    async def test_input_memory_business_failure_and_conflict_leave_state_intact(self):
        self.assertEqual((await self.model.learn("one", tokens=[], concepts=[])).code, "cognition.invalid")
        self.assertNotIn(("candidates",), self.core.events)
        for failure in (OperationFailure("memory.not_found", "missing"), TemporaryUnavailable("busy")):
            self.core.failure = failure
            self.assertEqual(await self.learn(), failure)
        self.core.failure = None
        self.core.record = record(content="wrong")
        self.assertEqual((await self.learn()).code, "cognition.invalid")
        self.assertFalse((await self.model.inspect("猫"))["known"])
        self.core.record = record()
        await self.learn()
        self.core.record["source"] = "changed source"
        self.assertEqual((await self.learn()).code, "cognition.conflict")
        self.assertEqual((await self.model.inspect("猫"))["count"], 1)
        self.assertFalse(any(e[0] == "health" for e in self.core.events))

    async def test_link_failure_cleanup_ack_health_and_no_replay(self):
        self.core.failure = LinkFailure(BindingKey("cognition", MEMORY_KEY), RuntimeError("broken"), 7)
        self.assertIsInstance(await self.learn(), LinkFailure)
        self.assertEqual(self.core.events.count(("get", "one")), 1)
        events = self.core.events
        self.assertLess(events.index(("close",)), events.index(("ack", 7)))
        self.assertLess(events.index(("ack", 7)), events.index(("health", ("memory",))))
        self.core.failure = None
        self.assertIsInstance(await self.learn(), dict)
        self.assertEqual(events.count(("prepare",)), 2)
        self.assertEqual(events.count(("bind", "memory")), 1)

    async def test_unknown_survives_health_and_idle_notification_failure(self):
        original = OutcomeUnknown(42)
        self.core.failure = original
        async def fail_health(**kwargs): raise RuntimeError("health failed")
        self.core.health_check = fail_health
        with self.assertRaises(OutcomeUnknown) as caught:
            await self.learn()
        self.assertIs(caught.exception, original)
        async def fail_idle(usage, **kwargs):
            if usage.active == 0: raise RuntimeError("idle failed")
        self.core.publish_usage = fail_idle
        with self.assertRaises(OutcomeUnknown) as caught:
            await self.learn()
        self.assertIs(caught.exception, original)
        self.assertEqual(str(caught.exception.__cause__), "idle failed")
        self.assertEqual(self.core.events.count(("get", "one")), 2)
        self.assertFalse(self.model.busy)

    async def test_malformed_provider_is_protocol_failure_without_learning(self):
        self.core.record = {"unexpected": "shape"}
        with self.assertRaises(ProtocolError): await self.learn()
        self.assertIn(("health", ("memory",)), self.core.events)
        self.assertFalse((await self.model.inspect("猫"))["known"])

    async def test_cancel_stop_capacity_and_input_copy_wait_for_worker(self):
        entered, release = threading.Event(), threading.Event()
        original = self.model.store.execute
        def slow(*args):
            entered.set()
            if not release.wait(5): raise AssertionError("test gate timeout")
            return original(*args)
        tokens, concepts = ["猫", "は", "眠る"], ["sleep"]
        with patch.object(self.model.store, "execute", side_effect=slow):
            call = asyncio.create_task(self.model.learn("one", tokens=tokens, concepts=concepts))
            async with asyncio.timeout(3):
                while not entered.is_set(): await asyncio.sleep(.001)
            tokens[0], concepts[0] = "mutated", "mutated"
            self.assertIsInstance(await self.model.inspect("猫"), TemporaryUnavailable)
            call.cancel(); await asyncio.sleep(0); call.cancel()
            stop = asyncio.create_task(self.model.stop())
            await asyncio.sleep(.02)
            self.assertFalse(call.done()); self.assertFalse(stop.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError): await call
            await stop
        self.assertIsNone(self.model.pool)
        self.assertIsInstance(await self.learn(), TemporaryUnavailable)
        store = Store(self.config["path"], "memory")
        store.open()
        try:
            result = store.execute("inspect", "猫", None, 0, 8)
            self.assertEqual(result["concepts"][0]["label"], "sleep")
        finally: store.close()

    async def test_start_failure_stop_and_configuration_boundaries(self):
        bad = factory(self.context, dict(self.config, path=str(self.root/"missing"/"model.db")))
        with self.assertRaises(sqlite3.Error): await bad.start()
        await bad.stop()
        self.assertIsNone(bad.pool)
        for config in ({}, dict(self.config, path="relative"), dict(self.config, memory_module_id=" ")):
            with self.assertRaises(ValueError): factory(self.context, config)
        await self.model.stop(); await self.model.stop()
        self.assertIsNone(self.model.store.connection)
