"""Completion checks must reject missing or altered acceptance evidence."""

# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from typing import Optional, TypeVar

from tools.check_api import signature
from tools.check_completion import ADR, validate


class ApiInventoryTests(unittest.TestCase):
    def test_path_uses_the_public_module_name_on_supported_pythons(self):
        def accept(path: Path) -> Path:
            return path
        self.assertEqual(signature(accept), "(path: pathlib.Path) -> pathlib.Path")

    def test_optional_type_variable_has_one_spelling_on_supported_pythons(self):
        value = TypeVar("Result")
        def optional() -> Optional[value]:
            pass
        def union() -> value | None:
            pass
        self.assertEqual(signature(optional), "() -> ~Result | None")
        self.assertEqual(signature(union), signature(optional))


class CompletionEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / ADR).parent.mkdir(parents=True)
        (self.root / ADR).write_text(
            "\n".join(f"| {n} | topic {n} | adopted {n} | A07-01 |" for n in range(1, 65)),
            encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests/test_dummy.py").write_text(
            "class Dummy:\n    def test_behavior(self):\n        pass\n", encoding="utf-8")
        self.data = {
            "schema": 1,
            "decisions": [
                {"number": n, "topic": f"topic {n}", "decision": f"adopted {n}",
                 "acceptance": "A07-01", "tests": ["tests.test_dummy.Dummy.test_behavior"],
                 "implementation": ["tests/test_dummy.py"], "documents": [ADR],
                 "note": "Reference integrity is separate from execution."}
                for n in range(1, 65)
            ],
            "baseline": [
                {"acceptance": f"A0{n}", "modules": ["tests.test_dummy"], "document": ADR}
                for n in range(2, 9)
            ],
        }

    def test_complete_references_are_valid_but_do_not_execute_a_test(self):
        self.assertEqual(validate(self.data, self.root), {"tests.test_dummy.Dummy.test_behavior"})

    def test_missing_duplicate_or_changed_adoption_is_rejected(self):
        for change in ("missing", "duplicate", "changed"):
            with self.subTest(change=change):
                data = deepcopy(self.data)
                if change == "missing":
                    data["decisions"].pop()
                elif change == "duplicate":
                    data["decisions"][-1]["number"] = 1
                else:
                    data["decisions"][0]["decision"] = "different behavior"
                with self.assertRaises(ValueError):
                    validate(data, self.root)

    def test_missing_behavior_and_nonexistent_test_are_rejected(self):
        for value in ([], ["tests.test_dummy.Dummy.test_removed"]):
            with self.subTest(value=value):
                data = deepcopy(self.data)
                data["decisions"][0]["tests"] = value
                with self.assertRaises(ValueError):
                    validate(data, self.root)

    def test_missing_document_and_outside_reference_are_rejected(self):
        for value in ("removed.md", "../outside.md"):
            with self.subTest(value=value):
                data = deepcopy(self.data)
                data["decisions"][0]["documents"] = [value]
                with self.assertRaises(ValueError):
                    validate(data, self.root)

    def test_missing_baseline_and_unknown_schema_are_rejected(self):
        data = deepcopy(self.data)
        data["baseline"].pop()
        with self.assertRaises(ValueError):
            validate(data, self.root)
        data = deepcopy(self.data)
        data["schema"] = 2
        with self.assertRaises(ValueError):
            validate(data, self.root)
