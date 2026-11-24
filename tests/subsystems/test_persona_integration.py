"""B07 real public Core routes, process placements, capacity and uncertainty."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from pathlib import Path
import sqlite3
import tempfile
import unittest

from examples.persona_demo import group_at
from examples.persona_requester import CONTROL_KEY, update_request
from nymph_toolkit.contracts import (
    BindingKey, ConnectionsStateError, LinkFailure, OutcomeUnknown, PeerClosed, Placement, RemoteError,
    TemporaryUnavailable,
)
from nymph_toolkit.contracts.persona import PERSONA_KEY
from nymph_toolkit.core import Runtime
from nymph_toolkit.subsystems import persona


class PersonaIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_placements_both_routes_and_restart(self):
        for requester in Placement:
            for provider in Placement:
                with self.subTest(requester=requester, provider=provider), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    first = None
                    for restored in (False, True):
                        group = group_at(root, requester_placement=requester, persona_placement=provider)
                        runtime = Runtime(group)
                        await runtime.start()
                        try:
                            await group.connections.bind("persona", CONTROL_KEY, "nymph", wait_timeout=5)
                            call = await group.connections.prepare(BindingKey("persona", CONTROL_KEY), wait_timeout=5)
                            result = await asyncio.wait_for(call.acall("exercise", restored), 45)
                            self.assertIsInstance(result, dict, repr(result))
                            self.assertEqual(result["updates"], 2)
                            self.assertEqual(result["current"]["traits"], {"curiosity": 600, "sociability": 350})
                            if restored: self.assertEqual(result["receipt"], first)
                            first = result["receipt"]
                        finally:
                            await runtime.stop()
                        for name in ("persona", "nymph"):
                            self.assertTrue(group.process(name).cleanup_confirmed)
                    await asyncio.sleep(0)
                    self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    async def test_busy_and_unknown_result_are_not_retried(self):
        for provider in Placement:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                group = group_at(root, persona_placement=provider)
                runtime = Runtime(group)
                await runtime.start()
                lock = sqlite3.connect(root / "persona.sqlite3", isolation_level=None)
                link = unlock = pending = None
                try:
                    core = group.client("nymph")
                    await core.bind(PERSONA_KEY, "persona", timeout=5)
                    link = await core.prepare(PERSONA_KEY, timeout=5)
                    lock.execute("BEGIN IMMEDIATE")
                    pending = asyncio.create_task(link.acall("apply", update_request(), timeout=.2))
                    async def unlock_later():
                        # Let the caller's deadline expire, but release before
                        # SQLite's 1s busy timeout. Cancel does not roll back.
                        await asyncio.sleep(.35)
                        lock.rollback()
                    unlock = asyncio.create_task(unlock_later())
                    async with asyncio.timeout(3):
                        while not (await core.candidates(PERSONA_KEY))[0].contract_usage.active:
                            await asyncio.sleep(.005)
                    self.assertIsInstance(await link.acall("get", timeout=5), TemporaryUnavailable)
                    if provider == Placement.LOCAL:
                        with self.assertRaises(TimeoutError): await pending
                    else:
                        with self.assertRaises(OutcomeUnknown) as captured: await pending
                        async with asyncio.timeout(5):
                            while True:
                                try:
                                    link.result(captured.exception.request_id)
                                    self.fail("The deadline cancelled the remote handler")
                                except OutcomeUnknown: await asyncio.sleep(.005)
                                except RemoteError as error:
                                    self.assertEqual(error.remote_type, "CancelledError")
                                    break
                        link.release(captured.exception.request_id)
                    await unlock
                    receipt = await core.invoke(PERSONA_KEY, "get_update", "experience-1", timeout=5)
                    self.assertEqual(receipt["revision"], 1)
                    self.assertEqual(len((await link.acall("history", timeout=5))["updates"]), 1)
                finally:
                    if unlock is not None: await unlock
                    if pending is not None: await asyncio.gather(pending, return_exceptions=True)
                    lock.close()
                    if link is not None: await link.close()
                    await runtime.stop()

    async def test_runtime_stop_waits_for_admitted_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = group_at(root)
            runtime = Runtime(group)
            await runtime.start()
            lock = sqlite3.connect(root / "persona.sqlite3", isolation_level=None)
            pending = stopping = None
            try:
                core = group.client("nymph")
                await core.bind(PERSONA_KEY, "persona", timeout=5)
                link = await core.prepare(PERSONA_KEY, timeout=5)
                lock.execute("BEGIN IMMEDIATE")
                pending = asyncio.create_task(link.acall("apply", update_request(), timeout=5))
                async with asyncio.timeout(3):
                    while not (await core.candidates(PERSONA_KEY))[0].contract_usage.active:
                        await asyncio.sleep(.005)
                stopping = asyncio.create_task(runtime.stop())
                await asyncio.sleep(.05)
                self.assertFalse(stopping.done())
                lock.rollback()
                results = await asyncio.gather(pending, stopping, return_exceptions=True)
                self.assertIsNone(results[1])
                self.assertIsInstance(results[0], (dict, ConnectionsStateError, PeerClosed, LinkFailure))
            finally:
                lock.close()
                await runtime.stop()
                await asyncio.gather(*(t for t in (pending, stopping) if t), return_exceptions=True)
            self.assertTrue(group.process("persona").cleanup_confirmed)
            restarted = group_at(root)
            again = Runtime(restarted)
            await again.start()
            try:
                core = restarted.client("nymph")
                await core.bind(PERSONA_KEY, "persona", timeout=5)
                receipt = await core.invoke(PERSONA_KEY, "get_update", "experience-1", timeout=5)
                self.assertEqual(receipt["revision"], 1)
            finally:
                await again.stop()

    def test_persona_uses_only_public_ntk_contracts(self):
        root = Path(persona.__file__).parent
        for file in root.glob("*.py"):
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("nymph_toolkit"):
                    self.assertTrue(node.module == "nymph_toolkit.contracts" or node.module.startswith("nymph_toolkit.contracts."), file)
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.startswith("nymph_toolkit") for alias in node.names), file)
