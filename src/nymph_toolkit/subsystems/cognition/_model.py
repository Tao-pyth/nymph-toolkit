"""Bounded observation counts with explicit labels, boundaries and provenance."""

# SPDX-License-Identifier: Apache-2.0
from collections import Counter
from datetime import datetime
import hashlib
import json
import re

from nymph_toolkit.contracts import ProtocolError

SOURCES = ("observed", "reported", "inferred", "imagined", "dream")
MAX_SAMPLES = 256
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", re.ASCII)


def dump(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def identifier(value):
    if type(value) is not str or not value or value != value.strip() or len(value.encode("utf-8")) > 128:
        raise ValueError("record_id must be nonempty trimmed UTF-8 text of at most 128 bytes")
    return value


def atom(value):
    if (type(value) is not str or not value or len(value.encode("utf-8")) > 64
            or "\x00" in value or any(c.isspace() for c in value)):
        raise ValueError("tokens and labels require nonempty text without whitespace/NUL, at most 64 UTF-8 bytes")
    return value


def annotations(record_id, tokens, concepts):
    identifier(record_id)
    if type(tokens) is not list or not 1 <= len(tokens) <= 32:
        raise ValueError("tokens requires 1..32 items")
    if type(concepts) is not list or not 0 <= len(concepts) <= 8:
        raise ValueError("concepts requires 0..8 distinct labels")
    tokens = [atom(t) for t in tokens]
    concepts = [atom(c) for c in concepts]
    if len(set(concepts)) != len(concepts):
        raise ValueError("Duplicate concept labels")
    return record_id, tokens, sorted(concepts)


def observation(record, record_id, tokens, concepts):
    text_fields = {"record_id", "kind", "content", "source_kind", "source", "occurred_at", "stored_at"}
    try:
        if (type(record) is not dict or set(record) != text_fields | {"sequence"}
                or any(type(record[k]) is not str or not record[k].strip() for k in text_fields)
                or record["record_id"] != record_id or record["kind"] not in ("experience", "knowledge")
                or record["source_kind"] not in SOURCES or type(record["sequence"]) is not int
                or not 1 <= record["sequence"] <= 2**63 - 1):
            raise ValueError("Malformed Memory record")
        for k in text_fields:
            record[k].encode("utf-8")
        for k in ("occurred_at", "stored_at"):
            stamp = record[k]
            if not STAMP.fullmatch(stamp):
                raise ValueError("Malformed Memory timestamp")
            if not stamp.endswith("Z") and (int(stamp[-5:-3]) > 23 or int(stamp[-2:]) > 59):
                raise ValueError("Invalid Memory timezone")
            datetime.fromisoformat(stamp)
        if len(dump({k: record[k] for k in text_fields - {"stored_at"}}).encode("ascii")) > 4096:
            raise ValueError("Oversized Memory record")
    except (ValueError, TypeError) as error:
        raise ProtocolError("Memory get did not return the records/1 shape") from error
    if "".join(record["content"].split()) != "".join(tokens):
        raise ValueError("tokens must reproduce the Memory content with whitespace removed")
    return {"record_id": record_id, "fingerprint": hashlib.sha256(dump(record).encode("ascii")).hexdigest(),
            "source_kind": record["source_kind"], "tokens": tokens, "concepts": concepts}


def validate_sample(sample):
    if type(sample) is not dict or set(sample) != {"record_id", "fingerprint", "source_kind", "tokens", "concepts"}:
        raise ValueError("Invalid saved observation")
    annotations(sample["record_id"], sample["tokens"], sample["concepts"])
    if (type(sample["fingerprint"]) is not str or not re.fullmatch("[0-9a-f]{64}", sample["fingerprint"])
            or sample["source_kind"] not in SOURCES or sample["concepts"] != sorted(sample["concepts"])):
        raise ValueError("Invalid saved evidence")


def query(token, source_kind, after, limit):
    atom(token)
    if source_kind is not None and (type(source_kind) is not str or source_kind not in SOURCES):
        raise ValueError("Unknown source_kind")
    if type(after) is not int or not 0 <= after <= 2**63 - 1 or type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError("after requires 0..2^63-1; limit requires 1..8")
    return token, source_kind, after, limit


def inspect_samples(samples, token, source_kind, after, limit):
    following, concepts, sources = Counter(), Counter(), Counter()
    count = documents = ends = 0
    evidence = []
    for sequence, sample in samples:
        if source_kind is not None and sample["source_kind"] != source_kind:
            continue
        tokens = sample["tokens"]
        occurrences = tokens.count(token)
        if not occurrences:
            continue
        count += occurrences
        documents += 1
        sources[sample["source_kind"]] += 1
        concepts.update(sample["concepts"])
        for i, value in enumerate(tokens):
            if value == token:
                if i + 1 < len(tokens):
                    following[tokens[i + 1]] += 1
                else:
                    ends += 1
        if sequence > after:
            evidence.append(dict(sequence=sequence, **{k: sample[k] for k in ("record_id", "fingerprint", "source_kind")}))
    def ranked(counter):
        return sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    page = evidence[:limit]
    return {"token": token, "known": count > 0, "count": count, "documents": documents,
            "source_counts": dict(sorted(sources.items())), "end_count": ends,
            "end_probability": ends / count if count else 0.0,
            "successors": [{"token": value, "count": n, "probability": n / count} for value, n in ranked(following)],
            "successor_total": len(following),
            "concepts": [{"label": value, "count": n, "support_ratio": n / documents} for value, n in ranked(concepts)],
            "concept_total": len(concepts), "evidence": page,
            "after": page[-1]["sequence"] if page else after, "has_more": len(evidence) > limit}
