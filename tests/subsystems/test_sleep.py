"""B09 consolidation semantics, provenance, durable expiry and correction proposals."""

# SPDX-License-Identifier: Apache-2.0
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from nymph_toolkit.contracts import OperationFailure
from nymph_toolkit.subsystems.sleep._model import (
    ActiveFull, dump, initial, inspect, memory_record, observation, page, persona,
    request, rules, sample, transition,
)
from nymph_toolkit.subsystems.sleep._store import Store


def identity():
    return dict(module_id="sleep", memory_module_id="memory", cognition_module_id="cognition", persona_module_id="persona",
                trait_rules=[dict(concept="explore", trait="curiosity", delta=3),
                             dict(concept="social", trait="sociability", delta=-2)])


def traits(**changes):
    return dict(module_id="persona", revision=0, traits={"curiosity": 500, "sociability": 400, **changes}, updated_at="2026-11-24T00:00:00Z")


def experience(key="a", source="observed", tokens=None, concepts=None):
    tokens = tokens or ["猫", "は", "眠る"]
    record = dict(record_id=key, kind="experience", content=" ".join(tokens), source_kind=source,
                  source="fixture", occurred_at="2026-11-24T00:00:00Z", stored_at="2026-11-24T00:00:01Z", sequence=1)
    annotation = dict(record_id=key, fingerprint=hashlib.sha256(dump(record).encode("ascii")).hexdigest(), source_kind=source,
                      tokens=tokens, concepts=sorted(concepts or ["explore"]), revision=0)
    return record, annotation


def evidence(key="a", **kwargs):
    return observation(*experience(key, **kwargs))


def cycle(key="one", revision=0, ids=None):
    return request(dict(cycle_id=key, expected_revision=revision, record_ids=["a"] if ids is None else ids))


