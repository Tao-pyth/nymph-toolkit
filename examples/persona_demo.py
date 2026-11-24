"""Read Persona, apply external deltas, verify persistence without resetting it."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import BindingKey, HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT
from nymph_toolkit.core import FileStore, HybridGroup, Runtime

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import persona_requester as requester
else:
    from examples import persona_requester as requester


def group_at(root, *, requester_placement=Placement.LOCAL, persona_placement=Placement.PROCESS):
    store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    group = HybridGroup(HybridSettings(10, 3, 30, 65536, 32, 4), store)
    group.register_module(ModuleSpec("persona", ModuleKind.SUBSYSTEM),
                          ModuleAdvertisement("persona", "1.7.0", (PERSONA_CONTRACT,)),
                          "nymph_toolkit.subsystems.persona:factory",
                          {"path": str(root / "persona.sqlite3"), "initial_traits": {"curiosity": 500, "sociability": 400}},
                          persona_placement)
    group.register_module(ModuleSpec("nymph", ModuleKind.SUBSYSTEM, ("persona",)),
                          ModuleAdvertisement("nymph", "example-1", (requester.CONTROL_CONTRACT,)),
                          requester.__name__ + ":factory", {}, requester_placement)
    return group


async def main():
    with tempfile.TemporaryDirectory(prefix="ntk-persona-demo-") as directory:
        root = Path(directory)
        first = None
        for restored in (False, True):
            group = group_at(root)
            runtime = Runtime(group)
            await runtime.start()
            try:
                await group.connections.bind("persona", requester.CONTROL_KEY, "nymph", wait_timeout=5)
                link = await group.connections.prepare(BindingKey("persona", requester.CONTROL_KEY), wait_timeout=5)
                result = await link.acall("exercise", restored)
                assert isinstance(result, dict), result
                if restored:
                    assert result["receipt"] == first
                first = result["receipt"]
                print({"restored": restored, "traits": result["current"]["traits"], "updates": result["updates"]})
            finally:
                await runtime.stop()
            assert group.process("persona").cleanup_confirmed
        print("PASS: Persona external updates, direct/Core RPC, history, restart, cleanup")


if __name__ == "__main__":
    os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parent)
    asyncio.run(main())
