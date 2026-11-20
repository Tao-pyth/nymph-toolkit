"""Immutable capability and operating-state information for v0.4 connections."""

# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import math
from types import MappingProxyType

from .registry import RegistryEntry
from . import LifecycleFailure


def _text(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be nonempty without surrounding whitespace")


def _count(value: int, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer, not bool")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


class OperationMode(StrEnum):
    SYNC = "sync"
    ASYNC = "async"


class OperatingState(StrEnum):
    UNKNOWN = "unknown"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, order=True)
class ContractKey:
    contract_id: str
    version: str

    def __post_init__(self) -> None:
        _text(self.contract_id, "contract_id")
        _text(self.version, "version")


@dataclass(frozen=True)
class OperationSpec:
    name: str
    mode: OperationMode

    def __post_init__(self) -> None:
        _text(self.name, "name")
        if not isinstance(self.mode, OperationMode):
            raise TypeError("mode must be an OperationMode")


@dataclass(frozen=True)
class ContractSpec:
    key: ContractKey
    operations: tuple[OperationSpec, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.key, ContractKey):
            raise TypeError("key must be a ContractKey")
        operations = tuple(self.operations)
        if not operations or not all(isinstance(op, OperationSpec) for op in operations):
            raise ValueError("operations must contain OperationSpec values")
        if len({op.name for op in operations}) != len(operations):
            raise ValueError("operation names must be unique within a contract")
        object.__setattr__(self, "operations", tuple(sorted(operations, key=lambda op: op.name)))


@dataclass(frozen=True)
class Usage:
    state: OperatingState = OperatingState.UNKNOWN
    accepting: bool = False
    active: int = 0
    capacity: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.state, OperatingState):
            raise TypeError("state must be an OperatingState")
        if type(self.accepting) is not bool:
            raise TypeError("accepting must be bool")
        _count(self.active, "active")
        _count(self.capacity, "capacity")

    @property
    def free(self) -> int:
        return max(0, self.capacity - self.active)


Scalar = str | bool | int | float | None


@dataclass(frozen=True)
class ModuleAdvertisement:
    module_id: str
    implementation_version: str
    contracts: tuple[ContractSpec, ...] = ()
    tags: frozenset[str] = field(default_factory=frozenset)
    attributes: Mapping[str, Scalar] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.module_id, "module_id")
        _text(self.implementation_version, "implementation_version")
        contracts = tuple(self.contracts)
        if not all(isinstance(c, ContractSpec) for c in contracts):
            raise TypeError("contracts must contain ContractSpec values")
        if len({c.key for c in contracts}) != len(contracts):
            raise ValueError("a contract key can only be declared once per module")
        if isinstance(self.tags, (str, bytes)):
            raise TypeError("tags must be a collection of strings")
        tags = frozenset(self.tags)
        for tag in tags:
            _text(tag, "tag")
        if not isinstance(self.attributes, Mapping):
            raise TypeError("attributes must be a mapping")
        attributes = dict(self.attributes)
        for name, value in attributes.items():
            _text(name, "attribute name")
            if type(value) not in (str, bool, int, float, type(None)):
                raise TypeError("attributes must be JSON scalar values")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("attribute floats must be finite")
        object.__setattr__(self, "contracts", tuple(sorted(contracts, key=lambda c: c.key)))
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "attributes", MappingProxyType(attributes))


@dataclass(frozen=True)
class Candidate:
    registration: RegistryEntry
    advertisement: ModuleAdvertisement
    contract: ContractKey
    module_usage: Usage
    contract_usage: Usage

    def __post_init__(self) -> None:
        if not isinstance(self.registration, RegistryEntry):
            raise TypeError("registration must be a RegistryEntry")
        if not isinstance(self.advertisement, ModuleAdvertisement):
            raise TypeError("advertisement must be a ModuleAdvertisement")
        if self.registration.spec.module_id != self.advertisement.module_id:
            raise ValueError("registration and advertisement must identify the same module")
        if not isinstance(self.contract, ContractKey):
            raise TypeError("contract must be a ContractKey")
        if not any(c.key == self.contract for c in self.advertisement.contracts):
            raise ValueError("candidate must declare the requested contract")
        if not isinstance(self.module_usage, Usage) or not isinstance(self.contract_usage, Usage):
            raise TypeError("candidate usage values must be Usage snapshots")


