"""B08 real traits, learning and controlled activities across process placements."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples.persona_agency_demo import Calls, CONTROL, PERSONA_KEY, exercise, group_at, saved, until, update, execution
from nymph_toolkit.contracts import Placement, TemporaryUnavailable
from nymph_toolkit.contracts.memory import MEMORY_KEY
from nymph_toolkit.core import Runtime
from nymph_toolkit.subsystems.persona import _Persona


class PersonaAgencyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_persona_capacity_waits_for_new_observation_without_stopping_current_work(self):
        await self.fault_scenario(capacity=True)

    async def test_persona_link_failure_stops_owned_work_and_does_not_retry(self):
        await self.fault_scenario(capacity=False)

    async def fault_scenario(self, *, capacity):
        original = _Persona.get
        failing = False
        failures = 0

        async def controlled(service):
            nonlocal failures
            if failing:
                failures += 1
                if capacity: return TemporaryUnavailable("controlled Persona capacity")
                raise RuntimeError("controlled Persona communication failure")
            return await original(service)

        with patch.object(_Persona, "get", controlled), tempfile.TemporaryDirectory() as directory:
            group = group_at(Path(directory).resolve(), persona=Placement.LOCAL)
            runtime = Runtime(group); call = Calls(group)
            await runtime.start()
            try:
                await call.start()
                await call(MEMORY_KEY, "put", dict(record_id="lesson", kind="experience", content="猫 は 眠る",
                    source_kind="observed", source="test:b08", occurred_at="2026-11-24T00:00:00Z"))
                observed = execution.observation(600)
                await call(CONTROL, "activate", "fault", observed)
                active = await until(call, lambda s:any(a["template_id"] == "apply" and a["state"] == "running" for a in s["activities"]))
                failing = True
                await call(CONTROL, "observe", "fault", active["observation_revision"], observed)
                state = await until(call, lambda s:s["state"] == ("waiting" if capacity else "failed"))
                self.assertEqual(failures, 1)
                await asyncio.sleep(.1)
                self.assertEqual(failures, 1)
                if capacity:
                    self.assertTrue(any(a["template_id"] == "apply" and a["state"] == "running" for a in state["activities"]))
                    failing = False
                    await call(PERSONA_KEY, "apply", update("rest", 0, 500))
                    # No automatic requery after the provider becomes available.
                    await asyncio.sleep(.1)
                    self.assertEqual((await call(CONTROL, "status"))["state"], "waiting")
                    await call(CONTROL, "observe", "fault", state["observation_revision"], observed)
                    await until(call, lambda s:any(a["template_id"] == "rest" and a["state"] == "running" for a in s["activities"]))
                    await call(CONTROL, "halt", "fault")
                    state = await until(call, lambda s:s["state"] == "stopped")
                self.assertTrue(all(a["cleanup_confirmed"] for a in state["activities"]), state)
            finally:
                await call.close(); await runtime.stop()
            self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))

    async def test_four_placements_both_routes_actual_change_and_restart(self):
        for agency in Placement:
            for persona in Placement:
                for direct in (False, True):
                    with self.subTest(agency=agency, persona=persona, direct=direct), tempfile.TemporaryDirectory() as directory:
                        root = Path(directory).resolve(); result = None
                        for restored in (False, True):
                            group = group_at(root, agency=agency, persona=persona)
                            runtime = Runtime(group); call = Calls(group, direct=direct)
                            await runtime.start()
                            try:
                                await call.start()
                                if not restored:
                                    result = await exercise(call)
                                    self.assertEqual(result["activities"], 3)
                                    self.assertEqual(result["first"]["selected"]["template_id"], "apply")
                                    self.assertEqual(result["altered"]["selected"]["template_id"], "rest")
                                else:
                                    state = await call(CONTROL, "status")
                                    self.assertEqual((state["state"], state["total_activities"]), ("inactive", 0))
                                    self.assertEqual(await saved(call, result["altered"]["decision_id"]), result["altered"])
                                    self.assertEqual((await call(PERSONA_KEY, "get"))["revision"], 2)
                                    self.assertEqual(len((await call(PERSONA_KEY, "history"))["updates"]), 2)
                            finally:
                                await call.close(); await runtime.stop()
                            self.assertTrue(all(group.process(name).cleanup_confirmed for name in group.modules))
                        await asyncio.sleep(0)
                        self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])
