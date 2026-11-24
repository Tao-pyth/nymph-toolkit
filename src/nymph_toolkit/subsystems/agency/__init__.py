"""Nymph-side decisions using Memory and Cognition over public contracts."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor

from nymph_toolkit.contracts import (
    ConnectionNotReadyError, LinkFailure, ModuleContextProtocol, OperatingState,
    OperationFailure, OutcomeUnknown, ProtocolError, RuntimeService, TemporaryUnavailable, Usage,
)
from nymph_toolkit.contracts.agency import AGENCY_KEY
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT
from ._model import catalog, decide, fields, identifier, observation, persona_observation, persona_settings, request, snapshot
from ._store import Store

__all__ = ["factory", "execution_factory"]


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


class _Agency:
    def __init__(self, context, config):
        has_persona = type(config) is dict and "persona" in config
        fields(config, "path memory_module_id cognition_module_id catalog" + (" persona" if has_persona else ""))
        self.persona = persona_settings(config["persona"]) if has_persona else None
        self.catalog = catalog(config["catalog"])
        self.providers = {MEMORY_CONTRACT.key:identifier(config["memory_module_id"]),
                          COGNITION_CONTRACT.key:identifier(config["cognition_module_id"])}
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Agency requires max_frame_bytes >= 65536")
        self.context = context
        identity = {"module_id":context.module_id, "catalog":self.catalog,
                    "memory_module_id":config["memory_module_id"], "cognition_module_id":config["cognition_module_id"]}
        if self.persona is not None:
            self.providers[PERSONA_CONTRACT.key] = self.persona["module_id"]
            identity["persona"] = self.persona
        self.store = Store(config["path"], identity)
        self.links, self.bound = {}, set()
        self.active = self.stop_task = self.pool = None
        self.started = self.ready = self.closing = self.busy = False
        context.provide(AGENCY_KEY, {"decide":self.decide, "get":self.get})

    async def _usage(self, active):
        usage = Usage(OperatingState.RUNNING, True, active, 1)
        await self.context.core.publish_usage(usage, contracts={AGENCY_KEY:usage})

    async def _work(self, function, *args):
        return await _settled(asyncio.get_running_loop().run_in_executor(self.pool,function,*args))

    async def start(self):
        if self.started or self.closing:
            raise RuntimeError("Agency cannot be started twice")
        self.started = True
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-agency")
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

    async def get(self, decision_id):
        try:
            identifier(decision_id)
        except (ValueError, TypeError) as error:
            return OperationFailure("agency.invalid", str(error))
        return await self._submit("get", decision_id)

    async def decide(self, value):
        try:
            value = request(value, self.catalog)
        except (ValueError, TypeError, OverflowError, RecursionError) as error:
            return OperationFailure("agency.invalid", str(error))
        return await self._submit("decide", value)

    async def _submit(self, operation, value):
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Agency is stopped or processing another operation")
        self.busy = True
        self.active = asyncio.create_task(self._execute(operation, value))
        return await _settled(self.active)

    async def _connect(self, contract):
        core, key = self.context.core, contract.key
        if key not in self.bound:
            candidates = await core.candidates(key, timeout=5)
            chosen = next((c for c in candidates if c.advertisement.module_id == self.providers[key]),None)
            if chosen is None or contract not in chosen.advertisement.contracts:
                return TemporaryUnavailable("Selected provider does not offer the required contract")
            for usage in (chosen.module_usage,chosen.contract_usage):
                if usage.state != OperatingState.RUNNING or not usage.accepting or not usage.free:
                    return TemporaryUnavailable("Selected provider has no available capacity")
            await core.bind(key,self.providers[key],timeout=5)
            self.bound.add(key)
        if key not in self.links:
            self.links[key] = await core.prepare(key,timeout=5)
        return None

    async def _recover(self, key, interruption_id=None):
        link = self.links.pop(key,None)
        if link is not None:
            await link.close()
        if not self.closing:
            if interruption_id is not None:
                await self.context.core.acknowledge_interruption(interruption_id,timeout=5)
            await self.context.core.health_check(module_ids=(self.providers[key],),timeout=5)

    async def _call(self, contract, operation, *args, **kwargs):
        key = contract.key
        try:
            unavailable = await self._connect(contract)
            if unavailable is not None:
                return unavailable
            result = await self.links[key].acall(operation,*args,**kwargs,timeout=5)
            if isinstance(result,LinkFailure):
                await self._recover(key,result.interruption_id)
            return result
        except (OutcomeUnknown,TimeoutError,ProtocolError,ConnectionNotReadyError) as original:
            try:
                await self._recover(key)
            except Exception as recovery:
                raise original from recovery
            raise

    async def _decision(self, value):
        replay = await self._work(self.store.execute,"replay",value)
        if replay is not None:
            return replay
        previous = None
        if value["current"] is not None:
            previous = await self._work(self.store.execute,"get",value["current"]["decision_id"])
            if isinstance(previous,OperationFailure):
                return previous
            if previous["plan"] is None:
                return OperationFailure("agency.invalid", "Current decision does not contain a plan")
        evidence = []
        for goal in value["goals"]:
            record = await self._call(MEMORY_CONTRACT,"get",goal["record_id"])
            if isinstance(record,(OperationFailure,TemporaryUnavailable,LinkFailure)):
                return record
            try:
                # Snapshot the public result before another await, including LOCAL calls.
                record = snapshot(record,8192)
                kind = record["source_kind"]
                if type(kind) is not str:
                    raise ValueError("Invalid Memory source kind")
            except (ValueError,TypeError,KeyError,RecursionError) as error:
                return OperationFailure("agency.evidence",str(error))
            profile = await self._call(COGNITION_CONTRACT,"inspect",goal["token"],source_kind=kind,after=0,limit=1)
            if isinstance(profile,(OperationFailure,TemporaryUnavailable,LinkFailure)):
                return profile
            try:
                evidence.append(observation(goal,record,profile))
            except (ValueError,TypeError,KeyError,OverflowError) as error:
                return OperationFailure("agency.evidence",str(error))
        if self.persona is not None:
            traits = await self._call(PERSONA_CONTRACT, "get")
            if isinstance(traits, (OperationFailure, TemporaryUnavailable, LinkFailure)):
                return traits
            try:
                evidence = dict(goals=evidence, persona=persona_observation(traits, self.persona))
            except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
                return OperationFailure("agency.evidence", str(error))
        try:
            result = decide(value,evidence,self.catalog,self.context.module_id,previous,persona=self.persona)
        except (ValueError,TypeError,OverflowError) as error:
            return OperationFailure("agency.invalid",str(error))
        return await self._work(self.store.execute,"save",value,evidence,result)

    async def _execute(self, operation, value):
        primary = None
        try:
            await self._usage(1)
            if operation == "get":
                return await self._work(self.store.execute,"get",value)
            return await self._decision(value)
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
                await asyncio.gather(self.active,return_exceptions=True)
        finally:
            try:
                links, self.links = self.links, {}
                results = await asyncio.gather(*(link.close() for link in links.values()),return_exceptions=True)
                for result in results:
                    if isinstance(result,BaseException):
                        raise result
            finally:
                if self.pool is not None:
                    try:
                        await self._work(self.store.close)
                    finally:
                        self.pool.shutdown(wait=True)
                        self.pool = None


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Agency(context,config)


def execution_factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    """Opt-in Agency-owned decisions and execution; starts inactive on every boot."""
    from ._execution import ExecutingAgency
    return ExecutingAgency(context, config)
