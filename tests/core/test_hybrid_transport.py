"""Real loopback sockets exercise wire boundaries, cancellation and stream ownership."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
import unittest

from nymph_toolkit.contracts import (
    ActivityChange, ActivityKey, ActivityRequest, ChunkTooLarge, HybridSettings,
    OutcomeUnknown, OverflowPolicy, PeerClosed, ProtocolError, RemoteError,
    StreamOptions, StreamState, UNCHANGED,
)
from nymph_toolkit.core._rpc import RpcPeer
from nymph_toolkit.core._streams import StreamReceiver, StreamSender
from nymph_toolkit.core._wire import decode, encode, json_value, read_frame, write_frame

SETTINGS = HybridSettings(5, 2, 2, 65536, 16, 4)


class WireTests(unittest.TestCase):
    def test_contract_roundtrip_and_unchanged_are_not_arbitrary_imports(self):
        request = ActivityRequest(ActivityKey("a", "b"), "work", datetime.now(timezone.utc), timedelta(seconds=1))
        self.assertEqual(decode(encode(request)), request)
        change = decode(encode(ActivityChange(priority=3)))
        self.assertIs(change.start_at, UNCHANGED)
        self.assertEqual(change.priority, 3)
        self.assertEqual(decode(encode({"$type": "user data"})), {"$type": "user data"})
        with self.assertRaises(ProtocolError):
            decode({"$type": "subprocess.Popen", "fields": {}})

    def test_settings_and_application_values(self):
        for value in (0, -1, True, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                HybridSettings(value, 1, 1, 1024, 1, 1)
        for value in (b"bytes", object(), {1: "key"}, float("nan")):
            with self.assertRaises(ProtocolError):
                json_value(value)
        self.assertEqual(json_value({"a": [1, None]}), {"a": [1, None]})


class RpcTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.peers = []
        self.connected = asyncio.Event()
        self.cancelled = asyncio.Event()
        async def handler(operation, payload):
            if operation == "wait":
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled.set()
            if operation == "fail":
                raise ValueError("provider failure")
            return payload
        self.handler = handler
        def accept(reader, writer):
            self.peers.append(RpcPeer(reader, writer, generation="run", module_id="server", settings=SETTINGS, handler=handler))
            self.connected.set()
        self.server = await asyncio.start_server(accept, "127.0.0.1", 0)
        self.address = self.server.sockets[0].getsockname()
        reader, writer = await asyncio.open_connection(*self.address)
        self.client = RpcPeer(reader, writer, generation="run", module_id="client", settings=SETTINGS, handler=handler)
        self.peers.append(self.client)
        await self.connected.wait()

    async def asyncTearDown(self):
        self.server.close()
        await asyncio.gather(*(peer.close() for peer in self.peers))
        await self.server.wait_closed()

    async def test_concurrent_requests_results_and_remote_exception(self):
        values = await asyncio.gather(*(self.client.call("echo", n, timeout=1) for n in range(12)))
        self.assertEqual(values, list(range(12)))
        with self.assertRaises(RemoteError) as caught:
            await self.client.call("fail", timeout=1)
        self.assertEqual(caught.exception.remote_type, "ValueError")

    async def test_deadline_cancels_cooperatively_and_retains_late_result(self):
        with self.assertRaises(OutcomeUnknown) as caught:
            await self.client.call("wait", timeout=.03)
        await asyncio.wait_for(self.cancelled.wait(), 1)
        request_id = caught.exception.request_id
        await asyncio.wait_for(asyncio.shield(self.client._pending[request_id]), 1)
        with self.assertRaises(RemoteError):
            self.client.result(request_id)
        self.client.release(request_id)
        self.assertNotIn(request_id, self.client._pending)

    async def test_peer_exit_finishes_outstanding_wait(self):
        task = asyncio.create_task(self.client.call("wait", timeout=2))
        await asyncio.sleep(.01)
        await self.peers[0].close()
        with self.assertRaises(PeerClosed):
            await task

    async def test_generation_mismatch_closes_channel(self):
        await write_frame(self.client.writer, {"version": "ntk.ipc.v1", "generation": "old", "kind": "cancel", "id": 1}, 65536)
        await asyncio.wait_for(self.client.closed.wait(), 1)
        self.assertIsInstance(self.peers[0].error, ProtocolError)

    async def test_frame_limit_and_duplicate_json_keys(self):
        reader = asyncio.StreamReader()
        reader.feed_data((100).to_bytes(4, "big"))
        with self.assertRaises(ProtocolError):
            await read_frame(reader, 10)
        raw = b'{"a":1,"a":2}'
        reader = asyncio.StreamReader()
        reader.feed_data(len(raw).to_bytes(4, "big") + raw)
        with self.assertRaises(ProtocolError):
            await read_frame(reader, 100)

    async def test_request_capacity_and_caller_cancel_are_not_automatic_retry(self):
        from dataclasses import replace
        from nymph_toolkit.contracts import CapacityExceeded
        self.client.settings = replace(SETTINGS, max_requests=1)
        first = asyncio.create_task(self.client.call("wait", timeout=2))
        await asyncio.sleep(.02)
        with self.assertRaises(CapacityExceeded):
            await self.client.call("echo", "excess", timeout=1)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        await asyncio.wait_for(self.cancelled.wait(), 1)
        await asyncio.wait_for(asyncio.shield(self.client._pending[1]), 1)
        self.client.release(1)
        self.assertEqual(await self.client.call("echo", "new request", timeout=1), "new request")
        self.assertEqual(self.peers[0]._received, 2)


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def pair(self, policy=OverflowPolicy.WAIT, send_bytes=4, send_chunks=2):
        options = StreamOptions(send_bytes, send_chunks, 4, 2, policy)
        future = asyncio.get_running_loop().create_future()
        def accept(reader, writer):
            future.set_result(StreamReceiver(reader, writer, options))
        self.server = await asyncio.start_server(accept, "127.0.0.1", 0)
        reader, writer = await asyncio.open_connection(*self.server.sockets[0].getsockname())
        self.sender = StreamSender(reader, writer, options)
        self.receiver = await future
        return self.sender, self.receiver

    async def asyncTearDown(self):
        await asyncio.gather(self.sender.aclose(), self.receiver.aclose())
        self.server.close()
        await self.server.wait_closed()

    async def test_send_is_local_acceptance_and_payload_is_copied(self):
        sender, receiver = await self.pair()
        data = bytearray(b"ab")
        number = await sender.send(data, timeout=1)
        data[:] = b"xx"
        self.assertEqual(number, 1)
        self.assertEqual((await receiver.receive(timeout=1)).data, b"ab")
        await sender.close(timeout=1)
        self.assertEqual((await receiver.receive(timeout=1)).kind, "end")

    async def test_drop_oldest_reports_gap_and_preserves_latest(self):
        sender, receiver = await self.pair(OverflowPolicy.DROP_OLDEST)
        for data in (b"aa", b"bb", b"cc"):
            await sender.send(data, timeout=1)
        first = await receiver.receive(timeout=1)
        self.assertEqual((first.data, first.missing, first.missing_count), (b"bb", (1, 1), 1))
        self.assertEqual((await receiver.receive(timeout=1)).data, b"cc")
        self.assertEqual(sender.dropped_chunks, 1)
        await sender.close(timeout=1)

    async def test_oversize_rejected_and_chunk_count_includes_empty_bytes(self):
        sender, receiver = await self.pair()
        with self.assertRaises(ChunkTooLarge):
            await sender.send(b"12345", timeout=1)
        await sender.send(b"", timeout=1)
        await sender.send(b"", timeout=1)
        self.assertEqual(sender.buffered_chunks, 2)
        self.assertEqual((await receiver.receive(timeout=1)).kind, "data")

    async def test_close_timeout_keeps_drain_alive_until_receiver_frees_capacity(self):
        sender, receiver = await self.pair()
        await sender.send(b"1234", timeout=1)
        await asyncio.sleep(.02)
        await sender.send(b"5678", timeout=1)
        with self.assertRaises(TimeoutError):
            await sender.close(timeout=.02)
        self.assertEqual(sender.state, StreamState.CLOSING)
        self.assertEqual((await receiver.receive(timeout=1)).data, b"1234")
        self.assertEqual((await receiver.receive(timeout=1)).data, b"5678")
        await sender.close(timeout=1)
        self.assertEqual(sender.state, StreamState.CLOSED)

    async def test_receive_timeout_does_not_abort_and_peer_abort_is_distinct(self):
        sender, receiver = await self.pair()
        with self.assertRaises(TimeoutError):
            await receiver.receive(timeout=.01)
        self.assertEqual(receiver.state, StreamState.OPEN)
        await sender.abort("no longer needed")
        event = await receiver.receive(timeout=1)
        self.assertEqual((event.kind, event.reason), ("error", "no longer needed"))

    async def test_failed_send_wait_is_not_enqueued_later(self):
        sender, receiver = await self.pair()
        await sender.send(b"aaaa", timeout=1)
        await asyncio.sleep(.02)
        await sender.send(b"bbbb", timeout=1)
        with self.assertRaises(TimeoutError):
            await sender.send(b"cccc", timeout=.01)
        self.assertEqual((await receiver.receive(timeout=1)).data, b"aaaa")
        self.assertEqual((await receiver.receive(timeout=1)).data, b"bbbb")
        await sender.close(timeout=1)
        self.assertEqual((await receiver.receive(timeout=1)).kind, "end")

    async def test_receiver_abort_unblocks_waiting_sender(self):
        sender, receiver = await self.pair()
        await receiver.abort("receiver stopped")
        async with asyncio.timeout(1):
            while sender.state == StreamState.OPEN:
                await asyncio.sleep(.001)
        self.assertEqual(sender.state, StreamState.ABORTED)
        self.assertEqual(sender.reason, "receiver stopped")

    async def test_disconnect_preserves_received_data_before_error(self):
        sender, receiver = await self.pair()
        await sender.send(b"data", timeout=1)
        async with asyncio.timeout(1):
            while receiver.buffered_chunks == 0:
                await asyncio.sleep(.001)
        sender.writer.close()
        self.assertEqual((await receiver.receive(timeout=1)).data, b"data")
        self.assertEqual((await receiver.receive(timeout=1)).kind, "error")
        self.assertEqual(receiver.state, StreamState.FAILED)

    async def test_end_without_following_data_exposes_missing_tail(self):
        from nymph_toolkit.core._streams import _frame
        sender, receiver = await self.pair()
        sender._last, sender._ending = 3, True
        await _frame(sender.writer, b"E", 3)
        terminal = await receiver.receive(timeout=1)
        self.assertEqual((terminal.kind, terminal.missing, terminal.missing_count), ("end", (1, 3), 3))

    async def test_cancelled_send_is_not_admitted_after_capacity_recovers(self):
        sender, receiver = await self.pair()
        await sender.send(b"aaaa", timeout=1)
        await asyncio.sleep(.02)
        await sender.send(b"bbbb", timeout=1)
        waiting = asyncio.create_task(sender.send(b"cccc", timeout=1))
        await asyncio.sleep(.01)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.assertEqual((await receiver.receive(timeout=1)).data, b"aaaa")
        self.assertEqual((await receiver.receive(timeout=1)).data, b"bbbb")
        await sender.close(timeout=1)
        self.assertEqual((await receiver.receive(timeout=1)).sequence, 2)
