"""Run a dummy service; no external integrations or activity decisions."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import json

from nymph_toolkit.core import Runtime
from nymph_toolkit.contracts import RuntimeState


class DummyService:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def start(self) -> None:
        self.events.append("start")

    async def run(self) -> str:
        await asyncio.sleep(0)
        self.events.append("run")
        return "dummy-result"

    async def stop(self) -> None:
        self.events.append("stop")


async def main() -> None:
    before = asyncio.all_tasks()
    service = DummyService()
    runtime = Runtime(service)
    await runtime.start()
    result = await runtime.wait()
    await runtime.stop()
    remaining = asyncio.all_tasks() - before
    assert runtime.state == RuntimeState.STOPPED
    assert service.events == ["start", "run", "stop"]
    assert not remaining
    print(json.dumps({"state": runtime.state, "result": result, "events": service.events,
                      "remaining_tasks": len(remaining)}))


if __name__ == "__main__":
    asyncio.run(main())
