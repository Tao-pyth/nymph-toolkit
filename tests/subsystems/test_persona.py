"""Persona contract, durable atomic updates, and owned cancellation regressions."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest

from nymph_toolkit.contracts import OperationFailure, TemporaryUnavailable
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT, PERSONA_KEY
from nymph_toolkit.subsystems.persona import factory
from nymph_toolkit.subsystems.persona._model import dump, request, traits
from nymph_toolkit.subsystems.persona._store import Store, MAX_UPDATES


INITIAL = {"curiosity": 500, "sociability": 400}


def change(key="update-1", revision=0, deltas=None):
    return dict(command_id=key, expected_revision=revision,
                deltas={"curiosity": 100} if deltas is None else deltas,
                reason="経験の集計結果", source={"actor_id": "observer", "reference": "memory:lesson-1"})


class PersonaModelTests(unittest.TestCase):
    def test_exact_contract_and_input_boundaries(self):
        self.assertEqual(PERSONA_KEY.contract_id, "ntk.persona.traits")
        self.assertEqual({op.name for op in PERSONA_CONTRACT.operations}, {"get", "apply", "get_update", "history"})
        self.assertTrue(all(op.mode.value == "async" for op in PERSONA_CONTRACT.operations))
        self.assertEqual(traits({"a": 0, "b": 1000}), {"a": 0, "b": 1000})
        for invalid in ({}, {"Upper": 1}, {"": 1}, {"a": True}, {"a": -1}, {"a": 1001}, {"a": 1.0},
                        {"a" * 33: 1}, {f"a{i}": 1 for i in range(33)}, {"a": float("nan")}):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                traits(invalid)
        value = change()
        detached = request(value, INITIAL)
        value["deltas"]["curiosity"] = 0; value["source"]["reference"] = "modified"
        self.assertEqual(detached, change())

    def test_invalid_updates_do_not_coerce_or_accept_extra_fields(self):
        cases = []
        for field, values in {
            "command_id": ["", " padded ", "x" * 129, "\x00", "\ud800", 3],
            "expected_revision": [True, -1, 2**63, 1.0],
            "deltas": [{}, {"missing": 1}, {"curiosity": True}, {"curiosity": -1001}, {"curiosity": float("inf")}],
            "reason": ["", "x" * 513],
            "source": [{}, {"actor_id": "x", "reference": "x", "other": 1}],
        }.items():
            cases.extend(dict(change(), **{field: value}) for value in values)
        cases.extend((dict(change(), extra=1), None, [], {k: v for k, v in change().items() if k != "source"}))
        recursive = change(); recursive["deltas"] = recursive; cases.append(recursive)
        for value in cases:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                request(value, INITIAL)

    def test_canonical_size_counts_ascii_escapes(self):
        initial = {f"trait_{n:02d}_" + "x" * 23: 500 for n in range(32)}
        value = change("x" * 128, deltas={key: 1000 for key in initial})
        value["reason"] = "\U0001f431" * 128
        value["source"] = {"actor_id": "a" * 128, "reference": "\U0001f431" * 128}
        self.assertGreater(len(dump(value).encode("ascii")), 4096)
        with self.assertRaisesRegex(ValueError, "4096"):
            request(value, initial)


class PersonaStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ntk-persona-")
        self.path = Path(self.temporary.name) / "persona.sqlite3"
        self.store = Store(str(self.path), "persona", INITIAL)
        await self.store.start()

    async def asyncTearDown(self):
        await self.store.stop()
        self.temporary.cleanup()

    async def test_atomic_changes_no_change_replay_and_restart(self):
        original = await self.store.execute("get")
        self.assertEqual(original["revision"], 0)
        first = change(deltas={"curiosity": 200, "sociability": -100})
        receipt = await self.store.execute("apply", first)
        self.assertEqual(receipt["before"], INITIAL)
        self.assertEqual(receipt["after"], {"curiosity": 700, "sociability": 300})
        self.assertEqual((receipt["status"], receipt["revision"], receipt["sequence"]), ("applied", 1, 1))
        no_change = await self.store.execute("apply", change("same", 1, {"curiosity": 0}))
        self.assertEqual((no_change["status"], no_change["revision"], no_change["sequence"]), ("no_change", 1, 2))
        current = await self.store.execute("get")
        self.assertEqual(current["updated_at"], receipt["stored_at"])
        self.assertEqual(await self.store.execute("apply", first), receipt)
        await self.store.stop()
        self.store = Store(str(self.path), "persona", INITIAL)
        await self.store.start()
        self.assertEqual(await self.store.execute("get"), current)
        self.assertEqual(await self.store.execute("get_update", "update-1"), receipt)
        self.assertEqual(await self.store.execute("apply", first), receipt)
        page = await self.store.execute("history", 0, 1)
        self.assertEqual(page["updates"], [receipt])
        self.assertEqual((await self.store.execute("history", page["next_after"], 1))["updates"], [no_change])
        self.assertEqual((await self.store.execute("history", 2, 4))["updates"], [])

    async def test_invalid_delta_rejects_every_field_and_stale_revision(self):
        initial = await self.store.execute("get")
        result = await self.store.execute("apply", change(deltas={"curiosity": 501, "sociability": -100}))
        self.assertEqual(result.code, "persona.invalid")
        self.assertEqual(await self.store.execute("get"), initial)
        self.assertEqual((await self.store.execute("history", 0, 4))["updates"], [])
        first = await self.store.execute("apply", change())
        self.assertEqual((await self.store.execute("apply", change("stale"))).code, "persona.revision_conflict")
        self.assertEqual((await self.store.execute("apply", change(deltas={"curiosity": 50}))).code, "persona.command_conflict")
        self.assertEqual((await self.store.execute("get_update", "stale")).code, "persona.not_found")
        self.assertEqual(await self.store.execute("get_update", "update-1"), first)
        for operation, arguments in (("get_update", ("",)), ("history", (True, 4)), ("history", (0, 5)),
                                     ("history", (4097, 1)), ("apply", (dict(change(), extra=1),))):
            self.assertEqual((await self.store.execute(operation, *arguments)).code, "persona.invalid")

    async def test_busy_and_input_snapshot_precede_first_await(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def changed(active):
            if active:
                entered.set(); await release.wait()
        self.store.changed = changed
        value = change()
        task = asyncio.create_task(self.store.execute("apply", value))
        await asyncio.wait_for(entered.wait(), 3)
        try:
            value["deltas"]["curiosity"] = 499
            value["source"]["reference"] = "mutated"
            self.assertIsInstance(await self.store.execute("get"), TemporaryUnavailable)
        finally:
            release.set()
        receipt = await task
        self.assertEqual(receipt["after"]["curiosity"], 600)
        self.assertEqual(receipt["source"]["reference"], "memory:lesson-1")

    async def test_transaction_rollback_preserves_state_and_prior_journal(self):
        first = await self.store.execute("apply", change())
        before = await self.store.execute("get")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TRIGGER reject_update BEFORE INSERT ON updates BEGIN SELECT RAISE(ABORT,'injected'); END")
            connection.commit()
        failed = await self.store.execute("apply", change("fail", 1))
        self.assertEqual(failed.code, "persona.storage")
        self.assertEqual(await self.store.execute("get"), before)
        self.assertEqual((await self.store.execute("history", 0, 4))["updates"], [first])
        self.assertEqual((await self.store.execute("get_update", "fail")).code, "persona.not_found")

    async def test_cancel_and_stop_drain_owned_write_before_closing(self):
        entered, release = threading.Event(), threading.Event()
        original = self.store._apply
        def blocked(value):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release the worker")
            return original(value)
        self.store._apply = blocked
        task = asyncio.create_task(self.store.execute("apply", change()))
        stopping = None
        try:
            async with asyncio.timeout(3):
                while not entered.is_set(): await asyncio.sleep(.005)
            task.cancel(); await asyncio.sleep(.01); task.cancel()
            stopping = asyncio.create_task(self.store.stop())
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
            self.assertFalse(stopping.done())
            self.assertIsInstance(await self.store.execute("get"), TemporaryUnavailable)
        finally:
            release.set()
            await asyncio.gather(task, *([stopping] if stopping else []), return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertIsNone(self.store.pool)
        self.store = Store(str(self.path), "persona", INITIAL)
        await self.store.start()
        self.assertEqual((await self.store.execute("get_update", "update-1"))["after"]["curiosity"], 600)

    async def test_identity_and_corrupt_current_state_are_rejected_without_repair(self):
        await self.store.execute("apply", change())
        await self.store.stop()
        intact = self.path.read_bytes()
        for module_id, initial in (("different", INITIAL), ("persona", dict(INITIAL, curiosity=400))):
            other = Store(str(self.path), module_id, initial)
            with self.assertRaises(ValueError): await other.start()
            self.assertIsNone(other.pool)
            self.assertEqual(self.path.read_bytes(), intact)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE metadata SET state='{}'")
            connection.commit()
        corrupt = self.path.read_bytes()
        other = Store(str(self.path), "persona", INITIAL)
        with self.assertRaises(ValueError): await other.start()
        self.assertEqual(self.path.read_bytes(), corrupt)

    async def test_corrupt_receipt_unknown_format_and_schema_are_not_repaired(self):
        await self.store.execute("apply", change())
        await self.store.stop()
        baseline = self.path.read_bytes()
        mutations = ["UPDATE updates SET receipt='{}'", "PRAGMA user_version=999", "PRAGMA application_id=123",
                     "ALTER TABLE updates ADD COLUMN extra TEXT", "UPDATE updates SET sequence=2",
                     "UPDATE updates SET request='not json'", "UPDATE updates SET command_id='wrong'"]
        for statement in mutations:
            self.path.write_bytes(baseline)
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute(statement)
                connection.commit()
            corrupt = self.path.read_bytes()
            other = Store(str(self.path), "persona", INITIAL)
            with self.subTest(statement=statement), self.assertRaises((ValueError, sqlite3.Error)):
                await other.start()
            self.assertIsNone(other.pool)
            self.assertEqual(self.path.read_bytes(), corrupt)

    async def test_foreign_view_only_database_is_not_treated_as_empty(self):
        path = self.path.with_name("foreign.sqlite3")
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE VIEW foreign_data AS SELECT 1 AS value")
            connection.commit()
        before = path.read_bytes()
        other = Store(str(path), "persona", INITIAL)
        with self.assertRaises(ValueError): await other.start()
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNone(other.pool)

    async def test_full_history_retains_receipts_and_allows_replay(self):
        # Exercise the adopted bound, not a smaller patched limit.
        first = change("full-0", 0, {"curiosity": 0})
        for number in range(MAX_UPDATES):
            result = await self.store.execute("apply", change(f"full-{number}", 0, {"curiosity": 0}))
            self.assertEqual(result["sequence"], number + 1)
        self.assertEqual((await self.store.execute("apply", change("overflow"))).code, "persona.history_full")
        self.assertEqual((await self.store.execute("apply", first))["sequence"], 1)
        self.assertEqual((await self.store.execute("get"))["traits"], INITIAL)
        self.assertEqual(len((await self.store.execute("history", 4092, 4))["updates"]), 4)
        await self.store.stop()
        self.store = Store(str(self.path), "persona", INITIAL)
        await self.store.start()
        self.assertEqual((await self.store.execute("get_update", "full-4095"))["sequence"], 4096)

    async def test_largest_traits_and_history_fit_minimum_transport(self):
        await self.store.stop()
        initial = {f"trait_{n:02d}_" + "x" * 23: 500 for n in range(32)}
        store = Store(str(self.path.with_name("large.sqlite3")), "persona", initial)
        await store.start()
        try:
            for n in range(4):
                value = change(f"large-{n}", n, {key: 1 for key in initial})
                value["reason"] = "x" * 512
                value["source"]["reference"] = "y" * 512
                self.assertIsInstance(await store.execute("apply", value), dict)
            page = await store.execute("history", 0, 4)
            self.assertLess(len(dump(page).encode("ascii")), 49152)
        finally:
            await store.stop()

    async def test_factory_has_no_autonomous_trait_changes(self):
        await self.store.stop()
        captured, usages = {}, []
        async def publish(usage, **kwargs): usages.append(usage)
        context = SimpleNamespace(module_id="persona", settings=SimpleNamespace(max_frame_bytes=65536),
                                  core=SimpleNamespace(publish_usage=publish),
                                  provide=lambda key, handlers: captured.update(handlers))
        service = factory(context, {"path": str(self.path), "initial_traits": INITIAL})
        await service.start()
        running = asyncio.create_task(service.run())
        try:
            original = await captured["get"]()
            await asyncio.sleep(.05)
            self.assertEqual(await captured["get"](), original)
            self.assertEqual((await captured["history"]())["updates"], [])
            self.assertEqual((await captured["apply"](change()))["revision"], 1)
            self.assertEqual((await captured["get_update"]("update-1"))["status"], "applied")
            self.assertTrue(all(usage.capacity == 1 for usage in usages))
        finally:
            running.cancel(); await asyncio.gather(running, return_exceptions=True)
            await service.stop()
