"""Offline acceptance-runner tests. These are not live Discord evidence."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from nymph_toolkit.contracts import Placement
from tools import validate_voice_live as probe

CONFIG = dict(token_env="NTK_PROBE_TEST_TOKEN", guild_id="100", voice_channel_id="200")
CONSENT = dict(notice_ref="fixture-not-consent", participants={"300": "fixture only", "400": "fixture only"}, retention_seconds=1)
OPTIONS = probe.Options("speaker", seconds=1, action_after=.15, placement=Placement.LOCAL)


def observation(user="300", **changes):
    result = dict(sequence=1, session_id="one", source_kind="observed", user_id=user, guild_id="100", voice_channel_id="200",
                  asr=dict(text="PRIVATE TRANSCRIPT", words=[dict(word="PRIVATE WORD")]), pcm_sha256="PRIVATE HASH")
    return dict(result, **changes)


class FakeCalls:
    def __init__(self, stop_reason="requested", *, user="300", empty=False, failed_cleanup=False, reconnect=False):
        self.stop_reason, self.user, self.empty = stop_reason, user, empty
        self.failed_cleanup, self.reconnect = failed_cleanup, reconnect
        self.calls = []
        self.active = False
        self.stopped = False
        self.status = dict(state="inactive", reason=None, cleanup_confirmed=True, participant_count=0,
                           observation_count=0, last_sequence=0, expired_count=0, discarded_segments=0)

    async def __call__(self, operation, *args, **kwargs):
        self.calls.append(operation)
        if operation == "start_session":
            self.status["session_id"] = args[0]
            if not self.stopped or self.reconnect:
                self.active = True
                self.status.update(state="listening", cleanup_confirmed=False, participant_count=2)
        elif operation in ("stop_session", "revoke"):
            self.active, self.stopped = False, True
            self.status.update(state="stopped", reason="revoked" if operation == "revoke" else self.stop_reason,
                               cleanup_confirmed=not self.failed_cleanup, participant_count=0, observation_count=0)
        elif operation == "read":
            item = observation(self.user, session_id=args[0])
            return dict(session_id=args[0], state=self.status["state"], observations=[item] if self.active and not self.empty else [],
                        last_sequence=0 if self.empty else 1, expired_count=0, next_after=None)
        return dict(self.status)


class FakeRuntime:
    def __init__(self, group): self.group = group
    async def start(self): self.group.started += 1
    async def stop(self): self.group.stopped += 1


class FakeGroup:
    def __init__(self, call):
        self.call = call
        self.modules = ("voice", "observer")
        self.started = self.stopped = 0
        self.closed = False
    def client(self, name): return self
    async def bind(self, *args, **kwargs): pass
    async def prepare(self, *args, **kwargs): return self
    async def acall(self, operation, *args, **kwargs):
        kwargs.pop("timeout", None)
        return await self.call(operation, *args, **kwargs)
    async def invoke(self, contract, operation, *args, **kwargs): return await self.acall(operation, *args, **kwargs)
    async def close(self): self.closed = True
    def process(self, name):
        class Snapshot: cleanup_confirmed = True
        return Snapshot()


class LiveProbeTests(unittest.IsolatedAsyncioTestCase):
    async def run_fake(self, call, options=OPTIONS, *, groups=None):
        group = FakeGroup(call)
        with patch.dict(os.environ, {CONFIG["token_env"]: "PRIVATE TOKEN"}), \
                patch.object(probe, "build_group", side_effect=groups or [group]), \
                patch.object(probe, "Runtime", FakeRuntime), patch.object(probe, "checkout_metadata", return_value={}):
            report = await probe.probe(CONFIG, CONSENT, options, announce=lambda text: None)
        return report, group

    async def test_counts_only_and_private_values_never_reach_report(self):
        report, group = await self.run_fake(FakeCalls())
        self.assertTrue(report["passed"], report)
        self.assertEqual((report["observations"], report["asr_observations"], report["word_count"]), (1, 1, 1))
        self.assertEqual(report["participant_observations"], [1, 0])
        self.assertEqual(report["initial_status"]["participant_count"], 2)
        serialized = json.dumps(report)
        for private in ("PRIVATE", '"300"', '"400"', '"100"', '"200"', "fixture-not-consent"):
            self.assertNotIn(private, serialized)
        self.assertGreater(group.stopped, 0)
        self.assertTrue(group.closed)

    async def test_empty_wrong_speaker_wrong_reason_cleanup_and_reconnect_never_pass(self):
        cases = [(FakeCalls(empty=True), OPTIONS), (FakeCalls(user="400"), OPTIONS),
                 (FakeCalls(user="999"), OPTIONS), (FakeCalls(failed_cleanup=True), OPTIONS),
                 (FakeCalls(reconnect=True), OPTIONS), (FakeCalls(), replace(OPTIONS, case="leave"))]
        for call, options in cases:
            with self.subTest(case=options.case, call=call.__dict__):
                report, group = await self.run_fake(call, options)
                self.assertFalse(report["passed"])
                self.assertGreater(group.stopped, 0)

    async def test_revoke_uses_selected_participant_and_fails_if_reason_is_overwritten(self):
        call = FakeCalls(stop_reason="revoked")
        original = call.__call__
        revoked = []
        async def observed(operation, *args, **kwargs):
            if operation == "revoke": revoked.append(args[1])
            return await original(operation, *args, **kwargs)
        report, _ = await self.run_fake(observed, replace(OPTIONS, case="revoke", participant=2))
        self.assertTrue(report["passed"], report)
        self.assertEqual(revoked, ["400"])
        self.assertEqual(report["status"]["reason"], "revoked")

    async def test_start_failure_and_exception_still_close_runtime_without_exception_text(self):
        for fail_at in ("start_session", "read"):
            calls = FakeCalls()
            async def broken(operation, *args, **kwargs):
                if operation == fail_at:
                    raise RuntimeError("PRIVATE EXCEPTION TOKEN")
                return await calls(operation, *args, **kwargs)
            report, group = await self.run_fake(broken)
            self.assertFalse(report["passed"])
            self.assertEqual(report["error"], "probe_failed")
            self.assertNotIn("PRIVATE", json.dumps(report))
            self.assertIn("stop_session", calls.calls)
            self.assertTrue(group.closed)
            self.assertGreater(group.stopped, 0)

    async def test_cancel_waiting_read_stops_session_and_runtime(self):
        entered = asyncio.Event()
        calls = FakeCalls()
        async def blocked(operation, *args, **kwargs):
            if operation == "read":
                entered.set()
                await asyncio.Event().wait()
            return await calls(operation, *args, **kwargs)
        group = FakeGroup(blocked)
        with patch.dict(os.environ, {CONFIG["token_env"]: "fixture"}), \
                patch.object(probe, "build_group", return_value=group), patch.object(probe, "Runtime", FakeRuntime):
            task = asyncio.create_task(probe.probe(CONFIG, CONSENT, OPTIONS, announce=lambda text: None))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertIn("stop_session", calls.calls)
        self.assertTrue(group.closed)
        self.assertGreater(group.stopped, 0)

    async def test_runtime_stop_does_not_call_session_stop_or_reconnect_and_requires_empty_restart(self):
        for stale in (False, True):
            calls, fresh = FakeCalls(), FakeCalls()
            if stale: fresh.status.update(state="listening", observation_count=1)
            groups = [FakeGroup(calls), FakeGroup(fresh)]
            report, _ = await self.run_fake(calls, replace(OPTIONS, case="runtime-stop"), groups=groups)
            self.assertEqual(report["passed"], not stale, report)
            self.assertNotIn("stop_session", calls.calls)
            self.assertNotIn("start_session", fresh.calls)
            self.assertTrue(all(group.stopped for group in groups))

    async def test_retention_requires_observed_sequence_to_disappear_after_time(self):
        for expired in (False, True):
            evidence = probe.Evidence(CONFIG, CONSENT, replace(OPTIONS, case="retention", seconds=1.5))
            calls = FakeCalls()
            original = calls.__call__
            clock = asyncio.get_running_loop().time
            start = clock()
            async def controlled(operation, *args, **kwargs):
                result = await original(operation, *args, **kwargs)
                if operation == "read" and clock() - start > 1.2 and expired:
                    result.update(observations=[], expired_count=1)
                return result
            await probe.exercise(controlled, None, evidence, CONSENT, "one", lambda text: None)
            self.assertEqual(evidence.retention_verified, expired)

    async def test_read_hang_cannot_extend_capture_and_is_not_a_pass(self):
        calls = FakeCalls()
        reads = 0
        async def blocked(operation, *args, **kwargs):
            nonlocal reads
            if operation == "read" and calls.active:
                reads += 1
                if reads > 1:
                    await asyncio.Event().wait()
            return await calls(operation, *args, **kwargs)
        async with asyncio.timeout(3):
            report, group = await self.run_fake(blocked)
        self.assertFalse(report["passed"])
        self.assertEqual(report["observations"], 1)
        self.assertTrue(report["read_timed_out"])
        self.assertIn("stop_session", calls.calls)
        self.assertGreater(group.stopped, 0)


class ProbeInputTests(unittest.TestCase):
    def test_unrecognized_status_is_redacted_and_invalid_inputs_do_not_start(self):
        safe = probe.summary(dict(state=["PRIVATE"], reason={"PRIVATE": "TOKEN"}, session_id="PRIVATE", observation_count="PRIVATE"))
        self.assertEqual((safe["state"], safe["reason"], safe["observation_count"]), ("unknown", "other", None))
        self.assertNotIn("PRIVATE", json.dumps(safe))
        for options in (replace(OPTIONS, seconds=float("nan")), replace(OPTIONS, seconds=31),
                        replace(OPTIONS, action_after=1), replace(OPTIONS, participant=3), replace(OPTIONS, case="retention")):
            with patch.dict(os.environ, {CONFIG["token_env"]: "fixture"}), self.assertRaises(ValueError):
                probe.validate_inputs(CONFIG, CONSENT, options)

    def test_cli_failure_and_explicit_output_are_content_free_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, consent, output = root / "config.json", root / "consent.json", root / "summary.json"
            config.write_text(json.dumps(CONFIG), encoding="utf-8")
            consent.write_text(json.dumps(CONSENT), encoding="utf-8")
            args = ["--config", str(config), "--consent", str(consent), "--case", "speaker", "--output", str(output)]
            for existing in (False, True):
                capture = io.StringIO()
                with patch.object(probe, "probe", new=AsyncMock(side_effect=ValueError("PRIVATE ERROR"))), contextlib.redirect_stdout(capture):
                    self.assertEqual(probe.main(args), 1)
                text = output.read_text(encoding="utf-8")
                self.assertNotIn("PRIVATE", text + capture.getvalue())
                self.assertEqual(json.loads(text), dict(passed=False, error="input_or_runtime_failed"))
                self.assertEqual("summary_not_saved" in capture.getvalue(), existing)


class ProbeCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_core_two_placements_both_routes_revoke_retention_and_runtime_stop(self):
        original = probe.build_group
        roots = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = dict(CONFIG, node_executable=__import__("sys").executable, node_modules_path=str(root), model_path=str(root))
            def group_at(state_root, settings, placement):
                group = original(state_root, settings, placement)
                # Replace the registered factory before lifecycle entry, retaining
                # the real Adapter/Core and the existing synthetic helper/ASR.
                group.modules["voice"].factory = "tests.doubles.voice:factory"
                roots.append(group)
                return group
            for placement in Placement:
                for via_core in (False, True):
                    for case in ("revoke", "retention", "runtime-stop"):
                        with self.subTest(placement=placement, via_core=via_core, case=case), \
                                patch.dict(os.environ, {CONFIG["token_env"]: "fixture"}), patch.object(probe, "build_group", group_at):
                            options = replace(OPTIONS, case=case, seconds=7 if case == "retention" else 3,
                                              action_after=1, placement=placement, via_core=via_core)
                            report = await probe.probe(config, CONSENT, options, announce=lambda text: None)
                            self.assertTrue(report["passed"], report)
                            self.assertEqual(report["observations"], 1)
                            self.assertTrue(all(group.process(name).cleanup_confirmed for group in roots for name in group.modules))
                            saved = json.loads((root / "voice-stopped.json").read_text(encoding="utf-8"))
                            self.assertTrue(saved["worker_released"] and saved["current_released"])
                            self.assertEqual(saved["history_count"], 0)
                            self.assertTrue(all(code == 0 for code in saved["processes"]))
            self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])


if __name__ == "__main__": unittest.main()
