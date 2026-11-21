"""A dedicated flow-controlled byte stream; control RPC never shares its data queue."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections import deque
import struct

from nymph_toolkit.contracts import ChunkTooLarge, OverflowPolicy, ProtocolError, StreamClosed, StreamEvent, StreamState
from nymph_toolkit.contracts.hybrid import seconds

HEADER = struct.Struct("!cQQ")  # kind, sequence/credit-count, payload-size/credit-bytes
REASON_LIMIT = 4096


async def _frame(writer, kind, number=0, payload=b""):
    writer.write(HEADER.pack(kind, number, len(payload)) + payload)
    await writer.drain()


class _Stream:
    def __init__(self, reader, writer, options):
        self.reader, self.writer, self.options = reader, writer, options
        self.state = StreamState.OPEN
        self.reason = ""
        self._changed = asyncio.Event()
        self._tasks = []
        self._queue = deque()
        self.buffered_bytes = 0
        self._last = 0

    @property
    def buffered_chunks(self):
        return len(self._queue)

    def _pulse(self):
        changed = self._changed
        self._changed = asyncio.Event()
        changed.set()

    def _failure(self, reason, *, aborted=False):
        if self.state == StreamState.CLOSED:
            return
        self.reason = reason
        self.state = StreamState.ABORTED if aborted else StreamState.FAILED
        self._pulse()
        self.writer.close()

    async def abort(self, reason="Explicit stream abort"):
        await self._terminate(reason, aborted=True)

    async def fail(self, reason):
        await self._terminate(reason, aborted=False)

    async def _terminate(self, reason, *, aborted):
        raw = reason.encode("utf-8")
        if not raw or len(raw) > REASON_LIMIT:
            raise ValueError("Abort reason must contain 1..4096 UTF-8 bytes")
        if self.state in (StreamState.CLOSED, StreamState.ABORTED, StreamState.FAILED):
            return
        # No await between the abort frame and closing: no data may follow it.
        self.writer.write(HEADER.pack(b"X" if aborted else b"F", self._last, len(raw)) + raw)
        self._failure(reason, aborted=aborted)
        for task in self._tasks:
            if task is not asyncio.current_task():
                task.cancel()
        await self.aclose()

    async def aclose(self):
        if self.state in (StreamState.OPEN, StreamState.CLOSING):
            self._failure("Owner closed the stream", aborted=True)
        for task in self._tasks:
            if task is not asyncio.current_task() and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in self._tasks if t is not asyncio.current_task()), return_exceptions=True)
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, OSError):
            pass


class StreamSender(_Stream):
    def __init__(self, reader, writer, options):
        super().__init__(reader, writer, options)
        self._credit_bytes = self._credit_chunks = 0
        self._ending = False
        self.dropped_chunks = 0
        self._tasks = [asyncio.create_task(self._credits(), name="ntk-stream-credits"),
                       asyncio.create_task(self._pump(), name="ntk-stream-send")]

    async def send(self, data, *, timeout):
        seconds(timeout)
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("Stream data must be bytes-like")
        raw = bytes(data)
        if len(raw) > min(self.options.send_bytes, self.options.receive_bytes):
            raise ChunkTooLarge("Chunk exceeds stream byte limit; sender must split it")
        async with asyncio.timeout(timeout):
            while True:
                changed = self._changed
                if self.state != StreamState.OPEN:
                    raise StreamClosed(self.reason or self.state)
                fits = (self.buffered_bytes + len(raw) <= self.options.send_bytes
                        and len(self._queue) < self.options.send_chunks)
                if fits:
                    self._last += 1
                    self._queue.append((self._last, raw))
                    self.buffered_bytes += len(raw)
                    self._pulse()
                    return self._last
                if self.options.overflow == OverflowPolicy.DROP_OLDEST:
                    _, old = self._queue.popleft()
                    self.buffered_bytes -= len(old)
                    self.dropped_chunks += 1
                    continue
                await changed.wait()

    async def close(self, *, timeout):
        seconds(timeout)
        if self.state == StreamState.OPEN:
            self.state = StreamState.CLOSING
            self._pulse()
        async with asyncio.timeout(timeout):
            while self.state == StreamState.CLOSING:
                await self._changed.wait()
        if self.state != StreamState.CLOSED:
            raise StreamClosed(self.reason)

    async def _pump(self):
        try:
            while self.state in (StreamState.OPEN, StreamState.CLOSING):
                changed = self._changed
                if self._queue:
                    number, data = self._queue[0]
                    if self._credit_chunks and self._credit_bytes >= len(data):
                        self._queue.popleft()
                        self.buffered_bytes -= len(data)
                        self._credit_chunks -= 1
                        self._credit_bytes -= len(data)
                        self._pulse()
                        await _frame(self.writer, b"D", number, data)
                        continue
                elif self.state == StreamState.CLOSING:
                    self._ending = True
                    await _frame(self.writer, b"E", self._last)
                    return
                await changed.wait()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._failure(str(exc))

    async def _credits(self):
        try:
            while True:
                kind, count, size = HEADER.unpack(await self.reader.readexactly(HEADER.size))
                if kind == b"C":
                    self._credit_chunks += count
                    self._credit_bytes += size
                    if (self._credit_chunks > self.options.receive_chunks
                            or self._credit_bytes > self.options.receive_bytes):
                        raise ProtocolError("Receiver granted excessive credit")
                    self._pulse()
                elif kind == b"A" and size == 0 and count == self._last and self._ending:
                    self.state = StreamState.CLOSED
                    self._pulse()
                    self.writer.close()
                    return
                elif kind in (b"X", b"F") and 0 < size <= REASON_LIMIT:
                    reason = (await self.reader.readexactly(size)).decode("utf-8")
                    self._failure(reason, aborted=kind == b"X")
                    self._queue.clear()
                    self.buffered_bytes = 0
                    return
                else:
                    raise ProtocolError("Invalid stream control frame")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._failure(str(exc))
        finally:
            if self.state in (StreamState.ABORTED, StreamState.FAILED):
                self._queue.clear()
                self.buffered_bytes = 0


class StreamReceiver(_Stream):
    def __init__(self, reader, writer, options):
        super().__init__(reader, writer, options)
        self._terminal = None
        self._credit_bytes = options.receive_bytes
        self._credit_chunks = options.receive_chunks
        self._credit_changed = asyncio.Event()
        self._credit_changed.set()
        self._tasks = [asyncio.create_task(self._read(), name="ntk-stream-receive"),
                       asyncio.create_task(self._credits(), name="ntk-stream-credit-return")]

    def _failure(self, reason, *, aborted=False):
        super()._failure(reason, aborted=aborted)
        if self._terminal is None:
            self._terminal = StreamEvent("error", self._last, reason=reason + "; undelivered tail may be unknown")

    async def receive(self, *, timeout):
        seconds(timeout)
        async with asyncio.timeout(timeout):
            while not self._queue and self._terminal is None:
                await self._changed.wait()
        if self._queue:
            event = self._queue.popleft()
            self.buffered_bytes -= len(event.data)
            self._credit_bytes += len(event.data)
            self._credit_chunks += 1
            self._credit_changed.set()
            return event
        return self._terminal

    async def _credits(self):
        try:
            while self.state == StreamState.OPEN:
                await self._credit_changed.wait()
                self._credit_changed.clear()
                count, size = self._credit_chunks, self._credit_bytes
                self._credit_chunks = self._credit_bytes = 0
                self.writer.write(HEADER.pack(b"C", count, size))
                await self.writer.drain()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if self.state == StreamState.OPEN:
                self._failure(str(exc))

    async def _read(self):
        try:
            while True:
                kind, number, size = HEADER.unpack(await self.reader.readexactly(HEADER.size))
                if kind == b"D":
                    if (number <= self._last or size > self.options.receive_bytes
                            or self.buffered_bytes + size > self.options.receive_bytes
                            or len(self._queue) >= self.options.receive_chunks):
                        raise ProtocolError("Stream order or receive capacity violated")
                    data = await self.reader.readexactly(size)
                    missing = (self._last + 1, number - 1) if number > self._last + 1 else None
                    self._last = number
                    self._queue.append(StreamEvent("data", number, data, missing))
                    self.buffered_bytes += size
                    self._pulse()
                elif kind == b"E" and size == 0 and number >= self._last:
                    missing = (self._last + 1, number) if number > self._last else None
                    self._terminal = StreamEvent("end", number, missing=missing)
                    await _frame(self.writer, b"A", number)
                    self.state = StreamState.CLOSED
                    self._pulse()
                    return
                elif kind in (b"X", b"F") and 0 < size <= REASON_LIMIT:
                    reason = (await self.reader.readexactly(size)).decode("utf-8")
                    missing = (self._last + 1, number) if number > self._last else None
                    self._terminal = StreamEvent("error", number, missing=missing, reason=reason)
                    self._failure(reason, aborted=kind == b"X")
                    return
                else:
                    raise ProtocolError("Invalid stream data frame")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._failure(str(exc))
        finally:
            self._credit_changed.set()
            if self.state != StreamState.OPEN:
                self.writer.close()
