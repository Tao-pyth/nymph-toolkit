"""Independent acoustic expectations and hostile/bounded ASR output checks."""

# SPDX-License-Identifier: Apache-2.0
from array import array
import json
import math
import struct
import unittest

from nymph_toolkit.adapters.discord_voice._audio import MAX_PCM_BYTES, features, mono_pcm, transcript


class AudioTests(unittest.TestCase):
    def test_channel_average_and_independent_acoustic_values(self):
        pcm = struct.pack("<8h", 32767, 32767, -32768, -32768, 100, -100, 20, 40)
        values = mono_pcm(pcm)
        self.assertEqual(list(values), [32767, -32768, 0, 30])
        result = features(values)
        self.assertEqual(result["duration_seconds"], 4 / 48000)
        self.assertEqual(result["peak"], 1)
        self.assertAlmostEqual(result["rms"], math.sqrt((32767**2 + 32768**2 + 30**2) / 4) / 32768)
        self.assertAlmostEqual(result["zero_crossing_rate"], 2 / 3)
        silent = features(array("h", [0] * 48000))
        self.assertEqual(silent, dict(duration_seconds=1, rms=0, peak=0, zero_crossing_rate=0))

    def test_pcm_boundaries_without_truncation(self):
        self.assertEqual(len(mono_pcm(bytes(MAX_PCM_BYTES))), 240000)
        for pcm in (b"", b"\x00", bytes(6), bytes(MAX_PCM_BYTES + 4), bytearray(4), None):
            with self.subTest(size=len(pcm) if pcm is not None else None), self.assertRaises(ValueError): mono_pcm(pcm)

    def test_word_times_confidence_silence_and_invalid_outputs(self):
        item = dict(text="猫", result=[dict(word="猫", start=.1, end=.4, conf=.8)])
        result = transcript([json.dumps(item), '{"text":""}'], .5)
        self.assertEqual(result, dict(text="猫", words=[dict(word="猫", start_seconds=.1, end_seconds=.4, confidence=.8)]))
        self.assertEqual(transcript(['{"text":""}'], 1), dict(text="", words=[]))
        for raw in ('null', '{"text":42}', '{"text":"","unknown":1}', '{"text":"x","result":false}',
                    json.dumps(dict(item, result=[dict(item["result"][0], conf=True)])),
                    json.dumps(dict(item, result=[dict(item["result"][0], end=12)])),
                    json.dumps(dict(item, result=[dict(item["result"][0], start=float("nan"))]))):
            with self.subTest(raw=raw), self.assertRaises(ValueError): transcript([raw], .5)


if __name__ == "__main__": unittest.main()
