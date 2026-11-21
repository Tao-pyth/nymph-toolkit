"""A08 crosses lifecycle, routing, activities, streams and durable evidence."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from nymph_toolkit.contracts import (
    ActivityFinishReason, ActivityKey, ActivityRequest, ActivityState, BindingKey, LinkFailure, Placement,
    RegistryStateError, RuntimeFailure, StreamOptions, OverflowPolicy,
)
from tests.doubles.scenario import KEY, invoke, make_group, owned_state, until


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ntk-integration-")
        self.addCleanup(self.temp.cleanup)
        self.runs = []

    def create(self, *args, **kwargs):
        root = Path(self.temp.name) / str(len(self.runs))
        root.mkdir()
        group, runtime = make_group(root, *args, **kwargs)
        self.runs.append((group, runtime))
        return group, runtime, root

    async def asyncTearDown(self):
        for group, runtime in self.runs:
            try:
                await asyncio.wait_for(runtime.stop(), 8)
            except RuntimeFailure:
                pass
            await asyncio.sleep(0)
            state = owned_state(group)
            self.assertEqual((state["live_tasks"], state["live_children"], state["running_slots"]), (0, 0, 0))

    def request(self, name="work"):
        return ActivityRequest(ActivityKey("requester", name), "investigate", None, timedelta(seconds=30))

    async def test_four_placements_complete_sequence_state_history_cleanup_and_detach(self):
        for requester in Placement:
            for provider in Placement:
                with self.subTest(requester=requester, provider=provider):
                    trace = Path(self.temp.name) / f"trace-{requester}-{provider}"
                    group, runtime, root = self.create(requester, provider, trace=trace)
                    await runtime.start()
                    ports = [group.port] + [s.port for s in group.modules.values()]
                    with self.assertRaises(RegistryStateError):
                        group.unregister("provider")
                    self.assertEqual(await invoke(group, "requester", "connect", "provider"), 2)
                    self.assertEqual(len(await invoke(group, "requester", "batch", 20, 4)), 20)
                    stream, activity = await asyncio.gather(
                        invoke(group, "requester", "transfer", "sequence", 32, 1024),
                        invoke(group, "requester", "activity_cycle", "provider", "activity", True))
                    self.assertEqual(stream["bytes"], 32768)
                    self.assertEqual(activity["state"], "stopped")
                    self.assertGreaterEqual(activity["elapsed"], activity["execution"])
                    self.assertEqual(group.connections.connection(BindingKey("requester", KEY)).provider_id, "provider")
                    await runtime.stop()
                    self.assertEqual(owned_state(group), {"live_tasks": 0, "live_children": 0,
                                                        "running_slots": 0, "unsaved_events": 0})
                    events = [json.loads(line) for p in (root / "primary").glob("history-*.jsonl")
                              for line in p.read_text(encoding="utf-8").splitlines()]
                    self.assertTrue(any(e["kind"].startswith("activity_v07_") for e in events))
                    self.assertEqual({e["data"]["phase"] for e in events if e["kind"] == "hybrid_stream"}, {"opened", "ended"})
                    self.assertEqual(len({(e["run_id"], e["sequence"]) for e in events}), len(events))
                    for port in ports:
                        with self.assertRaises(OSError):
                            await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 1)
                    group.unregister("requester")
                    group.unregister("provider")
                    self.assertFalse(group.entries())
                    self.assertEqual(trace.read_text(encoding="utf-8").splitlines(),
                                     ["start:provider", "start:requester", "stop:requester", "stop:provider"])

    async def test_partial_initialization_in_all_placements_reverses_cleanup(self):
        for requester in Placement:
            for provider in Placement:
                with self.subTest(requester=requester, provider=provider):
                    trace = Path(self.temp.name) / f"failure-{requester}-{provider}"
                    group, runtime, _ = self.create(requester, provider, trace=trace,
                                                    requester_config={"start_failure": True})
                    with self.assertRaises(RuntimeFailure):
                        await asyncio.wait_for(runtime.start(), 8)
                    self.assertEqual(trace.read_text(encoding="utf-8").splitlines(),
                                     ["start:provider", "start:requester", "stop:requester", "stop:provider"])
                    self.assertEqual(owned_state(group)["live_children"], 0)

    async def test_data_disconnect_during_activity_is_local_interruption_without_replay(self):
        group, runtime, _ = self.create()
        await runtime.start()
        await invoke(group, "requester", "connect", "provider")
        link = group.modules["requester"].node.service.link
        request = self.request()
        manager = group.activities
        manager.submit_remote(request, "provider", "work")
        await until(lambda: manager.snapshot(request.key).state == ActivityState.RUNNING)
        waiting = asyncio.create_task(link.acall("echo", {"wait": True}, timeout=5))
        async with asyncio.timeout(5):
            while (await invoke(group, "provider", "metrics"))["calls"] != 1:
                await asyncio.sleep(.005)
        link._peer.writer.transport.abort()
        failure = await asyncio.wait_for(waiting, 5)
        self.assertIsInstance(failure, LinkFailure)
        self.assertEqual(runtime.state.value, "running")
        self.assertEqual(group.connections.module_state("provider").value, "running")
        # The requester owns cooperative cleanup; Core does not decide which
        # activities to end or acknowledge interruption on its behalf.
        manager.request_finish(request.key, reason=ActivityFinishReason.CONNECTION_INTERRUPTION)
        ended = await asyncio.wait_for(manager.wait(request.key), 5)
        self.assertEqual(ended.state, ActivityState.STOPPED)
        self.assertTrue(ended.cleanup_confirmed)
        group.connections.acknowledge_interruption("requester", failure.interruption_id)
        await group.connections.health_check(module_ids=("provider",))
        await invoke(group, "requester", "connect", "provider")
        self.assertEqual((await invoke(group, "provider", "metrics"))["calls"], 1)
        self.assertEqual(len(await invoke(group, "requester", "batch", 1)), 1)
        self.assertEqual((await invoke(group, "provider", "metrics"))["calls"], 2)

    async def test_child_exit_or_parent_channel_loss_during_activity_and_stream(self):
        for fault in ("process", "management"):
            with self.subTest(fault=fault):
                group, runtime, _ = self.create()
                await runtime.start()
                await invoke(group, "requester", "connect", "provider")
                link = group.modules["requester"].node.service.link
                sender = await link.open_stream("stream", StreamOptions(16, 2, 16, 2, OverflowPolicy.WAIT),
                                                {"id": "pending", "hold": True}, timeout=5)
                await sender.send(b"payload", timeout=5)
                request = self.request()
                group.activities.submit_remote(request, "provider", "work")
                await until(lambda: group.activities.snapshot(request.key).state == ActivityState.RUNNING)
                generation = group.process("provider").generation
                if fault == "process":
                    group.modules["provider"].process.kill()
                else:
                    await group.modules["provider"].peer.close()
                with self.assertRaises(RuntimeFailure):
                    await asyncio.wait_for(runtime.wait(), 8)
                ended = group.activities.snapshot(request.key)
                self.assertEqual(ended.state, ActivityState.FAILED)
                self.assertFalse(ended.cleanup_confirmed)
                self.assertIsNone(ended.ended_at)
                self.assertEqual(group.process("provider").generation, generation)
                self.assertNotEqual(sender.state.value, "open")

    async def test_shutdown_deadline_does_not_apply_to_nymph_finish(self):
        group, runtime, _ = self.create()
        group.settings = replace(group.settings, shutdown_timeout=.15)
        await runtime.start()
        request = self.request()
        group.activities.submit_remote(request, "provider", "work", {"stuck_cleanup": True})
        await until(lambda: group.activities.snapshot(request.key).state == ActivityState.RUNNING)
        group.activities.request_finish(request.key)
        await asyncio.sleep(.25)
        self.assertIsNone(group.modules["provider"].process.returncode)
        self.assertEqual(group.activities.snapshot(request.key).state, ActivityState.FINISHING)
        try:
            await asyncio.wait_for(runtime.stop(), 5)
        except RuntimeFailure:
            pass
        self.assertIsNotNone(group.modules["provider"].process.returncode)
        self.assertFalse(group.activities.snapshot(request.key).cleanup_confirmed)
