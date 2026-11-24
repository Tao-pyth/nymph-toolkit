"""Consolidate actual evidence, expire dreams and explicitly apply a Persona proposal."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, Placement, Usage
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT, COGNITION_KEY
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT, PERSONA_KEY
from nymph_toolkit.contracts.sleep import SLEEP_CONTRACT, SLEEP_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


class Requester:
    def __init__(self, context): self.context = context
    async def start(self): await self.context.core.publish_usage(Usage(OperatingState.RUNNING, True, 0, 8))
    async def run(self): await asyncio.Event().wait()
    async def stop(self): pass


def requester_factory(context, config): return Requester(context)


def group_at(root, *, sleep=Placement.LOCAL, providers=Placement.PROCESS):
    group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4),
                        FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05))
    own = "sleep_demo" if __name__ == "__main__" else __name__
    for name, depends, contracts, factory, config, placement in (
        ("memory", (), (MEMORY_CONTRACT,), "nymph_toolkit.subsystems.memory:factory", dict(path=str(root / "memory.db")), providers),
        ("cognition", ("memory",), (COGNITION_CONTRACT, COGNITION_REVISION_CONTRACT), "nymph_toolkit.subsystems.cognition:factory",
         dict(path=str(root / "cognition.db"), memory_module_id="memory", enable_revision=True), providers),
        ("persona", (), (PERSONA_CONTRACT,), "nymph_toolkit.subsystems.persona:factory",
         dict(path=str(root / "persona.db"), initial_traits=dict(curiosity=500)), providers),
        ("sleep", ("memory", "cognition", "persona"), (SLEEP_CONTRACT,), "nymph_toolkit.subsystems.sleep:factory",
         dict(path=str(root / "sleep.db"), memory_module_id="memory", cognition_module_id="cognition", persona_module_id="persona",
              trait_rules=[dict(concept="explore", trait="curiosity", delta=3)]), sleep),
        ("requester", ("sleep",), (), own + ":requester_factory", {}, Placement.LOCAL),
    ):
        group.register_module(ModuleSpec(name, ModuleKind.SUBSYSTEM, depends), ModuleAdvertisement(name, "example-1", contracts),
                              factory, config, placement)
    return group


class Calls:
    def __init__(self, group, *, direct=False):
        self.group, self.core, self.direct, self.links = group, None, direct, {}

    async def start(self):
        self.core = self.group.client("requester")
        for key, target in ((MEMORY_KEY, "memory"), (COGNITION_KEY, "cognition"), (PERSONA_KEY, "persona"), (SLEEP_KEY, "sleep")):
            await self.core.bind(key, target, timeout=5)
            if self.direct: self.links[key] = await self.core.prepare(key, timeout=5)

    async def __call__(self, key, operation, *args, **kwargs):
        if self.direct: return await self.links[key].acall(operation, *args, timeout=30, **kwargs)
        return await self.core.invoke(key, operation, *args, timeout=30, **kwargs)

    async def close(self):
        for link in self.links.values(): await link.close()


async def exercise(call):
    originals = {}
    for key, source, tokens in (("a", "observed", ["猫", "は", "眠る"]), ("b", "observed", ["犬", "は", "走る"]),
                                ("c", "reported", ["鳥", "は", "飛ぶ"]), ("d", "dream", ["猫", "は", "飛ぶ"])):
        originals[key] = await call(MEMORY_KEY, "put", dict(record_id=key, kind="experience", content=" ".join(tokens),
            source_kind=source, source="example:sleep", occurred_at="2026-11-24T00:00:00Z"))
        assert isinstance(await call(COGNITION_KEY, "learn", key, tokens=tokens, concepts=["explore"]), dict)
    first_input = dict(cycle_id="one", expected_revision=0, record_ids=["a", "b", "c", "d"])
    first = await call(SLEEP_KEY, "cycle", first_input)
    assert first["persona_proposal"]["deltas"] == {"curiosity": 5}, first
    assert first["evaluated_ids"] == ["a", "b"]
    assert (await call(PERSONA_KEY, "get"))["traits"] == {"curiosity": 500}
    assert (await call(PERSONA_KEY, "history"))["updates"] == []
    assert (await call(SLEEP_KEY, "state"))["dreams"][0]["tokens"] == ["猫", "は", "は", "走る"]
    applied = await call(PERSONA_KEY, "apply", first["persona_proposal"])
    assert applied["after"] == {"curiosity": 505} and applied["revision"] == 1, applied
    assert await call(SLEEP_KEY, "cycle", first_input) == first
    assert await call(PERSONA_KEY, "apply", first["persona_proposal"]) == applied
    second = await call(SLEEP_KEY, "cycle", dict(first_input, cycle_id="two", expected_revision=1))
    assert second["persona_proposal"] is None
    assert second["expired_dream_ids"] == [first["dreams"][0]["dream_id"]]
    for revision, strength in ((2, 3000), (3, 2000), (4, 1000), (5, 0)):
        result = await call(SLEEP_KEY, "cycle", dict(cycle_id=f"empty-{revision}", expected_revision=revision, record_ids=[]))
        assert (await call(SLEEP_KEY, "inspect", "explore"))["strength"] == strength
    assert result["forgotten_ids"] == ["a", "b", "c", "d"]
    assert (await call(SLEEP_KEY, "state"))["dreams"] == []
    assert await call(SLEEP_KEY, "get", "one") == first
    restored = await call(SLEEP_KEY, "cycle", dict(cycle_id="again", expected_revision=6, record_ids=["a", "b"]))
    assert restored["persona_proposal"] is None
    for key, original in originals.items(): assert await call(MEMORY_KEY, "get", key) == original
    assert (await call(COGNITION_KEY, "inspect", "は"))["documents"] == 4
    assert len((await call(PERSONA_KEY, "history"))["updates"]) == 1
    return dict(first=first, final=await call(SLEEP_KEY, "state"), applied=applied)


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-sleep-") as directory:
        root, result = Path(directory).resolve(), None
        for restored in (False, True):
            group = group_at(root); runtime = Runtime(group); call = Calls(group, direct=True)
            await runtime.start()
            try:
                await call.start()
                if not restored:
                    result = await exercise(call)
                else:
                    assert await call(SLEEP_KEY, "state") == result["final"]
                    assert await call(SLEEP_KEY, "get", "one") == result["first"]
                    assert (await call(PERSONA_KEY, "get"))["traits"] == {"curiosity": 505}
            finally:
                await call.close(); await runtime.stop()
            assert all(group.process(name).cleanup_confirmed for name in group.modules)
        print("PASS: Sleep integration, source-separated forgetting, dream expiry, explicit Persona proposal, restart and cleanup")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parent)
    asyncio.run(main())
