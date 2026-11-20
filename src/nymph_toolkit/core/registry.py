"""Synchronous registration metadata; no service references or communication permissions."""

# SPDX-License-Identifier: Apache-2.0
import heapq
import threading

from nymph_toolkit.contracts import (
    DependencyCycleError, DuplicateModuleError, ModuleSpec, RegistryChange,
    RegistryEntry, RegistryStateError, RegistryUpdate, UnknownModuleError,
)
from nymph_toolkit.contracts.registry import _validate_module_id


class Registry:
    """Own immutable snapshots on one thread and return all changes with each mutation."""

    def __init__(self) -> None:
        self._owner = threading.current_thread()
        self._entries: dict[str, RegistryEntry] = {}
        self._revision = 0

    def _check_thread(self) -> None:
        if threading.current_thread() is not self._owner:
            raise RegistryStateError("Registry must be accessed from its owner thread")

    @property
    def revision(self) -> int:
        self._check_thread()
        return self._revision

    def get(self, module_id: str) -> RegistryEntry:
        self._check_thread()
        _validate_module_id(module_id)
        try:
            return self._entries[module_id]
        except KeyError:
            raise UnknownModuleError(module_id) from None

    def entries(self) -> tuple[RegistryEntry, ...]:
        self._check_thread()
        return tuple(self._entries[key] for key in sorted(self._entries))

    def register(self, spec: ModuleSpec) -> RegistryUpdate:
        self._check_thread()
        if not isinstance(spec, ModuleSpec):
            raise TypeError("spec must be a ModuleSpec")
        if spec.module_id in self._entries:
            raise DuplicateModuleError(spec.module_id)
        proposed = dict(self._entries)
        proposed[spec.module_id] = RegistryEntry(spec, self._revision + 1)
        return self._commit(self._evaluate(proposed))

    def unregister(self, module_id: str) -> RegistryUpdate:
        self.get(module_id)
        proposed = dict(self._entries)
        del proposed[module_id]
        return self._commit(self._evaluate(proposed))

    @staticmethod
    def _evaluate(proposed: dict[str, RegistryEntry]) -> dict[str, RegistryEntry]:
        """Evaluate in dependency order without recursion, before committing anything."""
        present = proposed.keys()
        waiting = {key: len(entry.spec.requires & present) for key, entry in proposed.items()}
        dependents: dict[str, list[str]] = {key: [] for key in proposed}
        for key, entry in proposed.items():
            for dependency in entry.spec.requires & present:
                dependents[dependency].append(key)
        ready = [key for key, count in waiting.items() if count == 0]
        heapq.heapify(ready)
        evaluated: dict[str, RegistryEntry] = {}
        while ready:
            key = heapq.heappop(ready)
            entry = proposed[key]
            missing = set(entry.spec.requires - present)
            for dependency in entry.spec.requires & present:
                missing.update(evaluated[dependency].missing_dependencies)
            evaluated[key] = RegistryEntry(entry.spec, entry.generation, frozenset(missing))
            for dependent in dependents[key]:
                waiting[dependent] -= 1
                if waiting[dependent] == 0:
                    heapq.heappush(ready, dependent)
        if len(evaluated) != len(proposed):
            raise DependencyCycleError("Dependency cycle: " + ", ".join(
                sorted(set(proposed) - evaluated.keys())
            ))
        return evaluated

    def _commit(self, evaluated: dict[str, RegistryEntry]) -> RegistryUpdate:
        before = self._entries
        changes = tuple(
            RegistryChange(key, before.get(key), evaluated.get(key))
            for key in sorted(before.keys() | evaluated.keys())
            if before.get(key) != evaluated.get(key)
        )
        self._entries = evaluated
        self._revision += 1
        return RegistryUpdate(self._revision, changes)

    def _dependency_order(self) -> tuple[RegistryEntry, ...]:
        self._check_thread()
        return tuple(self._entries.values())
