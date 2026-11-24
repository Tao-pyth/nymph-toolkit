"""Bounded, inspectable utility-v1 decisions. No execution or Core imports."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from nymph_toolkit.contracts import ActivityKey, ActivityRequest, ActivityState

POLICY = "utility-v1"
SOURCES = {"observed", "reported", "inferred", "imagined", "dream"}
MOTIVES = {"rest", "explore", "achieve", "social"}


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def snapshot(value, limit):
    def check(item, seen):
        if type(item) in (dict, list):
            if id(item) in seen:
                raise ValueError("JSON cycles are not allowed")
            seen.add(id(item))
            if type(item) is dict:
                if any(type(k) is not str for k in item):
                    raise ValueError("JSON keys must be strings")
                children = item.values()
            else:
                children = item
            for child in children:
                check(child, seen)
            seen.remove(id(item))
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("Only JSON values are allowed")
    check(value, set())
    encoded = dump(value)
    if len(encoded.encode("ascii")) > limit:
        raise ValueError("JSON input exceeds its byte limit")
    return json.loads(encoded)


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError("Expected fields: " + names)


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Expected integer in {low}..{high}, excluding bool")


def identifier(value, limit=128):
    if (type(value) is not str or not value or value != value.strip()
            or "\x00" in value or len(value.encode("utf-8")) > limit):
        raise ValueError("Expected bounded, nonempty, trimmed text without NUL")
    return value


def timestamp(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", value):
        raise ValueError("Time requires ISO date/time with seconds and explicit offset")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone")
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def catalog(value):
    value = snapshot(value, 65536)
    if type(value) is not list or not 1 <= len(value) <= 16:
        raise ValueError("catalog requires 1..16 templates")
    ids = set()
    for item in value:
        fields(item, "template_id motive content executor_module_id executor_id parameters min_seconds max_seconds delay_seconds")
        for key in ("template_id", "executor_module_id", "executor_id"):
            identifier(item[key])
        identifier(item["content"], 512)
        if type(item["motive"]) is not str or item["motive"] not in MOTIVES or item["template_id"] in ids:
            raise ValueError("Unknown motive or duplicate template")
        ids.add(item["template_id"])
        for key in ("min_seconds", "max_seconds"):
            integer(item[key], 1, 86400)
        integer(item["delay_seconds"], 0, 86400)
        if item["min_seconds"] > item["max_seconds"] or type(item["parameters"]) is not dict:
            raise ValueError("Invalid period or parameters")
        snapshot(item["parameters"], 4096)
    return sorted(value, key=lambda item: item["template_id"])


def request(value, templates):
    value = snapshot(value, 16384)
    fields(value, "decision_id now state goals available current")
    identifier(value["decision_id"])
    value["now"] = timestamp(value["now"]).isoformat()
    fields(value["state"], "sleep_pressure cognitive_load social_need")
    for number in value["state"].values():
        integer(number, 0, 1000)
    if type(value["goals"]) is not list or len(value["goals"]) > 8:
        raise ValueError("goals requires a list of at most 8 goals")
    ids = set()
    for goal in value["goals"]:
        fields(goal, "goal_id record_id token importance target_documents")
        identifier(goal["goal_id"]); identifier(goal["record_id"]); identifier(goal["token"], 64)
        if any(c.isspace() for c in goal["token"]) or goal["goal_id"] in ids:
            raise ValueError("Invalid token or duplicate goal")
        ids.add(goal["goal_id"])
        integer(goal["importance"], 0, 1000); integer(goal["target_documents"], 1, 256)
    value["goals"].sort(key=lambda goal: goal["goal_id"])
    available = value["available"]
    if type(available) is not list or any(type(v) is not str for v in available):
        raise ValueError("available requires template IDs")
    if len(set(available)) != len(available) or set(available) - {v["template_id"] for v in templates}:
        raise ValueError("Unknown or duplicate available template")
    value["available"] = sorted(available)
    current = value["current"]
    if current is not None:
        fields(current, "decision_id state revision planned_end_notified supports_pause")
        identifier(current["decision_id"])
        if type(current["state"]) is not str or current["state"] not in {s.value for s in ActivityState}:
            raise ValueError("Unknown activity state")
        integer(current["revision"], 0, 2**63 - 1)
        if any(type(current[k]) is not bool for k in ("planned_end_notified", "supports_pause")):
            raise ValueError("Activity flags require bool")
        if current["decision_id"] == value["decision_id"]:
            raise ValueError("A decision cannot refer to itself")
    return value


def observation(goal, record, profile):
    fields(record, "record_id kind content source_kind source occurred_at sequence stored_at")
    if record["record_id"] != goal["record_id"]:
        raise ValueError("Memory returned a different record")
    for key in ("record_id", "kind", "source_kind"):
        identifier(record[key], 4096)
    for key in ("content", "source"):
        text = record[key]
        if type(text) is not str or not text.strip() or "\x00" in text:
            raise ValueError("Invalid Memory text")
        text.encode("utf-8")
    if record["source_kind"] not in SOURCES or record["kind"] not in ("experience", "knowledge"):
        raise ValueError("Unknown Memory kind or source kind")
    timestamp(record["occurred_at"]); timestamp(record["stored_at"])
    integer(record["sequence"], 1, 2**63 - 1)
    if len(dump({k:v for k,v in record.items() if k not in ("sequence", "stored_at")}).encode("ascii")) > 4096:
        raise ValueError("Memory record exceeds records/1 limit")
    if goal["token"] not in "".join(record["content"].split()):
        raise ValueError("Goal token is absent from its Memory evidence")
    if type(profile) is not dict or profile.get("token") != goal["token"]:
        raise ValueError("Cognition returned a different token")
    documents = profile.get("documents")
    integer(documents, 0, 256)
    sources = profile.get("source_counts")
    expected = {record["source_kind"]: documents} if documents else {}
    if (type(sources) is not dict or any(type(n) is not int for n in sources.values()) or sources != expected
            or type(profile.get("known")) is not bool or profile["known"] != bool(documents)):
        raise ValueError("Cognition returned inconsistent source counts")
    return {"goal_id":goal["goal_id"], "record_id":goal["record_id"], "token":goal["token"],
            "fingerprint":hashlib.sha256(dump(record).encode("ascii")).hexdigest(),
            "source_kind":record["source_kind"], "documents":documents}


def validate_evidence(value, goals):
    if type(value) is not list or len(value) != len(goals):
        raise ValueError("Missing decision evidence")
    for item, goal in zip(value, goals):
        fields(item, "goal_id record_id token fingerprint source_kind documents")
        if any(item[k] != goal[k] for k in ("goal_id", "record_id", "token")):
            raise ValueError("Evidence does not match goal")
        if (type(item["fingerprint"]) is not str or not re.fullmatch("[0-9a-f]{64}", item["fingerprint"])
                or type(item["source_kind"]) is not str or item["source_kind"] not in SOURCES):
            raise ValueError("Invalid evidence fingerprint/source")
        integer(item["documents"], 0, 256)


def decide(value, evidence, templates, module_id, previous=None):
    validate_evidence(evidence, value["goals"])
    current = value["current"]
    if current is not None and (previous is None or previous["plan"] is None):
        raise ValueError("Current decision must refer to a saved plan")
    old = previous["plan"] if current is not None else None
    candidates = []
    state = value["state"]
    for template in templates:
        if template["template_id"] not in value["available"]:
            continue
        motive = template["motive"]
        if motive in ("rest", "social"):
            score = max(state["sleep_pressure"], state["cognitive_load"]) if motive == "rest" else state["social_need"]
            candidates.append(dict(template_id=template["template_id"], goal_id=None, motive=motive, score=score))
        else:
            for goal, item in zip(value["goals"], evidence):
                missing = max(0, goal["target_documents"]-item["documents"])*1000//goal["target_documents"]
                score = goal["importance"] * (missing if motive == "explore" else 1000-missing)//1000
                candidates.append(dict(template_id=template["template_id"], goal_id=goal["goal_id"], motive=motive, score=score))
    def order(candidate):
        retained = old is not None and all(candidate[k] == old[k] for k in ("template_id", "goal_id"))
        return (-candidate["score"], not retained, candidate["template_id"], candidate["goal_id"] or "")
    candidates.sort(key=order)
    selected = candidates[0] if candidates and candidates[0]["score"] > 0 else None
    plan = None
    if selected:
        template = next(t for t in templates if t["template_id"] == selected["template_id"])
        goal = next((g for g in value["goals"] if g["goal_id"] == selected["goal_id"]), None)
        duration = template["min_seconds"] + (template["max_seconds"]-template["min_seconds"])*selected["score"]//1000
        delay = template["delay_seconds"]*(1000-selected["score"])//1000
        start = timestamp(value["now"]) + timedelta(seconds=delay) if delay else None
        activity = ActivityRequest(ActivityKey(module_id, "agency-"+hashlib.sha256(value["decision_id"].encode()).hexdigest()),
                                   template["content"], start, timedelta(seconds=duration),
                                   {"configured":template["parameters"], "goal":None if goal is None else
                                    {k:goal[k] for k in ("goal_id", "record_id", "token")}}, selected["score"])
        plan = dict(activity.as_dict(), template_id=template["template_id"], goal_id=selected["goal_id"],
                    executor_module_id=template["executor_module_id"], executor_id=template["executor_id"])
    target = None
    directive = "start" if plan else "idle"
    if current and not ActivityState(current["state"]).terminal:
        target = {"requester_id":old["requester_id"], "activity_id":old["activity_id"], "expected_revision":current["revision"]}
        if current["state"] in ("starting", "pausing", "resume_pending", "finishing"):
            directive = "wait"
        elif plan is None:
            directive = "finish"
        elif all(plan[k] == old[k] for k in ("template_id", "goal_id", "parameters", "executor_module_id", "executor_id", "content")):
            plan["activity_id"] = old["activity_id"]
            if (current["state"] != "pending" or
                    all(plan[k] == old[k] for k in ("duration_us", "priority"))):
                # Re-observing unchanged motivation is not a request to postpone
                # an already scheduled start by another relative delay.
                plan["start_at"] = old["start_at"]
            if current["state"] == "paused":
                # Resume the existing continuation first; a later running-state
                # decision can change its duration/priority with a fresh revision.
                plan = snapshot(old, 16384)
            elif current["planned_end_notified"]:
                plan["duration_us"] += old["duration_us"]
            directive = "resume" if current["state"] == "paused" else (
                "change" if any(plan[k] != old[k] for k in ("start_at", "duration_us", "priority")) else "continue")
        else:
            directive = "pause" if current["state"] == "running" and current["supports_pause"] else "finish"
    result = dict(decision_id=value["decision_id"], policy=POLICY, requested_at=value["now"], directive=directive,
                  target=target, plan=plan, selected=selected, candidates=candidates, evidence=evidence, state=state)
    # Fail before saving if the receipt cannot fit its declared transport budget.
    return snapshot(result, 49152)
