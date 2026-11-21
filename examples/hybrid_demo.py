"""Run a local Nymph dummy and a Core-owned child with the installed NTK package."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import (
    ActivityKey, ActivityRequest, ActivityState, ContractSpec, HybridSettings, ModuleAdvertisement,
    ModuleKind, ModuleSpec, OperationMode, OperationSpec, OverflowPolicy, Placement, StreamOptions,
)
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


async def main():
    from hybrid_dummy import KEY
    contract = ContractSpec(KEY, tuple(OperationSpec(name, OperationMode.ASYNC) for name in ("echo", "received", "stream")))
    with tempfile.TemporaryDirectory(prefix="ntk-hybrid-") as directory:
        root = Path(directory)
        store = FileStore(root / "history", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
        group = HybridGroup(HybridSettings(10, 3, 5, 65536, 32, 4), store)
        for name, placement in (("nymph", Placement.LOCAL), ("worker", Placement.PROCESS)):
            group.register_module(ModuleSpec(name, ModuleKind.SUBSYSTEM), ModuleAdvertisement(name, "demo-1", (contract,)),
                                  "hybrid_dummy:factory", {}, placement)
        manager = group.enable_activities(clock_check_interval=.02, max_running=1)
        runtime = Runtime(group)
        await runtime.start()
        try:
            core = group.client("nymph")
            await core.bind(KEY, "worker", timeout=5)
            link = await core.prepare(KEY, timeout=5)
            echoed = await link.acall("echo", "direct child call", timeout=5)
            assert echoed["pid"] != os.getpid()
            sender = await link.open_stream("stream", StreamOptions(1024, 8, 1024, 8, OverflowPolicy.WAIT), timeout=5)
            await sender.send(b"dummy bytes", timeout=5)
            await sender.close(timeout=5)
            assert await link.acall("received", timeout=5) == ["dummy bytes"]
            request = ActivityRequest(ActivityKey("nymph", "investigate"), "dummy activity", None, timedelta(seconds=.05))
            manager.submit_remote(request, "worker", "wait_for_nymph")
            async with asyncio.timeout(5):
                while not manager.snapshot(request.key).planned_end_notified:
                    await asyncio.sleep(.005)
            assert manager.snapshot(request.key).state == ActivityState.RUNNING
            manager.request_finish(request.key)
            ended = await asyncio.wait_for(manager.wait(request.key), 5)
            assert ended.cleanup_confirmed and ended.state == ActivityState.STOPPED
            await link.close()
        finally:
            await runtime.stop()
        assert group.process("worker").returncode == 0
        assert group.process("worker").cleanup_confirmed
        await asyncio.sleep(0)
        remaining = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        assert not remaining, remaining
        print("PASS: direct RPC, stream, period notification, Nymph finish, child cleanup; remaining tasks=0")


if __name__ == "__main__":
    # Make only this example's dummy importable in both processes. A real function
    # should be installed in the shared environment, without modifying this path.
    demo_path = str(Path(__file__).resolve().parent)
    sys.path.insert(0, demo_path)
    os.environ["PYTHONPATH"] = demo_path
    asyncio.run(main())
