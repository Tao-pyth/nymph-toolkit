"""B09 public evidence reads, rejection, cooperative shutdown and uncertainty."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from nymph_toolkit.contracts import BindingKey, LinkFailure, OperatingState, OutcomeUnknown, ProtocolError, TemporaryUnavailable, Usage
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT, COGNITION_REVISION_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT, PERSONA_KEY
from nymph_toolkit.subsystems.sleep import factory
from tests.subsystems.test_sleep import cycle, experience, identity, traits


class Link:
    def __init__(self, core, key):
        self.core, self.key, self.closed = core, key, False

    async def acall(self, operation, *args, **kwargs):
        self.core.calls.append((self.key, operation, args))
        if self.key == MEMORY_KEY:
            result = self.core.record
        elif self.key == COGNITION_REVISION_KEY:
            if self.core.mutate_memory:
                self.core.record["content"] = "altered after the read"
            result = self.core.annotation
        else:
            self.core.entered.set()
            if self.core.wait is not None: await self.core.wait.wait()
            result = self.core.persona
        if isinstance(result, BaseException): raise result
        return result

    async def close(self):
        self.closed = True


class Core:
    def __init__(self):
        self.record, self.annotation = experience()
        self.persona = traits()
        self.bindings, self.calls, self.links, self.health, self.acks, self.usages = [], [], [], [], [], []
        self.entered, self.wait = asyncio.Event(), None
        self.available = True
        self.mutate_memory = False
        self.recovery_error = None

    async def publish_usage(self, usage, **kwargs): self.usages.append(usage)

    async def candidates(self, key, **kwargs):
        contract, name = {MEMORY_KEY: (MEMORY_CONTRACT, "memory"), COGNITION_REVISION_KEY: (COGNITION_REVISION_CONTRACT, "cognition"),
                          PERSONA_KEY: (PERSONA_CONTRACT, "persona")}[key]
        usage = Usage(OperatingState.RUNNING, True, 0 if self.available else 1, 1)
        return [SimpleNamespace(advertisement=SimpleNamespace(module_id=name, contracts=(contract,)), module_usage=usage, contract_usage=usage)]

    async def bind(self, key, provider, **kwargs): self.bindings.append((key, provider))

    async def prepare(self, key, **kwargs):
        link = Link(self, key); self.links.append(link); return link

    async def acknowledge_interruption(self, key, **kwargs): self.acks.append(key)

    async def health_check(self, *, module_ids, **kwargs):
        self.health.append(module_ids)
        if self.recovery_error is not None: raise self.recovery_error


class SleepServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.core = Core()
        self.config = {k: v for k, v in identity().items() if k != "module_id"}
        self.config["path"] = str(Path(self.temp.name).resolve() / "sleep.db")
        self.context = SimpleNamespace(module_id="sleep", core=self.core, settings=SimpleNamespace(max_frame_bytes=65536), provide=lambda k, v: None)
        self.service = factory(self.context, self.config)
        await self.service.start(); self.addAsyncCleanup(self.service.stop)

    async def test_read_only_connections_fixed_and_replay_without_new_observation(self):
        first = await self.service.cycle(cycle())
        self.assertEqual(first["persona_proposal"]["deltas"], {"curiosity": 3})
        calls = list(self.core.calls)
        self.core.persona = ProtocolError("offline")
        self.assertEqual(await self.service.cycle(cycle()), first)
        self.assertEqual(await self.service.get("one"), first)
        self.assertEqual(self.core.calls, calls)
        self.core.persona = traits()
        second = await self.service.cycle(cycle("next", 1))
        self.assertIsNone(second["persona_proposal"])
        self.assertEqual(len(self.core.bindings), 3)
        self.assertEqual({operation for _, operation, _ in self.core.calls}, {"get", "get_revision"})
        self.assertEqual((await self.service.inspect("explore"))["strength"], 1000)

    async def test_local_memory_result_is_copied_before_cognition_await(self):
        self.core.mutate_memory = True
        result = await self.service.cycle(cycle())
        self.assertEqual(result["revision"], 1)
        self.assertEqual((await self.service.state())["entries"][0]["tokens"], ["猫", "は", "眠る"])

    async def test_malformed_sources_input_and_current_traits_preserve_state(self):
        for target, bad in (("record", {}), ("annotation", {}), ("persona", {}), ("persona", traits(curiosity=True))):
            self.core.record, self.core.annotation = experience(); self.core.persona = traits()
            setattr(self.core, target, bad)
            self.assertEqual((await self.service.cycle(cycle())) .code, "sleep.evidence")
            self.assertEqual((await self.service.state())["revision"], 0)
        self.assertEqual((await self.service.cycle({})).code, "sleep.invalid")
        self.assertEqual((await self.service.state(after=True)).code, "sleep.invalid")
        self.assertEqual((await self.service.inspect("bad token")).code, "sleep.invalid")
        self.assertEqual((await self.service.inspect("label", source_kind=[])).code, "sleep.invalid")
        self.assertEqual((await self.service.get(" ")).code, "sleep.invalid")

    async def test_capacity_is_not_health_failure_and_link_failure_is_not_retried(self):
        self.core.available = False
        self.assertIsInstance(await self.service.cycle(cycle()), TemporaryUnavailable)
        self.assertEqual(self.core.calls, []); self.assertEqual(self.core.health, [])
        self.core.available = True
        self.core.persona = TemporaryUnavailable("busy")
        self.assertIsInstance(await self.service.cycle(cycle()), TemporaryUnavailable)
        self.assertEqual(self.core.health, [])
        self.core.persona = LinkFailure(BindingKey("sleep", PERSONA_KEY), "failed", "interrupted")
        self.assertIsInstance(await self.service.cycle(cycle()), LinkFailure)
        self.assertEqual(self.core.acks, ["interrupted"]); self.assertEqual(self.core.health, [("persona",)])
        self.assertTrue(next(l for l in self.core.links if l.key == PERSONA_KEY).closed)
        self.assertEqual((await self.service.state())["revision"], 0)

    async def test_unknown_read_preserved_over_recovery_error(self):
        error = OutcomeUnknown("pending-read"); self.core.persona = error
        self.core.recovery_error = ProtocolError("health failed")
        with self.assertRaises(OutcomeUnknown) as caught: await self.service.cycle(cycle())
        self.assertIs(caught.exception, error)
        self.assertEqual([o for k, o, _ in self.core.calls if k == PERSONA_KEY], ["get"])
        self.assertEqual((await self.service.get("one")).code, "sleep.not_found")

    async def test_cancel_and_stop_wait_for_admitted_cycle_and_worker(self):
        self.core.wait = asyncio.Event()
        pending = asyncio.create_task(self.service.cycle(cycle()))
        await asyncio.wait_for(self.core.entered.wait(), 5)
        self.assertIsInstance(await self.service.state(), TemporaryUnavailable)
        pending.cancel(); stopping = asyncio.create_task(self.service.stop()); await asyncio.sleep(0)
        self.assertFalse(pending.done()); self.assertFalse(stopping.done())
        self.core.wait.set()
        with self.assertRaises(asyncio.CancelledError): await pending
        await stopping
        self.assertIsNone(self.service.pool); self.assertTrue(all(l.closed for l in self.core.links))
        restored = factory(self.context, self.config); await restored.start()
        try:
            self.assertEqual((await restored.get("one"))["revision"], 1)
            self.assertEqual((await restored.state())["revision"], 1)
        finally: await restored.stop()

    async def test_configuration_is_detached_and_changed_configuration_refuses_restart(self):
        self.config["trait_rules"][0]["delta"] = 5
        self.assertEqual((await self.service.cycle(cycle()))["persona_proposal"]["deltas"], {"curiosity": 3})
        await self.service.stop()
        before = Path(self.config["path"]).read_bytes()
        restored = factory(self.context, self.config)
        with self.assertRaises(ValueError): await restored.start()
        self.assertIsNone(restored.pool)
        self.assertEqual(Path(self.config["path"]).read_bytes(), before)
