"""B04 adapter admission, public-contract boundaries and cooperative ownership."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

from nymph_toolkit.adapters import _interaction
from nymph_toolkit.adapters.text_interaction import factory
from nymph_toolkit.contracts import (
    BindingKey, LinkFailure, OperatingState, OperationFailure, OutcomeUnknown,
    ProtocolError, TemporaryUnavailable, Usage,
)
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.contracts.text_interaction import TEXT_INTERACTION_KEY


class FakeLink:
    def __init__(self, owner, key):
        self.owner, self.key = owner, key
        self.closed = False

    async def acall(self, operation, *args, **kwargs):
        self.owner.calls.append((self.key, operation, args, kwargs))
        self.owner.entered.set()
        if self.owner.wait is not None:
            await self.owner.wait.wait()
        if isinstance(self.owner.result, BaseException):
            raise self.owner.result
        return self.owner.result

    async def close(self):
        self.closed = True


class FakeCore:
    def __init__(self):
        self.calls, self.bindings, self.links, self.health, self.acks, self.usages = [], [], [], [], [], []
        self.result, self.wait = {"ok":True}, None
        self.entered = asyncio.Event()
        self.available = True
        self.recovery_error = self.reporting_error = None

    async def publish_usage(self, usage, **kwargs):
        self.usages.append(usage.active)
        if usage.active == 0 and self.reporting_error is not None:
            raise self.reporting_error

    async def candidates(self, key, **kwargs):
        contract = {c.key:c for c in (MEMORY_CONTRACT, COGNITION_CONTRACT, COGNITION_REVISION_CONTRACT)}[key]
        usage = Usage(OperatingState.RUNNING, True, 0 if self.available else 1, 1)
        return [SimpleNamespace(advertisement=SimpleNamespace(module_id="memory" if key == MEMORY_CONTRACT.key else "cognition", contracts=(contract,)), module_usage=usage, contract_usage=usage)]

    async def bind(self, key, provider, **kwargs): self.bindings.append((key,provider))
    async def prepare(self, key, **kwargs):
        link = FakeLink(self,key); self.links.append(link); return link
    async def acknowledge_interruption(self, value, **kwargs): self.acks.append(value)
    async def health_check(self, *, module_ids, **kwargs):
        self.health.append(module_ids)
        if self.recovery_error is not None: raise self.recovery_error


class TextAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.core = FakeCore()
        self.provided = {}
        context = SimpleNamespace(core=self.core, settings=SimpleNamespace(max_frame_bytes=65536),
                                  provide=lambda k,h: self.provided.update({k:h}))
        self.adapter = factory(context, dict(memory_module_id="memory",cognition_module_id="cognition"))
        await self.adapter.start()
        self.addAsyncCleanup(self.adapter.stop)

    async def test_contracts_forwarding_validation_and_connection_reuse(self):
        self.assertEqual(set(self.provided[TEXT_INTERACTION_KEY]), {"observe","learn","inspect","correct","get_revision"})
        await self.adapter.observe({"sample":"detached"})
        await self.adapter.learn("one",tokens=["猫"],concepts=[])
        await self.adapter.inspect("猫")
        await self.adapter.correct("one",command_id="fix",expected_revision=0,tokens=["猫"],concepts=["animal"])
        await self.adapter.get_revision("one")
        self.assertEqual([(c[0],c[1]) for c in self.core.calls], [(MEMORY_CONTRACT.key,"put"),(COGNITION_CONTRACT.key,"learn"),(COGNITION_CONTRACT.key,"inspect"),(COGNITION_REVISION_CONTRACT.key,"correct"),(COGNITION_REVISION_CONTRACT.key,"get_revision")])
        self.assertEqual(len(self.core.bindings),3)
        for invalid in (("猫",), [float("nan")], [object()]):
            self.assertEqual((await self.adapter.learn("one",tokens=invalid,concepts=[])).code,"text.invalid")
        self.core.result = OperationFailure("memory.invalid","fixture")
        self.assertEqual(await self.adapter.observe({}), self.core.result)
        self.assertEqual(len(self.core.bindings),3)

    async def test_snapshot_busy_cancel_and_stop_drain_the_admitted_call(self):
        self.core.wait = asyncio.Event()
        value = {"content":["original"]}
        task = asyncio.create_task(self.adapter.observe(value))
        await self.core.entered.wait()
        value["content"][0] = "mutated"
        self.assertEqual(self.core.calls[0][2], ({"content":["original"]},))
        self.assertIsInstance(await self.adapter.inspect("猫"),TemporaryUnavailable)
        task.cancel()
        stop = asyncio.create_task(self.adapter.stop())
        await asyncio.sleep(0)
        self.assertFalse(task.done()); self.assertFalse(stop.done())
        self.core.wait.set()
        with self.assertRaises(asyncio.CancelledError): await task
        await stop
        self.assertTrue(all(link.closed for link in self.core.links))
        self.assertIsInstance(await self.adapter.observe({}),TemporaryUnavailable)
        self.assertFalse(self.adapter.busy)

    async def test_link_failure_ack_health_explicit_new_request_no_retry(self):
        self.core.result = LinkFailure(BindingKey("text",MEMORY_CONTRACT.key), "broken", "interrupted")
        result = await self.adapter.observe({})
        self.assertIsInstance(result,LinkFailure)
        self.assertEqual(len(self.core.calls),1)
        self.assertEqual(self.core.acks,["interrupted"])
        self.assertEqual(self.core.health,[("memory",)])
        self.assertTrue(self.core.links[0].closed)
        self.core.result = {"ok":True}
        self.assertEqual(await self.adapter.observe({}),{"ok":True})
        self.assertEqual(len(self.core.bindings),1)
        self.assertEqual(len(self.core.links),2)

    async def test_unknown_outcome_survives_health_and_reporting_failures(self):
        # Constructor uses the public RPC outcome fields; the exact exception stays primary.
        unknown = OutcomeUnknown("pending-command")
        self.core.result = unknown
        self.core.recovery_error = ProtocolError("health unavailable")
        self.core.reporting_error = ProtocolError("report unavailable")
        with self.assertRaises(OutcomeUnknown) as caught: await self.adapter.observe({})
        self.assertIs(caught.exception,unknown)
        self.assertEqual(len(self.core.calls),1)
        self.assertTrue(self.core.links[0].closed)
        self.assertFalse(self.adapter.busy)

    async def test_capacity_does_not_bind_or_choose_a_different_provider(self):
        self.core.available = False
        self.assertIsInstance(await self.adapter.observe({}),TemporaryUnavailable)
        self.assertEqual(self.core.bindings,[])
        self.assertEqual(self.core.calls,[])

    def test_new_adapters_do_not_import_core_or_subsystem_internals(self):
        root = Path(_interaction.__file__).parent
        for path in [root/"_interaction.py", * (root/"text_interaction").glob("*.py"), * (root/"web").glob("*.py")]:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ""] if isinstance(node,ast.ImportFrom) else []
                for name in names:
                    if name.startswith("nymph_toolkit."):
                        self.assertTrue(name.startswith("nymph_toolkit.contracts"), (path,name))
