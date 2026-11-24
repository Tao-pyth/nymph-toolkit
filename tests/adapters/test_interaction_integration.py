"""B04 full public flows, both transports and process placements, actual console."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from nymph_toolkit.contracts import OperationFailure, Placement
from nymph_toolkit.contracts.memory import MEMORY_KEY
from nymph_toolkit.contracts.text_interaction import TEXT_INTERACTION_KEY
from nymph_toolkit.contracts.web import WEB_KEY
from nymph_toolkit.core import Runtime
from examples.interaction_setup import group_at
from tests.adapters.test_web import request, server


class InteractionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_placements_direct_and_core_routes_web_teaching_correction_restart(self):
        with server() as (http, base):
            for inputs in Placement:
                for storage in Placement:
                    with self.subTest(inputs=inputs,storage=storage), tempfile.TemporaryDirectory() as directory:
                        root = Path(directory).resolve()
                        before = None
                        for restored in (False,True):
                            group = group_at(root,inputs=inputs,storage=storage,allowed_origins=[base])
                            runtime = Runtime(group); await runtime.start()
                            try:
                                client = group.client("requester")
                                for key, provider in ((WEB_KEY,"web"),(TEXT_INTERACTION_KEY,"text"),(MEMORY_KEY,"memory")):
                                    await client.bind(key,provider,timeout=5)
                                web = await client.prepare(WEB_KEY,timeout=5)
                                try:
                                    saved = await web.acall("ingest",request(base+"/plain"),timeout=10)
                                    self.assertIsInstance(saved,dict,repr(saved))
                                finally: await web.close()
                                memory = await client.invoke(MEMORY_KEY,"get","web-one",timeout=5)
                                if before is not None: self.assertEqual(memory,before)
                                before = memory
                                if not restored:
                                    unknown = await client.invoke(TEXT_INTERACTION_KEY,"inspect","猫",timeout=5)
                                    self.assertFalse(unknown["known"])  # acquiring text did not implicitly learn
                                    learned = await client.invoke(TEXT_INTERACTION_KEY,"learn","web-one",tokens=["猫","は","眠る"],concepts=["wrong"],timeout=10)
                                    self.assertIsInstance(learned,dict,repr(learned))
                                text = await client.prepare(TEXT_INTERACTION_KEY,timeout=5)
                                try:
                                    fixed = await text.acall("correct","web-one",command_id="correction",expected_revision=0,tokens=["猫","は","眠る"],concepts=["animal","sleep"],timeout=10)
                                    self.assertEqual(fixed["revision"],1)
                                    state = await text.acall("inspect","猫",timeout=5)
                                    self.assertEqual([v["label"] for v in state["concepts"]],["animal","sleep"])
                                    self.assertEqual(state["count"],1)
                                    conflict = await text.acall("correct","web-one",command_id="stale",expected_revision=0,tokens=["猫","は","眠る"],concepts=[],timeout=10)
                                    self.assertIsInstance(conflict,OperationFailure)
                                    self.assertEqual(conflict.code,"cognition.revision_conflict")
                                    local = dict(before,record_id="dialog",source="console:user",content="犬 は 遊ぶ")
                                    del local["sequence"],local["stored_at"]
                                    observed = await text.acall("observe",local,timeout=10)
                                    self.assertIsInstance(observed,dict,repr(observed))
                                finally: await text.close()
                                self.assertEqual(await client.invoke(MEMORY_KEY,"get","web-one",timeout=5),before)
                            finally: await runtime.stop()
                            self.assertTrue(all(group.process(n).cleanup_confirmed for n in group.modules))
                        await asyncio.sleep(0)
                        self.assertFalse([t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()])
            self.assertEqual(http.calls,["/plain"]*8)


class ConsoleTests(unittest.TestCase):
    def test_actual_json_lines_console_observe_learn_correct_inspect_and_clean_eof(self):
        record = dict(record_id="lesson",kind="experience",content="猫 は 眠る",source_kind="reported",source="user:test",occurred_at="2026-11-24T00:00:00Z")
        commands = [
            "invalid JSON", json.dumps(dict(operation="inspect",args=[])),
            json.dumps(dict(operation="observe",args=[record])),
            json.dumps(dict(operation="inspect",args=["猫"])),
            json.dumps(dict(operation="learn",args=["lesson"],kwargs=dict(tokens=["猫","は","眠る"],concepts=["wrong"]))),
            json.dumps(dict(operation="correct",args=["lesson"],kwargs=dict(command_id="fix",expected_revision=0,tokens=["猫","は","眠る"],concepts=["sleep"]))),
            json.dumps(dict(operation="get_revision",args=["lesson"])),
            json.dumps(dict(operation="inspect",args=["猫"])),
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable,"-W","error","examples/text_interaction_demo.py","--interactive","--data-dir",directory],input="\n".join(commands)+"\n",encoding="utf-8",capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stderr,"")
            rows = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(rows),len(commands))
            self.assertEqual(rows[0]["error"],"JSONDecodeError")
            self.assertEqual(rows[1]["error"],"ValueError")
            self.assertFalse(rows[3]["known"])
            self.assertEqual(rows[5]["revision"],1)
            self.assertEqual(rows[6]["concepts"],["sleep"])
            self.assertEqual(rows[7]["concepts"][0]["label"],"sleep")
            self.assertTrue((Path(directory)/"cognition.db").is_file())
