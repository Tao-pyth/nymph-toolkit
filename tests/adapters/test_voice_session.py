"""Real owned pipe processes, retention, cancellation and discard-after-stop."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import base64
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nymph_toolkit.adapters.discord_voice import factory
from nymph_toolkit.adapters.discord_voice._audio import MODEL_ID, features, mono_pcm
from nymph_toolkit.adapters.discord_voice._model import consent, frame
from nymph_toolkit.adapters.discord_voice import _Voice
from nymph_toolkit.adapters.discord_voice._session import Session
from nymph_toolkit.adapters.discord_voice import _model_files
from nymph_toolkit.contracts import TemporaryUnavailable


class Processor:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event(); self.release.set()
        self.failed = False
    def process(self, pcm):
        self.entered.set()
        if not self.release.wait(5): raise RuntimeError("Fixture was not released")
        if self.failed: raise RuntimeError("Private diagnostic must not be exposed")
        return dict(asr_model=MODEL_ID, asr=dict(text="猫", words=[]), features=features(mono_pcm(pcm)),
                    pcm_sha256=hashlib.sha256(pcm).hexdigest(), sample_rate=48000, channels=2)


def permission(retention=30):
    return dict(notice_ref="local fixture only", participants={"300": "synthetic test input"}, retention_seconds=retention)


async def until(predicate):
    async with asyncio.timeout(10):
        while not predicate(): await asyncio.sleep(.01)


class VoiceSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.processor = Processor()
        self.config = dict(node_executable=sys.executable, node_modules_path=str(Path(self.temp.name).resolve()),
                           model_path=str(Path(self.temp.name).resolve()), guild_id="100", voice_channel_id="200", token_env="NTK_TEST_TOKEN")
        async def publish(*args, **kwargs): pass
        context = SimpleNamespace(settings=SimpleNamespace(max_frame_bytes=65536), provide=lambda *args: None,
                                  core=SimpleNamespace(publish_usage=publish))
        self.service = factory(context, self.config)
        async def check_node(): pass
        self.service._check_node = check_node
        self.service.processor_factory = lambda path: self.processor
        self.mode = "normal"
        self.processes = []
        async def spawn():
            process = await asyncio.create_subprocess_exec(sys.executable, "-u", str(Path(__file__).parents[1] / "doubles" / "voice_helper.py"), self.mode,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=131072)
            self.processes.append(process)
            return process
        self.service.spawn = spawn
        await self.service.start()
        self.addAsyncCleanup(self.service.stop)

    async def observation(self):
        async with asyncio.timeout(10):
            while True:
                page = await self.service.read("one")
                if isinstance(page, dict) and page["observations"]: return page
                if self.service.current.cleanup_confirmed: self.fail(await self.service.status())
                await asyncio.sleep(.01)

    async def test_real_pipe_capture_pages_and_revoke_clear_everything_without_restart(self):
        self.assertEqual(len(self.processes), 0)
        started = await self.service.start_session("one", permission())
        self.assertEqual(started["state"], "listening")
        page = await self.observation()
        item = page["observations"][0]
        self.assertEqual((item["user_id"], item["guild_id"], item["voice_channel_id"], item["source_kind"]), ("300", "100", "200", "observed"))
        self.assertEqual(item["asr"]["text"], "猫")
        self.assertEqual((await self.service.read("one", after=1))["observations"], [])
        page["observations"][0]["asr"]["text"] = "mutated"
        self.assertEqual((await self.service.read("one"))["observations"][0]["asr"]["text"], "猫")
        self.assertIsInstance(await self.service.start_session("two", permission()), TemporaryUnavailable)
        stopped = await self.service.revoke("one", "300")
        self.assertEqual((stopped["state"], stopped["reason"], stopped["cleanup_confirmed"]), ("stopped", "revoked", True))
        self.assertEqual((await self.service.read("one"))["observations"], [])
        self.assertEqual(self.service.current.permission, {})
        self.assertIsNotNone(self.processes[0].returncode)
        self.assertEqual((await self.service.start_session("one", permission()))["state"], "stopped")
        self.assertEqual(len(self.processes), 1)
        self.assertEqual((await self.service.start_session("one", permission(20))).code, "voice.session_conflict")

    async def test_retention_uses_monotonic_time_and_read_also_expires(self):
        clock = [100.0]; self.service.clock = lambda: clock[0]
        await self.service.start_session("one", permission(1))
        await self.observation()
        clock[0] = 102.0
        page = await self.service.read("one")
        self.assertEqual(page["observations"], [])
        self.assertEqual(page["expired_count"], 1)
        self.assertEqual(page["last_sequence"], 1)
        await self.service.stop_session("one")

    async def test_stop_and_waiter_cancel_drain_asr_without_resurrecting_data(self):
        self.processor.release.clear()
        await self.service.start_session("one", permission())
        await until(self.processor.entered.is_set)
        task = asyncio.create_task(self.service.stop_session("one"))
        await until(lambda: self.service.current.closing)
        task.cancel()
        await asyncio.sleep(.05)
        self.assertFalse(task.done())
        self.assertEqual((await self.service.read("one"))["observations"], [])
        self.processor.release.set()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(self.service.current.cleanup_confirmed)
        self.assertEqual((await self.service.read("one"))["observations"], [])
        self.assertIsNotNone(self.processes[0].returncode)

    async def test_start_cancel_closes_real_process_and_does_not_capture_later(self):
        self.mode = "delayed"
        task = asyncio.create_task(self.service.start_session("one", permission()))
        await until(lambda: bool(self.processes))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(self.service.current.cleanup_confirmed)
        self.assertEqual((await self.service.read("one"))["observations"], [])
        self.assertIsNotNone(self.processes[0].returncode)

    async def test_bad_frames_unknown_participant_and_eof_close_capture(self):
        for mode in ("malformed", "unknown", "eof"):
            self.mode = mode
            await self.service.start_session(mode, permission())
            await until(lambda: self.service.current.cleanup_confirmed)
            self.assertEqual((await self.service.status())["state"], "failed")
            self.assertEqual((await self.service.read(mode))["observations"], [])
            self.assertIsNotNone(self.processes[-1].returncode)

    async def test_queue_pressure_stops_and_failure_message_does_not_leak(self):
        self.mode = "flood"
        self.processor.release.clear()
        pending = asyncio.create_task(self.service.start_session("one", permission()))
        await until(lambda: self.service.current is not None and self.service.current.closing)
        self.processor.release.set()
        await pending
        await until(lambda: self.service.current.cleanup_confirmed)
        self.assertEqual((await self.service.status())["reason"], "audio_capacity")
        self.assertEqual((await self.service.read("one"))["observations"], [])
        self.mode = "normal"; self.processor.failed = True
        await self.service.start_session("two", permission())
        await until(lambda: self.service.current.cleanup_confirmed)
        status = await self.service.status()
        self.assertEqual(status["reason"], "recognition_failed")
        self.assertNotIn("Private", str(status))

    async def test_retention_erases_queued_pcm_and_incomplete_segments_during_slow_asr(self):
        clock = [100.0]; self.service.clock = lambda: clock[0]
        self.processor.release.clear()
        self.addCleanup(self.processor.release.set)
        await self.service.start_session("one", permission(1))
        await until(self.processor.entered.is_set)
        session = self.service.current
        value = dict(type="pcm", user_id="300", at="2026-11-24T00:00:00Z", pcm=base64.b64encode(b"\x00" * 16).decode())
        session._receive(value)
        session._receive(dict(type="segment_end", user_id="300"))
        session._receive(value)
        self.assertEqual((session.queue.qsize(), len(session.buffers)), (1, 1))
        clock[0] = 102.0
        self.assertEqual((await self.service.read("one"))["observations"], [])
        self.assertEqual((session.queue.qsize(), len(session.buffers), session.discarded), (0, 0, 2))
        self.processor.release.set()
        await until(lambda: session.discarded == 3)
        self.assertEqual((await self.service.read("one"))["observations"], [])
        self.assertEqual(session.sequence, 0)

    async def test_session_ceiling_and_explicit_new_sessions_release_all_helpers(self):
        self.mode = "eof"
        for number in range(64):
            result = await self.service.start_session(str(number), permission())
            await until(lambda: self.service.current.cleanup_confirmed)
            self.assertIn(result["state"], ("listening", "failed"))
        self.assertEqual((await self.service.start_session("65", permission())).code, "voice.session_limit")
        self.assertEqual(len(self.processes), 64)
        self.assertTrue(all(p.returncode is not None for p in self.processes))
        self.assertEqual((await self.service.read("0"))["observations"], [])
        self.assertEqual(set(self.service.history["0"]), {"summary", "fingerprint"})

    async def test_stop_during_process_creation_waits_and_drains_owned_helper(self):
        original = self.service.spawn
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed_spawn():
            entered.set()
            await release.wait()
            return await original()
        self.service.spawn = delayed_spawn
        starting = asyncio.create_task(self.service.start_session("one", permission()))
        await entered.wait()
        stopping = asyncio.create_task(self.service.stop_session("one"))
        await until(lambda: self.service.current.closing)
        release.set()
        await asyncio.wait_for(asyncio.gather(starting, stopping), 10)
        self.assertEqual(len(self.processes), 1)
        self.assertIsNotNone(self.processes[0].returncode)
        self.assertTrue(self.service.current.cleanup_confirmed)

    async def test_helper_environment_contains_only_named_bot_credential(self):
        captured = {}
        async def create(*args, **kwargs):
            captured.update(args=args, **kwargs)
            return "created"
        with patch.dict("os.environ", {"NTK_TEST_TOKEN": "test-bot-credential", "OTHER_SECRET": "unrelated", "NODE_OPTIONS": "unwanted"}), \
                patch("asyncio.create_subprocess_exec", create):
            self.assertEqual(await _Voice.spawn(self.service), "created")
        self.assertNotIn("test-bot-credential", str(captured["args"]))
        self.assertEqual(captured["env"]["NTK_DISCORD_TOKEN"], "test-bot-credential")
        self.assertNotIn("OTHER_SECRET", captured["env"])
        self.assertNotIn("NODE_OPTIONS", captured["env"])
        self.assertNotIn("NTK_TEST_TOKEN", captured["env"])


class VoiceInputTests(unittest.TestCase):
    def test_read_pages_respect_json_budget_without_losing_sequence(self):
        session = Session(SimpleNamespace(clock=lambda: 10.0), "one", permission())
        for sequence in range(1, 4):
            session.observations.append((20.0, dict(sequence=sequence, text="猫" * 5000)))
        session.sequence = 3
        after = 0
        seen = []
        while True:
            page = session.read(after, 4)
            self.assertLessEqual(len(json.dumps(page, ensure_ascii=True).encode()), 49152)
            seen.extend(value["sequence"] for value in page["observations"])
            if page["next_after"] is None: break
            self.assertGreater(page["next_after"], after)
            after = page["next_after"]
        self.assertEqual(seen, [1, 2, 3])

    def test_model_identity_rejects_missing_modified_and_extra_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"; model.mkdir()
            manifest = root / "manifest.json"
            original = b"known model bytes"
            manifest.write_text(json.dumps(dict(files={"data": dict(bytes=len(original), sha256=hashlib.sha256(original).hexdigest())})), encoding="utf-8")
            with patch.object(_model_files, "MANIFEST", manifest):
                with self.assertRaisesRegex(ValueError, "files"): _model_files.verify_model(model)
                (model / "data").write_bytes(original)
                _model_files.verify_model(model)
                (model / "data").write_bytes(b"!" + original[1:])
                with self.assertRaisesRegex(ValueError, "hash"): _model_files.verify_model(model)
                (model / "data").write_bytes(original)
                (model / "extra").write_bytes(b"")
                with self.assertRaisesRegex(ValueError, "files"): _model_files.verify_model(model)

    def test_consent_is_explicit_bounded_and_copied(self):
        value = permission(); accepted = consent(value)
        value["participants"].clear()
        self.assertEqual(accepted["participants"], {"300": "synthetic test input"})
        for invalid in ({}, dict(permission(), retention_seconds=True), dict(permission(), retention_seconds=301),
                        dict(permission(), participants={}), dict(permission(), participants={300: "ref"})):
            with self.subTest(value=invalid), self.assertRaises((ValueError, TypeError)): consent(invalid)
        for raw in (b'{"type":"ready","type":"pcm"}', b'{"type":NaN}', b'null', b'[' * 10000):
            with self.subTest(raw=raw[:30]), self.assertRaises((ValueError, RecursionError)): frame(raw)


if __name__ == "__main__": unittest.main()
