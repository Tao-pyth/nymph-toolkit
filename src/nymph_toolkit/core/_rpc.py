"""Bidirectional, bounded requests over a separately owned control or data socket."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import CapacityExceeded, OutcomeUnknown, PeerClosed, ProtocolError, RemoteError
from nymph_toolkit.contracts.hybrid import seconds
from ._wire import VERSION, decode, encode, read_frame, write_frame


class RpcPeer:
    def __init__(self, reader, writer, *, generation, module_id, settings, handler):
        self.reader, self.writer = reader, writer
        self.generation, self.module_id = generation, module_id
        self.settings, self.handler = settings, handler
        self.closed = asyncio.Event()
        self.error = None
        self._write_lock = asyncio.Lock()
        self._next = 0
        self._received = 0
        self._pending = {}
        self._incoming = {}
        self._auxiliary = set()
        self._reader = asyncio.create_task(self._read(), name=f"ntk-rpc:{module_id}")

    async def _send(self, message):
        if self.closed.is_set():
            raise PeerClosed(str(self.error or "Connection closed"))
        async with self._write_lock:
            await write_frame(self.writer, {"version": VERSION, "generation": self.generation, **message},
                              self.settings.max_frame_bytes)

    def _background(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._auxiliary.add(task)
        def done(t):
            self._auxiliary.discard(t)
            if not t.cancelled():
                t.exception()
        task.add_done_callback(done)
        return task

    async def call(self, operation, payload=None, *, timeout):
        seconds(timeout)
        if self.closed.is_set():
            raise PeerClosed(str(self.error or "Connection closed"))
        if sum(not future.done() for future in self._pending.values()) >= self.settings.max_requests:
            raise CapacityExceeded("Outgoing request limit reached")
        encoded = encode(payload)
        self._next += 1
        request_id = self._next
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            async with asyncio.timeout(timeout):
                await self._send({"kind": "request", "id": request_id, "operation": operation, "payload": encoded})
                result = await asyncio.shield(future)
        except TimeoutError as exc:
            self._background(self._cancel(request_id))
            raise OutcomeUnknown(request_id) from exc
        except asyncio.CancelledError:
            self._background(self._cancel(request_id))
            raise
        except Exception:
            self._pending.pop(request_id, None)
            raise
        self._pending.pop(request_id, None)
        return self._value(result)

    async def _cancel(self, request_id):
        try:
            async with asyncio.timeout(self.settings.call_timeout):
                await self._send({"kind": "cancel", "id": request_id})
        except (Exception, asyncio.CancelledError):
            pass

    @staticmethod
    def _value(result):
        failed, value = result
        if failed:
            raise value
        return value

    def result(self, request_id):
        future = self._pending[request_id]
        if not future.done():
            raise OutcomeUnknown(request_id)
        return self._value(future.result())

    def release(self, request_id):
        future = self._pending.get(request_id)
        if future is not None and not future.done():
            raise OutcomeUnknown(request_id, "Cannot release an unfinished request")
        self._pending.pop(request_id, None)

    async def _respond(self, request_id, operation, payload):
        try:
            result = await self.handler(operation, decode(payload))
            message = {"kind": "result", "id": request_id, "payload": encode(result)}
        except asyncio.CancelledError:
            message = {"kind": "error", "id": request_id,
                       "payload": encode(RemoteError(self.module_id, "CancelledError", "Operation cancelled; effects are not rolled back"))}
        except Exception as exc:
            error = exc if isinstance(exc, RemoteError) else RemoteError(self.module_id, type(exc).__name__, str(exc))
            message = {"kind": "error", "id": request_id, "payload": encode(error)}
        try:
            await self._send(message)
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            self._incoming.pop(request_id, None)

    async def _read(self):
        try:
            while True:
                message = await read_frame(self.reader, self.settings.max_frame_bytes)
                if not isinstance(message, dict) or message.get("version") != VERSION or message.get("generation") != self.generation:
                    raise ProtocolError("Wire version or generation mismatch")
                request_id, kind = message.get("id"), message.get("kind")
                if type(request_id) is not int or request_id <= 0:
                    raise ProtocolError("Invalid request ID")
                if kind == "request":
                    if set(message) != {"version", "generation", "id", "kind", "operation", "payload"}:
                        raise ProtocolError("Invalid request fields")
                    if request_id <= self._received or not isinstance(message["operation"], str):
                        raise ProtocolError("Stale request or invalid operation")
                    self._received = request_id
                    if len(self._incoming) >= self.settings.max_requests:
                        await self._send({"kind": "error", "id": request_id,
                                          "payload": encode(RemoteError(self.module_id, "CapacityExceeded", "Incoming request limit reached"))})
                    else:
                        task = asyncio.create_task(self._respond(request_id, message["operation"], message["payload"]))
                        self._incoming[request_id] = task
                elif kind in ("result", "error"):
                    if set(message) != {"version", "generation", "id", "kind", "payload"}:
                        raise ProtocolError("Invalid response fields")
                    if request_id > self._next:
                        raise ProtocolError("Response to a future request")
                    value = decode(message["payload"])
                    if kind == "error" and not isinstance(value, Exception):
                        raise ProtocolError("Invalid remote failure")
                    future = self._pending.get(request_id)
                    if future is not None and not future.done():
                        future.set_result((kind == "error", value))
                elif kind == "cancel":
                    if set(message) != {"version", "generation", "id", "kind"}:
                        raise ProtocolError("Invalid cancellation fields")
                    task = self._incoming.get(request_id)
                    if task is not None:
                        task.cancel()
                else:
                    raise ProtocolError("Unknown message kind")
        except asyncio.CancelledError:
            self.error = PeerClosed("Connection closed")
        except Exception as exc:
            self.error = exc
        finally:
            self.closed.set()
            self.writer.close()
            for future in self._pending.values():
                if not future.done():
                    future.set_result((True, PeerClosed(str(self.error))))
            for task in self._incoming.values():
                task.cancel()

    async def close(self):
        if not self._reader.done():
            self._reader.cancel()
        await asyncio.gather(self._reader, return_exceptions=True)
        tasks = (set(self._incoming.values()) | self._auxiliary) - {asyncio.current_task()}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, OSError):
            pass
