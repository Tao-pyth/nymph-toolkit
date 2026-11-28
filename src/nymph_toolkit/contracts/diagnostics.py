"""Version 1 diagnostics reports and Core connection declarations (ADR 0039)."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
import json
import math
import re

from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

__all__ = ["report_contract", "validate_report"]

_MAX_INT = 2**53 - 1
_SLOT = re.compile(r"[a-z][a-z0-9_-]{0,31}", re.ASCII)
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}", re.ASCII)
_RUN = re.compile(r"[a-f0-9]{32}", re.ASCII)
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z", re.ASCII)


def report_contract(slot: str) -> ContractSpec:
    if type(slot) is not str or not _SLOT.fullmatch(slot):
        raise ValueError("Invalid diagnostics slot")
    return ContractSpec(ContractKey("ntk.diagnostics.report." + slot, "1"),
                        (OperationSpec("publish", OperationMode.ASYNC),))


def _object(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("Invalid diagnostics object")


def _array(value, minimum, maximum):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError("Invalid diagnostics array")
    return value


def _text(value, maximum=80):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError("Invalid diagnostics text")


def _integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= _MAX_INT:
        raise ValueError("Invalid diagnostics integer")


def _number(value):
    if type(value) is int and -_MAX_INT <= value <= _MAX_INT:
        return
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("Invalid diagnostics number")


def _timestamp(value):
    if type(value) is not str or not _UTC.fullmatch(value):
        raise ValueError("Invalid diagnostics timestamp")
    datetime.fromisoformat(value)


def _identifier(value, used):
    if type(value) is not str or not _ID.fullmatch(value) or value in used:
        raise ValueError("Invalid or duplicate diagnostics ID")
    used.add(value)


def _choice(value, options):
    if value not in options:
        raise ValueError("Invalid diagnostics category")


def _output(value, used):
    _object(value, ("id", "label", "kind", "observed_at", "content"), ("source", "expires_at"))
    _identifier(value["id"], used)
    _text(value["label"])
    _timestamp(value["observed_at"])
    if ("source" in value) != ("expires_at" in value):
        raise ValueError("External diagnostic output requires source and expiry together")
    if "source" in value:
        _text(value["source"])
        _timestamp(value["expires_at"])
        if value["expires_at"] <= value["observed_at"]:
            raise ValueError("Expiry must follow observation")
    kind, content = value["kind"], value["content"]
    _choice(kind, ("text", "items", "series"))
    if kind == "text":
        _text(content, 1024)
    elif kind == "items":
        for item in _array(content, 1, 32):
            _object(item, ("label", "value"), ("unit",))
            _text(item["label"])
            if "unit" in item:
                _text(item["unit"])
            if type(item["value"]) is str:
                _text(item["value"], 1024)
            elif type(item["value"]) is not bool:
                _number(item["value"])
    else:
        _object(content, ("unit", "points"))
        _text(content["unit"])
        previous = ""
        for point in _array(content["points"], 1, 120):
            _object(point, ("at", "value"))
            _timestamp(point["at"])
            _number(point["value"])
            if point["at"] <= previous:
                raise ValueError("Series must be strictly ordered by time")
            previous = point["at"]


def validate_report(report: dict) -> dict:
    """Validate a report and return an independent JSON-compatible snapshot."""
    _object(report, ("version", "module_id", "run_id", "sequence", "reported_at", "resources", "outputs"),
            ("condition", "processing"))
    if type(report["version"]) is not int or report["version"] != 1:
        raise ValueError("Unsupported diagnostics version")
    _text(report["module_id"], 256)
    if type(report["run_id"]) is not str or not _RUN.fullmatch(report["run_id"]):
        raise ValueError("Invalid diagnostics run ID")
    _integer(report["sequence"], 1)
    _timestamp(report["reported_at"])
    if "condition" in report:
        condition = report["condition"]
        _object(condition, ("level", "label"))
        _choice(condition["level"], ("info", "warning", "error"))
        _text(condition["label"])
    if "processing" in report:
        processing = report["processing"]
        _object(processing, ("accepting", "active"), ("capacity",))
        if type(processing["accepting"]) is not bool:
            raise ValueError("Accepting must be a boolean")
        _integer(processing["active"])
        if "capacity" in processing:
            _integer(processing["capacity"])
    used = set()
    for resource in _array(report["resources"], 0, 16):
        _object(resource, ("id", "label", "kind", "unit", "used"), ("limit",))
        _identifier(resource["id"], used)
        _text(resource["label"])
        _choice(resource["kind"], ("disk", "memory"))
        _choice(resource["unit"], ("bytes", "items"))
        _integer(resource["used"])
        if "limit" in resource:
            _integer(resource["limit"], 1)
    used.clear()
    for output in _array(report["outputs"], 0, 16):
        _output(output, used)
    raw = json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > 16384:
        raise ValueError("Diagnostics report exceeds 16384 UTF-8 bytes")
    return json.loads(raw)
