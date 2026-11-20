"""Activity data preserves Nymph's intent without making execution decisions."""

# SPDX-License-Identifier: Apache-2.0
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo
import json
import unittest

from nymph_toolkit.contracts import (
    ActivityFailure, ActivityFinishReason, ActivityKey, ActivityNotice,
    ActivityNoticeKind, ActivityRequest, ActivitySnapshot, ActivityStartInPastError,
    ActivityState,
)

UTC = timezone.utc
START = datetime(2026, 11, 21, 13, tzinfo=UTC)


def request(**changes):
    values = dict(key=ActivityKey("nymph", "research"), content="調査",
                  start_at=START, duration=timedelta(hours=2))
    values.update(changes)
    return ActivityRequest(**values)


def snapshot(**changes):
    values = dict(request=request(), state=ActivityState.PENDING, accepted_at=START,
                  planned_start_at=START, planned_end_at=START + timedelta(hours=2))
    values.update(changes)
    return ActivitySnapshot(**values)


class ActivityContractTests(unittest.TestCase):
    def test_key_preserves_owner_identity_and_rejects_invalid_identifiers(self):
        self.assertNotEqual(ActivityKey("one", "work"), ActivityKey("two", "work"))
        self.assertNotEqual(ActivityKey("one", "work"), ActivityKey("one", "WORK"))
        for value in ("", " one", "one ", "\t", None, 1):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                ActivityKey(value, "work")
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                ActivityKey("one", value)
        with self.assertRaises(FrozenInstanceError):
            ActivityKey("one", "work").activity_id = "changed"

    def test_planned_time_is_utc_and_not_extended_by_a_late_actual_start(self):
        local = datetime(2026, 11, 21, 22, tzinfo=timezone(timedelta(hours=9)))
        plan = request(start_at=local)
        self.assertEqual(plan.start_at, START)
        self.assertIs(plan.start_at.tzinfo, UTC)
        start, end = plan.planned_times(START + timedelta(minutes=10))
        self.assertEqual(start, START)
        self.assertEqual(end, datetime(2026, 11, 21, 15, tzinfo=UTC))
        self.assertEqual(end.astimezone(local.tzinfo).hour, 0)

    def test_explicit_now_uses_acceptance_time_without_mutating_request(self):
        plan = request(start_at=None)
        accepted = START + timedelta(minutes=10)
        self.assertEqual(plan.planned_times(accepted), (accepted, accepted + plan.duration))
        self.assertIsNone(plan.start_at)
        self.assertIsNone(plan.as_dict()["start_at"])

    def test_ambiguous_or_out_of_range_times_and_invalid_durations_are_rejected(self):
        class NoOffset(tzinfo):
            def utcoffset(self, dt):
                return None
        for value in (datetime(2026, 11, 21), START.replace(tzinfo=NoOffset()), "22:00"):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                request(start_at=value)
        for value in (timedelta(), timedelta(microseconds=-1), 2, True, None):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                request(duration=value)
        with self.assertRaises(ValueError):
            request(start_at=datetime.max.replace(tzinfo=UTC))
        with self.assertRaises(ValueError):
            request(start_at=None).planned_times(datetime.max.replace(tzinfo=UTC))

    def test_nested_input_is_copied_frozen_and_record_copy_is_independent(self):
        shared = [1, {"text": "日本語", "flags": [True, None]}]
        source = {"first": shared, "second": shared}
        plan = request(parameters=source, duration=timedelta(microseconds=1))
        shared[1]["flags"].append(False)
        source.clear()
        self.assertEqual(plan.parameters["first"][1]["flags"], (True, None))
        with self.assertRaises(TypeError):
            plan.parameters["first"][1]["text"] = "changed"
        record = plan.as_dict()
        self.assertEqual(record["duration_us"], 1)
        json.dumps(record, allow_nan=False)
        record["parameters"]["first"].clear()
        self.assertEqual(len(plan.parameters["first"]), 2)

    def test_non_json_and_cyclic_input_is_rejected_without_mutating_the_input(self):
        cycle = []
        cycle.append(cycle)
        for value in ({1: "invalid key"}, {"v": float("nan")}, {"v": float("inf")},
                      {"v": object()}, {"v": {1, 2}}, {"v": cycle}, [], None):
            with self.subTest(value=type(value)), self.assertRaises((ValueError, TypeError)):
                request(parameters=value)
        self.assertIs(cycle[0], cycle)

    def test_content_is_opaque_and_data_does_not_choose_activity_value(self):
        work = request(content="調査")
        sleep = replace(work, content="睡眠")
        self.assertEqual(work.planned_times(START), sleep.planned_times(START))
        for value in ("", " \t", None, 10):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                request(content=value)

    def test_observation_retains_result_copy_exception_identity_and_finish_reason(self):
        original = ValueError("executor failed")
        failures = [ActivityFailure(original)]
        result = {"observed": [1, 2]}
        observed = snapshot(state=ActivityState.FAILED, result=result, failures=failures,
                            finish_reason=ActivityFinishReason.NYMPH)
        result["observed"].append(3)
        failures.clear()
        self.assertEqual(observed.result["observed"], (1, 2))
        self.assertIs(observed.failures[0].exception, original)
        self.assertIs(observed.finish_reason, ActivityFinishReason.NYMPH)
        with self.assertRaises(FrozenInstanceError):
            observed.state = ActivityState.COMPLETED

    def test_elapsed_time_and_notice_cannot_claim_an_invalid_observation(self):
        for value in (True, -1, float("nan"), float("inf"), "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                snapshot(elapsed_seconds=value)
        with self.assertRaises(TypeError):
            snapshot(accepted_at=None)
        for value in (True, 0, -1):
            with self.assertRaises(ValueError):
                ActivityNotice(value, ActivityNoticeKind.PLANNED_END, START, snapshot())
        notice = ActivityNotice(1, ActivityNoticeKind.PLANNED_END, START,
                                snapshot(state=ActivityState.RUNNING, planned_end_notified=True))
        self.assertFalse(notice.snapshot.state.terminal)
        self.assertFalse(ActivityState.FINISHING.terminal)
        for state in (ActivityState.COMPLETED, ActivityState.FAILED, ActivityState.STOPPED):
            self.assertTrue(state.terminal)

    def test_past_start_rejection_retains_original_request_for_nymph_to_revise(self):
        plan = request()
        error = ActivityStartInPastError(plan, START + timedelta(minutes=10))
        self.assertIs(error.request, plan)
        self.assertEqual(error.request.start_at, START)
        self.assertEqual(error.observed_at, START + timedelta(minutes=10))
        self.assertIn("Nymph", str(error))
