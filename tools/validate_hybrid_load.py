"""A08 reproducible measurements and bounded traffic; retained history is never pruned."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
# Only validation fixtures are imported here. Installed-wheel checks copy these
# fixtures and this tool outside the checkout; src is never injected into sys.path.
sys.path.insert(0, str(ROOT))
from nymph_toolkit.contracts import HybridSettings, Placement
from tests.doubles.measurement import memory
from tests.doubles.scenario import invoke, make_group, owned_state


class Samples:
    """Bounded measurement reservoir, distinct from NTK's retained activity/history."""
    def __init__(self):
        self.count = 0
        self.total = self.maximum = 0.0
        self.values = []

    def add(self, values):
        for value in values:
            self.count += 1
            self.total += value
            self.maximum = max(self.maximum, value)
            if len(self.values) < 2048:
                self.values.append(value)
            else:
                # A bounded, reproducible rolling window; not a global percentile.
                self.values[(self.count - 1) % 2048] = value

    def result(self):
        ordered = sorted(self.values)
        return {"count": self.count, "mean_seconds": self.total / self.count if self.count else None,
                "maximum_seconds": self.maximum, "window_size": len(ordered),
                "window_median_seconds": statistics.median(ordered) if ordered else None,
                "window_p95_seconds": ordered[math.ceil(len(ordered) * .95) - 1] if ordered else None}


def source_identity():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        return {"commit": None, "dirty": None}
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True)
    return {"commit": result.stdout.strip(), "dirty": bool(status.stdout.strip())}


async def measure(args):
    tracemalloc.start()
    result = {"format": "ntk.validation.load.v1", "at_utc": datetime.now(timezone.utc).isoformat(),
              "source": source_identity(), "environment": {"os": platform.system(), "release": platform.release(),
              "machine": platform.machine(), "python": platform.python_version()},
              "conditions": {key: value for key, value in vars(args).items() if key != "output"},
              "parent_samples": [], "cases": []}
    active = []
    with tempfile.TemporaryDirectory(prefix="ntk-load-") as directory:
        try:
            for requester in Placement:
                for provider in Placement:
                    root = Path(directory) / f"{requester}-{provider}"
                    group, runtime = make_group(root, requester, provider, measure=True,
                        settings=HybridSettings(10, 3, 5, 65536, 32, 8))
                    case = {"requester": requester.value, "provider": provider.value, "cycles": 0,
                            "activities": 0, "bytes": 0, "samples": [], "buffer_peaks": {}}
                    item = (case, group, runtime, root, Samples(), Samples())
                    active.append(item)
                    result["cases"].append(case)
                    started = time.perf_counter()
                    await runtime.start()
                    case["startup_seconds"] = time.perf_counter() - started
                    await invoke(group, "requester", "connect", "provider")
                    first = Samples()
                    first.add(await invoke(group, "requester", "batch", args.requests, args.concurrency))
                    case["initial_rpc"] = first.result()
                    case["initial_transfer"] = await invoke(group, "requester", "transfer", "initial", args.chunks, args.chunk_bytes)

            started = time.perf_counter()
            deadline = started + args.duration
            async def cycle(item):
                case, group, _, _, calls, management = item
                next_activity = started
                while time.perf_counter() < deadline:
                    calls.add(await invoke(group, "requester", "batch", args.cycle_requests, args.concurrency))
                    transfer = await invoke(group, "requester", "transfer", str(case["cycles"]), args.cycle_chunks, args.chunk_bytes)
                    case["bytes"] += transfer["bytes"]
                    management.add(transfer["management_seconds"])
                    for name in ("send_peak_bytes", "send_peak_chunks", "receive_peak_bytes", "receive_peak_chunks"):
                        case["buffer_peaks"][name] = max(case["buffer_peaks"].get(name, 0), transfer[name])
                    if time.perf_counter() >= next_activity:
                        await invoke(group, "requester", "activity_cycle", "provider", str(case["activities"]))
                        case["activities"] += 1
                        next_activity = time.perf_counter() + args.activity_interval
                    case["cycles"] += 1
                    await asyncio.sleep(args.pause)

            async def sample():
                elapsed = time.perf_counter() - started
                result["parent_samples"].append({"elapsed_seconds": elapsed, **memory()})
                for case, group, _, root, _, _ in active:
                    observations = {name: await invoke(group, name, "metrics") for name in ("requester", "provider")}
                    case["samples"].append({"elapsed_seconds": elapsed, "modules": observations,
                        "activities_retained": len(group.activities._activities),
                        "unsaved_events": group.connections.store.unsaved_events,
                        "history_bytes": sum(p.stat().st_size for p in root.rglob("history-*.jsonl"))})
                    for info in observations.values():
                        assert info["data_peers"] <= 1 and info["streams"] <= group.settings.max_streams
                        assert info["pending_rpc"] <= args.concurrency + 1

            workers = [asyncio.create_task(cycle(item), name="validation-load") for item in active]
            try:
                while not all(t.done() for t in workers):
                    await sample()
                    for worker in workers:
                        if worker.done():
                            worker.result()
                    print(json.dumps({"elapsed_seconds": round(time.perf_counter() - started, 2),
                                      "cycles": [item[0]["cycles"] for item in active]}), flush=True)
                    await asyncio.wait(workers, timeout=min(args.sample_interval, max(.01, deadline - time.perf_counter())),
                                       return_when=asyncio.FIRST_EXCEPTION)
                await asyncio.gather(*workers)
            finally:
                for worker in workers:
                    if not worker.done():
                        worker.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
            result["load_seconds"] = time.perf_counter() - started
            assert result["load_seconds"] >= args.duration
            await asyncio.sleep(.05)
            await sample()
            for case, group, runtime, _, calls, management in active:
                case["rpc"] = calls.result()
                case["management"] = management.result()
                case["idle_modules"] = {name: await invoke(group, name, "metrics") for name in ("requester", "provider")}
                for info in case["idle_modules"].values():
                    assert info["pending_rpc"] == info["streams"] == info["owned_tasks"] == info["opening_streams"] == 0
                    assert info["unconsumed_results"] == 0
                assert case["idle_modules"]["provider"]["work_started"] == case["activities"]
                assert case["idle_modules"]["provider"]["work_ended"] == case["activities"]
                assert len(group.activities._activities) == case["activities"]
                before = time.perf_counter()
                await runtime.stop()
                case["shutdown_seconds"] = time.perf_counter() - before
                case["after_stop"] = owned_state(group)
                assert all(value == 0 for value in case["after_stop"].values())
            result["outcome"] = "passed"
        finally:
            for _, _, runtime, _, _, _ in active:
                await runtime.stop()
    return result


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def count(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=positive, default=3)
    parser.add_argument("--requests", type=count, default=200)
    parser.add_argument("--concurrency", type=count, default=4)
    parser.add_argument("--chunks", type=count, default=64)
    parser.add_argument("--chunk-bytes", type=count, default=4096)
    parser.add_argument("--cycle-requests", type=count, default=8)
    parser.add_argument("--cycle-chunks", type=count, default=8)
    parser.add_argument("--pause", type=positive, default=.1)
    parser.add_argument("--activity-interval", type=positive, default=10)
    parser.add_argument("--sample-interval", type=positive, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.concurrency > 16 or args.chunk_bytes > 65536:
        parser.error("concurrency <= 16 and chunk-bytes <= 65536 are required by the recorded probe settings")
    result = asyncio.run(measure(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"PASS: 4 placements, {result['load_seconds']:.3f}s load; measurements: {args.output}")


if __name__ == "__main__":
    main()
