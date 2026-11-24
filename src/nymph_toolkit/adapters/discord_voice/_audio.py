"""Local perception of bounded PCM; no language-learning or recording policy."""

# SPDX-License-Identifier: Apache-2.0
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys

from ._model_files import verify_model

SAMPLE_RATE = 48000
MAX_SECONDS = 5
MAX_PCM_BYTES = SAMPLE_RATE * 2 * 2 * MAX_SECONDS
MODEL_ID = "vosk-model-small-ja-0.22"


def mono_pcm(pcm):
    """Decode little-endian stereo and average channels without float overflow."""
    if type(pcm) is not bytes or not pcm or len(pcm) % 4 or len(pcm) > MAX_PCM_BYTES:
        raise ValueError("Expected 1 sample..5 seconds of 48kHz signed-16 stereo PCM")
    stereo = array("h")
    stereo.frombytes(pcm)
    if sys.byteorder != "little":
        stereo.byteswap()
    mono = array("h", ((stereo[index] + stereo[index + 1]) // 2 for index in range(0, len(stereo), 2)))
    return mono


def features(samples):
    count = len(samples)
    if count == 0:
        raise ValueError("Empty audio has no observation")
    energy = sum(value * value for value in samples)
    crossings = sum((samples[index - 1] < 0) != (samples[index] < 0) for index in range(1, count))
    return dict(duration_seconds=count / SAMPLE_RATE, rms=math.sqrt(energy / count) / 32768,
                peak=max(abs(value) for value in samples) / 32768,
                zero_crossing_rate=crossings / max(1, count - 1))


def transcript(results, duration):
    """Validate ASR output, retaining uncertainty instead of inventing annotations."""
    words, texts, previous_end = [], [], 0.0
    for raw in results:
        if type(raw) is not str or len(raw.encode("utf-8")) > 49152:
            raise ValueError("ASR output exceeds its limit")
        result = json.loads(raw)
        if type(result) is not dict or not {"text"} <= set(result) <= {"text", "result"}:
            raise ValueError("Unexpected ASR output shape")
        text = result["text"]
        if type(text) is not str or "\x00" in text or len(text.encode("utf-8")) > 4096:
            raise ValueError("Invalid ASR text")
        if text:
            texts.append(text)
        tokens = result.get("result", [])
        if type(tokens) is not list or len(words) + len(tokens) > 256:
            raise ValueError("ASR word count exceeds its limit")
        for item in tokens:
            if type(item) is not dict or set(item) != {"word", "start", "end", "conf"}:
                raise ValueError("Invalid ASR word shape")
            word, start, end, confidence = (item[key] for key in ("word", "start", "end", "conf"))
            if type(word) is not str or not word or "\x00" in word or len(word.encode("utf-8")) > 256:
                raise ValueError("Invalid ASR word")
            if any(type(number) not in (int, float) or not math.isfinite(number) for number in (start, end, confidence)):
                raise ValueError("ASR word values must be finite numbers")
            if not 0 <= start <= end <= duration + .1 or not 0 <= confidence <= 1 or start < previous_end - .03:
                raise ValueError("Invalid ASR timing/confidence")
            words.append(dict(word=word, start_seconds=start, end_seconds=end, confidence=confidence))
            previous_end = end
    value = dict(text=" ".join(texts), words=words)
    if len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode("ascii")) > 40000:
        raise ValueError("ASR observation exceeds its transport budget")
    return value


class Processor:
    """One worker owns this processor; imports Vosk only when explicitly enabled."""

    def __init__(self, model_path):
        if type(model_path) is not str or not Path(model_path).is_absolute() or not Path(model_path).is_dir():
            raise ValueError("Voice model_path must name an existing absolute directory")
        verify_model(model_path)
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer

    def process(self, pcm):
        samples = mono_pcm(pcm)
        acoustic = features(samples)
        # Vosk's model permits downsampling. Do not substitute decimation, which
        # aliases high frequencies into the ASR band.
        if sys.byteorder != "little":
            samples.byteswap()
        data = samples.tobytes()
        recognizer = self.recognizer(self.model, SAMPLE_RATE)
        recognizer.SetWords(True)
        results = []
        for start in range(0, len(data), 8000):
            if recognizer.AcceptWaveform(data[start:start + 8000]):
                results.append(recognizer.Result())
        results.append(recognizer.FinalResult())
        return dict(asr_model=MODEL_ID, asr=transcript(results, acoustic["duration_seconds"]), features=acoustic,
                    pcm_sha256=hashlib.sha256(pcm).hexdigest(), sample_rate=SAMPLE_RATE, channels=2)
