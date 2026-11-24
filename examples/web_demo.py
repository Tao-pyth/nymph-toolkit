"""Acquire an explicit page from an owned HTTP fixture, then teach from its evidence."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading

from nymph_toolkit.contracts import Placement
from nymph_toolkit.contracts.memory import MEMORY_KEY
from nymph_toolkit.contracts.text_interaction import TEXT_INTERACTION_KEY
from nymph_toolkit.contracts.web import WEB_KEY
from nymph_toolkit.core import Runtime

if __package__:
    from .interaction_setup import group_at
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from interaction_setup import group_at


class Page(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        data = '<p>猫 は 眠る</p><script>not observation text</script>'.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)


async def main(base):
    with tempfile.TemporaryDirectory(prefix="ntk-web-demo-") as directory:
        group = group_at(Path(directory).resolve(),inputs=Placement.PROCESS,storage=Placement.LOCAL,allowed_origins=[base])
        runtime = Runtime(group); await runtime.start()
        try:
            client = group.client("requester")
            for key, provider in ((WEB_KEY,"web"),(TEXT_INTERACTION_KEY,"text"),(MEMORY_KEY,"memory")):
                await client.bind(key,provider,timeout=5)
            saved = await client.invoke(WEB_KEY,"ingest",dict(url=base+"/page",record_id="page",kind="experience",source_kind="observed",occurred_at="2026-11-24T00:00:00Z"),timeout=10)
            assert isinstance(saved,dict), repr(saved)
            record = await client.invoke(MEMORY_KEY,"get","page",timeout=5)
            assert record["content"] == "猫 は 眠る", record
            assert json.loads(record["source"])["url"] == base+"/page"
            before = await client.invoke(TEXT_INTERACTION_KEY,"inspect","猫",timeout=5)
            assert not before["known"]
            learned = await client.invoke(TEXT_INTERACTION_KEY,"learn","page",tokens=["猫","は","眠る"],concepts=["sleep"],timeout=10)
            assert isinstance(learned,dict), repr(learned)
            after = await client.invoke(TEXT_INTERACTION_KEY,"inspect","猫",timeout=5)
            assert after["count"] == 1 and after["concepts"][0]["label"] == "sleep"
        finally: await runtime.stop()
        assert all(group.process(name).cleanup_confirmed for name in group.modules)
    print("PASS: Web HTML extraction, provenance, Memory, explicit learning, cleanup")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1",0),Page)
    runner = threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
    runner.start()
    try: asyncio.run(main("http://127.0.0.1:"+str(server.server_port)))
    finally:
        server.shutdown(); server.server_close(); runner.join()
