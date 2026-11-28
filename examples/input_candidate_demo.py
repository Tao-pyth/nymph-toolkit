"""A requester prepares Web, document and conversation candidates and saves explicitly."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from nymph_toolkit.contracts import (
    ContractKey, ContractSpec, HybridSettings, ModuleAdvertisement, ModuleKind,
    ModuleSpec, OperatingState, OperationFailure, OperationMode, OperationSpec, Placement, Usage,
)
from nymph_toolkit.contracts.input_candidate import INPUT_CANDIDATE_CONTRACT, INPUT_CANDIDATE_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime

_CONTROL = ContractSpec(ContractKey("example.input.exercise", "1"), (OperationSpec("exercise", OperationMode.ASYNC),))
_PERMISSION = {"destination": "mock", "fields": ["content"]}
_LABELS = {"web": ("knowledge", "reported"), "document": ("knowledge", "reported"),
           "conversation": ("experience", "observed")}


def request(input_type="web", *, explicit=True):
    kind, source_kind = _LABELS[input_type]
    fields = {"occurred_at": "2026-11-28T08:00:00+09:00"}
    if explicit:
        fields.update(kind=kind, source_kind=source_kind)
    return {"record_id": "sample-" + input_type,
            "input": {"input_type": input_type, "content": "図書室は火曜10時に開館します。",
                      "source": "sample:" + input_type, "acquisition": "fixture/1"},
            "fields": fields, "permission": _PERMISSION}


def settings(method):
    common = {"method": method, "configuration_version": 1}
    if method == "defaults":
        return dict(common, defaults={name: dict(kind=labels[0], source_kind=labels[1])
                                      for name, labels in _LABELS.items()})
    return dict(common, model_id="fixed-example/1", operation="summarize", timeout=1,
                response={"content": "火曜10時開館。", "kind": "knowledge", "source_kind": "reported"})


class Requester:
    def __init__(self, context):
        self.core = context.core
        context.provide(_CONTROL.key, {"exercise": self.exercise})

    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 1)
        await self.core.publish_usage(usage, contracts={_CONTROL.key: usage})

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass

    async def exercise(self, method):
        await self.core.bind(INPUT_CANDIDATE_KEY, "candidate", timeout=5)
        await self.core.bind(MEMORY_KEY, "memory", timeout=5)
        link = await self.core.prepare(INPUT_CANDIDATE_KEY, timeout=5)
        saved_count = 0
        try:
            for input_type in _LABELS:
                supplied = request(input_type, explicit=method == "mock_ai")
                candidate = await link.acall("prepare", supplied, timeout=5)
                via_core = await self.core.invoke(INPUT_CANDIDATE_KEY, "prepare", supplied, timeout=5)
                assert via_core == candidate and candidate["status"] == "ready", candidate
                assert candidate["record"]["source"] == supplied["input"]["source"]
                before = await self.core.invoke(MEMORY_KEY, "query", timeout=5)
                assert len(before["records"]) == saved_count
                saved = await self.core.invoke(MEMORY_KEY, "put", candidate["record"], timeout=5)
                assert isinstance(saved, dict), saved
                assert await self.core.invoke(MEMORY_KEY, "get", candidate["record"]["record_id"], timeout=5) == saved
                conflict = await self.core.invoke(MEMORY_KEY, "put", dict(candidate["record"], content="別内容"), timeout=5)
                assert isinstance(conflict, OperationFailure) and conflict.code == "memory.conflict", conflict
                saved_count += 1
            return {"method": method, "saved": saved_count}
        finally:
            await link.close()


def requester_factory(context, config):
    return Requester(context)


async def exercise(root, method, requester=Placement.LOCAL, provider=Placement.LOCAL):
    store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4), store)
    modules = (
        ("memory", ModuleKind.SUBSYSTEM, MEMORY_CONTRACT, "nymph_toolkit.subsystems.memory:factory",
         {"path": str(root / "memory.db")}, provider),
        ("candidate", ModuleKind.ADAPTER, INPUT_CANDIDATE_CONTRACT,
         "nymph_toolkit.adapters.input_candidate:factory", settings(method), provider),
        ("requester", ModuleKind.SUBSYSTEM, _CONTROL, "examples.input_candidate_demo:requester_factory", {}, requester),
        ("driver", ModuleKind.SUBSYSTEM, None, "examples.interaction_setup:requester_factory", {}, Placement.LOCAL),
    )
    for name, kind, contract, factory, config, placement in modules:
        group.register_module(ModuleSpec(name, kind, ()), ModuleAdvertisement(name, "example-1", () if contract is None else (contract,)),
                              factory, config, placement)
    runtime = Runtime(group)
    await runtime.start()
    try:
        client = group.client("driver")
        await client.bind(_CONTROL.key, "requester", timeout=5)
        return await client.invoke(_CONTROL.key, "exercise", method, timeout=20)
    finally:
        await runtime.stop()


async def main():
    for method in ("defaults", "mock_ai"):
        with TemporaryDirectory() as work:
            print(await exercise(Path(work).resolve(), method))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    asyncio.run(main())
