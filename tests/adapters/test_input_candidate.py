# SPDX-License-Identifier: Apache-2.0
import asyncio
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from examples.input_candidate_demo import exercise, request, settings
from nymph_toolkit.adapters.input_candidate import _Preparation
from nymph_toolkit.contracts import Placement
from nymph_toolkit.contracts._memory_record import canonical


class Context:
    class Settings:
        max_frame_bytes = 65536

    class Core:
        async def publish_usage(self, *_args, **_kwargs):
            pass

    settings = Settings()
    core = Core()

    def provide(self, _key, _operations):
        pass


class CandidateTests(unittest.IsolatedAsyncioTestCase):
    async def service(self, method, mock=None, **changes):
        service = _Preparation(Context(), dict(settings(method), **changes), mock_api=mock)
        self.addAsyncCleanup(service.stop)
        await service.start()
        return service

    async def test_defaults_preserve_explicit_values_and_report_missing_time(self):
        service = await self.service("defaults")
        value = request("conversation", explicit=False)
        out = await service.prepare(value)
        self.assertEqual(out["provenance"]["kind"], "default")
        self.assertEqual(out["record"]["kind"], "experience")
        value["fields"]["kind"] = "knowledge"
        out = await service.prepare(value)
        self.assertEqual(out["record"]["kind"], "knowledge")
        self.assertEqual(out["provenance"]["kind"], "explicit")
        del value["fields"]["occurred_at"]
        self.assertEqual((await service.prepare(value))["missing"], ["occurred_at"])
        value["fields"]["occurred_at"] = "2026-04-99T12:00:00Z"
        self.assertEqual((await service.prepare(value))["code"], "invalid_input")

    async def test_normalized_limit_and_unicode(self):
        service = await self.service("defaults")
        value = request()
        value["input"]["content"] = "a"
        prepared = await service.prepare(value)
        _, encoded = canonical(prepared["record"])
        value["input"]["content"] += "a" * (4096 - len(encoded))
        self.assertEqual((await service.prepare(value))["status"], "ready")
        value["input"]["content"] += "a"
        self.assertEqual((await service.prepare(value))["code"], "too_large")
        value["input"]["content"] = "\ud800"
        self.assertEqual((await service.prepare(value))["code"], "invalid_input")

    async def test_ai_permissions_and_proposal(self):
        calls = []

        async def mock(**kwargs):
            calls.append(kwargs)
            return {"content": "要約", "kind": "knowledge"}

        service = await self.service("mock_ai", mock)
        value = request(explicit=False)
        permission = value.pop("permission")
        denied = await service.prepare(value)
        self.assertEqual(denied["code"], "send_not_permitted")
        self.assertEqual(calls, [])
        value["permission"] = permission
        asked = await service.prepare(value)
        self.assertEqual(asked["proposals"], {"kind": "knowledge"})
        self.assertEqual(asked["missing"], ["kind", "source_kind"])
        self.assertEqual(asked["model_id"], "fixed-example/1")
        self.assertEqual(calls, [{"content": value["input"]["content"], "operation": "summarize"}])
        approved = await service.prepare(request("conversation"))
        self.assertEqual(approved["record"]["kind"], "experience")
        self.assertEqual(approved["record"]["source"], "sample:conversation")
        self.assertEqual(approved["provenance"]["content"], "ai")

    async def test_timeout_and_invalid_response(self):
        async def slow(**_):
            await asyncio.Event().wait()

        service = await self.service("mock_ai", slow, timeout=.01)
        self.assertEqual((await service.prepare(request()))["code"], "external_processing_failed")
        invalid = await self.service("mock_ai", response={"content": "X", "source": "forged"})
        self.assertEqual((await invalid.prepare(request()))["code"], "external_processing_failed")


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_placement_and_both_paths(self):
        for requester, provider in product(Placement, repeat=2):
            method = "mock_ai" if requester is Placement.PROCESS else "defaults"
            with self.subTest(requester=requester, provider=provider), TemporaryDirectory() as work:
                self.assertEqual(await exercise(Path(work).resolve(), method, requester, provider),
                                 {"method": method, "saved": 3})
