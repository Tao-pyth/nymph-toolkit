"""One-shot, cooperative in-process runtime lifecycle."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from typing import Generic, TypeVar

from nymph_toolkit.contracts import (
    LifecycleFailure,
    LifecyclePhase,
    RuntimeFailure,
    RuntimeService,
    RuntimeState,
    RuntimeStateError,
)

T = TypeVar("T")


class Runtime(Generic[T]):
    """Own one supervisor task; leave the event loop and activity decisions to the caller."""

    def __init__(self, service: RuntimeService[T]) -> None:
        self._service = service
        self._state = RuntimeState.NEW
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._entered = False
        self._started = False
        self._stop_requested = False
        self._result: T | None = None
        self._failures: list[LifecycleFailure] = []

    @property
    def state(self) -> RuntimeState:
        return self._state

    async def start(self) -> None:
        """Start once, waiting for initialization or cleanup after initialization failure."""
        self._check_context()
        if self._state != RuntimeState.NEW:
            raise RuntimeStateError(f"Cannot start a runtime in state {self._state}")
        self._loop = asyncio.get_running_loop()
        self._state = RuntimeState.STARTING
        driver = self._drive()
        try:
            self._task = self._loop.create_task(driver, name="ntk-runtime")
        except Exception as exc:
            driver.close()
            self._failures.append(LifecycleFailure(LifecyclePhase.START, exc))
            self._state = RuntimeState.FAILED
            self._raise_failures()
        try:
            await self._ready.wait()
        except asyncio.CancelledError:
            self._request_stop()
            raise
        if not self._started:
            self._raise_failures()
            raise RuntimeStateError("Runtime was stopped before initialization completed")

    async def wait(self) -> T | None:
        """Wait for execution and cleanup without forwarding caller cancellation."""
        self._check_context()
        if self._state == RuntimeState.NEW:
            raise RuntimeStateError("Runtime has not been started")
        if self._task is not None:
            await asyncio.shield(self._task)
        self._raise_failures()
        return self._result

    async def stop(self) -> None:
        """Request cancellation once and wait for cleanup; safe to call repeatedly."""
        self._check_context()
        if self._state == RuntimeState.NEW:
            self._loop = asyncio.get_running_loop()
            self._state = RuntimeState.STOPPED
            return
        self._request_stop()
        await self.wait()

    def _check_context(self) -> None:
        if self._loop is not None and asyncio.get_running_loop() is not self._loop:
            raise RuntimeStateError("Runtime must be controlled from its original event loop")
        if self._task is not None and asyncio.current_task() is self._task:
            raise RuntimeStateError("A service cannot wait for its own runtime")

    def _request_stop(self) -> None:
        if self._state not in (RuntimeState.STARTING, RuntimeState.RUNNING):
            return
        self._stop_requested = True
        self._state = RuntimeState.STOPPING
        # A not-yet-entered coroutine cannot execute its finally block if cancelled.
        # Let it enter, observe the request, and signal completion instead.
        if self._entered and self._task is not None:
            self._task.cancel()

    def _raise_failures(self) -> None:
        if self._failures:
            raise RuntimeFailure(tuple(self._failures)) from self._failures[0].exception

    async def _drive(self) -> None:
        # Also establish ownership before invoking hooks with an eager task factory.
        await asyncio.sleep(0)
        self._entered = True
        attempted_start = False
        phase = LifecyclePhase.START
        try:
            if self._stop_requested:
                return
            attempted_start = True
            await self._service.start()
            self._started = True
            self._ready.set()
            if self._stop_requested:
                return
            self._state = RuntimeState.RUNNING
            phase = LifecyclePhase.RUN
            self._result = await self._service.run()
        except asyncio.CancelledError as exc:
            if not self._stop_requested:
                self._failures.append(LifecycleFailure(phase, exc))
        except Exception as exc:
            self._failures.append(LifecycleFailure(phase, exc))
        finally:
            self._state = RuntimeState.STOPPING
            try:
                if attempted_start:
                    await self._service.stop()
            except (Exception, asyncio.CancelledError) as exc:
                self._failures.append(LifecycleFailure(LifecyclePhase.STOP, exc))
            finally:
                self._state = RuntimeState.FAILED if self._failures else RuntimeState.STOPPED
                self._ready.set()
