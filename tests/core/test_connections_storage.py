"""Connections, ModuleGroup and Runtime exercised against actual persisted files."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import (
    BindingKey, BindingState, ConnectionNotReadyError, ModuleAdvertisement,
    ModuleExecutionState, ModuleKind, ModuleSpec, RuntimeFailure, RuntimeState,
)
from nymph_toolkit.core import Connections, FileStore, ModuleGroup, Runtime, _storage_io
from tests.core.test_connected_group import KEY, SPEC, Module


class PersistedConnectionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ntk-connected-store-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.instances = []

    def make(self, provider_id="b", implementation_version="1"):
        owner = SimpleNamespace()
        owner.store = FileStore(self.base / "primary", self.base / "archive",
                                retention=timedelta(days=2), batch_size=100, flush_interval=60)
        owner.group = ModuleGroup()
        owner.connections = Connections(owner.group, owner.store)
        owner.modules = {}
        for name in ("a", provider_id, "e"):
            provider = name == provider_id
            module = owner.modules[name] = Module(name, owner, provider=provider)
            owner.group.register(ModuleSpec(name, ModuleKind.SUBSYSTEM), module)
            owner.connections.declare(ModuleAdvertisement(name, implementation_version, (SPEC,) if provider else ()),
                                      {KEY: {"echo": module.echo}} if provider else None)
        owner.group.attach_connections(owner.connections)
        owner.runtime = Runtime(owner.group)
        self.instances.append(owner)
        return owner

    async def asyncTearDown(self):
        for owner in self.instances:
            try:
                await owner.runtime.stop()
            except RuntimeFailure:
                pass
        leaked = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()
                  and not t.done() and t.get_name().startswith("ntk-")]
        self.assertEqual(leaked, [])

    async def wait(self, event):
        await asyncio.wait_for(event.wait(), 5)

    def history(self):
        return [json.loads(line) for path in sorted((self.base / "primary").glob("history-*.jsonl"))
                for line in path.read_text(encoding="utf-8").splitlines()]

    async def test_restart_reuses_contract_despite_implementation_version_and_old_stopped_history(self):
        first = self.make()
        await first.runtime.start()
        binding = await first.connections.bind("a", KEY, "b", wait_timeout=5)
        first.modules["a"].trigger.set()
        await self.wait(first.modules["a"].progressed)
        await first.runtime.stop()
        self.assertEqual(first.modules["a"].results, ["activity"])
        self.assertTrue(any(e["kind"] == "usage" and e["data"]["module"]["state"] == "stopped"
                            for e in self.history()))
        second = self.make(implementation_version="99")
        await second.runtime.start()
        restored = second.connections.connection(binding.key)
        self.assertEqual(restored.state, BindingState.VALID)
        self.assertEqual(restored.provider_id, "b")
        second.modules["a"].trigger.set()
        await self.wait(second.modules["a"].progressed)
        self.assertEqual(second.modules["a"].results, ["activity"])
        await second.runtime.stop()
        self.assertEqual(len({e["run_id"] for e in self.history()}), 2)

    async def test_invalid_saved_provider_does_not_fail_start_and_new_demand_can_select(self):
        first = self.make()
        await first.runtime.start()
        await first.connections.bind("a", KEY, "b", wait_timeout=5)
        await first.runtime.stop()
        second = self.make(provider_id="f")
        await second.runtime.start()
        self.assertEqual(await second.store.load_bindings(), ())
        new = await second.connections.bind("a", KEY, "f", wait_timeout=5)
        self.assertEqual(new.provider_id, "f")
        self.assertEqual(await second.connections.invoke(new.key, "echo", wait_timeout=0, args=("fresh",)), "fresh")

    async def test_cooperative_interruption_and_new_request_recovery_are_persisted(self):
        owner = self.make()
        await owner.runtime.start()
        await owner.connections.bind("a", KEY, "b", wait_timeout=5)
        a, b, e = (owner.modules[name] for name in ("a", "b", "e"))
        b.bad_link = True
        a.trigger.set()
        await self.wait(a.interrupted)
        self.assertEqual(owner.connections.module_state("a"), ModuleExecutionState.INTERRUPTING)
        e.trigger.set()
        await self.wait(e.progressed)
        a.cleanup.set()
        await self.wait(a.completed_cleanup)
        b.bad_link = False
        b.publish()
        await owner.connections.health_check(module_ids=("b",))
        self.assertEqual(len(a.results), 1)
        a.progressed.clear()
        a.trigger.set()
        await self.wait(a.progressed)
        self.assertEqual(a.results[1:], ["activity"])
        await owner.runtime.stop()
        kinds = [e["kind"] for e in self.history()]
        for kind in ("binding_created", "link_error", "interruption_completed", "health_requested", "health_completed"):
            self.assertIn(kind, kinds)
        sequences = [e["sequence"] for e in self.history()]
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))

    async def test_configuration_rescue_pauses_existing_operations_then_resumes(self):
        owner = self.make()
        await owner.runtime.start()
        key = (await owner.connections.bind("a", KEY, "b", wait_timeout=5)).key
        handle = await owner.connections.prepare(key, wait_timeout=0)
        event = {"format": "ntk.history.v1", "run_id": "a" * 32, "sequence": 1,
                 "at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(), "kind": "old", "data": {}}
        batch = owner.store._disk.history_batch((event,))
        batch.write()
        old = next(iter(batch.protected))
        original_save, original_archive = owner.store._disk.save_bindings, owner.store._disk.archive_old
        entered, release = threading.Event(), threading.Event()
        def full(records):
            if old.exists():
                raise OSError("primary full")
            original_save(records)
        def hold(*args):
            entered.set()
            if not release.wait(5):
                raise OSError("test gate timed out")
            return original_archive(*args)
        with patch.object(owner.store._disk, "save_bindings", side_effect=full), \
             patch.object(owner.store._disk, "archive_old", side_effect=hold):
            adding = asyncio.create_task(owner.connections.bind("e", KEY, "b", wait_timeout=5))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                with self.assertRaises(ConnectionNotReadyError):
                    handle.call("echo", "not admitted")
                waiting = asyncio.create_task(owner.connections.invoke(key, "echo", wait_timeout=5, args=("after rescue",)))
                await asyncio.sleep(0)
                self.assertFalse(waiting.done())
            finally:
                release.set()
            await adding
            self.assertEqual(await waiting, "after rescue")
        self.assertEqual(len(await owner.store.load_bindings()), 2)
        self.assertFalse(old.exists())

    async def test_real_unrecoverable_history_error_stops_runtime_without_buffer_export(self):
        owner = self.make()
        await owner.runtime.start()
        await owner.connections.bind("a", KEY, "b", wait_timeout=5)
        with patch.object(_storage_io, "_append", side_effect=OSError("disk unavailable")) as writes:
            flushing = asyncio.create_task(owner.store.flush())
            await asyncio.wait_for(owner.store.wait_failure(), 5)
            with self.assertRaises(RuntimeFailure):
                await asyncio.wait_for(owner.runtime.wait(), 5)
            result = await asyncio.gather(flushing, return_exceptions=True)
            self.assertIs(result[0], owner.store.failure)
            self.assertEqual(writes.call_count, 2)
        self.assertEqual(owner.runtime.state, RuntimeState.FAILED)
        self.assertTrue(all(module.stopped for module in owner.modules.values()))
        self.assertGreater(owner.store.failure.unsaved_events, 0)
        self.assertFalse(owner.store._disk.archive.exists())


if __name__ == "__main__":
    unittest.main()
