"""Observe how learning and internal state change Agency decisions, then restart."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, Placement, Usage
from nymph_toolkit.contracts.agency import AGENCY_CONTRACT, AGENCY_KEY
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT, COGNITION_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


def activity_catalog():
    return [dict(template_id=name,motive=motive,content=content,executor_module_id="worker",executor_id=name,
                 parameters={},min_seconds=60,max_seconds=300,delay_seconds=0)
            for name,motive,content in (("study","explore","Investigate the learning goal"),
                                       ("apply","achieve","Apply learned knowledge"),
                                       ("sleep","rest","Rest"),("talk","social","Ask or exchange information"))]


def decision_input(decision_id, *, sleep_pressure=100):
    return dict(decision_id=decision_id,now="2026-11-24T12:00:00Z",
                state=dict(sleep_pressure=sleep_pressure,cognitive_load=100,social_need=50),
                goals=[dict(goal_id="understand-cat",record_id="lesson",token="猫",importance=800,target_documents=1)],
                available=[t["template_id"] for t in activity_catalog()],current=None)


class Requester:
    def __init__(self,context): self.context=context
    async def start(self): await self.context.core.publish_usage(Usage(OperatingState.RUNNING,True,0,1))
    async def run(self): await asyncio.Event().wait()
    async def stop(self): pass


def requester_factory(context,config):
    return Requester(context)


def group_at(root, *, agency=Placement.LOCAL, storage=Placement.PROCESS):
    store=FileStore(root/"core",root/"archive",retention=timedelta(days=1),batch_size=16,flush_interval=.05)
    group=HybridGroup(HybridSettings(10,3,30,65536,32,4),store)
    for name,depends,contract,module,config,placement in (
        ("memory",(),MEMORY_CONTRACT,"memory",dict(path=str(root/"memory.db")),storage),
        ("cognition",("memory",),COGNITION_CONTRACT,"cognition",dict(path=str(root/"cognition.db"),memory_module_id="memory"),storage),
        ("agency",("memory","cognition"),AGENCY_CONTRACT,"agency",dict(path=str(root/"agency.db"),memory_module_id="memory",cognition_module_id="cognition",catalog=activity_catalog()),agency),
    ):
        group.register_module(ModuleSpec(name,ModuleKind.SUBSYSTEM,depends),ModuleAdvertisement(name,"1.5.0",(contract,)),
                              "nymph_toolkit.subsystems."+module+":factory",config,placement)
    group.register_module(ModuleSpec("requester",ModuleKind.SUBSYSTEM,("agency",)),ModuleAdvertisement("requester","example-1",()),
                          ("agency_demo" if __name__=="__main__" else __name__)+":requester_factory",{},Placement.LOCAL)
    return group


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-agency-") as directory:
        root=Path(directory).resolve()
        first=None
        for restored in (False,True):
            group=group_at(root); runtime=Runtime(group); await runtime.start()
            try:
                core=group.client("requester")
                for key,provider in ((MEMORY_KEY,"memory"),(COGNITION_KEY,"cognition"),(AGENCY_KEY,"agency")):
                    await core.bind(key,provider,timeout=5)
                if not restored:
                    record=dict(record_id="lesson",kind="experience",content="猫 は 眠る",source_kind="observed",source="example:agency",occurred_at="2026-11-24T00:00:00Z")
                    assert isinstance(await core.invoke(MEMORY_KEY,"put",record,timeout=5),dict)
                    first=await core.invoke(AGENCY_KEY,"decide",decision_input("unknown"),timeout=10)
                    assert first["selected"]["template_id"]=="study",first
                    assert isinstance(await core.invoke(COGNITION_KEY,"learn","lesson",tokens=["猫","は","眠る"],concepts=["sleep"],timeout=10),dict)
                    learned=await core.invoke(AGENCY_KEY,"decide",decision_input("learned"),timeout=10)
                    tired=await core.invoke(AGENCY_KEY,"decide",decision_input("tired",sleep_pressure=950),timeout=10)
                    assert learned["selected"]["template_id"]=="apply",learned
                    assert tired["selected"]["template_id"]=="sleep",tired
                    print({"unknown":first["selected"],"learned":learned["selected"],"tired":tired["selected"]})
                link=await core.prepare(AGENCY_KEY,timeout=5)
                try:
                    assert await link.acall("decide",decision_input("unknown"),timeout=10)==first
                    assert await link.acall("get","unknown",timeout=5)==first
                finally: await link.close()
            finally: await runtime.stop()
            assert all(group.process(name).cleanup_confirmed for name in group.modules)
        print("PASS: Agency selects from evidence/state, durable decisions, restart, cleanup; execution follows in v1.6")


if __name__=="__main__":
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    asyncio.run(main())
