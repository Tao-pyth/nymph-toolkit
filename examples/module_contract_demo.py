"""Connect a Contracts-only Subsystem and Adapter through the public Core API."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from nymph_toolkit.contracts import (
    BindingKey, ContractSpec, HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec,
    OperationMode, OperationSpec, Placement,
)
from nymph_toolkit.core import FileStore, HybridGroup, Runtime, validate_module_registration


async def main():
    from contract_dummy import KEY, OPERATIONS
    contract = ContractSpec(KEY, tuple(OperationSpec(name, OperationMode.ASYNC) for name in OPERATIONS))
    with tempfile.TemporaryDirectory(prefix="ntk-contract-") as directory:
        root = Path(directory)
        store = FileStore(root / "history", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
        group = HybridGroup(HybridSettings(10, 3, 5, 65536, 32, 4), store)
        for name, kind, placement in (("nymph", ModuleKind.SUBSYSTEM, Placement.LOCAL),
                                       ("document", ModuleKind.ADAPTER, Placement.PROCESS)):
            args = (ModuleSpec(name, kind), ModuleAdvertisement(name, "example-1", (contract,)),
                    "contract_dummy:factory", {}, placement)
            validate_module_registration(*args)
            group.register_module(*args)
        group.enable_activities(clock_check_interval=.01)
        runtime = Runtime(group)
        await runtime.start()
        try:
            # The host asks the dummy to run its own requester-side scenario.
            await group.connections.bind("document", KEY, "nymph", wait_timeout=5)
            call = await group.connections.prepare(BindingKey("document", KEY), wait_timeout=5)
            result = await call.acall("exercise", "document")
            assert result == {"rpc": "direct+core", "stream": "received", "activity": "nymph-finished", "registration": "sealed"}, result
            print(result)
        finally:
            await runtime.stop()
        assert group.process("document").cleanup_confirmed
        print("PASS: public Contracts, Subsystem/Adapter, direct/Core RPC, stream, Nymph activity, cleanup")


if __name__ == "__main__":
    demo_path = str(Path(__file__).resolve().parent)
    sys.path.insert(0, demo_path)
    os.environ["PYTHONPATH"] = demo_path
    asyncio.run(main())
