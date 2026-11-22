"""Fault-injected socket shutdown, independent of TCP reset timing (#94)."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import socket
import sys
import unittest
from unittest.mock import patch

from nymph_toolkit.core import _net


@unittest.skipUnless(sys.platform == "win32", "Windows Proactor transport")
class WindowsShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.loop = asyncio.get_running_loop()
        self.errors = []
        self.previous_handler = self.loop.get_exception_handler()
        self.loop.set_exception_handler(lambda loop, context: self.errors.append(context))
        self.servers, self.writers = [], []

    async def asyncTearDown(self):
        try:
            for writer in self.writers:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
                # Repair only the pre-fix failure so a red test does not leak
                # sockets or hang the test runner's event-loop cleanup.
                transport = writer.transport
                if transport._sock is not None:
                    transport._call_connection_lost(None)
            for server in self.servers:
                server.close()
                await asyncio.wait_for(server.wait_closed(), 1)
        finally:
            self.loop.set_exception_handler(self.previous_handler)

    async def pair(self, *, owned=True):
        connected = self.loop.create_future()
        net = _net if owned else asyncio
        def accept(reader, writer):
            connected.set_result((reader, writer))
        server = await net.start_server(accept, "127.0.0.1", 0)
        self.servers.append(server)
        client = await net.open_connection(*server.sockets[0].getsockname())
        accepted = await connected
        self.writers.extend((client[1], accepted[1]))
        return server, client, accepted

    async def close_with_shutdown_error(self, writer, error):
        target = writer.transport._sock
        original = socket.socket.shutdown
        def shutdown(sock, how):
            if sock is target:
                self.assertEqual(how, socket.SHUT_RDWR)
                raise error
            return original(sock, how)
        with patch.object(socket.socket, "shutdown", shutdown):
            writer.close()
            await writer.wait_closed()
            # wait_closed resolves in protocol.connection_lost, before the
            # enclosing transport callback reports its exception.
            await asyncio.sleep(0)
        return target

    async def test_reset_releases_client_and_server_socket(self):
        for side in ("client", "server"):
            with self.subTest(side=side):
                server, client, accepted = await self.pair()
                writer = (client if side == "client" else accepted)[1]
                reset = ConnectionResetError("injected shutdown reset")
                reset.winerror = 10054
                sock = await self.close_with_shutdown_error(writer, reset)
                self.assertEqual(self.errors, [])
                self.assertEqual(sock.fileno(), -1)
                self.assertIsNone(writer.transport._sock)
                self.assertTrue(writer.transport._called_connection_lost)
                for other in (client[1], accepted[1]):
                    other.close()
                    await other.wait_closed()
                server.close()
                await asyncio.wait_for(server.wait_closed(), 1)

    async def test_unexpected_shutdown_error_remains_observable(self):
        _, _, accepted = await self.pair()
        error = OSError("unexpected shutdown failure")
        await self.close_with_shutdown_error(accepted[1], error)
        self.assertEqual([c.get("exception") for c in self.errors], [error])

    async def test_read_failure_is_not_converted_to_success(self):
        _, _, (reader, writer) = await self.pair()
        sock = writer.transport._sock
        error = ConnectionResetError("connection lost while reading")
        writer.transport._force_close(error)
        with self.assertRaises(ConnectionResetError):
            await reader.read(1)
        with self.assertRaises(ConnectionResetError):
            await writer.wait_closed()
        self.assertEqual(sock.fileno(), -1)
        self.assertEqual(self.errors, [])

    async def test_protocol_exception_remains_observable_and_socket_closes(self):
        _, _, accepted = await self.pair()
        writer = accepted[1]
        protocol = writer.transport.get_protocol()
        original = protocol.connection_lost
        error = RuntimeError("protocol failure")
        def connection_lost(exc):
            original(exc)
            raise error
        with patch.object(protocol, "connection_lost", connection_lost):
            sock = await self.close_with_shutdown_error(writer, ConnectionResetError("reset"))
        self.assertEqual([c.get("exception") for c in self.errors], [error])
        self.assertEqual(sock.fileno(), -1)
        self.assertIsNone(writer.transport._sock)

    async def test_application_streams_and_loop_handler_are_unchanged(self):
        from asyncio.proactor_events import _ProactorSocketTransport
        original = _ProactorSocketTransport._call_connection_lost
        handler = self.loop.get_exception_handler()
        await self.pair()
        _, client, accepted = await self.pair(owned=False)
        self.assertIs(_ProactorSocketTransport._call_connection_lost, original)
        self.assertIs(self.loop.get_exception_handler(), handler)
        for writer in (client[1], accepted[1]):
            self.assertIs(writer.transport._call_connection_lost.__func__, original)


if __name__ == "__main__":
    unittest.main()
