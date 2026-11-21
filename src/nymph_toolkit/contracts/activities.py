"""Immutable activity inputs and observations; activity decisions belong to Nymph."""

# SPDX-License-Identifier: Apache-2.0
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, StrEnum
import math
from types import MappingProxyType
from typing import Protocol

from . import LifecycleFailure


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be nonempty without surrounding whitespace")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("Time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Time must have an explicit UTC offset")
    try:
        return value.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("Time is outside the UTC datetime range") from exc


def _freeze_json(value, ancestors=None):
    """Copy JSON-compatible data recursively, retaining no mutable caller containers."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if not isinstance(value, (Mapping, tuple, list)):
        raise TypeError("Activity data must be JSON-compatible")
    ancestors = set() if ancestors is None else ancestors
    identity = id(value)
    if identity in ancestors:
        raise ValueError("Activity data must not contain cycles")
    ancestors.add(identity)
    try:
        if isinstance(value, Mapping):
            if not all(isinstance(key, str) for key in value):
                raise TypeError("Activity object keys must be strings")
            return MappingProxyType({key: _freeze_json(item, ancestors) for key, item in value.items()})
        return tuple(_freeze_json(item, ancestors) for item in value)
    finally:
        ancestors.remove(identity)


def _json_data(value):
    """Return a mutable, JSON-serializable copy of an already validated value."""
    if isinstance(value, Mapping):
        return {key: _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    return value


@dataclass(frozen=True, order=True)
class ActivityKey:
    requester_id: str
    activity_id: str

    def __post_init__(self) -> None:
        _identifier(self.requester_id, "requester_id")
        _identifier(self.activity_id, "activity_id")


@dataclass(frozen=True)
class ActivityRequest:
    key: ActivityKey
    content: str
    start_at: datetime | None
    duration: timedelta
    parameters: Mapping[str, object] = field(default_factory=dict, hash=False)
    priority: int = 0

    def __post_init__(self) -> None:
        if type(self.priority) is not int:
            raise TypeError("priority must be an integer, not bool")
        if not isinstance(self.key, ActivityKey):
            raise TypeError("key must be an ActivityKey")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        if not self.content.strip():
            raise ValueError("content must describe the requested activity")
        if not isinstance(self.duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if self.duration <= timedelta(0):
            raise ValueError("duration must be positive")
        if self.start_at is not None:
            object.__setattr__(self, "start_at", _utc(self.start_at))
            self.planned_times(self.start_at)
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be an object with string keys")
        object.__setattr__(self, "parameters", _freeze_json(self.parameters))

    def planned_times(self, accepted_at: datetime) -> tuple[datetime, datetime]:
        """Resolve an explicit 'now'; do not move an explicitly specified start."""
        accepted_at = _utc(accepted_at)
        start = accepted_at if self.start_at is None else self.start_at
        try:
            return start, start + self.duration
        except OverflowError as exc:
            raise ValueError("Planned end is outside the datetime range") from exc

    def as_dict(self) -> dict:
        """An independent record of Nymph's input, not an executable restoration."""
        duration_us = ((self.duration.days * 86400 + self.duration.seconds) * 1_000_000
                       + self.duration.microseconds)
        return {"requester_id": self.key.requester_id, "activity_id": self.key.activity_id,
                "content": self.content, "start_at": None if self.start_at is None else self.start_at.isoformat(),
                "duration_us": duration_us, "parameters": _json_data(self.parameters), "priority": self.priority}


class _Unchanged(Enum):
    VALUE = "unchanged"


UNCHANGED = _Unchanged.VALUE


@dataclass(frozen=True)
class ActivityChange:
    start_at: datetime | None | _Unchanged = UNCHANGED
    duration: timedelta | _Unchanged = UNCHANGED
    priority: int | _Unchanged = UNCHANGED

    def __post_init__(self):
        if all(value is UNCHANGED for value in (self.start_at, self.duration, self.priority)):
            raise ValueError("An activity change must specify at least one field")
        if self.start_at is not UNCHANGED and self.start_at is not None:
            object.__setattr__(self, "start_at", _utc(self.start_at))
        if self.duration is not UNCHANGED:
            if not isinstance(self.duration, timedelta):
                raise TypeError("duration must be a timedelta")
            if self.duration <= timedelta(0):
                raise ValueError("duration must be positive")
        if self.priority is not UNCHANGED and type(self.priority) is not int:
            raise TypeError("priority must be an integer, not bool")

    def as_dict(self):
        result = {}
        if self.start_at is not UNCHANGED:
            result["start_at"] = None if self.start_at is None else self.start_at.isoformat()
        if self.duration is not UNCHANGED:
            result["duration_us"] = self.duration // timedelta(microseconds=1)
        if self.priority is not UNCHANGED:
            result["priority"] = self.priority
        return result


