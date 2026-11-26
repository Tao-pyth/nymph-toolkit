"""Live example preflight is offline, early, and never discloses credentials."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from examples import voice_capture
from nymph_toolkit.contracts import Placement


class VoiceExampleTests(unittest.TestCase):
    def test_bad_credentials_fail_before_runtime_and_do_not_leak(self):
        for value in (None, "", "private-credential" * 300):
            environment = {"OTHER_SECRET": "private-unrelated"}
            if value is not None:
                environment["VOICE_TEST_TOKEN"] = value
            with patch.dict(os.environ, environment, clear=True), patch.object(voice_capture, "Runtime") as runtime:
                with self.assertRaises(ValueError) as raised:
                    asyncio.run(voice_capture.capture({"token_env": "VOICE_TEST_TOKEN"}, {}, seconds=30,
                                placement=Placement.PROCESS, via_core=False, show_text=False))
                runtime.assert_not_called()
                self.assertIn("this shell", str(raised.exception))
                self.assertNotIn("private", str(raised.exception))

    def test_invalid_config_name_is_not_echoed_or_used_for_lookup(self):
        for config in (None, [], {}, {"token_env": "private.invalid.name"}, {"token_env": 1}):
            with patch.object(os.environ, "get") as lookup:
                with self.assertRaises(ValueError) as raised:
                    voice_capture.check_credential(config)
                lookup.assert_not_called()
                self.assertNotIn("private", str(raised.exception))

    def test_cli_error_is_actionable_without_traceback_and_valid_input_reaches_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, consent = {"token_env": "VOICE_TEST_TOKEN"}, {"fixture": True}
            (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
            (root / "consent.json").write_text(json.dumps(consent), encoding="utf-8")
            args = ["voice_capture", "--config", str(root / "config.json"), "--consent", str(root / "consent.json")]
            with patch("sys.argv", args), patch.dict(os.environ, {}, clear=True), \
                    patch.object(voice_capture, "capture", new_callable=AsyncMock) as capture:
                output = io.StringIO()
                with contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as raised:
                    voice_capture.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("Set the Bot token", output.getvalue())
                self.assertNotIn("Traceback", output.getvalue())
                capture.assert_not_called()
            with patch("sys.argv", args), patch.dict(os.environ, {"VOICE_TEST_TOKEN": "private-fixture"}), \
                    patch.object(voice_capture, "capture", new_callable=AsyncMock) as capture:
                voice_capture.main()
                capture.assert_awaited_once_with(config, consent, seconds=30, placement=Placement.PROCESS,
                                                via_core=False, show_text=False)
                self.assertEqual(os.environ["VOICE_TEST_TOKEN"], "private-fixture")


if __name__ == "__main__": unittest.main()
