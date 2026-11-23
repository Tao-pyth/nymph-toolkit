"""Learn inspectable counts from Memory/Document evidence, then restart."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import BindingKey, HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT
from nymph_toolkit.contracts.document import DOCUMENT_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


async def main():
    from cognition_requester import CONTROL_CONTRACT, CONTROL_KEY
    with tempfile.TemporaryDirectory(prefix="ntk-cognition-demo-") as directory:
        root = Path(directory).resolve()
        (root/"note.md").write_text("猫 は 眠る", encoding="utf-8")
        first = None
        for restored in (False, True):
            store = FileStore(root/"core", root/"archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
            group = HybridGroup(HybridSettings(10, 3, 60, 65536, 32, 4), store)
            for spec, version, contract, entry, config, placement in (
                (ModuleSpec("memory", ModuleKind.SUBSYSTEM), "1.1.0", MEMORY_CONTRACT, "subsystems.memory", {"path": str(root/"memory.db")}, Placement.PROCESS),
                (ModuleSpec("document", ModuleKind.ADAPTER, ("memory",)), "1.2.0", DOCUMENT_CONTRACT, "adapters.document", {"root": str(root), "memory_module_id": "memory"}, Placement.LOCAL),
                (ModuleSpec("cognition", ModuleKind.SUBSYSTEM, ("memory",)), "1.3.0", COGNITION_CONTRACT, "subsystems.cognition", {"path": str(root/"cognition.db"), "memory_module_id": "memory"}, Placement.PROCESS),
            ):
                group.register_module(spec, ModuleAdvertisement(spec.module_id, version, (contract,)), "nymph_toolkit."+entry+":factory", config, placement)
            group.register_module(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, ("document", "cognition")),
                                  ModuleAdvertisement("nymph", "dummy-1", (CONTROL_CONTRACT,)), "cognition_requester:factory", {}, Placement.LOCAL)
            runtime = Runtime(group)
            await runtime.start()
            try:
                await group.connections.bind("memory", CONTROL_KEY, "nymph", wait_timeout=5)
                call = await group.connections.prepare(BindingKey("memory", CONTROL_KEY), wait_timeout=5)
                result = await asyncio.wait_for(call.acall("exercise", restored), 70)
                assert isinstance(result, dict), repr(result)
                if restored:
                    assert (result["receipt"], result["profile"]) == first
                first = result["receipt"], result["profile"]
                print({"restored": restored, "word_count": result["profile"]["count"], "sources": result["profile"]["source_counts"]})
            finally:
                await runtime.stop()
            assert all(group.process(n).cleanup_confirmed for n in ("memory", "document", "cognition", "nymph"))
        print("PASS: Cognition learning, evidence, source separation, Memory/Document, restart, cleanup")


if __name__ == "__main__":
    demo_path = str(Path(__file__).resolve().parent)
    sys.path.insert(0, demo_path)
    os.environ["PYTHONPATH"] = demo_path
    asyncio.run(main())
