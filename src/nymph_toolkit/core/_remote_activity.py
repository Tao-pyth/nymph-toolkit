"""Executor-side continuation and monotonic evidence; no activity value decisions."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timezone

from nymph_toolkit.contracts import ActivityControlKind, ActivityFinishReason, RemoteError
from ._wire import json_value


class _ExecutionContext:
    def __init__(self, host, payload):
        self.host, self.payload = host, payload
        self.request = payload["request"]
        self.current_request = payload["current_request"]
        self.planned_start_at, self.planned_end_at = payload["start_at"], payload["end_at"]
        self.finish_reason = None
        self.pause_requested = False
        self._control, self._resume = asyncio.Event(), asyncio.Event()
        self._revision = -1
        self.task = None
        self.started = None
        self._active = None
        self._execution = 0.0
        self.entered = False
        self.cancel_requested = False

    @property
    def finish_requested(self):
        return self.finish_reason is not None

    def control(self, payload):
        if payload["revision"] < self._revision:
            return
        self._revision = payload["revision"]
        self.current_request = payload["request"]
        self.planned_start_at, self.planned_end_at = payload["start_at"], payload["end_at"]
        self.finish_reason = payload["finish_reason"]
        self.pause_requested = payload["pause"]
        if self.finish_requested or self.pause_requested:
            self._control.set()
        else:
            self._control.clear()
        if payload["resume"] or self.finish_requested:
            self._resume.set()

    def _stop_clock(self):
        if self._active is not None:
            self._execution += max(0, asyncio.get_running_loop().time() - self._active)
            self._active = None

    async def report(self, phase, *, result=None, error=None, cancelled=False):
        self._stop_clock()
        now = asyncio.get_running_loop().time()
        return await self.host.node.event("activity", {"key": self.request.key, "phase": phase,
                    "at": datetime.now(timezone.utc), "elapsed": 0.0 if self.started is None else now - self.started,
                    "execution": self._execution, "result": result, "error": error, "cancelled": cancelled})

    async def wait_for_control(self):
        await self._control.wait()
        return ActivityControlKind.FINISH if self.finish_requested else ActivityControlKind.PAUSE

    async def wait_for_finish(self):
        while not self.finish_requested:
            await self._control.wait()
            if not self.finish_requested:
                await self.checkpoint()
        return self.finish_reason

    async def checkpoint(self):
        if self.finish_requested:
            return self.finish_reason
        if not self.pause_requested:
            return None
        self._resume.clear()
        await self.report("paused")
        await self._resume.wait()
        if self.finish_requested:
            self._active = asyncio.get_running_loop().time()
            return self.finish_reason
        await self.report("resumed")
        self._active = asyncio.get_running_loop().time()
        return None


class ExecutorHost:
    def __init__(self, node):
        self.node, self.jobs = node, {}

    async def dispatch(self, operation, payload):
        key = payload["key"]
        if operation == "activity_begin":
            if key in self.jobs:
                raise ValueError("Activity key was already dispatched")
            handler, _ = self.node.context.executors[payload["executor_id"]]
            context = _ExecutionContext(self, payload)
            self.jobs[key] = context
            context.task = asyncio.create_task(self._run(context, handler), name=f"ntk-remote-work:{key.activity_id}")
            return None
        context = self.jobs[key]
        if operation == "activity_control":
            context.control(payload)
        elif operation == "activity_cancel":
            if context.task is not None and not context.task.done():
                if context.entered:
                    context.task.cancel()
                else:
                    context.cancel_requested = True
        else:
            raise ValueError("Unknown executor control")

    async def _run(self, context, handler):
        context.entered = True
        result = error = None
        cancelled = False
        try:
            if context.cancel_requested:
                raise asyncio.CancelledError
            context.started = asyncio.get_running_loop().time()
            await context.report("started")
            context._active = asyncio.get_running_loop().time()
            result = json_value(await handler(context, context.payload["arguments"]))
        except asyncio.CancelledError:
            cancelled = True
        except Exception as exc:
            error = RemoteError(self.node.spec.module_id, type(exc).__name__, str(exc))
        finally:
            try:
                await context.report("ended", result=result, error=error, cancelled=cancelled)
            except (Exception, asyncio.CancelledError):
                # Parent records loss of evidence; a lost parent cannot acknowledge it.
                pass

    async def stop(self):
        tasks = [c.task for c in self.jobs.values() if c.task is not None]
        for context in self.jobs.values():
            if context.task is not None and not context.task.done():
                if context.entered:
                    context.task.cancel()
                else:
                    context.cancel_requested = True
        await asyncio.gather(*tasks, return_exceptions=True)