class SleepPolicyTests(unittest.TestCase):
    def test_integrates_source_separately_and_forgets_after_four_unused_cycles(self):
        samples = [evidence("a"), evidence("b", source="reported")]
        state, receipt, credited = transition(initial(), set(), cycle(ids=["b", "a"]), samples, traits(), identity())
        profile = inspect(state, "explore", None)
        self.assertEqual((profile["records"], profile["strength"]), (2, 2000))
        self.assertEqual((profile["source_counts"]["observed"], profile["source_counts"]["reported"]), (1, 1))
        self.assertEqual(inspect(state, "explore", "reported")["strength"], 1000)
        self.assertEqual(inspect(state, "unknown", None)["records"], 0)
        self.assertEqual(receipt["persona_proposal"]["deltas"], {"curiosity": 3})
        for number, strength in ((1, 1500), (2, 1000), (3, 500), (4, 0)):
            state, receipt, added = transition(state, set(credited), cycle(str(number), number, []), [], traits(), identity())
            self.assertEqual(inspect(state, "explore", None)["strength"], strength)
            self.assertEqual(receipt["forgotten_ids"], ["a", "b"] if number == 4 else [])
            self.assertEqual(added, [])
        state, receipt, _ = transition(state, set(credited), cycle("return", 5), [evidence()], traits(), identity())
        self.assertEqual(inspect(state, "explore", None)["strength"], 1000)
        self.assertIsNone(receipt["persona_proposal"])

    def test_dream_is_deterministic_recombination_and_expiry_not_real_evidence(self):
        samples = [evidence("a", tokens=["赤い", "猫", "眠る"]), evidence("b", tokens=["犬", "海", "走る"]), evidence("c", source="dream")]
        state, first, _ = transition(initial(), set(), cycle(ids=["a", "b", "c"]), samples, traits(), identity())
        self.assertEqual(state["dreams"][0]["tokens"], ["赤い", "猫", "海", "走る"])
        self.assertEqual(state["dreams"][0]["source_record_ids"], ["a", "b"])
        self.assertEqual(state["dreams"][0]["source_kind"], "dream")
        self.assertEqual(first["evaluated_ids"], ["a", "b"])
        self.assertNotIn("tokens", first["dreams"][0])
        later, receipt, _ = transition(state, {"a", "b"}, cycle("next", 1, []), [], traits(), identity())
        self.assertEqual(receipt["expired_dream_ids"], [state["dreams"][0]["dream_id"]])
        self.assertNotEqual(later["dreams"][0]["dream_id"], state["dreams"][0]["dream_id"])
        self.assertEqual(inspect(later, "explore", "dream")["records"], 1)  # Only explicitly supplied dream evidence.

    def test_persona_contribution_once_bounds_and_unmatched_observations(self):
        samples = [evidence("a", concepts=["explore", "social"]), evidence("b", concepts=["explore", "social"])]
        current = traits(); current["traits"] = {"curiosity": 998, "sociability": 1}
        state, receipt, credited = transition(initial(), set(), cycle(ids=["a", "b"]), samples, current, identity())
        self.assertEqual(receipt["persona_proposal"]["deltas"], {"curiosity": 2, "sociability": -1})
        self.assertEqual(receipt["persona_proposal"]["expected_revision"], 0)
        self.assertEqual(len(receipt["contributions"]), 2)
        _, receipt, _ = transition(initial(), set(), cycle(ids=["a", "b"]), samples, traits(), identity())
        self.assertEqual(receipt["persona_proposal"]["deltas"], {"curiosity": 5, "sociability": -4})
        samples[0]["annotation_revision"] = 1
        _, again, added = transition(state, set(credited), cycle("again", 1, ["a", "b"]), samples, traits(), identity())
        self.assertIsNone(again["persona_proposal"]); self.assertEqual(added, [])
        _, none, _ = transition(initial(), set(), cycle(), [evidence(concepts=["unmapped"])], traits(), identity())
        self.assertEqual(none["evaluated_ids"], ["a"]); self.assertIsNone(none["persona_proposal"])
        for source in ("reported", "inferred", "imagined", "dream"):
            _, none, _ = transition(initial(), set(), cycle(), [evidence(source=source)], traits(), identity())
            self.assertEqual(none["evaluated_ids"], []); self.assertIsNone(none["persona_proposal"])

    def test_refresh_annotations_detaches_inputs_and_pages_are_snapshots(self):
        record, annotation = experience()
        copied = memory_record(record, "a"); record["content"] = "altered"
        before = observation(copied, annotation); annotation["tokens"][0] = "犬"
        self.assertEqual(before["tokens"][0], "猫")
        state, _, credited = transition(initial(), set(), cycle(), [before], traits(), identity())
        new = dict(before, annotation_revision=1, concepts=["social"])
        updated, _, _ = transition(state, set(credited), cycle("corrected", 1), [new], traits(), identity())
        self.assertEqual(inspect(updated, "explore", None)["records"], 0)
        self.assertEqual(inspect(updated, "social", None)["strength"], 1000)
        result = page(updated, 0, 1); result["entries"][0]["tokens"].clear()
        self.assertEqual(updated["entries"][0]["tokens"], ["猫", "は", "眠る"])

    def test_input_provenance_limits_rejected_without_truncation(self):
        bad = [dict(cycle_id="a", expected_revision=True, record_ids=[]), dict(cycle_id="a", expected_revision=0, record_ids=["a"] * 2),
               dict(cycle_id="a", expected_revision=4097, record_ids=[]), dict(cycle_id="a\x00", expected_revision=0, record_ids=[])]
        for value in bad:
            with self.assertRaises(ValueError): request(value)
        for count in (0, 17):
            value = evidence(); value["tokens"] = ["a"] * count
            with self.assertRaises(ValueError): sample(value)
        record, annotation = experience()
        for field, value in (("fingerprint", "b" * 64), ("source_kind", "dream"), ("tokens", ["犬"]), ("record_id", "b")):
            with self.subTest(field=field), self.assertRaises(ValueError): observation(record, dict(annotation, **{field: value}))
        invalid = traits(); invalid["revision"] = True
        with self.assertRaises(ValueError): persona(invalid, identity())
        invalid = traits(); invalid["updated_at"] = "2026-11-24T00:00:00+00:99"
        with self.assertRaises(ValueError): persona(invalid, identity())
        with self.assertRaises(ValueError): rules(identity()["trait_rules"] * 2)
        with self.assertRaises(ValueError): evidence(tokens=["\x01" * 64] * 16)

    def test_bounded_retention_window_and_pagination(self):
        state, credited = initial(), set()
        for number in range(6):
            ids = [f"{number}-{i}" for i in range(4)]
            state, receipt, added = transition(state, credited, cycle(str(number), number, ids), [evidence(k) for k in ids], traits(), identity())
            credited.update(added)
            self.assertEqual(len(state["entries"]), min(4 * (number + 1), 16))
        self.assertEqual(receipt["forgotten_ids"], [f"1-{i}" for i in range(4)])
        collected, after = [], 0
        while True:
            result = page(state, after, 4); collected.extend(result["entries"])
            if result["next_after"] is None: break
            after = result["next_after"]
        self.assertEqual(collected, state["entries"])
        # The guard also rejects a future policy/state that could exceed the window.
        over = deepcopy(state)
        for item in over["entries"]: item["strength"] = 1000
        with self.assertRaises(ActiveFull):
            transition(over, credited, cycle("overflow", 6, ["new"]), [evidence("new")], traits(), identity())


class SleepStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name).resolve() / "sleep.db")
        self.store = Store(self.path, identity()); self.store.open(); self.addCleanup(self.store.close)

    def save(self, key="one", ids=None):
        value = cycle(key, self.store.current["revision"], ids)
        return self.store.execute("save", value, [evidence(k) for k in value["record_ids"]], traits())

    def test_commit_replay_conflicts_restart_and_old_dream_not_restored(self):
        first = self.save(ids=["a", "b"])
        current = self.store.execute("state", 0, 4)
        second = self.save("two", [])
        self.assertEqual(self.store.execute("preflight", cycle(ids=["a", "b"])), first)
        self.assertEqual(self.store.execute("preflight", cycle(ids=["a"])).code, "sleep.cycle_conflict")
        self.assertEqual(self.store.execute("preflight", cycle("stale")).code, "sleep.revision_conflict")
        self.assertEqual(self.store.execute("get", "absent").code, "sleep.not_found")
        self.store.close(); self.store.open()
        self.assertEqual(self.store.execute("get", "one"), first)
        self.assertEqual(self.store.execute("get", "two"), second)
        self.assertNotEqual(self.store.execute("state", 0, 4)["dreams"], current["dreams"])
        self.assertEqual(self.store.credited, {"a", "b"})

    def test_transaction_failure_does_not_expire_dream_or_consume_id(self):
        first = self.save(ids=["a", "b"]); state = deepcopy(self.store.current)
        self.store.connection.execute("CREATE TRIGGER fail_write BEFORE UPDATE ON metadata BEGIN SELECT RAISE(ABORT, 'injected'); END")
        self.assertEqual(self.save("two", []).code, "sleep.storage")
        self.assertEqual(self.store.current, state)
        self.assertEqual(self.store.execute("get", "one"), first)
        self.assertEqual(self.store.execute("get", "two").code, "sleep.not_found")
        self.store.connection.execute("DROP TRIGGER fail_write")
        self.assertEqual(self.save("two", [])["revision"], 2)

    def test_all_4096_cycles_and_capacity_keep_existing_receipts(self):
        first = self.save(ids=[])
        for number in range(1, 4096):
            self.assertEqual(self.save(str(number), [])["revision"], number + 1)
        self.assertEqual(self.store.execute("preflight", cycle("overflow", 4096, [])).code, "sleep.history_full")
        self.assertEqual(self.store.execute("preflight", cycle(ids=[])), first)
        self.store.close(); self.store.open()
        self.assertEqual(self.store.current["revision"], 4096)

    def test_corrupt_receipt_unknown_format_and_identity_rejected_without_repair(self):
        self.save(); self.store.close()
        original = Path(self.path).read_bytes()
        other = identity(); other["trait_rules"][0]["delta"] = 4
        with self.assertRaises(ValueError): Store(self.path, other).open()
        self.assertEqual(Path(self.path).read_bytes(), original)
        for sql in ("PRAGMA user_version=99", "UPDATE cycles SET receipt='{}'", "UPDATE metadata SET state='{}'", "DELETE FROM credited"):
            Path(self.path).write_bytes(original)
            with closing(sqlite3.connect(self.path)) as db: db.execute(sql); db.commit()
            before = Path(self.path).read_bytes()
            with self.assertRaises((ValueError, sqlite3.DatabaseError)): self.store.open()
            self.assertEqual(Path(self.path).read_bytes(), before)
