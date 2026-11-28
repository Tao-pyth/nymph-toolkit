"""Prepare explicit Memory candidates using a configured preparation method."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import math

from nymph_toolkit.contracts import ModuleContextProtocol, RuntimeService
from nymph_toolkit.contracts._memory_record import KINDS, SOURCES, RecordTooLarge, canonical, identifier, timestamp
from nymph_toolkit.contracts.input_candidate import INPUT_CANDIDATE_CONTRACT

from .._interaction import InputAdapter, snapshot

__all__ = ["factory"]

_INPUT_FIELDS = ("input_type", "content", "source", "acquisition")
_LABELS = {"kind": KINDS, "source_kind": SOURCES}
_INPUT_TYPES = ("web", "document", "conversation")


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty text")
    value.encode("utf-8")


def _labels(value):
    if type(value) is not dict or value.keys() - _LABELS.keys():
        raise ValueError("Unknown record label")
    for name, label in value.items():
        if label not in _LABELS[name]:
            raise ValueError("Invalid record label")


class _LocalMockAPI:
    def __init__(self, response):
        self._response = response

    async def __call__(self, *, content, operation):
        # This fixture has no transport, credentials or external destination.
        return snapshot(self._response)


class _Preparation(InputAdapter):
    def __init__(self, context, config, *, mock_api=None):
        config = snapshot(config)
        if type(config) is not dict:
            raise ValueError("Input preparation settings must be an object")
        self.method = config.get("method")
        version = config.get("configuration_version")
        if type(version) is not int or version < 1:
            raise ValueError("configuration_version must be a positive integer")
        self.metadata = {"method_id": self.method, "configuration_version": version}
        shared = {"method", "configuration_version"}
        if self.method == "defaults":
            if set(config) != shared | {"defaults"}:
                raise ValueError("defaults requires per-input-type labels")
            self.defaults = config["defaults"]
            if type(self.defaults) is not dict or self.defaults.keys() - set(_INPUT_TYPES):
                raise ValueError("Unknown input type in defaults")
            for labels in self.defaults.values():
                _labels(labels)
        elif self.method == "mock_ai":
            if set(config) != shared | {"model_id", "operation", "timeout", "response"}:
                raise ValueError("mock_ai requires model_id, operation, timeout and response")
            _text(config["model_id"])
            if config["operation"] not in ("summarize", "extract"):
                raise ValueError("Unknown mock AI operation")
            timeout = config["timeout"]
            if type(timeout) not in (int, float) or not 0 < timeout <= 60 or not math.isfinite(timeout):
                raise ValueError("timeout must be in (0, 60] seconds")
            self.metadata["model_id"] = config["model_id"]
            self.operation, self.timeout = config["operation"], timeout
            self.mock_api = _LocalMockAPI(config["response"]) if mock_api is None else mock_api
        else:
            raise ValueError("method must be defaults or mock_ai")
        super().__init__(context, INPUT_CANDIDATE_CONTRACT, {"prepare": self.prepare}, {})

    def _failed(self, stage, code):
        return dict(self.metadata, status="failed", stage=stage, code=code)

    def _needs_input(self, missing, reason, **details):
        return dict(self.metadata, status="needs_input", missing=missing, reason=reason, **details)

    async def prepare(self, request):
        try:
            request = snapshot(request)
            if type(request) is not dict or request.keys() - {"record_id", "input", "fields", "permission"}:
                raise ValueError("Invalid request")
            acquired = request.get("input", {})
            fields = request.get("fields", {})
            if type(acquired) is not dict or acquired.keys() - set(_INPUT_FIELDS):
                raise ValueError("Invalid acquired input")
            if type(fields) is not dict or fields.keys() - {"kind", "source_kind", "occurred_at"}:
                raise ValueError("Invalid explicit fields")
            if "record_id" in request:
                identifier(request["record_id"])
            for name, value in acquired.items():
                _text(value)
                if name == "input_type" and value not in _INPUT_TYPES:
                    raise ValueError("Unknown input type")
            _labels({key: value for key, value in fields.items() if key in _LABELS})
            if "occurred_at" in fields:
                _text(fields["occurred_at"])
                timestamp(fields["occurred_at"])
        except (ValueError, TypeError, OverflowError, RecursionError):
            return self._failed("request", "invalid_input")
        missing = [key for key in ("record_id",) if key not in request]
        missing.extend("input." + key for key in _INPUT_FIELDS if key not in acquired)
        if "occurred_at" not in fields:
            missing.append("occurred_at")
        if missing:
            return self._needs_input(missing, "required_fields")
        return await self.submit(self._prepare, request, acquired, fields)

    async def _prepare(self, request, acquired, explicit):
        record = {"record_id": request["record_id"], "source": acquired["source"],
                  "content": acquired["content"], **explicit}
        provenance = {"record_id": "explicit", "source": "input", "content": "input"}
        provenance.update(dict.fromkeys(explicit, "explicit"))
        if self.method == "defaults":
            for key, value in self.defaults.get(acquired["input_type"], {}).items():
                if key not in record:
                    record[key] = value
                    provenance[key] = "default"
        else:
            permission = {"destination": "mock", "fields": ["content"]}
            if request.get("permission") != permission:
                return self._failed("permission", "send_not_permitted")
            try:
                async with asyncio.timeout(self.timeout):
                    response = snapshot(await self.mock_api(content=acquired["content"], operation=self.operation))
                if type(response) is not dict or response.keys() - {"content", *_LABELS}:
                    raise ValueError("Invalid mock API response")
                _text(response.get("content"))
                labels = {name: value for name, value in response.items() if name != "content"}
                _labels(labels)
            except Exception:
                return self._failed("preparation", "external_processing_failed")
            missing = [name for name in _LABELS if name not in record]
            if missing:
                proposals = {name: labels[name] for name in missing if name in labels}
                return self._needs_input(missing, "explicit_labels_required", proposals=proposals)
            record["content"] = response["content"]
            provenance["content"] = "ai"
        missing = [name for name in _LABELS if name not in record]
        if missing:
            return self._needs_input(missing, "required_fields")
        try:
            canonical(record)
        except RecordTooLarge:
            return self._failed("validation", "too_large")
        except (ValueError, OverflowError):
            return self._failed("validation", "invalid_input")
        return dict(self.metadata, status="ready", record=record,
                    provenance=provenance, acquisition=acquired["acquisition"])


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Preparation(context, config)
