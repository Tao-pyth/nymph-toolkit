"""Additional contracts preserve explicit intent and immutable command evidence."""

# SPDX-License-Identifier: Apache-2.0
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone
import unittest

from nymph_toolkit.contracts import (
    UNCHANGED, ActivityChange, ActivityCommandResult, ActivityCommandStatus,
    ActivityNotice, ActivityNoticeKind, ActivityRequest,
)
from tests.core.test_activity_contracts import START, request, snapshot


class ActivityChangeContractTests(unittest.TestCase):
    def test_original_positional_request_keeps_default_priority(self):
        original = request()
        compatible = ActivityRequest(original.key, original.content, original.start_at,
                                     original.duration, {"x": [1]})
        self.assertEqual(compatible.priority, 0)
        self.assertEqual(replace(compatible, priority=-12).as_dict()["priority"], -12)
        for value in (True, 1.5, "1", None):
            with self.assertRaises(TypeError):
                replace(compatible, priority=value)

    def test_absent_start_and_explicit_immediate_are_distinct(self):
        duration = ActivityChange(duration=timedelta(seconds=30))
        immediate = ActivityChange(start_at=None)
        self.assertIs(duration.start_at, UNCHANGED)
        self.assertNotIn("start_at", duration.as_dict())
        self.assertEqual(immediate.as_dict(), {"start_at": None})
        local = START.astimezone(timezone(timedelta(hours=9)))
        self.assertEqual(ActivityChange(start_at=local).start_at, START)
        with self.assertRaises(FrozenInstanceError):
            duration.priority = 10

    def test_invalid_change_cannot_enter_the_manager(self):
        for values in ({}, {"duration": None}, {"duration": timedelta()},
                       {"priority": True}, {"priority": 1.0}, {"start_at": START.replace(tzinfo=None)}):
            with self.subTest(values=values), self.assertRaises((ValueError, TypeError)):
                ActivityChange(**values)

    def test_current_observation_preserves_original_and_validates_time_and_versions(self):
        initial = snapshot()
        current = replace(initial.request, priority=5)
        changed = replace(initial, current_request=current, revision=1, elapsed_seconds=10, execution_seconds=3)
        self.assertEqual(initial.current_request, initial.request)
        self.assertEqual(changed.request.priority, 0)
        self.assertEqual(changed.current_request.priority, 5)
        for values in ({"revision": True}, {"scheduled_revision": -1}, {"execution_seconds": 11},
                       {"execution_seconds": float("nan")}):
            with self.assertRaises(ValueError):
                replace(changed, **values)

    def test_command_result_and_notice_are_stable_observations(self):
        observed = snapshot()
        result = ActivityCommandResult(observed.request.key, "pause-1", "pause", START,
                                       ActivityCommandStatus.ACCEPTED, None, observed)
        notice = ActivityNotice(1, ActivityNoticeKind.COMMAND_RESULT, START, observed, result)
        applied = replace(result, status=ActivityCommandStatus.APPLIED)
        self.assertFalse(notice.command.status.terminal)
        self.assertTrue(applied.status.terminal)
        with self.assertRaises(FrozenInstanceError):
            result.status = ActivityCommandStatus.APPLIED
        with self.assertRaises(ValueError):
            replace(result, command_id=" whitespace ")
        with self.assertRaises(ValueError):
            replace(notice, command=None)
