"""Run dummy Subsystem/Adapter registrations and inspect dependency changes."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import ModuleKind, ModuleSpec, RuntimeState
from nymph_toolkit.core import ModuleGroup, Runtime


class Dummy:
    def __init__(self, module_id, trace):
        self.module_id = module_id
        self.trace = trace

    async def start(self):
        self.trace.append((self.module_id, "start"))

    async def run(self):
        self.trace.append((self.module_id, "run"))
        await asyncio.sleep(0)
        return self.module_id + ":done"

    async def stop(self):
        self.trace.append((self.module_id, "stop"))


async def main():
    trace = []
    group = ModuleGroup()
    group.register(
        ModuleSpec("document", ModuleKind.ADAPTER, frozenset({"memory"})),
        Dummy("document", trace),
    )
    old = group.get("document")
    assert not old.available
    update = group.register(ModuleSpec("memory", ModuleKind.SUBSYSTEM), Dummy("memory", trace))
    assert [change.module_id for change in update.changes] == ["document", "memory"]
    assert group.get("document").available and not old.available
    runtime = Runtime(group)
    await runtime.start()
    result = await runtime.wait()
    assert result == {"document": "document:done", "memory": "memory:done"}
    assert runtime.state == RuntimeState.STOPPED
    assert [entry for entry in trace if entry[1] == "start"] == [("memory", "start"), ("document", "start")]
    assert [entry for entry in trace if entry[1] == "stop"] == [("document", "stop"), ("memory", "stop")]
    update = group.unregister("memory")
    assert [change.module_id for change in update.changes] == ["document", "memory"]
    assert group.get("document").missing_dependencies == frozenset({"memory"})
    group.unregister("document")
    assert group.entries() == ()
    remaining = asyncio.all_tasks() - {asyncio.current_task()}
    assert not remaining, remaining
    print("registry and dependency changes: PASS")
    print("module lifecycle:", trace)
    print("results:", result)
    print("state:", runtime.state.value, "remaining tasks:", len(remaining))


if __name__ == "__main__":
    asyncio.run(main())
