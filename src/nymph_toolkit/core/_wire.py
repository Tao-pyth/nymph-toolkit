"""Bounded JSON frames and an explicit NTK value vocabulary; never import wire types."""

# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
import struct

from nymph_toolkit import contracts
from nymph_toolkit.contracts.activities import _Unchanged
from nymph_toolkit.contracts.hybrid import ProtocolError, RemoteError

VERSION = "ntk.ipc.v1"


def _types():
    return {value.__name__: value for name in contracts.__all__
            if isinstance((value := getattr(contracts, name)), type)
            and (is_dataclass(value) or issubclass(value, Enum))} | {"_Unchanged": _Unchanged}


def encode(value, depth=0):
    if depth > 64:
        raise ProtocolError("Value nesting exceeds 64")
    enc = lambda item: encode(item, depth + 1)
    if isinstance(value, Enum):
        return {"$enum": type(value).__name__, "value": value.value}
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, timedelta):
        return {"$duration_us": (value.days * 86400 + value.seconds) * 1000000 + value.microseconds}
    if isinstance(value, BaseException):
        if isinstance(value, RemoteError):
            return {"$error": [value.module_id, value.remote_type, value.message]}
        return {"$error": ["", type(value).__name__, str(value)]}
    if is_dataclass(value) and type(value).__name__ in _types():
        return {"$type": type(value).__name__, "fields": {f.name: enc(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, Mapping):
        return {"$map": [[enc(k), enc(v)] for k, v in value.items()]}
    if isinstance(value, tuple):
        return {"$tuple": [enc(v) for v in value]}
    if isinstance(value, frozenset):
        return {"$set": [enc(v) for v in sorted(value)]}
    if isinstance(value, list):
        return [enc(v) for v in value]
    raise ProtocolError(f"Unsupported wire value: {type(value).__name__}")


def decode(value, depth=0):
    if depth > 64:
        raise ProtocolError("Value nesting exceeds 64")
    dec = lambda item: decode(item, depth + 1)
    if isinstance(value, list):
        return [dec(v) for v in value]
    if not isinstance(value, dict):
        return value
    try:
        if set(value) == {"$enum", "value"}:
            cls = _types()[value["$enum"]]
            if not issubclass(cls, Enum):
                raise ValueError("Not an enum")
            return cls(value["value"])
        if set(value) == {"$type", "fields"}:
            cls = _types()[value["$type"]]
            if not is_dataclass(cls) or set(value["fields"]) != {f.name for f in fields(cls)}:
                raise ValueError("Invalid record fields")
            return cls(**{k: dec(v) for k, v in value["fields"].items()})
        if set(value) == {"$datetime"}:
            result = datetime.fromisoformat(value["$datetime"])
            if result.tzinfo is None:
                raise ValueError("Naive datetime")
            return result
        if set(value) == {"$duration_us"}:
            if type(value["$duration_us"]) is not int:
                raise ValueError("Invalid duration")
            return timedelta(microseconds=value["$duration_us"])
        if set(value) == {"$error"}:
            if len(value["$error"]) != 3 or not all(isinstance(v, str) for v in value["$error"]):
                raise ValueError("Invalid error")
            return RemoteError(*value["$error"])
        if set(value) == {"$tuple"}:
            return tuple(dec(v) for v in value["$tuple"])
        if set(value) == {"$set"}:
            return frozenset(dec(v) for v in value["$set"])
        if set(value) == {"$map"}:
            result = {}
            for k, v in value["$map"]:
                key = dec(k)
                if key in result:
                    raise ValueError("Duplicate map key")
                result[key] = dec(v)
            return result
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ProtocolError(str(exc)) from exc
    raise ProtocolError("Unknown wire record")


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ProtocolError("Duplicate JSON key")
        result[k] = v
    return result


def _constant(value):
    raise ProtocolError("Nonfinite JSON number: " + value)


def json_value(value):
    """Validate/copy application data without permitting NTK records or arbitrary objects."""
    if isinstance(value, Mapping):
        if not all(isinstance(k, str) for k in value):
            raise ProtocolError("Application object keys must be strings")
        value = {k: json_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        value = [json_value(v) for v in value]
    elif value is not None and type(value) not in (bool, int, float, str):
        raise ProtocolError("Application values must be JSON values")
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProtocolError(str(exc)) from exc


async def read_frame(reader, limit):
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 0 < size <= limit:
        raise ProtocolError("Invalid frame length")
    try:
        return json.loads((await reader.readexactly(size)).decode("utf-8"),
                          object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError(str(exc)) from exc


async def write_frame(writer, value, limit):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProtocolError(str(exc)) from exc
    if not 0 < len(raw) <= limit:
        raise ProtocolError("Frame exceeds configured maximum")
    writer.write(struct.pack("!I", len(raw)) + raw)
    await writer.drain()
