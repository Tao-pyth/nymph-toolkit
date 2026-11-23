"""Bounded local text acquisition; neither interpretation nor Memory internals."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat

from nymph_toolkit.contracts import OperationFailure

MAX_BYTES = 65536
FIELDS = {"path", "record_id", "kind", "source_kind", "occurred_at"}
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", re.ASCII)


def root_path(value):
    root = Path(value).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Document root must be an existing directory")
    return root


def read_record(root, request):
    """Return one Memory records/1 payload, or a business failure before any put."""
    try:
        if type(request) is not dict or set(request) != FIELDS:
            raise ValueError("request requires exactly path, record_id, kind, source_kind, occurred_at")
        if any(type(v) is not str for v in request.values()):
            raise ValueError("request fields must be strings")
        for value in request.values():
            value.encode("utf-8")
        name, key = request["path"], request["record_id"]
        if not key or key != key.strip() or len(key.encode("utf-8")) > 128:
            raise ValueError("record_id must be trimmed nonempty text of at most 128 UTF-8 bytes")
        if request["kind"] not in ("experience", "knowledge") or request["source_kind"] not in (
            "observed", "reported", "inferred", "imagined", "dream"
        ):
            raise ValueError("Unknown kind or source_kind")
        stamp = request["occurred_at"]
        if not STAMP.fullmatch(stamp):
            raise ValueError("occurred_at requires RFC 3339 seconds and timezone")
        if not stamp.endswith("Z") and (int(stamp[-5:-3]) > 23 or int(stamp[-2:]) > 59):
            raise ValueError("Invalid timezone offset")
        occurred = datetime.fromisoformat(stamp).astimezone(timezone.utc).isoformat()
        path = Path(name)
        if not name.strip() or "\x00" in name or path.anchor or ".." in path.parts:
            raise ValueError("path must be relative to root without parent traversal")
        if path.suffix.lower() not in (".txt", ".md"):
            return OperationFailure("document.unsupported", "Only UTF-8 .txt and .md files are supported")
        path = (root / path).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("Resolved path is outside Document root")
        if path.suffix.lower() not in (".txt", ".md"):
            return OperationFailure("document.unsupported", "Resolved file has an unsupported extension")
        if not stat.S_ISREG(path.stat().st_mode):
            return OperationFailure("document.unsupported", "Only regular files are supported")
        with path.open("rb") as source:
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return OperationFailure("document.too_large", "File exceeds 65536 bytes; no record saved")
        text = data.decode("utf-8-sig")
        if not text.strip() or "\x00" in text:
            raise ValueError("Document must contain nonempty text without NUL")
        record = {"record_id": key, "kind": request["kind"], "content": text,
                  "source_kind": request["source_kind"],
                  "source": path.as_uri() + "#sha256=" + hashlib.sha256(data).hexdigest(),
                  "occurred_at": occurred}
        payload = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        if len(payload.encode("ascii")) > 4096:
            return OperationFailure("document.too_large", "Memory record exceeds 4096 JSON bytes; no record saved")
        return record
    except (ValueError, TypeError, OverflowError) as exc:
        return OperationFailure("document.invalid", str(exc))
    except (OSError, RuntimeError):
        return OperationFailure("document.read", "Document could not be read; no record saved")
