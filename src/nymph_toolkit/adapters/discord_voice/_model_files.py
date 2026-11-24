"""Identify the explicitly installed model before labeling any observations."""

# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path

MANIFEST = Path(__file__).with_name("model-files.json")


def verify_model(path):
    root = Path(path)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = manifest["files"]
    actual = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}
    if set(actual) != set(expected):
        raise ValueError("Voice model files do not match the supported model")
    for name, spec in expected.items():
        file = actual[name]
        if file.stat().st_size != spec["bytes"]:
            raise ValueError("Voice model file size mismatch")
        with file.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != spec["sha256"]:
            raise ValueError("Voice model file hash mismatch")
