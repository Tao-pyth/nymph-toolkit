"""TaskManager extension driven by executor evidence across process boundaries."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import dataclass, field, replace

from nymph_toolkit.contracts import (
    ActivityCommandStatus, ActivityFailure, ActivityFinishReason, ActivityNoticeKind,
    ActivityState, PeerClosed, RemoteError, RuntimeState,
)
from .task_manager import TaskManager
from ._wire import json_value


@dataclass
class _Remote:
    module_id: str
    executor_id: str
    arguments: object
    done: asyncio.Event = field(default_factory=asyncio.Event)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    elapsed: float = 0.0
    execution: float = 0.0
    timing_confirmed: bool = False
    cleanup_confirmed: bool = False
    execution_ended: bool = False
    dispatch_entered: bool = False
    resume: bool = False
    error: Exception | None = None
    result: object = None
    control_task: asyncio.Task | None = None


class HybridTaskManager(TaskManager):
    def __init__(self, group, *, clock_check_interval, max_running=None):
        super().__init__(group.connections, clock_check_interval=clock_check_interval, max_running=max_running)
        self.group = group
        self._remote = {}

    def submit_remote(self, request, module_id, executor_id, arguments=None):
        service = self.group.modules[module_id]
        if executor_id not in service.executors:
            raise ValueError("Unknown executor ID")
        remote = _Remote(module_id, executor_id, json_value(arguments))
        if request.key in self._activities:
            from nymph_toolkit.contracts import DuplicateActivityError
            raise DuplicateActivityError(request.key)
        self._remote[request.key] = remote
        async def placeholder(context):
            raise AssertionError("Remote executor must use its evidence-driven driver")
        try:
            return super().submit(request, placeholder, supports_pause=service.executors[executor_id])
        except BaseException:
            self._remote.pop(request.key, None)
            raise

    def _snapshot(self, entry):
        snapshot = super()._snapshot(entry)
        remote = self._remote.get(entry.request.key)
        if remote is None:
            return snapshot
        return replace(snapshot, elapsed_seconds=remote.elapsed, execution_seconds=min(remote.elapsed, remote.execution),
                       timing_confirmed=remote.timing_confirmed, cleanup_confirmed=remote.cleanup_confirmed)

    def _history_record(self, entry, kind, record, command):
        remote = self._remote.get(entry.request.key)
        if remote is None:
            return super()._history_record(entry, kind, record, command)
        record.update(timing_confirmed=remote.timing_confirmed, cleanup_confirmed=remote.cleanup_confirmed,
                      executor_module_id=remote.module_id, executor_id=remote.executor_id)
        return "activity_v07_" + ("command" if command is not None else kind.value), record

    def _emit(self, entry, kind=ActivityNoticeKind.STATE_CHANGED, *, command=None):
        result = super()._emit(entry, kind, command=command)
        remote = self._remote.get(entry.request.key)
        if remote is not None:
            remote.changed.set()
        return result

    def _grant_resume(self, entry):
        remote = self._remote.get(entry.request.key)
        if remote is None:
            return super()._grant_resume(entry)
        remote.resume = True
        remote.changed.set()

    def request_pause(self, key, *, command_id, expected_revision):
        remote = self._remote.get(key)
        entry = self._entry(key)
        if remote is None or entry.state != ActivityState.RESUME_PENDING or not remote.resume:
            return super().request_pause(key, command_id=command_id, expected_revision=expected_revision)
        entry, command, existing = self._command(key, "pause", None, command_id, expected_revision)
        if existing is not None:
            return existing
        # A granted resume may already be executing remotely. Keep its slot until
        # the next safe-point report rather than treating it as a queued resume.
        entry.state = ActivityState.PAUSING
        entry.revision += 1
        self._emit(entry)
        self._resolve_commands(entry, "resume", ActivityCommandStatus.SUPERSEDED, "pause_requested")
        return self._result(entry, command, ActivityCommandStatus.ACCEPTED)

    async def _controls(self, entry, remote):
        await remote.ready.wait()
        while not remote.done.is_set():
            await remote.changed.wait()
            remote.changed.clear()
            if remote.done.is_set():
                return
            await self.group.modules[remote.module_id].invoke("activity_control", {
                "key": entry.request.key, "revision": entry.revision, "request": entry.current_request,
                "start_at": entry.start_at, "end_at": entry.end_at, "finish_reason": entry.finish_reason,
                "pause": entry.state == ActivityState.PAUSING, "resume": remote.resume})

    async def _run_remote(self, entry, remote):
        remote.dispatch_entered = True
        service = self.group.modules[remote.module_id]
        submitted = False
        try:
            await service.invoke("activity_begin", {"key": entry.request.key, "request": entry.request,
                "current_request": entry.current_request, "start_at": entry.start_at, "end_at": entry.end_at,
                "executor_id": remote.executor_id, "arguments": remote.arguments})
            submitted = True
            remote.ready.set()
            remote.changed.set()
            remote.control_task = self._spawn(self._controls(entry, remote), "ntk-remote-controls", fatal=True)
            await remote.done.wait()
        except asyncio.CancelledError:
            try:
                await service.invoke("activity_cancel", {"key": entry.request.key})
            except Exception:
                pass
            # Do not release the slot while a child may still execute. The group's
            # shutdown guardian confirms process exit when cooperation fails.
            if submitted or entry.started_at is not None:
                while not remote.done.is_set():
                    try:
                        await asyncio.shield(remote.done.wait())
                    except asyncio.CancelledError:
                        pass
            else:
                remote.error = PeerClosed("Dispatch cancellation outcome is not confirmed")
                self.group.fail(remote.error)
                if service.process is not None:
                    await service.process.wait()
                remote.execution_ended = True
            raise
        except Exception as exc:
            remote.error = exc
            if not remote.done.is_set() and not isinstance(exc, RemoteError):
                self.group.fail(exc)
                if service.process is not None:
                    await service.process.wait()
            remote.execution_ended = True
        finally:
            if remote.control_task is not None:
                remote.control_task.cancel()
                await asyncio.gather(remote.control_task, return_exceptions=True)
        if remote.error is not None:
            raise remote.error
        return remote.result

    async def _drive(self, entry):
        await asyncio.sleep(0)
        remote = self._remote.get(entry.request.key)
        if remote is None:
            return await super()._drive(entry)
        entry.entered = True
        try:
            if self.state != RuntimeState.RUNNING:
                self._request_finish(entry, ActivityFinishReason.RUNTIME)
            if entry.finish_reason is None:
                await self._await_start(entry)
                if entry.finish_reason is None and self.state == RuntimeState.RUNNING:
                    self._owner(entry.request.key.requester_id)
                    entry.state = ActivityState.STARTING
                    entry.revision += 1
                    self._emit(entry)
                    entry.worker = self._spawn(self._run_remote(entry, remote), "ntk-remote-activity", fatal=False)
                    entry.result = await entry.worker
        except asyncio.CancelledError:
            if remote.error is not None:
                entry.failures = (ActivityFailure(remote.error),)
        except Exception as exc:
            entry.failures = (ActivityFailure(exc),)
        finally:
            try:
                if entry.timer is not None:
                    entry.timer.cancel()
                    await asyncio.gather(entry.timer, return_exceptions=True)
                if entry.started_at is None and not remote.dispatch_entered:
                    entry.ended_at = self._now()
                    remote.cleanup_confirmed = remote.timing_confirmed = remote.execution_ended = True
                entry.state = (ActivityState.FAILED if entry.failures else
                               ActivityState.STOPPED if entry.finish_reason else ActivityState.COMPLETED)
                entry.revision += 1
                self._emit(entry)
                self._resolve_commands(entry, None, ActivityCommandStatus.FAILED if entry.failures else ActivityCommandStatus.SUPERSEDED,
                                       "executor_failed" if entry.failures else "finished")
            finally:
                self._remove_ready(entry)
                if remote.execution_ended or entry.worker is None:
                    self._release_slot(entry)
                entry.done.set()

    async def _remote_event(self, module_id, data):
        key = data["key"]
        remote, entry = self._remote[key], self._entry(key)
        if remote.module_id != module_id or remote.done.is_set():
            raise ValueError("Stale or mismatched activity report")
        elapsed, execution = data["elapsed"], data["execution"]
        if not 0 <= execution <= elapsed or elapsed < remote.elapsed or execution < remote.execution:
            raise ValueError("Invalid executor timing evidence")
        remote.elapsed, remote.execution = elapsed, execution
        phase = data["phase"]
        if phase == "started":
            if entry.started_at is not None:
                raise ValueError("Duplicate start report")
            entry.started_at = data["at"]
            if entry.finish_reason is None:
                entry.state = ActivityState.RUNNING
            remote.timing_confirmed = False
        elif phase == "paused":
            entry.paused_at = data["at"]
            remote.timing_confirmed = True
            if entry.finish_reason is None:
                entry.state = ActivityState.PAUSED
                self._release_slot(entry)
        elif phase == "resumed":
            if not remote.resume:
                raise ValueError("Resume was not granted")
            remote.resume = False
            entry.resumed_at = data["at"]
            remote.timing_confirmed = False
            if entry.finish_reason is None and entry.state != ActivityState.PAUSING:
                entry.state = ActivityState.RUNNING
        elif phase == "ended":
            entry.ended_at = data["at"]
            remote.cleanup_confirmed = remote.timing_confirmed = remote.execution_ended = True
            remote.result, remote.error = data["result"], data["error"]
            if data["cancelled"] and entry.finish_reason is None:
                remote.error = RemoteError(module_id, "CancelledError", "Executor cancelled without a finish instruction")
            remote.done.set()
            return None
        else:
            raise ValueError("Unknown activity report phase")
        entry.revision += 1
        self._emit(entry)
        if phase == "paused" and entry.finish_reason is None:
            self._resolve_commands(entry, "pause", ActivityCommandStatus.APPLIED)
        elif phase == "resumed" and entry.finish_reason is None:
            self._resolve_commands(entry, "resume", ActivityCommandStatus.APPLIED)

    def _module_lost(self, module_id):
        for key, remote in self._remote.items():
            if remote.module_id == module_id and not remote.done.is_set():
                remote.error = PeerClosed("Executor process ended; result/cleanup and unforwarded history may be unknown")
                remote.execution_ended = True
                remote.timing_confirmed = remote.cleanup_confirmed = False
                remote.done.set()

    async def _client(self, module_id, operation, payload):
        if operation == "activity_submit":
            if payload["request"].key.requester_id != module_id:
                raise ValueError("Activity requester must match calling module")
            return self.submit_remote(**payload)
        key = payload.get("key") if payload else None
        if key is not None and key.requester_id != module_id:
            raise ValueError("Activity key must belong to calling module")
        arguments = {} if payload is None else {k: v for k, v in payload.items() if k != "key"}
        name = operation.removeprefix("activity_")
        if name == "snapshot":
            return self.snapshot(key)
        if name == "change":
            return self.change(key, **arguments)
        if name in ("pause", "resume", "finish"):
            return getattr(self, "request_" + name)(key, **arguments)
        if name == "wait":
            return await self.wait(key)
        if name == "command":
            return await self.wait_command(key, **arguments)
        if name == "notice":
            return await self.next_notice(module_id)
        if name == "history":
            return await self.history(module_id)
        raise ValueError("Unknown activity operation")
