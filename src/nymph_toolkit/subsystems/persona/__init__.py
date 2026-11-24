"""Persistent Persona traits; updates only follow explicit external requests."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import ModuleContextProtocol, OperatingState, RuntimeService, Usage
from nymph_toolkit.contracts.persona import PERSONA_KEY
from ._model import fields
from ._store import Store

__all__ = ["factory"]


class _Persona:
    def __init__(self, context, config):
        fields(config, "path initial_traits")
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Persona requires max_frame_bytes >= 65536")
        self.context = context
        self.store = Store(config["path"], context.module_id, config["initial_traits"], self._usage)
        context.provide(PERSONA_KEY, {name: getattr(self, name) for name in ("get", "apply", "get_update", "history")})

    async def _usage(self, active):
        usage = Usage(OperatingState.RUNNING, True, active, 1)
        await self.context.core.publish_usage(usage, contracts={PERSONA_KEY: usage})

    async def start(self):
        await self.store.start()
        await self._usage(0)

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        await self.store.stop()

    async def get(self):
        return await self.store.execute("get")

    async def apply(self, request):
        return await self.store.execute("apply", request)

    async def get_update(self, command_id):
        return await self.store.execute("get_update", command_id)

    async def history(self, *, after=0, limit=4):
        return await self.store.execute("history", after, limit)


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Persona(context, config)
