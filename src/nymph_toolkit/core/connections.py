"""Core-managed binding with cached direct calls and cooperative error handling."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import inspect
import math
import threading
from typing import TYPE_CHECKING

from nymph_toolkit.contracts import (
    BindingHealth, BindingKey, BindingRecord, BindingState, Candidate, ConnectionConflictError,
    ConnectionNotReadyError, ConnectionNotice, ConnectionSnapshot,
    ConnectionsStateError, ConnectionUnavailableError, ContractDeclarationError,
    ContractKey, ContractSpec, HealthResult, LinkFailure, ModuleAdvertisement,
    ModuleExecutionState, ModuleHealth, NoticeKind, OperatingState, OperationMode,
    PreparationTimeoutError, RuntimeState, UnknownConnectionError,
    UnknownModuleError, Usage,
)

if TYPE_CHECKING:
    from .storage import FileStore


@dataclass
class _Module:
    advertisement: ModuleAdvertisement
    generation: int
    handlers: dict[ContractKey, dict[str, Callable]]
    usage: Usage = field(default_factory=Usage)
    contracts: dict[ContractKey, Usage] = field(default_factory=dict)
    execution: ModuleExecutionState = ModuleExecutionState.RUNNING
    interruption_id: int = 0
    causes: set[BindingKey] = field(default_factory=set)
    notices: asyncio.Queue = field(default_factory=asyncio.Queue)


@dataclass
class _Binding:
    record: BindingRecord
    requester: _Module
    provider: _Module
    healthy: bool = True
    reason: str = ""
    checking: int = 0

    def snapshot(self) -> ConnectionSnapshot:
        state = BindingState.CHECKING if self.checking else (
            BindingState.VALID if self.healthy else BindingState.INVALID
        )
        return ConnectionSnapshot(self.record.key, self.record.provider_id, state, self.reason)


@dataclass
class _HealthRequest:
    request_id: int
    modules: tuple[str, ...]
    bindings: tuple[BindingKey, ...]
    future: asyncio.Future


def _key_data(key: BindingKey) -> dict:
    return {"requester_id": key.requester_id, "contract_id": key.contract.contract_id,
            "version": key.contract.version}


def _usage_data(usage: Usage) -> dict:
    return {"state": usage.state.value, "accepting": usage.accepting,
            "active": usage.active, "capacity": usage.capacity}


class PreparedConnection:
    """A direct endpoint reference; state gates do not rediscover or reauthorize it."""

    def __init__(self, owner: "Connections", binding: _Binding) -> None:
        self._owner = owner
        self._binding = binding
        self._handlers = binding.provider.handlers[binding.record.key.contract]
        self._modes = {op.name: op.mode for op in owner._specs[binding.record.key.contract].operations}

    @property
    def snapshot(self) -> ConnectionSnapshot:
        self._owner._check_context()
        return self._binding.snapshot()

    def _handler(self, operation: str, mode: OperationMode) -> Callable:
        self._owner._check_running()
        if self._modes.get(operation) != mode:
            raise ContractDeclarationError(f"Operation {operation!r} is not declared as {mode}")
        if not self._owner._is_ready(self._binding):
            raise ConnectionNotReadyError("Connection changed state; prepare again before use")
        return self._handlers[operation]

    def _failed(self, exception: Exception) -> LinkFailure:
        if self._owner.state != RuntimeState.RUNNING:
            return LinkFailure(self._binding.record.key, exception, None)
        notice_id = self._owner.report_link_error(self._binding.record.key, exception)
        return LinkFailure(self._binding.record.key, exception, notice_id)

    def call(self, operation: str, *args, **kwargs):
        handler = self._handler(operation, OperationMode.SYNC)
        try:
            result = handler(*args, **kwargs)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise ContractDeclarationError("A sync operation returned an awaitable")
            return result
        except asyncio.CancelledError as exc:
            error = ContractDeclarationError("A sync provider raised cancellation")
            error.__cause__ = exc
            return self._failed(error)
        except Exception as exc:
            return self._failed(exc)

    async def acall(self, operation: str, *args, **kwargs):
        handler = self._handler(operation, OperationMode.ASYNC)
        try:
            result = handler(*args, **kwargs)
            if not inspect.isawaitable(result):
                raise ContractDeclarationError("An async operation did not return an awaitable")
            return await result
        except asyncio.CancelledError:
            # Caller cancellation is not evidence that a provider is unhealthy.
            if asyncio.current_task().cancelling():
                raise
            return self._failed(ContractDeclarationError("Provider cancelled without caller cancellation"))
        except Exception as exc:
            return self._failed(exc)


class Connections:
    """One-loop, one-shot connection manager and RuntimeService.

    A catalog supplies get/entries (Registry or ModuleGroup). Providers retain
    capacity admission and business semantics; this class manages their links.
    """

    def __init__(self, catalog, store: "FileStore") -> None:
        self.catalog = catalog
        self.store = store
        self._thread = threading.current_thread()
        self._loop = None
        self._state = RuntimeState.NEW
        self._run_entered = False
        self._modules: dict[str, _Module] = {}
        self._specs: dict[ContractKey, ContractSpec] = {}
        self._bindings: dict[BindingKey, _Binding] = {}
        self._saved: tuple[BindingRecord, ...] = ()
        self._bind_lock = asyncio.Lock()
        self._changed = asyncio.Event()
        self._health_requests: asyncio.Queue[_HealthRequest] = asyncio.Queue()
        self._notice_id = 0
        self._request_id = 0
        self._commits: set[asyncio.Task] = set()

    @property
    def state(self) -> RuntimeState:
        return self._state

    def _check_context(self) -> None:
        if threading.current_thread() is not self._thread:
            raise ConnectionsStateError("Connections belongs to its creating thread")
        if self._loop is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not self._loop:
                raise ConnectionsStateError("Connections belongs to its original event loop")

    def _check_running(self) -> None:
        self._check_context()
        if self._state != RuntimeState.RUNNING:
            raise ConnectionsStateError(f"Connections is {self._state}")
        if self.store.failure is not None:
            raise self.store.failure

    def _pulse(self) -> None:
        previous = self._changed
        self._changed = asyncio.Event()
        previous.set()

    def _module(self, module_id: str) -> _Module:
        try:
            return self._modules[module_id]
        except KeyError:
            raise UnknownModuleError(module_id) from None

    def declare(self, advertisement: ModuleAdvertisement, handlers: Mapping | None = None) -> None:
        self._check_context()
        if self._state != RuntimeState.NEW:
            raise ConnectionsStateError("Declarations are frozen when start begins")
        if not isinstance(advertisement, ModuleAdvertisement):
            raise TypeError("advertisement must be a ModuleAdvertisement")
        registration = self.catalog.get(advertisement.module_id)
        if advertisement.module_id in self._modules:
            raise ContractDeclarationError("Module was already declared")
        provided = {} if handlers is None else dict(handlers)
        contracts = {spec.key: spec for spec in advertisement.contracts}
        if provided.keys() != contracts.keys():
            raise ContractDeclarationError("Handlers must match declared contract keys")
        copied = {}
        for key, spec in contracts.items():
            if key in self._specs and self._specs[key] != spec:
                raise ContractDeclarationError("Conflicting definitions for one contract ID/version")
            operations = dict(provided[key])
            if operations.keys() != {op.name for op in spec.operations} or not all(map(callable, operations.values())):
                raise ContractDeclarationError("Handlers must match declared operation names")
            copied[key] = operations
        self._modules[advertisement.module_id] = _Module(
            advertisement, registration.generation, copied,
            contracts={key: Usage() for key in contracts},
        )
        self._specs.update(contracts)

    def publish_usage(self, module_id: str, usage: Usage, *, contracts: Mapping[ContractKey, Usage] | None = None) -> None:
        self._check_context()
        if self._state in (RuntimeState.STOPPED, RuntimeState.FAILED):
            raise ConnectionsStateError("Connections is closed")
        module = self._module(module_id)
        if not isinstance(usage, Usage):
            raise TypeError("usage must be Usage")
        updates = {} if contracts is None else dict(contracts)
        if not updates.keys() <= module.contracts.keys() or not all(isinstance(v, Usage) for v in updates.values()):
            raise ContractDeclarationError("Usage must reference declared contracts")
        if self.catalog.get(module_id).generation != module.generation:
            raise ContractDeclarationError("Usage belongs to a stale module registration")
        if module.usage == usage and all(module.contracts[k] == v for k, v in updates.items()):
            return
        self.store.append("usage", {"module_id": module_id, "module": _usage_data(usage),
                                   "contracts": [dict(contract_id=k.contract_id, version=k.version, **_usage_data(v))
                                                 for k, v in sorted(updates.items())]})
        module.usage = usage
        module.contracts.update(updates)
        self._pulse()

    def candidates(self, contract: ContractKey) -> tuple[Candidate, ...]:
        self._check_context()
        if not isinstance(contract, ContractKey):
            raise TypeError("contract must be ContractKey")
        candidates = []
        for entry in self.catalog.entries():
            module = self._modules.get(entry.spec.module_id)
            if module is not None and entry.generation == module.generation and contract in module.contracts:
                candidates.append(Candidate(entry, module.advertisement, contract, module.usage, module.contracts[contract]))
        return tuple(sorted(candidates, key=lambda c: c.advertisement.module_id))

    def _module_health(self, module_id: str) -> ModuleHealth:
        module = self._modules.get(module_id)
        if module is None:
            return ModuleHealth(module_id, False, "module not declared")
        try:
            entry = self.catalog.get(module_id)
        except UnknownModuleError:
            return ModuleHealth(module_id, False, "module not registered")
        if entry.generation != module.generation:
            return ModuleHealth(module_id, False, "registration generation changed")
        if module.usage.state != OperatingState.RUNNING:
            return ModuleHealth(module_id, False, f"module is {module.usage.state}")
        return ModuleHealth(module_id, True)

    def _binding_health(self, binding: _Binding) -> tuple[bool, str]:
        for module_id in (binding.record.key.requester_id, binding.record.provider_id):
            health = self._module_health(module_id)
            if not health.healthy:
                return False, f"{module_id}: {health.reason}"
        usage = binding.provider.contracts.get(binding.record.key.contract)
        if usage is None:
            return False, "provider does not declare this contract"
        if usage.state != OperatingState.RUNNING:
            return False, f"provider contract is {usage.state}"
        return True, ""

    def _make_binding(self, record: BindingRecord) -> _Binding:
        requester = self._module(record.key.requester_id)
        provider = self._module(record.provider_id)
        if record.key.contract not in provider.contracts:
            raise ContractDeclarationError("Provider does not declare the requested contract")
        return _Binding(record, requester, provider)

    async def start(self, *, defer_activation: bool = False) -> None:
        self._check_context()
        if self._state != RuntimeState.NEW:
            raise ConnectionsStateError("Connections cannot be restarted")
        self._loop = asyncio.get_running_loop()
        self._state = RuntimeState.STARTING
        try:
            await self.store.start()
            self._saved = await self.store.load_bindings()
            if not defer_activation:
                await self.activate()
        except BaseException:
            self._state = RuntimeState.FAILED
            self._pulse()
            raise

    async def activate(self) -> None:
        self._check_context()
        if self._state != RuntimeState.STARTING:
            raise ConnectionsStateError("Activation requires initialized storage and module state")
        restored = {}
        for record in self._saved:
            try:
                binding = self._make_binding(record)
                healthy, reason = self._binding_health(binding)
            except (UnknownModuleError, ContractDeclarationError) as exc:
                healthy, reason = False, str(exc)
            self.store.append("startup_binding", dict(_key_data(record.key), provider_id=record.provider_id,
                                                     valid=healthy, reason=reason))
            if healthy:
                restored[record.key] = binding
        if len(restored) != len(self._saved):
            await self.store.save_bindings(tuple(b.record for b in restored.values()))
        self._bindings = restored
        self._state = RuntimeState.RUNNING
        self._pulse()

    def connection(self, key: BindingKey) -> ConnectionSnapshot:
        self._check_context()
        return self._binding(key).snapshot()

    def _binding(self, key: BindingKey) -> _Binding:
        if not isinstance(key, BindingKey):
            raise TypeError("key must be a BindingKey")
        try:
            return self._bindings[key]
        except KeyError:
            raise UnknownConnectionError(str(key)) from None

    async def bind(self, requester_id: str, contract: ContractKey, provider_id: str, *, wait_timeout: float) -> ConnectionSnapshot:
        self._check_running()
        self._validate_timeout(wait_timeout)
        key = BindingKey(requester_id, contract)
        locked = False
        try:
            try:
                async with asyncio.timeout(wait_timeout):
                    await self._bind_lock.acquire()
                    locked = True
                    self._check_running()
                    existing = self._bindings.get(key)
                    if existing is not None:
                        if existing.record.provider_id != provider_id:
                            raise ConnectionConflictError("An established provider cannot change during this runtime")
                        return existing.snapshot()
                    binding = self._make_binding(BindingRecord(key, provider_id))
                    healthy, reason = self._binding_health(binding)
                    if not healthy:
                        raise ConnectionUnavailableError(reason)
                    while not self.store.admitting:
                        change, storage_change = self._changed, self.store.changed
                        self._check_running()
                        await self._wait_changes(change, storage_change)
                    self._check_running()
                    healthy, reason = self._binding_health(binding)
                    if not healthy:
                        raise ConnectionUnavailableError(reason)
            except TimeoutError:
                raise PreparationTimeoutError("Initial connection admission deadline expired") from None
            # The store owns completion of a started disk write. Shield the entire
            # commit so cancellation cannot split persisted and in-memory settings.
            async def commit():
                await self.store.save_bindings(tuple(b.record for b in self._bindings.values()) + (binding.record,))
                self._bindings[key] = binding
                self.store.append("binding_created", dict(_key_data(key), provider_id=provider_id))
                self._pulse()
            task = asyncio.create_task(commit(), name="ntk-binding-commit")
            self._commits.add(task)
            task.add_done_callback(self._commits.discard)
            cancelled = False
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled = True
            task.result()
            if cancelled:
                raise asyncio.CancelledError
            return binding.snapshot()
        finally:
            if locked:
                self._bind_lock.release()

    def module_state(self, module_id: str) -> ModuleExecutionState:
        self._check_context()
        return self._module(module_id).execution

    def _notice(self, module_id: str, kind: NoticeKind, key: BindingKey | None = None, reason: str = "") -> int:
        self._notice_id += 1
        notice = ConnectionNotice(self._notice_id, module_id, kind, key, reason)
        self._module(module_id).notices.put_nowait(notice)
        self.store.append("notice", {"notice_id": notice.notice_id, "module_id": module_id,
                                    "kind": kind.value, "binding": None if key is None else _key_data(key), "reason": reason})
        return notice.notice_id

    async def next_notice(self, module_id: str) -> ConnectionNotice:
        self._check_context()
        module = self._module(module_id)
        if module.notices.empty() and self._state in (RuntimeState.STOPPING, RuntimeState.STOPPED, RuntimeState.FAILED):
            raise ConnectionsStateError("No further notifications after shutdown")
        return await module.notices.get()

    def report_link_error(self, key: BindingKey, exception: Exception) -> int:
        self._check_running()
        if not isinstance(exception, Exception):
            raise TypeError("exception must be an Exception")
        binding = self._binding(key)
        requester = binding.requester
        requester.execution = ModuleExecutionState.INTERRUPTING
        requester.causes.add(key)
        reason = f"{type(exception).__name__}: {exception}"
        binding.healthy, binding.reason = False, reason
        notice_id = self._notice(key.requester_id, NoticeKind.INTERRUPT, key, reason)
        requester.interruption_id = notice_id
        self.store.append("link_error", dict(_key_data(key), error_type=type(exception).__name__, message=str(exception)))
        provider_id = binding.record.provider_id
        affected = tuple(sorted(k for k, b in self._bindings.items()
                                if k.requester_id == provider_id or b.record.provider_id == provider_id))
        self._enqueue_health((provider_id,), affected)
        self._pulse()
        return notice_id

    def acknowledge_interruption(self, module_id: str, notice_id: int) -> bool:
        self._check_running()
        module = self._module(module_id)
        if type(notice_id) is not int or notice_id <= 0:
            raise ValueError("notice_id must be a positive integer")
        if module.execution != ModuleExecutionState.INTERRUPTING or module.interruption_id != notice_id:
            return False
        module.execution = ModuleExecutionState.SUSPENDED
        self.store.append("interruption_completed", {"module_id": module_id, "notice_id": notice_id})
        self._pulse()
        return True

    def _resume_for_request(self, module: _Module) -> None:
        if module.execution != ModuleExecutionState.SUSPENDED or not self.store.admitting:
            return
        if all(self._bindings[key].healthy and not self._bindings[key].checking for key in module.causes):
            module.execution = ModuleExecutionState.RUNNING
            module.causes.clear()
            self._notice(module.advertisement.module_id, NoticeKind.RESUMED)
            self._pulse()

    def _is_ready(self, binding: _Binding) -> bool:
        return (self._state == RuntimeState.RUNNING and binding.healthy and not binding.checking
                and binding.requester.execution == ModuleExecutionState.RUNNING and self.store.admitting)

    @staticmethod
    def _validate_timeout(wait_timeout: float) -> None:
        if type(wait_timeout) not in (int, float) or not math.isfinite(wait_timeout) or wait_timeout < 0:
            raise ValueError("wait_timeout must be finite nonnegative seconds")

    @staticmethod
    async def _wait_changes(change: asyncio.Event, storage_change: asyncio.Event) -> None:
        waits = [asyncio.create_task(change.wait()), asyncio.create_task(storage_change.wait())]
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waits:
                task.cancel()
            await asyncio.gather(*waits, return_exceptions=True)

    async def prepare(self, key: BindingKey, *, wait_timeout: float) -> PreparedConnection:
        self._check_running()
        self._validate_timeout(wait_timeout)
        binding = self._binding(key)
        try:
            async with asyncio.timeout(wait_timeout):
                while True:
                    change, storage_change = self._changed, self.store.changed
                    self._check_running()
                    self._resume_for_request(binding.requester)
                    if self._is_ready(binding):
                        return PreparedConnection(self, binding)
                    await self._wait_changes(change, storage_change)
        except TimeoutError:
            raise PreparationTimeoutError("Connection preparation deadline expired") from None

    async def invoke(self, key: BindingKey, operation: str, *, wait_timeout: float, args=(), kwargs=None):
        handle = await self.prepare(key, wait_timeout=wait_timeout)
        mode = handle._modes.get(operation)
        if mode == OperationMode.SYNC:
            return handle.call(operation, *args, **(kwargs or {}))
        return await handle.acall(operation, *args, **(kwargs or {}))

    def _enqueue_health(self, modules: tuple[str, ...], bindings: tuple[BindingKey, ...]) -> asyncio.Future:
        self._request_id += 1
        future = asyncio.get_running_loop().create_future()
        # A cancelled requester need not later retrieve an error from its ticket.
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        for key in bindings:
            self._bindings[key].checking += 1
        self._health_requests.put_nowait(_HealthRequest(self._request_id, modules, bindings, future))
        self.store.append("health_requested", {"request_id": self._request_id, "modules": list(modules),
                                              "bindings": [_key_data(k) for k in bindings]})
        self._pulse()
        return future

    async def health_check(self, *, module_ids=None, bindings=None) -> HealthResult:
        self._check_running()
        if isinstance(module_ids, (str, bytes)) or isinstance(bindings, (str, bytes)):
            raise TypeError("Health targets must be collections")
        if module_ids is None and bindings is None:
            modules, keys = tuple(sorted(self._modules)), tuple(sorted(self._bindings))
        else:
            modules = tuple(sorted(set(module_ids or ())))
            for module_id in modules:
                if not isinstance(module_id, str) or not module_id:
                    raise ValueError("Module targets must be nonempty strings")
            keys = set(bindings or ())
            for key in keys:
                self._binding(key)
            keys.update(key for key, binding in self._bindings.items()
                        if key.requester_id in modules or binding.record.provider_id in modules)
            keys = tuple(sorted(keys))
        future = self._enqueue_health(modules, keys)
        return await asyncio.shield(future)

    def _complete_health(self, request: _HealthRequest) -> None:
        module_results = tuple(self._module_health(module_id) for module_id in request.modules)
        results = []
        for key in request.bindings:
            binding = self._bindings[key]
            previous = binding.healthy
            binding.healthy, binding.reason = self._binding_health(binding)
            if previous != binding.healthy:
                self._notice(key.requester_id, NoticeKind.RECOVERED if binding.healthy else NoticeKind.INVALIDATED, key, binding.reason)
            results.append(BindingHealth(key, binding.record.provider_id, binding.healthy, binding.reason))
        self.store.append("health_completed", {"request_id": request.request_id,
                                              "connections": [dict(_key_data(r.key), healthy=r.healthy, reason=r.reason) for r in results]})
        if not request.future.done():
            request.future.set_result(HealthResult(request.request_id, module_results, tuple(results)))
        self._pulse()

    async def run(self) -> None:
        self._check_running()
        if self._run_entered:
            raise ConnectionsStateError("Connections run already entered")
        self._run_entered = True
        failure_wait = asyncio.create_task(self.store.wait_failure(), name="ntk-storage-watch")
        receive = None
        try:
            while self._state == RuntimeState.RUNNING:
                receive = asyncio.create_task(self._health_requests.get(), name="ntk-health-receive")
                done, _ = await asyncio.wait((failure_wait, receive), return_when=asyncio.FIRST_COMPLETED)
                if failure_wait in done:
                    raise failure_wait.result()
                request = receive.result()
                receive = None
                for key in request.bindings:
                    self._bindings[key].checking -= 1
                try:
                    self._complete_health(request)
                except BaseException as exc:
                    if not request.future.done():
                        request.future.set_exception(exc)
                    raise
                finally:
                    self._health_requests.task_done()
        finally:
            owned = [task for task in (failure_wait, receive) if task is not None]
            for task in owned:
                task.cancel()
            await asyncio.gather(*owned, return_exceptions=True)
            if receive is not None and not receive.cancelled() and receive.exception() is None:
                self._cancel_health(receive.result())

    def _cancel_health(self, request: _HealthRequest) -> None:
        for key in request.bindings:
            self._bindings[key].checking -= 1
        if not request.future.done():
            request.future.set_exception(ConnectionsStateError("Shutdown ended health processing"))
        self._health_requests.task_done()

    def begin_shutdown(self) -> None:
        self._check_context()
        if self._state in (RuntimeState.STOPPING, RuntimeState.STOPPED):
            return
        self._state = RuntimeState.STOPPING
        for module_id in self._modules:
            if self.store.failure is None:
                self._notice(module_id, NoticeKind.SHUTDOWN)
            else:
                self._notice_id += 1
                self._modules[module_id].notices.put_nowait(ConnectionNotice(self._notice_id, module_id, NoticeKind.SHUTDOWN, None))
        while not self._health_requests.empty():
            self._cancel_health(self._health_requests.get_nowait())
        self._pulse()

    async def stop(self) -> None:
        self._check_context()
        if self._state == RuntimeState.STOPPED:
            return
        self.begin_shutdown()
        if self._commits:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._commits)), return_exceptions=True)
        await self.store.stop()
        self._state = RuntimeState.FAILED if self.store.failure else RuntimeState.STOPPED
        self._pulse()
