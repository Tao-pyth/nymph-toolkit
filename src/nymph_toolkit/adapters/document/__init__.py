"""Local text import into a selected Memory provider, through public Contracts."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nymph_toolkit.contracts import (
    ConnectionNotReadyError, LinkFailure, ModuleContextProtocol, OperationFailure,
    OperatingState, OutcomeUnknown, ProtocolError, RuntimeService, TemporaryUnavailable, Usage,
)
from nymph_toolkit.contracts.document import DOCUMENT_KEY
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT, MEMORY_KEY
from ._reader import read_record, root_path

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


class _Document:
    def __init__(self, context, config):
        if type(config) is not dict or set(config) != {"root", "memory_module_id"}:
            raise ValueError("Document config requires root and memory_module_id")
        if type(config["root"]) is not str or not Path(config["root"]).is_absolute():
            raise ValueError("Document root must be an absolute directory")
        provider = config["memory_module_id"]
        if type(provider) is not str or not provider.strip() or provider != provider.strip():
            raise ValueError("memory_module_id must be nonempty trimmed text")
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Document requires max_frame_bytes >= 65536")
        self.context, self.root, self.provider = context, config["root"], provider
        self.pool = self.link = self.active = self.stop_task = None
        self.ready = self.closing = self.busy = self.bound = False
        context.provide(DOCUMENT_KEY, {"ingest": self.ingest})

    async def _usage(self, active):
        usage = Usage(OperatingState.RUNNING, True, active, 1)
        await self.context.core.publish_usage(usage, contracts={DOCUMENT_KEY: usage})

    async def start(self):
        if self.pool is not None or self.closing:
            raise RuntimeError("Document cannot be started twice")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-document")
        try:
            self.root = await _settled(asyncio.get_running_loop().run_in_executor(self.pool, root_path, self.root))
            self.ready = True
            await self._usage(0)
        except BaseException:
            await self.stop()
            raise

    async def run(self):
        try:
            await asyncio.Event().wait()
        finally:
            # Runtime cancels run before draining handlers during node shutdown.
            self.ready = False
            self.closing = True

    async def ingest(self, request):
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Document is stopped or processing another import")
        # All valid values are strings. Snapshot before any notification can yield.
        if type(request) is dict:
            request = dict(request)
        self.busy = True
        self.active = asyncio.create_task(self._ingest(request))
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
            core = self.context.core
            if interruption_id is not None:
                await core.acknowledge_interruption(interruption_id, timeout=5)
            await core.health_check(module_ids=(self.provider,), timeout=5)

    async def _ingest(self, request):
        primary_error = None
        try:
            await self._usage(1)
            record = await _settled(asyncio.get_running_loop().run_in_executor(self.pool, read_record, self.root, request))
            if isinstance(record, OperationFailure):
                return record
            try:
                unavailable = await self._connect()
                if unavailable is not None:
                    return unavailable
                result = await self.link.acall("put", record, timeout=5)
                if isinstance(result, LinkFailure):
                    await self._recover(result.interruption_id)
                return result
            except (OutcomeUnknown, TimeoutError, ProtocolError, ConnectionNotReadyError) as original:
                try:
                    await self._recover()
                except Exception as recovery_error:
                    # Failed cleanup/health cannot turn an unknown put outcome
                    # into an apparently definite failure of that put.
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
                # Retrieving the result also consumes failures owned by a cancelled caller.
                await asyncio.gather(self.active, return_exceptions=True)
        finally:
            try:
                if self.link is not None:
                    await self.link.close()
                    self.link = None
            finally:
                if self.pool is not None:
                    self.pool.shutdown(wait=True)
                    self.pool = None


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Document(context, config)
