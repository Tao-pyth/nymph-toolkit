"""Process exit racing kill must not skip monitoring or final history."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.core import FileStore
from nymph_toolkit.core.hybrid import _Service


class ExitsBeforeKill:
    """Control the OS exit notification independently of the kill attempt."""
    def __init__(self, error=ProcessLookupError):
        self.exited = asyncio.Event()
        self.returncode = None
        self.error = error

    async def wait(self):
        await self.exited.wait()
        self.returncode = 0
        return self.returncode

    def kill(self):
        if self.error is ProcessLookupError:
            self.exited.set()
        raise self.error("exit raced the termination request")


class ShutdownRaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = FileStore(self.root / "main", self.root / "archive",
                               retention=timedelta(days=1), batch_size=8, flush_interval=.01)
        await self.store.start()
        hub = SimpleNamespace(settings=HybridSettings(1, .01, 1, 65536, 8, 2),
                              connections=SimpleNamespace(store=self.store), activities=None, _stopping=True)
        self.service = _Service(hub, ModuleSpec("child", ModuleKind.SUBSYSTEM),
                                ModuleAdvertisement("child", "1", ()), "unused:factory", {}, Placement.PROCESS)
        self.service.process = ExitsBeforeKill()
        self.service.monitor = asyncio.create_task(self.service._watch_process())

    async def asyncTearDown(self):
        self.service.process.exited.set()
        await asyncio.gather(self.service.monitor, return_exceptions=True)
        await self.store.stop()

    async def verify_reaped_and_saved(self):
        self.assertTrue(self.service.monitor.done())
        self.service.monitor.result()
        self.assertEqual(self.service.snapshot.returncode, 0)
        self.assertEqual(self.service.snapshot.state, "stopped")
        self.assertFalse(self.service.snapshot.cleanup_confirmed)
        await self.store.stop()
        events = [json.loads(line) for path in (self.root / "main").rglob("*.jsonl")
                  for line in path.read_text(encoding="utf-8").splitlines()]
        final = [event["data"] for event in events if event["kind"] == "hybrid_process"][-1]
        self.assertEqual(final["state"], "stopped")
        self.assertEqual(final["returncode"], 0)
        self.assertFalse(final["cleanup_confirmed"])

    async def test_stop_reaps_exit_racing_kill_before_store_closes(self):
        await self.service.stop()
        await self.verify_reaped_and_saved()

    async def test_guardian_accepts_already_exited_child_and_stop_saves_final_state(self):
        await self.service.force_after_deadline()
        await self.service.stop()
        await self.verify_reaped_and_saved()

    async def test_other_termination_error_is_not_hidden(self):
        self.service.process.error = PermissionError
        with self.assertRaises(PermissionError):
            await self.service.force_after_deadline()
