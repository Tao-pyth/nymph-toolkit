"""Immutable registration data and failures adopted for v0.3."""

# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
from enum import StrEnum

from . import LifecyclePhase


def _validate_module_id(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError("module_id must be a string")
    if not value or value.strip() != value:
        raise ValueError("module_id must be nonempty without surrounding whitespace")


class ModuleKind(StrEnum):
    SUBSYSTEM = "subsystem"
    ADAPTER = "adapter"


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    kind: ModuleKind
    requires: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        _validate_module_id(self.module_id)
        if not isinstance(self.kind, ModuleKind):
            raise TypeError("kind must be a ModuleKind")
        if isinstance(self.requires, (str, bytes)):
            raise TypeError("requires must be a collection of module IDs")
        requires = frozenset(self.requires)
        for module_id in requires:
            _validate_module_id(module_id)
        object.__setattr__(self, "requires", requires)


@dataclass(frozen=True)
class RegistryEntry:
    spec: ModuleSpec
    generation: int
    missing_dependencies: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_dependencies", frozenset(self.missing_dependencies))

    @property
    def available(self) -> bool:
        """All required IDs are registered; this is not runtime health or permission."""
        return not self.missing_dependencies


@dataclass(frozen=True)
class RegistryChange:
    module_id: str
    before: RegistryEntry | None
    after: RegistryEntry | None


@dataclass(frozen=True)
class RegistryUpdate:
    revision: int
    changes: tuple[RegistryChange, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "changes", tuple(self.changes))


class RegistryError(RuntimeError):
    """A registration or configuration operation could not be applied."""


class RegistryStateError(RegistryError):
    """Wrong owner thread, or configuration is frozen by a running ModuleGroup."""


class DuplicateModuleError(RegistryError):
    pass


class UnknownModuleError(RegistryError):
    pass


class DependencyCycleError(RegistryError):
    pass


class DependencyUnavailableError(RegistryError):
    def __init__(self, missing_dependencies: frozenset[str]) -> None:
        self.missing_dependencies = frozenset(missing_dependencies)
        super().__init__("Missing dependencies: " + ", ".join(sorted(self.missing_dependencies)))


@dataclass(frozen=True)
class ModuleFailure:
    module_id: str
    phase: LifecyclePhase
    exception: BaseException


class ModuleGroupFailure(RuntimeError):
    """Identify every ordinary service failure, including cleanup failures."""

    def __init__(self, failures: tuple[ModuleFailure, ...]) -> None:
        if not failures:
            raise ValueError("ModuleGroupFailure requires at least one failure")
        self.failures = tuple(failures)
        super().__init__("; ".join(
            f"{f.module_id}/{f.phase}: {type(f.exception).__name__}: {f.exception}"
            for f in self.failures
        ))
