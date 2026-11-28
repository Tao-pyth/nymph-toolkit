"""Bounded, canonical record inputs; no inference or source verification."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import json
import re

KINDS = ("experience", "knowledge")
SOURCES = ("observed", "reported", "inferred", "imagined", "dream")
FIELDS = {"record_id", "kind", "content", "source_kind", "source", "occurred_at"}
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", re.ASCII)


def identifier(value):
    if (type(value) is not str or not value or value != value.strip()
            or len(value.encode("utf-8")) > 128):
        raise ValueError("record_id must be nonempty, trimmed UTF-8 text of at most 128 bytes")
    return value


class RecordTooLarge(ValueError):
    """The normalized record exceeds the Memory wire limit."""


def timestamp(value):
    if not STAMP.fullmatch(value):
        raise ValueError("occurred_at must be an RFC 3339 timestamp with seconds and a timezone")
    if not value.endswith("Z"):
        offset = value[-6:]
        if int(offset[1:3]) > 23 or int(offset[4:]) > 59:
            raise ValueError("Invalid timezone offset")
    return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()


def canonical(record):
    if type(record) is not dict or set(record) != FIELDS:
        raise ValueError("record must have exactly record_id, kind, content, source_kind, source, occurred_at")
    if any(type(v) is not str for v in record.values()):
        raise ValueError("record fields must be strings")
    identifier(record["record_id"])
    if record["kind"] not in KINDS or record["source_kind"] not in SOURCES:
        raise ValueError("Unknown kind or source_kind")
    if not record["content"].strip() or not record["source"].strip():
        raise ValueError("content and source must not be empty")
    result = dict(record)
    result["occurred_at"] = timestamp(record["occurred_at"])
    # Validate Unicode before JSON escaping could hide unpaired surrogates.
    for value in result.values():
        value.encode("utf-8")
    payload = json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    if len(payload.encode("ascii")) > 4096:
        raise RecordTooLarge("Normalized record exceeds 4096 JSON bytes")
    return result, payload