@dataclass(frozen=True, order=True)
class BindingKey:
    requester_id: str
    contract: ContractKey

    def __post_init__(self) -> None:
        _text(self.requester_id, "requester_id")
        if not isinstance(self.contract, ContractKey):
            raise TypeError("contract must be a ContractKey")


@dataclass(frozen=True)
class OperationFailure:
    """A declared business failure returned as data, not a broken connection."""

    code: str
    message: str

    def __post_init__(self) -> None:
        _text(self.code, "code")
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")


@dataclass(frozen=True)
class TemporaryUnavailable:
    """The provider declined admission; do not queue or request health for this alone."""

    message: str = "Provider has no capacity or is not accepting work"

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")


class BindingState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    CHECKING = "checking"


@dataclass(frozen=True)
class BindingRecord:
    key: BindingKey
    provider_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, BindingKey):
            raise TypeError("key must be a BindingKey")
        _text(self.provider_id, "provider_id")


class ModuleExecutionState(StrEnum):
    RUNNING = "running"
    INTERRUPTING = "interrupting"
    SUSPENDED = "suspended"


class NoticeKind(StrEnum):
    INTERRUPT = "interrupt"
    INVALIDATED = "invalidated"
    RECOVERED = "recovered"
    RESUMED = "resumed"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class ConnectionSnapshot:
    key: BindingKey
    provider_id: str
    state: BindingState
    reason: str = ""


@dataclass(frozen=True)
class ConnectionNotice:
    notice_id: int
    module_id: str
    kind: NoticeKind
    binding: BindingKey | None
    reason: str = ""


@dataclass(frozen=True)
class ModuleHealth:
    module_id: str
    healthy: bool
    reason: str = ""


@dataclass(frozen=True)
class BindingHealth:
    key: BindingKey
    provider_id: str
    healthy: bool
    reason: str = ""


@dataclass(frozen=True)
class HealthResult:
    request_id: int
    modules: tuple[ModuleHealth, ...]
    connections: tuple[BindingHealth, ...]


@dataclass(frozen=True)
class LinkFailure:
    binding: BindingKey
    exception: Exception
    interruption_id: int | None


class ConnectionsError(RuntimeError):
    """A connection management operation could not be applied."""


class ConnectionsStateError(ConnectionsError):
    """An operation was used from the wrong lifecycle, thread or event loop."""


class ConnectionsLifecycleFailure(ConnectionsError):
    """Infrastructure failures, distinct from a registered module's failures."""

    def __init__(self, failures: tuple[LifecycleFailure, ...]) -> None:
        if not failures:
            raise ValueError("ConnectionsLifecycleFailure requires failures")
        self.failures = tuple(failures)
        super().__init__("Connections: " + "; ".join(
            f"{failure.phase}: {type(failure.exception).__name__}: {failure.exception}"
            for failure in failures
        ))


class ContractDeclarationError(ConnectionsError):
    pass


class UnknownConnectionError(ConnectionsError):
    pass


class ConnectionConflictError(ConnectionsError):
    pass


class ConnectionUnavailableError(ConnectionsError):
    """An initial provider is not ready; no binding was established."""


class ConnectionNotReadyError(ConnectionsError):
    """A prepared handle changed state before use; its operation was not executed."""


class PreparationTimeoutError(ConnectionsError, TimeoutError):
    pass


class StorageError(RuntimeError):
    pass


class StorageCorruptionError(StorageError):
    """Existing settings cannot be interpreted and must not be overwritten."""


class StorageFailure(StorageError):
    """A failed rescue, retained for the owner to report after shutdown."""

    def __init__(self, cause: Exception, unsaved_events: int, pending_configuration: bool) -> None:
        self.cause = cause
        self.unsaved_events = unsaved_events
        self.pending_configuration = pending_configuration
        super().__init__(str(self))

    def __str__(self) -> str:
        return (f"Storage rescue failed: {self.cause}; unsaved_events={self.unsaved_events}, "
                f"pending_configuration={self.pending_configuration}")
