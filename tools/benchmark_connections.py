"""Measure separate v0.4 paths against a real FileStore; no pass/fail speed target."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import platform
import statistics
import tempfile
from time import perf_counter_ns

from nymph_toolkit.contracts import (
    ContractKey, ContractSpec, ModuleAdvertisement, ModuleKind, ModuleSpec,
    OperatingState, OperationMode, OperationSpec, Usage,
)
from nymph_toolkit.core import Connections, FileStore, Registry, Runtime


async def sample(iterations, initial_connections):
    metrics = {}
    with tempfile.TemporaryDirectory(prefix="ntk-connections-bench-") as temporary:
        root = Path(temporary)
        # Keep disk flushes outside CPU-call phases; these are measurement settings.
        store = FileStore(root / "primary", root / "archive", retention=timedelta(days=7),
                          batch_size=iterations * 10 + initial_connections * 10, flush_interval=60)
        registry = Registry()
        core = Connections(registry, store)
        key = ContractKey("benchmark.echo", "1")
        spec = ContractSpec(key, (OperationSpec("echo", OperationMode.SYNC),))
        ready = Usage(OperatingState.RUNNING, True, 0, iterations + 1)
        def echo(value):
            return value
        for name in ["provider", "requester"] + [f"initial-{i}" for i in range(initial_connections)]:
            registry.register(ModuleSpec(name, ModuleKind.SUBSYSTEM))
            core.declare(ModuleAdvertisement(name, "1", (spec,) if name == "provider" else ()),
                         {key: {"echo": echo}} if name == "provider" else None)
            core.publish_usage(name, ready, contracts={key: ready} if name == "provider" else None)
        runtime = Runtime(core)
        try:
            await runtime.start()
            binding = (await core.bind("requester", key, "provider", wait_timeout=10)).key
            handle = await core.prepare(binding, wait_timeout=0)
            await store.flush()
            for _ in range(100):
                handle.call("echo", "warmup")
            start = perf_counter_ns()
            for i in range(iterations):
                echo(i)
            metrics["raw_call_us"] = (perf_counter_ns() - start) / iterations / 1000
            start = perf_counter_ns()
            for i in range(iterations):
                handle.call("echo", i)
            metrics["prepared_direct_call_us"] = (perf_counter_ns() - start) / iterations / 1000
            start = perf_counter_ns()
            for i in range(iterations):
                await core.invoke(binding, "echo", wait_timeout=0, args=(i,))
            metrics["mediated_call_us"] = (perf_counter_ns() - start) / iterations / 1000
            start = perf_counter_ns()
            for i in range(initial_connections):
                await core.bind(f"initial-{i}", key, "provider", wait_timeout=10)
            metrics["initial_binding_with_settings_save_ms"] = (perf_counter_ns() - start) / initial_connections / 1_000_000
            await store.flush()
            start = perf_counter_ns()
            for i in range(1, iterations + 1):
                core.publish_usage("provider", Usage(OperatingState.RUNNING, True, i, iterations + 1))
            metrics["usage_snapshot_and_enqueue_us"] = (perf_counter_ns() - start) / iterations / 1000
            assert store.unsaved_events == iterations
            start = perf_counter_ns()
            await store.flush()
            metrics["history_batch_flush_total_ms"] = (perf_counter_ns() - start) / 1_000_000
            metrics["history_batch_flush_us_per_event"] = metrics["history_batch_flush_total_ms"] * 1000 / iterations
            health_count = min(iterations, 200)
            start = perf_counter_ns()
            for _ in range(health_count):
                await core.health_check(bindings=(binding,))
            metrics["health_request_us"] = (perf_counter_ns() - start) / health_count / 1000
        finally:
            await runtime.stop()
    return metrics


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--initial-connections", type=int, default=20)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if min(args.iterations, args.initial_connections, args.samples) <= 0:
        parser.error("counts must be positive")
    results = [await sample(args.iterations, args.initial_connections) for _ in range(args.samples)]
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
                      "iterations": args.iterations, "initial_connections": args.initial_connections,
                      "samples": results,
                      "median": {key: statistics.median(result[key] for result in results) for key in results[0]},
                      "limitations": "Single-process dummy echo; loop overhead included; local temporary disk; no IPC, contention or hard realtime guarantee."},
                     indent=2))


if __name__ == "__main__":
    asyncio.run(main())
