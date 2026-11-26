"""Validate public receipts without importing another feature's internals."""

# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import re


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def copy(value, limit=49152):
    raw = dump(value)
    if len(raw.encode("ascii")) > limit:
        raise ValueError("Sleep activity data exceeds its JSON limit")
    return json.loads(raw)


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError("Expected fields: " + names)


def text(value):
    if type(value) is not str or not value or value.strip() != value or "\x00" in value or len(value.encode("utf-8")) > 128:
        raise ValueError("Expected nonempty trimmed UTF-8 identifier, at most 128 bytes")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Expected bounded integer, excluding bool")


def request(value):
    fields(value, "request_id expected_revision record_ids apply_persona")
    text(value["request_id"])
    integer(value["expected_revision"], 0, 4096)
    ids = value["record_ids"]
    if type(ids) is not list or len(ids) > 4 or any(text(x) != x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("Expected 0..4 distinct record identifiers")
    if type(value["apply_persona"]) is not bool:
        raise ValueError("apply_persona must be bool")
    return dict(value, record_ids=sorted(ids))


def cycle_id(module_id, value):
    return "sleep-activity:" + hashlib.sha256(dump([module_id, value]).encode("ascii")).hexdigest()


def traits(value, *, delta=False):
    if type(value) is not dict or not 1 <= len(value) <= 32:
        raise ValueError("Expected Persona traits")
    for name, number in value.items():
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name):
            raise ValueError("Invalid Persona trait name")
        integer(number, -5 if delta else 0, 5 if delta else 1000)
        if delta and number == 0:
            raise ValueError("Sleep proposal must not contain zero deltas")


def cycle_receipt(value, row, identity):
    value = copy(value, 32768)
    fields(value, "cycle_id revision policy retained_ids forgotten_ids source_counts expired_dream_ids dreams evaluated_ids contributions persona_proposal")
    if value["cycle_id"] != row["cycle_id"] or value["revision"] != row["request"]["expected_revision"] + 1 or value["policy"] != "consolidation-v1":
        raise ValueError("Sleep receipt does not match the submitted cycle")
    integer(value["revision"], 1, 4096)
    for name, limit in (("retained_ids", 16), ("forgotten_ids", 16), ("evaluated_ids", 4), ("expired_dream_ids", 1)):
        ids = value[name]
        if type(ids) is not list or len(ids) > limit or any(text(x) != x for x in ids) or len(ids) != len(set(ids)):
            raise ValueError("Invalid Sleep receipt identifiers")
    if not set(value["evaluated_ids"]) <= set(row["request"]["record_ids"]):
        raise ValueError("Sleep evaluated unrequested records")
    fields(value["source_counts"], "observed reported inferred imagined dream")
    for count in value["source_counts"].values():
        integer(count, 0, 16)
    if sum(value["source_counts"].values()) != len(value["retained_ids"]):
        raise ValueError("Sleep source counts disagree")
    if type(value["dreams"]) is not list or len(value["dreams"]) > 1 or type(value["contributions"]) is not list or len(value["contributions"]) > 4:
        raise ValueError("Invalid Sleep receipt summaries")
    proposal = value["persona_proposal"]
    if proposal is not None:
        fields(proposal, "command_id expected_revision deltas reason source")
        expected = "sleep-persona:" + hashlib.sha256(dump([identity["sleep_module_id"], row["cycle_id"]]).encode("ascii")).hexdigest()
        if proposal["command_id"] != expected:
            raise ValueError("Unexpected Persona command identity")
        integer(proposal["expected_revision"], 0, 2**63 - 1)
        traits(proposal["deltas"], delta=True)
        if proposal["reason"] != "Sleep consolidation-v1: observed labelled experience":
            raise ValueError("Unexpected proposal reason")
        if proposal["source"] != dict(actor_id=identity["sleep_module_id"], reference="sleep-cycle:" + row["cycle_id"]):
            raise ValueError("Unexpected proposal source")
    return value


def persona_receipt(value, proposal):
    value = copy(value, 8192)
    fields(value, "sequence command_id status previous_revision revision before after reason source stored_at")
    integer(value["sequence"], 1, 4096)
    integer(value["previous_revision"], 0, 2**63 - 1)
    integer(value["revision"], 1, 2**63 - 1)
    traits(value["before"]); traits(value["after"])
    expected = dict(value["before"])
    for name, delta in proposal["deltas"].items():
        if name not in expected:
            raise ValueError("Missing updated Persona trait")
        expected[name] += delta
    if (value["command_id"] != proposal["command_id"] or value["status"] != "applied"
            or value["previous_revision"] != proposal["expected_revision"]
            or value["revision"] != value["previous_revision"] + 1 or value["after"] != expected
            or value["reason"] != proposal["reason"] or value["source"] != proposal["source"]):
        raise ValueError("Persona receipt does not match the proposal")
    from datetime import datetime
    at = datetime.fromisoformat(value["stored_at"].replace("Z", "+00:00"))
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Persona receipt requires an explicit time offset")
    return value


def record(value, identity):
    value = copy(value)
    fields(value, "request cycle_id activity phase cycle persona error")
    normalized = request(value["request"])
    if normalized != value["request"] or value["cycle_id"] != cycle_id(identity["module_id"], normalized):
        raise ValueError("Invalid stored request identity")
    fields(value["activity"], "requester_id activity_id")
    for item in value["activity"].values():
        text(item)
    phase = value["phase"]
    if phase not in ("prepared", "cycle_sent", "cycle_saved", "apply_sent", "completed", "failed"):
        raise ValueError("Unknown execution phase")
    if value["cycle"] is not None:
        cycle_receipt(value["cycle"], value, identity)
    elif phase in ("cycle_saved", "apply_sent", "completed") or value["persona"] is not None:
        raise ValueError("Phase requires a confirmed cycle")
    if phase in ("prepared", "cycle_sent") and value["cycle"] is not None:
        raise ValueError("Unconfirmed phase has a confirmed cycle")
    if value["persona"] is not None:
        if not normalized["apply_persona"] or value["cycle"]["persona_proposal"] is None:
            raise ValueError("Unexpected Persona receipt")
        persona_receipt(value["persona"], value["cycle"]["persona_proposal"])
        if phase != "completed":
            raise ValueError("Persona receipt requires completion")
    if phase == "apply_sent" and (not normalized["apply_persona"] or value["cycle"]["persona_proposal"] is None):
        raise ValueError("Unrequested Persona apply")
    if phase == "completed" and normalized["apply_persona"] and value["cycle"]["persona_proposal"] is not None and value["persona"] is None:
        raise ValueError("Completion lacks confirmed Persona apply")
    if value["error"] is not None:
        fields(value["error"], "kind message")
        if any(type(x) is not str or len(x) > 512 for x in value["error"].values()):
            raise ValueError("Invalid bounded failure description")
    return value
