"""B10 real sleep cycle across public Contracts and both process placements."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples import sleep_activity_demo as demo
from nymph_toolkit.contracts import ActivityKey, ActivityRequest, ActivityState, Placement
from nymph_toolkit.contracts.agency import AGENCY_ACTIVITIES_KEY
from nymph_toolkit.contracts.persona import PERSONA_KEY
from nymph_toolkit.contracts.sleep_activity import SLEEP_ACTIVITY_KEY
from nymph_toolkit.core import Runtime
from nymph_toolkit.subsystems.persona import _Persona


class SleepActivityIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_persona_commit_then_link_failure_is_resolved_without_reapply(self):
        original = _Persona.apply
        for actor in Placement:
            calls = 0
            async def committed_then_failed(provider, value):
                nonlocal calls
                calls += 1
                await original(provider, value)
                raise RuntimeError("Controlled failure after Persona commit")
            with self.subTest(actor=actor), tempfile.TemporaryDirectory() as directory, patch.object(_Persona, "apply", committed_then_failed):
                group = demo.group_at(Path(directory).resolve(), actor=actor, providers=Placement.LOCAL)
                runtime, call = Runtime(group), demo.Calls(group)
                await runtime.start()
                try:
                    await call.start()
                    for key, tokens in (("a", ["猫", "は", "眠る"]), ("b", ["犬", "も", "眠る"])):
                        await call(demo.MEMORY_KEY, "put", dict(record_id=key, kind="experience", content=" ".join(tokens),
                            source_kind="observed", source="test:sleep-activity", occurred_at="2026-11-24T00:00:00Z"))
                        await call(demo.COGNITION_KEY, "learn", key, tokens=tokens, concepts=["sleep"])
                    key = ActivityKey("requester", "failure")
                    request = ActivityRequest(key, "Test partial success", None, timedelta(seconds=60))
                    await call.core.submit_remote(request, "sleep-worker", "sleep",
                        dict(request_id="failure", expected_revision=0, record_ids=["a", "b"], apply_persona=True), timeout=5)
                    ended = await call.core.activity("wait", key, timeout=15)
                    self.assertEqual(ended.state, ActivityState.FAILED)
                    self.assertTrue(ended.cleanup_confirmed)
                    self.assertEqual((await call(SLEEP_ACTIVITY_KEY, "get", "failure"))["phase"], "apply_sent")
                    resolved = await call(SLEEP_ACTIVITY_KEY, "reconcile", "failure")
                    self.assertEqual(resolved["phase"], "completed")
                    self.assertEqual(resolved["persona"]["after"]["rest_affinity"], 495)
                    self.assertEqual(calls, 1)
                    self.assertEqual((await call(PERSONA_KEY, "history"))["updates"], [resolved["persona"]])
                finally:
                    await call.close(); await runtime.stop()
                self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))

    async def test_four_placements_both_routes_and_restart(self):
        for actor in Placement:
            for providers in Placement:
                for direct in (False, True):
                    with self.subTest(actor=actor, providers=providers, direct=direct), tempfile.TemporaryDirectory() as directory:
                        root, result = Path(directory).resolve(), None
                        for restored in (False, True):
                            group = demo.group_at(root, actor=actor, providers=providers)
                            runtime, call = Runtime(group), demo.Calls(group, direct=direct)
                            await runtime.start()
                            try:
                                await call.start()
                                if not restored:
                                    result = await demo.exercise(call)
                                else:
                                    state = await call(AGENCY_ACTIVITIES_KEY, "status")
                                    self.assertEqual((state["state"], state["total_activities"]), ("inactive", 0))
                                    self.assertEqual(await call(SLEEP_ACTIVITY_KEY, "get", "night-one"), result["receipt"])
                                    self.assertEqual((await call(PERSONA_KEY, "history"))["updates"], [result["receipt"]["persona"]])
                            finally:
                                await call.close()
                                await runtime.stop()
                            self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))
                            self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])


if __name__ == "__main__": unittest.main()
