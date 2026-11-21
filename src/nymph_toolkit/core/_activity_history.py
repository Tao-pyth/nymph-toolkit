"""Read saved activity evidence without restoring tasks or changing any files."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta
import json
import math
from pathlib import Path

from nymph_toolkit.contracts import (
    ActivityFinishReason, ActivityHistory, ActivityHistoryIssue, ActivityHistoryRecord,
    ActivityKey, ActivityRequest, ActivityState,
    ActivityChange, ActivityCommandStatus,
)
from nymph_toolkit.contracts.activities import _utc, _identifier
from ._storage_io import _HISTORY, _object


def _time(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO datetime string")
    return _utc(datetime.fromisoformat(value))


def _positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Sequence or duration must be a positive integer")


def _constant(value):
    raise ValueError("Non-finite JSON number: " + value)


def _request(data, *, version=5):
    if not isinstance(data, dict) or set(data) != {
        "requester_id", "activity_id", "content", "start_at", "duration_us", "parameters",
        *({"priority"} if version >= 6 else set())
    }:
        raise ValueError("Invalid activity request fields")
    _positive(data["duration_us"])
    return ActivityRequest(ActivityKey(data["requester_id"], data["activity_id"]), data["content"],
                           None if data["start_at"] is None else _time(data["start_at"]),
                           timedelta(microseconds=data["duration_us"]), data["parameters"],
                           data["priority"] if version >= 6 else 0)


def _nonnegative_int(value):
    if type(value) is not int or value < 0:
        raise ValueError("Revision must be a nonnegative integer")


def _command(data, state):
    if not isinstance(data, dict) or set(data) != {
        "command_id", "operation", "expected_revision", "change", "received_at", "status", "reason"
    }:
        raise ValueError("Invalid activity command fields")
    _identifier(data["command_id"], "command_id")
    _nonnegative_int(data["expected_revision"])
    _time(data["received_at"])
    status = ActivityCommandStatus(data["status"])
    if data["reason"] is not None:
        _identifier(data["reason"], "reason")
    if data["operation"] == "change":
        change = data["change"]
        if not isinstance(change, dict) or set(change) - {"start_at", "duration_us", "priority"}:
            raise ValueError("Invalid activity change fields")
        values = dict(change)
        if "start_at" in values and values["start_at"] is not None:
            values["start_at"] = _time(values["start_at"])
        if "duration_us" in values:
            _positive(values["duration_us"])
            values["duration"] = timedelta(microseconds=values.pop("duration_us"))
        ActivityChange(**values)
        if status == ActivityCommandStatus.ACCEPTED:
            raise ValueError("Synchronous change cannot remain accepted")
    elif data["operation"] in ("pause", "resume"):
        if data["change"] is not None:
            raise ValueError("Control command cannot contain changed fields")
        if status == ActivityCommandStatus.ACCEPTED and state != {
            "pause": ActivityState.PAUSING, "resume": ActivityState.RESUME_PENDING
        }[data["operation"]]:
            raise ValueError("Accepted command has inconsistent state")
    else:
        raise ValueError("Unknown activity command")


def _validate_activity(kind, data):
    if not isinstance(data, dict):
        raise ValueError("Activity data must be an object")
    if kind not in ("activity_rejected", "activity_state_changed", "activity_planned_end",
                    "activity_v06_state_changed", "activity_v06_planned_end", "activity_v06_command",
                    "activity_v07_state_changed", "activity_v07_planned_end", "activity_v07_command"):
        raise ValueError("Unknown activity history kind")
    version = 7 if kind.startswith("activity_v07_") else 6 if kind.startswith("activity_v06_") else 5
    if kind == "activity_rejected" and isinstance(data.get("request"), dict) and "priority" in data["request"]:
        version = 6
    request = _request(data.get("request"), version=version)
    if kind == "activity_rejected":
        if set(data) != {"request", "reason", "observed_at"} or data["reason"] != "start_in_past":
            raise ValueError("Unknown activity rejection")
        observed = _time(data["observed_at"])
        if request.start_at is None or request.start_at >= observed:
            raise ValueError("Past-start rejection does not match its request")
        return request.key.requester_id
    if kind not in ("activity_state_changed", "activity_planned_end",
                    "activity_v06_state_changed", "activity_v06_planned_end", "activity_v06_command",
                    "activity_v07_state_changed", "activity_v07_planned_end", "activity_v07_command"):
        raise ValueError("Unknown activity history kind")
    times = ("accepted_at", "planned_start_at", "planned_end_at", "started_at", "ended_at", "finish_requested_at")
    expected = {"request", "state", "notice_sequence", "observed_at", "elapsed_seconds",
                "planned_end_notified", "finish_reason", "result", "failures", *times}
    if version >= 6:
        expected.update({"current_request", "revision", "scheduled_revision", "execution_seconds", "paused_at", "resumed_at"})
    if version == 7:
        expected.update({"timing_confirmed", "cleanup_confirmed", "executor_module_id", "executor_id"})
        for name in ("timing_confirmed", "cleanup_confirmed"):
            if type(data.get(name)) is not bool:
                raise ValueError("Invalid remote evidence flag")
        _identifier(data.get("executor_module_id"), "executor_module_id")
        _identifier(data.get("executor_id"), "executor_id")
    if kind in ("activity_v06_command", "activity_v07_command"):
        expected.add("command")
    if set(data) != expected:
        raise ValueError("Invalid activity observation fields")
    _positive(data["notice_sequence"])
    _time(data["observed_at"])
    for name in times:
        if name in times[:3] or data[name] is not None:
            _time(data[name])
    current = _request(data["current_request"], version=6) if version >= 6 else request
    if (current.key, current.content, current.parameters) != (request.key, request.content, request.parameters):
        raise ValueError("Current request changes immutable activity input")
    start, end = current.planned_times(_time(data["accepted_at"]))
    if start != _time(data["planned_start_at"]) or end != _time(data["planned_end_at"]):
        raise ValueError("Planned times do not match Nymph's request")
    elapsed = data["elapsed_seconds"]
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Invalid elapsed seconds")
    if type(data["planned_end_notified"]) is not bool:
        raise ValueError("Invalid planned-end notification flag")
    state = ActivityState(data["state"])
    if version < 7 and state == ActivityState.STARTING:
        raise ValueError("Remote starting state in legacy history")
    if version == 5 and state in (ActivityState.PAUSING, ActivityState.PAUSED, ActivityState.RESUME_PENDING):
        raise ValueError("New activity state in legacy history")
    if version >= 6:
        _nonnegative_int(data["revision"])
        _nonnegative_int(data["scheduled_revision"])
        if data["scheduled_revision"] > data["revision"]:
            raise ValueError("Schedule revision exceeds activity revision")
        execution = data["execution_seconds"]
        if type(execution) not in (int, float) or not math.isfinite(execution) or not 0 <= execution <= elapsed:
            raise ValueError("Invalid execution seconds")
        for name in ("paused_at", "resumed_at"):
            if data[name] is not None:
                _time(data[name])
        if state in (ActivityState.PAUSED, ActivityState.RESUME_PENDING) and data["paused_at"] is None:
            raise ValueError("Paused activity has no acknowledged pause")
        if kind in ("activity_v06_command", "activity_v07_command"):
            _command(data["command"], state)
    unknown_end = version == 7 and not data["cleanup_confirmed"] and state == ActivityState.FAILED and data["ended_at"] is None
    if not unknown_end and state.terminal != (data["ended_at"] is not None):
        raise ValueError("Terminal state and end timestamp disagree")
    if (data["finish_reason"] is None) != (data["finish_requested_at"] is None):
        raise ValueError("Finish reason and timestamp disagree")
    if data["finish_reason"] is not None:
        ActivityFinishReason(data["finish_reason"])
    if kind in ("activity_planned_end", "activity_v06_planned_end", "activity_v07_planned_end") and (not data["planned_end_notified"] or state.terminal):
        raise ValueError("Invalid planned-end observation")
    if not isinstance(data["failures"], list):
        raise ValueError("Failures must be an array")
    for failure in data["failures"]:
        if (not isinstance(failure, dict) or set(failure) != {"type", "message"}
                or not all(isinstance(value, str) for value in failure.values())):
            raise ValueError("Invalid historical failure description")
    if state == ActivityState.COMPLETED and (data["started_at"] is None or data["failures"] or data["finish_reason"] is not None):
        raise ValueError("Completed activity has inconsistent execution evidence")
    if state == ActivityState.FAILED and not data["failures"]:
        raise ValueError("Failed activity has no failure description")
    if state in (ActivityState.STOPPED, ActivityState.FINISHING) and data["finish_reason"] is None:
        raise ValueError("Stopped or finishing activity has no finish reason")
    if state == ActivityState.PENDING and (data["started_at"] is not None or data["finish_reason"] is not None):
        raise ValueError("Pending activity has execution or finish evidence")
    if state in (ActivityState.RUNNING, ActivityState.PAUSING, ActivityState.PAUSED, ActivityState.RESUME_PENDING) and (data["started_at"] is None or data["finish_reason"] is not None):
        raise ValueError("Running activity has inconsistent execution evidence")
    if data["started_at"] is None and elapsed != 0:
        raise ValueError("Unstarted activity has elapsed execution time")
    return request.key.requester_id


def read_activity_history(root: Path, archive: Path, current_run_id: str, requester_id: str) -> ActivityHistory:
    records, seen, conflicts, issues = {}, {}, set(), []
    for directory in (root, archive):
        try:
            if not directory.exists():
                continue
            paths = sorted(directory.iterdir())
        except OSError as exc:
            issues.append(ActivityHistoryIssue(str(directory), None, str(exc)))
            continue
        for path in paths:
            match = _HISTORY.fullmatch(path.name)
            if match is None or match[2] == current_run_id:
                continue
            try:
                if path.is_symlink() or not path.is_file():
                    issues.append(ActivityHistoryIssue(str(path), None, "History is not a regular nonsymlink file"))
                    continue
                with path.open("rb") as stream:
                    for line_number, raw in enumerate(stream, 1):
                        try:
                            if not raw.endswith(b"\n"):
                                raise ValueError("Incomplete history line: missing final newline")
                            record = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
                            if not isinstance(record, dict) or set(record) != {"format", "run_id", "sequence", "at", "kind", "data"}:
                                raise ValueError("Invalid history envelope")
                            if record["format"] != "ntk.history.v1" or record["run_id"] != match[2]:
                                raise ValueError("Unknown history format or mismatched run ID")
                            _positive(record["sequence"])
                            at = _time(record["at"])
                            if at.date().isoformat() != match[1]:
                                raise ValueError("History timestamp does not match its filename date")
                            kind = record["kind"]
                            if not isinstance(kind, str) or not kind or not isinstance(record["data"], dict):
                                raise ValueError("Invalid history kind or data")
                            key = (record["run_id"], record["sequence"])
                            canonical = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False)
                            if key in seen:
                                if seen[key] != canonical:
                                    conflicts.add(key)
                                    records.pop(key, None)
                                    raise ValueError("Conflicting records have the same run ID and sequence")
                                continue
                            seen[key] = canonical
                            if kind.startswith("activity_"):
                                owner = _validate_activity(kind, record["data"])
                                if owner == requester_id and key not in conflicts:
                                    records[key] = ActivityHistoryRecord(record["run_id"], record["sequence"], at, kind, record["data"])
                        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
                            issues.append(ActivityHistoryIssue(str(path), line_number, str(exc)))
            except OSError as exc:
                issues.append(ActivityHistoryIssue(str(path), None, str(exc)))
    return ActivityHistory(tuple(records[key] for key in sorted(records)), tuple(issues))
