"""B09 real evidence providers, both Core routes, placements and saved outcomes."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from examples.sleep_demo import Calls, exercise, group_at
from nymph_toolkit.contracts import LinkFailure, OutcomeUnknown, Placement, RemoteError, TemporaryUnavailable
from nymph_toolkit.contracts.persona import PERSONA_KEY
from nymph_toolkit.contracts.sleep import SLEEP_KEY
from nymph_toolkit.core import Runtime
from nymph_toolkit.subsystems import sleep
from nymph_toolkit.subsystems.persona import _Persona


class SleepIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_provider_capacity_and_failure_do_not_commit_or_retry(self):
        for capacity in (True, False):
            calls = 0
            async def failing(provider):
                nonlocal calls
                calls += 1
                if capacity: return TemporaryUnavailable("Controlled capacity")
                raise RuntimeError("Controlled Persona failure")
            with self.subTest(capacity=capacity), patch.object(_Persona, "get", failing), tempfile.TemporaryDirectory() as directory:
                group = group_at(Path(directory).resolve(), providers=Placement.LOCAL)
                runtime = Runtime(group); call = Calls(group)
                await runtime.start()
                try:
                    await call.start()
                    result = await call(SLEEP_KEY, "cycle", dict(cycle_id="fault", expected_revision=0, record_ids=[]))
                    self.assertIsInstance(result, TemporaryUnavailable if capacity else LinkFailure)
                    self.assertEqual(calls, 1)
                    self.assertEqual((await call(SLEEP_KEY, "state"))["revision"], 0)
                    self.assertEqual((await call(SLEEP_KEY, "get", "fault")).code, "sleep.not_found")
                finally:
                    await call.close(); await runtime.stop()
                self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))

    async def test_four_placements_both_routes_evidence_expiry_proposal_and_restart(self):
        for own in Placement:
            for providers in Placement:
                for direct in (False, True):
                    with self.subTest(sleep=own, providers=providers, direct=direct), tempfile.TemporaryDirectory() as directory:
                        root, result = Path(directory).resolve(), None
                        for restored in (False, True):
                            group = group_at(root, sleep=own, providers=providers)
                            runtime = Runtime(group); call = Calls(group, direct=direct)
                            await runtime.start()
                            try:
                                await call.start()
                                if not restored:
                                    result = await exercise(call)
                                    self.assertEqual(result["final"]["revision"], 7)
                                else:
                                    self.assertEqual(await call(SLEEP_KEY, "state"), result["final"])
                                    self.assertEqual(await call(SLEEP_KEY, "get", "one"), result["first"])
                                    self.assertEqual((await call(PERSONA_KEY, "get"))["revision"], 1)
                            finally:
                                await call.close(); await runtime.stop()
                            self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))
                        await asyncio.sleep(0)
                        self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    async def test_cancelled_or_unknown_call_can_have_committed_cycle(self):
        for own in Placement:
            with self.subTest(sleep=own), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                group = group_at(root, sleep=own, providers=Placement.LOCAL)
                runtime = Runtime(group); call = Calls(group, direct=True)
                await runtime.start()
                lock = sqlite3.connect(root / "sleep.db", isolation_level=None)
                pending = unlock = None
                try:
                    await call.start(); link = call.links[SLEEP_KEY]
                    lock.execute("BEGIN IMMEDIATE")
                    pending = asyncio.create_task(link.acall("cycle", dict(cycle_id="uncertain", expected_revision=0, record_ids=[]), timeout=.2))
                    async def release_lock():
                        await asyncio.sleep(.4); lock.rollback()
                    unlock = asyncio.create_task(release_lock())
                    async with asyncio.timeout(3):
                        while not (await call.core.candidates(SLEEP_KEY))[0].contract_usage.active: await asyncio.sleep(.005)
                    self.assertIsInstance(await link.acall("state", timeout=5), TemporaryUnavailable)
                    if own == Placement.LOCAL:
                        with self.assertRaises(TimeoutError): await pending
                    else:
                        with self.assertRaises(OutcomeUnknown) as captured: await pending
                        async with asyncio.timeout(5):
                            while True:
                                try:
                                    link.result(captured.exception.request_id); self.fail("Remote handler was cancelled")
                                except OutcomeUnknown: await asyncio.sleep(.005)
                                except RemoteError as error:
                                    self.assertEqual(error.remote_type, "CancelledError"); break
                        link.release(captured.exception.request_id)
                    await unlock
                    async with asyncio.timeout(5):
                        while True:
                            receipt = await call(SLEEP_KEY, "get", "uncertain")
                            if not isinstance(receipt, TemporaryUnavailable): break
                            await asyncio.sleep(.005)
                    self.assertEqual(receipt["revision"], 1)
                    self.assertEqual((await call(SLEEP_KEY, "state"))["revision"], 1)
                finally:
                    if unlock is not None: await unlock
                    if pending is not None: await asyncio.gather(pending, return_exceptions=True)
                    lock.close(); await call.close(); await runtime.stop()
                self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))

    def test_only_public_ntk_contracts_are_imported_by_sleep(self):
        for file in Path(sleep.__file__).parent.glob("*.py"):
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("nymph_toolkit"):
                    self.assertTrue(node.module == "nymph_toolkit.contracts" or node.module.startswith("nymph_toolkit.contracts."), file)
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(n.name.startswith("nymph_toolkit") for n in node.names), file)
