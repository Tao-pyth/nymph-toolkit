"""Small, explicit composition shared by v1.4 executable examples."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta

from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, Placement, Usage
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.contracts.text_interaction import TEXT_INTERACTION_CONTRACT
from nymph_toolkit.contracts.web import WEB_CONTRACT
from nymph_toolkit.core import FileStore, HybridGroup


class Requester:
    def __init__(self, context): self.context = context
    async def start(self): await self.context.core.publish_usage(Usage(OperatingState.RUNNING, True, 0, 1))
    async def run(self): await asyncio.Event().wait()
    async def stop(self): pass


def requester_factory(context, config):
    return Requester(context)


def group_at(root, *, inputs=Placement.LOCAL, storage=Placement.PROCESS, allowed_origins=None):
    store = FileStore(root/"core", root/"archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4), store)
    definitions = [
        ("memory", ModuleKind.SUBSYSTEM, (), (MEMORY_CONTRACT,), "subsystems.memory", {"path":str(root/"memory.db")}, storage),
        ("cognition", ModuleKind.SUBSYSTEM, ("memory",), (COGNITION_CONTRACT,COGNITION_REVISION_CONTRACT), "subsystems.cognition",
         {"path":str(root/"cognition.db"),"memory_module_id":"memory","enable_revision":True}, storage),
        ("text", ModuleKind.ADAPTER, ("memory","cognition"), (TEXT_INTERACTION_CONTRACT,), "adapters.text_interaction",
         {"memory_module_id":"memory","cognition_module_id":"cognition"}, inputs),
    ]
    if allowed_origins is not None:
        definitions.append(("web",ModuleKind.ADAPTER,("memory",),(WEB_CONTRACT,),"adapters.web",
                            {"memory_module_id":"memory","allowed_origins":allowed_origins},inputs))
    for name, kind, depends, contracts, module, config, placement in definitions:
        group.register_module(ModuleSpec(name,kind,depends),ModuleAdvertisement(name,"1.4.0",contracts),
                              "nymph_toolkit."+module+":factory",config,placement)
    dependencies = ("text",) if allowed_origins is None else ("text","web")
    group.register_module(ModuleSpec("requester",ModuleKind.SUBSYSTEM,dependencies),ModuleAdvertisement("requester","example-1",()),
                          __name__+":requester_factory",{},Placement.LOCAL)
    return group
