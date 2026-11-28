# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.request import Request, urlopen

from examples.runtime_diagnostics_demo import configure
from nymph_toolkit.contracts import ActivityKey, ActivityRequest, BindingKey, Placement, RuntimeFailure
from nymph_toolkit.contracts.diagnostics import validate_report
from nymph_toolkit.diagnostics import DiagnosticSession, ReportPublisher
from nymph_toolkit.diagnostics._viewer import View
from tests.doubles.integration import KEY
from tests.doubles.scenario import invoke, make_group, until

STAMP = datetime(2026, 11, 28, tzinfo=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def report(run_id="a" * 32, sequence=1, **extra):
    return dict(version=1, module_id="weather", run_id=run_id, sequence=sequence, reported_at=STAMP,
                resources=[], outputs=[], **extra)


class ContractTests(unittest.TestCase):
    def test_report_limits_and_bad_types(self):
        value = report()
        value["outputs"] = [{"id": f"x{index}", "label": "日本語",
                             "kind": "text", "observed_at": STAMP, "content": "x"}
                            for index in range(16)]
        used = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        remaining = 16384 - used
        for entry in value["outputs"]:
            additional = min(1022, remaining)
            entry["content"] += "x" * additional
            remaining -= additional
        self.assertEqual(remaining, 0)
        self.assertEqual(validate_report(value), value)
        value["outputs"][-1]["content"] += "x"
        with self.assertRaises(ValueError):
            validate_report(value)
        for bad in (report(version_wrong=True), report(sequence=True), report(processing={"accepting": True, "active": -1})):
            with self.assertRaises(ValueError):
                validate_report(bad)

    def test_internal_output_can_have_an_expiry_without_external_source(self):
        value = report()
        value["outputs"] = [{"id": "notice", "label": "表示", "kind": "text", "content": "",
                             "observed_at": STAMP, "expires_at": "2026-11-28T00:00:01.000Z"}]
        self.assertEqual(validate_report(value), value)
        value["outputs"][0]["expires_at"] = STAMP
        with self.assertRaises(ValueError):
            validate_report(value)

    def test_stall_terminal_and_history(self):
        view = View(lambda _: None)
        view.apply({"type": "update", "state": "running", "changes": {}, "events": range(201), "terminal": {}})
        view.last_pulse -= 3.1
        read = json.loads(view.snapshot(None))
        self.assertTrue(read["stalled"])
        self.assertEqual(read["events"], list(range(1, 201)))
        self.assertEqual(json.loads(view.snapshot(read["revision"]))["events"], [])
        view.apply({"type": "update", "state": "failed", "changes": {}, "events": [], "terminal": {"x": {"state": "failed"}}})
        view.last_pulse -= 3.1
        read = json.loads(view.snapshot(None))
        self.assertFalse(read["stalled"])
        self.assertEqual(read["terminal"]["x"]["state"], "failed")


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_coalesces_and_does_not_retry_failure(self):
        calls = deque()

        class Client:
            async def bind(self, *args, **kwargs):
                pass

            async def invoke(self, key, op, item, *, timeout):
                calls.append((asyncio.get_running_loop().time(), item))
                if len(calls) == 1:
                    raise TimeoutError

        publisher = ReportPublisher(Client(), module_id="weather", slot="weather", run_id="a" * 32)
        self.addAsyncCleanup(publisher.close)
        publisher.update(condition={"level": "info", "label": "初回"})
        await until(lambda: len(calls) == 1)
        publisher.update(condition={"level": "info", "label": "途中"})
        publisher.update(condition={"level": "info", "label": "最新"})
        await until(lambda: len(calls) == 2)
        self.assertGreaterEqual(calls[1][0] - calls[0][0], 1)
        self.assertEqual(calls[1][1]["condition"]["label"], "最新")
        self.assertEqual([row[1]["sequence"] for row in calls], [1, 2])


async def fetch(url, *, body=None, headers=None):
    def get():
        with urlopen(Request(url, data=body, headers=headers or {}), timeout=4) as reply:
            return json.loads(reply.read())

    return await asyncio.to_thread(get)


class ViewerTests(unittest.IsolatedAsyncioTestCase):
    async def test_reports_across_placements_console_and_failure_isolation(self):
        for placement in Placement:
            with self.subTest(placement=placement), TemporaryDirectory() as directory:
                group, runtime, session = configure(Path(directory), placement=placement)
                try:
                    url = await session.start()
                    self.assertIsNotNone(url)
                    await runtime.start()
                    await until(lambda: session.report_count == 1)
                    actual = session._reports["weather"]
                    self.assertEqual(actual["processing"], {"accepting": True, "active": 0, "capacity": 1})
                    self.assertEqual(actual["outputs"][0]["content"][0]["value"], "東京")
                    result = await session._query("status", {})
                    self.assertEqual(result, {"status": "completed", "values": {"observations": 1}})
                    self.assertEqual(await session._query("unknown", {}), {"status": "invalid"})
                    self.assertEqual(await session._query("status", {"no": "x"}), {"status": "invalid"})
                    outcomes = [session.accept_report("weather", report(session.run_id, number))["status"]
                                for number in (3, 2, 3, 4)]
                    self.assertEqual(outcomes, ["accepted", "stale_report", "stale_report", "accepted"])
                    self.assertEqual(session.accept_report("weather", report(sequence=100))["status"], "stale_report")
                    wrong = dict(report(session.run_id, 50), module_id="other")
                    self.assertEqual(session.accept_report("weather", wrong)["status"], "invalid_report")
                    await asyncio.sleep(1.05)
                    view = await fetch(url + "api/snapshot")
                    self.assertEqual(view["changes"]["reports"]["weather"]["sequence"], 4)
                    self.assertEqual(view["changes"]["modules"]["weather"]["placement"], placement.value)
                    self.assertNotIn("weather", view["terminal"])
                    again = await fetch(url + "api/snapshot?since=" + str(view["revision"]))
                    self.assertFalse(again["reset"])
                    if placement is Placement.PROCESS:
                        group.modules["weather"].process.kill()
                        with self.assertRaises(RuntimeFailure):
                            await runtime.wait()
                        await asyncio.sleep(1.05)
                        view = await fetch(url + "api/snapshot")
                        self.assertEqual(view["state"], "failed")
                        self.assertIn("weather", view["terminal"])
                    else:
                        await session.close()
                        self.assertEqual(runtime.state.value, "running")
                        self.assertTrue(group.connections.store.admitting)
                finally:
                    try:
                        await runtime.stop()
                    except RuntimeFailure:
                        if placement is Placement.LOCAL:
                            raise
                    finally:
                        await session.close()

    async def test_real_runtime_transitions_use_safe_projection(self):
        with TemporaryDirectory() as directory:
            group, runtime = make_group(Path(directory), Placement.LOCAL, Placement.LOCAL)
            session = DiagnosticSession(group, runtime)
            try:
                url = await session.start()
                await runtime.start()
                await invoke(group, "requester", "connect", "provider")
                client = group.client("requester")
                activity_key = ActivityKey("requester", "arrives")
                request = ActivityRequest(activity_key, "private-business-text", None, timedelta(seconds=.05))
                await client.submit_remote(request, "provider", "work", None, timeout=5)
                await until(lambda: group.activities.snapshot(activity_key).planned_end_notified)
                self.assertEqual(group.activities.snapshot(activity_key).state.value, "running")
                await client.activity("finish", activity_key, timeout=5)
                await client.activity("wait", activity_key, timeout=5)

                link = BindingKey("requester", KEY)
                group.connections.report_link_error(link, ValueError("private-exception-text"))
                self.assertEqual(session._changes["connections"]["requester/validation.probe/1"]["state"], "checking")
                await until(lambda: not session._checking)

                await asyncio.sleep(1.05)
                view = await fetch(url + "api/snapshot")
                self.assertEqual(view["changes"]["usage"]["provider"]["active"], 0)
                self.assertIn("requester/arrives", view["changes"]["activities"])
                activity = view["changes"]["activities"]["requester/arrives"]
                for key in ("planned_start_at", "planned_end_at", "started_at", "ended_at"):
                    self.assertIsNotNone(activity[key])
                self.assertTrue(activity["planned_end_notified"])
                kinds = {entry["kind"] for entry in view["events"]}
                self.assertTrue({"link_error", "health_requested", "health_completed"} <= kinds)
                self.assertNotIn("private-", json.dumps(view))
                self.assertEqual(view["changes"]["reports"], {})
            finally:
                try:
                    await runtime.stop()
                finally:
                    await session.close()
