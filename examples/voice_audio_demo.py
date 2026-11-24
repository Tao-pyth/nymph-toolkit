"""Offline PCM features; explicitly add --model and optionally --wav for real ASR."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import math
from pathlib import Path
import struct
import wave

from nymph_toolkit.adapters.discord_voice._audio import MAX_PCM_BYTES, Processor, features, mono_pcm


def audio(path=None):
    if path is None:
        # A self-generated 440 Hz stereo tone, not a person's voice.
        return b"".join(struct.pack("<hh", value, value) for value in
                        (round(8192 * math.sin(2 * math.pi * 440 * i / 48000)) for i in range(4800)))
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (2, 2, 48000, "NONE"):
            raise ValueError("WAV must be uncompressed 48 kHz / signed 16-bit / stereo")
        if not 1 <= source.getnframes() <= MAX_PCM_BYTES // 4:
            raise ValueError("WAV must contain 1 sample..5 seconds; it will not be truncated")
        pcm = source.readframes(source.getnframes())
        if len(pcm) != source.getnframes() * 4:
            raise ValueError("WAV sample data is incomplete")
        return pcm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Explicitly installed vosk-model-small-ja-0.22 directory")
    parser.add_argument("--wav", type=Path, help="An authorized local PCM WAV; never contacts Discord")
    args = parser.parse_args()
    pcm = audio(args.wav)
    acoustic = features(mono_pcm(pcm))
    if args.wav is None:
        assert acoustic["duration_seconds"] == .1 and .17 < acoustic["rms"] < .18
        assert acoustic["peak"] == .25
    result = dict(features=acoustic, recognition="not requested")
    if args.model is not None:
        result = Processor(str(args.model.resolve())).process(pcm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("offline voice perception: PASS (no Discord connection)")


if __name__ == "__main__": main()
