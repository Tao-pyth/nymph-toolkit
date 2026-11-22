"""B00 registration and external Contracts-only modules in all placements."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from datetime import timedelta
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nymph_toolkit import contracts
from nymph_toolkit.contracts import (
    BindingKey, ContractKey, ContractSpec, HybridSettings, ModuleAdvertisement,
    ModuleKind, ModuleSpec, OperationMode, OperationSpec, Placement, ProtocolError,
)
from nymph_toolkit.core import (
    CoreClient, DirectLink, FileStore, HybridGroup, ModuleContext, Runtime,
    StreamReceiver, StreamSender, validate_module_registration,
)
from examples.contract_dummy import KEY, OPERATIONS

CONTRACT = ContractSpec(KEY, tuple(OperationSpec(n, OperationMode.ASYNC) for n in OPERATIONS))
SETTINGS = HybridSettings(10, 3, 5, 65536, 32, 4)


class RegistrationTests(unittest.TestCase):
    def description(self, **changes):
        result = dict(spec=ModuleSpec("module", ModuleKind.ADAPTER),
                      advertisement=ModuleAdvertisement("module", "1", (CONTRACT,)),
                      factory="not_installed:anything", config={"items": [{"value": 1}]}, placement=Placement.PROCESS)
        result.update(changes)
        return result

    def test_preflight_copies_json_without_importing_or_starting_factory(self):
        args = self.description()
        with patch("importlib.import_module", side_effect=AssertionError("Must not import")):
            result = validate_module_registration(**args)
        result["items"][0]["value"] = 2
        self.assertEqual(args["config"]["items"][0]["value"], 1)

    def test_invalid_description_is_rejected_before_registration_or_storage(self):
        sync = ContractSpec(ContractKey("sync", "1"), (OperationSpec("call", OperationMode.SYNC),))
        cases = [(dict(spec=None), TypeError), (dict(advertisement=None), ValueError),
                 (dict(advertisement=ModuleAdvertisement("other", "1", (CONTRACT,))), ValueError),
                 (dict(placement="process"), TypeError), (dict(factory="missing"), ValueError),
                 (dict(config={"not_json": object()}), ProtocolError),
                 (dict(advertisement=ModuleAdvertisement("module", "1", (sync,))), ValueError)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = HybridGroup(SETTINGS, FileStore(root / "history", root / "archive",
                                retention=timedelta(days=1), batch_size=16, flush_interval=.05))
            for changes, error in cases:
                with self.subTest(changes=changes):
                    with self.assertRaises(error):
                        validate_module_registration(**self.description(**changes))
                    with self.assertRaises(error):
                        group.register_module(**self.description(**changes))
                    self.assertFalse(group.entries())
                    self.assertFalse(list(root.iterdir()))

    def test_contracts_and_external_example_do_not_import_core(self):
        paths = list(Path(contracts.__file__).parent.glob("*.py"))
        paths.append(Path(__file__).resolve().parents[2] / "examples/contract_dummy.py")
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                    self.assertFalse(node.level and (node.module or "").startswith("core"), path)
                else:
                    continue
                self.assertFalse(any(n.startswith("nymph_toolkit.core") for n in names), path)

    def test_protocol_call_shapes_match_concrete_endpoints(self):
        pairs = [(contracts.ModuleContextProtocol, ModuleContext), (contracts.CoreClientProtocol, CoreClient),
                 (contracts.DirectLinkProtocol, DirectLink), (contracts.StreamSenderProtocol, StreamSender),
                 (contracts.StreamReceiverProtocol, StreamReceiver)]
        for protocol, concrete in pairs:
            for name, method in vars(protocol).items():
                if name.startswith("_") or not inspect.isfunction(method):
                    continue
                with self.subTest(protocol=protocol.__name__, name=name):
                    actual = getattr(concrete, name)
                    self.assertEqual(inspect.iscoroutinefunction(method), inspect.iscoroutinefunction(actual))
                    def shape(value):
                        return [(p.name, p.kind, p.default) for p in inspect.signature(value).parameters.values()]
                    self.assertEqual(shape(method), shape(actual))


class ModuleContractIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_kinds_and_four_placements_use_only_public_contracts(self):
        for kind in ModuleKind:
            for requester in Placement:
                for provider in Placement:
                    with self.subTest(kind=kind, requester=requester, provider=provider):
                        await self.scenario(kind, requester, provider)

    async def scenario(self, kind, requester, provider):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileStore(root / "history", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
            group = HybridGroup(SETTINGS, store)
            other_kind = ModuleKind.ADAPTER if kind == ModuleKind.SUBSYSTEM else ModuleKind.SUBSYSTEM
            for name, module_kind, placement in (("provider", other_kind, provider), ("requester", kind, requester)):
                group.register_module(ModuleSpec(name, module_kind, ("provider",) if name == "requester" else ()),
                                      ModuleAdvertisement(name, "1", (CONTRACT,), attributes={"example": True}),
                                      "examples.contract_dummy:" + ("async_factory" if module_kind == ModuleKind.ADAPTER else "factory"),
                                      {}, placement)
            group.enable_activities(clock_check_interval=.01)
            runtime = Runtime(group)
            contexts = []
            await runtime.start()
            try:
                for name, placement in (("provider", provider), ("requester", requester)):
                    if placement == Placement.LOCAL:
                        context = group.client(name).context
                        contexts.append(context)
                        self.check_sealed(context)
                await group.connections.bind("provider", KEY, "requester", wait_timeout=5)
                call = await group.connections.prepare(BindingKey("provider", KEY), wait_timeout=5)
                result = await asyncio.wait_for(call.acall("exercise", "provider"), 15)
                self.assertEqual(result, {"rpc": "direct+core", "stream": "received",
                                          "activity": "nymph-finished", "registration": "sealed"})
            finally:
                await runtime.stop()
            for context in contexts:
                self.check_sealed(context)
            for name in ("requester", "provider"):
                self.assertTrue(group.process(name).cleanup_confirmed)
            await asyncio.sleep(0)
            self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    def check_sealed(self, context):
        for register in (lambda: context.provide(KEY, {"late": lambda: None}),
                         lambda: context.provide_stream(KEY, "late", lambda: None),
                         lambda: context.provide_executor("late", lambda: None)):
            with self.assertRaises(ProtocolError):
                register()
