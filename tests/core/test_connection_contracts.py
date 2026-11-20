"""Public information contracts: copying, exact identity and invalid inputs."""

# SPDX-License-Identifier: Apache-2.0
from dataclasses import FrozenInstanceError
import unittest

from nymph_toolkit.contracts import (
    BindingKey, Candidate, ContractKey, ContractSpec, ModuleAdvertisement,
    ModuleKind, ModuleSpec, OperatingState, OperationFailure, OperationMode,
    OperationSpec, TemporaryUnavailable, Usage,
)
from nymph_toolkit.core import Registry


class ConnectionContractTests(unittest.TestCase):
    def setUp(self):
        self.key = ContractKey("memory.read", "1")
        self.operation = OperationSpec("get", OperationMode.SYNC)
        self.spec = ContractSpec(self.key, (self.operation,))

    def test_explicit_contract_and_requester_identity(self):
        self.assertNotEqual(self.key, ContractKey("memory.read", "1.0"))
        self.assertNotEqual(self.key, ContractKey("Memory.read", "1"))
        self.assertEqual(BindingKey("a", self.key), BindingKey("a", self.key))
        self.assertNotEqual(BindingKey("a", self.key), BindingKey("b", self.key))
        for key, version in (("", "1"), ("id ", "1"), ("id", " 1")):
            with self.subTest(key=key, version=version), self.assertRaises(ValueError):
                ContractKey(key, version)
        with self.assertRaises(TypeError):
            ContractKey("id", 1)

    def test_declarations_are_canonical_snapshots(self):
        operations = [OperationSpec("z", OperationMode.ASYNC), self.operation]
        contract = ContractSpec(self.key, operations)
        operations.clear()
        self.assertEqual([op.name for op in contract.operations], ["get", "z"])
        with self.assertRaises(ValueError):
            ContractSpec(self.key, (self.operation, self.operation))
        with self.assertRaises(ValueError):
            ContractSpec(self.key, ())
        with self.assertRaises(TypeError):
            OperationSpec("get", "sync")

    def test_attributes_do_not_allow_live_objects_or_mutable_aliases(self):
        attrs = {"language": "ja", "cost": 2.5, "local": True, "limit": None}
        tags = {"fast"}
        declarations = [self.spec]
        ad = ModuleAdvertisement("provider", "9", declarations, tags, attrs)
        attrs["cost"] = 99
        tags.clear()
        declarations.clear()
        self.assertEqual(ad.attributes["cost"], 2.5)
        self.assertEqual(ad.tags, frozenset({"fast"}))
        self.assertEqual(ad.contracts, (self.spec,))
        with self.assertRaises(TypeError):
            ad.attributes["cost"] = 0
        with self.assertRaises(FrozenInstanceError):
            ad.module_id = "changed"
        for value in ([], {}, lambda: True, object(), float("nan"), float("inf")):
            with self.subTest(value=type(value)), self.assertRaises((ValueError, TypeError)):
                ModuleAdvertisement("provider", "9", attributes={"bad": value})
        with self.assertRaises(ValueError):
            ModuleAdvertisement("provider", "9", (self.spec, self.spec))
        with self.assertRaises(TypeError):
            ModuleAdvertisement("provider", "9", tags="fast")

    def test_usage_does_not_confuse_unknown_with_running_or_capacity_with_health(self):
        self.assertEqual(Usage().state, OperatingState.UNKNOWN)
        self.assertFalse(Usage().accepting)
        full = Usage(OperatingState.RUNNING, True, 4, 4)
        shrinking = Usage(OperatingState.RUNNING, True, 4, 2)
        self.assertEqual(full.free, 0)
        self.assertEqual(shrinking.free, 0)
        self.assertEqual(shrinking.state, OperatingState.RUNNING)
        for field in ("active", "capacity"):
            for value in (-1, True, 1.5, None):
                with self.subTest(field=field, value=value), self.assertRaises((ValueError, TypeError)):
                    Usage(**{field: value})
        with self.assertRaises(TypeError):
            Usage(state="running")
        with self.assertRaises(TypeError):
            Usage(accepting=1)

    def test_candidate_keeps_registration_and_live_state_separate(self):
        registry = Registry()
        registry.register(ModuleSpec("provider", ModuleKind.SUBSYSTEM))
        ad = ModuleAdvertisement("provider", "2", (self.spec,))
        candidate = Candidate(registry.get("provider"), ad, self.key, Usage(), Usage())
        self.assertTrue(candidate.registration.available)
        self.assertEqual(candidate.module_usage.state, OperatingState.UNKNOWN)
        registry.unregister("provider")
        self.assertTrue(candidate.registration.available)
        with self.assertRaises(ValueError):
            Candidate(candidate.registration, ad, ContractKey("other", "1"), Usage(), Usage())
        with self.assertRaises(ValueError):
            Candidate(candidate.registration, ModuleAdvertisement("other", "2", (self.spec,)), self.key, Usage(), Usage())

    def test_declared_failures_are_data_and_capacity_is_distinct(self):
        failure = OperationFailure("not_found", "missing record")
        unavailable = TemporaryUnavailable()
        self.assertNotIsInstance(failure, BaseException)
        self.assertNotIsInstance(unavailable, OperationFailure)
        with self.assertRaises(ValueError):
            OperationFailure("", "message")
        with self.assertRaises(TypeError):
            TemporaryUnavailable(None)


if __name__ == "__main__":
    unittest.main()
