"""Bounded consent, configuration and helper frames. Never accept credentials."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def dump(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def snapshot(value, limit=49152):
    raw = dump(value)
    if len(raw.encode("ascii")) > limit:
        raise ValueError("Voice data exceeds its JSON limit")
    return json.loads(raw)


def fields(value, expected):
    if type(value) is not dict or set(value) != set(expected.split()):
        raise ValueError("Unexpected voice input fields")


def text(value, limit=128):
    if type(value) is not str or not value or value.strip() != value or "\x00" in value or len(value.encode("utf-8")) > limit:
        raise ValueError("Expected bounded, trimmed, nonempty UTF-8 text")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Expected bounded integer, excluding bool")


def user_id(value):
    if type(value) is not str or not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ValueError("Expected Discord identifier as a decimal string")
    return value


def configuration(value):
    fields(value, "node_executable node_modules_path model_path guild_id voice_channel_id token_env")
    result = {}
    for name in ("node_executable", "node_modules_path", "model_path"):
        item = value[name]
        if type(item) is not str or not item or not Path(item).is_absolute():
            raise ValueError("Voice runtime and model paths must be absolute")
        if name == "node_executable" and not Path(item).is_file():
            raise ValueError("Voice node_executable is not an existing file")
        if name != "node_executable" and not Path(item).is_dir():
            raise ValueError("Voice dependency/model directory does not exist")
        result[name] = item
    for name in ("guild_id", "voice_channel_id"):
        result[name] = user_id(value[name])
    if type(value["token_env"]) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value["token_env"]):
        raise ValueError("token_env must be an environment-variable name, never a token")
    result["token_env"] = value["token_env"]
    return result


def consent(value):
    fields(value, "notice_ref participants retention_seconds")
    refs = value["participants"]
    if type(refs) is not dict or not 1 <= len(refs) <= 8:
        raise ValueError("Consent requires 1..8 participants")
    integer(value["retention_seconds"], 1, 300)
    result = dict(notice_ref=text(value["notice_ref"], 512), participants={user_id(k): text(v, 512) for k, v in sorted(refs.items())},
                  retention_seconds=value["retention_seconds"])
    return snapshot(result, 32768)


def fingerprint(value):
    return hashlib.sha256(dump(value).encode("ascii")).hexdigest()


def timestamp(value):
    text(value)
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Voice timestamps require an explicit UTC offset")
    return at.astimezone(timezone.utc).isoformat()


def frame(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate helper field")
            result[key] = value
        return result
    if len(raw) > 131072:
        raise ValueError("Voice helper frame exceeds its limit")
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite helper number")))
    if type(value) is not dict or type(value.get("type")) is not str:
        raise ValueError("Invalid voice helper frame")
    return value
