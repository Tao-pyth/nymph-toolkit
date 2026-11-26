"""Local JSON/PCM pipe fixture. Never connects to Discord or reads credentials."""

# SPDX-License-Identifier: Apache-2.0
import base64
import json
import struct
import sys
import time


def emit(value):
    print(json.dumps(value), flush=True)


def main():
    mode = sys.argv[1]
    initial = json.loads(sys.stdin.readline())
    if initial.get("type") != "start":
        return
    user = initial["participants"][0]
    if mode == "delayed":
        time.sleep(.3)
    emit(dict(type="ready", participants=[user], dave=True))
    if mode == "malformed":
        emit(dict(type="pcm", user_id=user, at="2026-11-24T00:00:00Z", pcm="not-base64!"))
    elif mode == "unknown":
        emit(dict(type="ready", participants=["99999"], dave=True))
    elif mode == "eof":
        return
    else:
        pcm = base64.b64encode(struct.pack("<4h", 1000, 1000, -1000, -1000) * 2400).decode()
        for _ in range(20 if mode == "flood" else 1):
            emit(dict(type="pcm", user_id=user, at="2026-11-24T00:00:00Z", pcm=pcm))
            emit(dict(type="segment_end", user_id=user))
    for line in sys.stdin:
        kind = json.loads(line).get("type")
        if kind == "stop":
            emit(dict(type="stopped", reason="requested"))
            return
        if kind == "segment":
            emit(dict(type="pcm", user_id=user, at="2026-11-24T00:00:00Z", pcm=pcm))
            emit(dict(type="segment_end", user_id=user))


if __name__ == "__main__": main()
