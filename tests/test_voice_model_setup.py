"""Explicit model installation preserves existing content and rejects changed downloads."""

# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from nymph_toolkit.adapters.discord_voice import _model_files
from tools import prepare_voice_model as setup


class VoiceModelSetupTests(unittest.TestCase):
    def test_verified_archive_publishes_once_and_existing_model_uses_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"fixture model"
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("fixture/config/data", content)
            data = buffer.getvalue()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(dict(model_id="fixture", source="https://example.invalid/model.zip",
                archive_bytes=len(data), archive_sha256=hashlib.sha256(data).hexdigest(),
                files={"config/data": dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())})), encoding="utf-8")
            with patch.object(setup, "MANIFEST", manifest), patch.object(_model_files, "MANIFEST", manifest):
                with patch.object(setup.urllib.request, "urlopen", return_value=io.BytesIO(data)) as download:
                    self.assertEqual(setup.prepare(root / "installed"), root / "installed")
                    download.assert_called_once()
                with patch.object(setup.urllib.request, "urlopen", side_effect=AssertionError("Unrequested network")):
                    self.assertEqual(setup.prepare(root / "installed"), root / "installed")
                    target = root / "installed/config/data"
                    target.write_bytes(b"user changed")
                    with self.assertRaises(ValueError): setup.prepare(root / "installed")
                    self.assertEqual(target.read_bytes(), b"user changed")
                for changed in (data[:-1], b"!" + data[1:], data + b"!"):
                    with self.subTest(size=len(changed)), patch.object(setup.urllib.request, "urlopen", return_value=io.BytesIO(changed)):
                        with self.assertRaises(ValueError): setup.prepare(root / "rejected")
                        self.assertFalse((root / "rejected").exists())
                        self.assertEqual(list(root.glob("ntk-model-*")), [])


if __name__ == "__main__": unittest.main()
