"""Optional localhost Runtime diagnostics with an explicit synthetic weather report."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from nymph_toolkit.contracts import (
    ActivityKey, ActivityRequest, ContractKey, ContractSpec, HybridSettings, ModuleAdvertisement,
    ModuleKind, ModuleSpec, OperatingState, OperationMode, OperationSpec, Placement, RuntimeState, Usage,
)
from nymph_toolkit.core import FileStore, HybridGroup, Runtime
from nymph_toolkit.diagnostics import BrowserLauncher, ConsoleQuery, DiagnosticSession, ReportPublisher

WEATHER = ContractSpec(ContractKey("example.diagnostics.weather", "1"), (OperationSpec("status", OperationMode.ASYNC),))


def _stamp(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Weather:
    def __init__(self, context, config):
        self.context, self.config = context, config
        self.publisher = None
        context.provide(WEATHER.key, {"status": self.status})

    async def status(self):
        return {"observations": 1, "provider": "fixture"}

    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 1)
        await self.context.core.publish_usage(usage, contracts={WEATHER.key: usage})

    async def run(self):
        if not self.config.get("report"):
            await asyncio.Event().wait()
            return
        self.publisher = ReportPublisher(self.context.core, **self.config["report"])
        sequence = 0
        while True:
            now = datetime.now(timezone.utc)
            self.publisher.update(
                condition={"level": "info", "label": "固定教材を表示"},
                processing={"accepting": True, "active": 0, "capacity": 1},
                resources=[{"id": "samples", "label": "試験用データ", "kind": "memory", "unit": "items",
                            "used": 1, "limit": 4}],
                outputs=[{"id": "forecast", "label": "天気情報", "kind": "items", "observed_at": _stamp(now),
                          "source": "固定サンプル", "expires_at": _stamp(now + timedelta(seconds=30)),
                          "content": [{"label": "地域", "value": "東京"},
                                      {"label": "気温", "value": 21 + (sequence % 2), "unit": "°C"}]}],
            )
            if not self.config.get("repeat"):
                await asyncio.Event().wait()
                return
            sequence += 1
            await asyncio.sleep(.1)

    async def stop(self):
        if self.publisher is not None:
            await self.publisher.close()


def weather_factory(context, config):
    return Weather(context, config)


def add_weather(group, settings=None, *, placement=Placement.LOCAL, repeat=False):
    group.register_module(ModuleSpec("weather", ModuleKind.ADAPTER, ()),
                          ModuleAdvertisement("weather", "example-1", (WEATHER,)),
                          "examples.runtime_diagnostics_demo:weather_factory",
                          {"report": settings, "repeat": repeat}, placement)


def demo_group(root):
    store = FileStore(root / "history", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.05)
    return HybridGroup(HybridSettings(10, 3, 5, 65536, 16, 4), store)


def configure(root, *, placement=Placement.LOCAL):
    group = demo_group(root)
    runtime = Runtime(group)
    query = ConsoleQuery("天気サンプルの状態を照会", "weather", WEATHER.key, "status", ("observations",))
    session = DiagnosticSession(group, runtime, slots={"weather": "weather"}, queries={"status": query})
    add_weather(group, session.report_settings("weather"), placement=placement)
    return group, runtime, session


async def demo(seconds, external_browser):
    with TemporaryDirectory(prefix="ntk-diagnostics-demo-") as work:
        _, runtime, session = configure(Path(work))
        try:
            url = await session.start()
            if url is None:
                raise RuntimeError("The local diagnostic process could not start")
            await runtime.start()
            print(url, flush=True)
            if external_browser:
                import webbrowser
                await asyncio.to_thread(webbrowser.open, url)
            await asyncio.sleep(seconds)
            await runtime.stop()
        finally:
            try:
                await runtime.stop()
            finally:
                await session.close()


class SampleModule:
    def __init__(self, context, config):
        if config["worker"]:
            context.provide_executor("batches", self.batches, supports_pause=True)

    async def start(self):
        pass

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass

    async def batches(self, activity, arguments):
        count = checksum = 0
        while await activity.checkpoint() is None:
            first = count * 1000
            checksum ^= sum(value * value for value in range(first, first + 1000))
            count += 1
            await asyncio.sleep(.25)
        return {"batches": count, "checksum": checksum}


def sample_factory(context, config):
    return SampleModule(context, config)


async def launcher_demo(seconds, external_browser):
    with TemporaryDirectory(prefix="ntk-browser-launcher-") as work:
        group = demo_group(Path(work))
        for name, placement in (("nymph", Placement.LOCAL), ("worker", Placement.PROCESS)):
            group.register_module(ModuleSpec(name, ModuleKind.SUBSYSTEM), ModuleAdvertisement(name, "demo-1", ()),
                                  "examples.runtime_diagnostics_demo:sample_factory", {"worker": name == "worker"},
                                  placement)
        manager = group.enable_activities(clock_check_interval=.1, max_running=1)
        launcher = BrowserLauncher(group, owner_id="nymph")
        try:
            url = await launcher.open()
            if url is None:
                raise RuntimeError("The local launcher could not start")
            print(url, flush=True)
            if external_browser:
                import webbrowser
                await asyncio.to_thread(webbrowser.open, url)
            async with asyncio.timeout(seconds):
                while launcher.runtime.state in (RuntimeState.NEW, RuntimeState.STARTING):
                    await asyncio.sleep(.05)
                if launcher.runtime.state != RuntimeState.RUNNING:
                    await launcher.runtime.wait()
                    return
                key = ActivityKey("nymph", "sample-batches")
                start = datetime.now(timezone.utc) + timedelta(seconds=3)
                manager.submit_remote(ActivityRequest(key, "Generated batches", start, timedelta(minutes=2)),
                                      "worker", "batches")
                await launcher.runtime.wait()
        except TimeoutError:
            pass
        finally:
            await launcher.close()


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--open", action="store_true", help="Open the system browser")
    parser.add_argument("--launcher", action="store_true", help="Include explicit browser Runtime and activity controls")
    args = parser.parse_args()
    if not 0 <= args.seconds <= 3600:
        parser.error("--seconds must be between 0 and 3600")
    run = launcher_demo if args.launcher else demo
    asyncio.run(run(args.seconds, args.open))


if __name__ == "__main__":
    main()
