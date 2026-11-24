"""Exercise real optional Vosk on silence; optional authorized speech WAV adds a speech check."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import json
from pathlib import Path
import sys
import time

from nymph_toolkit.adapters.discord_voice._audio import Processor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--wav", type=Path)
    parser.add_argument("--expected-text", help="Expected transcript after whitespace removal")
    args = parser.parse_args()
    if bool(args.wav) != bool(args.expected_text): parser.error("Speech validation requires both --wav and --expected-text")
    started = time.monotonic()
    processor = Processor(str(args.model.resolve()))
    result = processor.process(bytes(48000 * 4))
    assert result["asr"] == dict(text="", words=[]), result["asr"]
    assert result["features"] == dict(duration_seconds=1, rms=0, peak=0, zero_crossing_rate=0)
    if args.wav:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
        from voice_audio_demo import audio
        result = processor.process(audio(args.wav))
        assert "".join(result["asr"]["text"].split()) == "".join(args.expected_text.split())
        assert result["asr"]["words"] and result["features"]["rms"] > 0
    print(json.dumps(dict(model=result["asr_model"], silence="PASS", speech="PASS" if args.wav else "not requested",
                          seconds=time.monotonic() - started), ensure_ascii=False))


if __name__ == "__main__": main()
