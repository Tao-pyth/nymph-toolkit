"""A08 race boundaries use barriers and real channels, not inferred success."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import replace
from datetime import timedelta
import unittest

from nymph_toolkit.contracts import (
    ActivityChange, ActivityCommandStatus, ActivityState, OutcomeUnknown, OverflowPolicy,
    Placement, RemoteError, StreamOptions, StreamState, TemporaryUnavailable,
)
from nymph_toolkit.core._wire import VERSION, read_frame, write_frame
from tests.core import test_hybrid_transport as rpc_baseline
from tests.core import test_v08_integration as baseline
from tests.doubles.scenario import KEY, invoke, make_group, until


class ContentionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.IntegrationTests.asyncSetUp
    asyncTearDown = baseline.IntegrationTests.asyncTearDown
    create = baseline.IntegrationTests.create
    request = baseline.IntegrationTests.request

    async def test_capacity_cancel_and_new_calls_keep_control_available(self):
        group, runtime, _ = self.create()
        group.settings = replace(group.settings, max_requests=2)
        await runtime.start()
        await invoke(group, "requester", "connect", "provider")
        link = group.modules["requester"].node.service.link
        first = asyncio.create_task(link.acall("echo", {"wait": True, "id": 1}, timeout=5))
        second = asyncio.create_task(link.acall("echo", {"wait": True, "id": 2}, timeout=5))
        async with asyncio.timeout(5):
            while (await group.diagnostics("provider"))["active_calls"] != 2:
                await asyncio.sleep(.005)
        rejected = await link.acall("echo", "excess", timeout=1)
        self.assertIsInstance(rejected, TemporaryUnavailable)
        self.assertEqual(len(await group.client("requester").candidates(KEY, timeout=1)), 2)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        await asyncio.wait_for(asyncio.shield(link._peer._pending[1]), 3)
        with self.assertRaises(RemoteError):
            link.result(1)
        link.release(1)
        self.assertEqual((await link.acall("echo", "next", timeout=2))["value"], "next")
        await invoke(group, "provider", "gate", "echo")
        self.assertEqual((await second)["value"]["id"], 2)
        self.assertFalse(link._peer._pending)
        self.assertEqual((await invoke(group, "provider", "metrics"))["calls"], 3)
        self.assertEqual(group.connections.module_state("requester").value, "running")

    async def test_stream_pressure_drop_cancel_close_and_activity_change(self):
        group, runtime, _ = self.create()
        await runtime.start()
        await invoke(group, "requester", "connect", "provider")
        link = group.modules["requester"].node.service.link
        wait = await link.open_stream("stream", StreamOptions(4, 1, 4, 1, OverflowPolicy.WAIT),
                                      {"id": "wait", "hold": True}, timeout=3)
        drop = await link.open_stream("stream", StreamOptions(4, 1, 4, 1, OverflowPolicy.DROP_OLDEST),
                                      {"id": "drop", "hold": True}, timeout=3)
        await wait.send(b"1111", timeout=1)
        async with asyncio.timeout(3):
            while not any(s["buffered_bytes"] == 4 for s in (await group.diagnostics("provider"))["streams"]):
                await asyncio.sleep(.005)
        await wait.send(b"2222", timeout=1)
        pending = asyncio.create_task(wait.send(b"3333", timeout=3))
        await asyncio.sleep(0)
        self.assertFalse(pending.done())
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        for _ in range(20):
            await drop.send(b"xxxx", timeout=1)
        with self.assertRaises(TimeoutError):
            await wait.close(timeout=.02)
        self.assertEqual(wait.state, StreamState.CLOSING)
        manager, request = group.activities, self.request()
        manager.submit_remote(request, "provider", "work")
        await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
        before = manager.snapshot(request.key)
        changed = manager.change(request.key, ActivityChange(priority=7, duration=timedelta(seconds=60)),
                                 command_id="during-pressure", expected_revision=before.revision)
        self.assertEqual(changed.status, ActivityCommandStatus.APPLIED)
        self.assertEqual(len(await group.client("requester").candidates(KEY, timeout=1)), 2)
        await invoke(group, "provider", "gate", "stream")
        await asyncio.gather(wait.close(timeout=3), drop.close(timeout=3))
        normal = await link.acall("stream_result", "wait", timeout=3)
        dropped = await link.acall("stream_result", "drop", timeout=3)
        self.assertEqual((normal["chunks"], normal["bytes"], normal["missing"]), (2, 8, 0))
        self.assertEqual(dropped["chunks"] + dropped["missing"], 20)
        self.assertGreater(dropped["missing"], 0)
        self.assertEqual((wait.state, drop.state), (StreamState.CLOSED, StreamState.CLOSED))
        manager.request_finish(request.key)
        await asyncio.wait_for(manager.wait(request.key), 3)

    async def test_restarted_binding_rejects_old_handshake_without_changing_live_target(self):
        group, runtime, root = self.create()
        await runtime.start()
        await invoke(group, "requester", "connect", "provider")
        old = dict(group.modules["requester"].node.service.link.route)
        await runtime.stop()
        next_group, next_runtime = make_group(root)
        self.runs.append((next_group, next_runtime))
        await next_runtime.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", next_group.modules["provider"].port)
        try:
            await write_frame(writer, {"version": VERSION, "generation": old["generation"],
                                      "token": old["token"], "kind": "rpc"}, 65536)
            response = await asyncio.wait_for(read_frame(reader, 65536), 3)
            self.assertNotEqual(response, {"ready": True})
        finally:
            writer.close()
            await writer.wait_closed()
        await invoke(next_group, "requester", "connect", "provider")
        self.assertEqual(len(await invoke(next_group, "requester", "batch", 1)), 1)
        self.assertEqual(next_runtime.state.value, "running")
        self.assertFalse(next_group.activities._activities)

    async def test_revision_and_idempotency_with_pause_report_racing_shutdown(self):
        for provider in Placement:
            with self.subTest(provider=provider):
                group, runtime, _ = self.create(provider=provider)
                await runtime.start()
                manager, request = group.activities, self.request()
                manager.submit_remote(request, "provider", "work")
                await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
                before = manager.snapshot(request.key)
                change = ActivityChange(priority=4)
                applied = manager.change(request.key, change, command_id="one", expected_revision=before.revision)
                self.assertEqual(manager.change(request.key, change, command_id="one", expected_revision=before.revision), applied)
                rejected = manager.change(request.key, ActivityChange(priority=9), command_id="two", expected_revision=before.revision)
                self.assertEqual(rejected.reason, "revision_conflict")
                arrived, release = asyncio.Event(), asyncio.Event()
                original = manager._remote_event
                async def delayed(module_id, data):
                    if data["phase"] == "paused":
                        arrived.set()
                        await release.wait()
                    return await original(module_id, data)
                manager._remote_event = delayed
                manager.request_pause(request.key, command_id="pause", expected_revision=manager.snapshot(request.key).revision)
                await asyncio.wait_for(arrived.wait(), 3)
                stopping = asyncio.create_task(runtime.stop())
                await until(lambda: group._stopping)
                release.set()
                await asyncio.wait_for(stopping, 5)
                self.assertTrue(manager.command_result(request.key, "pause").status.terminal)
                self.assertTrue(manager.snapshot(request.key).state.terminal)
                self.assertEqual(manager._running_slots, 0)


class LateRpcTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = rpc_baseline.RpcTests.asyncSetUp
    asyncTearDown = rpc_baseline.RpcTests.asyncTearDown

    async def test_late_cancelled_result_is_not_delivered_to_next_request(self):
        entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = []
        async def handler(operation, payload):
            calls.append(payload)
            if payload == "old":
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    await release.wait()
            return payload
        self.peers[0].handler = handler
        with self.assertRaises(OutcomeUnknown) as failure:
            await self.client.call("echo", "old", timeout=.03)
        await asyncio.wait_for(cancelled.wait(), 1)
        self.assertEqual(await self.client.call("echo", "new", timeout=1), "new")
        release.set()
        request_id = failure.exception.request_id
        await asyncio.wait_for(asyncio.shield(self.client._pending[request_id]), 1)
        self.assertEqual(self.client.result(request_id), "old")
        self.client.release(request_id)
        self.assertEqual(calls, ["old", "new"])
        self.assertFalse(self.client._pending)