class ActivityState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    RESUME_PENDING = "resume_pending"
    FINISHING = "finishing"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def terminal(self) -> bool:
        return self in (ActivityState.COMPLETED, ActivityState.FAILED, ActivityState.STOPPED)


class ActivityFinishReason(StrEnum):
    NYMPH = "nymph"
    RUNTIME = "runtime"
    CONNECTION_INTERRUPTION = "connection_interruption"


@dataclass(frozen=True)
class ActivityFailure:
    exception: BaseException

    def __post_init__(self) -> None:
        if not isinstance(self.exception, BaseException):
            raise TypeError("failure must retain the original exception")


@dataclass(frozen=True)
class ActivitySnapshot:
    request: ActivityRequest
    state: ActivityState
    accepted_at: datetime
    planned_start_at: datetime
    planned_end_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    elapsed_seconds: float = 0.0
    finish_reason: ActivityFinishReason | None = None
    finish_requested_at: datetime | None = None
    planned_end_notified: bool = False
    result: object = field(default=None, hash=False)
    failures: tuple[ActivityFailure, ...] = ()
    revision: int = 0
    scheduled_revision: int = 0
    current_request: ActivityRequest | None = None
    execution_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.request, ActivityRequest) or not isinstance(self.state, ActivityState):
            raise TypeError("Snapshot requires an ActivityRequest and ActivityState")
        if self.current_request is None:
            object.__setattr__(self, "current_request", self.request)
        if not isinstance(self.current_request, ActivityRequest) or self.current_request.key != self.request.key:
            raise ValueError("current_request must retain the activity key")
        for value in (self.revision, self.scheduled_revision):
            if type(value) is not int or value < 0:
                raise ValueError("Revisions must be nonnegative integers")
        for name in ("accepted_at", "planned_start_at", "planned_end_at"):
            object.__setattr__(self, name, _utc(getattr(self, name)))
        for name in ("started_at", "ended_at", "finish_requested_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value))
        if (type(self.elapsed_seconds) not in (int, float)
                or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0):
            raise ValueError("elapsed_seconds must be finite nonnegative seconds")
        if (type(self.execution_seconds) not in (int, float) or not math.isfinite(self.execution_seconds)
                or not 0 <= self.execution_seconds <= self.elapsed_seconds):
            raise ValueError("execution_seconds must be between zero and elapsed_seconds")
        if self.finish_reason is not None and not isinstance(self.finish_reason, ActivityFinishReason):
            raise TypeError("finish_reason must be an ActivityFinishReason")
        if type(self.planned_end_notified) is not bool:
            raise TypeError("planned_end_notified must be a bool")
        failures = tuple(self.failures)
        if not all(isinstance(item, ActivityFailure) for item in failures):
            raise TypeError("failures must contain ActivityFailure values")
        object.__setattr__(self, "failures", failures)
        object.__setattr__(self, "result", _freeze_json(self.result))


class ActivityNoticeKind(StrEnum):
    STATE_CHANGED = "state_changed"
    PLANNED_END = "planned_end"
    COMMAND_RESULT = "command_result"


class ActivityControlKind(StrEnum):
    PAUSE = "pause"
    FINISH = "finish"


class ActivityCommandStatus(StrEnum):
    ACCEPTED = "accepted"
    APPLIED = "applied"
    NO_CHANGE = "no_change"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    FAILED = "failed"

    @property
    def terminal(self):
        return self != ActivityCommandStatus.ACCEPTED


@dataclass(frozen=True)
class ActivityCommandResult:
    key: ActivityKey
    command_id: str
    operation: str
    received_at: datetime
    status: ActivityCommandStatus
    reason: str | None
    snapshot: ActivitySnapshot

    def __post_init__(self):
        _identifier(self.command_id, "command_id")
        if self.operation not in ("change", "pause", "resume"):
            raise ValueError("Unknown activity command operation")
        if not isinstance(self.status, ActivityCommandStatus):
            raise TypeError("status must be an ActivityCommandStatus")
        if not isinstance(self.key, ActivityKey) or not isinstance(self.snapshot, ActivitySnapshot) or self.snapshot.request.key != self.key:
            raise ValueError("Command result must reference its activity snapshot")
        if self.reason is not None:
            _identifier(self.reason, "reason")
        object.__setattr__(self, "received_at", _utc(self.received_at))


@dataclass(frozen=True)
class ActivityNotice:
    sequence: int
    kind: ActivityNoticeKind
    at: datetime
    snapshot: ActivitySnapshot
    command: ActivityCommandResult | None = None

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence <= 0:
            raise ValueError("Notice sequence must be a positive integer")
        if not isinstance(self.kind, ActivityNoticeKind) or not isinstance(self.snapshot, ActivitySnapshot):
            raise TypeError("Notice requires an ActivityNoticeKind and ActivitySnapshot")
        object.__setattr__(self, "at", _utc(self.at))
        if self.kind == ActivityNoticeKind.COMMAND_RESULT:
            if not isinstance(self.command, ActivityCommandResult) or self.command.snapshot != self.snapshot:
                raise ValueError("Command notice requires the matching command result")
        elif self.command is not None:
            raise ValueError("Only command notices may contain a command result")


class ActivityContext(Protocol):
    """Executor input and cooperative finish signal; not an activity decision maker."""

    @property
    def request(self) -> ActivityRequest: ...

    @property
    def current_request(self) -> ActivityRequest: ...

    @property
    def pause_requested(self) -> bool: ...

    async def wait_for_control(self) -> ActivityControlKind: ...

    async def checkpoint(self) -> ActivityFinishReason | None: ...

    @property
    def planned_start_at(self) -> datetime: ...

    @property
    def planned_end_at(self) -> datetime: ...

    @property
    def finish_requested(self) -> bool: ...

    @property
    def finish_reason(self) -> ActivityFinishReason | None: ...

    async def wait_for_finish(self) -> ActivityFinishReason: ...


ActivityExecutor = Callable[[ActivityContext], Awaitable[object]]


class ActivityError(RuntimeError):
    """An activity request could not be applied; not a link or Core health failure."""


class ActivityStateError(ActivityError):
    pass


class ActivityAdmissionError(ActivityError):
    pass


class DuplicateActivityError(ActivityError):
    pass


class UnknownActivityError(ActivityError):
    pass


class ActivityStartInPastError(ActivityError):
    def __init__(self, request: ActivityRequest, observed_at: datetime) -> None:
        self.request = request
        self.observed_at = _utc(observed_at)
        super().__init__("Requested start is in the past; Nymph must specify a new start")


class TaskManagerLifecycleFailure(ActivityError):
    """Infrastructure failures, distinct from an individual activity's result."""

    def __init__(self, failures: tuple[LifecycleFailure, ...]):
        if not failures:
            raise ValueError("TaskManagerLifecycleFailure requires failures")
        self.failures = tuple(failures)
        super().__init__("; ".join(f"{f.phase}: {type(f.exception).__name__}: {f.exception}" for f in failures))


@dataclass(frozen=True)
class ActivityHistoryRecord:
    run_id: str
    sequence: int
    at: datetime
    kind: str
    data: Mapping[str, object]

    def __post_init__(self):
        object.__setattr__(self, "at", _utc(self.at))
        object.__setattr__(self, "data", _freeze_json(self.data))


@dataclass(frozen=True)
class ActivityHistoryIssue:
    path: str
    line: int | None
    message: str


@dataclass(frozen=True)
class ActivityHistory:
    """Readable saved evidence plus problems; absence of problems is not completeness."""
    records: tuple[ActivityHistoryRecord, ...]
    issues: tuple[ActivityHistoryIssue, ...]

    def __post_init__(self):
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "issues", tuple(self.issues))
