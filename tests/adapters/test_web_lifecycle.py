"""Web workers finish before adapter shutdown, including cancelled callers."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nymph_toolkit.adapters.web import factory
from nymph_toolkit.contracts import OperationFailure, TemporaryUnavailable
from tests.adapters.test_text_interaction import FakeCore
from tests.adapters.test_web import request


class WebLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_during_acquisition_and_stop_wait_for_worker_and_admitted_put(self):
        core = FakeCore()
        context = SimpleNamespace(core=core,settings=SimpleNamespace(max_frame_bytes=65536),provide=lambda k,h:None)
        adapter = factory(context,dict(memory_module_id="memory",allowed_origins=["http://example.com"]))
        await adapter.start()
        entered, release = threading.Event(), threading.Event()
        captured = []
        def reader(value, allowed):
            captured.append(value); entered.set()
            if not release.wait(5): raise TimeoutError("test fixture not released")
            return {"example":"record"}
        try:
            with patch("nymph_toolkit.adapters.web.read_record",side_effect=reader):
                value = request("http://example.com/page")
                pending = asyncio.create_task(adapter.ingest(value))
                async with asyncio.timeout(3):
                    while not entered.is_set(): await asyncio.sleep(.001)
                value["url"] = "http://elsewhere.invalid"
                self.assertEqual(captured[0]["url"],"http://example.com/page")
                self.assertIsInstance(await adapter.ingest(value),TemporaryUnavailable)
                pending.cancel()
                stopping = asyncio.create_task(adapter.stop())
                await asyncio.sleep(0)
                self.assertFalse(pending.done()); self.assertFalse(stopping.done())
                release.set()
                with self.assertRaises(asyncio.CancelledError): await pending
                await stopping
        finally:
            release.set(); await adapter.stop()
        self.assertEqual(len(core.calls),1)  # cancellation did not promise 'not saved'
        self.assertTrue(all(link.closed for link in core.links))
        self.assertIsNone(adapter.pool)
        self.assertFalse(any(t.name.startswith("ntk-web") for t in threading.enumerate()))

    async def test_acquisition_failure_does_not_bind_or_save(self):
        core = FakeCore()
        context = SimpleNamespace(core=core,settings=SimpleNamespace(max_frame_bytes=65536),provide=lambda k,h:None)
        adapter = factory(context,dict(memory_module_id="memory",allowed_origins=["http://example.com"]))
        await adapter.start()
        try:
            result = await adapter.ingest(request("http://elsewhere.invalid/page"))
            self.assertIsInstance(result,OperationFailure)
            self.assertEqual(result.code,"web.origin")
            self.assertEqual(core.calls,[]); self.assertEqual(core.bindings,[])
        finally: await adapter.stop()
