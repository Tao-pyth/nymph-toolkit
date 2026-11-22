"""Dummy requester using only public Contracts, including the Memory declaration."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import (
    ContractKey, ContractSpec, OperationFailure, OperationMode, OperationSpec, OperatingState, Usage,
)
from nymph_toolkit.contracts.memory import MEMORY_KEY

CONTROL_KEY = ContractKey("example.memory.requester", "1")
CONTROL_CONTRACT = ContractSpec(CONTROL_KEY, (OperationSpec("exercise", OperationMode.ASYNC),))


class Requester:
    def __init__(self, context, config):
        self.context = context
        context.provide(CONTROL_KEY, {"exercise": self.exercise})

    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 1)
        await self.context.core.publish_usage(usage, contracts={CONTROL_KEY: usage})

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass

    async def exercise(self, provider, restored=False):
        core = self.context.core
        candidates = await core.candidates(MEMORY_KEY)
        assert provider in [c.advertisement.module_id for c in candidates]
        # Selection is the requester's decision, never Memory's or Core's.
        await core.bind(MEMORY_KEY, provider, timeout=5)
        link = await core.prepare(MEMORY_KEY, timeout=5)
        try:
            value = {"record_id": "rain", "kind": "experience", "content": "雨を観測した。",
                     "source_kind": "observed", "source": "dummy:weather", "occurred_at": "2026-11-23T09:30:00+09:00"}
            if restored:
                saved = await link.acall("get", "rain", timeout=5)
            else:
                saved = await link.acall("put", value, timeout=5)
            assert isinstance(saved, dict), saved
            assert await core.invoke(MEMORY_KEY, "put", value, timeout=5) == saved
            assert await core.invoke(MEMORY_KEY, "get", "rain", timeout=5) == saved
            conflict = await link.acall("put", dict(value, content="別の内容"), timeout=5)
            assert isinstance(conflict, OperationFailure) and conflict.code == "memory.conflict"
            missing = await core.invoke(MEMORY_KEY, "get", "missing", timeout=5)
            assert isinstance(missing, OperationFailure) and missing.code == "memory.not_found"
            invalid = await link.acall("put", {}, timeout=5)
            assert isinstance(invalid, OperationFailure) and invalid.code == "memory.invalid"
            # Near-limit records exercise the largest supported page on the wire.
            for index in range(8):
                knowledge = dict(value, record_id=f"knowledge-{index}", kind="knowledge",
                                 source_kind="reported", content="x" * 3700)
                assert isinstance(await link.acall("put", knowledge, timeout=5), dict)
            page = await core.invoke(MEMORY_KEY, "query", kind="knowledge", source_kind="reported", timeout=5)
            assert len(page["records"]) == 8 and not page["has_more"]
            direct_page = await link.acall("query", kind="knowledge", source_kind="reported", timeout=5)
            assert page == direct_page
            # Business errors leave the existing prepared connection usable.
            assert await link.acall("get", "rain", timeout=5) == saved
            return {"saved": saved, "page_count": len(page["records"]), "restored": restored,
                    "routes": "direct+core", "failures": "invalid+not_found+conflict"}
        finally:
            await link.close()


def factory(context, config):
    return Requester(context, config)
