"""B02 input, capacity, ownership and downstream failure boundaries."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nymph_toolkit.adapters.document import factory
from nymph_toolkit.adapters.document._reader import read_record
from nymph_toolkit.contracts import BindingKey, LinkFailure, OperationFailure, OperatingState, OutcomeUnknown, TemporaryUnavailable, Usage
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from nymph_toolkit.subsystems.memory._records import canonical


def request(**changes):
    return dict({"path": "note.md", "record_id": "doc-1", "kind": "knowledge",
                 "source_kind": "reported", "occurred_at": "2026-11-23T09:00:00+09:00"}, **changes)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "note.md"
        self.path.write_bytes(b"# title\r\ntext\n")

    def test_text_provenance_bom_and_memory_contract(self):
        raw = b"\xef\xbb\xbf" + "# 文書\r\n本文\n".encode()
        self.path.write_bytes(raw)
        result = read_record(self.root, request())
        self.assertEqual(result["content"], "# 文書\r\n本文\n")
        self.assertEqual(result["source"], self.path.as_uri() + "#sha256=" + hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["occurred_at"], "2026-11-23T00:00:00+00:00")
        self.assertEqual(result, canonical(result)[0])

    def test_caller_controls_all_memory_kinds_and_sources(self):
        for kind in ("experience", "knowledge"):
            for source in ("observed", "reported", "inferred", "imagined", "dream"):
                value = read_record(self.root, request(kind=kind, source_kind=source))
                self.assertEqual(value["kind"], kind)
                self.assertEqual(value["source_kind"], source)

    def test_invalid_requests_rejected(self):
        inputs = [None, [], {}, dict(request(), unknown="x"), request(record_id=" "),
                  request(record_id="あ" * 43), request(kind="fact"), request(source_kind="truth"),
                  request(occurred_at="2026-11-23"), request(occurred_at="2026-02-30T00:00:00Z"),
                  request(occurred_at="2026-11-23T00:00:00+24:00"), request(record_id="\ud800"),
                  request(path=1), request(path="../note.md"), request(path=str(self.path)), request(path="\x00.md")]
        for value in inputs:
            with self.subTest(value=value):
                self.assertEqual(read_record(self.root, value).code, "document.invalid")

    def test_unsupported_missing_directory_and_root_escape(self):
        (self.root / "folder.md").mkdir()
        for name, code in (("file.pdf", "unsupported"), ("missing.txt", "read"), ("folder.md", "unsupported")):
            self.assertEqual(read_record(self.root, request(path=name)).code, "document." + code)
        with patch.object(Path, "resolve", return_value=self.root.parent / "outside.md"):
            self.assertEqual(read_record(self.root, request()).code, "document.invalid")

    def test_permission_failure(self):
        with patch.object(Path, "open", side_effect=PermissionError):
            self.assertEqual(read_record(self.root, request()).code, "document.read")

    def test_empty_nul_invalid_utf8_and_no_lossy_conversion(self):
        for data in (b"", b" \r\n", b"\xef\xbb\xbf", b"a\x00b", b"\xff"):
            self.path.write_bytes(data)
            with self.subTest(data=data):
                self.assertEqual(read_record(self.root, request()).code, "document.invalid")

    def test_exact_memory_json_limit_and_file_limit(self):
        self.path.write_text("x", encoding="utf-8")
        value = read_record(self.root, request())
        size = len(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii"))
        count = 4096 - size + 1
        self.path.write_bytes(b"x" * count)
        result = read_record(self.root, request())
        self.assertEqual(len(canonical(result)[1]), 4096)
        self.path.write_bytes(b"x" * (count + 1))
        self.assertEqual(read_record(self.root, request()).code, "document.too_large")
        self.path.write_bytes(b"x" * 65537)
        self.assertEqual(read_record(self.root, request()).code, "document.too_large")

    def test_uppercase_txt_and_no_markdown_parsing(self):
        (self.root / "NOTE.TXT").write_text("**literal**", encoding="utf-8")
        self.assertEqual(read_record(self.root, request(path="NOTE.TXT"))["content"], "**literal**")


class FakeCore:
    def __init__(self):
        self.events, self.records = [], []
        self.usage = Usage(OperatingState.RUNNING, True, 0, 1)
        self.failure = None
        self.provider = "memory"

    async def publish_usage(self, usage, **kwargs):
        self.events.append(("usage", usage.active))

    async def candidates(self, *args, **kwargs):
        self.events.append(("candidates",))
        ad = SimpleNamespace(module_id=self.provider, contracts=(MEMORY_CONTRACT,))
        return [SimpleNamespace(advertisement=ad, module_usage=self.usage, contract_usage=self.usage)]

    async def bind(self, key, provider, **kwargs):
        self.events.append(("bind", provider))

    async def prepare(self, *args, **kwargs):
        self.events.append(("prepare",))
        return self

    async def acall(self, operation, value, **kwargs):
        self.events.append(("put",))
        self.records.append(value)
        if isinstance(self.failure, Exception):
            raise self.failure
        if self.failure is not None:
            return self.failure
        return dict(value, sequence=1, stored_at="2026-11-23T00:00:01+00:00")

    async def close(self):
        self.events.append(("close",))

    async def acknowledge_interruption(self, notice_id, **kwargs):
        self.events.append(("ack", notice_id))

    async def health_check(self, **kwargs):
        self.events.append(("health", kwargs["module_ids"]))


class DocumentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "note.md").write_text("document", encoding="utf-8")
        self.core = FakeCore()
        self.context = SimpleNamespace(settings=SimpleNamespace(max_frame_bytes=65536), core=self.core, provide=lambda *args: None)
        self.doc = factory(self.context, {"root": str(self.root), "memory_module_id": "memory"})
        await self.doc.start()
        self.addAsyncCleanup(self.doc.stop)

    async def test_invalid_and_oversize_inputs_never_call_memory(self):
        for value in ({}, request(path="missing.txt"), request(path="x.pdf")):
            self.assertIsInstance(await self.doc.ingest(value), OperationFailure)
        (self.root / "note.md").write_bytes(b"x" * 4096)
        self.assertEqual((await self.doc.ingest(request())).code, "document.too_large")
        self.assertEqual(self.core.records, [])
        self.assertNotIn(("candidates",), self.core.events)

    async def test_selected_provider_and_link_reused_without_reselection(self):
        self.core.provider = "other"
        self.assertIsInstance(await self.doc.ingest(request()), TemporaryUnavailable)
        self.assertEqual(self.core.records, [])
        self.core.provider = "memory"
        result = await self.doc.ingest(request())
        self.assertEqual(result["content"], "document")
        self.core.provider = "other"
        await self.doc.ingest(request())
        self.assertEqual(self.core.events.count(("bind", "memory")), 1)
        self.assertEqual(self.core.events.count(("prepare",)), 1)

    async def test_memory_capacity_and_business_failure_are_not_link_errors(self):
        self.core.usage = Usage(OperatingState.RUNNING, True, 1, 1)
        self.assertIsInstance(await self.doc.ingest(request()), TemporaryUnavailable)
        self.assertEqual(self.core.records, [])
        self.core.usage = Usage(OperatingState.RUNNING, True, 0, 1)
        for failure in (TemporaryUnavailable("busy"), OperationFailure("memory.storage", "failed")):
            self.core.failure = failure
            self.assertEqual(await self.doc.ingest(request()), failure)
        self.assertFalse(any(e[0] == "health" for e in self.core.events))

    async def test_link_failure_cleanup_ack_health_and_no_replay(self):
        self.core.failure = LinkFailure(BindingKey("document", MEMORY_KEY), RuntimeError("broken"), 7)
        result = await self.doc.ingest(request())
        self.assertIsInstance(result, LinkFailure)
        events = self.core.events
        self.assertLess(events.index(("close",)), events.index(("ack", 7)))
        self.assertLess(events.index(("ack", 7)), events.index(("health", ("memory",))))
        self.assertEqual(len(self.core.records), 1)
        self.core.failure = None
        await self.doc.ingest(request())
        self.assertEqual(events.count(("bind", "memory")), 1)
        self.assertEqual(events.count(("prepare",)), 2)

    async def test_unknown_outcome_remains_unknown_without_replay(self):
        self.core.failure = OutcomeUnknown(42)
        with self.assertRaises(OutcomeUnknown):
            await self.doc.ingest(request())
        self.assertEqual(len(self.core.records), 1)
        self.assertIn(("health", ("memory",)), self.core.events)

    async def test_health_failure_does_not_mask_unknown_write_outcome(self):
        self.core.failure = OutcomeUnknown(42)
        async def failed_health(**kwargs):
            raise RuntimeError("health unavailable")
        self.core.health_check = failed_health
        with self.assertRaises(OutcomeUnknown) as caught:
            await self.doc.ingest(request())
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)
        self.assertEqual(len(self.core.records), 1)

    async def test_idle_notification_failure_preserves_unknown_outcome(self):
        original = OutcomeUnknown(42)
        notification_error = RuntimeError("idle usage transport failed")
        publish = self.core.publish_usage
        async def failed_idle(usage, **kwargs):
            if usage.active == 0:
                raise notification_error
            await publish(usage, **kwargs)
        self.core.publish_usage = failed_idle
        self.core.failure = original
        with self.assertRaises(OutcomeUnknown) as caught:
            await self.doc.ingest(request())
        self.assertIs(caught.exception, original)
        self.assertIs(caught.exception.__cause__, notification_error)
        self.assertEqual(len(self.core.records), 1)
        self.assertIn(("close",), self.core.events)
        self.assertIn(("health", ("memory",)), self.core.events)
        self.assertFalse(self.doc.busy)
        self.assertIsNone(self.doc.link)
        # A standalone notification failure remains observable too.
        self.core.failure = None
        with self.assertRaises(RuntimeError) as standalone:
            await self.doc.ingest(request())
        self.assertIs(standalone.exception, notification_error)
        self.assertEqual(len(self.core.records), 2)
        self.assertFalse(self.doc.busy)

    async def test_cancel_stop_and_capacity_wait_for_owned_reader(self):
        entered, release = threading.Event(), threading.Event()
        original = read_record
        def slow(root, value):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test gate timed out")
            return original(root, value)
        with patch("nymph_toolkit.adapters.document.read_record", side_effect=slow):
            value = request()
            call = asyncio.create_task(self.doc.ingest(value))
            async with asyncio.timeout(3):
                while not entered.is_set():
                    await asyncio.sleep(.001)
            value["record_id"] = "mutated"
            self.assertIsInstance(await self.doc.ingest(request()), TemporaryUnavailable)
            call.cancel()
            await asyncio.sleep(0)
            call.cancel()
            stop = asyncio.create_task(self.doc.stop())
            await asyncio.sleep(.02)
            self.assertFalse(call.done())
            self.assertFalse(stop.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await call
            await stop
        self.assertEqual(self.core.records[0]["record_id"], "doc-1")
        self.assertIsNone(self.doc.pool)
        self.assertIsInstance(await self.doc.ingest(request()), TemporaryUnavailable)
        self.assertFalse(self.doc.busy)

    async def test_start_failure_and_repeated_stop_release_pool(self):
        doc = factory(self.context, {"root": str(self.root / "missing"), "memory_module_id": "memory"})
        with self.assertRaises(OSError):
            await doc.start()
        await doc.stop()
        self.assertIsNone(doc.pool)
        for config in ({}, {"root": "relative", "memory_module_id": "memory"}, {"root": str(self.root), "memory_module_id": " "}):
            with self.assertRaises(ValueError):
                factory(self.context, config)
