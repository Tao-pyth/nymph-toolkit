"""Importable dummy functions for real child-process contract verification."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import os

from nymph_toolkit.contracts import ContractKey, OperatingState, OperationFailure, Usage, TemporaryUnavailable

KEY = ContractKey("dummy.echo", "1")


class Dummy:
    def __init__(self, context, config):
        self.context, self.config = context, config or {}
        self.received = []
        context.provide_executor("work", self.work, supports_pause=True)
        if self.config.get("provider"):
            context.provide(KEY, {"echo": self.echo, "request": self.request, "received": self.get_received,
                                  "failure": self.failure, "crash": self.crash, "activity": self.activity})
            context.provide_stream(KEY, "stream", self.stream)

    async def start(self):
        self.trace("start")
        if self.config.get("start_wait"):
            await asyncio.Event().wait()
        if self.config.get("start_failure"):
            raise ValueError("dummy initialization failed")
        usage = Usage(OperatingState.RUNNING, True, 0, 8)
        await self.context.core.publish_usage(usage, contracts={KEY: usage} if self.config.get("provider") else None)

    async def run(self):
        if self.config.get("run_failure"):
            raise ValueError("dummy run failed")
        if self.config.get("return_run"):
            return "complete"
        await asyncio.Event().wait()

    async def stop(self):
        self.trace("stop")
        if self.config.get("stop_failure"):
            raise ValueError("cleanup failed")
        if self.config.get("stuck_stop"):
            while True:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass

    async def echo(self, value):
        if self.config.get("echo_wait"):
            await asyncio.Event().wait()
        return {"value": value, "pid": os.getpid()}

    def trace(self, phase):
        if self.config.get("trace"):
            with open(self.config["trace"], "a", encoding="utf-8") as output:
                output.write(f"{phase}:{self.context.module_id}\n")

    async def failure(self, kind):
        if kind == "business":
            return OperationFailure("declined", "ordinary failure")
        if kind == "capacity":
            return TemporaryUnavailable()
        raise ValueError("unexpected provider error")

    async def crash(self):
        os._exit(17)

    async def request(self, provider_id, stream=False):
        core = self.context.core
        await core.bind(KEY, provider_id, timeout=2)
        link = await core.prepare(KEY, timeout=2)
        result = await link.acall("echo", "from requester", timeout=2)
        if stream:
            from nymph_toolkit.contracts import StreamOptions, OverflowPolicy
            sender = await link.open_stream("stream", StreamOptions(64, 4, 64, 4, OverflowPolicy.WAIT), timeout=2)
            await sender.send(b"dummy bytes", timeout=2)
            await sender.close(timeout=2)
            await sender.aclose()
        await link.close()
        return result

    async def stream(self, receiver, metadata):
        if metadata == "fail":
            raise ValueError("stream handler failed")
        if metadata == "wait":
            await asyncio.Event().wait()
        while True:
            event = await receiver.receive(timeout=2)
            if event.kind != "data":
                return
            self.received.append(event.data.decode("utf-8"))

    async def get_received(self):
        return self.received

    async def activity(self, provider_id):
        from datetime import timedelta
        from nymph_toolkit.contracts import ActivityChange, ActivityKey, ActivityRequest, ActivityState
        core = self.context.core
        request = ActivityRequest(ActivityKey(self.context.module_id, "remote"), "investigate", None, timedelta(seconds=20))
        await core.submit_remote(request, provider_id, "work")
        async with asyncio.timeout(4):
            while True:
                observed = await core.activity("snapshot", request.key)
                if observed.state == ActivityState.RUNNING:
                    break
                await asyncio.sleep(.005)
        await core.activity("change", request.key, change=ActivityChange(duration=timedelta(seconds=30), priority=2),
                            command_id="change", expected_revision=observed.revision)
        observed = await core.activity("snapshot", request.key)
        await core.activity("pause", request.key, command_id="pause", expected_revision=observed.revision)
        paused = await core.activity("command", request.key, command_id="pause")
        await core.activity("resume", request.key, command_id="resume", expected_revision=paused.snapshot.revision)
        await core.activity("command", request.key, command_id="resume")
        await core.activity("finish", request.key)
        ended = await core.activity("wait", request.key)
        return {"state": ended.state.value, "cleanup": ended.cleanup_confirmed, "result": dict(ended.result)}

    async def work(self, context, arguments):
        arguments = arguments or {}
        steps = 0
        if arguments.get("fail"):
            raise ValueError("activity failed")
        try:
            if arguments.get("complete"):
                return {"pid": os.getpid(), "steps": steps}
            while not context.finish_requested:
                await context.wait_for_control()
                reason = await context.checkpoint()
                if reason is not None:
                    break
                steps += 1
        finally:
            if arguments.get("stuck_cleanup"):
                while True:
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        pass
        return {"pid": os.getpid(), "steps": steps}


def factory(context, config):
    return Dummy(context, config)
