"""Deterministic, bounded consolidation, expiry and externally applied proposals."""

# SPDX-License-Identifier: Apache-2.0
from collections import Counter
from datetime import datetime
import hashlib
import json
import re

SOURCES = ("observed", "reported", "inferred", "imagined", "dream")
MAX_CYCLES = 4096
MAX_ACTIVE = 16


def dump(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def snapshot(value, maximum=49152):
    raw = dump(value)
    if len(raw.encode("ascii")) > maximum:
        raise ValueError("Sleep JSON size limit exceeded")
    return json.loads(raw)


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError("Expected fields: " + names)


def text(value, maximum=128):
    if (type(value) is not str or not value or value != value.strip() or "\x00" in value
            or len(value.encode("utf-8")) > maximum):
        raise ValueError("Expected nonempty trimmed text within the byte limit")
    return value


def atom(value):
    text(value, 64)
    if any(c.isspace() for c in value):
        raise ValueError("Tokens and concepts cannot contain whitespace")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Expected integer in {low}..{high}")
    return value


def trait_name(value):
    if type(value) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value):
        raise ValueError("Invalid Persona trait name")
    return value


def timestamp(value):
    if type(value) is not str or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value, re.ASCII
    ):
        raise ValueError("Expected an explicit offset timestamp")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timestamp offset")
    datetime.fromisoformat(value)
    return value


def rules(value):
    if type(value) is not list or not 1 <= len(value) <= 8:
        raise ValueError("trait_rules requires 1..8 rules")
    result, seen = [], set()
    for row in value:
        fields(row, "concept trait delta")
        label = atom(row["concept"])
        if label in seen or integer(row["delta"], -5, 5) == 0:
            raise ValueError("Rule concepts must be unique and deltas nonzero")
        seen.add(label)
        result.append(dict(concept=label, trait=trait_name(row["trait"]), delta=row["delta"]))
    return sorted(result, key=lambda x: x["concept"])


def request(value):
    fields(value, "cycle_id expected_revision record_ids")
    text(value["cycle_id"])
    integer(value["expected_revision"], 0, MAX_CYCLES)
    ids = value["record_ids"]
    if type(ids) is not list or len(ids) > 4:
        raise ValueError("record_ids requires 0..4 identifiers")
    ids = [text(i) for i in ids]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate record_ids")
    return dict(cycle_id=value["cycle_id"], expected_revision=value["expected_revision"], record_ids=sorted(ids))


def memory_record(value, record_id):
    value = snapshot(value, 8192)
    fields(value, "record_id kind content source_kind source occurred_at sequence stored_at")
    for name in ("record_id", "kind", "content", "source_kind", "source", "occurred_at", "stored_at"):
        if type(value[name]) is not str or not value[name].strip():
            raise ValueError("Malformed Memory text")
        value[name].encode("utf-8")
    if value["record_id"] != record_id or value["kind"] not in ("experience", "knowledge") or value["source_kind"] not in SOURCES:
        raise ValueError("Malformed Memory identity or provenance")
    timestamp(value["occurred_at"]); timestamp(value["stored_at"])
    integer(value["sequence"], 1, 2**63 - 1)
    snapshot({k: v for k, v in value.items() if k not in ("sequence", "stored_at")}, 4096)
    return value


def sample(value):
    value = snapshot(value, 4096)
    fields(value, "record_id fingerprint source_kind tokens concepts annotation_revision")
    text(value["record_id"])
    if type(value["fingerprint"]) is not str or not re.fullmatch("[0-9a-f]{64}", value["fingerprint"]):
        raise ValueError("Invalid Memory fingerprint")
    if type(value["source_kind"]) is not str or value["source_kind"] not in SOURCES:
        raise ValueError("Invalid source kind")
    tokens, concepts = value["tokens"], value["concepts"]
    if type(tokens) is not list or not 1 <= len(tokens) <= 16 or type(concepts) is not list or len(concepts) > 8:
        raise ValueError("Sleep supports 1..16 tokens and 0..8 concepts per record")
    for item in tokens + concepts:
        atom(item)
    if len(set(concepts)) != len(concepts) or concepts != sorted(concepts):
        raise ValueError("Expected distinct sorted concepts")
    integer(value["annotation_revision"], 0, 2**63 - 1)
    return value


def observation(record, annotation):
    annotation = snapshot(annotation, 16384)
    fields(annotation, "record_id fingerprint source_kind tokens concepts revision")
    value = sample({("annotation_revision" if k == "revision" else k): v for k, v in annotation.items()})
    if (record["record_id"] != value["record_id"] or record["source_kind"] != value["source_kind"]
            or hashlib.sha256(dump(record).encode("ascii")).hexdigest() != value["fingerprint"]
            or "".join(record["content"].split()) != "".join(value["tokens"])):
        raise ValueError("Memory and Cognition evidence do not agree")
    return value


