"""Agency chooses real learning work and controls it through TaskManager."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import (
    HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, Placement, Usage,
)
from nymph_toolkit.contracts.agency import AGENCY_CONTRACT, AGENCY_KEY, AGENCY_ACTIVITIES_CONTRACT, AGENCY_ACTIVITIES_KEY
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT, COGNITION_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


def observation(sleep_pressure=100):
    return dict(state=dict(sleep_pressure=sleep_pressure,cognitive_load=100,social_need=0),
        goals=[dict(goal_id="cat",record_id="lesson",token="猫",importance=800,target_documents=1)],
        available=["study","apply","rest"])


def catalog():
    return [dict(template_id=name,motive=motive,content=content,executor_module_id="worker",executor_id=name,
                 parameters={"tokens":["猫","は","眠る"],"concepts":["sleep"]} if name=="study" else {},
                 min_seconds=60,max_seconds=300,delay_seconds=0)
            for name,motive,content in (("study","explore","Learn from the supplied lesson"),
                                       ("apply","achieve","Consult learned evidence"),("rest","rest","Rest"))]


class Worker:
    def __init__(self,context,config):
        self.context,self.config,self.link=context,config,None
        context.provide_executor("study",self.study,supports_pause=config.get("supports_pause",True))
        context.provide_executor("apply",self.apply,supports_pause=config.get("supports_pause",True))
        context.provide_executor("rest",self.rest,supports_pause=config.get("supports_pause",True))

    async def start(self):
        await self.context.core.publish_usage(Usage(OperatingState.RUNNING,True,0,32))

    async def run(self): await asyncio.Event().wait()

    async def stop(self):
        if self.link is not None: await self.link.close()

    async def _call(self,operation,*args,**kwargs):
        if self.link is None:
            await self.context.core.bind(COGNITION_KEY,"cognition",timeout=5)
            self.link=await self.context.core.prepare(COGNITION_KEY,timeout=5)
        result=await self.link.acall(operation,*args,timeout=5,**kwargs)
        if not isinstance(result,dict):raise RuntimeError(f"Learning operation failed: {result}")
        return result

    async def _hold(self,activity):
        checkpoints=0
        while True:
            reason=await activity.checkpoint()
            if reason is not None:return checkpoints
            checkpoints+=1
            await activity.wait_for_control()

    async def study(self,activity,arguments):
        if await activity.checkpoint() is not None:return {"learned":False}
        teaching=arguments["configured"]
        receipt=await self._call("learn",arguments["goal"]["record_id"],tokens=teaching["tokens"],concepts=teaching["concepts"])
        return {"learned":True,"receipt":receipt}

    async def apply(self,activity,arguments):
        profile=await self._call("inspect",arguments["goal"]["token"],source_kind="observed",after=0,limit=1)
        checkpoints=await self._hold(activity)
        return {"documents":profile["documents"],"checkpoints":checkpoints}

    async def rest(self,activity,arguments):
        return {"checkpoints":await self._hold(activity)}


def worker_factory(context,config):return Worker(context,config)


class Requester:
    def __init__(self,context):self.context=context
    async def start(self):await self.context.core.publish_usage(Usage(OperatingState.RUNNING,True,0,32))
    async def run(self):await asyncio.Event().wait()
    async def stop(self):pass


def requester_factory(context,config):return Requester(context)


def group_at(root, *, agency=Placement.LOCAL, worker=Placement.PROCESS, templates=None, max_activities=32, supports_pause=True):
    store=FileStore(root/"core",root/"archive",retention=timedelta(days=1),batch_size=16,flush_interval=.05)
    group=HybridGroup(HybridSettings(10,3,30,65536,32,4),store)
    group.enable_activities(clock_check_interval=.02,max_running=1)
    own_module="agency_execution_demo" if __name__=="__main__" else __name__
    for name,depends,contracts,factory,config,placement in (
        ("memory",(),(MEMORY_CONTRACT,),"nymph_toolkit.subsystems.memory:factory",dict(path=str(root/"memory.db")),Placement.LOCAL),
        ("cognition",("memory",),(COGNITION_CONTRACT,),"nymph_toolkit.subsystems.cognition:factory",dict(path=str(root/"cognition.db"),memory_module_id="memory"),Placement.LOCAL),
        ("worker",("cognition",),(),own_module+":worker_factory",dict(supports_pause=supports_pause),worker),
        ("agency",("memory","cognition","worker"),(AGENCY_CONTRACT,AGENCY_ACTIVITIES_CONTRACT),"nymph_toolkit.subsystems.agency:execution_factory",
         dict(path=str(root/"agency.db"),memory_module_id="memory",cognition_module_id="cognition",catalog=templates or catalog(),
              execution=dict(poll_seconds=.02,max_activities=max_activities,pause_executors=[dict(module_id="worker",executor_id=k) for k in ("study","apply","rest")])),agency),
        ("requester",("agency",),(),own_module+":requester_factory",{},Placement.LOCAL),
    ):
        group.register_module(ModuleSpec(name,ModuleKind.SUBSYSTEM,depends),ModuleAdvertisement(name,"example-1",contracts),factory,config,placement)
    return group


async def until(core, predicate):
    last=None
    async with asyncio.timeout(15):
        while True:
            last=await core.invoke(AGENCY_ACTIVITIES_KEY,"status",timeout=5)
            if isinstance(last,dict) and predicate(last):return last
            if isinstance(last,dict) and last["state"]=="failed":raise AssertionError(last)
            await asyncio.sleep(.02)


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-agency-execution-") as directory:
        root=Path(directory).resolve(); group=group_at(root); runtime=Runtime(group)
        await runtime.start()
        try:
            core=group.client("requester")
            for key,target in ((MEMORY_KEY,"memory"),(COGNITION_KEY,"cognition"),(AGENCY_ACTIVITIES_KEY,"agency"),(AGENCY_KEY,"agency")):
                await core.bind(key,target,timeout=5)
            await core.invoke(MEMORY_KEY,"put",dict(record_id="lesson",kind="experience",content="猫 は 眠る",source_kind="observed",source="example:cycle",occurred_at="2026-11-24T00:00:00Z"),timeout=5)
            assert (await core.invoke(AGENCY_ACTIVITIES_KEY,"status",timeout=5))["state"]=="inactive"
            await core.invoke(AGENCY_ACTIVITIES_KEY,"activate","demo",observation(),timeout=5)
            applied=await until(core,lambda s:any(a["template_id"]=="apply" and a["state"]=="running" for a in s["activities"]))
            await core.invoke(AGENCY_ACTIVITIES_KEY,"observe","demo",applied["observation_revision"],observation(950),timeout=5)
            rested=await until(core,lambda s:any(a["template_id"]=="rest" and a["state"]=="running" for a in s["activities"]))
            assert any(a["template_id"]=="apply" and a["state"]=="paused" for a in rested["activities"]),rested
            await core.invoke(AGENCY_ACTIVITIES_KEY,"observe","demo",rested["observation_revision"],observation(),timeout=5)
            resumed=await until(core,lambda s:any(e["operation"]=="resume" and e["status"]=="applied" for e in s["recent_operations"]))
            assert resumed["total_activities"]==3,resumed
            await core.invoke(AGENCY_ACTIVITIES_KEY,"halt","demo",timeout=5)
            stopped=await until(core,lambda s:s["state"]=="stopped")
            assert all(a["cleanup_confirmed"] for a in stopped["activities"]),stopped
            profile=await core.invoke(COGNITION_KEY,"inspect","猫",source_kind="observed",after=0,limit=1,timeout=5)
            assert profile["documents"]==1,profile
            print({"activities":[(a["template_id"],a["state"]) for a in stopped["activities"]],"learned_documents":profile["documents"]})
        finally:await runtime.stop()
        assert all(group.process(name).cleanup_confirmed for name in group.modules)
        print("PASS: Agency chooses learning, executes, pauses for rest, resumes the same activity, and stops cooperatively")


if __name__=="__main__":
    demo_path=str(Path(__file__).resolve().parent)
    sys.path.insert(0,demo_path)
    # The example worker is outside the installed library. Production workers
    # are installed into the common environment used by Core-owned children.
    os.environ["PYTHONPATH"]=demo_path
    asyncio.run(main())
