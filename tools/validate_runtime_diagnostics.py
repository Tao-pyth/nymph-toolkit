"""Compare opt-in diagnostics with the existing 4-placement hybrid workload."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
from contextlib import AsyncExitStack
import itertools
import json
from pathlib import Path
import platform
import statistics
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from examples.runtime_diagnostics_demo import add_weather
from nymph_toolkit.contracts import HybridSettings, Placement
from nymph_toolkit.diagnostics import DiagnosticSession
from tests.doubles.measurement import memory
from tests.doubles.scenario import invoke, make_group
from validate_hybrid_load import Samples, source_identity


async def stop_browser(worker):
    worker.stdin.close()
    try:
        async with asyncio.timeout(15):
            await worker.wait()
    except TimeoutError:
        worker.kill()
        await worker.wait()


async def browser(stack, tabs, urls):
    process = await asyncio.create_subprocess_exec(
        "node", str(ROOT / "tools/customer-docs/check-diagnostics.mjs"), "--tabs", str(tabs), *urls,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, cwd=ROOT)
    stack.push_async_callback(stop_browser, process)
    async with asyncio.timeout(70):
        if await process.stdout.readline() != b"ready\n":
            raise RuntimeError("Load browser could not establish its tabs")
    return process


async def workload(group, seconds, *, collect):
    results = Samples()
    sequence = itertools.count()
    start = time.perf_counter()
    deadline = start + seconds
    next_activity = start
    while time.perf_counter() < deadline:
        number = str(next(sequence))
        calls = await invoke(group, "requester", "batch", 4, 2)
        await invoke(group, "requester", "transfer", "diag-" + number, 2, 1024)
        now = time.perf_counter()
        if now >= next_activity:
            await invoke(group, "requester", "activity_cycle", "provider", "diag-" + number + str(start))
            next_activity = now + 1
        if collect:
            results.add(calls)
        await asyncio.sleep(.01)
    elapsed = time.perf_counter() - start
    measured = results.result()
    return {"rpc": measured, "elapsed_seconds": elapsed, "rpc_per_second": measured["count"] / elapsed}


async def condition(tabs, warmup, duration):
    async with AsyncExitStack() as stack:
        root = Path(stack.enter_context(TemporaryDirectory(prefix="ntk-diagnostics-load-")))
        cases, urls = [], []
        for requester, provider in itertools.product(Placement, repeat=2):
            group, runtime = make_group(root / f"{requester}-{provider}", requester, provider, measure=True,
                                        settings=HybridSettings(10, 3, 10, 65536, 32, 8))
            session = DiagnosticSession(group, runtime, slots={"weather": "weather"}) if tabs else None
            if session is not None:
                stack.push_async_callback(session.close)
                address = await session.start()
                if address is None:
                    raise RuntimeError("Diagnostic server unavailable")
                urls.append(address)
            config = None if session is None else session.report_settings("weather")
            add_weather(group, config, placement=provider, repeat=True)
            await runtime.start()
            stack.push_async_callback(runtime.stop)
            await invoke(group, "requester", "connect", "provider")
            cases.append((requester, provider, group, session))
        worker = await browser(stack, tabs, urls) if tabs else None
        await asyncio.gather(*(workload(group, warmup, collect=False) for _, _, group, _ in cases))
        before = time.process_time()
        report_counts = [0 if session is None else session.report_count for _, _, _, session in cases]
        counters = await asyncio.gather(*(workload(group, duration, collect=True) for _, _, group, _ in cases))
        if worker is not None and worker.returncode is not None:
            raise RuntimeError("Load browser ended during measurement")
        cpu = time.process_time() - before
        result = []
        for index, (requester, provider, _, session) in enumerate(cases):
            result.append(dict(counters[index], requester=requester.value, provider=provider.value,
                               reports=0 if session is None else session.report_count - report_counts[index],
                               peak_report_slots=0 if session is None else session.peak_reports))
        return {"tabs": tabs, "parent_cpu_seconds": cpu, "parent_memory": memory(), "cases": result}


def compare(observations):
    results = []
    for index in range(4):
        def statistic(tabs, extract):
            return statistics.median(extract(run["cases"][index]) for run in observations if run["tabs"] == tabs)

        baseline_latency = statistic(0, lambda case: case["rpc"]["window_p95_seconds"])
        baseline_rate = statistic(0, lambda case: case["rpc_per_second"])
        for tabs in (1, 3):
            latency = statistic(tabs, lambda case: case["rpc"]["window_p95_seconds"])
            rate = statistic(tabs, lambda case: case["rpc_per_second"])
            first = observations[0]["cases"][index]
            latency_delta = latency - baseline_latency
            rate_drop = (baseline_rate - rate) / baseline_rate
            results.append({"requester": first["requester"], "provider": first["provider"], "tabs": tabs,
                            "baseline_p95_seconds": baseline_latency, "p95_seconds": latency,
                            "baseline_rpc_per_second": baseline_rate, "rpc_per_second": rate,
                            "p95_delta_seconds": latency_delta, "rpc_rate_drop": rate_drop,
                            "passed": latency_delta <= max(.05 * baseline_latency, .00025) and rate_drop <= .05})
    return results


async def main(args):
    repetitions = 1 if args.smoke else 3
    warmup, duration = (.4, 1.0) if args.smoke else (30, 300)
    output = {"format": "ntk.validation.diagnostics.v1", "source": source_identity(),
              "platform": platform.platform(), "python": platform.python_version(),
              "warmup_seconds": warmup, "duration_seconds": duration, "smoke": args.smoke, "observations": []}
    order = (0, 1, 3)
    try:
        for attempt in range(repetitions):
            for tabs in order[attempt:] + order[:attempt]:
                print(f"LD-09 iteration {attempt + 1}/{repetitions}, tabs={tabs}", flush=True)
                result = await condition(tabs, warmup, duration)
                output["observations"].append(dict(result, iteration=attempt + 1))
        output["comparisons"] = compare(output["observations"])
        output["passed"] = all(case["passed"] for case in output["comparisons"])
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if output["passed"] or args.smoke else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
