"""Public registration contracts must retain immutable observations."""

# SPDX-License-Identifier: Apache-2.0
from dataclasses import FrozenInstanceError
import unittest

from nymph_toolkit.contracts import (
    LifecyclePhase, ModuleFailure, ModuleGroupFailure, ModuleKind, ModuleSpec,
    RegistryChange, RegistryEntry, RegistryUpdate,
)


class RegistryContractTests(unittest.TestCase):
    def test_spec_copies_dependencies_and_is_immutable(self):
        required = {"memory"}
        spec = ModuleSpec("reader", ModuleKind.ADAPTER, required)
        required.clear()
        self.assertEqual(spec.requires, frozenset({"memory"}))
        with self.assertRaises(FrozenInstanceError):
            spec.module_id = "changed"

    def test_invalid_ids_and_kinds_are_rejected(self):
        for module_id in ("", " leading", "trailing ", "\t"):
            with self.subTest(module_id=module_id), self.assertRaises(ValueError):
                ModuleSpec(module_id, ModuleKind.SUBSYSTEM)
        with self.assertRaises(TypeError):
            ModuleSpec(1, ModuleKind.SUBSYSTEM)
        with self.assertRaises(TypeError):
            ModuleSpec("a", "subsystem")

    def test_dependencies_are_ids_not_a_string(self):
        for dependencies in ("memory", b"memory", {1}, None):
            with self.subTest(dependencies=dependencies), self.assertRaises(TypeError):
                ModuleSpec("a", ModuleKind.ADAPTER, dependencies)
        with self.assertRaises(ValueError):
            ModuleSpec("a", ModuleKind.ADAPTER, {""})

    def test_snapshot_and_notification_copy_collections(self):
        missing = {"b"}
        entry = RegistryEntry(ModuleSpec("a", ModuleKind.SUBSYSTEM), 1, missing)
        change = RegistryChange("a", None, entry)
        changes = [change]
        update = RegistryUpdate(1, changes)
        missing.clear()
        changes.clear()
        self.assertFalse(entry.available)
        self.assertEqual(entry.missing_dependencies, frozenset({"b"}))
        self.assertEqual(update.changes, (change,))
        with self.assertRaises(FrozenInstanceError):
            change.after = None

    def test_failure_preserves_identity_phase_and_original_exception(self):
        original = ValueError("failure")
        failure = ModuleFailure("a", LifecyclePhase.RUN, original)
        group = ModuleGroupFailure((failure,))
        self.assertIs(group.failures[0].exception, original)
        self.assertEqual(group.failures[0].module_id, "a")
        self.assertIn("a/run", str(group))
        with self.assertRaises(ValueError):
            ModuleGroupFailure(())
