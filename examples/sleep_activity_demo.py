"""Agency chooses sleep; its real result changes the next activity decision."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import agency_execution_demo as execution
else:
    from . import agency_execution_demo as execution
from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement, TemporaryUnavailable
from nymph_toolkit.contracts.agency import AGENCY_CONTRACT, AGENCY_KEY, AGENCY_ACTIVITIES_CONTRACT, AGENCY_ACTIVITIES_KEY as CONTROL
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT, COGNITION_KEY
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT, PERSONA_KEY
from nymph_toolkit.contracts.sleep import SLEEP_CONTRACT, SLEEP_KEY
from nymph_toolkit.contracts.sleep_activity import SLEEP_ACTIVITY_CONTRACT, SLEEP_ACTIVITY_KEY as EXECUTION
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


def group_at(root, *, actor=Placement.LOCAL, providers=Placement.PROCESS):
    group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4),
                        FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05))
    group.enable_activities(clock_check_interval=.02, max_running=1)
    catalog = [
        dict(template_id="rest", motive="rest", content="Consolidate observed experience", executor_module_id="sleep-worker", executor_id="sleep",
             parameters=dict(request_id="night-one", expected_revision=0, record_ids=["a", "b"], apply_persona=True), min_seconds=60, max_seconds=60, delay_seconds=0),
        dict(template_id="apply", motive="achieve", content="Consult learned evidence", executor_module_id="worker", executor_id="apply",
             parameters={}, min_seconds=60, max_seconds=60, delay_seconds=0),
    ]
    for name, depends, contracts, factory, config, placement in (
        ("memory", (), (MEMORY_CONTRACT,), "nymph_toolkit.subsystems.memory:factory", dict(path=str(root / "memory.db")), providers),
        ("cognition", ("memory",), (COGNITION_CONTRACT, COGNITION_REVISION_CONTRACT), "nymph_toolkit.subsystems.cognition:factory",
         dict(path=str(root / "cognition.db"), memory_module_id="memory", enable_revision=True), providers),
        ("persona", (), (PERSONA_CONTRACT,), "nymph_toolkit.subsystems.persona:factory",
         dict(path=str(root / "persona.db"), initial_traits=dict(rest_affinity=500, curiosity=500, focus=500, sociability=500)), providers),
        ("sleep", ("memory", "cognition", "persona"), (SLEEP_CONTRACT,), "nymph_toolkit.subsystems.sleep:factory",
         dict(path=str(root / "sleep.db"), memory_module_id="memory", cognition_module_id="cognition", persona_module_id="persona",
              trait_rules=[dict(concept="sleep", trait="rest_affinity", delta=-3)]), providers),
        ("sleep-worker", ("sleep", "persona"), (SLEEP_ACTIVITY_CONTRACT,), "nymph_toolkit.subsystems.sleep_activity:factory",
         dict(path=str(root / "sleep-activity.db"), sleep_module_id="sleep", persona_module_id="persona"), actor),
        ("worker", ("cognition",), (), execution.__name__ + ":worker_factory", {}, actor),
        ("agency", ("sleep-worker", "worker", "memory", "cognition", "persona"), (AGENCY_CONTRACT, AGENCY_ACTIVITIES_CONTRACT),
         "nymph_toolkit.subsystems.agency:execution_factory",
         dict(path=str(root / "agency.db"), memory_module_id="memory", cognition_module_id="cognition", catalog=catalog,
              persona=dict(module_id="persona", motive_traits=dict(rest="rest_affinity", explore="curiosity", achieve="focus", social="sociability")),
              execution=dict(poll_seconds=.02, max_activities=8, pause_executors=[dict(module_id="sleep-worker", executor_id="sleep"),
                                                                              dict(module_id="worker", executor_id="apply")])), actor),
        ("requester", ("agency",), (), execution.__name__ + ":requester_factory", {}, Placement.LOCAL),
    ):
        group.register_module(ModuleSpec(name, ModuleKind.SUBSYSTEM, depends), ModuleAdvertisement(name, "example-1", contracts), factory, config, placement)
    return group


class Calls:
    def __init__(self, group, *, direct=False): self.group, self.direct, self.links = group, direct, {}
    async def start(self):
        self.core = self.group.client("requester")
        for key, target in ((MEMORY_KEY, "memory"), (COGNITION_KEY, "cognition"), (PERSONA_KEY, "persona"),
                            (SLEEP_KEY, "sleep"), (EXECUTION, "sleep-worker"), (AGENCY_KEY, "agency"), (CONTROL, "agency")):
            await self.core.bind(key, target, timeout=5)
            if self.direct: self.links[key] = await self.core.prepare(key, timeout=5)
    async def __call__(self, key, operation, *args, **kwargs):
        if self.direct: return await self.links[key].acall(operation, *args, timeout=10, **kwargs)
        return await self.core.invoke(key, operation, *args, timeout=10, **kwargs)
    async def close(self):
        for link in self.links.values(): await link.close()


async def until(call, predicate):
    async with asyncio.timeout(20):
        while True:
            state = await call(CONTROL, "status")
            if isinstance(state, dict) and predicate(state): return state
            if isinstance(state, dict) and state["state"] == "failed": raise AssertionError(state)
            await asyncio.sleep(.02)


async def saved(call, decision_id):
    async with asyncio.timeout(10):
        while True:
            value = await call(AGENCY_KEY, "get", decision_id)
            if not isinstance(value, TemporaryUnavailable): return value
            await asyncio.sleep(.02)


async def exercise(call):
    originals = {}
    for record_id, tokens in (("a", ["猫", "は", "眠る"]), ("b", ["犬", "も", "眠る"])):
        originals[record_id] = await call(MEMORY_KEY, "put", dict(record_id=record_id, kind="experience", content=" ".join(tokens),
            source_kind="observed", source="example:sleep-activity", occurred_at="2026-11-24T00:00:00Z"))
        assert isinstance(await call(COGNITION_KEY, "learn", record_id, tokens=tokens, concepts=["sleep"]), dict)
    observation = dict(state=dict(sleep_pressure=800, cognitive_load=100, social_need=0),
                       goals=[dict(goal_id="cat", record_id="a", token="猫", importance=799, target_documents=1)], available=["rest", "apply"])
    await call(CONTROL, "activate", "sleep-cycle", observation)
    active = await until(call, lambda s:any(a["template_id"] == "apply" and a["state"] == "running" for a in s["activities"]))
    assert active["total_activities"] == 2, active
    rest = next(a for a in active["activities"] if a["template_id"] == "rest")
    assert rest["state"] == "completed" and rest["cleanup_confirmed"], rest
    first = await saved(call, rest["decision_id"])
    after = await saved(call, next(a["decision_id"] for a in active["activities"] if a["template_id"] == "apply"))
    assert first["persona"]["revision"] == 0 and first["selected"]["score"] == 800, first
    assert after["persona"]["revision"] == 1 and after["persona"]["traits"]["rest_affinity"] == 495, after
    assert after["selected"]["template_id"] == "apply" and after["selected"]["score"] == 799, after
    receipt = await call(EXECUTION, "get", "night-one")
    assert receipt["phase"] == "completed" and receipt["persona"]["after"]["rest_affinity"] == 495, receipt
    assert await call(SLEEP_KEY, "get", receipt["cycle_id"]) == receipt["cycle"]
    assert (await call(PERSONA_KEY, "history"))["updates"] == [receipt["persona"]]
    assert (await call(SLEEP_KEY, "state"))["dreams"][0]["source_kind"] == "dream"
    await call(CONTROL, "halt", "sleep-cycle")
    ended = await until(call, lambda s:s["state"] == "stopped")
    assert all(a["cleanup_confirmed"] for a in ended["activities"])
    for key, original in originals.items(): assert await call(MEMORY_KEY, "get", key) == original
    return dict(receipt=receipt, first=first, after=after)


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-sleep-activity-") as directory:
        root, result = Path(directory).resolve(), None
        for restored in (False, True):
            group = group_at(root); runtime = Runtime(group); call = Calls(group, direct=True)
            await runtime.start()
            try:
                await call.start()
                if not restored: result = await exercise(call)
                else:
                    assert (await call(CONTROL, "status"))["state"] == "inactive"
                    assert (await call(CONTROL, "status"))["total_activities"] == 0
                    assert await call(EXECUTION, "get", "night-one") == result["receipt"]
                    assert (await call(PERSONA_KEY, "history"))["updates"] == [result["receipt"]["persona"]]
            finally:
                await call.close(); await runtime.stop()
            assert all(group.process(name).cleanup_confirmed for name in group.modules)
        print("PASS: Agency sleep choice, actual consolidation and Persona application, next decision, restart and cleanup")


if __name__ == "__main__":
    os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parent)
    asyncio.run(main())
