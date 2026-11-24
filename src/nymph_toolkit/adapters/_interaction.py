"""Lifecycle and outbound calls owned by the v1.4 input adapters."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

from nymph_toolkit.contracts import (
    ConnectionNotReadyError, LinkFailure, OperatingState, OutcomeUnknown,
    ProtocolError, TemporaryUnavailable, Usage,
)


def snapshot(value):
    """Detach admitted JSON inputs from local callers before the first await."""
    def validate(item):
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise ValueError("JSON object keys must be strings")
            for child in item.values():
                validate(child)
        elif type(item) is list:
            for child in item:
                validate(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("Input must contain only JSON values")
    validate(value)
    return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=False))


def provider_id(value):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("provider module IDs must be nonempty trimmed text")
    return value


async def settled(future):
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        if not future.cancelled():
            future.exception()
        raise asyncio.CancelledError
    return future.result()


class InputAdapter:
    def __init__(self, context, contract, handlers, providers, *, worker=False):
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Input adapters require max_frame_bytes >= 65536")
        self.context, self.contract, self.providers = context, contract, providers
        self.worker = worker
        self.links, self.bound = {}, set()
        self.active = self.stop_task = self.pool = None
        self.started = self.ready = self.closing = self.busy = False
        context.provide(contract.key, handlers)

    async def usage(self, active):
        usage = Usage(OperatingState.RUNNING, True, active, 1)
        await self.context.core.publish_usage(usage, contracts={self.contract.key: usage})

    async def start(self):
        if self.started or self.closing:
            raise RuntimeError("Input adapter cannot be started twice")
        self.started = True
        if self.worker:
            self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-web")
        try:
            self.ready = True
            await self.usage(0)
        except BaseException:
            await self.stop()
            raise

    async def run(self):
        try:
            await asyncio.Event().wait()
        finally:
            self.ready = False
            self.closing = True

    async def submit(self, function, *args):
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Input adapter is stopped or processing another operation")
        self.busy = True
        self.active = asyncio.create_task(self._execute(function, *args))
        return await settled(self.active)

    async def work(self, function, *args):
        return await settled(asyncio.get_running_loop().run_in_executor(self.pool, function, *args))

    async def _execute(self, function, *args):
        primary_error = None
        try:
            await self.usage(1)
            return await function(*args)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                if not self.closing:
                    await self.usage(0)
            except Exception as reporting_error:
                if primary_error is not None:
                    raise primary_error from reporting_error
                raise
            finally:
                self.busy = False

    async def _connect(self, contract):
        core, key = self.context.core, contract.key
        provider = self.providers[key]
        if key not in self.bound:
            candidates = await core.candidates(key, timeout=5)
            chosen = next((c for c in candidates if c.advertisement.module_id == provider), None)
            if chosen is None or contract not in chosen.advertisement.contracts:
                return TemporaryUnavailable("Selected provider does not offer the required contract")
            for usage in (chosen.module_usage, chosen.contract_usage):
                if usage.state != OperatingState.RUNNING or not usage.accepting or not usage.free:
                    return TemporaryUnavailable("Selected provider has no available capacity")
            await core.bind(key, provider, timeout=5)
            self.bound.add(key)
        if key not in self.links:
            self.links[key] = await core.prepare(key, timeout=5)
        return None

    async def _recover(self, key, interruption_id=None):
        link = self.links.pop(key, None)
        if link is not None:
            await link.close()
        if not self.closing:
            if interruption_id is not None:
                await self.context.core.acknowledge_interruption(interruption_id, timeout=5)
            await self.context.core.health_check(module_ids=(self.providers[key],), timeout=5)

    async def forward(self, contract, operation, args, kwargs):
        key = contract.key
        try:
            unavailable = await self._connect(contract)
            if unavailable is not None:
                return unavailable
            result = await self.links[key].acall(operation, *args, **kwargs, timeout=5)
            if isinstance(result, LinkFailure):
                await self._recover(key, result.interruption_id)
            return result
        except (OutcomeUnknown, TimeoutError, ProtocolError, ConnectionNotReadyError) as original:
            try:
                await self._recover(key)
            except Exception as recovery_error:
                raise original from recovery_error
            raise

    async def stop(self):
        self.ready = False
        self.closing = True
        if self.stop_task is None:
            self.stop_task = asyncio.create_task(self._close())
        await settled(self.stop_task)

    async def _close(self):
        try:
            if self.active is not None:
                await asyncio.gather(self.active, return_exceptions=True)
        finally:
            try:
                links, self.links = self.links, {}
                results = await asyncio.gather(*(link.close() for link in links.values()), return_exceptions=True)
                for result in results:
                    if isinstance(result, BaseException):
                        raise result
            finally:
                if self.pool is not None:
                    self.pool.shutdown(wait=True)
                    self.pool = None
