"""B05 deterministic choices, evidence, journal integrity and activity proposals."""

# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from examples.agency_demo import activity_catalog, decision_input
from nymph_toolkit.contracts import OperationFailure
from nymph_toolkit.subsystems.agency._model import catalog, decide, dump, observation, request
from nymph_toolkit.subsystems.agency._store import Store


def evidence(value, documents=0):
    return [dict(goal_id=g["goal_id"],record_id=g["record_id"],token=g["token"],fingerprint="a"*64,source_kind="observed",documents=documents) for g in value["goals"]]


def normalized(key="one",**kwargs):
    return request(decision_input(key,**kwargs),catalog(activity_catalog()))


class AgencyPolicyTests(unittest.TestCase):
    def choose(self,value=None,documents=0,previous=None,templates=None):
        value=value or normalized()
        return decide(value,evidence(value,documents),templates or catalog(activity_catalog()),"agency",previous)

    def test_learning_and_internal_state_change_choice_with_independent_expected_scores(self):
        unknown=self.choose()
        self.assertEqual(unknown["selected"],dict(template_id="study",goal_id="understand-cat",motive="explore",score=800))
        self.assertEqual((unknown["directive"],unknown["plan"]["priority"],unknown["plan"]["duration_us"]),("start",800,252_000_000))
        self.assertIsNone(unknown["plan"]["start_at"])
        learned=self.choose(documents=1)
        self.assertEqual(learned["selected"]["template_id"],"apply")
        tired=self.choose(normalized(sleep_pressure=950),documents=1)
        self.assertEqual(tired["selected"]["template_id"],"sleep")
        value=normalized();value["state"]["social_need"]=900
        self.assertEqual(self.choose(value)["selected"]["template_id"],"talk")

    def test_competing_goals_ties_availability_and_zero_need(self):
        value=normalized(); goal=dict(value["goals"][0],goal_id="a",importance=900)
        value["goals"].append(goal);value=request(value,catalog(activity_catalog()))
        self.assertEqual(self.choose(value)["selected"]["goal_id"],"a")
        value["available"]=["sleep","talk"]
        self.assertEqual(self.choose(value)["selected"]["template_id"],"sleep")
        value["state"]={k:0 for k in value["state"]}
        self.assertEqual(self.choose(value)["directive"],"idle")
        value=normalized(sleep_pressure=800)
        self.assertEqual(self.choose(value)["selected"]["template_id"],"sleep") # lexical tie
        previous=self.choose()
        value["current"]=dict(decision_id="old",state="running",revision=3,planned_end_notified=False,supports_pause=True)
        self.assertEqual(self.choose(value,previous=previous)["selected"]["template_id"],"study") # retain current

    def test_schedule_and_fractional_learning_need(self):
        templates=catalog(activity_catalog()); next(t for t in templates if t["template_id"]=="study")["delay_seconds"]=100
        value=normalized();value["goals"][0]["target_documents"]=4
        result=self.choose(value,documents=1,templates=templates)
        self.assertEqual(result["selected"]["score"],600)
        self.assertEqual(result["plan"]["start_at"],"2026-11-24T12:00:40+00:00")
        self.assertEqual(result["plan"]["duration_us"],204_000_000)

    def test_unchanged_pending_plan_does_not_keep_postponing_on_reobservation(self):
        templates=catalog(activity_catalog());next(t for t in templates if t["template_id"]=="study")["delay_seconds"]=100
        value=normalized();first=self.choose(value,templates=templates)
        self.assertEqual(first["plan"]["start_at"],"2026-11-24T12:00:20+00:00")
        value=normalized("again");value["now"]="2026-11-24T12:00:10+00:00"
        value["current"]=dict(decision_id="one",state="pending",revision=0,planned_end_notified=False,supports_pause=False)
        same=self.choose(value,templates=templates,previous=first)
        self.assertEqual(same["directive"],"continue")
        self.assertEqual(same["plan"]["start_at"],first["plan"]["start_at"])
        value["goals"][0]["importance"]=900
        changed=self.choose(value,templates=templates,previous=first)
        self.assertEqual(changed["directive"],"change")
        self.assertEqual(changed["plan"]["priority"],900)

    def test_current_states_change_pause_resume_finish_wait_and_terminal_start(self):
        previous=self.choose()
        value=normalized("next")
        current=dict(decision_id="one",state="running",revision=7,planned_end_notified=False,supports_pause=True)
        value["current"]=current
        result=self.choose(value,previous=previous)
        self.assertEqual(result["directive"],"continue")
        self.assertEqual(result["target"]["expected_revision"],7)
        self.assertEqual(result["plan"]["activity_id"],previous["plan"]["activity_id"])
        current["planned_end_notified"]=True
        extended=self.choose(value,previous=previous)
        self.assertEqual((extended["directive"],extended["plan"]["duration_us"]),("change",504_000_000))
        current["planned_end_notified"]=False
        value["state"]["sleep_pressure"]=950
        self.assertEqual(self.choose(value,previous=previous)["directive"],"pause")
        current["supports_pause"]=False
        self.assertEqual(self.choose(value,previous=previous)["directive"],"finish")
        for state in ("starting","pausing","resume_pending","finishing"):
            current["state"]=state
            self.assertEqual(self.choose(value,previous=previous)["directive"],"wait")
        for state in ("completed","failed","stopped"):
            current["state"]=state
            started=self.choose(value,previous=previous)
            self.assertEqual(started["directive"],"start");self.assertIsNone(started["target"])
            self.assertNotEqual(started["plan"]["activity_id"],previous["plan"]["activity_id"])
        current["state"]="paused";value["state"]["sleep_pressure"]=100
        self.assertEqual(self.choose(value,previous=previous)["directive"],"resume")
        value["available"]=[]
        self.assertEqual(self.choose(value,previous=previous)["directive"],"finish")
        current["state"]="pending";value["available"]=["study"]
        value["goals"][0]["importance"]=700
        changed=self.choose(value,previous=previous)
        self.assertEqual(changed["directive"],"change");self.assertEqual(changed["plan"]["priority"],700)

    def test_strict_inputs_snapshots_bounds_and_unknown_fields(self):
        template=catalog(activity_catalog()); value=decision_input("snapshot")
        detached=request(value,template);value["goals"][0]["importance"]=0
        self.assertEqual(detached["goals"][0]["importance"],800)
        cases=[]
        for key,bad in (("decision_id"," "),("now","2026-11-24"),("now","2026-11-24T00:00:00+00:99"),("available",["unknown"]),("available",["sleep","sleep"]),("goals",[{}]*9),("current",{})):
            v=decision_input("bad");v[key]=bad;cases.append(v)
        for bad in (True,-1,1001,float("nan")):
            v=decision_input("bad");v["state"]["sleep_pressure"]=bad;cases.append(v)
        v=decision_input("bad");v["extra"]=1;cases.append(v)
        v=decision_input("bad");v["goals"][0]["token"]="猫 犬";cases.append(v)
        v=decision_input("bad");v["goals"][0]["importance"]=True;cases.append(v)
        for v in cases:
            with self.subTest(value=v),self.assertRaises((ValueError,TypeError)): request(v,template)
        for field,bad in (("motive","bad"),("parameters",[]),("min_seconds",0),("max_seconds",True),("delay_seconds",86401)):
            invalid=activity_catalog();invalid[0][field]=bad
            with self.assertRaises(ValueError):catalog(invalid)
        with self.assertRaises(ValueError):catalog(activity_catalog()*5)
        invalid=activity_catalog();invalid[0]["parameters"]={"x":"a"*4096}
        with self.assertRaises(ValueError):catalog(invalid)

    def test_changed_goal_execution_data_is_not_applied_as_activity_change(self):
        previous=self.choose();value=normalized("next")
        value["current"]=dict(decision_id="one",state="running",revision=0,planned_end_notified=False,supports_pause=True)
        value["goals"][0]["record_id"]="new-evidence"
        self.assertEqual(self.choose(value,previous=previous)["directive"],"pause")
        value=normalized("resume")
        value["current"]=dict(decision_id="one",state="paused",revision=2,planned_end_notified=True,supports_pause=True)
        result=self.choose(value,previous=previous)
        self.assertEqual(result["directive"],"resume");self.assertEqual(result["plan"],previous["plan"])

    def test_evidence_identity_source_and_goal_correspondence(self):
        goal=normalized()["goals"][0]
        record=dict(record_id="lesson",kind="experience",content="猫 は 眠る",source_kind="dream",source="fixture",occurred_at="2026-11-24T00:00:00Z",stored_at="2026-11-24T00:00:01Z",sequence=1)
        profile=dict(token="猫",documents=2,known=True,source_counts={"dream":2})
        result=observation(goal,record,profile)
        self.assertEqual(result["source_kind"],"dream");self.assertEqual(len(result["fingerprint"]),64)
        for bad in (dict(profile,token="犬"),dict(profile,documents=True),dict(profile,source_counts={"observed":2}),dict(profile,known=False)):
            with self.assertRaises(ValueError):observation(goal,record,bad)
        with self.assertRaises(ValueError):observation(goal,dict(record,record_id="else"),profile)
        with self.assertRaises(ValueError):observation(goal,dict(record,content="犬"),profile)
        with self.assertRaises(ValueError):observation(goal,dict(record,kind="invented"),profile)
        bad=dict(profile,documents=1,source_counts={"dream":True})
        with self.assertRaises(ValueError):observation(goal,record,bad)
        self.assertEqual(observation(goal,dict(record,content=" 猫 は 眠る ",source=" fixture "),profile)["documents"],2)


class AgencyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=str(Path(self.temp.name).resolve()/"agency.db")
        self.identity=dict(module_id="agency",catalog=catalog(activity_catalog()),memory_module_id="memory",cognition_module_id="cognition")
        self.store=Store(self.path,self.identity);self.store.open();self.addCleanup(self.store.close)

    def save(self,key="one",current=None):
        value=normalized(key);value["current"]=current
        old=self.store.execute("get",current["decision_id"]) if current else None
        data=evidence(value);result=decide(value,data,self.identity["catalog"],"agency",old)
        return self.store.execute("save",value,data,result)

    def test_replay_conflict_restart_and_detached_result(self):
        first=self.save()
        self.assertEqual(first["sequence"],1)
        self.assertEqual(self.store.execute("replay",normalized()),first)
        changed=normalized();changed["state"]["sleep_pressure"]=900
        self.assertEqual(self.store.execute("replay",changed).code,"agency.decision_conflict")
        self.save("next",dict(decision_id="one",state="running",revision=0,planned_end_notified=True,supports_pause=True))
        self.store.close();self.store.open()
        self.assertEqual(self.store.execute("get","one"),first)
        first["plan"]["content"]="mutated"
        self.assertNotEqual(self.store.execute("get","one"),first)
        self.assertEqual(self.store.execute("get","missing").code,"agency.not_found")

    def test_atomic_rollback_storage_failure_and_no_lost_prior_decisions(self):
        first=self.save()
        self.store.connection.execute("CREATE TEMP TRIGGER fail BEFORE UPDATE ON decisions BEGIN SELECT RAISE(ABORT,'injected'); END")
        self.assertEqual(self.save("failure").code,"agency.storage")
        self.assertEqual(self.store.execute("get","failure").code,"agency.not_found")
        self.assertEqual(self.store.execute("get","one"),first)
        self.store.connection.execute("DROP TRIGGER fail")
        self.assertEqual(self.save("failure")["sequence"],2)

    def test_full_journal_retains_get_and_replay(self):
        first=self.save()
        # Exercise the actual boundary with valid receipts, avoiding network I/O.
        for i in range(1,4096): self.save(str(i))
        self.assertEqual(self.save("overflow").code,"agency.history_full")
        self.assertEqual(self.store.execute("replay",normalized()),first)
        self.store.close();self.store.open()
        self.assertEqual(self.store.execute("get","one"),first)

    def test_unknown_version_configuration_and_corrupt_decisions_rejected_without_rewrite(self):
        self.save();self.store.close()
        changed=dict(self.identity,memory_module_id="other")
        before=Path(self.path).read_bytes()
        with self.assertRaises(ValueError):Store(self.path,changed).open()
        self.assertEqual(Path(self.path).read_bytes(),before)
        with closing(sqlite3.connect(self.path)) as db:db.execute("PRAGMA user_version=99")
        before=Path(self.path).read_bytes()
        with self.assertRaises(ValueError):self.store.open()
        self.assertEqual(Path(self.path).read_bytes(),before)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA user_version=1");db.execute("UPDATE decisions SET result='{}'");db.commit()
        before=Path(self.path).read_bytes()
        with self.assertRaises(ValueError):self.store.open()
        self.assertEqual(Path(self.path).read_bytes(),before)
