"""Old and new saved evidence coexists without restoring commands or continuations."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta
import json
import unittest

from nymph_toolkit.contracts import ActivityChange, ActivityKey, ActivityRequest, ActivityState
from tests.core import test_activity_history as history_tests


class ActivityV06HistoryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = history_tests.ActivityHistoryTests.asyncSetUp
    asyncTearDown = history_tests.ActivityHistoryTests.asyncTearDown
    store = history_tests.ActivityHistoryTests.store
    run_nymph = history_tests.ActivityHistoryTests.run_nymph
    save_completed = history_tests.ActivityHistoryTests.save_completed
    read = history_tests.ActivityHistoryTests.read

    async def save_controls(self):
        async def nymph(manager):
            async def execute(context):
                while True:
                    await context.wait_for_control()
                    if await context.checkpoint() is not None:
                        return "cleaned"
            plan = ActivityRequest(ActivityKey("nymph", "a"), "作業", None, timedelta(hours=1))
            manager.submit(plan, execute, supports_pause=True)
            while manager.snapshot(plan.key).state != ActivityState.RUNNING:
                await asyncio.sleep(0)
            manager.request_pause(plan.key, command_id="pause", expected_revision=manager.snapshot(plan.key).revision)
            await manager.wait_command(plan.key, "pause")
            manager.change(plan.key, ActivityChange(duration=timedelta(hours=2), priority=2),
                           command_id="edit", expected_revision=manager.snapshot(plan.key).revision)
            manager.request_resume(plan.key, command_id="resume", expected_revision=manager.snapshot(plan.key).revision)
            await manager.wait_command(plan.key, "resume")
            manager.request_finish(plan.key)
            await manager.wait(plan.key)
        await self.run_nymph(nymph)

    async def test_saved_control_results_and_original_current_inputs_remain_immutable(self):
        await self.save_controls()
        history = await self.read()
        self.assertEqual(history.issues, ())
        commands = [r.data for r in history.records if r.kind == "activity_v06_command"]
        self.assertEqual([(d["command"]["operation"], d["command"]["status"]) for d in commands],
                         [("pause", "accepted"), ("pause", "applied"), ("change", "applied"),
                          ("resume", "accepted"), ("resume", "applied")])
        changed = commands[2]
        self.assertEqual(changed["request"]["priority"], 0)
        self.assertEqual(changed["current_request"]["priority"], 2)
        self.assertIsNotNone(changed["paused_at"])
        self.assertIsNotNone(commands[-1]["resumed_at"])
        with self.assertRaises(TypeError):
            changed["command"]["change"]["priority"] = 10
        async def restarted(manager):
            self.assertEqual(manager.activities(), ())
            self.assertFalse((await manager.history("nymph")).issues)
        await self.run_nymph(restarted)

    async def test_v05_and_v06_history_are_read_together_without_inventing_old_fields(self):
        await self.save_completed()
        legacy = next(self.root.glob("history-*.jsonl"))
        records = [json.loads(line) for line in legacy.read_bytes().splitlines()]
        for row in records:
            if row["kind"].startswith("activity_v06_"):
                row["kind"] = row["kind"].replace("activity_v06_", "activity_")
                for name in ("current_request", "revision", "scheduled_revision", "execution_seconds", "paused_at", "resumed_at"):
                    del row["data"][name]
                del row["data"]["request"]["priority"]
        legacy.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
        before = legacy.read_bytes()
        await self.save_controls()
        history = await self.read()
        self.assertEqual(history.issues, ())
        old = [r for r in history.records if r.kind == "activity_state_changed"]
        self.assertEqual(len(old), 3)
        self.assertNotIn("execution_seconds", old[0].data)
        self.assertNotIn("priority", old[0].data["request"])
        self.assertTrue(any(r.kind == "activity_v06_command" for r in history.records))
        self.assertEqual(legacy.read_bytes(), before)

    async def test_corrupt_v06_timing_commands_and_versions_are_reported_without_repair(self):
        await self.save_controls()
        path = next(self.root.glob("history-*.jsonl"))
        original = [json.loads(line) for line in path.read_bytes().splitlines()]
        command_index = next(i for i, row in enumerate(original) if row["kind"] == "activity_v06_command")
        for field, value in (("execution_seconds", -1), ("scheduled_revision", 999), ("revision", True),
                             ("paused_at", "not-a-date"), ("command", {})):
            changed = json.loads(json.dumps(original))
            changed[command_index]["data"][field] = value
            path.write_text("".join(json.dumps(row) + "\n" for row in changed), encoding="utf-8")
            before = path.read_bytes()
            history = await self.read()
            self.assertEqual(len(history.issues), 1, (field, history.issues))
            self.assertEqual(path.read_bytes(), before)
