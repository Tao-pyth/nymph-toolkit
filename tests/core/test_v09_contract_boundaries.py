"""Verify that hybrid placement does not silently change existing local contracts."""

# SPDX-License-Identifier: Apache-2.0
import tempfile
from datetime import timedelta
from pathlib import Path
import unittest

from nymph_toolkit.contracts import (
    BindingKey, ContractKey, ContractSpec, HybridSettings, ModuleAdvertisement,
    ModuleKind, ModuleSpec, OperatingState, OperationMode, OperationSpec, Placement, Usage,
)
from nymph_toolkit.core import Connections, FileStore, HybridGroup, Registry, Runtime
from tests.doubles.connection_store import MemoryStore

KEY = ContractKey("v09.local-object", "1")
SYNC = ContractSpec(KEY, (OperationSpec("identity", OperationMode.SYNC),))


class PlacementContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_sync_contract_keeps_python_object_identity_on_both_routes(self):
        registry = Registry()
        connections = Connections(registry, MemoryStore())
        for name in ("requester", "provider"):
            registry.register(ModuleSpec(name, ModuleKind.SUBSYSTEM))
            provides = name == "provider"
            connections.declare(
                ModuleAdvertisement(name, "1", (SYNC,) if provides else ()),
                {KEY: {"identity": lambda value: value}} if provides else None)
            usage = Usage(OperatingState.RUNNING, True, 0, 2)
            connections.publish_usage(name, usage, contracts={KEY: usage} if provides else None)
        runtime = Runtime(connections)
        await runtime.start()
        try:
            await connections.bind("requester", KEY, "provider", wait_timeout=1)
            key = BindingKey("requester", KEY)
            prepared = await connections.prepare(key, wait_timeout=1)
            value = object()
            self.assertIs(prepared.call("identity", value), value)
            self.assertIs(await connections.invoke(key, "identity", wait_timeout=1, args=(value,)), value)
        finally:
            await runtime.stop()

    async def test_hybrid_rejects_same_sync_contract_without_partial_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for placement in Placement:
                with self.subTest(placement=placement):
                    store = FileStore(root / placement / "main", root / placement / "archive",
                                      retention=timedelta(days=1), batch_size=8, flush_interval=.01)
                    group = HybridGroup(HybridSettings(5, 2, 2, 65536, 8, 2), store)
                    before = group.revision
                    with self.assertRaisesRegex(ValueError, "ASYNC"):
                        group.register_module(
                            ModuleSpec("provider", ModuleKind.SUBSYSTEM),
                            ModuleAdvertisement("provider", "1", (SYNC,)),
                            "tests.doubles.hybrid:factory", {}, placement)
                    self.assertEqual(group.entries(), ())
                    self.assertEqual(group.revision, before)
                    self.assertEqual(group.connections.candidates(KEY), ())
                    self.assertFalse((root / placement / "main").exists())
