"""Sleep consolidation through public evidence contracts; no autonomous writes."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor

from nymph_toolkit.contracts import (
    ConnectionNotReadyError, LinkFailure, ModuleContextProtocol, OperatingState,
    OperationFailure, OutcomeUnknown, ProtocolError, RuntimeService, TemporaryUnavailable, Usage,
)
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT
from nymph_toolkit.contracts.sleep import SLEEP_KEY
from ._model import SOURCES, atom, fields, integer, memory_record, observation, persona, request, rules, text
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


class _Sleep:
    def __init__(self, context, config):
        fields(config, "path memory_module_id cognition_module_id persona_module_id trait_rules")
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Sleep requires max_frame_bytes >= 65536")
        self.context = context
        self.identity = dict(module_id=text(context.module_id), trait_rules=rules(config["trait_rules"]))
        self.identity.update({name: text(config[name]) for name in ("memory_module_id", "cognition_module_id", "persona_module_id")})
        self.store = Store(config["path"], self.identity)
        self.providers = {MEMORY_CONTRACT.key: self.identity["memory_module_id"],
                          COGNITION_REVISION_CONTRACT.key: self.identity["cognition_module_id"],
                          PERSONA_CONTRACT.key: self.identity["persona_module_id"]}
        self.links, self.bound = {}, set()
        self.active = self.stop_task = self.pool = None
        self.started = self.ready = self.closing = self.busy = False
        context.provide(SLEEP_KEY, {name: getattr(self, name) for name in ("cycle", "get", "state", "inspect")})

    async def _usage(self, active):
        usage = Usage(OperatingState.RUNNING, True, active, 1)
        await self.context.core.publish_usage(usage, contracts={SLEEP_KEY: usage})

    async def _work(self, function, *args):
        return await _settled(asyncio.get_running_loop().run_in_executor(self.pool, function, *args))

    async def start(self):
        if self.started or self.closing:
            raise RuntimeError("Sleep cannot be started twice")
        self.started = True
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-sleep")
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

    async def cycle(self, value):
        try:
            value = request(value)
        except (ValueError, TypeError, OverflowError, RecursionError) as error:
            return OperationFailure("sleep.invalid", str(error))
        return await self._submit("cycle", value)

    async def get(self, cycle_id):
        try:
            text(cycle_id)
        except (ValueError, TypeError) as error:
            return OperationFailure("sleep.invalid", str(error))
        return await self._submit("get", cycle_id)

    async def state(self, *, after=0, limit=4):
        try:
            integer(after, 0, 16); integer(limit, 1, 4)
        except (ValueError, TypeError) as error:
            return OperationFailure("sleep.invalid", str(error))
        return await self._submit("state", after, limit)

    async def inspect(self, concept, *, source_kind=None):
        try:
            atom(concept)
            if source_kind is not None and (type(source_kind) is not str or source_kind not in SOURCES):
                raise ValueError("Invalid source_kind")
        except (ValueError, TypeError) as error:
            return OperationFailure("sleep.invalid", str(error))
        return await self._submit("inspect", concept, source_kind)

    async def _submit(self, operation, *args):
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Sleep is stopped or processing another operation")
        self.busy = True
        self.active = asyncio.create_task(self._execute(operation, *args))
        return await _settled(self.active)

    async def _connect(self, contract):
        core, key = self.context.core, contract.key
        if key not in self.bound:
            candidates = await core.candidates(key, timeout=5)
            chosen = next((c for c in candidates if c.advertisement.module_id == self.providers[key]), None)
            if chosen is None or contract not in chosen.advertisement.contracts:
                return TemporaryUnavailable("Selected provider does not offer the required contract")
            for usage in (chosen.module_usage, chosen.contract_usage):
                if usage.state != OperatingState.RUNNING or not usage.accepting or not usage.free:
                    return TemporaryUnavailable("Selected provider has no available capacity")
            await core.bind(key, self.providers[key], timeout=5)
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

    async def _call(self, contract, operation, *args):
        key = contract.key
        try:
            unavailable = await self._connect(contract)
            if unavailable is not None:
                return unavailable
            result = await self.links[key].acall(operation, *args, timeout=5)
            if isinstance(result, LinkFailure):
                await self._recover(key, result.interruption_id)
            return result
        except (OutcomeUnknown, TimeoutError, ProtocolError, ConnectionNotReadyError) as original:
            try:
                await self._recover(key)
            except Exception as recovery:
                raise original from recovery
            raise

    async def _cycle(self, value):
        replay = await self._work(self.store.execute, "preflight", value)
        if replay is not None:
            return replay
        evidence = []
        for record_id in value["record_ids"]:
            record = await self._call(MEMORY_CONTRACT, "get", record_id)
            if isinstance(record, (OperationFailure, TemporaryUnavailable, LinkFailure)):
                return record
            try:
                record = memory_record(record, record_id)
            except (ValueError, TypeError, KeyError, RecursionError) as error:
                return OperationFailure("sleep.evidence", str(error))
            annotation = await self._call(COGNITION_REVISION_CONTRACT, "get_revision", record_id)
            if isinstance(annotation, (OperationFailure, TemporaryUnavailable, LinkFailure)):
                return annotation
            try:
                evidence.append(observation(record, annotation))
            except (ValueError, TypeError, KeyError, RecursionError) as error:
                return OperationFailure("sleep.evidence", str(error))
        traits = await self._call(PERSONA_CONTRACT, "get")
        if isinstance(traits, (OperationFailure, TemporaryUnavailable, LinkFailure)):
            return traits
        try:
            traits = persona(traits, self.identity)
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            return OperationFailure("sleep.evidence", str(error))
        return await self._work(self.store.execute, "save", value, evidence, traits)

    async def _execute(self, operation, *args):
        primary = None
        try:
            await self._usage(1)
            if operation == "cycle":
                return await self._cycle(*args)
            return await self._work(self.store.execute, operation, *args)
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                if not self.closing:
                    await self._usage(0)
            except Exception as reporting:
                if primary is not None:
                    raise primary from reporting
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
                links, self.links = self.links, {}
                results = await asyncio.gather(*(link.close() for link in links.values()), return_exceptions=True)
                for result in results:
                    if isinstance(result, BaseException):
                        raise result
            finally:
                if self.pool is not None:
                    try:
                        await self._work(self.store.close)
                    finally:
                        self.pool.shutdown(wait=True)
                        self.pool = None


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Sleep(context, config)
