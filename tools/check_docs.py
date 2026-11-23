"""Verify documentation links, formatting, license and standalone handoff."""

# SPDX-License-Identifier: Apache-2.0
import hashlib
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").rglob("*.md"))
    links = 0
    for path in files:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        assert b"\r" not in raw and text.endswith("\n") and "\ufffd" not in text, path
        assert all(line == line.rstrip() for line in text.splitlines()), path
        assert len(re.findall(r"^```", text, re.M)) % 2 == 0, path
        for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if "://" in target:
                continue
            links += 1
            destination, _, fragment = target.partition("#")
            resolved = (path.parent / unquote(destination)).resolve() if destination else path
            assert resolved.is_file(), (path, target)
            if fragment:
                assert f'id="{fragment}"' in resolved.read_text(encoding="utf-8"), (path, target)
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == (
        "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
    )
    subprocess.run([sys.executable, str(ROOT / "tools/build_handoff.py"), "--check"], check=True)
    subprocess.run([sys.executable, str(ROOT / "tools/check_customer_docs.py")], check=True)
    print(f"PASS: {len(files)} Markdown files, {links} local links, UTF-8/LF, license")


if __name__ == "__main__":
    main()
