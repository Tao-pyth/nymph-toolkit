"""One-loop history buffering with owned, serialized disk I/O and built-in rescue."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from itertools import islice
import json
import math
from pathlib import Path
import threading
from uuid import uuid4

from nymph_toolkit.contracts import BindingRecord, RuntimeState, StorageError, StorageFailure
from ._storage_io import Disk


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FileStore:
    """Unbounded event buffer; only an I/O failure pauses admission, not backlog size."""

    def __init__(self, root: Path, archive: Path, *, retention: timedelta,
                 batch_size: int, flush_interval: float) -> None:
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if (type(flush_interval) not in (int, float) or not math.isfinite(flush_interval)
                or flush_interval <= 0):
            raise ValueError("flush_interval must be finite positive seconds")
        self._disk = Disk(root, archive, retention)
        self._batch_size = batch_size
        self._interval = flush_interval
        self._thread = threading.current_thread()
        self._loop = None
        self._state = RuntimeState.NEW
        self._buffer: deque[dict] = deque()
        self._sequence = 0
        self._run_id = uuid4().hex
        self._due = None
        self._io_lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._changed = asyncio.Event()
        self._failed = asyncio.Event()
        self._failure: StorageFailure | None = None
        self._rescuing = False
        self._closing = False
        self._initialized = False
        self._pending_configurations = 0
        self._operations: set[asyncio.Task] = set()
        self._writer = None
        self._stop_task = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def failure(self) -> StorageFailure | None:
        return self._failure

    @property
    def changed(self) -> asyncio.Event:
        return self._changed

    @property
    def unsaved_events(self) -> int:
        return len(self._buffer)

    @property
    def admitting(self) -> bool:
        return (self._state == RuntimeState.RUNNING and not self._closing
                and not self._rescuing and self._failure is None)

    def _check_context(self) -> None:
        if threading.current_thread() is not self._thread:
            raise StorageError("FileStore belongs to its creating thread")
        if self._loop is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not self._loop:
                raise StorageError("FileStore belongs to its original event loop")

    def _check_open(self) -> None:
        self._check_context()
        if self._failure is not None:
            raise self._failure
        if self._state != RuntimeState.RUNNING or self._closing:
            raise StorageError("FileStore is not open for new operations")

    def _pulse(self) -> None:
        old, self._changed = self._changed, asyncio.Event()
        old.set()

    def _fatal(self, cause: Exception) -> StorageFailure:
        if self._failure is None:
            self._failure = StorageFailure(cause, len(self._buffer), self._pending_configurations > 0)
            self._state = RuntimeState.FAILED
            self._failed.set()
            self._wake.set()
            self._pulse()
        return self._failure

    def append(self, kind: str, data: dict) -> None:
        self._check_context()
        if self._closing or self._state == RuntimeState.STOPPED:
            raise StorageError("FileStore has stopped accepting events")
        if not isinstance(kind, str) or not kind or kind.strip() != kind:
            raise ValueError("kind must be nonempty without surrounding whitespace")
        if not isinstance(data, dict):
            raise TypeError("event data must be a dictionary")
        # Snapshot now, before the caller can mutate its input. Validate before enqueueing.
        copied = json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))
        now = _utcnow()
        if now.tzinfo is None:
            raise ValueError("History clock must return an aware datetime")
        self._sequence += 1
        self._buffer.append({"format": "ntk.history.v1", "run_id": self._run_id,
                             "sequence": self._sequence, "at": now.astimezone(timezone.utc).isoformat(),
                             "kind": kind, "data": copied})
        if self._due is None and self._loop is not None:
            self._due = self._loop.time() + self._interval
        if self._failure is not None:
            # Final notifications from already-running modules remain visible in the report.
            self._failure.unsaved_events = len(self._buffer)
        self._wake.set()

    @staticmethod
    async def _join(task: asyncio.Task):
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        result = task.result()
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def _own(self, coroutine, name: str):
        try:
            task = asyncio.create_task(coroutine, name=name)
        except BaseException:
            coroutine.close()
            raise
        self._operations.add(task)
        task.add_done_callback(self._operations.discard)
        return await self._join(task)

    def _protected(self) -> frozenset[Path]:
        return frozenset(self._disk.root / f"history-{r['at'][:10]}-{r['run_id']}.jsonl"
                         for r in self._buffer)

    async def _execute(self, operation, protected=frozenset()):
        """Called with the I/O lock held by an owned task; never detach to_thread work."""
        if self._failure is not None:
            raise self._failure
        try:
            try:
                return await asyncio.to_thread(operation)
            except OSError as original:
                self._rescuing = True
                self._pulse()
                try:
                    await asyncio.to_thread(self._disk.archive_old, _utcnow(), protected | self._protected())
                    return await asyncio.to_thread(operation)
                except Exception as rescue_error:
                    raise ExceptionGroup("Storage operation and rescue failed", [original, rescue_error])
                finally:
                    self._rescuing = False
                    self._pulse()
        except Exception as exc:
            raise self._fatal(exc) from exc

    async def start(self) -> None:
        self._check_context()
        if self._state != RuntimeState.NEW or self._closing:
            raise StorageError("FileStore cannot be restarted")
        self._loop = asyncio.get_running_loop()
        self._state = RuntimeState.STARTING
        await self._own(self._start(), "ntk-storage-start")

    async def _start(self) -> None:
        async with self._io_lock:
            await self._execute(self._disk.initialize)
            self._initialized = True
        if not self._closing:
            self._state = RuntimeState.RUNNING
            if self._buffer:
                self._due = self._loop.time() + self._interval
            self._writer = asyncio.create_task(self._write_loop(), name="ntk-history-writer")
        self._pulse()

    async def load_bindings(self) -> tuple[BindingRecord, ...]:
        self._check_open()
        async def load():
            async with self._io_lock:
                return await self._execute(self._disk.load_bindings)
        return await self._own(load(), "ntk-settings-load")

    async def save_bindings(self, bindings: tuple[BindingRecord, ...]) -> None:
        self._check_open()
        records = tuple(bindings)
        if not all(isinstance(record, BindingRecord) for record in records):
            raise TypeError("bindings must contain BindingRecord values")
        if len({record.key for record in records}) != len(records):
            raise ValueError("Duplicate binding key")
        self._pending_configurations += 1
        async def save():
            try:
                async with self._io_lock:
                    await self._execute(lambda: self._disk.save_bindings(records))
            finally:
                self._pending_configurations -= 1
        await self._own(save(), "ntk-settings-save")

    async def _flush_once(self, through: int) -> None:
        async with self._io_lock:
            if self._failure is not None:
                raise self._failure
            records = tuple(r for r in islice(self._buffer, self._batch_size) if r["sequence"] <= through)
            if not records:
                return
            try:
                batch = await asyncio.to_thread(self._disk.history_batch, records)
            except Exception as exc:
                raise self._fatal(exc) from exc
            await self._execute(batch.write, batch.protected)
            for _ in records:
                self._buffer.popleft()
            if not self._buffer:
                self._due = None

    async def _flush_through(self, through: int) -> None:
        while self._buffer and self._buffer[0]["sequence"] <= through:
            await self._flush_once(through)
            await asyncio.sleep(0)

    async def flush(self) -> None:
        self._check_open()
        await self._own(self._flush_through(self._sequence), "ntk-history-flush")

    async def _write_loop(self) -> None:
        try:
            while not self._closing and self._failure is None:
                self._wake.clear()
                if not self._buffer:
                    await self._wake.wait()
                    continue
                if len(self._buffer) < self._batch_size:
                    remaining = max(0, self._due - self._loop.time())
                    if remaining:
                        try:
                            async with asyncio.timeout(remaining):
                                await self._wake.wait()
                            continue
                        except TimeoutError:
                            pass
                await self._flush_once(self._sequence)
                await asyncio.sleep(0)
        except Exception as exc:
            self._fatal(exc)

    async def wait_failure(self) -> StorageFailure:
        self._check_context()
        await self._failed.wait()
        return self._failure

    async def wait_ready(self) -> None:
        self._check_context()
        while not self.admitting:
            event = self._changed
            if self._failure is not None:
                raise self._failure
            if self._closing or self._state != RuntimeState.RUNNING:
                raise StorageError("FileStore is not running")
            await event.wait()

    async def stop(self) -> None:
        self._check_context()
        if self._stop_task is None:
            self._closing = True
            if self._failure is None:
                self._state = RuntimeState.STOPPING
            self._wake.set()
            self._pulse()
            self._stop_task = asyncio.create_task(self._stop(), name="ntk-storage-stop")
        await self._join(self._stop_task)

    async def _stop(self) -> None:
        failed_before_stop = self._failure
        try:
            if self._operations:
                await asyncio.gather(*tuple(self._operations), return_exceptions=True)
            if self._writer is not None:
                await self._writer
            if self._failure is None:
                if not self._initialized and self._buffer:
                    async with self._io_lock:
                        await self._execute(self._disk.initialize)
                        self._initialized = True
                await self._flush_through(self._sequence)
        except Exception as exc:
            self._fatal(exc)
        finally:
            self._state = RuntimeState.FAILED if self._failure is not None else RuntimeState.STOPPED
            self._pulse()
        if self._failure is not None and failed_before_stop is None:
            raise self._failure
