"""Nymph-side sleep executor with durable intent and explicit result lookup."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor

from nymph_toolkit.contracts import (
    ConnectionNotReadyError, LinkFailure, ModuleContextProtocol, OperatingState, OperationFailure,
    OutcomeUnknown, ProtocolError, RuntimeService, TemporaryUnavailable, Usage,
)
from nymph_toolkit.contracts.persona import PERSONA_CONTRACT
from nymph_toolkit.contracts.sleep import SLEEP_CONTRACT
from nymph_toolkit.contracts.sleep_activity import SLEEP_ACTIVITY_KEY
from ._model import copy, cycle_receipt, fields, persona_receipt, request, text
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


class _SleepActivity:
    def __init__(self, context, config):
        fields(config, "path sleep_module_id persona_module_id")
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Sleep activity requires max_frame_bytes >= 65536")
        self.context = context
        self.identity = dict(module_id=text(context.module_id), sleep_module_id=text(config["sleep_module_id"]),
                             persona_module_id=text(config["persona_module_id"]))
        self.store = Store(config["path"], self.identity)
        self.providers = {SLEEP_CONTRACT.key: self.identity["sleep_module_id"], PERSONA_CONTRACT.key: self.identity["persona_module_id"]}
        self.links, self.bound, self.recoveries, self.tasks = {}, set(), [], set()
        self.pool = self.stop_task = None
        self.started = self.ready = self.closing = self.busy = False
        context.provide(SLEEP_ACTIVITY_KEY, {name: getattr(self, name) for name in ("get", "reconcile", "apply")})
        context.provide_executor("sleep", self.execute, supports_pause=True)

    async def _work(self, function, *args):
        return await _settled(asyncio.get_running_loop().run_in_executor(self.pool, function, *args))

    async def start(self):
        if self.started or self.closing:
            raise RuntimeError("Sleep activity cannot be started twice")
        self.started = True
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-sleep-activity")
        try:
            await self._work(self.store.open)
            self.ready = True
            # Read-only get remains available while a real activity is paused.
            usage = Usage(OperatingState.RUNNING, True, 0, 32)
            await self.context.core.publish_usage(usage, contracts={SLEEP_ACTIVITY_KEY: usage})
        except BaseException:
            await self.stop()
            raise

    async def run(self):
        try:
            await asyncio.Event().wait()
        finally:
            self.ready = False
            self.closing = True

    async def _owned(self, function, *args):
        task = asyncio.create_task(function(*args))
        self.tasks.add(task)
        try:
            return await _settled(task)
        finally:
            self.tasks.discard(task)

    async def get(self, request_id):
        try:
            text(request_id)
        except (ValueError, TypeError) as error:
            return OperationFailure("sleep_activity.invalid", str(error))
        if not self.ready or self.closing:
            return TemporaryUnavailable("Sleep activity is not accepting requests")
        return await self._owned(self._work, self.store.get, request_id)

    async def _control(self, operation, request_id):
        try:
            text(request_id)
        except (ValueError, TypeError) as error:
            return OperationFailure("sleep_activity.invalid", str(error))
        if not self.ready or self.closing or self.busy:
            return TemporaryUnavailable("Another sleep activity/control operation is active")
        self.busy = True
        return await self._owned(self._control_run, operation, request_id)

    async def _control_run(self, operation, key):
        primary = None
        try:
            row = await self._work(self.store.get, key)
            if not isinstance(row, dict):
                return row
            if operation == "apply" and row["phase"] == "cycle_saved":
                return await self._apply(row)
            return await self._reconcile(row)
        except BaseException as error:
            primary = error
            raise
        finally:
            await self._finished(primary)

    async def reconcile(self, request_id):
        return await self._control("reconcile", request_id)

    async def apply(self, request_id):
        return await self._control("apply", request_id)

    async def _connect(self, contract):
        core, key = self.context.core, contract.key
        if key not in self.bound:
            candidates = await core.candidates(key, timeout=5)
            chosen = next((x for x in candidates if x.advertisement.module_id == self.providers[key]), None)
            if chosen is None or contract not in chosen.advertisement.contracts:
                return TemporaryUnavailable("Configured provider does not offer the contract")
            if any(x.state != OperatingState.RUNNING or not x.accepting or not x.free
                   for x in (chosen.module_usage, chosen.contract_usage)):
                return TemporaryUnavailable("Configured provider is unavailable")
            await core.bind(key, self.providers[key], timeout=5)
            self.bound.add(key)
        if key not in self.links:
            self.links[key] = await core.prepare(key, timeout=5)
        return None

    async def _call(self, contract, operation, *args):
        key = contract.key
        try:
            unavailable = await self._connect(contract)
            if unavailable is not None:
                return unavailable
            result = await self.links[key].acall(operation, *args, timeout=5)
            if isinstance(result, LinkFailure):
                self.recoveries.append((key, result.interruption_id))
            return result
        except (OutcomeUnknown, TimeoutError, ProtocolError, ConnectionNotReadyError):
            self.recoveries.append((key, None))
            raise

    async def _finished(self, primary):
        # No external write follows this point. Drain and record the operation
        # before acknowledging its interruption; keep the original error visible.
        try:
            recoveries, self.recoveries = self.recoveries, []
            for key, notice in recoveries:
                link = self.links.pop(key, None)
                if link is not None:
                    await link.close()
                if not self.closing:
                    if notice is not None:
                        await self.context.core.acknowledge_interruption(notice, timeout=5)
                    await self.context.core.health_check(module_ids=(self.providers[key],), timeout=5)
        except Exception as recovery:
            if primary is not None:
                raise primary from recovery
            raise
        finally:
            self.busy = False

    async def _save(self, row, **changes):
        return await self._work(self.store.save, row, dict(row, **changes))

    async def _error(self, row, result, *, definite=False):
        error = dict(kind=getattr(result, "code", type(result).__name__), message=str(result)[:512])
        return await self._save(row, phase="failed" if definite else row["phase"], error=error)

    async def _send(self, row, contract, operation, value, validate, finish):
        try:
            result = await self._call(contract, operation, value)
            if isinstance(result, (OperationFailure, TemporaryUnavailable, LinkFailure)):
                return await self._error(row, result, definite=not isinstance(result, LinkFailure))
            receipt = validate(result)
            return await finish(receipt)
        except BaseException as error:
            # A send, its reply or local receipt persistence may have failed after
            # the provider committed. Leave the sent phase for a later lookup.
            try:
                current = await self._work(self.store.get, row["request"]["request_id"])
                if isinstance(current, dict) and current["phase"] == row["phase"]:
                    await self._error(current, error)
            except BaseException as recording:
                raise error from recording
            raise

    async def _cycle_confirmed(self, row, receipt):
        needs_apply = row["request"]["apply_persona"] and receipt["persona_proposal"] is not None
        return await self._save(row, phase="cycle_saved" if needs_apply else "completed", cycle=receipt, error=None)

    async def _apply(self, row):
        if row["phase"] != "cycle_saved":
            return row
        proposal = row["cycle"]["persona_proposal"]
        if not row["request"]["apply_persona"] or proposal is None:
            return await self._save(row, phase="completed", error=None)
        row = await self._save(row, phase="apply_sent", error=None)
        return await self._send(row, PERSONA_CONTRACT, "apply", proposal,
                                lambda value: persona_receipt(value, proposal),
                                lambda value: self._save(row, phase="completed", persona=value, error=None))

    async def _reconcile(self, row):
        phase = row["phase"]
        if phase not in ("cycle_sent", "apply_sent"):
            return row
        if phase == "cycle_sent":
            result = await self._call(SLEEP_CONTRACT, "get", row["cycle_id"])
        else:
            result = await self._call(PERSONA_CONTRACT, "get_update", row["cycle"]["persona_proposal"]["command_id"])
        if isinstance(result, (OperationFailure, TemporaryUnavailable, LinkFailure)):
            return await self._error(row, result)  # not_found is not proof of non-execution
        if phase == "cycle_sent":
            return await self._cycle_confirmed(row, cycle_receipt(result, row, self.identity))
        return await self._save(row, phase="completed", persona=persona_receipt(result, row["cycle"]["persona_proposal"]), error=None)

    async def execute(self, activity, arguments):
        # Accept the standard Agency wrapper as well as direct Core arguments.
        arguments = copy(arguments, 8192)
        if type(arguments) is dict and set(arguments) == {"configured", "goal"}:
            arguments = arguments["configured"]
        value = request(arguments)
        if not self.ready or self.closing or self.busy:
            raise RuntimeError("Sleep activity is not accepting another execution")
        self.busy = True
        task = asyncio.current_task()
        self.tasks.add(task)
        primary = None
        try:
            if await activity.checkpoint() is not None:
                return {"request_id": value["request_id"], "phase": "not_started"}
            key = activity.request.key
            row, fresh = await self._work(self.store.begin, value, dict(requester_id=key.requester_id, activity_id=key.activity_id))
            if not isinstance(row, dict):
                raise RuntimeError(str(row))
            if not fresh:
                return row  # new activity registration is not permission to replay a side effect
            row = await self._save(row, phase="cycle_sent")
            cycle = {name: value[name] for name in ("expected_revision", "record_ids")}
            cycle["cycle_id"] = row["cycle_id"]
            row = await self._send(row, SLEEP_CONTRACT, "cycle", cycle,
                                   lambda result: cycle_receipt(result, row, self.identity),
                                   lambda result: self._cycle_confirmed(row, result))
            if row["phase"] == "cycle_saved" and await activity.checkpoint() is None:
                row = await self._apply(row)
            if row["phase"] in ("failed", "cycle_sent", "apply_sent"):
                raise RuntimeError("Sleep activity requires inspection: " + value["request_id"])
            return row
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                await self._finished(primary)
            finally:
                self.tasks.discard(task)

    async def stop(self):
        self.ready = False
        self.closing = True
        if self.stop_task is None:
            self.stop_task = asyncio.create_task(self._close())
        await _settled(self.stop_task)

    async def _close(self):
        try:
            while self.tasks:
                await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
                await asyncio.sleep(0)
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
    return _SleepActivity(context, config)