def persona(value, identity):
    value = snapshot(value, 4096)
    fields(value, "module_id revision traits updated_at")
    if value["module_id"] != identity["persona_module_id"]:
        raise ValueError("Unexpected Persona provider")
    integer(value["revision"], 0, 2**63 - 1)
    traits = value["traits"]
    if type(traits) is not dict or not 1 <= len(traits) <= 32:
        raise ValueError("Expected 1..32 Persona traits")
    for name, number in traits.items():
        trait_name(name); integer(number, 0, 1000)
    if any(r["trait"] not in traits for r in identity["trait_rules"]):
        raise ValueError("Required Persona trait is missing")
    timestamp(value["updated_at"])
    return value


def initial():
    return dict(revision=0, entries=[], dreams=[])


class ActiveFull(ValueError):
    pass


def transition(previous, credited, value, evidence, traits, identity):
    value = request(value)
    if value["expected_revision"] != previous["revision"]:
        raise ValueError("Cycle revision mismatch")
    if type(evidence) is not list:
        raise ValueError("Expected observed evidence list")
    evidence = [sample(s) for s in evidence]
    if [s["record_id"] for s in evidence] != value["record_ids"]:
        raise ValueError("Cycle evidence does not match requested identifiers")
    traits = persona(traits, identity)
    entries = {s["record_id"]: dict(s, strength=s["strength"] - 250) for s in previous["entries"]}
    for s in evidence:
        entries[s["record_id"]] = dict(s, strength=1000)
    forgotten = sorted(key for key, s in entries.items() if s["strength"] <= 0)
    for key in forgotten:
        del entries[key]
    if len(entries) > MAX_ACTIVE:
        raise ActiveFull("At most 16 active consolidation records are supported")
    entries = [entries[key] for key in sorted(entries)]
    revision = previous["revision"] + 1
    cycle_hash = hashlib.sha256(dump([identity["module_id"], value["cycle_id"]]).encode("ascii")).hexdigest()
    real = [s for s in entries if s["source_kind"] != "dream"]
    dreams = []
    if len(real) >= 2:
        first, second = real[:2]
        tokens = first["tokens"][:(len(first["tokens"]) + 1) // 2] + second["tokens"][len(second["tokens"]) // 2:]
        dreams = [dict(dream_id="sleep-dream:" + cycle_hash, source_kind="dream", tokens=tokens,
                       source_record_ids=[first["record_id"], second["record_id"]], rule="first-half/second-half-v1")]
    evaluated, contributions, totals = [], [], Counter()
    for s in evidence:
        if s["source_kind"] != "observed" or s["record_id"] in credited:
            continue
        evaluated.append(s["record_id"])
        matched = [r for r in identity["trait_rules"] if r["concept"] in s["concepts"]]
        for r in matched:
            totals[r["trait"]] += r["delta"]
        if matched:
            contributions.append(dict(record_id=s["record_id"], rules=matched))
    deltas = {}
    for name, total in sorted(totals.items()):
        current = traits["traits"][name]
        delta = max(-current, min(1000 - current, max(-5, min(5, total))))
        if delta:
            deltas[name] = delta
    proposal = None
    if deltas:
        proposal = dict(command_id="sleep-persona:" + cycle_hash, expected_revision=traits["revision"], deltas=deltas,
                        reason="Sleep consolidation-v1: observed labelled experience", source=dict(
                            actor_id=identity["module_id"], reference="sleep-cycle:" + value["cycle_id"]))
    result = dict(cycle_id=value["cycle_id"], revision=revision, policy="consolidation-v1",
                  retained_ids=[s["record_id"] for s in entries], forgotten_ids=forgotten,
                  source_counts={kind: sum(s["source_kind"] == kind for s in entries) for kind in SOURCES},
                  expired_dream_ids=[d["dream_id"] for d in previous["dreams"]],
                  dreams=[dict(dream_id=d["dream_id"], source_kind="dream", sha256=hashlib.sha256(dump(d).encode("ascii")).hexdigest()) for d in dreams],
                  evaluated_ids=evaluated, contributions=contributions, persona_proposal=proposal)
    return dict(revision=revision, entries=entries, dreams=dreams), snapshot(result), evaluated


def page(state, after, limit):
    integer(after, 0, MAX_ACTIVE); integer(limit, 1, 4)
    items = state["entries"][after:after + limit]
    return snapshot(dict(revision=state["revision"], total_entries=len(state["entries"]), entries=items,
                         next_after=after + len(items) if after + len(items) < len(state["entries"]) else None,
                         dreams=state["dreams"]))


def inspect(state, concept, source_kind):
    atom(concept)
    if source_kind is not None and (type(source_kind) is not str or source_kind not in SOURCES):
        raise ValueError("Invalid source_kind")
    entries = [s for s in state["entries"] if concept in s["concepts"] and (source_kind is None or s["source_kind"] == source_kind)]
    return snapshot(dict(revision=state["revision"], concept=concept, source_kind=source_kind,
                         records=len(entries), strength=sum(s["strength"] for s in entries),
                         source_counts={kind: sum(s["source_kind"] == kind for s in entries) for kind in SOURCES},
                         evidence=[{k: s[k] for k in ("record_id", "fingerprint", "source_kind", "annotation_revision", "strength")} for s in entries]))
