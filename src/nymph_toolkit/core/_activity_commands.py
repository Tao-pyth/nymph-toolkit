"""Synchronous command arbitration on the TaskManager's owning event loop."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import dataclass, field, replace

from nymph_toolkit.contracts import (
    UNCHANGED, ActivityAdmissionError, ActivityChange, ActivityCommandResult,
    ActivityCommandStatus as Status, ActivityNoticeKind, ActivityState,
)
from nymph_toolkit.contracts.activities import _identifier


@dataclass
class _Command:
    command_id: str
    operation: str
    received_at: object
    expected_revision: int
    change: ActivityChange | None
    result: ActivityCommandResult | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


class _Commands:
    def request_pause(self, key, *, command_id, expected_revision):
        entry, command, existing = self._command(key, "pause", None, command_id, expected_revision)
        if existing is not None:
            return existing
        if not entry.supports_pause:
            return self._result(entry, command, Status.REJECTED, "unsupported_operation")
        if entry.state == ActivityState.RUNNING:
            entry.state = ActivityState.PAUSING
            entry.revision += 1
            self._emit(entry)
            entry.control.set()
            return self._result(entry, command, Status.ACCEPTED)
        if entry.state == ActivityState.PAUSING:
            return self._result(entry, command, Status.ACCEPTED)
        if entry.state == ActivityState.PAUSED:
            return self._result(entry, command, Status.NO_CHANGE)
        if entry.state == ActivityState.RESUME_PENDING:
            entry.state = ActivityState.PAUSED
            entry.revision += 1
            self._withdraw_resume(entry)
            self._emit(entry)
            self._resolve_commands(entry, "resume", Status.SUPERSEDED, "pause_requested")
            return self._result(entry, command, Status.APPLIED)
        return self._result(entry, command, Status.REJECTED, "invalid_state")

    def request_resume(self, key, *, command_id, expected_revision):
        entry, command, existing = self._command(key, "resume", None, command_id, expected_revision)
        if existing is not None:
            return existing
        if entry.state == ActivityState.RUNNING:
            return self._result(entry, command, Status.NO_CHANGE)
        if entry.state == ActivityState.RESUME_PENDING:
            return self._result(entry, command, Status.ACCEPTED)
        if entry.state != ActivityState.PAUSED:
            return self._result(entry, command, Status.REJECTED, "invalid_state")
        entry.state = ActivityState.RESUME_PENDING
        entry.revision += 1
        self._emit(entry)
        result = self._result(entry, command, Status.ACCEPTED)
        self._enqueue_resume(entry)
        return result

    def _command(self, key, operation, change, command_id, expected_revision):
        self._check_running()
        entry = self._entry(key)
        _identifier(command_id, "command_id")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision must be a nonnegative integer")
        command = _Command(command_id, operation, self._now(), expected_revision, change)
        previous = entry.commands.get(command_id)
        if previous is not None:
            if (previous.operation, previous.change, previous.expected_revision) == (operation, change, expected_revision):
                return entry, previous, previous.result
            return entry, command, self._result(entry, command, Status.REJECTED, "command_id_conflict")
        entry.commands[command_id] = command
        if expected_revision != entry.revision:
            return entry, command, self._result(entry, command, Status.REJECTED, "revision_conflict")
        if entry.state.terminal or entry.state == ActivityState.FINISHING:
            return entry, command, self._result(entry, command, Status.REJECTED, "invalid_state")
        if operation in ("change", "resume"):
            if self.store.failure is not None or not self.store.admitting:
                return entry, command, self._result(entry, command, Status.REJECTED, "storage_unavailable")
            try:
                self._owner(key.requester_id)
            except ActivityAdmissionError:
                return entry, command, self._result(entry, command, Status.REJECTED, "requester_unavailable")
        return entry, command, None

    def _result(self, entry, command, status, reason=None):
        result = ActivityCommandResult(entry.request.key, command.command_id, command.operation,
                                       command.received_at, status, reason, self._snapshot(entry))
        command.result = result
        self._emit(entry, ActivityNoticeKind.COMMAND_RESULT, command=command)
        if status.terminal:
            command.done.set()
        return result

    def _resolve_commands(self, entry, operation, status, reason=None):
        for command in tuple(entry.commands.values()):
            if (command.result is not None and not command.result.status.terminal
                    and (operation is None or command.operation == operation)):
                self._result(entry, command, status, reason)

    def command_result(self, key, command_id):
        self._check_context()
        _identifier(command_id, "command_id")
        return self._entry(key).commands[command_id].result

    async def wait_command(self, key, command_id):
        self._check_context()
        _identifier(command_id, "command_id")
        entry = self._entry(key)
        command = entry.commands[command_id]
        if asyncio.current_task() in (entry.worker, entry.driver) and not command.done.is_set():
            from nymph_toolkit.contracts import ActivityStateError
            raise ActivityStateError("An activity cannot wait for its own pending command")
        await command.done.wait()
        return command.result

    def change(self, key, change, *, command_id, expected_revision):
        if not isinstance(change, ActivityChange):
            raise TypeError("change must be an ActivityChange")
        # Validate combined datetime range before registering a command or changing state.
        self._check_running()
        entry = self._entry(key)
        _identifier(command_id, "command_id")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision must be a nonnegative integer")
        if command_id in entry.commands:
            _, _, existing = self._command(key, "change", change, command_id, expected_revision)
            return existing
        current = entry.current_request
        start = entry.start_at if change.start_at is UNCHANGED else self._now() if change.start_at is None else change.start_at
        updated = replace(current, start_at=start,
                          duration=current.duration if change.duration is UNCHANGED else change.duration,
                          priority=current.priority if change.priority is UNCHANGED else change.priority)
        entry, command, existing = self._command(key, "change", change, command_id, expected_revision)
        if existing is not None:
            return existing
        if change.start_at is not UNCHANGED:
            if entry.state != ActivityState.PENDING or entry.started_at is not None:
                return self._result(entry, command, Status.REJECTED, "invalid_state")
            if change.start_at is not None and start < command.received_at:
                return self._result(entry, command, Status.REJECTED, "start_in_past")
        end = start + updated.duration
        timing = (start, end) != (entry.start_at, entry.end_at)
        if not timing and updated.priority == current.priority:
            return self._result(entry, command, Status.NO_CHANGE)
        # Preserve the original immediate input unless the caller explicitly replaces it.
        if change.start_at is UNCHANGED:
            updated = replace(updated, start_at=current.start_at)
        entry.current_request = updated
        entry.start_at, entry.end_at = start, end
        if timing:
            entry.scheduled_revision += 1
            entry.notified = False
            entry.start_changed.set()
            entry.end_changed.set()
        entry.revision += 1
        self._emit(entry)
        if timing:
            self._reach_end(entry)
        self._schedule_changed(entry)
        return self._result(entry, command, Status.APPLIED)

    def _schedule_changed(self, entry):
        """Hook for the execution-slot scheduler; changes themselves never start work."""
