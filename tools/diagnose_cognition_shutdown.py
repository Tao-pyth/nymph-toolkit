"""Repeat issue #169's exact test with parent-side lifecycle timing evidence.

Diagnostic wrappers observe the existing test without changing its three-second
shutdown deadline, storage, or assertions. Requires a source checkout's tests.
"""

# SPDX-License-Identifier: Apache-2.0
import argparse
from dataclasses import asdict
import faulthandler
import json
from pathlib import Path
import platform
import sys
import time
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.attempts <= 100:
        parser.error("--attempts must be between 1 and 100")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from tests.subsystems import test_cognition_integration as scenario

    original = scenario.group_at
    report = dict(python=sys.version, platform=platform.platform(), shutdown_timeout=3,
                  requested_attempts=args.attempts, completed_attempts=0, successful=True, cases=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    attempt = 0

    def instrumented(*values, **options):
        group = original(*values, **options)
        assert group.settings.shutdown_timeout == 3
        origin = time.monotonic()
        case = dict(attempt=attempt, events=[], processes={}, stop_seconds=None)
        report["cases"].append(case)

        def event(kind, **data):
            case["events"].append(dict(seconds=round(time.monotonic() - origin, 6), kind=kind, **data))

        def wrap_stop(function, module_id):
            async def observed():
                before = time.monotonic()
                event("stop_begin", module_id=module_id)
                try:
                    return await function()
                finally:
                    event("stop_end", module_id=module_id, duration=round(time.monotonic() - before, 6))
            return observed

        def wrap_observe(service):
            observe = service.observe
            def observed(**changes):
                result = observe(**changes)
                event("process", snapshot=asdict(service.snapshot))
                return result
            return observed

        for module_id, service in group.modules.items():
            service.stop = wrap_stop(service.stop, module_id)
            service.observe = wrap_observe(service)
        store = group.connections.store
        flush = store._flush_once

        async def observed_flush(through):
            before = time.monotonic()
            event("flush_begin", through=through)
            try:
                return await flush(through)
            finally:
                event("flush_end", through=through, duration=round(time.monotonic() - before, 6))
        store._flush_once = observed_flush
        stop = group.stop

        async def observed_group_stop():
            before = time.monotonic()
            event("group_stop_begin")
            try:
                return await stop()
            finally:
                case["stop_seconds"] = round(time.monotonic() - before, 6)
                case["processes"] = {key: asdict(group.process(key)) for key in group.modules}
                event("group_stop_end")
        group.stop = observed_group_stop
        return group

    faulthandler.dump_traceback_later(60, repeat=True)
    try:
        with patch.object(scenario, "group_at", instrumented):
            for attempt in range(1, args.attempts + 1):
                suite = unittest.TestSuite([scenario.CognitionIntegrationTests(
                    "test_cancel_and_runtime_stop_drain_admitted_learning")])
                result = unittest.TextTestRunner(verbosity=2).run(suite)
                report["completed_attempts"] = attempt
                report["successful"] = report["successful"] and result.wasSuccessful()
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
                latest = [case for case in report["cases"] if case["attempt"] == attempt]
                print(json.dumps(dict(attempt=attempt, successful=result.wasSuccessful(),
                                      stop_seconds=[case["stop_seconds"] for case in latest])), flush=True)
                if not result.wasSuccessful():
                    return 1
    finally:
        faulthandler.cancel_dump_traceback_later()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
