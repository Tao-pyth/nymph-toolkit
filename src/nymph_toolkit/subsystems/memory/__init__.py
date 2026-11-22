"""A minimal persistent Memory Subsystem; factory is the public lifecycle entry."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import ModuleContextProtocol, OperatingState, RuntimeService, Usage
from nymph_toolkit.contracts.memory import MEMORY_KEY
from ._store import Store

__all__ = ["factory"]


class _Memory:
    def __init__(self, context, config):
        if type(config) is not dict or set(config) != {"path"}:
            raise ValueError("Memory config requires only an absolute path")
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Memory requires max_frame_bytes >= 65536")
        self.context = context
        self.store = Store(config["path"], self._usage)
        context.provide(MEMORY_KEY, {"put": self.put, "get": self.get, "query": self.query})

    async def _usage(self, active):
        usage = Usage(OperatingState.RUNNING, True, active, 1)
        await self.context.core.publish_usage(usage, contracts={MEMORY_KEY: usage})

    async def start(self):
        await self.store.start()
        await self._usage(0)

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        await self.store.stop()
        # Core owns the final stopped state; no control RPC after teardown.

    async def put(self, record):
        return await self.store.execute("put", record)

    async def get(self, record_id):
        return await self.store.execute("get", record_id)

    async def query(self, *, kind=None, source_kind=None, after=0, limit=8):
        return await self.store.execute("query", kind, source_kind, after, limit)


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Memory(context, config)
