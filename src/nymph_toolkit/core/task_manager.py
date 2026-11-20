"""Own activities specified by Nymph; elapsed schedules notify, never decide to stop."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import math
import threading

from nymph_toolkit.contracts import (
    ActivityAdmissionError, ActivityFailure, ActivityFinishReason, ActivityKey,
    ActivityNotice, ActivityNoticeKind, ActivityRequest, ActivitySnapshot,
    ActivityStartInPastError, ActivityState, ActivityStateError, DuplicateActivityError,
    ModuleExecutionState, RegistryError, RuntimeState, UnknownActivityError,
)
from nymph_toolkit.contracts.activities import _freeze_json, _json_data, _utc
from .connections import Connections


class _Clock:
    def now(self):
        return datetime.now(timezone.utc)

    def monotonic(self):
        return asyncio.get_running_loop().time()

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


@dataclass(frozen=True)
class _Context:
    request: ActivityRequest
    planned_start_at: datetime
    planned_end_at: datetime
    _entry: "_Activity" = field(repr=False, compare=False)

    @property
    def finish_requested(self):
        return self._entry.finish_reason is not None

    @property
    def finish_reason(self):
        return self._entry.finish_reason

    async def wait_for_finish(self):
        await self._entry.finish.wait()
        return self.finish_reason


@dataclass
class _Activity:
    request: ActivityRequest
    execute: Callable
    accepted_at: datetime
    start_at: datetime
    end_at: datetime
    state: ActivityState = ActivityState.PENDING
    started_at: datetime | None = None
    ended_at: datetime | None = None
    started_mono: float | None = None
    elapsed: float = 0.0
    finish_reason: ActivityFinishReason | None = None
    finish_requested_at: datetime | None = None
    notified: bool = False
    result: object = None
    failures: tuple[ActivityFailure, ...] = ()
    finish: asyncio.Event = field(default_factory=asyncio.Event)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    entered: bool = False
    driver: asyncio.Task | None = None
    timer: asyncio.Task | None = None
    worker: asyncio.Task | None = None


class TaskManager:
    """One-loop activities sharing the existing connection catalog and store."""

    def __init__(self, connections: Connections, *, clock_check_interval: float, clock=None):
        if not isinstance(connections, Connections):
            raise TypeError("connections must be a Connections instance")
        if (type(clock_check_interval) not in (int, float)
                or not math.isfinite(clock_check_interval) or clock_check_interval <= 0):
            raise ValueError("clock_check_interval must be finite positive seconds")
        self.connections = connections
        self.store = connections.store
        self._clock = _Clock() if clock is None else clock
        if not all(callable(getattr(self._clock, name, None)) for name in ("now", "monotonic", "sleep")):
            raise TypeError("clock must provide now, monotonic and async sleep")
        self._interval = clock_check_interval
        self._thread = threading.current_thread()
        self._loop = None
        self._state = RuntimeState.NEW
        self._activities: dict[ActivityKey, _Activity] = {}
        self._notices: dict[str, asyncio.Queue] = {}
        self._sequence = 0
        self._fatal = None
        self._fatal_reported = False
        self._errors = []
        self._run_entered = False
        self._stop_task = None
        self._owned: set[asyncio.Task] = set()

    @property
    def state(self):
        return self._state

    def _check_context(self):
        if threading.current_thread() is not self._thread:
            raise ActivityStateError("TaskManager belongs to its creating thread")
        if self._loop is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not self._loop:
                raise ActivityStateError("TaskManager belongs to its original event loop")

    def _check_running(self):
        self._check_context()
        if self._state != RuntimeState.RUNNING:
            raise ActivityStateError(f"TaskManager is {self._state}")

    def _now(self):
        return _utc(self._clock.now())

    def _entry(self, key):
        if not isinstance(key, ActivityKey):
            raise TypeError("key must be an ActivityKey")
        try:
            return self._activities[key]
        except KeyError:
            raise UnknownActivityError(key) from None

    def _owner(self, requester_id):
        try:
            entry = self.connections.catalog.get(requester_id)
            execution = self.connections.module_state(requester_id)
        except RegistryError as exc:
            raise ActivityAdmissionError("Requester is not registered and declared") from exc
        if not entry.available:
            raise ActivityAdmissionError("Requester has missing registered dependencies")
        if execution != ModuleExecutionState.RUNNING:
            raise ActivityAdmissionError("Requester must handle its connection interruption before starting an activity")

    async def start(self):
        self._check_context()
        if self._state != RuntimeState.NEW:
            raise ActivityStateError("TaskManager cannot be restarted")
        if self.connections.state != RuntimeState.RUNNING:
            raise ActivityStateError("Connections must be running before TaskManager starts")
        self._loop = asyncio.get_running_loop()
        self._fatal = self._loop.create_future()
        self._state = RuntimeState.RUNNING

    async def run(self):
        self._check_running()
        if self._run_entered:
            raise ActivityStateError("TaskManager run can only be entered once")
        self._run_entered = True
        failure = await asyncio.shield(self._fatal)
        if failure is not None:
            self._fatal_reported = True
            raise failure

    def _failed(self, error):
        if not any(error is previous for previous in self._errors):
            self._errors.append(error)
        if self._fatal is not None and not self._fatal.done():
            self._fatal.set_result(error)

    def _spawn(self, coroutine, name, *, fatal=True):
        try:
            task = asyncio.create_task(coroutine, name=name)
        except BaseException:
            coroutine.close()
            raise
        self._owned.add(task)
        def observe(done):
            self._owned.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                if fatal:
                    self._failed(exc)
        task.add_done_callback(observe)
        return task

    def _snapshot(self, entry):
        elapsed = entry.elapsed
        if entry.started_mono is not None and not entry.state.terminal:
            elapsed = max(0.0, self._clock.monotonic() - entry.started_mono)
        return ActivitySnapshot(
            request=entry.request, state=entry.state, accepted_at=entry.accepted_at,
            planned_start_at=entry.start_at, planned_end_at=entry.end_at,
            started_at=entry.started_at, ended_at=entry.ended_at, elapsed_seconds=elapsed,
            finish_reason=entry.finish_reason, finish_requested_at=entry.finish_requested_at,
            planned_end_notified=entry.notified, result=entry.result, failures=entry.failures,
        )

    def snapshot(self, key):
        self._check_context()
        return self._snapshot(self._entry(key))

    def activities(self, requester_id=None):
        self._check_context()
        return tuple(self._snapshot(entry) for key, entry in sorted(self._activities.items())
                     if requester_id is None or key.requester_id == requester_id)

    def _emit(self, entry, kind=ActivityNoticeKind.STATE_CHANGED):
        observed = self._snapshot(entry)
        at = self._now()
        self._sequence += 1
        record = {"request": entry.request.as_dict(), "state": observed.state.value,
                  "notice_sequence": self._sequence, "observed_at": at.isoformat(),
                  "elapsed_seconds": observed.elapsed_seconds, "planned_end_notified": entry.notified,
                  "finish_reason": None if entry.finish_reason is None else entry.finish_reason.value,
                  "result": _json_data(entry.result),
                  "failures": [{"type": type(f.exception).__name__, "message": str(f.exception)} for f in entry.failures]}
        for name in ("accepted_at", "planned_start_at", "planned_end_at", "started_at", "ended_at", "finish_requested_at"):
            value = getattr(observed, name)
            record[name] = None if value is None else value.isoformat()
        self.store.append("activity_" + kind.value, record)
        queue = self._notices.setdefault(entry.request.key.requester_id, asyncio.Queue())
        queue.put_nowait(ActivityNotice(self._sequence, kind, at, observed))
        return observed

    def submit(self, request: ActivityRequest, execute: Callable):
        self._check_running()
        if not isinstance(request, ActivityRequest) or not callable(execute):
            raise TypeError("submit requires an ActivityRequest and async execution callable")
        if self.store.failure is not None:
            raise self.store.failure
        if not self.store.admitting:
            raise ActivityAdmissionError("Storage has paused new admission")
        if request.key in self._activities:
            raise DuplicateActivityError(request.key)
        self._owner(request.key.requester_id)
        now = self._now()
        if request.start_at is not None and request.start_at < now:
            self.store.append("activity_rejected", {"request": request.as_dict(),
                              "reason": "start_in_past", "observed_at": now.isoformat()})
            raise ActivityStartInPastError(request, now)
        start, end = request.planned_times(now)
        entry = _Activity(request, execute, now, start, end)
        self._activities[request.key] = entry
        try:
            observed = self._emit(entry)
            entry.timer = self._spawn(self._notify_end(entry), "ntk-activity-clock:" + request.key.activity_id)
            entry.driver = self._spawn(self._drive(entry), "ntk-activity:" + request.key.activity_id)
        except Exception as exc:
            if entry.timer is not None:
                entry.timer.cancel()
            entry.state = ActivityState.FAILED
            entry.failures = (ActivityFailure(exc),)
            entry.ended_at = self._now()
            entry.done.set()
            self._failed(exc)
            raise
        return observed

    async def _until(self, when):
        while True:
            remaining = (when - self._now()).total_seconds()
            if remaining <= 0:
                return
            await self._clock.sleep(min(remaining, self._interval))

    async def _notify_end(self, entry):
        await asyncio.sleep(0)
        await self._until(entry.end_at)
        if not entry.state.terminal and not entry.notified:
            entry.notified = True
            self._emit(entry, ActivityNoticeKind.PLANNED_END)

    async def _execute(self, entry):
        await asyncio.sleep(0)
        context = _Context(entry.request, entry.start_at, entry.end_at, entry)
        result = entry.execute(context)
        if not inspect.isawaitable(result):
            raise TypeError("Activity execution must return an awaitable")
        return await result

    async def _drive(self, entry):
        # Ownership must be established before any executor or eager factory can run.
        await asyncio.sleep(0)
        entry.entered = True
        try:
            if self._state != RuntimeState.RUNNING:
                self._request_finish(entry, ActivityFinishReason.RUNTIME)
            if entry.finish_reason is None:
                await self._until(entry.start_at)
                await self.store.wait_ready()
                if self._state != RuntimeState.RUNNING:
                    self._request_finish(entry, ActivityFinishReason.RUNTIME)
                    entry.state = ActivityState.STOPPED
                    return
                try:
                    self._owner(entry.request.key.requester_id)
                except ActivityAdmissionError as exc:
                    entry.failures = (ActivityFailure(exc),)
                    entry.state = ActivityState.FAILED
                else:
                    entry.started_at = self._now()
                    entry.started_mono = self._clock.monotonic()
                    entry.state = ActivityState.RUNNING
                    self._emit(entry)
                    entry.worker = self._spawn(self._execute(entry), "ntk-activity-work:" + entry.request.key.activity_id, fatal=False)
                    try:
                        result = await entry.worker
                        entry.result = _freeze_json(result)
                    except asyncio.CancelledError as exc:
                        if entry.finish_reason is None:
                            entry.failures = (ActivityFailure(exc),)
                    except Exception as exc:
                        entry.failures = (ActivityFailure(exc),)
                    entry.state = (ActivityState.FAILED if entry.failures else
                                   ActivityState.STOPPED if entry.finish_reason is not None else ActivityState.COMPLETED)
            else:
                entry.state = ActivityState.STOPPED
        except asyncio.CancelledError as exc:
            entry.state = ActivityState.STOPPED
            if entry.finish_reason is None:
                entry.failures = (ActivityFailure(exc),)
                entry.state = ActivityState.FAILED
        except Exception as exc:
            entry.failures = (ActivityFailure(exc),)
            entry.state = ActivityState.FAILED
            self._failed(exc)
        finally:
            try:
                if entry.timer is not None:
                    entry.timer.cancel()
                    await asyncio.gather(entry.timer, return_exceptions=True)
                if entry.started_mono is not None:
                    entry.elapsed = max(0.0, self._clock.monotonic() - entry.started_mono)
                entry.ended_at = self._now()
                self._emit(entry)
            finally:
                entry.done.set()

    def request_finish(self, key, *, reason=ActivityFinishReason.NYMPH):
        self._check_context()
        if self._state not in (RuntimeState.RUNNING, RuntimeState.STOPPING):
            raise ActivityStateError("TaskManager is not running")
        if not isinstance(reason, ActivityFinishReason) or reason not in (ActivityFinishReason.NYMPH, ActivityFinishReason.CONNECTION_INTERRUPTION):
            raise ValueError("Only Nymph or its connection interruption may request activity finish")
        return self._request_finish(self._entry(key), reason)

    def _request_finish(self, entry, reason, *, override=False):
        if entry.state.terminal or (entry.finish_reason is not None and not override):
            return self._snapshot(entry)
        entry.finish_reason = reason
        entry.finish.set()
        entry.finish_requested_at = self._now()
        entry.state = ActivityState.FINISHING
        observed = self._emit(entry)
        # A pending schedule has no executor to reach a safe point. Wake its wait.
        if (entry.entered and entry.worker is None and entry.driver is not None
                and entry.driver is not asyncio.current_task()):
            entry.driver.cancel()
        return observed

    async def wait(self, key):
        self._check_context()
        entry = self._entry(key)
        if entry.worker is asyncio.current_task() or entry.driver is asyncio.current_task():
            raise ActivityStateError("An activity cannot wait for its own completion")
        await entry.done.wait()
        return self._snapshot(entry)

    async def next_notice(self, requester_id):
        self._check_context()
        self.connections.catalog.get(requester_id)
        if self._state == RuntimeState.NEW:
            raise ActivityStateError("TaskManager has not started")
        queue = self._notices.setdefault(requester_id, asyncio.Queue())
        if queue.empty() and self._state in (RuntimeState.STOPPED, RuntimeState.FAILED):
            raise ActivityStateError("TaskManager notices have ended")
        notice = await queue.get()
        if notice is None:
            queue.put_nowait(None)
            raise ActivityStateError("TaskManager notices have ended")
        return notice

    async def history(self, requester_id):
        """Give Nymph saved evidence; never register or restart an activity from it."""
        self._check_running()
        self.connections.catalog.get(requester_id)
        return await self.store.read_activity_history(requester_id)

    def begin_shutdown(self):
        self._check_context()
        if self._state not in (RuntimeState.STOPPED, RuntimeState.FAILED):
            self._state = RuntimeState.STOPPING

    async def stop(self):
        self._check_context()
        if any(asyncio.current_task() in (entry.driver, entry.worker) for entry in self._activities.values()):
            raise ActivityStateError("An activity cannot stop its own TaskManager")
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._stop_task is None:
            self.begin_shutdown()
            coroutine = self._stop()
            try:
                self._stop_task = asyncio.create_task(coroutine, name="ntk-activities-stop")
            except Exception as exc:
                coroutine.close()
                self._failed(exc)
                # A failing user task factory must not abandon already-owned activities.
                self._stop_task = asyncio.Task(self._stop(), loop=self._loop, name="ntk-activities-stop")
        cancelled = False
        while not self._stop_task.done():
            try:
                await asyncio.shield(self._stop_task)
            except asyncio.CancelledError:
                cancelled = True
        self._stop_task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _stop(self):
        for entry in self._activities.values():
            if entry.timer is not None:
                entry.timer.cancel()
            if not entry.state.terminal:
                try:
                    self._request_finish(entry, ActivityFinishReason.RUNTIME, override=True)
                except Exception as exc:
                    self._failed(exc)
                # Global Runtime shutdown retains the existing cooperative cancellation contract.
                if (entry.entered and entry.driver is not None and not entry.driver.done()
                        and not entry.driver.cancelling()):
                    entry.driver.cancel()
        if self._owned:
            await asyncio.gather(*tuple(self._owned), return_exceptions=True)
        self._state = RuntimeState.FAILED if self._errors else RuntimeState.STOPPED
        for queue in self._notices.values():
            queue.put_nowait(None)
        if self._fatal is not None and not self._fatal.done():
            self._fatal.set_result(None)
        reported = self._fatal.result() if self._fatal_reported else None
        unreported = [error for error in self._errors if error is not reported]
        if len(unreported) == 1:
            raise unreported[0]
        if unreported:
            raise ExceptionGroup("TaskManager infrastructure cleanup failures", unreported)
