"""Parent-side observation and the separately owned loopback diagnostic process."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections import Counter, deque
from dataclasses import dataclass
from functools import partial
import json
import math
import subprocess
import sys
from uuid import uuid4
from weakref import WeakValueDictionary

from nymph_toolkit.contracts import (
    ContractKey, ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, Placement,
    OutcomeUnknown, Usage,
)
from nymph_toolkit.contracts.diagnostics import report_contract, validate_report

_RECEIVER = "ntk-diagnostics"
_SESSIONS = WeakValueDictionary()
_EVENT_LIMIT = 200
_ACTIVITY_FIELDS = ("state", "planned_start_at", "planned_end_at", "started_at", "ended_at", "planned_end_notified")


@dataclass(frozen=True)
class ConsoleQuery:
    """Declare an already public, side-effect-free query and its display fields."""

    label: str
    provider_id: str
    contract: ContractKey
    operation: str
    fields: tuple[str, ...]
    inputs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        names = [name for name, _ in self.inputs]
        if (not self.label.strip() or not self.provider_id or not self.operation
                or not self.fields or len(names) != len(set(names))
                or any(kind not in ("string", "integer", "number", "boolean") for _, kind in self.inputs)):
            raise ValueError("Invalid diagnostics console declaration")


class _Receiver:
    def __init__(self, context, config):
        self.session = _SESSIONS[config["run_id"]]
        self.core = context.core
        self.contracts = tuple(report_contract(slot) for slot in self.session.slots)
        for slot, contract in zip(self.session.slots, self.contracts, strict=True):
            context.provide(contract.key, {"publish": partial(self.publish, slot)})

    async def publish(self, slot, report):
        return self.session.accept_report(slot, report)

    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 1)
        await self.core.publish_usage(usage, contracts={c.key: usage for c in self.contracts})

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass


def receiver_factory(context, config):
    return _Receiver(context, config)


def _project(data, keys):
    return {key: data[key] for key in keys if key in data}


def _scalar(value, kind=None):
    if kind == "string":
        return type(value) is str and len(value) <= 1024
    if kind == "integer":
        return type(value) is int and abs(value) <= 2**53 - 1
    if kind == "number":
        return _scalar(value, "integer") or (type(value) is float and math.isfinite(value))
    if kind == "boolean":
        return type(value) is bool
    return value is None or any(_scalar(value, name) for name in ("string", "number", "boolean"))


class DiagnosticSession:
    """Attach before Runtime start. Start and close the viewer independently."""

    def __init__(self, group, runtime, *, slots=None, queries=None):
        self.group, self.runtime = group, runtime
        self.store = group.connections.store
        if self.store._diagnostic_observer is not None:
            raise ValueError("A diagnostic session is already attached")
        self.slots = dict(slots or {})
        if len(self.slots) > 64 or len(set(self.slots.values())) != len(self.slots):
            raise ValueError("At most 64 distinct modules can declare a report")
        self.queries = dict(queries or {})
        if any(not isinstance(item, ConsoleQuery) for item in self.queries.values()):
            raise ValueError("Diagnostics console queries must be ConsoleQuery declarations")
        # A fixed Core connection key cannot be bound to two providers.
        bindings = {}
        for query in self.queries.values():
            if bindings.setdefault(query.contract, query.provider_id) != query.provider_id:
                raise ValueError("A diagnostic console contract must use one fixed provider")
        self.run_id = uuid4().hex
        self.url = None
        self._process = self._task = self._commands = None
        self._io_lock = asyncio.Lock()
        self._reports, self._changes = {}, {}
        self._events = deque(maxlen=_EVENT_LIMIT)
        self._terminal = {}
        self._published, self.report_count, self.peak_reports = set(), 0, 0
        self._bound = set()
        self._checking = Counter()
        self._closing = False
        contracts = tuple(report_contract(slot) for slot in self.slots)
        group.register_module(ModuleSpec(_RECEIVER, ModuleKind.ADAPTER, ()),
                              ModuleAdvertisement(_RECEIVER, "1.12.0", contracts),
                              "nymph_toolkit.diagnostics._session:receiver_factory",
                              {"run_id": self.run_id}, Placement.LOCAL)
        _SESSIONS[self.run_id] = self
        self.store._diagnostic_observer = self._observe

    def report_settings(self, slot):
        """Return JSON settings to pass into the corresponding adapter at setup."""
        return {"slot": slot, "module_id": self.slots[slot], "run_id": self.run_id,
                "receiver_id": _RECEIVER}

    def _observe(self, event):
        kind, data = event["kind"], event["data"]
        value = label = key = None
        if kind == "hybrid_process" and data["module_id"] != _RECEIVER:
            label, key = "modules", data["module_id"]
            value = _project(data, ("state", "pid", "returncode", "cleanup_confirmed"))
            value["placement"] = self.group.process(key).placement.value
            if (data["state"] in ("failed", "forcing")
                    or (data["state"] == "stopped" and data["cleanup_confirmed"] is False)):
                self._terminal[key] = dict(value)
        elif kind == "usage" and data["module_id"] != _RECEIVER:
            label, key = "usage", data["module_id"]
            value = _project(data["module"], ("state", "accepting", "active", "capacity"))
        elif kind in ("binding_created", "startup_binding"):
            label = "connections"
            key = self._binding_key(data)
            value = _project(data, ("requester_id", "provider_id", "contract_id", "version"))
            value["state"] = "invalid" if data.get("valid") is False else "ready"
            self._published.add(key)
        elif kind in ("health_requested", "health_completed", "link_error"):
            label = "connections"
            values = {"link_error": [data], "health_requested": data.get("bindings", ()),
                      "health_completed": data.get("connections", ())}[kind]
            for item in values:
                binding = self._binding_key(item)
                if binding not in self._published:
                    continue
                if kind == "health_requested":
                    self._checking[binding] += 1
                elif kind == "health_completed" and self._checking[binding] > 0:
                    self._checking[binding] -= 1
                state = "ready" if item.get("healthy") else "invalid"
                if self._checking[binding]:
                    state = "checking"
                else:
                    self._checking.pop(binding, None)
                self._change(label, binding, {"state": state})
            if not values:
                self._events.append({"sequence": event["sequence"], "at": event["at"],
                                     "kind": kind, "subject": "connections"})
        elif kind.startswith(("activity_v06_", "activity_v07_")) and "request" in data:
            label = "activities"
            request = data["request"]
            key = "/".join(str(request.get(part, "")) for part in ("requester_id", "activity_id"))
            value = _project(data, _ACTIVITY_FIELDS)
        if value is not None:
            self._change(label, key, value)
        if label is not None and kind != "usage":
            self._events.append({"sequence": event["sequence"], "at": event["at"],
                                 "kind": kind, "subject": key or label})

    @staticmethod
    def _binding_key(data):
        return "/".join(str(data.get(key, "")) for key in ("requester_id", "contract_id", "version"))

    def _change(self, group, key, value):
        values = self._changes.setdefault(group, {})
        values.setdefault(key, {}).update(value)
        if group == "activities" and len(values) > _EVENT_LIMIT:
            del values[next(iter(values))]

    def accept_report(self, slot, report):
        if self.url is None or slot not in self.slots or self._closing:
            return {"status": "not_available"}
        try:
            value = validate_report(report)
            if value["module_id"] != self.slots[slot]:
                raise ValueError("Incorrect diagnostics module")
        except (ValueError, TypeError, RecursionError, OverflowError):
            return {"status": "invalid_report"}
        current = self._reports.get(slot)
        if value["run_id"] != self.run_id or (current and value["sequence"] <= current["sequence"]):
            return {"status": "stale_report"}
        self._reports[slot] = value
        self._changes.setdefault("reports", {})[slot] = value
        self.report_count += 1
        self.peak_reports = max(self.peak_reports, len(self._changes["reports"]))
        return {"status": "accepted", "sequence": value["sequence"]}

    async def start(self):
        if self._process is not None or self._closing:
            raise RuntimeError("Diagnostic session may start once")
        try:
            self._process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "nymph_toolkit.diagnostics._viewer",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
            async with asyncio.timeout(5):
                ready = json.loads(await self._process.stdout.readline())
            self.url = f"http://127.0.0.1:{int(ready['port'])}/"
            self._task = asyncio.create_task(self._publish(), name="ntk-diagnostics-heartbeat")
            self._commands = asyncio.create_task(self._serve_queries(), name="ntk-diagnostics-console")
            return self.url
        except (OSError, ValueError, RuntimeError, KeyError, NotImplementedError):
            await self.close()
            return None
        except asyncio.CancelledError:
            await self.close()
            raise

    async def _send(self, value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode() + b"\n"
        async with self._io_lock, asyncio.timeout(1):
            if self._process.stdin.is_closing():
                raise BrokenPipeError
            self._process.stdin.write(raw)
            await self._process.stdin.drain()

    async def _publish(self):
        try:
            await self._send({"type": "setup", "run_id": self.run_id, "queries": {
                name: {"label": query.label, "inputs": query.inputs} for name, query in self.queries.items()
            }})
            while True:
                changes, self._changes = self._changes, {}
                events = list(self._events)
                self._events.clear()
                await self._send({"type": "update", "state": self.runtime.state.value,
                                  "changes": changes, "events": events, "terminal": self._terminal})
                await asyncio.sleep(1)
        except (OSError, TimeoutError, ValueError, RuntimeError):
            self.url = None
            self._detach()

    async def _serve_queries(self):
        try:
            while raw := await self._process.stdout.readline():
                command = json.loads(raw)
                result = await self._query(command.get("operation"), command.get("arguments"))
                await self._send({"type": "reply", "id": command["id"], "result": result})
        except (OSError, TimeoutError, ValueError, RuntimeError, KeyError):
            pass
        finally:
            self.url = None
            self._detach()

    async def _query(self, operation, arguments):
        query = self.queries.get(operation) if type(operation) is str else None
        fields = {} if query is None else dict(query.inputs)
        if (query is None or type(arguments) is not dict or arguments.keys() != fields.keys()
                or any(not _scalar(value, fields[name]) for name, value in arguments.items())):
            return {"status": "invalid"}
        if self.runtime.state.value != "running":
            return {"status": "not_available"}
        try:
            core = self.group.client(_RECEIVER)
            if query.contract not in self._bound:
                await core.bind(query.contract, query.provider_id, timeout=1)
                self._bound.add(query.contract)
            result = await core.invoke(query.contract, query.operation, timeout=1, **arguments)
        except (OutcomeUnknown, TimeoutError):
            return {"status": "outcome_unknown"}
        except Exception:
            return {"status": "business_error"}
        if type(result) is not dict:
            return {"status": "business_error"}
        return {"status": "completed", "values": {name: result[name] for name in query.fields
                                                  if name in result and _scalar(result[name])}}

    def _detach(self):
        if self.store._diagnostic_observer == self._observe:
            self.store._diagnostic_observer = None

    async def close(self):
        self._closing = True
        self.url = None
        self._detach()
        tasks = [task for task in (self._task, self._commands) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._process is not None and self._process.returncode is None:
            self._process.stdin.close()
            try:
                async with asyncio.timeout(3):
                    await self._process.wait()
            except TimeoutError:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
                await self._process.wait()
