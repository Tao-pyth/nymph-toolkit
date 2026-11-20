"""Controllable service for lifecycle, failure and cleanup observations."""

# SPDX-License-Identifier: Apache-2.0
import asyncio


class Service:
    def __init__(self, *, start_gate=None, run_gate=None, stop_gate=None, errors=None, child=False):
        self.gates = {"start": start_gate, "run": run_gate, "stop": stop_gate}
        self.errors = errors or {}
        self.events = []
        self.entered = {phase: asyncio.Event() for phase in self.gates}
        self.make_child = child
        self.child = None

    async def _phase(self, phase):
        self.events.append(phase)
        self.entered[phase].set()
        if self.gates[phase] is not None:
            await self.gates[phase].wait()
        if phase in self.errors:
            raise self.errors[phase]

    async def start(self):
        if self.make_child:
            self.child = asyncio.create_task(asyncio.Event().wait(), name="dummy-owned")
        await self._phase("start")

    async def run(self):
        await self._phase("run")
        return "result"

    async def stop(self):
        if self.child is not None:
            self.child.cancel()
            await asyncio.gather(self.child, return_exceptions=True)
        await self._phase("stop")
