"""Instrumented functions exercise the real Core without application semantics."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import datetime, timedelta, timezone
import os
import time
import tracemalloc

from nymph_toolkit.contracts import (
    ActivityChange, ActivityKey, ActivityRequest, ActivityState, ContractKey, ContractSpec,
    OperatingState, OperationMode, OperationSpec, OverflowPolicy, StreamOptions, Usage,
)
from tests.doubles.hybrid import Dummy
from tests.doubles.measurement import memory

KEY = ContractKey("validation.probe", "1")
OPERATIONS = ("echo", "connect", "batch", "transfer", "stream_result", "activity_cycle", "metrics", "gate", "stream")
CONTRACT = ContractSpec(KEY, tuple(OperationSpec(name, OperationMode.ASYNC) for name in OPERATIONS))


class Probe(Dummy):
    def __init__(self, context, config):
        super().__init__(context, {**(config or {}), "provider": False})
        context.provide(KEY, {name: getattr(self, name) for name in OPERATIONS if name != "stream"})
        context.provide_stream(KEY, "stream", self.stream)
        self.link = None
        self.calls = self.work_started = self.work_ended = 0
        self.results = {}
        self.result_changed = asyncio.Event()
        self.stream_gate = asyncio.Event()
        self.echo_gate = asyncio.Event()
        self.execution_host = None
        if self.config.get("measure") and not tracemalloc.is_tracing():
            tracemalloc.start()

    async def start(self):
        await super().start()
        usage = Usage(OperatingState.RUNNING, True, 0, 32)
        await self.context.core.publish_usage(usage, contracts={KEY: usage})

    async def stop(self):
        if self.link is not None:
            await self.link.close()
        await super().stop()

    async def echo(self, value):
        self.calls += 1
        if isinstance(value, dict) and value.get("wait"):
            await self.echo_gate.wait()
        if isinstance(value, dict) and value.get("fail"):
            raise ValueError("injected data operation failure")
        return {"value": value, "pid": os.getpid()}

    async def gate(self, name, opened=True):
        event = self.stream_gate if name == "stream" else self.echo_gate
        event.set() if opened else event.clear()

    async def connect(self, provider):
        candidates = await self.context.core.candidates(KEY)
        assert candidates
        await self.context.core.bind(KEY, provider, timeout=5)
        if self.link is not None:
            await self.link.close()
        self.link = await self.context.core.prepare(KEY, timeout=5)
        return len(candidates)

    async def batch(self, count, width=1):
        latencies = []
        async def one(number):
            start = time.perf_counter()
            result = await self.link.acall("echo", number, timeout=5)
            assert result["value"] == number
            latencies.append(time.perf_counter() - start)
        for offset in range(0, count, width):
            await asyncio.gather(*(one(i) for i in range(offset, min(count, offset + width))))
        return latencies

    async def stream(self, receiver, metadata):
        key = metadata["id"]
        count = size = missing = peak_bytes = peak_chunks = 0
        try:
            if metadata.get("hold"):
                await self.stream_gate.wait()
            while True:
                event = await receiver.receive(timeout=5)
                peak_bytes = max(peak_bytes, receiver.buffered_bytes + len(event.data))
                peak_chunks = max(peak_chunks, receiver.buffered_chunks + (event.kind == "data"))
                missing += event.missing_count
                if event.kind != "data":
                    break
                count += 1
                size += len(event.data)
            self.results[key] = {"chunks": count, "bytes": size, "missing": missing,
                                 "terminal": event.kind, "receive_peak_bytes": peak_bytes,
                                 "receive_peak_chunks": peak_chunks}
        finally:
            self.result_changed.set()

    async def stream_result(self, key):
        async with asyncio.timeout(5):
            while key not in self.results:
                self.result_changed.clear()
                await self.result_changed.wait()
        return self.results.pop(key)

    async def transfer(self, key, chunks=64, chunk_bytes=4096):
        options = StreamOptions(65536, 16, 65536, 16, OverflowPolicy.WAIT)
        sender = await self.link.open_stream("stream", options, {"id": key}, timeout=5)
        payload = b"x" * chunk_bytes
        started = time.perf_counter()
        peak_bytes = peak_chunks = 0
        management = []
        try:
            for index in range(chunks):
                await sender.send(payload, timeout=5)
                peak_bytes = max(peak_bytes, sender.buffered_bytes)
                peak_chunks = max(peak_chunks, sender.buffered_chunks)
                if index % 8 == 0:
                    before = time.perf_counter()
                    await self.context.core.candidates(KEY, timeout=5)
                    management.append(time.perf_counter() - before)
            await sender.close(timeout=5)
            elapsed = time.perf_counter() - started
            result = await self.link.acall("stream_result", key, timeout=5)
            assert result["bytes"] == chunks * chunk_bytes and result["chunks"] == chunks
            assert result["terminal"] == "end" and result["missing"] == 0
            assert peak_bytes <= options.send_bytes and peak_chunks <= options.send_chunks
            assert result["receive_peak_bytes"] <= options.receive_bytes
            assert result["receive_peak_chunks"] <= options.receive_chunks
            return {**result, "seconds": elapsed, "send_peak_bytes": peak_bytes,
                    "send_peak_chunks": peak_chunks, "management_seconds": management}
        finally:
            await sender.aclose()

    async def work(self, context, arguments):
        self.execution_host = context.host
        self.work_started += 1
        try:
            return await super().work(context, arguments)
        finally:
            self.work_ended += 1

    async def activity_cycle(self, provider, identity, changes=False):
        core = self.context.core
        key = ActivityKey(self.context.module_id, identity)
        start = datetime.now(timezone.utc) + timedelta(seconds=60) if changes else None
        request = ActivityRequest(key, "probe", start, timedelta(seconds=30))
        initial = await core.submit_remote(request, provider, "work", None if changes else {"complete": True})
        if changes:
            await core.activity("change", key, change=ActivityChange(start_at=None, duration=timedelta(seconds=60), priority=3),
                                command_id="schedule", expected_revision=initial.revision)
            async with asyncio.timeout(5):
                while (snapshot := await core.activity("snapshot", key)).state != ActivityState.RUNNING:
                    await asyncio.sleep(.005)
            await core.activity("pause", key, command_id="pause", expected_revision=snapshot.revision)
            paused = await core.activity("command", key, command_id="pause", timeout=5)
            assert paused.snapshot.state == ActivityState.PAUSED
            await core.activity("resume", key, command_id="resume", expected_revision=paused.snapshot.revision)
            await core.activity("command", key, command_id="resume", timeout=5)
            await core.activity("finish", key)
        ended = await core.activity("wait", key, timeout=5)
        assert ended.state == (ActivityState.STOPPED if changes else ActivityState.COMPLETED)
        assert ended.timing_confirmed and ended.cleanup_confirmed
        return {"state": ended.state.value, "elapsed": ended.elapsed_seconds,
                "execution": ended.execution_seconds, "started": ended.started_at.isoformat(),
                "ended": ended.ended_at.isoformat()}

    async def metrics(self):
        peers = tuple(self.context.peers)
        return {**memory(), "calls": self.calls, "work_started": self.work_started, "work_ended": self.work_ended,
                "retained_executions": 0 if self.execution_host is None else len(self.execution_host.jobs),
                "pending_rpc": sum(len(p._pending) for p in peers), "data_peers": len(peers),
                "pending_management": len(self.context.core.pending_requests),
                "streams": len(self.context.streams), "owned_tasks": len(self.context.owned),
                "opening_streams": self.context.opening_streams, "unconsumed_results": len(self.results)}


def factory(context, config):
    return Probe(context, config)
