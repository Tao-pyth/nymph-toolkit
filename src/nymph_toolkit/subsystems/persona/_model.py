"""Bounded trait values and atomic external deltas, without a decision policy."""

# SPDX-License-Identifier: Apache-2.0
import json
import re

from nymph_toolkit.contracts import OperationFailure


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Expected integer in {low}..{high}, excluding bool")


def text(value, limit):
    if (type(value) is not str or not value or value != value.strip() or "\x00" in value
            or len(value.encode("utf-8")) > limit):
        raise ValueError("Expected bounded, nonempty, trimmed UTF-8 text without NUL")
    return value


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError("Expected fields: " + names)


def traits(value, *, delta=False):
    if type(value) is not dict or not 1 <= len(value) <= 32:
        raise ValueError("Expected 1..32 traits")
    for key, number in value.items():
        if type(key) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key):
            raise ValueError("Trait names require lowercase ASCII identifiers (1..32 characters)")
        integer(number, -1000 if delta else 0, 1000)
    return dict(sorted(value.items()))


def request(value, names):
    # Every accepted leaf is a primitive of a checked type. Rebuild all mappings
    # before awaiting, rather than retaining mutable caller dictionaries.
    fields(value, "command_id expected_revision deltas reason source")
    integer(value["expected_revision"], 0, 2**63 - 1)
    deltas = traits(value["deltas"], delta=True)
    if set(deltas) - set(names):
        raise ValueError("Unknown trait")
    fields(value["source"], "actor_id reference")
    result = dict(command_id=text(value["command_id"], 128), expected_revision=value["expected_revision"],
                  deltas=deltas, reason=text(value["reason"], 512),
                  source=dict(actor_id=text(value["source"]["actor_id"], 128),
                              reference=text(value["source"]["reference"], 512)))
    if len(dump(result).encode("ascii")) > 4096:
        raise ValueError("Canonical Persona request exceeds 4096 bytes")
    return result


def apply(state, value, sequence, at):
    if value["expected_revision"] != state["revision"]:
        return OperationFailure("persona.revision_conflict", "Persona revision changed")
    after = dict(state["traits"])
    for key, delta in value["deltas"].items():
        if not 0 <= after[key] + delta <= 1000:
            return OperationFailure("persona.invalid", "A resulting trait would exceed 0..1000; nothing applied")
        after[key] += delta
    changed = after != state["traits"]
    new = dict(state, traits=after, revision=state["revision"] + int(changed),
               updated_at=at if changed else state["updated_at"])
    receipt = dict(sequence=sequence, command_id=value["command_id"],
                   status="applied" if changed else "no_change", previous_revision=state["revision"],
                   revision=new["revision"], before=state["traits"], after=after,
                   reason=value["reason"], source=value["source"], stored_at=at)
    return new, receipt
