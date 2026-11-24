"""Run a bounded demonstration or a JSON-lines teaching console (--interactive)."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
from concurrent.futures import Future
from contextlib import nullcontext
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import sys
import tempfile
import threading

from nymph_toolkit.contracts.text_interaction import TEXT_INTERACTION_KEY
from nymph_toolkit.core import Runtime

if __package__:
    from .interaction_setup import group_at
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from interaction_setup import group_at


def decode_command(line):
    command = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Finite JSON values required")))
    if type(command) is not dict or set(command) - {"operation","args","kwargs"}:
        raise ValueError("Command requires operation and optional args/kwargs")
    operation = command.get("operation")
    schema = {"observe":(set(),set()),"learn":({"tokens","concepts"},{"tokens","concepts"}),
              "inspect":(set(),{"source_kind","after","limit"}),"get_revision":(set(),set()),
              "correct":({"command_id","expected_revision","tokens","concepts"},{"command_id","expected_revision","tokens","concepts"})}
    if type(operation) is not str or operation not in schema:
        raise ValueError("Unsupported operation")
    args, kwargs = command.get("args",[]), command.get("kwargs",{})
    required, permitted = schema[operation]
    if type(args) is not list or len(args) != 1 or type(kwargs) is not dict or not required <= set(kwargs) <= permitted:
        raise ValueError("Operation requires one positional argument and its declared keyword arguments")
    return operation,args,kwargs


class ConsoleHost:
    """Keep stdin on the main thread, so waiting for input never stalls Core."""
    def __init__(self, root):
        self.root = root
        self.started, self.completed = Future(), Future()
        self.thread = threading.Thread(target=self._run, name="ntk-console-runtime")

    def _run(self):
        try:
            asyncio.run(self._serve())
        except BaseException as error:
            if not self.started.done(): self.started.set_exception(error)
            self.completed.set_exception(error)
        else:
            self.completed.set_result(None)

    async def _serve(self):
        self.loop, self.finish = asyncio.get_running_loop(), asyncio.Event()
        group = group_at(self.root)
        runtime = Runtime(group)
        try:
            await runtime.start()
            self.client = group.client("requester")
            await self.client.bind(TEXT_INTERACTION_KEY,"text",timeout=5)
            self.started.set_result(None)
            await self.finish.wait()
        finally:
            await runtime.stop()
        if not all(group.process(name).cleanup_confirmed for name in group.modules):
            raise RuntimeError("Runtime cleanup was not confirmed")

    def __enter__(self):
        self.thread.start()
        try:
            self.started.result(timeout=45)
        except BaseException:
            if self.started.done(): self.thread.join()
            else: self.loop.call_soon_threadsafe(self.finish.set)
            raise
        return self

    def call(self, command):
        operation,args,kwargs = decode_command(command)
        future = asyncio.run_coroutine_threadsafe(self.client.invoke(TEXT_INTERACTION_KEY,operation,*args,**kwargs,timeout=10),self.loop)
        return future.result(timeout=15)

    def __exit__(self, *exc):
        self.loop.call_soon_threadsafe(self.finish.set)
        self.thread.join()
        self.completed.result()


def json_default(value):
    if is_dataclass(value): return {"type":type(value).__name__,**asdict(value)}
    raise TypeError("Unsupported result type")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive",action="store_true",help="Read JSON commands from stdin until EOF; output one JSON result per line")
    parser.add_argument("--data-dir",type=Path,help="Persistent directory; otherwise an explicitly temporary demo is used")
    options = parser.parse_args()
    if options.data_dir is not None and not options.interactive:
        parser.error("--data-dir requires --interactive; the default demonstration uses temporary data")
    if options.data_dir is not None: options.data_dir.mkdir(parents=True,exist_ok=True)
    storage = nullcontext(str(options.data_dir)) if options.data_dir is not None else tempfile.TemporaryDirectory(prefix="ntk-text-demo-")
    with storage as directory, ConsoleHost(Path(directory).resolve()) as host:
        if options.interactive:
            for line in sys.stdin:
                try:
                    result = host.call(line)
                except Exception as error:
                    result = {"error":type(error).__name__,"message":str(error)}
                print(json.dumps(result,ensure_ascii=True,default=json_default),flush=True)
        else:
            record = dict(record_id="lesson",kind="experience",content="猫 は 眠る",source_kind="reported",source="console:teacher",occurred_at="2026-11-24T00:00:00Z")
            commands = [
                dict(operation="observe",args=[record]),
                dict(operation="learn",args=["lesson"],kwargs=dict(tokens=["猫","は","眠る"],concepts=["wrong"])),
                dict(operation="inspect",args=["猫"]),
                dict(operation="correct",args=["lesson"],kwargs=dict(command_id="fix",expected_revision=0,tokens=["猫","は","眠る"],concepts=["animal","sleep"])),
                dict(operation="get_revision",args=["lesson"]),
            ]
            results = [host.call(json.dumps(command)) for command in commands]
            assert all(isinstance(value,dict) for value in results), results
            assert results[2]["concepts"][0]["label"] == "wrong"
            assert results[-1]["revision"] == 1 and results[-1]["concepts"] == ["animal","sleep"]
            print("PASS: Text observation, explicit teaching, correction and evidence queries")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
