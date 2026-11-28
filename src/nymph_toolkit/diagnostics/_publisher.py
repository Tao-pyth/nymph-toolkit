"""Non-blocking, coalescing publisher for an adapter-owned lifecycle."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timezone

from nymph_toolkit.contracts.diagnostics import report_contract, validate_report


def utcstamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ReportPublisher:
    """Construct at adapter start and await close during adapter stop."""

    def __init__(self, core, *, module_id, slot, run_id, receiver_id="ntk-diagnostics"):
        self._core = core
        self._key = report_contract(slot).key
        self._identity = {"module_id": module_id, "run_id": run_id, "version": 1}
        self._receiver_id = receiver_id
        self._wake = asyncio.Event()
        self._pending = self._last = None
        self._number = 0
        self._closed = False
        self._task = asyncio.create_task(self._send(), name="ntk-diagnostics-publisher")

    def update(self, *, resources=None, outputs=None, condition=None, processing=None):
        """Return after replacing the pending report, without waiting for the receiver."""
        if self._closed:
            raise RuntimeError("Diagnostic publisher is closed")
        payload = {"resources": [] if resources is None else resources,
                   "outputs": [] if outputs is None else outputs}
        if condition is not None:
            payload["condition"] = condition
        if processing is not None:
            payload["processing"] = processing
        report = validate_report(dict(payload, **self._identity, sequence=1, reported_at=utcstamp()))
        current = {key: report[key] for key in payload}
        if current != self._last:
            self._last = self._pending = current
            self._wake.set()

    async def _send(self):
        loop = asyncio.get_running_loop()
        next_at, bound = 0.0, False
        while True:
            await self._wake.wait()
            await asyncio.sleep(max(0.0, next_at - loop.time()))
            item, self._pending = self._pending, None
            self._wake.clear()
            self._number += 1
            next_at = loop.time() + 1
            try:
                if not bound:
                    await self._core.bind(self._key, self._receiver_id, timeout=.5)
                    bound = True
                # Include the bind duration before computing the next send boundary.
                next_at = loop.time() + 1
                await self._core.invoke(self._key, "publish",
                                        dict(item, **self._identity, sequence=self._number, reported_at=utcstamp()),
                                        timeout=.5)
            except Exception:
                # Only a subsequent changed observation can cause a new publish.
                continue

    async def close(self):
        self._closed = True
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
