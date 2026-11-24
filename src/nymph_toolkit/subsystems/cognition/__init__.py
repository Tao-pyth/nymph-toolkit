"""Evidence-backed initial learning through public Core and Memory Contracts."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor

from nymph_toolkit.contracts import (
    ConnectionNotReadyError, LinkFailure, ModuleContextProtocol, OperationFailure,
    OperatingState, OutcomeUnknown, ProtocolError, RuntimeService, TemporaryUnavailable, Usage,
)
from nymph_toolkit.contracts.cognition import COGNITION_KEY
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from ._model import annotations, identifier, observation, query
from ._store import Store

__all__ = ["factory"]


async def _settled(future):
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


class _Cognition:
    def __init__(self, context, config):
        if (type(config) is not dict or not {"path", "memory_module_id"} <= set(config)
                or set(config) - {"path", "memory_module_id", "enable_revision"}
                or type(config.get("enable_revision", False)) is not bool):
            raise ValueError("Cognition config requires path/memory_module_id and optional bool enable_revision")
        provider = config["memory_module_id"]
        if type(provider) is not str or not provider.strip() or provider != provider.strip():
            raise ValueError("memory_module_id must be nonempty trimmed text")
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Cognition requires max_frame_bytes >= 65536")
        self.context, self.provider = context, provider
        self.enable_revision = config.get("enable_revision", False)
        self.store = Store(config["path"], provider, self.enable_revision)
        self.pool = self.active = self.link = self.stop_task = None
        self.ready = self.closing = self.busy = self.bound = False
        context.provide(COGNITION_KEY, {"learn": self.learn, "inspect": self.inspect})
        if self.enable_revision:
            context.provide(COGNITION_REVISION_KEY, {"correct": self.correct, "get_revision": self.get_revision})

    async def _usage(self, active):
        usage = Usage(OperatingState.RUNNING, True, active, 1)
        contracts = {COGNITION_KEY: usage}
        if self.enable_revision:
            contracts[COGNITION_REVISION_KEY] = usage
        await self.context.core.publish_usage(usage, contracts=contracts)

    async def _work(self, function, *args):
        return await _settled(asyncio.get_running_loop().run_in_executor(self.pool, function, *args))

    async def start(self):
        if self.pool is not None or self.closing:
            raise RuntimeError("Cognition cannot be started twice")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-cognition")
        try:
            await self._work(self.store.open)
            self.ready = True
            await self._usage(0)
        except BaseException:
            await self.stop()
            raise

    async def run(self):
        try:
            await asyncio.Event().wait()
        finally:
            self.ready = False
            self.closing = True

    async def learn(self, record_id, *, tokens, concepts):
        try:
            args = annotations(record_id, tokens, concepts)
        except (ValueError, TypeError) as error:
            return OperationFailure("cognition.invalid", str(error))
        return await self._submit("learn", *args)

    async def inspect(self, token, *, source_kind=None, after=0, limit=8):
        try:
            args = query(token, source_kind, after, limit)
        except (ValueError, TypeError) as error:
            return OperationFailure("cognition.invalid", str(error))
        return await self._submit("inspect", *args)

    async def get_revision(self, record_id):
        if not self.enable_revision:
            return OperationFailure("cognition.disabled", "Annotation revision is not enabled")
        try:
            identifier(record_id)
        except (ValueError, TypeError) as error:
            return OperationFailure("cognition.invalid", str(error))
        return await self._submit("get_revision", record_id)

    async def correct(self, record_id, *, command_id, expected_revision, tokens, concepts):
        if not self.enable_revision:
            return OperationFailure("cognition.disabled", "Annotation revision is not enabled")
        try:
            args = annotations(record_id, tokens, concepts)
            identifier(command_id)
            if type(expected_revision) is not int or not 0 <= expected_revision <= 2**63-2:
                raise ValueError("expected_revision requires an integer in 0..2^63-2")
        except (ValueError, TypeError) as error:
            return OperationFailure("cognition.invalid", str(error))
        return await self._submit("correct", *args, command_id, expected_revision)

    async def _submit(self, operation, *args):
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Cognition is stopped or processing another operation")
        self.busy = True
        self.active = asyncio.create_task(self._execute(operation, *args))
        return await _settled(self.active)

    async def _connect(self):
        core = self.context.core
        if not self.bound:
            candidates = await core.candidates(MEMORY_KEY, timeout=5)
            chosen = next((c for c in candidates if c.advertisement.module_id == self.provider), None)
            if chosen is None or MEMORY_CONTRACT not in chosen.advertisement.contracts:
                return TemporaryUnavailable("Selected Memory provider does not offer records/1")
            for usage in (chosen.module_usage, chosen.contract_usage):
                if usage.state != OperatingState.RUNNING or not usage.accepting or not usage.free:
                    return TemporaryUnavailable("Selected Memory provider has no available capacity")
            await core.bind(MEMORY_KEY, self.provider, timeout=5)
            self.bound = True
        if self.link is None:
            self.link = await core.prepare(MEMORY_KEY, timeout=5)
        return None

    async def _recover(self, interruption_id=None):
        if self.link is not None:
            link, self.link = self.link, None
            await link.close()
        if not self.closing:
            if interruption_id is not None:
                await self.context.core.acknowledge_interruption(interruption_id, timeout=5)
            await self.context.core.health_check(module_ids=(self.provider,), timeout=5)

    async def _execute(self, operation, *args):
        primary_error = None
        try:
            await self._usage(1)
            if operation in ("inspect", "get_revision"):
                return await self._work(self.store.execute, operation, *args)
            try:
                unavailable = await self._connect()
                if unavailable is not None:
                    return unavailable
                record = await self.link.acall("get", args[0], timeout=5)
                if isinstance(record, LinkFailure):
                    await self._recover(record.interruption_id)
                    return record
                if isinstance(record, (OperationFailure, TemporaryUnavailable)):
                    return record
                try:
                    sample = observation(record, *args[:3])
                except (ValueError, TypeError) as error:
                    return OperationFailure("cognition.invalid", str(error))
                return await self._work(self.store.execute, operation, sample, *args[3:])
            except (OutcomeUnknown, TimeoutError, ProtocolError, ConnectionNotReadyError) as original:
                try:
                    await self._recover()
                except Exception as recovery_error:
                    raise original from recovery_error
                raise
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                if not self.closing:
                    await self._usage(0)
            except Exception as reporting_error:
                if primary_error is not None:
                    raise primary_error from reporting_error
                raise
            finally:
                self.busy = False

    async def stop(self):
        self.ready = False
        self.closing = True
        if self.stop_task is None:
            self.stop_task = asyncio.create_task(self._close())
        await _settled(self.stop_task)

    async def _close(self):
        try:
            if self.active is not None:
                await asyncio.gather(self.active, return_exceptions=True)
        finally:
            try:
                if self.link is not None:
                    await self.link.close()
                    self.link = None
            finally:
                if self.pool is not None:
                    try:
                        await self._work(self.store.close)
                    finally:
                        self.pool.shutdown(wait=True)
                        self.pool = None


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Cognition(context, config)
