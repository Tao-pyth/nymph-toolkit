"""Importable demo service; contains no real Nymph decisions or external input."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import os

from nymph_toolkit.contracts import ContractKey, OperatingState, Usage

KEY = ContractKey("example.hybrid", "1")


class Dummy:
    def __init__(self, context, config):
        self.context = context
        self.received = asyncio.Event()
        self.data = []
        context.provide(KEY, {"echo": self.echo, "received": self.result})
        context.provide_stream(KEY, "stream", self.stream)
        context.provide_executor("wait_for_nymph", self.activity, supports_pause=True)

    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 4)
        await self.context.core.publish_usage(usage, contracts={KEY: usage})

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass

    async def echo(self, value):
        return {"value": value, "pid": os.getpid()}

    async def stream(self, receiver, metadata):
        while True:
            event = await receiver.receive(timeout=5)
            if event.kind != "data":
                self.received.set()
                return
            self.data.append(event.data.decode("utf-8"))

    async def result(self):
        await self.received.wait()
        return self.data

    async def activity(self, context, arguments):
        await context.wait_for_finish()
        return {"pid": os.getpid(), "cleanup": "complete"}


def factory(context, config):
    return Dummy(context, config)
