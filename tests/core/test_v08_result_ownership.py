"""Regression #78: results remain observable and releasable after abandoned waits."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import OutcomeUnknown, PeerClosed, Placement, RemoteError
from nymph_toolkit.core._hybrid_client import CoreClient, DirectLink
from tests.core import test_hybrid_transport as rpc_baseline
from tests.core import test_v08_integration as baseline
from tests.doubles.scenario import invoke, until


class ResultOwnershipTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = rpc_baseline.RpcTests.asyncSetUp
    asyncTearDown = rpc_baseline.RpcTests.asyncTearDown

    async def test_unsent_deadlines_and_cancellations_do_not_exhaust_capacity(self):
        async with self.client._write_lock:
            for _ in range(20):
                with self.assertRaises(TimeoutError) as caught:
                    await self.client.call("echo", "not sent", timeout=.001)
                self.assertNotIsInstance(caught.exception, OutcomeUnknown)
                task = asyncio.create_task(self.client.call("echo", "cancel before send", timeout=2))
                await until(lambda: bool(self.client._pending))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertFalse(self.client._pending)
                self.assertFalse(self.client._auxiliary)
        self.assertEqual(self.peers[0]._received, 0)
        self.assertEqual(await self.client.call("echo", "next", timeout=2), "next")
        self.assertFalse(self.client._pending)

    async def test_write_started_before_drain_timeout_retains_uncertain_result(self):
        release = asyncio.Event()
        async def drain():
            await release.wait()
        with patch.object(self.client.writer, "drain", side_effect=drain):
            try:
                with self.assertRaises(OutcomeUnknown) as caught:
                    await self.client.call("wait", timeout=.03)
                identity = caught.exception.request_id
                self.assertIn(identity, self.client._pending)
                self.assertEqual(self.peers[0]._received, identity)
            finally:
                release.set()
        await until(lambda: self.client._pending[identity].done())
        with self.assertRaises(RemoteError):
            self.client.result(identity)
        self.client.release(identity)
        self.assertFalse(self.client._pending)

    async def test_internal_release_waits_for_result_or_disconnect(self):
        for disconnect in (False, True):
            entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
            async def handler(operation, payload):
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    await release.wait()
                return payload
            self.peers[0].handler = handler
            with self.assertRaises(OutcomeUnknown):
                await self.client.call("internal", timeout=.02, retain_result=False)
            await asyncio.wait_for(cancelled.wait(), 1)
            self.assertEqual(len(self.client._pending), 1)
            if disconnect:
                self.peers[0].writer.close()
            release.set()
            await until(lambda: not self.client._pending)

    async def test_cancelled_internal_wait_also_releases_only_after_completion(self):
        task = asyncio.create_task(self.client.call("wait", timeout=2, retain_result=False))
        await until(lambda: bool(self.peers[0]._incoming))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await until(lambda: not self.client._pending)

    async def test_public_ids_result_and_release_cover_late_error_and_disconnect(self):
        core = CoreClient(None, None)
        core._result_peer = self.client
        link = DirectLink(core, {})
        link._peer = self.client
        with self.assertRaises(OutcomeUnknown) as caught:
            await self.client.call("wait", timeout=.02)
        identity = caught.exception.request_id
        self.assertIn(identity, core.pending_requests)
        self.assertIn(identity, link.pending_requests)
        await until(lambda: self.client._pending[identity].done())
        with self.assertRaises(RemoteError):
            core.result(identity)
        core.release(identity)
        self.assertFalse(core.pending_requests)
        self.assertFalse(link.pending_requests)
        with self.assertRaises(KeyError):
            core.result(identity)
        task = asyncio.create_task(self.client.call("wait", timeout=2))
        await until(lambda: bool(core.pending_requests))
        identity = core.pending_requests[0]
        with self.assertRaises(OutcomeUnknown):
            core.release(identity)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await self.client.close()
        try:
            core.result(identity)
        except (PeerClosed, RemoteError):
            pass
        else:
            self.fail("Cancelled or disconnected call cannot succeed")
        core.release(identity)

    async def test_local_clients_have_no_rpc_results(self):
        core = CoreClient(None, None)
        link = DirectLink(core, {})
        for client in (core, link):
            self.assertEqual(client.pending_requests, ())
            for method in (client.result, client.release):
                with self.assertRaises(KeyError):
                    method(1)


class ManagementIntegrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.IntegrationTests.asyncSetUp
    asyncTearDown = baseline.IntegrationTests.asyncTearDown
    create = baseline.IntegrationTests.create

    async def test_child_can_release_repeated_management_timeouts_and_cancellation(self):
        group, runtime, _ = self.create(requester=Placement.PROCESS)
        group.modules["requester"].factory = "tests.doubles.management:factory"
        await runtime.start()
        result = await invoke(group, "requester", "echo", 20)
        self.assertEqual(result, {"released": 21, "pending": 0})
        self.assertTrue(await invoke(group, "requester", "connect", "provider"))
        self.assertEqual(len(await invoke(group, "requester", "batch", 3)), 3)
