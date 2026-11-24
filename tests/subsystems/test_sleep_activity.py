"""B10 intent durability, public receipt checks and no replay after ambiguity."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import ActivityKey, ActivityFinishReason, OperationFailure, OutcomeUnknown, TemporaryUnavailable, Usage, OperatingState
from nymph_toolkit.contracts.sleep import SLEEP_CONTRACT, SLEEP_KEY
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT, PERSONA_KEY
from nymph_toolkit.subsystems.sleep_activity import factory
from nymph_toolkit.subsystems.sleep_activity._model import dump, request
from nymph_toolkit.subsystems.sleep_activity._store import Store


def value(key="one", **changes):
    return dict(request_id=key, expected_revision=0, record_ids=["a", "b"], apply_persona=True, **changes)


class Activity:
    def __init__(self, key="activity", stop_at=0):
        self.request = SimpleNamespace(key=ActivityKey("agency", key))
        self.checkpoints = 0
        self.stop_at = stop_at
        self.pause = None

    async def checkpoint(self):
        self.checkpoints += 1
        if self.checkpoints == self.stop_at:
            return ActivityFinishReason.NYMPH
        if self.checkpoints == 2 and self.pause is not None:
            await self.pause.wait()
        return None


class Link:
    def __init__(self, core, key): self.core, self.key, self.closed = core, key, False
    async def close(self): self.closed = True
    async def acall(self, operation, *args, **kwargs):
        core = self.core
        core.calls.append((self.key, operation))
        if operation == "cycle":
            core.entered.set()
            if core.wait is not None: await core.wait.wait()
            if core.reject is not None: return core.reject
            item = args[0]
            command = "sleep-persona:" + hashlib.sha256(dump(["sleep", item["cycle_id"]]).encode()).hexdigest()
            proposal = dict(command_id=command, expected_revision=0, deltas={"curiosity": 5},
                            reason="Sleep consolidation-v1: observed labelled experience",
                            source=dict(actor_id="sleep", reference="sleep-cycle:" + item["cycle_id"]))
            core.cycle = dict(cycle_id=item["cycle_id"], revision=1, policy="consolidation-v1", retained_ids=["a", "b"],
                forgotten_ids=[], source_counts=dict(observed=2, reported=0, inferred=0, imagined=0, dream=0),
                expired_dream_ids=[], dreams=[], evaluated_ids=["a", "b"], contributions=[], persona_proposal=proposal)
            if core.unknown_cycle: raise OutcomeUnknown("cycle-pending")
            return core.cycle
        if operation == "get":
            return core.cycle or OperationFailure("sleep.not_found", "not observed")
        if operation == "apply":
            proposal = args[0]
            core.applied = dict(sequence=1, command_id=proposal["command_id"], status="applied", previous_revision=0, revision=1,
                before={"curiosity": 500}, after={"curiosity": 505}, reason=proposal["reason"], source=proposal["source"],
                stored_at="2026-11-24T00:00:00Z")
            if core.unknown_apply: raise OutcomeUnknown("apply-pending")
            return core.applied
        if operation == "get_update":
            return core.applied or OperationFailure("persona.not_found", "not observed")
        raise AssertionError(operation)


class Core:
    def __init__(self):
        self.calls, self.links, self.health = [], [], []
        self.cycle = self.applied = self.wait = self.reject = None
        self.unknown_cycle = self.unknown_apply = False
        self.entered = asyncio.Event()
    async def publish_usage(self, *args, **kwargs): pass
    async def candidates(self, key, **kwargs):
        contract, name = (SLEEP_CONTRACT, "sleep") if key == SLEEP_KEY else (PERSONA_CONTRACT, "persona")
        usage = Usage(OperatingState.RUNNING, True, 0, 1)
        return [SimpleNamespace(advertisement=SimpleNamespace(module_id=name, contracts=(contract,)), module_usage=usage, contract_usage=usage)]
    async def bind(self, *args, **kwargs): pass
    async def prepare(self, key, **kwargs):
        link = Link(self, key); self.links.append(link); return link
    async def health_check(self, *, module_ids, **kwargs): self.health.append(module_ids)


class SleepActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.core = Core()
        self.config = dict(path=str(Path(self.temp.name).resolve() / "activity.db"), sleep_module_id="sleep", persona_module_id="persona")
        self.context = SimpleNamespace(module_id="sleep-worker", core=self.core, settings=SimpleNamespace(max_frame_bytes=65536),
                                       provide=lambda *a: None, provide_executor=lambda *a, **kw: None)
        self.service = factory(self.context, self.config)
        await self.service.start(); self.addAsyncCleanup(self.service.stop)

    async def test_cycle_then_apply_receipts_replay_and_restart_without_external_calls(self):
        first = await self.service.execute(Activity(), value())
        self.assertEqual(first["phase"], "completed")
        self.assertEqual(first["persona"]["after"], {"curiosity": 505})
        calls = list(self.core.calls)
        self.assertEqual(await self.service.execute(Activity("another"), value()), first)
        self.assertEqual(await self.service.reconcile("one"), first)
        self.assertEqual(await self.service.apply("one"), first)
        self.assertEqual(self.core.calls, calls)
        await self.service.stop()
        restored = factory(self.context, self.config)
        await restored.start()
        try: self.assertEqual(await restored.get("one"), first)
        finally: await restored.stop()
        self.assertEqual(self.core.calls, calls)
        self.assertTrue(all(x.closed for x in self.core.links))

    async def test_unknown_cycle_lookup_does_not_apply_until_explicit_request(self):
        self.core.unknown_cycle = True
        with self.assertRaises(OutcomeUnknown): await self.service.execute(Activity(), value())
        self.assertEqual((await self.service.get("one"))["phase"], "cycle_sent")
        self.assertEqual((await self.service.reconcile("one"))["phase"], "cycle_saved")
        self.assertNotIn((PERSONA_KEY, "apply"), self.core.calls)
        result = await self.service.apply("one")
        self.assertEqual(result["phase"], "completed")
        self.assertEqual(self.core.calls.count((SLEEP_KEY, "cycle")), 1)
        self.assertEqual(self.core.calls.count((PERSONA_KEY, "apply")), 1)

    async def test_unknown_apply_and_not_found_do_not_resend(self):
        self.core.unknown_apply = True
        with self.assertRaises(OutcomeUnknown): await self.service.execute(Activity(), value())
        saved = self.core.applied; self.core.applied = None
        self.assertEqual((await self.service.apply("one"))["phase"], "apply_sent")
        self.core.applied = saved
        self.assertEqual((await self.service.reconcile("one"))["phase"], "completed")
        self.assertEqual(self.core.calls.count((PERSONA_KEY, "apply")), 1)

    async def test_stop_at_safe_point_and_false_apply_preserve_cycle_without_trait_change(self):
        stopped = await self.service.execute(Activity(stop_at=2), value())
        self.assertEqual(stopped["phase"], "cycle_saved")
        self.assertNotIn((PERSONA_KEY, "apply"), self.core.calls)
        # A distinct explicitly requested cycle can omit Persona application.
        config = dict(value("two"), apply_persona=False)
        done = await self.service.execute(Activity("two"), config)
        self.assertEqual(done["phase"], "completed")
        self.assertIsNone(done["persona"])

    async def test_pause_keeps_state_and_get_works_while_writes_are_busy(self):
        activity = Activity(); activity.pause = asyncio.Event()
        task = asyncio.create_task(self.service.execute(activity, value()))
        async with asyncio.timeout(5):
            while activity.checkpoints < 2: await asyncio.sleep(.01)
        self.assertEqual((await self.service.get("one"))["phase"], "cycle_saved")
        self.assertIsInstance(await self.service.apply("one"), TemporaryUnavailable)
        activity.pause.set()
        self.assertEqual((await task)["phase"], "completed")
        self.assertEqual(self.core.calls.count((SLEEP_KEY, "cycle")), 1)

    async def test_input_snapshot_conflict_capacity_and_cancellation_keep_intent(self):
        self.core.wait = asyncio.Event()
        arguments = value()
        task = asyncio.create_task(self.service.execute(Activity(), arguments))
        await self.core.entered.wait()
        arguments["record_ids"].clear()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        saved = await self.service.get("one")
        self.assertEqual(saved["request"]["record_ids"], ["a", "b"])
        self.assertEqual(saved["phase"], "cycle_sent")
        self.assertEqual((await self.service.reconcile("one"))["phase"], "cycle_sent")
        with self.assertRaises(RuntimeError): await self.service.execute(Activity("different"), arguments)
        self.assertEqual(self.core.calls.count((SLEEP_KEY, "cycle")), 1)

    async def test_provider_rejection_is_failed_without_apply_or_health(self):
        self.core.reject = TemporaryUnavailable("busy")
        with self.assertRaises(RuntimeError): await self.service.execute(Activity(), value())
        self.assertEqual((await self.service.get("one"))["phase"], "failed")
        self.assertEqual(self.core.health, [])
        self.assertEqual(self.core.calls, [(SLEEP_KEY, "cycle")])

    async def test_bad_public_receipt_never_becomes_permission_to_apply(self):
        original = Link.acall
        async def malformed(link, operation, *args, **kwargs):
            result = await original(link, operation, *args, **kwargs)
            if operation == "cycle":
                result = json.loads(json.dumps(result))
                result["persona_proposal"]["command_id"] = "unrelated"
            return result
        with patch.object(Link, "acall", malformed):
            with self.assertRaises(ValueError): await self.service.execute(Activity(), value())
        self.assertEqual((await self.service.get("one"))["phase"], "cycle_sent")
        self.assertNotIn((PERSONA_KEY, "apply"), self.core.calls)
        self.assertEqual((await self.service.reconcile("one"))["phase"], "cycle_saved")

    async def test_receipt_save_failure_retains_sent_intent_for_read_only_recovery(self):
        await self.service._work(self.service.store.connection.execute,
            "CREATE TRIGGER fail_receipt BEFORE UPDATE ON requests WHEN json_extract(NEW.record, '$.phase')='cycle_saved' "
            "BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(sqlite3.Error): await self.service.execute(Activity(), value())
        self.assertIsNotNone(self.core.cycle)
        self.assertEqual((await self.service.get("one"))["phase"], "cycle_sent")
        await self.service._work(self.service.store.connection.execute, "DROP TRIGGER fail_receipt")
        self.assertEqual((await self.service.reconcile("one"))["phase"], "cycle_saved")
        self.assertEqual(self.core.calls.count((SLEEP_KEY, "cycle")), 1)
        self.assertNotIn((PERSONA_KEY, "apply"), self.core.calls)


class JournalTests(unittest.TestCase):
    def test_full_history_rejects_new_ids_and_retains_pending_intents_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = dict(module_id="worker", sleep_module_id="sleep", persona_module_id="persona")
            path = str(Path(directory).resolve() / "history.db")
            store = Store(path, identity); store.open()
            try:
                for number in range(4096):
                    row, fresh = store.begin(value(str(number)), dict(requester_id="agency", activity_id=str(number)))
                    self.assertTrue(fresh)
                rejected, fresh = store.begin(value("overflow"), dict(requester_id="agency", activity_id="extra"))
                self.assertEqual(rejected.code, "sleep_activity.history_full")
                self.assertFalse(fresh)
                self.assertEqual(store.get("0")["phase"], "prepared")
            finally: store.close()
            restored = Store(path, identity); restored.open()
            try:
                replay, fresh = restored.begin(value("4095"), dict(requester_id="agency", activity_id="new"))
                self.assertEqual(replay, row)
                self.assertFalse(fresh)
            finally: restored.close()

    def test_strict_inputs_atomic_transition_and_corrupt_history_rejected(self):
        for bad in (dict(value(), expected_revision=True), dict(value(), apply_persona=1), dict(value(), record_ids=["a", "a"]), {}):
            with self.assertRaises(ValueError): request(bad)
        with tempfile.TemporaryDirectory() as directory:
            identity = dict(module_id="worker", sleep_module_id="sleep", persona_module_id="persona")
            path = str(Path(directory).resolve() / "activity.db")
            store = Store(path, identity); store.open()
            row, fresh = store.begin(value(), dict(requester_id="agency", activity_id="one"))
            self.assertTrue(fresh)
            store.connection.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON requests BEGIN SELECT RAISE(ABORT, 'test'); END")
            with self.assertRaises(sqlite3.Error): store.save(row, dict(row, phase="cycle_sent"))
            self.assertEqual(store.get("one"), row)
            store.connection.execute("DROP TRIGGER fail_update")
            store.save(row, dict(row, phase="cycle_sent")); store.close()
            wrong = Store(path, dict(identity, persona_module_id="different"))
            with self.assertRaises(ValueError): wrong.open()
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    raw = json.loads(connection.execute("SELECT record FROM requests").fetchone()[0])
                    raw["phase"] = "completed"
                    connection.execute("UPDATE requests SET record=?", (dump(raw),))
            before = Path(path).read_bytes()
            with self.assertRaises(ValueError): Store(path, identity).open()
            self.assertEqual(Path(path).read_bytes(), before)


if __name__ == "__main__": unittest.main()
