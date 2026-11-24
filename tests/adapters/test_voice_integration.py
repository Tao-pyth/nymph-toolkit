"""Core routes/placements and cleanup with synthetic audio, not live Discord/ASR proof."""

# SPDX-License-Identifier: Apache-2.0
import ast
import asyncio
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from nymph_toolkit.adapters import discord_voice
from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.contracts.voice import VOICE_CONTRACT
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from tests.doubles.voice import CONTROL_CONTRACT, CONTROL_KEY


def group_at(root, requester, provider):
    store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    group = HybridGroup(HybridSettings(15, 15, 60, 65536, 32, 4), store)
    config = dict(node_executable=sys.executable, node_modules_path=str(root), model_path=str(root),
                  guild_id="100", voice_channel_id="200", token_env="NTK_TEST_TOKEN")
    group.register_module(ModuleSpec("voice", ModuleKind.ADAPTER), ModuleAdvertisement("voice", "1.10.0", (VOICE_CONTRACT,)),
                          "tests.doubles.voice:factory", config, provider)
    group.register_module(ModuleSpec("requester", ModuleKind.SUBSYSTEM, ("voice",)),
                          ModuleAdvertisement("requester", "test", (CONTROL_CONTRACT,)), "tests.doubles.voice:requester", {}, requester)
    return group


class VoiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_maximum_text_and_word_count_cross_minimum_core_frame_limit(self):
        for direct in (False, True):
            with self.subTest(direct=direct), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / "large-test").touch()
                group = group_at(root, Placement.LOCAL, Placement.PROCESS)
                runtime = Runtime(group)
                await runtime.start()
                try:
                    result = await group.modules["requester"].invoke("invoke", dict(contract=CONTROL_KEY,
                        operation="exercise", args=[direct, False], kwargs={}), timeout=40)
                    item, = result["page"]["observations"]
                    self.assertEqual(len(item["asr"]["text"].encode("utf-8")), 4095)
                    self.assertEqual(len(item["asr"]["words"]), 256)
                    self.assertTrue(result["stopped"]["cleanup_confirmed"])
                finally:
                    await runtime.stop()
                self.assertTrue(group.process("voice").cleanup_confirmed, group.process("voice"))

    async def test_four_placements_both_routes_revoke_runtime_stop_and_restart(self):
        expected_hash = hashlib.sha256(struct.pack("<4h", 1000, 1000, -1000, -1000) * 2400).hexdigest()
        for requester in Placement:
            for provider in Placement:
                for direct in (False, True):
                    with self.subTest(requester=requester, provider=provider, direct=direct), tempfile.TemporaryDirectory() as directory:
                        root = Path(directory).resolve()
                        for restored in (False, True):
                            group = group_at(root, requester, provider)
                            runtime = Runtime(group)
                            await runtime.start()
                            try:
                                result = await group.modules["requester"].invoke("invoke", dict(contract=CONTROL_KEY,
                                    operation="exercise", args=[direct, restored], kwargs={}), timeout=40)
                                self.assertEqual(result["before"]["state"], "inactive")
                                self.assertEqual(result["before"]["observation_count"], 0)
                                self.assertEqual(result["started"]["state"], "listening")
                                item, = result["page"]["observations"]
                                self.assertEqual((item["sequence"], item["source_kind"], item["user_id"]), (1, "observed", "300"))
                                self.assertEqual((item["guild_id"], item["voice_channel_id"]), ("100", "200"))
                                self.assertEqual(item["pcm_sha256"], expected_hash)
                                self.assertAlmostEqual(item["features"]["duration_seconds"], .1)
                                self.assertAlmostEqual(item["features"]["rms"], 1000 / 32768)
                                if not restored:
                                    self.assertEqual(result["stopped"]["reason"], "revoked")
                                    self.assertTrue(result["stopped"]["cleanup_confirmed"])
                                    self.assertEqual(result["cleared"]["observations"], [])
                                    self.assertEqual(result["replay"]["state"], "stopped")
                            finally:
                                await runtime.stop()
                            self.assertEqual(json.loads((root / "voice-stopped.json").read_text(encoding="utf-8")),
                                             dict(processes=[0], worker_released=True, current_released=True, history_count=0))
                            for name in group.modules:
                                self.assertTrue(group.process(name).cleanup_confirmed, group.process(name))
                            self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])

    def test_voice_uses_public_contracts_without_core_or_other_feature_imports(self):
        for path in Path(discord_voice.__file__).parent.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse(any(n.startswith(("nymph_toolkit.core", "nymph_toolkit.subsystems", "nymph_toolkit.adapters")) for n in names), path)


if __name__ == "__main__": unittest.main()
