"""Manually advance wall and monotonic clocks without waiting for real hours."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta


class ActivityClock:
    def __init__(self, now):
        self.wall = now
        self.ticks = 0.0
        self.waiters = []

    def now(self):
        return self.wall

    def monotonic(self):
        return self.ticks

    async def sleep(self, seconds):
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future = asyncio.get_running_loop().create_future()
        item = (self.ticks + seconds, future)
        self.waiters.append(item)
        try:
            await future
        finally:
            self.waiters.remove(item)

    def advance(self, seconds, *, wall_seconds=None):
        self.ticks += seconds
        self.wall += timedelta(seconds=seconds if wall_seconds is None else wall_seconds)
        for deadline, future in tuple(self.waiters):
            if deadline <= self.ticks and not future.done():
                future.set_result(None)
