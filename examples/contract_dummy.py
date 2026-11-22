"""External function example: only public Contracts are imported from NTK."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta

from nymph_toolkit.contracts import (
    ActivityContext, ActivityKey, ActivityRequest, ActivityState, ContractKey,
    CoreClientProtocol, DirectLinkProtocol, ModuleContextProtocol, OperatingState,
    OperationFailure, OverflowPolicy, ProtocolError, RuntimeService, StreamOptions,
    StreamReceiverProtocol, StreamSenderProtocol, TemporaryUnavailable, Usage,
)

KEY = ContractKey("example.contract", "1")
OPERATIONS = ("echo", "exercise", "failure", "received", "stream")


class Function:
    def __init__(self, context: ModuleContextProtocol, config):
        self.context, self.config = context, config
        self.data = []
        self.received = asyncio.Event()
        context.provide(KEY, {"echo": self.echo, "exercise": self.exercise, "failure": self.failure,
                              "received": self.result})

    async def start(self):
        # Both factory and start may register. Registration closes before run.
        self.context.provide_stream(KEY, "stream", self.stream)
        self.context.provide_executor("work", self.work)
        usage = Usage(OperatingState.RUNNING, True, 0, 4)
        await self.context.core.publish_usage(usage, contracts={KEY: usage})

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass

    async def echo(self, value):
        return value

    async def failure(self, capacity=False):
        return TemporaryUnavailable("busy") if capacity else OperationFailure("business", "rejected")

    async def stream(self, receiver: StreamReceiverProtocol, metadata):
        assert isinstance(receiver, StreamReceiverProtocol)
        self.data = []
        while True:
            event = await receiver.receive(timeout=5)
            if event.kind != "data":
                self.received.set()
                return
            self.data.append(event.data.decode("utf-8"))

    async def result(self):
        await self.received.wait()
        return self.data

    async def work(self, context: ActivityContext, arguments):
        await context.wait_for_finish()
        return {"cleaned": True, "argument": arguments}

    async def exercise(self, provider):
        core = self.context.core
        assert isinstance(self.context, ModuleContextProtocol)
        assert isinstance(core, CoreClientProtocol)
        candidates = await core.candidates(KEY)
        assert provider in [candidate.advertisement.module_id for candidate in candidates]
        await core.bind(KEY, provider, timeout=5)
        link = await core.prepare(KEY, timeout=5)
        assert isinstance(link, DirectLinkProtocol)
        try:
            assert await link.acall("echo", {"route": "direct"}, timeout=5) == {"route": "direct"}
            assert await core.invoke(KEY, "echo", {"route": "core"}, timeout=5) == {"route": "core"}
            assert isinstance(await link.acall("failure", timeout=5), OperationFailure)
            assert isinstance(await link.acall("failure", True, timeout=5), TemporaryUnavailable)
            sender = await link.open_stream("stream", StreamOptions(128, 4, 128, 4, OverflowPolicy.WAIT), timeout=5)
            assert isinstance(sender, StreamSenderProtocol)
            await sender.send(b"contract payload", timeout=5)
            await sender.close(timeout=5)
            assert await link.acall("received", timeout=5) == ["contract payload"]
            request = ActivityRequest(ActivityKey(self.context.module_id, "work"), "dummy work", None,
                                      timedelta(seconds=.02))
            await core.submit_remote(request, provider, "work", {"via": "contract"})
            async with asyncio.timeout(5):
                while not (await core.activity("snapshot", request.key)).planned_end_notified:
                    await asyncio.sleep(.005)
            assert (await core.activity("snapshot", request.key)).state == ActivityState.RUNNING
            await core.activity("finish", request.key)
            ended = await core.activity("wait", request.key, timeout=5)
            assert ended.cleanup_confirmed and ended.state == ActivityState.STOPPED
            try:
                self.context.provide(KEY, {"late": self.echo})
            except ProtocolError:
                pass
            else:
                raise AssertionError("Registration must close after start")
            return {"rpc": "direct+core", "stream": "received", "activity": "nymph-finished", "registration": "sealed"}
        finally:
            await link.close()


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return Function(context, config)


async def async_factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    await asyncio.sleep(0)
    return Function(context, config)
