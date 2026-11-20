"""A controllable store double for connection state-machine tests only."""

# SPDX-License-Identifier: Apache-2.0
import asyncio


class MemoryStore:
    def __init__(self, bindings=()):
        self.bindings = tuple(bindings)
        self.records = []
        self.failure = None
        self.admitting = True
        self.changed = asyncio.Event()
        self.save_entered = asyncio.Event()
        self.save_gate = None
        self.failed = asyncio.Event()

    async def start(self):
        pass

    def append(self, kind, data):
        self.records.append((kind, data))

    async def load_bindings(self):
        return self.bindings

    async def save_bindings(self, bindings):
        self.save_entered.set()
        if self.save_gate is not None:
            await self.save_gate.wait()
        self.bindings = tuple(bindings)

    async def wait_ready(self):
        while not self.admitting:
            event = self.changed
            if self.failure:
                raise self.failure
            await event.wait()

    async def wait_failure(self):
        await self.failed.wait()
        return self.failure

    async def stop(self):
        self.admitting = False
        self.pulse()

    def pulse(self):
        old, self.changed = self.changed, asyncio.Event()
        old.set()
