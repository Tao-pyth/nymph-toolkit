"""Shared acceptance setup; each run owns its directory, processes and connections."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta

from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from tests.doubles.integration import CONTRACT, KEY


def make_group(root, requester=Placement.LOCAL, provider=Placement.PROCESS, *, measure=False, trace=None,
               requester_config=None, provider_config=None, settings=None):
    store = FileStore(root / "primary", root / "archive", retention=timedelta(days=2),
                      batch_size=128, flush_interval=.05)
    group = HybridGroup(settings or HybridSettings(5, 2, 5, 65536, 32, 8), store)
    for identity, placement, kind, dependencies, extra in (
        ("requester", requester, ModuleKind.ADAPTER, frozenset({"provider"}), requester_config),
        ("provider", provider, ModuleKind.SUBSYSTEM, frozenset(), provider_config),
    ):
        config = {"measure": measure, **(extra or {})}
        if trace is not None:
            config["trace"] = str(trace)
        group.register_module(ModuleSpec(identity, kind, dependencies),
                              ModuleAdvertisement(identity, "probe-v1", (CONTRACT,)),
                              "tests.doubles.integration:factory", config, placement)
    group.enable_activities(clock_check_interval=.02, max_running=2)
    return group, Runtime(group)


async def invoke(group, module, operation, *args, timeout=10, **kwargs):
    async with asyncio.timeout(timeout):
        return await group.modules[module].invoke("invoke", {
            "contract": KEY, "operation": operation, "args": args, "kwargs": kwargs}, timeout=timeout)


async def until(predicate, timeout=5):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.005)


def owned_state(group):
    """Internal observations are test evidence, not new public API promises."""
    tasks = set(group._tasks.values()) | set(group._control_tasks)
    for task in (group._route_task, group._connections_task, group._activities_task):
        if task is not None:
            tasks.add(task)
    for service in group.modules.values():
        for task in (service.monitor,):
            if task is not None:
                tasks.add(task)
        if service.node is not None:
            tasks |= service.node.tasks | service.node.context.owned
            for peer in service.node.context.peers:
                tasks.add(peer._reader)
            for stream in service.node.context.streams:
                tasks.update(stream._tasks)
    store = group.connections.store
    tasks |= store._operations
    for task in (store._writer, store._stop_task):
        if task is not None:
            tasks.add(task)
    return {"live_tasks": sum(not t.done() for t in tasks),
            "live_children": sum(s.process is not None and s.process.returncode is None for s in group.modules.values()),
            "running_slots": group.activities._running_slots,
            "unsaved_events": store.unsaved_events}
