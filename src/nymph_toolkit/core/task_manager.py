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
    ActivityCommandStatus, ActivityControlKind,
    ModuleExecutionState, RegistryError, RuntimeState, UnknownActivityError,
)
from nymph_toolkit.contracts.activities import _freeze_json, _json_data, _utc
from .connections import Connections
from ._activity_commands import _Commands
from ._activity_slots import _Slots


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
    _entry: "_Activity" = field(repr=False, compare=False)
    _manager: "TaskManager" = field(repr=False, compare=False)

    @property
    def current_request(self):
        return self._entry.current_request

    @property
    def planned_start_at(self):
        return self._entry.start_at

    @property
    def planned_end_at(self):
        return self._entry.end_at

    @property
    def finish_requested(self):
        return self._entry.finish_reason is not None

    @property
    def finish_reason(self):
        return self._entry.finish_reason

    @property
    def pause_requested(self):
        return self._entry.state == ActivityState.PAUSING

    async def wait_for_control(self):
        while True:
            if self.finish_requested:
                return ActivityControlKind.FINISH
            if self.pause_requested:
                return ActivityControlKind.PAUSE
            await self._entry.control.wait()

    async def checkpoint(self):
        return await self._manager._checkpoint(self._entry)

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
    current_request: ActivityRequest | None = None
    revision: int = 0
    scheduled_revision: int = 0
    commands: dict = field(default_factory=dict)
    start_changed: asyncio.Event = field(default_factory=asyncio.Event)
    end_changed: asyncio.Event = field(default_factory=asyncio.Event)
    supports_pause: bool = False
    control: asyncio.Event = field(default_factory=asyncio.Event)
    resumed: asyncio.Event = field(default_factory=asyncio.Event)
    granted: asyncio.Event = field(default_factory=asyncio.Event)
    ticket: int | None = None
    slot: bool = False
    paused_at: datetime | None = None
    resumed_at: datetime | None = None
    paused_mono: float | None = None
    paused_total: float = 0.0

    def __post_init__(self):
        self.current_request = self.request


