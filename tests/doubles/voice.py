"""Synthetic transport/recognizer at the external boundary; real Voice/Core lifecycle."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import json
from pathlib import Path
import sys

from nymph_toolkit.adapters.discord_voice import factory as voice_factory
from nymph_toolkit.adapters.discord_voice._audio import MODEL_ID, features, mono_pcm, transcript
from nymph_toolkit.contracts import ContractKey, ContractSpec, OperatingState, OperationMode, OperationSpec, Usage
from nymph_toolkit.contracts.voice import VOICE_KEY

CONTROL_KEY = ContractKey("test.voice.control", "1")
CONTROL_CONTRACT = ContractSpec(CONTROL_KEY, (OperationSpec("exercise", OperationMode.ASYNC),))


class Processor:
    def __init__(self, path): self.large = (Path(path) / "large-test").exists()
    def process(self, pcm):
        asr = dict(text="猫", words=[])
        if self.large:
            asr = transcript([json.dumps(dict(text="猫" * 1365, result=[dict(word="word", start=0, end=0, conf=1) for _ in range(256)]))], .1)
        return dict(asr_model=MODEL_ID, asr=asr, features=features(mono_pcm(pcm)),
                    pcm_sha256=hashlib.sha256(pcm).hexdigest(), sample_rate=48000, channels=2)


def factory(context, config):
    service = voice_factory(context, config)
    async def check_node(): pass
    service._check_node = check_node
    service.processor_factory = Processor
    processes = []
    async def spawn():
        process = await asyncio.create_subprocess_exec(sys.executable, "-u", str(Path(__file__).with_name("voice_helper.py")), "normal",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=131072)
        processes.append(process)
        return process
    service.spawn = spawn
    stop = service.stop
    async def observed_stop():
        await stop()
        result = dict(processes=[p.returncode for p in processes], worker_released=service.pool is None,
                      current_released=service.current is None, history_count=len(service.history))
        Path(config["model_path"], "voice-stopped.json").write_text(json.dumps(result), encoding="utf-8")
    service.stop = observed_stop
    return service


class Requester:
    def __init__(self, context):
        self.context = context
        context.provide(CONTROL_KEY, {"exercise": self.exercise})
    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 8)
        await self.context.core.publish_usage(usage, contracts={CONTROL_KEY: usage})
    async def run(self): await asyncio.Event().wait()
    async def stop(self): pass
    async def exercise(self, direct, leave_running):
        client = self.context.core
        await client.bind(VOICE_KEY, "voice", timeout=10)
        link = await client.prepare(VOICE_KEY, timeout=10)
        async def call(name, *args, **kwargs):
            if direct:
                return await link.acall(name, *args, **kwargs, timeout=15)
            return await client.invoke(VOICE_KEY, name, *args, **kwargs, timeout=15)
        try:
            before = await call("status")
            permission = dict(notice_ref="synthetic fixture", participants={"300": "synthetic PCM only"}, retention_seconds=30)
            started = await call("start_session", "one", permission)
            async with asyncio.timeout(15):
                while True:
                    page = await call("read", "one")
                    if page["observations"]: break
                    await asyncio.sleep(.01)
            stopped = None if leave_running else await call("revoke", "one", "300")
            cleared = None if leave_running else await call("read", "one")
            replay = None if leave_running else await call("start_session", "one", permission)
            return dict(before=before, started=started, page=page, stopped=stopped, cleared=cleared, replay=replay)
        finally:
            await link.close()


def requester(context, config): return Requester(context)
