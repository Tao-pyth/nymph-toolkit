"""Persist Memory records through Core and direct RPC, then restart and retrieve."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import BindingKey, HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


async def main():
    from memory_requester import CONTROL_CONTRACT, CONTROL_KEY
    with tempfile.TemporaryDirectory(prefix="ntk-memory-demo-") as directory:
        root = Path(directory)
        first = None
        for restored in (False, True):
            store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
            group = HybridGroup(HybridSettings(10, 3, 5, 65536, 32, 4), store)
            group.register_module(ModuleSpec("memory", ModuleKind.SUBSYSTEM),
                                  ModuleAdvertisement("memory", "1.1.0", (MEMORY_CONTRACT,)),
                                  "nymph_toolkit.subsystems.memory:factory", {"path": str(root / "memory.sqlite3")}, Placement.PROCESS)
            group.register_module(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, ("memory",)),
                                  ModuleAdvertisement("nymph", "dummy-1", (CONTROL_CONTRACT,)),
                                  "memory_requester:factory", {}, Placement.LOCAL)
            runtime = Runtime(group)
            await runtime.start()
            try:
                await group.connections.bind("memory", CONTROL_KEY, "nymph", wait_timeout=5)
                call = await group.connections.prepare(BindingKey("memory", CONTROL_KEY), wait_timeout=5)
                result = await call.acall("exercise", "memory", restored)
                if restored:
                    assert result["saved"] == first
                else:
                    first = result["saved"]
                print({"restored": restored, "routes": result["routes"], "page_count": result["page_count"]})
            finally:
                await runtime.stop()
            assert group.process("memory").cleanup_confirmed
        print("PASS: Memory persistence, provenance, direct/Core RPC, restart, cleanup")


if __name__ == "__main__":
    demo_path = str(Path(__file__).resolve().parent)
    sys.path.insert(0, demo_path)
    os.environ["PYTHONPATH"] = demo_path
    asyncio.run(main())
