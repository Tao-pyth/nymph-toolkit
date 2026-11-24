"""Agency-owned execution loop using only public Task and Module contracts."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import math
from uuid import uuid4

from nymph_toolkit.contracts import (
    ActivityChange, ActivityCommandStatus, ActivityFinishReason, ActivityKey, ActivityRequest, ActivityState,
    LinkFailure, OperatingState, OperationFailure, OutcomeUnknown, TemporaryUnavailable, Usage,
)
from nymph_toolkit.contracts.agency import AGENCY_ACTIVITIES_KEY, AGENCY_KEY
from . import _Agency, _settled
from ._model import dump, fields, identifier, integer, request, snapshot, timestamp


def _identity(plan):
    return dump({k: plan[k] for k in (
        "template_id", "goal_id", "parameters", "executor_module_id", "executor_id", "content")})


def _activity(plan):
    return ActivityRequest(ActivityKey(plan["requester_id"], plan["activity_id"]), plan["content"],
                           None if plan["start_at"] is None else timestamp(plan["start_at"]),
                           timedelta(microseconds=plan["duration_us"]), plan["parameters"], plan["priority"])


class _CycleFailure(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class _CapacityWait(Exception):
    pass


class ExecutingAgency(_Agency):
    def __init__(self, context, config):
        fields(config, "path memory_module_id cognition_module_id catalog execution" +
               (" persona" if type(config) is dict and "persona" in config else ""))
        options = snapshot(config["execution"], 8192)
        fields(options, "poll_seconds max_activities pause_executors")
        interval = options["poll_seconds"]
        if type(interval) not in (int, float) or not math.isfinite(interval) or not .02 <= interval <= 60:
            raise ValueError("poll_seconds requires a finite number in 0.02..60")
        integer(options["max_activities"], 1, 128)
        pause = options["pause_executors"]
        if type(pause) is not list or len(pause) > 16:
            raise ValueError("pause_executors requires a list of at most 16 executors")
        self.pause_executors = set()
        for item in pause:
            fields(item, "module_id executor_id")
            pair = (identifier(item["module_id"]), identifier(item["executor_id"]))
            if pair in self.pause_executors:
                raise ValueError("Duplicate pause executor")
            self.pause_executors.add(pair)
        super().__init__(context, {k: v for k, v in config.items() if k != "execution"})
        self.interval, self.max_activities = interval, options["max_activities"]
        self.wake = asyncio.Event()
        self.session = None
        self.sessions = {}
        self.session_results = {}
        self.records = []
        self.events = deque(maxlen=32)
        self.foreground = self.pending = self.uncertain = self.last_signature = None
        self.mode, self.error = "inactive", None
        self.revision = self.counter = 0
        self.epoch = uuid4().hex
        self.observed = self.initial = self.last_observe = self.last_decision = None
        self.core_operation = None
        self.reconsider = False
        context.provide(AGENCY_ACTIVITIES_KEY, {name: getattr(self, name)
                        for name in ("activate", "observe", "status", "halt", "history")})

    async def _usage(self, active):
        # Control/status remain available while a decision is reading or saving.
        control = Usage(OperatingState.RUNNING, True, 0, 32)
        await self.context.core.publish_usage(control, contracts={
            AGENCY_KEY: Usage(OperatingState.RUNNING, True, active, 1), AGENCY_ACTIVITIES_KEY: control})

    def _observation(self, value):
        fields(value, "state goals available")
        checked = request(dict(value, decision_id="validate", now="2026-01-01T00:00:00Z", current=None), self.catalog)
        return {k: checked[k] for k in ("state", "goals", "available")}

    @staticmethod
    def _invalid(error):
        return OperationFailure("agency.invalid", str(error))

    async def activate(self, session_id, observation):
        try:
            identifier(session_id)
            observed = self._observation(observation)
        except (ValueError, TypeError, RecursionError, OverflowError) as error:
            return self._invalid(error)
        if not self.ready or self.closing:
            return TemporaryUnavailable("Agency is not accepting sessions")
        if session_id in self.sessions:
            if self.sessions[session_id] != observed:
                return OperationFailure("agency.session_conflict", "Session ID already has different initial input")
            return await self.status() if session_id == self.session else snapshot(self.session_results[session_id], 49152)
        if (self.uncertain is not None or self.mode not in ("inactive", "stopped", "failed")
                or any(not r["snapshot"].state.terminal or not r["snapshot"].cleanup_confirmed for r in self.records)):
            return TemporaryUnavailable("A session still owns unfinished activities")
        if len(self.sessions) >= 64:
            return OperationFailure("agency.session_full", "64 sessions retained in this runtime")
        if self.session is not None:
            self.session_results[self.session] = await self.status()
        self.sessions[session_id] = observed
        self.session, self.observed, self.initial = session_id, observed, observed
        self.revision = 0
        self.records, self.events = [], deque(maxlen=32)
        self.foreground = self.pending = self.last_signature = self.last_observe = self.last_decision = self.error = None
        self.mode = "active"
        self.wake.set()
        return await self.status()

    async def observe(self, session_id, expected_revision, observation):
        try:
            identifier(session_id); integer(expected_revision, 0, 2**63 - 2)
            observed = self._observation(observation)
        except (ValueError, TypeError, RecursionError, OverflowError) as error:
            return self._invalid(error)
        if session_id != self.session:
            return OperationFailure("agency.session_conflict", "Not the current session")
        if self.last_observe == (expected_revision, observed):
            return await self.status()
        if expected_revision != self.revision:
            return OperationFailure("agency.revision_conflict", "Observation revision changed")
        if self.mode not in ("active", "waiting") or self.closing:
            return TemporaryUnavailable("Session is not accepting observations")
        self.last_observe = (expected_revision, observed)
        self.observed, self.revision = observed, self.revision + 1
        self.mode = "active"
        self.wake.set()
        return await self.status()

    async def halt(self, session_id):
        try:
            identifier(session_id)
        except (ValueError, TypeError) as error:
            return self._invalid(error)
        if session_id != self.session:
            return OperationFailure("agency.session_conflict", "Not the current session")
        if self.mode not in ("stopped", "inactive", "failed"):
            self.mode = "stopping"
            self.wake.set()
        return await self.status()

    async def history(self):
        return await self.context.core.activity("history", timeout=5)

    async def _recover(self, key, interruption_id=None):
        # The requesting function owns real activities now. Complete their safe
        # interruption before acknowledging the Connections interruption.
        link = self.links.pop(key, None)
        if link is not None:
            await link.close()
        if not self.closing:
            self.mode = "stopping"
            while any(not r["snapshot"].state.terminal for r in self.records):
                await self._finish_owned(reason=ActivityFinishReason.CONNECTION_INTERRUPTION)
                if any(not r["snapshot"].state.terminal for r in self.records):
                    await asyncio.sleep(self.interval)
            if any(not r["snapshot"].cleanup_confirmed for r in self.records):
                raise _CycleFailure("agency.cleanup_unknown", "Cannot acknowledge unfinished cleanup")
        await super()._recover(key, interruption_id)

    async def status(self, *, after=0, limit=8):
        try:
            integer(after, 0, 128); integer(limit, 1, 16)
        except (ValueError, TypeError) as error:
            return self._invalid(error)
        activities = []
        for index, record in enumerate(self.records[after:after + limit], after + 1):
            observed = record["snapshot"]
            activities.append(dict(index=index, activity_id=record["key"].activity_id,
                decision_id=record["decision"]["decision_id"], template_id=record["plan"]["template_id"],
                state=observed.state.value, revision=observed.revision, scheduled_revision=observed.scheduled_revision,
                planned_start_at=observed.planned_start_at.isoformat(), planned_end_at=observed.planned_end_at.isoformat(),
                planned_end_notified=observed.planned_end_notified, priority=observed.current_request.priority,
                duration_us=observed.current_request.duration // timedelta(microseconds=1),
                elapsed_seconds=observed.elapsed_seconds, execution_seconds=observed.execution_seconds,
                timing_confirmed=observed.timing_confirmed, cleanup_confirmed=observed.cleanup_confirmed,
                failures=[type(f.exception).__name__ for f in observed.failures]))
        return snapshot(dict(session_id=self.session, state=self.mode, observation_revision=self.revision,
            last_decision_id=self.last_decision, foreground=None if self.foreground is None else self.foreground["key"].activity_id,
            total_activities=len(self.records), activities=activities, next_after=after+len(activities),
            recent_operations=list(self.events), unknown=self.uncertain, error=self.error), 49152)

    def _event(self, operation, decision_id, status, reason=None):
        self.events.append(dict(operation=operation, decision_id=decision_id, status=status,
                                reason=None if reason is None else str(reason)[:512]))

    async def _core(self, operation, *args, **kwargs):
        async def complete():
            try:
                if operation == "submit":
                    return await self.context.core.submit_remote(*args, timeout=5, **kwargs)
                return await self.context.core.activity(operation, *args, timeout=5, **kwargs)
            except OutcomeUnknown as unknown:
                self.uncertain = {"operation": operation, "request_id": unknown.request_id}
                while True:
                    try:
                        value = self.context.core.result(unknown.request_id)
                    except OutcomeUnknown:
                        await asyncio.sleep(self.interval)
                        continue
                    except Exception:
                        # Failed resolution is not a known non-execution result.
                        raise
                    self.context.core.release(unknown.request_id)
                    self.uncertain = None
                    return value
        self.core_operation = asyncio.create_task(complete())
        return await _settled(self.core_operation)

    def _signature(self):
        def phase(state):
            # Starting an already chosen activity does not require reading its
            # dependencies again while its executor is using them.
            return "executing" if state in (ActivityState.PENDING, ActivityState.STARTING, ActivityState.RUNNING) else state
        return (self.revision, tuple((r["key"].activity_id, phase(r["snapshot"].state),
            dump(r["snapshot"].current_request.as_dict()), r["snapshot"].scheduled_revision,
            r["snapshot"].planned_end_notified) for r in self.records))

    async def _refresh(self):
        for record in self.records:
            if not record["snapshot"].state.terminal:
                record["snapshot"] = await self._core("snapshot", record["key"])
            observed = record["snapshot"]
            if observed.state.terminal and not record["finished"]:
                record["finished"] = True
                record["finished_revision"] = self.revision
                if observed.state == ActivityState.FAILED or not observed.cleanup_confirmed:
                    raise _CycleFailure("agency.execution_failed", "Activity failed or cleanup is unconfirmed")
        if self.foreground is not None and self.foreground["snapshot"].state.terminal:
            self.foreground = None

    async def _decision_for(self, current=None):
        self.counter += 1
        decision_id = f"cycle-{self.epoch}-{self.counter}"
        observation = self.observed
        value = dict(observation, decision_id=decision_id, now=datetime.now(timezone.utc).isoformat(), current=None)
        if current is not None:
            state = current["snapshot"]
            value["current"] = dict(decision_id=current["decision"]["decision_id"], state=state.state.value,
                revision=state.revision, planned_end_notified=state.planned_end_notified,
                supports_pause=(current["plan"]["executor_module_id"], current["plan"]["executor_id"]) in self.pause_executors)
        result = await self.decide(value)
        if isinstance(result, TemporaryUnavailable):
            raise _CapacityWait(result.message)
        if isinstance(result, (OperationFailure, LinkFailure)):
            raise _CycleFailure(getattr(result, "code", type(result).__name__), str(result))
        self.last_decision = decision_id
        return result

    async def _resolve_command(self):
        if self.pending is None:
            return False
        record, decision, command_id = self.pending
        observed = record["snapshot"]
        if observed.state in (ActivityState.PAUSING, ActivityState.RESUME_PENDING, ActivityState.STARTING):
            return True
        result = await self._core("command", record["key"], command_id=command_id)
        self.pending = None
        await self._command_result(record, decision, result)
        self.last_signature = None
        return False

    async def _command_result(self, record, decision, result):
        op = decision["directive"]
        record["snapshot"] = result.snapshot
        self._event(op, decision["decision_id"], result.status.value, result.reason)
        if result.status == ActivityCommandStatus.ACCEPTED:
            self.pending = (record, decision, result.command_id)
            return
        if result.status not in (ActivityCommandStatus.APPLIED, ActivityCommandStatus.NO_CHANGE):
            raise _CycleFailure("agency.command_rejected", result.reason or result.status.value)
        if op == "pause":
            self.foreground = None
        else:
            record["plan"], record["decision"] = decision["plan"], decision
            if op == "resume":
                self.foreground = record
        if op in ("pause", "resume"):
            self.reconsider = True

    async def _apply(self, decision, record):
        operation, plan = decision["directive"], decision["plan"]
        if operation in ("idle", "continue", "wait"):
            self.mode = "waiting" if operation == "idle" else "active"
            return
        self.mode = "active"
        if operation == "start":
            old = next((r for r in self.records if r["snapshot"].state == ActivityState.PAUSED and _identity(r["plan"]) == _identity(plan)), None)
            if old is not None:
                revision = self.revision
                resumed = await self._decision_for(old)
                if self.mode == "stopping" or self.closing or revision != self.revision:
                    return
                if resumed["directive"] != "resume":
                    raise _CycleFailure("agency.observation_changed", "Selection changed while preparing resume")
                return await self._apply(resumed, old)
            if any(r["finished"] and r["finished_revision"] == self.revision and _identity(r["plan"]) == _identity(plan) for r in self.records):
                self.mode = "waiting"
                self._event("start", decision["decision_id"], "not_repeated", "completed_in_observation")
                return
            if len(self.records) >= self.max_activities:
                raise _CycleFailure("agency.activity_full", "Session activity limit reached")
            # A new decision is not sent if halt/update arrived while reading evidence.
            observed = await self._core("submit", _activity(plan), plan["executor_module_id"], plan["executor_id"], plan["parameters"])
            record = dict(key=observed.request.key, decision=decision, plan=plan, snapshot=observed,
                          finished=False, finished_revision=None, finish_sent=False)
            self.records.append(record); self.foreground = record
            self._event("start", decision["decision_id"], "registered")
        elif operation == "finish":
            record["snapshot"] = await self._core("finish", record["key"])
            record["finish_sent"] = True
            self._event("finish", decision["decision_id"], "requested")
        else:
            command_id = "agency-" + hashlib.sha256(decision["decision_id"].encode()).hexdigest()
            kwargs = dict(command_id=command_id, expected_revision=decision["target"]["expected_revision"])
            if operation == "change":
                changes = dict(duration=timedelta(microseconds=plan["duration_us"]), priority=plan["priority"])
                if record["snapshot"].state == ActivityState.PENDING:
                    changes["start_at"] = None if plan["start_at"] is None else timestamp(plan["start_at"])
                kwargs["change"] = ActivityChange(**changes)
            result = await self._core(operation, record["key"], **kwargs)
            await self._command_result(record, decision, result)

    async def _finish_owned(self, *, reason=ActivityFinishReason.NYMPH):
        for record in self.records:
            if not record["snapshot"].state.terminal:
                if not record["finish_sent"]:
                    record["snapshot"] = await self._core("finish", record["key"], reason=reason)
                    record["finish_sent"] = True
                record["snapshot"] = await self._core("snapshot", record["key"])
        if all(r["snapshot"].state.terminal for r in self.records):
            if any(not r["snapshot"].cleanup_confirmed for r in self.records):
                self.error = self.error or {"code": "agency.cleanup_unknown", "message": "Cleanup not confirmed"}
            self.mode = "failed" if self.error else "stopped"
            self.pending = self.foreground = None

    async def _tick(self):
        if self.mode == "stopping":
            await self._finish_owned()
            return
        if self.mode not in ("active", "waiting"):
            return
        await self._refresh()
        if await self._resolve_command():
            return
        signature = self._signature()
        if signature == self.last_signature:
            return
        revision = self.revision
        try:
            decision = await self._decision_for(self.foreground)
        except _CapacityWait as waiting:
            self.mode = "waiting" if self.mode != "stopping" else self.mode
            self._event("decide", None, "unavailable", str(waiting))
            self.last_signature = signature
            return
        if self.mode == "stopping" or self.closing or revision != self.revision:
            return  # Saved decision is observable, but has not been applied.
        self.reconsider = False
        try:
            await self._apply(decision, self.foreground)
        except _CapacityWait as waiting:
            self.mode = "waiting" if self.mode != "stopping" else self.mode
            self._event("decide", None, "unavailable", str(waiting))
            self.last_signature = signature
            return
        # Own applied changes are already represented; do not undo an extension
        # simply because the Core revision changed as a result of that extension.
        self.last_signature = (self._signature() if self.revision == revision
            and not self.reconsider else None)

    async def run(self):
        try:
            while True:
                self.wake.clear()
                try:
                    await self._tick()
                except Exception as error:
                    if isinstance(error, OutcomeUnknown):
                        self.error = {"code": "OutcomeUnknown", "message": str(error)[:512],
                                      "request_id": error.request_id, "scope": "decision_dependency",
                                      "cleanup_error": self.error}
                    else:
                        self.error = self.error or {"code": getattr(error, "code", type(error).__name__), "message": str(error)[:512]}
                    # If cleanup itself fails, stop issuing requests and preserve uncertainty.
                    self.mode = "failed" if self.mode == "stopping" or self.uncertain else "stopping"
                try:
                    await asyncio.wait_for(self.wake.wait(), self.interval)
                except TimeoutError:
                    pass
        finally:
            self.ready = False
            self.closing = True

    async def _close(self):
        # Runtime owns stopping TaskManager before tearing down module services.
        # Drain admitted decision/management operations; never restart the loop.
        try:
            if self.core_operation is not None:
                await asyncio.gather(self.core_operation, return_exceptions=True)
        finally:
            await super()._close()
