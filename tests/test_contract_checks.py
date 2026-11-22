"""The compatibility check must detect real consumer-visible changes."""

# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
import unittest

from tools.check_api import inventory
from tools.check_contracts import BASELINE, differences


class ContractBaselineTests(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.actual = inventory()

    def test_current_public_surface_matches_reviewed_baseline(self):
        self.assertEqual(differences(self.baseline, self.actual), [])

    def test_removed_export_is_rejected(self):
        del self.actual["nymph_toolkit.core"]["validate_module_registration"]
        self.assertTrue(differences(self.baseline, self.actual))

    def test_changed_call_signature_is_rejected(self):
        self.actual["nymph_toolkit.core"]["CoreClient"]["members"]["bind"]["signature"] = "(self, different)"
        self.assertTrue(differences(self.baseline, self.actual))

    def test_changed_enum_or_dataclass_field_is_rejected(self):
        for name, field, value in (("Placement", "values", {}), ("ModuleSpec", "fields", {})):
            with self.subTest(name=name):
                changed = deepcopy(self.actual)
                changed["nymph_toolkit.contracts"][name][field] = value
                self.assertTrue(differences(self.baseline, changed))

    def test_core_owned_constructor_is_not_a_function_author_contract(self):
        self.actual["nymph_toolkit.core"]["ModuleContext"]["signature"] = "(internal_detail)"
        self.assertEqual(differences(self.baseline, self.actual), [])
