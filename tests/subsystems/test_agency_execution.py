"""B06: autonomous decisions, actual learning/execution, changes and ownership."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from examples.agency_execution_demo import catalog, group_at, observation, until
from nymph_toolkit.contracts import (
    ActivityCommandResult, ActivityCommandStatus, ActivityFinishReason, ActivityKey, ActivityRequest, ActivitySnapshot, ActivityState,
    OutcomeUnknown, PeerClosed, Placement, ProtocolError, TemporaryUnavailable,
)
from nymph_toolkit.contracts.agency import AGENCY_ACTIVITIES_KEY as CONTROL, AGENCY_KEY
from nymph_toolkit.contracts.cognition import COGNITION_KEY
from nymph_toolkit.contracts.memory import MEMORY_KEY
from nymph_toolkit.core import Runtime
from nymph_toolkit.subsystems.agency import execution_factory
from tests.subsystems.test_agency_service import Core


def lesson():
    return dict(record_id="lesson",kind="experience",content="猫 は 眠る",source_kind="observed",source="test:execution",occurred_at="2026-11-24T00:00:00Z")


async def connect(group):
    core=group.client("requester")
    for key,target in ((MEMORY_KEY,"memory"),(COGNITION_KEY,"cognition"),(CONTROL,"agency"),(AGENCY_KEY,"agency")):
        await core.bind(key,target,timeout=5)
    return core


async def decision(core,decision_id):
    async with asyncio.timeout(5):
        while True:
            result=await core.invoke(AGENCY_KEY,"get",decision_id,timeout=5)
            if not isinstance(result,TemporaryUnavailable):return result
            await asyncio.sleep(.01)


class ExecutionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_plan_is_reported_without_starting_or_moving_the_time(self):
        class OldClock:
            @staticmethod
            def now(zone):return datetime.now(zone)-timedelta(seconds=10)
        templates=[dict(t,delay_seconds=2) for t in catalog() if t["template_id"]=="rest"]
        value=dict(state=dict(sleep_pressure=500,cognitive_load=0,social_need=0),goals=[],available=["rest"])
        with tempfile.TemporaryDirectory() as directory:
            group=group_at(Path(directory).resolve(),templates=templates);runtime=Runtime(group)
            await runtime.start()
            try:
                core=await connect(group)
                with patch('nymph_toolkit.subsystems.agency._execution.datetime',OldClock):
                    await core.invoke(CONTROL,"activate","expired",value,timeout=5)
                    state=await until(core,lambda s:s["state"]=="failed")
                self.assertEqual(state["error"]["code"],"ActivityStartInPastError")
                self.assertEqual(state["total_activities"],0)
                saved=await decision(core,state["last_decision_id"])
                self.assertEqual(saved["directive"],"start")
                self.assertLess(datetime.fromisoformat(saved["plan"]["start_at"]),datetime.now(timezone.utc))
                await asyncio.sleep(.06)
                self.assertEqual((await core.invoke(CONTROL,"status",timeout=5))["last_decision_id"],state["last_decision_id"])
            finally:await runtime.stop()

    async def test_execution_failure_and_unsupported_pause_stop_without_retry(self):
        for bad_teaching in (False,True):
            with self.subTest(bad_teaching=bad_teaching),tempfile.TemporaryDirectory() as directory:
                templates=catalog()
                if bad_teaching:
                    next(t for t in templates if t["template_id"]=="study")["parameters"]["tokens"]=["wrong"]
                group=group_at(Path(directory).resolve(),templates=templates,supports_pause=False)
                runtime=Runtime(group);await runtime.start()
                try:
                    core=await connect(group)
                    await core.invoke(MEMORY_KEY,"put",lesson(),timeout=5)
                    await core.invoke(CONTROL,"activate","failure",observation(),timeout=5)
                    if not bad_teaching:
                        await until(core,lambda s:any(a["template_id"]=="apply" and a["state"]=="running" for a in s["activities"]))
                        await core.invoke(CONTROL,"observe","failure",0,observation(950),timeout=5)
                    state=await until(core,lambda s:s["state"]=="failed")
                    self.assertEqual(state["error"]["code"],"agency.execution_failed" if bad_teaching else "agency.command_rejected")
                    self.assertTrue(all(a["cleanup_confirmed"] for a in state["activities"]))
                    if not bad_teaching:self.assertEqual(state["error"]["message"],"unsupported_operation")
                    await asyncio.sleep(.05)
                    self.assertEqual((await core.invoke(CONTROL,"status",timeout=5))["total_activities"],1 if bad_teaching else 2)
                finally:await runtime.stop()

    async def test_activity_bound_and_missing_executor_fail_without_repeating(self):
        for missing in (False, True):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as directory:
                templates=catalog()
                if missing:
                    for t in templates:t["executor_id"]="absent"
                group=group_at(Path(directory).resolve(),templates=templates,max_activities=1)
                runtime=Runtime(group);await runtime.start()
                try:
                    core=await connect(group)
                    await core.invoke(MEMORY_KEY,"put",lesson(),timeout=5)
                    await core.invoke(CONTROL,"activate","bounded",observation(),timeout=5)
                    failed=await until(core,lambda s:s["state"]=="failed")
                    self.assertIsNotNone(failed["error"])
                    self.assertEqual(failed["total_activities"],0 if missing else 1)
                    if not missing:self.assertEqual(failed["error"]["code"],"agency.activity_full")
                    await asyncio.sleep(.06)
                    self.assertEqual((await core.invoke(CONTROL,"status",timeout=5))["total_activities"],failed["total_activities"])
                finally:await runtime.stop()

    async def test_four_placements_learning_pause_resume_both_routes_restart(self):
        for agency in Placement:
            for worker in Placement:
                with self.subTest(agency=agency,worker=worker),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory).resolve();first_id=None
                    for restored in (False,True):
                        group=group_at(root,agency=agency,worker=worker); runtime=Runtime(group)
                        await runtime.start()
                        try:
                            core=await connect(group)
                            self.assertEqual((await core.invoke(CONTROL,"status",timeout=5))["state"],"inactive")
                            if restored:
                                history=await core.invoke(CONTROL,"history",timeout=5)
                                self.assertFalse(history.issues)
                                self.assertTrue(history.records)
                                self.assertEqual((await decision(core,first_id))["selected"]["template_id"],"study")
                                await asyncio.sleep(.05)
                                self.assertEqual((await core.invoke(CONTROL,"status",timeout=5))["total_activities"],0)
                                continue
                            memory=await core.invoke(MEMORY_KEY,"put",lesson(),timeout=5)
                            await core.invoke(CONTROL,"activate","integration",observation(),timeout=5)
                            state=await until(core,lambda s:any(a["template_id"]=="apply" and a["state"]=="running" for a in s["activities"]))
                            self.assertEqual([a["template_id"] for a in state["activities"]],["study","apply"])
                            first_id=state["activities"][0]["decision_id"]
                            applied_id=state["activities"][1]["activity_id"]
                            self.assertEqual(state["activities"][0]["state"],"completed")
                            link=await core.prepare(CONTROL,timeout=5)
                            try:
                                await link.acall("observe","integration",0,observation(950),timeout=5)
                                state=await until(core,lambda s:any(a["template_id"]=="rest" and a["state"]=="running" for a in s["activities"]))
                                self.assertEqual(state["activities"][1]["state"],"paused")
                                await link.acall("observe","integration",1,observation(),timeout=5)
                                state=await until(core,lambda s:any(e["operation"]=="resume" and e["status"]=="applied" for e in s["recent_operations"]))
                                self.assertEqual(state["total_activities"],3)
                                self.assertEqual(state["foreground"],applied_id)
                                await link.acall("halt","integration",timeout=5)
                                state=await until(core,lambda s:s["state"]=="stopped")
                                self.assertTrue(all(a["cleanup_confirmed"] and a["timing_confirmed"] for a in state["activities"]))
                            finally:await link.close()
                            profile=await core.invoke(COGNITION_KEY,"inspect","猫",source_kind="observed",after=0,limit=1,timeout=5)
                            self.assertEqual(profile["documents"],1)
                            self.assertEqual(await core.invoke(MEMORY_KEY,"get","lesson",timeout=5),memory)
                        finally:await runtime.stop()
                        self.assertTrue(all(group.process(n).cleanup_confirmed for n in group.modules))
                    await asyncio.sleep(0)
                    self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    async def test_duration_priority_changes_and_one_extension_per_schedule(self):
        templates=[dict(t,min_seconds=1,max_seconds=1) for t in catalog() if t["template_id"]=="rest"]
        value=dict(state=dict(sleep_pressure=500,cognitive_load=0,social_need=0),goals=[],available=["rest"])
        with tempfile.TemporaryDirectory() as directory:
            group=group_at(Path(directory).resolve(),templates=templates); runtime=Runtime(group)
            await runtime.start()
            try:
                core=await connect(group)
                await core.invoke(CONTROL,"activate","time",value,timeout=5)
                first=await until(core,lambda s:bool(s["activities"]) and s["activities"][0]["state"]=="running")
                extended=await until(core,lambda s:bool(s["activities"]) and s["activities"][0]["duration_us"]==2000000)
                self.assertEqual(extended["activities"][0]["scheduled_revision"],1)
                await asyncio.sleep(.15)
                unchanged=await core.invoke(CONTROL,"status",timeout=5)
                self.assertEqual(unchanged["activities"][0]["duration_us"],2000000)
                self.assertEqual(unchanged["activities"][0]["planned_start_at"],first["activities"][0]["planned_start_at"])
                await core.invoke(CONTROL,"halt","time",timeout=5)
                await until(core,lambda s:s["state"]=="stopped")
            finally:await runtime.stop()

    async def test_pending_start_changed_only_before_execution_and_observation_conflict(self):
        templates=[dict(t,min_seconds=10,max_seconds=20,delay_seconds=6) for t in catalog() if t["template_id"]=="rest"]
        value=dict(state=dict(sleep_pressure=500,cognitive_load=0,social_need=0),goals=[],available=["rest"])
        with tempfile.TemporaryDirectory() as directory:
            group=group_at(Path(directory).resolve(),templates=templates);runtime=Runtime(group)
            await runtime.start()
            try:
                core=await connect(group)
                await core.invoke(CONTROL,"activate","schedule",value,timeout=5)
                pending=await until(core,lambda s:bool(s["activities"]))
                self.assertEqual(pending["activities"][0]["state"],"pending")
                self.assertEqual(pending["activities"][0]["duration_us"],15000000)
                value["state"]["sleep_pressure"]=1000
                await core.invoke(CONTROL,"observe","schedule",0,value,timeout=5)
                running=await until(core,lambda s:bool(s["activities"]) and s["activities"][0]["state"]=="running")
                self.assertEqual(running["activities"][0]["duration_us"],20000000)
                self.assertEqual(running["activities"][0]["priority"],1000)
                self.assertLess(running["activities"][0]["planned_start_at"],pending["activities"][0]["planned_start_at"])
                duplicate=await core.invoke(CONTROL,"observe","schedule",0,value,timeout=5)
                self.assertEqual(duplicate["observation_revision"],1)
                value["state"]["sleep_pressure"]=800
                conflict=await core.invoke(CONTROL,"observe","schedule",0,value,timeout=5)
                self.assertEqual(conflict.code,"agency.revision_conflict")
                await core.invoke(CONTROL,"observe","schedule",1,value,timeout=5)
                changed=await until(core,lambda s:s["activities"][0]["priority"]==800)
                self.assertEqual(changed["activities"][0]["duration_us"],18000000)
                self.assertEqual(changed["activities"][0]["planned_start_at"],running["activities"][0]["planned_start_at"])
                await core.invoke(CONTROL,"halt","schedule",timeout=5)
                await until(core,lambda s:s["state"]=="stopped")
            finally:await runtime.stop()

    async def test_completed_work_not_repeated_and_runtime_stop_cleans_active_work(self):
        with tempfile.TemporaryDirectory() as directory:
            group=group_at(Path(directory).resolve()); runtime=Runtime(group);await runtime.start()
            core=await connect(group)
            try:
                await core.invoke(MEMORY_KEY,"put",lesson(),timeout=5)
                value=observation();value["available"]=["study"]
                await core.invoke(CONTROL,"activate","once",value,timeout=5)
                waiting=await until(core,lambda s:s["state"]=="waiting" and any(a["state"]=="completed" for a in s["activities"]))
                await asyncio.sleep(.08)
                self.assertEqual((await core.invoke(CONTROL,"status",timeout=5))["total_activities"],1)
                await core.invoke(CONTROL,"activate","once",value,timeout=5)
                self.assertEqual((await core.invoke(CONTROL,"status",timeout=5))["total_activities"],1)
                await core.invoke(CONTROL,"observe","once",waiting["observation_revision"],observation(950),timeout=5)
                running=await until(core,lambda s:any(a["template_id"]=="rest" and a["state"]=="running" for a in s["activities"]))
                key=ActivityKey("agency",running["foreground"])
            finally:await runtime.stop()
            ended=group.activities.snapshot(key)
            self.assertEqual(ended.state,ActivityState.STOPPED)
            self.assertTrue(ended.cleanup_confirmed)


class ExecutionControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.core=Core();self.provided={}
        config=dict(path=str(Path(self.temp.name).resolve()/"agency.db"),memory_module_id="memory",cognition_module_id="cognition",catalog=catalog(),
                    execution=dict(poll_seconds=.02,max_activities=16,pause_executors=[]))
        context=SimpleNamespace(module_id="agency",core=self.core,settings=SimpleNamespace(max_frame_bytes=65536),provide=lambda k,v:self.provided.update({k:v}))
        self.config,self.context=config,context
        self.service=execution_factory(context,config);await self.service.start();self.addAsyncCleanup(self.service.stop)

    async def test_strict_contract_inputs_idempotence_and_snapshot(self):
        self.assertEqual(set(self.provided[CONTROL]),{"activate","observe","status","halt","history"})
        self.assertEqual((await self.service.status())["state"],"inactive")
        self.assertEqual((await self.service.activate("bad",dict(observation(),current=None))).code,"agency.invalid")
        self.assertEqual((await self.service.status(limit=True)).code,"agency.invalid")
        value=observation();first=await self.service.activate("one",value)
        value["state"]["sleep_pressure"]=999
        self.assertEqual(self.service.observed["state"]["sleep_pressure"],100)
        self.assertEqual((await self.service.activate("one",value)).code,"agency.session_conflict")
        self.assertEqual((await self.service.activate("one",observation()))["observation_revision"],0)
        self.assertIsInstance(await self.service.activate("two",value),TemporaryUnavailable)
        self.assertEqual((await self.service.observe("one",True,value)).code,"agency.invalid")
        updated=await self.service.observe("one",0,value)
        self.assertEqual(updated["observation_revision"],1)
        self.assertEqual((await self.service.observe("one",0,value))["observation_revision"],1)
        self.assertEqual((await self.service.halt("one"))["state"],"stopping")
        await self.service._tick()
        self.assertEqual((await self.service.status())["state"],"stopped")

    def test_execution_setting_bounds_reject_before_opening_storage(self):
        for key,value in (("poll_seconds",True),("poll_seconds",float('nan')),("poll_seconds",.001),
                          ("poll_seconds",61),("max_activities",False),("max_activities",0),("max_activities",129),
                          ("pause_executors",{}),("pause_executors",[dict(module_id="worker",executor_id="rest")]*2)):
            with self.subTest(key=key,value=value):
                config=dict(self.config,execution=dict(self.config["execution"],**{key:value}))
                with self.assertRaises((ValueError,TypeError)):execution_factory(self.context,config)

    async def test_unconfirmed_terminal_cleanup_blocks_new_session(self):
        now=datetime.now(timezone.utc)
        req=ActivityRequest(ActivityKey("agency","lost"),"lost",None,timedelta(seconds=1))
        state=ActivitySnapshot(req,ActivityState.FAILED,now,now,now+timedelta(seconds=1),cleanup_confirmed=False)
        self.service.mode="failed";self.service.records=[dict(snapshot=state)]
        self.assertIsInstance(await self.service.activate("new",observation()),TemporaryUnavailable)

    async def test_management_unknown_uses_same_result_handle_and_cancellation_drains(self):
        entered=asyncio.Event();answer=asyncio.Event();calls=[];released=[]
        async def activity(operation,key=None,**kwargs):
            calls.append(operation);entered.set();raise OutcomeUnknown(17)
        def result(request_id):
            self.assertEqual(request_id,17)
            if not answer.is_set():raise OutcomeUnknown(request_id)
            return {"confirmed":True}
        self.core.activity=activity;self.core.result=result;self.core.release=released.append
        task=asyncio.create_task(self.service._core("snapshot",ActivityKey("agency","one")))
        await entered.wait();await asyncio.sleep(.03)
        self.assertEqual((await self.service.status())["unknown"],{"request_id":17,"operation":"snapshot"})
        task.cancel();await asyncio.sleep(0);self.assertFalse(task.done())
        answer.set()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(calls,["snapshot"]);self.assertEqual(released,[17])
        self.assertIsNone((await self.service.status())["unknown"])

    async def test_new_observation_during_evidence_read_does_not_apply_old_decision(self):
        self.core.wait=asyncio.Event()
        await self.service.activate("one",observation())
        tick=asyncio.create_task(self.service._tick())
        await self.core.entered.wait()
        await self.service.observe("one",0,observation(950))
        self.core.wait.set();await tick
        self.assertEqual((await self.service.status())["total_activities"],0)
        self.assertIsNone(self.service.last_signature)

    async def test_capacity_wait_does_not_retry_without_observation_or_stop_activities(self):
        self.core.available=False
        await self.service.activate("one",observation())
        await self.service._tick()
        self.assertEqual((await self.service.status())["state"],"waiting")
        counter=self.service.counter
        await self.service._tick()
        self.assertEqual(self.service.counter,counter)
        self.assertEqual(self.core.health,[])
        self.assertIsNone(self.service.error)
        async def submit(req,module_id,executor_id,arguments,**kwargs):
            now=datetime.now(timezone.utc)
            return ActivitySnapshot(req,ActivityState.RUNNING,now,now,now+req.duration,started_at=now)
        self.core.available=True;self.core.submit_remote=submit
        await self.service.observe("one",0,observation())
        await self.service._tick()
        self.assertEqual((await self.service.status())["state"],"active")
        self.assertEqual(len(self.service.records),1)

    async def test_sessions_bounded_and_prior_failure_not_reported_as_success(self):
        await self.service.activate("failed",observation())
        self.service.mode="failed";self.service.error={"code":"test.failure","message":"failed"}
        await self.service.activate("next",observation())
        replay=await self.service.activate("failed",observation())
        self.assertEqual(replay["state"],"failed")
        self.assertEqual(replay["error"]["code"],"test.failure")
        for i in range(2,64):
            await self.service.halt(self.service.session);await self.service._tick()
            self.assertIsInstance(await self.service.activate(str(i),observation()),dict)
        await self.service.halt(self.service.session);await self.service._tick()
        self.assertEqual((await self.service.activate("overflow",observation())).code,"agency.session_full")
        self.assertIsInstance(await self.service.activate("next",observation()),dict)

    async def test_failed_resolution_retains_unknown_and_prevents_new_session(self):
        async def activity(*args,**kwargs):raise OutcomeUnknown(31)
        def result(request_id):raise PeerClosed("Transport lost; effects unknown")
        self.core.activity=activity;self.core.result=result
        with self.assertRaises(PeerClosed):await self.service._core("finish",ActivityKey("agency","lost"))
        self.service.mode="failed"
        self.assertEqual((await self.service.status())["unknown"]["request_id"],31)
        self.assertIsInstance(await self.service.activate("new",observation()),TemporaryUnavailable)

    async def test_dependency_unknown_is_not_hidden_by_recovery_failure(self):
        self.core.failure=OutcomeUnknown(77)
        self.core.recovery_error=ProtocolError("Health report failed")
        await self.service.activate("unknown",observation())
        running=asyncio.create_task(self.service.run())
        try:
            async with asyncio.timeout(5):
                while (await self.service.status())["state"]!="failed":await asyncio.sleep(.01)
            error=(await self.service.status())["error"]
            self.assertEqual(error["code"],"OutcomeUnknown")
            self.assertEqual(error["request_id"],77)
            self.assertEqual(error["scope"],"decision_dependency")
            self.assertEqual(len(self.core.calls),1)
        finally:
            running.cancel();await asyncio.gather(running,return_exceptions=True)

    async def test_link_interruption_finishes_owned_activity_before_acknowledging(self):
        now=datetime.now(timezone.utc)
        req=ActivityRequest(ActivityKey("agency","owned"),"test",None,timedelta(seconds=60))
        state=ActivitySnapshot(req,ActivityState.RUNNING,now,now,now+timedelta(seconds=60),started_at=now)
        order=[]
        async def activity(operation,key=None,**kwargs):
            nonlocal state
            self.assertEqual(key,req.key)
            order.append(operation)
            if operation=="finish":
                self.assertEqual(kwargs["reason"],ActivityFinishReason.CONNECTION_INTERRUPTION)
                state=replace(state,state=ActivityState.STOPPED,ended_at=now)
            return state
        async def acknowledge(notice_id,**kwargs):
            self.assertTrue(state.state.terminal and state.cleanup_confirmed)
            order.append("ack")
        self.core.activity=activity;self.core.acknowledge_interruption=acknowledge
        await self.service.activate("owned",observation())
        self.service.records=[dict(key=req.key,snapshot=state,finish_sent=False)]
        await self.service._recover(MEMORY_KEY,"notice-1")
        self.assertLess(order.index("finish"),order.index("ack"))
        self.assertEqual(self.core.health,[("memory",)])
        self.assertEqual(order.count("finish"),1)

    async def test_pause_receipt_does_not_replace_applied_plan_and_rejection_is_retained(self):
        now=datetime.now(timezone.utc)
        req=ActivityRequest(ActivityKey("agency","current"),"current",None,timedelta(seconds=60))
        observed=ActivitySnapshot(req,ActivityState.PAUSING,now,now,now+timedelta(seconds=60),revision=4)
        original={"decision_id":"applied","plan":{"template_id":"study"}}
        record=dict(key=req.key,decision=original,plan=original["plan"],snapshot=observed)
        proposed=dict(decision_id="pause",directive="pause",plan={"template_id":"rest"})
        self.service.foreground=record
        accepted=ActivityCommandResult(req.key,"pause-command","pause",now,ActivityCommandStatus.ACCEPTED,None,observed)
        await self.service._command_result(record,proposed,accepted)
        self.assertIs(record["decision"],original)
        self.assertIs(self.service.foreground,record)
        self.assertIsNotNone(self.service.pending)
        applied=replace(accepted,status=ActivityCommandStatus.APPLIED,snapshot=replace(observed,state=ActivityState.PAUSED,revision=5))
        await self.service._command_result(record,proposed,applied)
        self.assertEqual(record["plan"]["template_id"],"study")
        self.assertIsNone(self.service.foreground)
        rejected=replace(accepted,status=ActivityCommandStatus.REJECTED,reason="revision_conflict")
        with self.assertRaisesRegex(Exception,"revision_conflict"):
            await self.service._command_result(record,proposed,rejected)
        self.assertEqual(self.service.events[-1]["status"],"rejected")
        self.assertEqual(self.service.events[-1]["reason"],"revision_conflict")
