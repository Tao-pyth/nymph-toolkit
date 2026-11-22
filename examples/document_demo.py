"""Import a local Markdown file into Memory, restart, and retrieve its record."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import BindingKey, HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.contracts.document import DOCUMENT_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


async def main():
    from document_requester import CONTROL_CONTRACT, CONTROL_KEY
    with tempfile.TemporaryDirectory(prefix="ntk-document-demo-") as directory:
        root = Path(directory).resolve()
        (root / "note.md").write_bytes("# 観測メモ\r\n窓の外は雨。\n".encode("utf-8"))
        first = None
        for restored in (False, True):
            store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
            group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4), store)
            group.register_module(ModuleSpec("memory", ModuleKind.SUBSYSTEM),
                                  ModuleAdvertisement("memory", "1.1.0", (MEMORY_CONTRACT,)),
                                  "nymph_toolkit.subsystems.memory:factory", {"path": str(root / "memory.db")}, Placement.PROCESS)
            group.register_module(ModuleSpec("document", ModuleKind.ADAPTER, ("memory",)),
                                  ModuleAdvertisement("document", "1.2.0", (DOCUMENT_CONTRACT,)),
                                  "nymph_toolkit.adapters.document:factory",
                                  {"root": str(root), "memory_module_id": "memory"}, Placement.PROCESS)
            group.register_module(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, ("document",)),
                                  ModuleAdvertisement("nymph", "dummy-1", (CONTROL_CONTRACT,)),
                                  "document_requester:factory", {}, Placement.LOCAL)
            runtime = Runtime(group)
            await runtime.start()
            try:
                await group.connections.bind("memory", CONTROL_KEY, "nymph", wait_timeout=5)
                call = await group.connections.prepare(BindingKey("memory", CONTROL_KEY), wait_timeout=5)
                result = await call.acall("exercise", restored)
                assert isinstance(result, dict), result
                if restored:
                    assert result["saved"] == first
                first = result["saved"]
                print({"restored": restored, "routes": result["routes"], "record_id": first["record_id"]})
            finally:
                await runtime.stop()
            assert all(group.process(name).cleanup_confirmed for name in ("memory", "document", "nymph"))
        print("PASS: Document text, provenance/hash, Memory commit/restart, direct/Core RPC, cleanup")


if __name__ == "__main__":
    demo_path = str(Path(__file__).resolve().parent)
    sys.path.insert(0, demo_path)
    os.environ["PYTHONPATH"] = demo_path
    asyncio.run(main())
