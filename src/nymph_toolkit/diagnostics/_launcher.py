"""Explicit operator commands for one locally launched Runtime."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from uuid import uuid4

from nymph_toolkit.contracts import (
    ActivityKey, ActivityState, ActivityStateError, RuntimeFailure, RuntimeState, RuntimeStateError,
    UnknownActivityError,
)
from nymph_toolkit.core import Runtime

from ._session import DiagnosticSession


class BrowserLauncher:
    """Own one HybridGroup Runtime and expose explicitly scoped local controls."""

    def __init__(self, group, *, owner_id, slots=None, queries=None):
        if type(owner_id) is not str or owner_id not in group.modules or group.activities is None:
            raise ValueError("Configure an activity manager and a registered activity owner before the launcher")
        self._owner = owner_id
        self._manager = group.activities
        self._start = None
        self._closing = False
        self.runtime = Runtime(group)
        self.diagnostics = DiagnosticSession(group, self.runtime, slots=slots, queries=queries)
        self.diagnostics._launcher = self

    async def open(self):
        """Serve the launcher before accepting an explicit Runtime start."""
        return await self.diagnostics.start()

    async def _start_runtime(self):
        try:
            await self.runtime.start()
        except (RuntimeFailure, RuntimeStateError):
            # The Runtime retains the failure and reports it through its lifecycle state.
            pass

    def _command(self, operation, arguments):
        if self._closing or self.diagnostics.url is None:
            return {"status": "not_available"}
        if type(operation) is not str or type(arguments) is not dict:
            return {"status": "invalid"}
        if operation == "start_runtime":
            if arguments:
                return {"status": "invalid"}
            if self._start is not None or self.runtime.state != RuntimeState.NEW:
                return {"status": "not_available"}
            self._start = asyncio.create_task(self._start_runtime(), name="ntk-browser-runtime-start")
            return {"status": "accepted"}
        if operation not in ("pause", "resume", "finish") or arguments.keys() != {"activity_id", "expected_revision"}:
            return {"status": "invalid"}
        revision = arguments["expected_revision"]
        if (type(arguments["activity_id"]) is not str or type(revision) is not int
                or not 0 <= revision <= 2**53 - 1):
            return {"status": "invalid"}
        if self.runtime.state != RuntimeState.RUNNING:
            return {"status": "not_available"}
        try:
            key = ActivityKey(self._owner, arguments["activity_id"])
            snapshot = self._manager.snapshot(key)
        except ValueError:
            return {"status": "invalid"}
        except UnknownActivityError:
            return {"status": "not_available"}
        if snapshot.revision != revision:
            return {"status": "conflict"}
        try:
            if operation == "finish":
                if snapshot.state.terminal or snapshot.state == ActivityState.FINISHING:
                    return {"status": "not_available"}
                self._manager.request_finish(key)
                return {"status": "accepted"}
            request = self._manager.request_pause if operation == "pause" else self._manager.request_resume
            result = request(key, command_id=uuid4().hex, expected_revision=revision)
            return {"status": result.status.value}
        except ActivityStateError:
            return {"status": "not_available"}

    async def close(self):
        """Stop the owned Runtime cooperatively, then collect the diagnostic process."""
        self._closing = True
        try:
            if self._start is not None or self.runtime.state != RuntimeState.NEW:
                await self.runtime.stop()
        finally:
            try:
                if self._start is not None:
                    await self._start
            finally:
                await self.diagnostics.close()
