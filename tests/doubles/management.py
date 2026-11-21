"""A function exercises management result ownership through its public client."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import OutcomeUnknown, RemoteError
from tests.doubles.integration import Probe


class ManagementProbe(Probe):
    async def echo(self, value):
        core = self.context.core
        released = 0
        for _ in range(value):
            try:
                await core.next_notice(timeout=.01)
            except OutcomeUnknown as exc:
                assert exc.request_id in core.pending_requests
            else:
                raise AssertionError("No notice should exist")
            async with asyncio.timeout(2):
                while core.pending_requests:
                    for identity in core.pending_requests:
                        try:
                            core.result(identity)
                        except OutcomeUnknown:
                            continue
                        except RemoteError as exc:
                            assert exc.remote_type == "CancelledError"
                        core.release(identity)
                        released += 1
                    await asyncio.sleep(.001)
        task = asyncio.create_task(core.next_notice(timeout=2))
        async with asyncio.timeout(2):
            while not core.pending_requests:
                await asyncio.sleep(.001)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        async with asyncio.timeout(2):
            while core.pending_requests:
                for identity in core.pending_requests:
                    try:
                        core.result(identity)
                    except OutcomeUnknown:
                        continue
                    except RemoteError:
                        pass
                    core.release(identity)
                    released += 1
                await asyncio.sleep(.001)
        return {"released": released, "pending": len(core.pending_requests)}


def factory(context, config):
    return ManagementProbe(context, config)
