"""Dummy Nymph choosing the document, record identity and provenance labels."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from nymph_toolkit.contracts import ContractKey, ContractSpec, OperationFailure, OperationMode, OperationSpec, OperatingState, Usage
from nymph_toolkit.contracts.document import DOCUMENT_KEY
from nymph_toolkit.contracts.memory import MEMORY_KEY

CONTROL_KEY = ContractKey("example.document.requester", "1")
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

    async def exercise(self, restored=False):
        core = self.context.core
        await core.bind(DOCUMENT_KEY, "document", timeout=5)
        await core.bind(MEMORY_KEY, "memory", timeout=5)
        link = await core.prepare(DOCUMENT_KEY, timeout=5)
        value = {"path": "note.md", "record_id": "document-1", "kind": "knowledge",
                 "source_kind": "reported", "occurred_at": "2026-11-23T09:00:00+09:00"}
        try:
            before = await core.invoke(MEMORY_KEY, "get", "document-1", timeout=5) if restored else None
            saved = await link.acall("ingest", value, timeout=10)
            assert isinstance(saved, dict), saved
            assert await core.invoke(DOCUMENT_KEY, "ingest", value, timeout=10) == saved
            assert await core.invoke(MEMORY_KEY, "get", "document-1", timeout=5) == saved
            if restored:
                assert saved == before
            invalid = await link.acall("ingest", dict(value, path="missing.txt"), timeout=5)
            assert isinstance(invalid, OperationFailure) and invalid.code == "document.read", invalid
            conflict = await link.acall("ingest", dict(value, source_kind="observed"), timeout=5)
            assert isinstance(conflict, OperationFailure) and conflict.code == "memory.conflict", conflict
            assert await core.invoke(MEMORY_KEY, "get", "document-1", timeout=5) == saved
            page = await core.invoke(MEMORY_KEY, "query", kind="knowledge", timeout=5)
            assert len(page["records"]) == 1
            return {"saved": saved, "restored": restored, "routes": "direct+core"}
        finally:
            await link.close()


def factory(context, config):
    return Requester(context, config)