class TaskManager(_Slots, _Commands):
    """One-loop activities sharing the existing connection catalog and store."""

    def __init__(self, connections: Connections, *, clock_check_interval: float, clock=None, max_running=None):
        if not isinstance(connections, Connections):
            raise TypeError("connections must be a Connections instance")
        if (type(clock_check_interval) not in (int, float)
                or not math.isfinite(clock_check_interval) or clock_check_interval <= 0):
            raise ValueError("clock_check_interval must be finite positive seconds")
        if max_running is not None and (type(max_running) is not int or max_running <= 0):
            raise ValueError("max_running must be None or a positive integer")
        self._max_running = max_running
        self._running_slots = 0
        self._ticket = 0
        self._ready = {}
        self._dispatch_changed = asyncio.Event()
        self._dispatcher = None
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
        self._dispatcher = self._spawn(self._dispatch(), "ntk-activity-dispatch")

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
        paused = entry.paused_total
        if entry.paused_mono is not None:
            paused += max(0.0, self._clock.monotonic() - entry.paused_mono)
        return ActivitySnapshot(
            request=entry.request, state=entry.state, accepted_at=entry.accepted_at,
            planned_start_at=entry.start_at, planned_end_at=entry.end_at,
            started_at=entry.started_at, ended_at=entry.ended_at, elapsed_seconds=elapsed,
            finish_reason=entry.finish_reason, finish_requested_at=entry.finish_requested_at,
            planned_end_notified=entry.notified, result=entry.result, failures=entry.failures,
            current_request=entry.current_request, revision=entry.revision,
            scheduled_revision=entry.scheduled_revision, execution_seconds=max(0.0, elapsed - paused),
        )

    def snapshot(self, key):
        self._check_context()
        return self._snapshot(self._entry(key))

    def activities(self, requester_id=None):
        self._check_context()
        return tuple(self._snapshot(entry) for key, entry in sorted(self._activities.items())
                     if requester_id is None or key.requester_id == requester_id)

    def _emit(self, entry, kind=ActivityNoticeKind.STATE_CHANGED, *, command=None):
        observed = self._snapshot(entry) if command is None else command.result.snapshot
        at = self._now()
        self._sequence += 1
        record = {"request": entry.request.as_dict(), "state": observed.state.value,
                  "notice_sequence": self._sequence, "observed_at": at.isoformat(),
                  "elapsed_seconds": observed.elapsed_seconds, "planned_end_notified": entry.notified,
                  "finish_reason": None if entry.finish_reason is None else entry.finish_reason.value,
                  "result": _json_data(entry.result),
                  "failures": [{"type": type(f.exception).__name__, "message": str(f.exception)} for f in entry.failures]}
        record.update(current_request=entry.current_request.as_dict(), revision=entry.revision,
                      scheduled_revision=entry.scheduled_revision, execution_seconds=observed.execution_seconds,
                      paused_at=None if entry.paused_at is None else entry.paused_at.isoformat(),
                      resumed_at=None if entry.resumed_at is None else entry.resumed_at.isoformat())
        for name in ("accepted_at", "planned_start_at", "planned_end_at", "started_at", "ended_at", "finish_requested_at"):
            value = getattr(observed, name)
            record[name] = None if value is None else value.isoformat()
        if command is not None:
            record["command"] = {"command_id": command.command_id, "operation": command.operation,
                                 "expected_revision": command.expected_revision,
                                 "change": None if command.change is None else command.change.as_dict(),
                                 "received_at": command.received_at.isoformat(),
                                 "status": command.result.status.value, "reason": command.result.reason}
        history_kind, record = self._history_record(entry, kind, record, command)
        self.store.append(history_kind, record)
        queue = self._notices.setdefault(entry.request.key.requester_id, asyncio.Queue())
        queue.put_nowait(ActivityNotice(self._sequence, kind, at, command.result.snapshot if command else observed,
                                       command.result if command else None))
        return observed

    def _history_record(self, entry, kind, record, command):
        return "activity_v06_" + ("command" if command is not None else kind.value), record

    def submit(self, request: ActivityRequest, execute: Callable, *, supports_pause=False):
        self._check_running()
        if not isinstance(request, ActivityRequest) or not callable(execute):
            raise TypeError("submit requires an ActivityRequest and async execution callable")
        if type(supports_pause) is not bool:
            raise TypeError("supports_pause must be a bool")
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
        entry = _Activity(request, execute, now, start, end, supports_pause=supports_pause)
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

    async def _until(self, entry, name, changed):
        while True:
            changed.clear()
            remaining = (getattr(entry, name) - self._now()).total_seconds()
            if remaining <= 0:
                return
            async def delay():
                # Resolve at actual task entry; an injectable clock may advance before then.
                seconds = (getattr(entry, name) - self._now()).total_seconds()
                await self._clock.sleep(max(0, min(seconds, self._interval)))
            sleeper = self._spawn(delay(), "ntk-activity-delay", fatal=False)
            try:
                wake = self._spawn(changed.wait(), "ntk-activity-revision", fatal=False)
                try:
                    done, _ = await asyncio.wait((sleeper, wake), return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    wake.cancel()
                    await asyncio.gather(wake, return_exceptions=True)
            finally:
                sleeper.cancel()
                await asyncio.gather(sleeper, return_exceptions=True)

    def _reach_end(self, entry):
        if not entry.state.terminal and not entry.notified and entry.end_at <= self._now():
            entry.notified = True
            entry.revision += 1
            self._emit(entry, ActivityNoticeKind.PLANNED_END)

    async def _notify_end(self, entry):
        await asyncio.sleep(0)
        while not entry.state.terminal:
            await self._until(entry, "end_at", entry.end_changed)
            self._reach_end(entry)
            entry.end_changed.clear()
            await entry.end_changed.wait()

    async def _execute(self, entry):
        await asyncio.sleep(0)
        context = _Context(entry.request, entry, self)
        result = entry.execute(context)
        if not inspect.isawaitable(result):
            raise TypeError("Activity execution must return an awaitable")
        return await result

    def _unpause_clock(self, entry):
        if entry.paused_mono is not None:
            entry.paused_total += max(0.0, self._clock.monotonic() - entry.paused_mono)
            entry.paused_mono = None

    async def _checkpoint(self, entry):
        self._check_context()
        if asyncio.current_task() is not entry.worker:
            raise ActivityStateError("Only the activity executor may acknowledge its safe point")
        if entry.finish_reason is not None:
            return entry.finish_reason
        if entry.state != ActivityState.PAUSING:
            return None
        entry.resumed.clear()
        entry.control.clear()
        entry.state = ActivityState.PAUSED
        entry.paused_at = self._now()
        entry.paused_mono = self._clock.monotonic()
        entry.revision += 1
        self._emit(entry)
        self._release_slot(entry)
        self._resolve_commands(entry, "pause", ActivityCommandStatus.APPLIED)
        await entry.resumed.wait()
        return entry.finish_reason

    async def _drive(self, entry):
        # Ownership must be established before any executor or eager factory can run.
        await asyncio.sleep(0)
        entry.entered = True
        try:
            if self._state != RuntimeState.RUNNING:
                self._request_finish(entry, ActivityFinishReason.RUNTIME)
            if entry.finish_reason is None:
                await self._await_start(entry)
                if self._state != RuntimeState.RUNNING:
                    self._request_finish(entry, ActivityFinishReason.RUNTIME)
                    return
                try:
                    self._owner(entry.request.key.requester_id)
                except ActivityAdmissionError as exc:
                    entry.failures = (ActivityFailure(exc),)
                else:
                    entry.started_at = self._now()
                    entry.started_mono = self._clock.monotonic()
                    entry.state = ActivityState.RUNNING
                    entry.revision += 1
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
        except asyncio.CancelledError as exc:
            if entry.finish_reason is None:
                entry.failures = (ActivityFailure(exc),)
        except Exception as exc:
            entry.failures = (ActivityFailure(exc),)
            self._failed(exc)
        finally:
            try:
                if entry.timer is not None:
                    entry.timer.cancel()
                    while not entry.timer.done():
                        try:
                            await asyncio.shield(entry.timer)
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            break  # Owned timer failure is observed by _spawn.
                if entry.started_mono is not None:
                    self._unpause_clock(entry)
                    entry.elapsed = max(0.0, self._clock.monotonic() - entry.started_mono)
                entry.ended_at = self._now()
                entry.state = (ActivityState.FAILED if entry.failures else
                               ActivityState.STOPPED if entry.finish_reason is not None else ActivityState.COMPLETED)
                entry.revision += 1
                self._emit(entry)
                self._resolve_commands(entry, None, ActivityCommandStatus.FAILED if entry.failures else ActivityCommandStatus.SUPERSEDED,
                                       "executor_failed" if entry.failures else "finished" if entry.finish_reason else "completed")
            finally:
                self._remove_ready(entry)
                self._release_slot(entry)
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
        entry.control.set()
        self._withdraw_resume(entry)
        self._unpause_clock(entry)
        entry.resumed.set()
        entry.finish_requested_at = self._now()
        entry.state = ActivityState.FINISHING
        entry.revision += 1
        observed = self._emit(entry)
        self._resolve_commands(entry, None, ActivityCommandStatus.SUPERSEDED, "finished")
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
        if self._dispatcher is not None:
            self._dispatcher.cancel()
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
