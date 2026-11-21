"""A shared priority/FIFO queue for due starts and explicitly requested resumes."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import ActivityAdmissionError, ActivityCommandStatus, ActivityState, RuntimeState


class _Slots:
    def _queue(self, entry):
        if entry.ticket is None:
            self._ticket += 1
            entry.ticket = self._ticket
            self._ready[entry.request.key] = entry
        self._dispatch_changed.set()

    def _release_slot(self, entry):
        if entry.slot:
            entry.slot = False
            self._running_slots -= 1
        self._dispatch_changed.set()

    def _remove_ready(self, entry):
        self._ready.pop(entry.request.key, None)
        entry.ticket = None

    def _withdraw_resume(self, entry):
        self._remove_ready(entry)
        self._dispatch_changed.set()

    def _enqueue_resume(self, entry):
        self._queue(entry)

    def _schedule_changed(self, entry):
        if entry.state == ActivityState.PENDING and entry.start_at > self._now():
            self._remove_ready(entry)
            self._release_slot(entry)
            entry.granted.set()
        self._dispatch_changed.set()

    async def _await_start(self, entry):
        while entry.finish_reason is None and self._state == RuntimeState.RUNNING:
            await self._until(entry, "start_at", entry.start_changed)
            entry.granted.clear()
            self._queue(entry)
            await entry.granted.wait()
            if (entry.slot and entry.start_at <= self._now() and self.store.admitting):
                return
            self._release_slot(entry)

    async def _dispatch(self):
        await asyncio.sleep(0)
        while self._state == RuntimeState.RUNNING:
            await self._dispatch_changed.wait()
            self._dispatch_changed.clear()
            if not self._ready:
                continue
            await self.store.wait_ready()
            while (self._state == RuntimeState.RUNNING and self.store.admitting and self._ready
                   and (self._max_running is None or self._running_slots < self._max_running)):
                entry = min(self._ready.values(), key=lambda e: (-e.current_request.priority, e.ticket))
                self._remove_ready(entry)
                if entry.state == ActivityState.PENDING:
                    if entry.start_at <= self._now():
                        entry.slot = True
                        self._running_slots += 1
                    entry.granted.set()
                elif entry.state == ActivityState.RESUME_PENDING:
                    try:
                        self._owner(entry.request.key.requester_id)
                    except ActivityAdmissionError:
                        entry.state = ActivityState.PAUSED
                        entry.revision += 1
                        self._emit(entry)
                        self._resolve_commands(entry, "resume", ActivityCommandStatus.REJECTED, "requester_unavailable")
                        continue
                    entry.slot = True
                    self._running_slots += 1
                    self._unpause_clock(entry)
                    entry.resumed_at = self._now()
                    entry.state = ActivityState.RUNNING
                    entry.revision += 1
                    self._emit(entry)
                    self._resolve_commands(entry, "resume", ActivityCommandStatus.APPLIED)
                    entry.resumed.set()
