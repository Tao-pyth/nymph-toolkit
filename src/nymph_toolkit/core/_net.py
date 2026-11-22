"""TCP streams owned by the hybrid runtime.

CPython gh-160429: on Windows, a reset from shutdown() can skip Proactor
socket closure and server detachment, leaving Server.wait_closed() pending.
Keep the workaround local to our TCP transports, including bootstrap failures.
Do not patch asyncio classes, loop policy or the application's error handler.
"""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import sys


class _ShutdownSocket:
    """Delegate everything except an already-disconnected socket's shutdown."""

    def __init__(self, sock):
        self.socket = sock

    def __getattr__(self, name):
        return getattr(self.socket, name)

    def shutdown(self, how):
        try:
            self.socket.shutdown(how)
        except ConnectionError:
            # This does not make an RPC, stream or module stop successful.
            # Only the final transport cleanup must still close and detach.
            pass


def _protect_shutdown(transport):
    if sys.platform != "win32":
        return
    from asyncio.proactor_events import _ProactorSocketTransport
    if not isinstance(transport, _ProactorSocketTransport):
        return
    original = transport._call_connection_lost

    def connection_lost(exc):
        sock = transport._sock
        if sock is None:
            return original(exc)
        guarded = _ShutdownSocket(sock)
        # The callback is synchronous. No read/write task sees this delegate;
        # retain CPython's own protocol notification and bookkeeping, including
        # on interpreters where the upstream fix is already present.
        transport._sock = guarded
        try:
            return original(exc)
        finally:
            if transport._sock is guarded:
                transport._sock = sock

    transport._call_connection_lost = connection_lost


class _ReaderProtocol(asyncio.StreamReaderProtocol):
    def connection_made(self, transport):
        _protect_shutdown(transport)
        super().connection_made(transport)


async def open_connection(host, port):
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = _ReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_connection(lambda: protocol, host, port)
    return reader, asyncio.StreamWriter(transport, protocol, reader, loop)


async def start_server(client_connected, host, port):
    loop = asyncio.get_running_loop()
    def protocol():
        return _ReaderProtocol(asyncio.StreamReader(loop=loop), client_connected, loop=loop)
    return await loop.create_server(protocol, host, port)
