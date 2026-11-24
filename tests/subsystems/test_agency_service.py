"""B05 public integration, failures, admission and owned-worker shutdown."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from examples.agency_demo import activity_catalog, decision_input, group_at
from nymph_toolkit.contracts import BindingKey, LinkFailure, OperationFailure, OutcomeUnknown, Placement, ProtocolError, TemporaryUnavailable
from nymph_toolkit.contracts.agency import AGENCY_KEY
from nymph_toolkit.contracts.cognition import COGNITION_KEY
from nymph_toolkit.contracts.memory import MEMORY_KEY
from nymph_toolkit.core import Runtime
from nymph_toolkit.subsystems import agency
from tests.adapters.test_text_interaction import FakeCore


def record():
    return dict(record_id="lesson",kind="experience",content="猫 は 眠る",source_kind="observed",source="fixture",occurred_at="2026-11-24T00:00:00Z")


class Link:
    def __init__(self,core,key): self.core,self.key,self.closed=core,key,False
    async def acall(self,operation,*args,**kwargs):
        core=self.core;core.calls.append((self.key,operation,args,kwargs));core.entered.set()
        if core.wait is not None:await core.wait.wait()
        if core.failure is not None:
            if isinstance(core.failure,BaseException):raise core.failure
            return core.failure
        if self.key==MEMORY_KEY:return dict(record(),sequence=1,stored_at="2026-11-24T00:00:01Z")
        return dict(token="猫",documents=core.documents,known=bool(core.documents),source_counts={"observed":core.documents} if core.documents else {})
    async def close(self):self.closed=True


class Core(FakeCore):
    def __init__(self):super().__init__();self.failure=None;self.documents=0
    async def prepare(self,key,**kwargs):
        link=Link(self,key);self.links.append(link);return link


class AgencyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.core=Core();self.provided={}
        self.config=dict(path=str(Path(self.temp.name).resolve()/"agency.db"),memory_module_id="memory",cognition_module_id="cognition",catalog=activity_catalog())
        self.context=SimpleNamespace(module_id="agency",core=self.core,settings=SimpleNamespace(max_frame_bytes=65536),provide=lambda k,v:self.provided.update({k:v}))
        self.service=agency.factory(self.context,self.config);await self.service.start()
        self.addAsyncCleanup(self.service.stop)

    async def test_decision_saved_replay_precedes_changed_external_observations_and_get_is_local(self):
        first=await self.service.decide(decision_input("first"))
        self.assertEqual(first["selected"]["template_id"],"study")
        self.assertEqual(set(self.provided[AGENCY_KEY]),{"decide","get"})
        self.core.documents=1
        learned=await self.service.decide(decision_input("learned"))
        self.assertEqual(learned["selected"]["template_id"],"apply")
        calls=len(self.core.calls);self.core.failure=ProtocolError("offline")
        self.assertEqual(await self.service.decide(decision_input("first")),first)
        self.assertEqual(await self.service.get("first"),first)
        self.assertEqual(len(self.core.calls),calls)
        self.assertEqual(len(self.core.bindings),2)
        self.assertEqual((await self.service.decide(decision_input("first",sleep_pressure=500))).code,"agency.decision_conflict")

    async def test_capacity_business_failure_no_automatic_retry_or_binding_switch(self):
        self.core.available=False
        self.assertIsInstance(await self.service.decide(decision_input("full")),TemporaryUnavailable)
        self.assertEqual(self.core.bindings,[]);self.assertEqual(self.core.health,[])
        self.core.available=True;self.core.failure=OperationFailure("memory.not_found","unknown")
        self.assertEqual(await self.service.decide(decision_input("missing")),self.core.failure)
        self.assertEqual(len(self.core.calls),1)
        self.assertEqual((await self.service.get("missing")).code,"agency.not_found")

    async def test_link_failure_cooperative_close_ack_health_and_new_request(self):
        self.core.failure=LinkFailure(BindingKey("agency",MEMORY_KEY),"broken","interrupted")
        self.assertIsInstance(await self.service.decide(decision_input("one")),LinkFailure)
        self.assertEqual(len(self.core.calls),1);self.assertEqual(self.core.acks,["interrupted"])
        self.assertEqual(self.core.health,[("memory",)]);self.assertTrue(self.core.links[0].closed)
        self.core.failure=None
        self.assertIsInstance(await self.service.decide(decision_input("new")),dict)
        self.assertEqual(len(self.core.bindings),2) # Memory was not rebound; Cognition newly bound

    async def test_unknown_result_survives_recovery_and_reporting_failures(self):
        unknown=OutcomeUnknown("pending")
        self.core.failure=unknown;self.core.recovery_error=ProtocolError("health failed");self.core.reporting_error=ProtocolError("usage failed")
        with self.assertRaises(OutcomeUnknown) as caught:await self.service.decide(decision_input("uncertain"))
        self.assertIs(caught.exception,unknown);self.assertEqual(len(self.core.calls),1)
        self.assertTrue(self.core.links[0].closed);self.assertFalse(self.service.busy)

    async def test_input_snapshot_cancellation_and_stop_drain_admitted_decision(self):
        value=decision_input("snapshot");self.core.wait=asyncio.Event()
        task=asyncio.create_task(self.service.decide(value))
        await asyncio.wait_for(self.core.entered.wait(),5)
        value["state"]["sleep_pressure"]=1000;value["goals"][0]["importance"]=0
        self.assertIsInstance(await self.service.get("snapshot"),TemporaryUnavailable)
        task.cancel();stop=asyncio.create_task(self.service.stop());await asyncio.sleep(0)
        self.assertFalse(task.done());self.assertFalse(stop.done())
        self.core.wait.set()
        with self.assertRaises(asyncio.CancelledError):await task
        await stop
        self.assertTrue(all(l.closed for l in self.core.links));self.assertIsNone(self.service.pool)
        reopened=agency.factory(self.context,self.config);await reopened.start()
        try:
            result=await reopened.get("snapshot")
            self.assertEqual(result["selected"]["template_id"],"study")
        finally:await reopened.stop()

    async def test_cancel_during_journal_write_waits_for_commit_and_owned_worker(self):
        entered,released=threading.Event(),threading.Event()
        original=self.service.store._save
        def slow(*args):
            entered.set()
            if not released.wait(10):raise TimeoutError("test failed to release worker")
            return original(*args)
        self.service.store._save=slow
        task=asyncio.create_task(self.service.decide(decision_input("writing")))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,5))
            task.cancel();stop=asyncio.create_task(self.service.stop());await asyncio.sleep(0)
            self.assertFalse(task.done());self.assertFalse(stop.done())
        finally:released.set()
        with self.assertRaises(asyncio.CancelledError):await task
        await stop
        reopened=agency.factory(self.context,self.config);await reopened.start()
        try:self.assertEqual((await reopened.get("writing"))["decision_id"],"writing")
        finally:await reopened.stop()

    async def test_validation_reference_and_start_failure_cleanup(self):
        for value in ({},dict(decision_input("bad"),extra=1)):
            self.assertEqual((await self.service.decide(value)).code,"agency.invalid")
        value=decision_input("new")
        value["current"]=dict(decision_id="missing",state="running",revision=0,planned_end_notified=False,supports_pause=True)
        self.assertEqual((await self.service.decide(value)).code,"agency.not_found")
        self.assertEqual(self.core.calls,[])
        config=dict(self.config,path=str(Path(self.temp.name)/"missing"/"db"))
        failed=agency.factory(self.context,config)
        with self.assertRaises(Exception):await failed.start()
        self.assertIsNone(failed.pool);self.assertIsNone(failed.store.connection)
        await failed.stop()

    def test_agency_imports_only_public_contracts(self):
        for path in Path(agency.__file__).parent.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ""] if isinstance(node,ast.ImportFrom) else []
                for name in names:
                    if name.startswith("nymph_toolkit."):self.assertTrue(name.startswith("nymph_toolkit.contracts"),(path,name))


class AgencyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_placements_both_routes_actual_learning_and_restart(self):
        for decision_placement in Placement:
            for storage in Placement:
                with self.subTest(agency=decision_placement,storage=storage),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory).resolve();first=None;memory_before=None
                    for restored in (False,True):
                        group=group_at(root,agency=decision_placement,storage=storage)
                        runtime=Runtime(group);await runtime.start()
                        try:
                            core=group.client("requester")
                            for key,provider in ((MEMORY_KEY,"memory"),(COGNITION_KEY,"cognition"),(AGENCY_KEY,"agency")):
                                await core.bind(key,provider,timeout=5)
                            memory=await core.invoke(MEMORY_KEY,"put",record(),timeout=5)
                            self.assertIsInstance(memory,dict,repr(memory))
                            if memory_before:self.assertEqual(memory,memory_before)
                            memory_before=memory
                            if not restored:
                                first=await core.invoke(AGENCY_KEY,"decide",decision_input("first"),timeout=10)
                                self.assertIsInstance(first,dict,repr(first))
                                self.assertEqual(first["selected"]["template_id"],"study")
                                learned=await core.invoke(COGNITION_KEY,"learn","lesson",tokens=["猫","は","眠る"],concepts=["sleep"],timeout=10)
                                self.assertIsInstance(learned,dict,repr(learned))
                                second=await core.invoke(AGENCY_KEY,"decide",decision_input("second"),timeout=10)
                                self.assertEqual(second["selected"]["template_id"],"apply")
                                self.assertEqual(second["evidence"][0]["documents"],1)
                                self.assertEqual(second["evidence"][0]["fingerprint"],first["evidence"][0]["fingerprint"])
                                value=decision_input("change",sleep_pressure=950)
                                value["current"]=dict(decision_id="second",state="running",revision=0,planned_end_notified=False,supports_pause=True)
                                changed=await core.invoke(AGENCY_KEY,"decide",value,timeout=10)
                                self.assertEqual(changed["directive"],"pause")
                                self.assertEqual(changed["target"]["activity_id"],second["plan"]["activity_id"])
                            link=await core.prepare(AGENCY_KEY,timeout=5)
                            try:
                                self.assertEqual(await link.acall("decide",decision_input("first"),timeout=10),first)
                                self.assertEqual(await link.acall("get","first",timeout=5),first)
                            finally:await link.close()
                            self.assertEqual(await core.invoke(MEMORY_KEY,"get","lesson",timeout=5),memory_before)
                        finally:await runtime.stop()
                        self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))
                    await asyncio.sleep(0)
                    self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])
