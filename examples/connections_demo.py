"""Select a dummy provider, call it, persist the binding, and reuse it after restart."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import tempfile

from nymph_toolkit.contracts import (
    BindingKey, ContractKey, ContractSpec, ModuleAdvertisement, ModuleKind, ModuleSpec,
    OperatingState, OperationMode, OperationSpec, UnknownConnectionError, Usage,
)
from nymph_toolkit.core import Connections, FileStore, ModuleGroup, Runtime


CONTRACT = ContractKey("demo.echo", "1")
SPEC = ContractSpec(CONTRACT, (OperationSpec("echo", OperationMode.SYNC),
                               OperationSpec("echo_async", OperationMode.ASYNC)))
READY = Usage(OperatingState.RUNNING, True, 0, 1)
STOPPED = Usage(OperatingState.STOPPED, False, 0, 1)


class DummyProvider:
    def __init__(self, connections):
        self.connections = connections

    def echo(self, value):
        return "echo:" + value

    async def echo_async(self, value):
        await asyncio.sleep(0)
        return "async:" + value

    async def start(self):
        self.connections.publish_usage("provider", READY, contracts={CONTRACT: READY})

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        self.connections.publish_usage("provider", STOPPED, contracts={CONTRACT: STOPPED})


class DummyRequester:
    def __init__(self, connections):
        self.connections = connections
        self.done = asyncio.Event()
        self.reused = False

    async def start(self):
        self.connections.publish_usage("requester", READY)

    async def run(self):
        key = BindingKey("requester", CONTRACT)
        try:
            self.connections.connection(key)
            self.reused = True
        except UnknownConnectionError:
            # Selection belongs to the requester; the Core does not execute this filter.
            candidates = self.connections.candidates(CONTRACT)
            selected = next(c for c in candidates if c.advertisement.attributes["language"] == "ja"
                            and c.module_usage.state == OperatingState.RUNNING
                            and c.contract_usage.accepting and c.contract_usage.free > 0)
            await self.connections.bind("requester", CONTRACT, selected.advertisement.module_id, wait_timeout=5)
        handle = await self.connections.prepare(key, wait_timeout=5)
        assert handle.call("echo", "direct") == "echo:direct"
        assert await handle.acall("echo_async", "async") == "async:async"
        assert await self.connections.invoke(key, "echo", wait_timeout=5, args=("mediated",)) == "echo:mediated"
        self.done.set()
        await asyncio.Event().wait()

    async def stop(self):
        self.connections.publish_usage("requester", STOPPED)


async def run_once(primary, archive):
    group = ModuleGroup()
    # These are demonstration settings, not library defaults or memory-buffer limits.
    store = FileStore(primary, archive, retention=timedelta(days=7), batch_size=64, flush_interval=0.05)
    connections = Connections(group, store)
    provider, requester = DummyProvider(connections), DummyRequester(connections)
    group.register(ModuleSpec("provider", ModuleKind.ADAPTER), provider)
    group.register(ModuleSpec("requester", ModuleKind.SUBSYSTEM, frozenset({"provider"})), requester)
    connections.declare(ModuleAdvertisement("provider", "1", (SPEC,), attributes={"language": "ja"}),
                        {CONTRACT: {"echo": provider.echo, "echo_async": provider.echo_async}})
    connections.declare(ModuleAdvertisement("requester", "1"))
    group.attach_connections(connections)
    runtime = Runtime(group)
    try:
        await runtime.start()
        await asyncio.wait_for(requester.done.wait(), 10)
    finally:
        await runtime.stop()
    assert store.unsaved_events == 0
    return requester.reused


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-connections-demo-") as temporary:
        base = Path(temporary)
        assert not await run_once(base / "primary", base / "archive")
        assert await run_once(base / "primary", base / "archive")
        events = [json.loads(line) for path in (base / "primary").glob("history-*.jsonl")
                  for line in path.read_text(encoding="utf-8").splitlines()]
        assert len({event["run_id"] for event in events}) == 2
        assert sum(event["kind"] == "binding_created" for event in events) == 1
        assert any(event["kind"] == "startup_binding" and event["data"]["valid"] for event in events)
    remaining = asyncio.all_tasks() - {asyncio.current_task()}
    assert not remaining, remaining
    print("requester selection, direct/sync/async and mediated calls: PASS")
    print("persisted binding reused after restart, fresh module state: PASS")
    print("history drained, remaining tasks:", len(remaining))


if __name__ == "__main__":
    asyncio.run(main())
