"""Nymph receives a time notice, requests a safe finish, then reads history after restart."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
from pathlib import Path
import tempfile

from nymph_toolkit.contracts import (
    ActivityKey, ActivityNoticeKind, ActivityRequest, ActivityState, ContractKey, ContractSpec,
    ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, OperationMode, OperationSpec, Usage,
)
from nymph_toolkit.core import Connections, FileStore, ModuleGroup, Runtime, TaskManager


CONTRACT = ContractKey("demo.observation", "1")
SPEC = ContractSpec(CONTRACT, (OperationSpec("observe", OperationMode.ASYNC),))
READY = Usage(OperatingState.RUNNING, True, 0, 1)
STOPPED = Usage(OperatingState.STOPPED, False, 0, 1)


class Provider:
    def __init__(self, connections):
        self.connections = connections

    async def start(self):
        self.connections.publish_usage("provider", READY, contracts={CONTRACT: READY})

    async def run(self):
        # Resources remain available until ModuleGroup calls stop.
        return None

    async def observe(self, topic):
        await asyncio.sleep(0)
        return {"observed_topic": topic}

    async def stop(self):
        self.connections.publish_usage("provider", STOPPED, contracts={CONTRACT: STOPPED})


class Nymph:
    def __init__(self, connections, manager, run_number):
        self.connections = connections
        self.manager = manager
        self.run_number = run_number

    async def start(self):
        self.connections.publish_usage("nymph", READY)

    async def run(self):
        history = await self.manager.history("nymph")
        assert not history.issues
        assert not self.manager.activities(), "Old activities must not be restored automatically"
        assert bool(history.records) == (self.run_number > 1)
        print(f"run {self.run_number}: previous activity records={len(history.records)}, active activities=0")
        candidates = self.connections.candidates(CONTRACT)
        selected = next(candidate for candidate in candidates if candidate.advertisement.module_id == "provider")
        binding = await self.connections.bind("nymph", CONTRACT, selected.advertisement.module_id, wait_timeout=5)
        entered = asyncio.Event()

        async def execute(context):
            entered.set()
            prepared = await self.connections.prepare(binding.key, wait_timeout=5)
            observation = await prepared.acall("observe", context.request.parameters["topic"])
            await context.wait_for_finish()
            # A real executor releases its own activity resources at this safe point.
            await asyncio.sleep(0)
            return observation

        # These short timings are demonstration settings, not product defaults.
        request = ActivityRequest(ActivityKey("nymph", "research"), "調査", None,
                                  timedelta(milliseconds=50), {"topic": "dummy document"})
        self.manager.submit(request, execute)
        await entered.wait()
        while True:
            notice = await self.manager.next_notice("nymph")
            if notice.kind == ActivityNoticeKind.PLANNED_END:
                break
        current = self.manager.snapshot(request.key)
        assert not current.state.terminal and current.finish_reason is None
        print(f"run {self.run_number}: planned time reached; activity continues ({current.state})")
        # The dummy Nymph makes this decision. The time notification did not stop it.
        self.manager.request_finish(request.key)
        result = await self.manager.wait(request.key)
        assert result.state == ActivityState.STOPPED
        assert result.result["observed_topic"] == "dummy document"
        print(f"run {self.run_number}: Nymph requested finish; cleanup completed ({result.state})")

    async def stop(self):
        self.connections.publish_usage("nymph", STOPPED)


async def run_once(base, run_number):
    group = ModuleGroup()
    store = FileStore(base / "primary", base / "archive", retention=timedelta(days=7),
                      batch_size=32, flush_interval=0.05)
    connections = Connections(group, store)
    manager = TaskManager(connections, clock_check_interval=0.005)
    provider = Provider(connections)
    nymph = Nymph(connections, manager, run_number)
    group.register(ModuleSpec("provider", ModuleKind.SUBSYSTEM), provider)
    group.register(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, frozenset({"provider"})), nymph)
    connections.declare(ModuleAdvertisement("provider", "1", (SPEC,)), {CONTRACT: {"observe": provider.observe}})
    connections.declare(ModuleAdvertisement("nymph", "1", ()))
    group.attach_connections(connections)
    group.attach_task_manager(manager)
    runtime = Runtime(group)
    try:
        await runtime.start()
        await asyncio.wait_for(runtime.wait(), 10)
    finally:
        await runtime.stop()
    remaining = [task for task in asyncio.all_tasks() if task is not asyncio.current_task() and not task.done()]
    assert not remaining, remaining
    print(f"run {run_number}: remaining tasks=0, unsaved history={store.unsaved_events}")
    assert store.unsaved_events == 0


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-activities-demo-") as directory:
        for run_number in (1, 2):
            await run_once(Path(directory), run_number)


if __name__ == "__main__":
    asyncio.run(main())
