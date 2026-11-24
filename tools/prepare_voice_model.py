"""Explicitly fetch and verify the supported ASR model; never run by Runtime."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

from nymph_toolkit.adapters.discord_voice._model_files import MANIFEST, verify_model


def prepare(destination):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    destination = destination.resolve()
    if destination.exists():
        verify_model(destination)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Download, validate and extract in a temporary sibling; publish once valid.
    with tempfile.TemporaryDirectory(prefix="ntk-model-", dir=destination.parent) as directory:
        temporary = Path(directory)
        archive = temporary / "model.zip"
        size, digest = 0, hashlib.sha256()
        with urllib.request.urlopen(manifest["source"], timeout=60) as source, archive.open("wb") as target:
            while data := source.read(1048576):
                size += len(data)
                if size > manifest["archive_bytes"]: raise ValueError("Model download exceeds expected size")
                digest.update(data); target.write(data)
        if size != manifest["archive_bytes"] or digest.hexdigest() != manifest["archive_sha256"]:
            raise ValueError("Downloaded model archive size/hash mismatch")
        extracted = temporary / "model"; extracted.mkdir()
        with zipfile.ZipFile(archive) as package:
            expected = manifest["model_id"] + "/"
            for item in package.infolist():
                if item.is_dir(): continue
                name = item.filename.removeprefix(expected)
                if name == item.filename or name not in manifest["files"]:
                    raise ValueError("Unexpected model archive member")
                target = extracted / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        verify_model(extracted)
        if destination.exists(): raise FileExistsError("Model destination appeared during installation")
        extracted.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print("Verified model:", prepare(args.destination))


if __name__ == "__main__": main()
