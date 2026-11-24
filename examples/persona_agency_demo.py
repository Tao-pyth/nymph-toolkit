"""External trait updates change Agency choices and real Core-managed activities."""

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
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT, PERSONA_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


def persona_config():
    return dict(module_id="persona", motive_traits=dict(rest="rest_affinity", explore="curiosity", achieve="focus", social="sociability"))


def group_at(root, *, agency=Placement.LOCAL, persona=Placement.PROCESS):
    group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4),
                        FileStore(root/"core", root/"archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05))
    group.enable_activities(clock_check_interval=.02, max_running=1)
    for name, depends, contracts, factory, config, placement in (
        ("memory", (), (MEMORY_CONTRACT,), "nymph_toolkit.subsystems.memory:factory", dict(path=str(root/"memory.db")), Placement.LOCAL),
        ("cognition", ("memory",), (COGNITION_CONTRACT,), "nymph_toolkit.subsystems.cognition:factory",
         dict(path=str(root/"cognition.db"), memory_module_id="memory"), Placement.LOCAL),
        ("persona", (), (PERSONA_CONTRACT,), "nymph_toolkit.subsystems.persona:factory",
         dict(path=str(root/"persona.db"), initial_traits={name:500 for name in persona_config()["motive_traits"].values()}), persona),
        ("worker", ("cognition",), (), execution.__name__+":worker_factory", dict(supports_pause=True), Placement.PROCESS),
        ("agency", ("memory", "cognition", "persona", "worker"), (AGENCY_CONTRACT, AGENCY_ACTIVITIES_CONTRACT),
         "nymph_toolkit.subsystems.agency:execution_factory",
         dict(path=str(root/"agency-persona.db"), memory_module_id="memory", cognition_module_id="cognition", catalog=execution.catalog(),
              persona=persona_config(), execution=dict(poll_seconds=.02, max_activities=16,
                  pause_executors=[dict(module_id="worker", executor_id=k) for k in ("study", "apply", "rest")])), agency),
        ("requester", ("agency",), (), execution.__name__+":requester_factory", {}, Placement.LOCAL),
    ):
        group.register_module(ModuleSpec(name, ModuleKind.SUBSYSTEM, depends), ModuleAdvertisement(name, "example-1", contracts),
                              factory, config, placement)
    return group


class Calls:
    def __init__(self, group, *, direct=False):
        self.group, self.core = group, None
        self.direct, self.links = direct, {}

    async def start(self):
        self.core = self.group.client("requester")
        for key, target in ((MEMORY_KEY, "memory"), (COGNITION_KEY, "cognition"), (PERSONA_KEY, "persona"),
                            (AGENCY_KEY, "agency"), (CONTROL, "agency")):
            await self.core.bind(key, target, timeout=5)
            if self.direct: self.links[key] = await self.core.prepare(key, timeout=5)

    async def __call__(self, key, operation, *args, **kwargs):
        if self.direct: return await self.links[key].acall(operation, *args, timeout=5, **kwargs)
        return await self.core.invoke(key, operation, *args, timeout=5, **kwargs)

    async def close(self):
        for link in self.links.values(): await link.close()


async def until(call, predicate):
    async with asyncio.timeout(15):
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


def update(command_id, revision, delta):
    return dict(command_id=command_id, expected_revision=revision, deltas=dict(rest_affinity=delta),
                reason="Explicit demonstration of a changed preference", source=dict(actor_id="requester", reference="example:persona-agency"))


async def exercise(call):
    record = dict(record_id="lesson", kind="experience", content="猫 は 眠る", source_kind="observed",
                  source="example:persona-agency", occurred_at="2026-11-24T00:00:00Z")
    original = await call(MEMORY_KEY, "put", record)
    assert (await call(CONTROL, "status"))["state"] == "inactive"
    observation = execution.observation(600)
    await call(CONTROL, "activate", "persona-cycle", observation)
    active = await until(call, lambda s:any(a["template_id"] == "apply" and a["state"] == "running" for a in s["activities"]))
    first_activity = next(a for a in active["activities"] if a["template_id"] == "apply")
    first = await saved(call, first_activity["decision_id"])
    assert first["persona"]["revision"] == 0 and first["plan"]["priority"] == 800, first

    changed = await call(PERSONA_KEY, "apply", update("prefer-rest", 0, 500))
    assert changed["revision"] == 1, changed
    await call(CONTROL, "observe", "persona-cycle", active["observation_revision"], observation)
    resting = await until(call, lambda s:any(a["template_id"] == "rest" and a["state"] == "running" for a in s["activities"]))
    assert any(a["activity_id"] == first_activity["activity_id"] and a["state"] == "paused" for a in resting["activities"]), resting
    rest = next(a for a in resting["activities"] if a["template_id"] == "rest")
    altered = await saved(call, rest["decision_id"])
    assert altered["persona"]["revision"] == 1 and rest["priority"] == 900, altered
    assert altered["selected"]["base_score"] == 600, altered

    returned = await call(PERSONA_KEY, "apply", update("neutral-rest", 1, -500))
    assert returned["revision"] == 2, returned
    await call(CONTROL, "observe", "persona-cycle", resting["observation_revision"], observation)
    resumed = await until(call, lambda s:
        any(a["activity_id"] == first_activity["activity_id"] and a["state"] == "running" for a in s["activities"])
        and any(e["operation"] == "resume" and e["status"] == "applied" for e in s["recent_operations"]))
    assert resumed["total_activities"] == 3, resumed
    assert any(e["operation"] == "resume" and e["status"] == "applied" for e in resumed["recent_operations"]), resumed
    await call(CONTROL, "halt", "persona-cycle")
    ended = await until(call, lambda s:s["state"] == "stopped")
    assert all(a["cleanup_confirmed"] for a in ended["activities"]), ended
    assert await saved(call, first["decision_id"]) == first
    assert await call(MEMORY_KEY, "get", "lesson") == original
    assert (await call(COGNITION_KEY, "inspect", "猫", source_kind="observed", after=0, limit=1))["documents"] == 1
    history = await call(PERSONA_KEY, "history")
    assert len(history["updates"]) == 2, history
    return dict(first=first, altered=altered, activities=ended["total_activities"])


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-persona-agency-") as directory:
        root = Path(directory).resolve()
        result = None
        for restored in (False, True):
            group = group_at(root); runtime = Runtime(group); call = Calls(group)
            await runtime.start()
            try:
                await call.start()
                if not restored:
                    result = await exercise(call)
                else:
                    assert (await call(CONTROL, "status"))["state"] == "inactive"
                    assert (await call(CONTROL, "status"))["total_activities"] == 0
                    assert await saved(call, result["altered"]["decision_id"]) == result["altered"]
                    assert (await call(PERSONA_KEY, "get"))["revision"] == 2
            finally:
                await call.close(); await runtime.stop()
            assert all(group.process(name).cleanup_confirmed for name in group.modules)
        print({"activities": result["activities"], "before": result["first"]["selected"], "after": result["altered"]["selected"]})
        print("PASS: trait update changes Agency choice, real activity pauses/resumes, history survives restart without automatic execution")


if __name__ == "__main__":
    os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parent)
    asyncio.run(main())
