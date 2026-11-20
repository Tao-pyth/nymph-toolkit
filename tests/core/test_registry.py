"""Observe registration, transactional rejection and dependency changes through the API."""

# SPDX-License-Identifier: Apache-2.0
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import unittest

from nymph_toolkit.contracts import (
    DependencyCycleError, DuplicateModuleError, ModuleKind, ModuleSpec,
    RegistryStateError, UnknownModuleError,
)
from nymph_toolkit.core import Registry


def spec(module_id, *requires, kind=ModuleKind.SUBSYSTEM):
    return ModuleSpec(module_id, kind, frozenset(requires))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()

    def test_both_kinds_register_query_and_unregister(self):
        self.assertEqual(self.registry.entries(), ())
        self.assertEqual(self.registry.revision, 0)
        first = self.registry.register(spec("memory"))
        second = self.registry.register(spec("document", kind=ModuleKind.ADAPTER))
        self.assertEqual((first.revision, second.revision), (1, 2))
        self.assertEqual([e.spec.module_id for e in self.registry.entries()], ["document", "memory"])
        self.assertIsNone(first.changes[0].before)
        self.assertEqual(first.changes[0].after, self.registry.get("memory"))
        removed = self.registry.unregister("memory")
        self.assertIsNone(removed.changes[0].after)
        self.assertEqual(removed.changes[0].before.spec.module_id, "memory")
        with self.assertRaises(UnknownModuleError):
            self.registry.get("memory")

    def test_duplicate_does_not_replace_or_advance_revision(self):
        self.registry.register(spec("a"))
        before = self.registry.entries()
        with self.assertRaises(DuplicateModuleError):
            self.registry.register(spec("a", "missing", kind=ModuleKind.ADAPTER))
        self.assertEqual(self.registry.entries(), before)
        self.assertEqual(self.registry.revision, 1)

    def test_unknown_operations_and_invalid_values_are_atomic(self):
        for operation in (self.registry.get, self.registry.unregister):
            with self.assertRaises(UnknownModuleError):
                operation("unknown")
            with self.assertRaises(ValueError):
                operation("")
            with self.assertRaises(TypeError):
                operation(None)
        with self.assertRaises(TypeError):
            self.registry.register("a")
        self.assertEqual((self.registry.entries(), self.registry.revision), ((), 0))

    def test_ids_are_case_sensitive(self):
        self.registry.register(spec("A"))
        self.registry.register(spec("a"))
        self.assertEqual(len(self.registry.entries()), 2)

    def test_reregistration_has_new_generation_and_preserves_old_snapshot(self):
        self.registry.register(spec("a"))
        old = self.registry.get("a")
        self.registry.unregister("a")
        self.registry.register(spec("a", "b"))
        new = self.registry.get("a")
        self.assertTrue(old.available)
        self.assertFalse(new.available)
        self.assertGreater(new.generation, old.generation)
        with self.assertRaises(FrozenInstanceError):
            old.generation = new.generation

    def test_missing_dependencies_are_replaced_by_transitive_roots(self):
        self.registry.register(spec("a", "b"))
        before = self.registry.get("a")
        update = self.registry.register(spec("b", "c"))
        self.assertEqual(before.missing_dependencies, frozenset({"b"}))
        self.assertEqual(self.registry.get("a").missing_dependencies, frozenset({"c"}))
        self.assertEqual([c.module_id for c in update.changes], ["a", "b"])
        self.assertEqual(update.changes[0].before, before)
        self.assertEqual(self.registry.get("a").generation, before.generation)

    def test_dependency_registration_removal_and_recovery_notify_all_affected(self):
        self.registry.register(spec("a", "b"))
        self.registry.register(spec("b", "c"))
        self.registry.register(spec("unrelated"))
        for operation in (
            lambda: self.registry.register(spec("c")),
            lambda: self.registry.unregister("c"),
            lambda: self.registry.register(spec("c")),
        ):
            update = operation()
            self.assertEqual([c.module_id for c in update.changes], ["a", "b", "c"])
            self.assertEqual(update.revision, self.registry.revision)
        self.assertTrue(all(entry.available for entry in self.registry.entries()))

    def test_diamond_dependencies_report_each_missing_id_once(self):
        for item in (spec("a", "b", "c"), spec("b", "d"), spec("c", "d", "e")):
            self.registry.register(item)
        self.assertEqual(self.registry.get("a").missing_dependencies, frozenset({"d", "e"}))
        self.registry.register(spec("d"))
        self.assertEqual(self.registry.get("a").missing_dependencies, frozenset({"e"}))

    def test_self_cycle_is_rejected_without_committing(self):
        with self.assertRaises(DependencyCycleError):
            self.registry.register(spec("a", "a"))
        self.assertEqual((self.registry.entries(), self.registry.revision), ((), 0))

    def test_cycle_through_previously_missing_target_is_atomic(self):
        self.registry.register(spec("a", "b"))
        self.registry.register(spec("b", "c"))
        before = self.registry.entries()
        with self.assertRaises(DependencyCycleError):
            self.registry.register(spec("c", "a"))
        self.assertEqual(self.registry.entries(), before)
        self.assertEqual(self.registry.revision, 2)
        self.registry.register(spec("c"))
        self.assertTrue(self.registry.get("a").available)

    def test_generation_is_not_reused_after_failed_attempt(self):
        self.registry.register(spec("a"))
        self.registry.unregister("a")
        with self.assertRaises(DependencyCycleError):
            self.registry.register(spec("a", "a"))
        update = self.registry.register(spec("a"))
        self.assertEqual(update.changes[0].after.generation, 3)

    def test_cross_thread_reads_and_writes_are_rejected(self):
        operations = (
            lambda: self.registry.register(spec("a")),
            lambda: self.registry.get("a"),
            lambda: self.registry.unregister("a"),
            self.registry.entries,
            lambda: self.registry.revision,
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            for operation in operations:
                with self.assertRaises(RegistryStateError):
                    executor.submit(operation).result()
        self.assertEqual(self.registry.revision, 0)

    def test_chain_uses_iterative_dependency_evaluation(self):
        for index in range(100):
            self.registry.register(spec(str(index), str(index + 1)))
        self.assertEqual(self.registry.get("0").missing_dependencies, frozenset({"100"}))
        update = self.registry.register(spec("100"))
        self.assertEqual(len(update.changes), 101)
        self.assertTrue(self.registry.get("0").available)
