"""Explicit live Discord observation after operator-confirmed notice and consent."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, OperatingState, Placement, Usage
from nymph_toolkit.contracts.voice import VOICE_CONTRACT, VOICE_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime


class Requester:
    def __init__(self, context): self.context = context
    async def start(self): await self.context.core.publish_usage(Usage(OperatingState.RUNNING, True, 0, 32))
    async def run(self): await asyncio.Event().wait()
    async def stop(self): pass


def requester(context, config): return Requester(context)


def check_credential(config):
    """Check local input without connecting or including a secret in errors."""
    name = config.get("token_env") if isinstance(config, dict) else None
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
        raise ValueError("token_env must be an environment-variable name, never a token")
    token = os.environ.get(name)
    if not token or len(token) > 4096:
        raise ValueError("Set the Bot token in the configured token_env variable in this shell before running; "
                         "the value must be nonempty and at most 4096 characters. Never share the token.")


async def capture(config, consent, *, seconds, placement, via_core, show_text):
    check_credential(config)
    with tempfile.TemporaryDirectory(prefix="ntk-voice-session-") as directory:
        root = Path(directory).resolve()
        group = HybridGroup(HybridSettings(60, 30, 60, 65536, 32, 4),
                            FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.1))
        group.register_module(ModuleSpec("voice", ModuleKind.ADAPTER), ModuleAdvertisement("voice", "1.10.0", (VOICE_CONTRACT,)),
                              "nymph_toolkit.adapters.discord_voice:factory", config, placement)
        group.register_module(ModuleSpec("observer", ModuleKind.SUBSYSTEM, ("voice",)), ModuleAdvertisement("observer", "example", ()),
                              __name__ + ":requester", {}, Placement.LOCAL)
        runtime, link = Runtime(group), None
        session_id, count = "voice-" + uuid4().hex, 0
        await runtime.start()
        try:
            client = group.client("observer")
            await client.bind(VOICE_KEY, "voice", timeout=10)
            link = await client.prepare(VOICE_KEY, timeout=10)
            async def call(name, *args, **kwargs):
                if via_core: return await client.invoke(VOICE_KEY, name, *args, **kwargs, timeout=40)
                return await link.acall(name, *args, **kwargs, timeout=40)
            status = await call("start_session", session_id, consent)
            if not isinstance(status, dict) or status.get("state") != "listening":
                raise RuntimeError("Voice session did not start: " + repr(status))
            print("Voice observation started; no raw audio or transcript is saved by this example.")
            end, after = asyncio.get_running_loop().time() + seconds, 0
            try:
                while asyncio.get_running_loop().time() < end:
                    page = await call("read", session_id, after=after)
                    if not isinstance(page, dict): raise RuntimeError("Voice read failed")
                    for item in page["observations"]:
                        after = item["sequence"]
                        count += 1
                        if show_text:
                            print(json.dumps(item, ensure_ascii=False))
                        else:
                            print(json.dumps(dict(sequence=after, duration_seconds=item["features"]["duration_seconds"],
                                                  word_count=len(item["asr"]["words"]))))
                    if page["state"] != "listening": break
                    if page["next_after"] is None: await asyncio.sleep(.1)
            finally:
                status = await call("stop_session", session_id)
                print(json.dumps(status, ensure_ascii=False))
                if not isinstance(status, dict) or not status.get("cleanup_confirmed"):
                    raise RuntimeError("Voice cleanup was not confirmed")
        finally:
            if link is not None: await link.close()
            await runtime.stop()
        for name in group.modules:
            if not group.process(name).cleanup_confirmed: raise RuntimeError("Runtime cleanup was not confirmed")
        print(f"Received observations: {count}; helper and Runtime cleanup confirmed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Local configuration containing token_env NAME, never the token")
    parser.add_argument("--consent", required=True, type=Path, help="Operator-verified notice and participant consent references")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--placement", choices=[p.value for p in Placement], default="process")
    parser.add_argument("--via-core", action="store_true")
    parser.add_argument("--show-text", action="store_true", help="Print observations to your terminal; you control retention of returned copies")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600: parser.error("--seconds must be 1..600")
    config, consent = (json.loads(path.read_text(encoding="utf-8")) for path in (args.config, args.consent))
    try:
        check_credential(config)
    except ValueError as error:
        parser.error(str(error))
    asyncio.run(capture(config, consent, seconds=args.seconds, placement=Placement(args.placement), via_core=args.via_core, show_text=args.show_text))


if __name__ == "__main__": main()
