"""Nymph changes plans and explicitly pauses/resumes one retained continuation."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from nymph_toolkit.contracts import (
    ActivityChange, ActivityCommandStatus, ActivityKey, ActivityRequest, ActivityState,
    ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, Usage,
)
from nymph_toolkit.core import Connections, FileStore, ModuleGroup, Runtime, TaskManager


class DummyNymph:
    def __init__(self, links, manager, run_number):
        self.links, self.manager, self.run_number = links, manager, run_number

    async def start(self):
        self.links.publish_usage("nymph", Usage(OperatingState.RUNNING, True, 0, 1))

    def control(self, key, action, command_id):
        return getattr(self.manager, "request_" + action)(key, command_id=command_id,
                    expected_revision=self.manager.snapshot(key).revision)

    def change(self, key, command_id, **values):
        return self.manager.change(key, ActivityChange(**values), command_id=command_id,
                                   expected_revision=self.manager.snapshot(key).revision)

    async def run(self):
        history = await self.manager.history("nymph")
        assert not history.issues and not self.manager.activities()
        assert bool(history.records) == (self.run_number > 1)
        print(f"run {self.run_number}: previous evidence={len(history.records)}, restored activities=0")
        entered, continued = asyncio.Event(), asyncio.Event()
        invocations = 0

        async def research(context):
            nonlocal invocations
            invocations += 1
            position = 0
            entered.set()
            while True:
                await context.wait_for_control()
                # A real executor releases shared resources before this checkpoint.
                if await context.checkpoint() is not None:
                    break
                position += 1
                continued.set()
            await asyncio.sleep(0)  # executor-owned cleanup
            return {"position": position}

        key = ActivityKey("nymph", "research")
        original = ActivityRequest(key, "調査", datetime.now(timezone.utc) + timedelta(hours=1),
                                   timedelta(hours=1), priority=0)
        self.manager.submit(original, research, supports_pause=True)
        changed = self.change(key, "begin-now", start_at=None, priority=2)
        assert changed.status == ActivityCommandStatus.APPLIED
        await entered.wait()
        self.control(key, "pause", "pause")
        await self.manager.wait_command(key, "pause")
        # Older Windows clocks can return the same timestamp across these operations.
        # Establish that the new end is past, instead of assuming microsecond resolution.
        short_end = self.manager.snapshot(key).planned_start_at + timedelta(microseconds=1)
        while datetime.now(timezone.utc) <= short_end:
            await asyncio.sleep(0.01)
        reached = self.change(key, "shorten", duration=timedelta(microseconds=1))
        assert reached.snapshot.planned_end_notified and reached.snapshot.state == ActivityState.PAUSED
        self.change(key, "extend", duration=timedelta(hours=2))
        print(f"run {self.run_number}: shortened deadline notified while paused; Nymph extended the plan")

        other_entered = asyncio.Event()
        async def other(context):
            other_entered.set()
            await context.wait_for_finish()
        other_key = ActivityKey("nymph", "other")
        self.manager.submit(ActivityRequest(other_key, "別の活動", None, timedelta(hours=1)), other)
        await other_entered.wait()
        self.control(key, "resume", "resume")
        assert self.manager.snapshot(key).state == ActivityState.RESUME_PENDING
        self.manager.request_finish(other_key)
        await self.manager.wait(other_key)
        await self.manager.wait_command(key, "resume")
        await continued.wait()
        self.manager.request_finish(key)
        result = await self.manager.wait(key)
        assert result.state == ActivityState.STOPPED and result.result["position"] == 1
        assert invocations == 1 and result.request == original
        assert result.current_request.priority == 2
        assert 0 <= result.execution_seconds <= result.elapsed_seconds
        print(f"run {self.run_number}: resumed once from retained position, cleanup complete")

    async def stop(self):
        self.links.publish_usage("nymph", Usage(OperatingState.STOPPED, False, 0, 1))


async def run_once(base, run_number):
    group = ModuleGroup()
    store = FileStore(base / "primary", base / "archive", retention=timedelta(days=7), batch_size=32, flush_interval=0.05)
    links = Connections(group, store)
    manager = TaskManager(links, clock_check_interval=0.01, max_running=1)
    group.register(ModuleSpec("nymph", ModuleKind.SUBSYSTEM), DummyNymph(links, manager, run_number))
    links.declare(ModuleAdvertisement("nymph", "1", ()))
    group.attach_connections(links)
    group.attach_task_manager(manager)
    runtime = Runtime(group)
    try:
        await runtime.start()
        await asyncio.wait_for(runtime.wait(), 10)
    finally:
        await runtime.stop()
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    assert store.unsaved_events == 0
    print(f"run {run_number}: remaining tasks=0, unsaved history=0")


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-changes-demo-") as directory:
        for run_number in (1, 2):
            await run_once(Path(directory), run_number)


if __name__ == "__main__":
    asyncio.run(main())
