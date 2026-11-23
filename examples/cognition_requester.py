"""Dummy Nymph supplying segmentation and labels, never delegating choices to Core."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from nymph_toolkit.contracts import ContractKey, ContractSpec, OperationFailure, OperationMode, OperationSpec, OperatingState, Usage
from nymph_toolkit.contracts.cognition import COGNITION_KEY
from nymph_toolkit.contracts.document import DOCUMENT_KEY
from nymph_toolkit.contracts.memory import MEMORY_KEY

CONTROL_KEY = ContractKey("example.cognition.requester", "1")
CONTROL_CONTRACT = ContractSpec(CONTROL_KEY, (OperationSpec("exercise", OperationMode.ASYNC),))


def success(value):
    assert isinstance(value, dict), repr(value)
    return value


class Requester:
    def __init__(self, context, config):
        self.context = context
        context.provide(CONTROL_KEY, {"exercise": self.exercise})

    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 1)
        await self.context.core.publish_usage(usage, contracts={CONTROL_KEY: usage})

    async def run(self): await asyncio.Event().wait()
    async def stop(self): pass

    async def exercise(self, restored=False):
        core = self.context.core
        for key, module in ((COGNITION_KEY, "cognition"), (MEMORY_KEY, "memory"), (DOCUMENT_KEY, "document")):
            await core.bind(key, module, timeout=5)
        link = await core.prepare(COGNITION_KEY, timeout=5)
        try:
            before = success(await link.acall("inspect", "猫", timeout=5))
            assert before["known"] == restored, before
            saved = success(await core.invoke(DOCUMENT_KEY, "ingest", {
                "path": "note.md", "record_id": "cat-sleep", "kind": "experience",
                "source_kind": "observed", "occurred_at": "2026-11-23T00:00:00Z"}, timeout=10))
            args = {"tokens": ["猫", "は", "眠る"], "concepts": ["sleep", "animal"]}
            receipt = success(await link.acall("learn", "cat-sleep", timeout=10, **args))
            assert await core.invoke(COGNITION_KEY, "learn", "cat-sleep", timeout=10, **args) == receipt
            for key, tokens, labels, source in (
                ("cat-play", ["猫", "は", "遊ぶ"], ["animal", "play"], "observed"),
                ("dream-cat", ["猫", "飛ぶ"], ["fantasy"], "dream"),
            ):
                success(await core.invoke(MEMORY_KEY, "put", {"record_id": key, "kind": "experience",
                    "content": " ".join(tokens), "source_kind": source, "source": "fixture:"+key,
                    "occurred_at": "2026-11-23T00:00:00Z"}, timeout=5))
                success(await link.acall("learn", key, tokens=tokens, concepts=labels, timeout=10))
            profile = success(await core.invoke(COGNITION_KEY, "inspect", "猫", timeout=5))
            assert (profile["count"], profile["documents"]) == (3, 3), profile
            assert {x["token"]: x["count"] for x in profile["successors"]} == {"は": 2, "飛ぶ": 1}
            assert profile["source_counts"] == {"dream": 1, "observed": 2}
            observed = success(await link.acall("inspect", "猫", source_kind="observed", timeout=5))
            assert observed["count"] == 2 and all(c["label"] != "fantasy" for c in observed["concepts"])
            assert not success(await link.acall("inspect", "unseen", timeout=5))["known"]
            conflict = await link.acall("learn", "cat-sleep", tokens=args["tokens"], concepts=["wrong"], timeout=10)
            assert isinstance(conflict, OperationFailure) and conflict.code == "cognition.conflict", conflict
            assert await core.invoke(MEMORY_KEY, "get", "cat-sleep", timeout=5) == saved
            if restored:
                assert profile == before, (profile, before)
            return {"receipt": receipt, "profile": profile, "restored": restored, "routes": "direct+core"}
        finally:
            await link.close()


def factory(context, config): return Requester(context, config)
