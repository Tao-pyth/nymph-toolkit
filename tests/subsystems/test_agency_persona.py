"""B08: personality evidence changes choices without changing Core authority."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from examples.agency_demo import activity_catalog, decision_input
from nymph_toolkit.contracts import BindingKey, LinkFailure, OperationFailure, OutcomeUnknown, ProtocolError, TemporaryUnavailable
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT, PERSONA_KEY
from nymph_toolkit.contracts.memory import MEMORY_KEY
from nymph_toolkit.subsystems.agency import factory
from nymph_toolkit.subsystems.agency._model import catalog, decide, dump, persona_observation, persona_settings
from nymph_toolkit.subsystems.agency._store import Store
from tests.subsystems.test_agency import evidence, normalized
from tests.subsystems.test_agency_service import Core, Link


def settings():
    return dict(module_id="persona", motive_traits=dict(rest="rest_affinity", explore="curiosity", achieve="focus", social="sociability"))


def traits(**changes):
    return dict(module_id="persona", revision=0, updated_at="2026-11-24T00:00:00+00:00",
                traits=dict(dict(rest_affinity=500, curiosity=500, focus=500, sociability=500), **changes))


def material(value, observed=None, documents=0):
    return dict(goals=evidence(value, documents), persona=observed or traits())


class PersonaPolicyTests(unittest.TestCase):
    def choose(self, observed=None, value=None, previous=None, templates=None):
        value = value or normalized()
        return decide(value, material(value, observed), templates or catalog(activity_catalog()), "agency", previous, persona=settings())

    def test_neutral_values_preserve_old_choice_and_expose_actual_evidence(self):
        value = normalized()
        old = decide(value, evidence(value), catalog(activity_catalog()), "agency")
        current = self.choose()
        self.assertEqual(current["plan"], old["plan"])
        self.assertEqual(current["selected"]["score"], 800)
        self.assertEqual(current["policy"], "utility-persona-v1")
        self.assertEqual(current["persona"], dict(traits(), motive_traits=settings()["motive_traits"]))
        self.assertNotIn("persona", old)
        self.assertEqual(old["policy"], "utility-v1")

    def test_only_personality_changes_choice_and_schedule_with_hand_calculated_scores(self):
        value = normalized(sleep_pressure=600)
        before = self.choose(value=value)
        self.assertEqual(before["selected"]["template_id"], "study")
        after = self.choose(traits(rest_affinity=1000), value)
        self.assertEqual(after["selected"], dict(template_id="sleep", goal_id=None, motive="rest",
                                               base_score=600, multiplier_per_mille=1500, score=900))
        templates = catalog(activity_catalog())
        next(t for t in templates if t["template_id"] == "study")["delay_seconds"] = 100
        softened = self.choose(traits(curiosity=0), templates=templates)
        self.assertEqual(softened["plan"]["priority"], 400)
        self.assertEqual(softened["plan"]["duration_us"], 156_000_000)
        self.assertEqual(softened["plan"]["start_at"], "2026-11-24T12:01:00+00:00")

    def test_clamp_rounding_zero_and_unavailable_candidates(self):
        top = self.choose(traits(curiosity=1000))
        self.assertEqual(top["selected"]["score"], 1000)
        value = normalized(); value["goals"][0]["importance"] = 801
        self.assertEqual(self.choose(traits(curiosity=1), value)["selected"]["score"], 401)
        value["available"] = ["sleep", "talk"]; value["state"] = {k: 0 for k in value["state"]}
        zero = self.choose(traits(rest_affinity=1000, sociability=1000), value)
        self.assertEqual(zero["directive"], "idle")
        self.assertTrue(all(c["score"] == 0 for c in zero["candidates"]))
        self.assertNotIn("study", {c["template_id"] for c in zero["candidates"]})

    def test_changed_traits_use_existing_pause_resume_and_tie_rules(self):
        old = self.choose(value=normalized(sleep_pressure=600))
        value = normalized("next", sleep_pressure=600)
        value["current"] = dict(decision_id="one", state="running", revision=7, planned_end_notified=False, supports_pause=True)
        changed = self.choose(traits(rest_affinity=1000), value, old)
        self.assertEqual(changed["directive"], "pause")
        self.assertEqual(changed["target"]["expected_revision"], 7)
        value["state"]["sleep_pressure"] = 800
        tied = self.choose(traits(), value, old)
        self.assertEqual(tied["selected"]["template_id"], "study")
        value["current"]["state"] = "paused"
        resumed = self.choose(traits(), value, old)
        self.assertEqual((resumed["directive"], resumed["plan"]), ("resume", old["plan"]))

    def test_strict_mapping_and_remote_evidence_are_detached(self):
        config = settings(); checked = persona_settings(config)
        config["motive_traits"]["rest"] = "changed"
        self.assertEqual(checked["motive_traits"]["rest"], "rest_affinity")
        raw = traits(); copy = persona_observation(raw, checked); raw["traits"]["curiosity"] = 0
        self.assertEqual(copy["traits"]["curiosity"], 500)
        for bad in (None, {}, dict(settings(), extra=1), dict(settings(), module_id=" "),
                    dict(settings(), motive_traits={}), dict(settings(), motive_traits=dict(settings()["motive_traits"], rest="UPPER"))):
            with self.subTest(config=bad), self.assertRaises((ValueError, TypeError)): persona_settings(bad)
        invalid = [None, {}, dict(traits(), module_id="other"), dict(traits(), revision=True),
                   dict(traits(), revision=-1), dict(traits(), updated_at="2026-11-24"),
                   dict(traits(), traits={}), dict(traits(), extra=1), traits(curiosity=True), traits(curiosity=1001)]
        missing = traits(); del missing["traits"]["focus"]; invalid.append(missing)
        for bad in invalid:
            with self.subTest(evidence=bad), self.assertRaises((ValueError, TypeError)): persona_observation(bad, checked)


class PersonaJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name).resolve() / "agency.db")
        self.identity = dict(module_id="agency", catalog=catalog(activity_catalog()), memory_module_id="memory",
                             cognition_module_id="cognition", persona=settings())
        self.store = Store(self.path, self.identity); self.store.open(); self.addCleanup(self.store.close)

    def save(self, key="first", observed=None):
        value = normalized(key, sleep_pressure=600); data = material(value, observed)
        result = decide(value, data, self.identity["catalog"], "agency", persona=settings())
        return self.store.execute("save", value, data, result)

    def test_restart_keeps_old_persona_and_replay_without_redeciding(self):
        first = self.save(); second = self.save("new", dict(traits(rest_affinity=1000), revision=1))
        self.assertEqual(first["selected"]["template_id"], "study")
        self.assertEqual(second["selected"]["template_id"], "sleep")
        self.assertEqual(self.store.connection.execute("PRAGMA user_version").fetchone(), (2,))
        self.store.close(); self.store.open()
        self.assertEqual(self.store.execute("get", "first"), first)
        self.assertEqual(self.store.execute("replay", normalized("first", sleep_pressure=600)), first)
        self.assertEqual(self.store.execute("get", "new"), second)
        self.assertEqual(self.store.execute("replay", normalized("first", sleep_pressure=601)).code, "agency.decision_conflict")

    def test_new_and_old_formats_reject_cross_open_without_modifying_bytes(self):
        self.save(); self.store.close()
        plain = {k: v for k, v in self.identity.items() if k != "persona"}
        before = Path(self.path).read_bytes()
        with self.assertRaises(ValueError): Store(self.path, plain).open()
        self.assertEqual(Path(self.path).read_bytes(), before)
        old_path = str(Path(self.temp.name) / "old.db"); old = Store(old_path, plain)
        old.open(); self.assertEqual(old.connection.execute("PRAGMA user_version").fetchone(), (1,)); old.close()
        before = Path(old_path).read_bytes()
        with self.assertRaises(ValueError): Store(old_path, self.identity).open()
        self.assertEqual(Path(old_path).read_bytes(), before)
        old.open(); old.close()

    def test_atomic_failure_retains_prior_evidence_and_does_not_reserve_id(self):
        first = self.save()
        self.store.connection.execute("CREATE TEMP TRIGGER fail BEFORE UPDATE ON decisions BEGIN SELECT RAISE(ABORT,'test'); END")
        self.assertEqual(self.save("failure", traits(curiosity=0)).code, "agency.storage")
        self.assertEqual(self.store.execute("get", "failure").code, "agency.not_found")
        self.assertEqual(self.store.execute("get", "first"), first)
        self.store.connection.execute("DROP TRIGGER fail")
        self.assertEqual(self.save("failure")["sequence"], 2)

    def test_configuration_and_corrupt_trait_evidence_rejected_without_repair(self):
        self.save(); self.store.close()
        changed = deepcopy(self.identity); changed["persona"]["motive_traits"]["rest"] = "focus"
        before = Path(self.path).read_bytes()
        with self.assertRaises(ValueError): Store(self.path, changed).open()
        self.assertEqual(Path(self.path).read_bytes(), before)
        with closing(sqlite3.connect(self.path)) as db:
            data = json.loads(db.execute("SELECT evidence FROM decisions").fetchone()[0])
            data["persona"]["traits"]["curiosity"] = 0
            db.execute("UPDATE decisions SET evidence=?", (dump(data),)); db.commit()
        before = Path(self.path).read_bytes()
        with self.assertRaises(ValueError): self.store.open()
        self.assertEqual(Path(self.path).read_bytes(), before)


class PersonaLink(Link):
    async def acall(self, operation, *args, **kwargs):
        if self.key != PERSONA_KEY: return await super().acall(operation, *args, **kwargs)
        self.core.calls.append((self.key, operation, args, kwargs)); self.core.persona_entered.set()
        if self.core.persona_wait is not None: await self.core.persona_wait.wait()
        if isinstance(self.core.persona, BaseException): raise self.core.persona
        return self.core.persona


class PersonaCore(Core):
    def __init__(self):
        super().__init__(); self.persona = traits(); self.persona_wait = None; self.persona_entered = asyncio.Event()
    async def candidates(self, key, **kwargs):
        if key != PERSONA_KEY: return await super().candidates(key, **kwargs)
        # Reuse the fixture capacity, replacing only the advertised capability.
        item = (await super().candidates(MEMORY_KEY, **kwargs))[0]
        item.advertisement = SimpleNamespace(module_id="persona", contracts=(PERSONA_CONTRACT,))
        return [item]
    async def prepare(self, key, **kwargs):
        link = PersonaLink(self, key); self.links.append(link); return link


class PersonaAgencyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.core = PersonaCore()
        self.config = dict(path=str(Path(self.temp.name).resolve()/"agency.db"), memory_module_id="memory",
                           cognition_module_id="cognition", catalog=activity_catalog(), persona=settings())
        self.context = SimpleNamespace(module_id="agency", core=self.core, settings=SimpleNamespace(max_frame_bytes=65536), provide=lambda k,v: None)
        self.service = factory(self.context, self.config); await self.service.start(); self.addAsyncCleanup(self.service.stop)

    async def test_changed_traits_new_decision_replay_without_read_and_no_auto_update(self):
        first = await self.service.decide(decision_input("first", sleep_pressure=600))
        self.core.persona = dict(traits(rest_affinity=1000), revision=1)
        second = await self.service.decide(decision_input("next", sleep_pressure=600))
        self.assertEqual((first["selected"]["template_id"], second["selected"]["template_id"]), ("study", "sleep"))
        self.assertEqual([c[1] for c in self.core.calls if c[0] == PERSONA_KEY], ["get", "get"])
        calls = len(self.core.calls); self.core.persona = ProtocolError("offline")
        self.assertEqual(await self.service.decide(decision_input("first", sleep_pressure=600)), first)
        self.assertEqual(await self.service.get("next"), second)
        self.assertEqual(len(self.core.calls), calls)
        self.assertEqual(sum(k == PERSONA_KEY for k, target in self.core.bindings), 1)

    async def test_invalid_capacity_and_link_failure_are_not_replaced_by_neutral_traits(self):
        for bad, expected in (({}, "agency.evidence"), (traits(curiosity=True), "agency.evidence"),
                              (OperationFailure("persona.storage", "test"), "persona.storage")):
            self.core.persona = bad
            self.assertEqual((await self.service.decide(decision_input(expected))).code, expected)
            self.assertEqual((await self.service.get(expected)).code, "agency.not_found")
        self.core.persona = TemporaryUnavailable("busy")
        self.assertIsInstance(await self.service.decide(decision_input("busy")), TemporaryUnavailable)
        self.assertEqual(self.core.health, [])
        self.core.persona = LinkFailure(BindingKey("agency", PERSONA_KEY), "failure", "interrupted")
        self.assertIsInstance(await self.service.decide(decision_input("broken")), LinkFailure)
        self.assertEqual(self.core.health, [("persona",)]); self.assertEqual(self.core.acks, ["interrupted"])
        self.assertTrue(next(l for l in self.core.links if l.key == PERSONA_KEY).closed)

    async def test_cancellation_and_stop_own_pending_persona_read_and_saved_decision(self):
        self.core.persona_wait = asyncio.Event()
        task = asyncio.create_task(self.service.decide(decision_input("cancel")))
        await asyncio.wait_for(self.core.persona_entered.wait(), 5)
        task.cancel(); stop = asyncio.create_task(self.service.stop()); await asyncio.sleep(0)
        self.assertFalse(task.done()); self.assertFalse(stop.done())
        self.core.persona_wait.set()
        with self.assertRaises(asyncio.CancelledError): await task
        await stop
        self.assertTrue(all(l.closed for l in self.core.links)); self.assertIsNone(self.service.pool)
        reopened = factory(self.context, self.config); await reopened.start()
        try: self.assertEqual((await reopened.get("cancel"))["persona"]["revision"], 0)
        finally: await reopened.stop()

    async def test_unknown_persona_result_preserved_over_recovery_failures(self):
        unknown = OutcomeUnknown("persona-read")
        self.core.persona = unknown; self.core.recovery_error = ProtocolError("health failed")
        with self.assertRaises(OutcomeUnknown) as caught: await self.service.decide(decision_input("unknown"))
        self.assertIs(caught.exception, unknown)
        self.assertEqual([c[1] for c in self.core.calls if c[0] == PERSONA_KEY], ["get"])
        self.assertEqual((await self.service.get("unknown")).code, "agency.not_found")
