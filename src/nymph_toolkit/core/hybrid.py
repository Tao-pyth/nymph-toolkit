"""Parent-owned hybrid lifecycle and routing, layered on the existing four Core roles."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from dataclasses import replace
import os
import sys
from uuid import uuid4

from nymph_toolkit.contracts import (
    BindingKey, HybridSettings, OperationMode, PeerClosed, Placement,
    ProcessSnapshot, ProtocolError, RemoteError, RuntimeState, Usage, OperatingState,
    CapacityExceeded, TemporaryUnavailable, OutcomeUnknown,
)
from .connections import Connections
from .module_group import ModuleGroup
from ._module_contract import validate_module_registration
from ._module_node import ModuleNode
from ._net import start_server
from ._rpc import RpcPeer
from ._wire import VERSION, decode, encode, read_frame, write_frame


def _future():
    future = asyncio.get_running_loop().create_future()
    future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
    return future


class _Service:
    def __init__(self, hub, spec, advertisement, factory, config, placement):
        self.hub, self.spec, self.advertisement = hub, spec, advertisement
        self.factory, self.config, self.placement = factory, config, placement
        self.generation = uuid4().hex
        self.node = self.peer = self.process = self.monitor = None
        self.ready = self.finished = None
        self.port = None
        self.executors = {}
        self.snapshot = ProcessSnapshot(spec.module_id, placement, self.generation, "new")

    def observe(self, **changes):
        self.snapshot = replace(self.snapshot, **changes)
        store = self.hub.connections.store
        if store.state not in (RuntimeState.STOPPED, RuntimeState.FAILED):
            store.append("hybrid_process", {"module_id": self.spec.module_id, "generation": self.generation,
                         **{name: getattr(self.snapshot, name) for name in ("state", "pid", "returncode", "cleanup_confirmed", "reason")}})

    async def start(self):
        self.ready, self.finished = _future(), _future()
        self.observe(state="starting")
        if self.placement == Placement.LOCAL:
            async def dispatch(operation, payload, timeout):
                async with asyncio.timeout(timeout):
                    return await self.hub._core(self.spec.module_id, operation, payload)
            self.node = ModuleNode(self.spec, self.advertisement, self.factory, self.config,
                                   self.generation, self.hub.settings, dispatch,
                                   lambda kind, data: self.hub._event(self.spec.module_id, kind, data), self.hub)
            self.hub.local_nodes[self.spec.module_id] = self.node
            # Same-process services remain cooperative; timeout does not force a thread to stop.
            async with asyncio.timeout(self.hub.settings.startup_timeout):
                await self.node.start()
            self.port = self.node.port
            self.executors = {k: pause for k, (_, pause) in self.node.context.executors.items()}
            self.ready.set_result(None)
            self.observe(state="ready", pid=os.getpid())
        else:
            try:
                self.process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "nymph_toolkit.core._child", str(self.hub.port), self.spec.module_id, self.generation)
            except NotImplementedError as exc:
                raise RuntimeError("Event loop does not support subprocesses; use a subprocess-capable loop") from exc
            self.observe(pid=self.process.pid)
            self.monitor = asyncio.create_task(self._watch_process(), name=f"ntk-child:{self.spec.module_id}")
            async with asyncio.timeout(self.hub.settings.startup_timeout):
                await asyncio.shield(self.ready)

    async def _watch_process(self):
        code = await self.process.wait()
        expected = self.hub._stopping
        self.observe(state="stopped" if expected else "failed", returncode=code,
                     reason=self.snapshot.reason if expected else "Unexpected child exit; unforwarded history is unknown")
        if self.hub.activities is not None:
            self.hub.activities._module_lost(self.spec.module_id)
        error = PeerClosed(f"{self.spec.module_id} exited ({code}); cleanup={self.snapshot.cleanup_confirmed}")
        for future in (self.ready, self.finished):
            if future is not None and not future.done():
                future.set_exception(error)
        if not expected:
            self.hub.fail(error)

    async def invoke(self, operation, payload, *, timeout=None):
        if self.node is not None:
            return await self.node.dispatch(operation, payload)
        if self.peer is None:
            raise PeerClosed("Child control channel is not ready")
        return await self.peer.call(operation, payload, timeout=self.hub.settings.call_timeout if timeout is None else timeout,
                                    retain_result=False)

    async def run(self):
        self.observe(state="running")
        await self.invoke("run_start", None)
        return await asyncio.shield(self.finished)

    async def force_after_deadline(self):
        await asyncio.sleep(self.hub.settings.shutdown_timeout)
        if self.process is not None and self.process.returncode is None:
            self.observe(state="forcing", reason="Core shutdown deadline exceeded; cleanup unconfirmed", cleanup_confirmed=False)
            try:
                self.process.kill()
            except ProcessLookupError:
                # Exit can race this deadline or the service's own stop path.
                pass
            await self.process.wait()

    async def stop(self):
        if self.node is not None:
            await self.node.stop()
            self.observe(state="stopped", cleanup_confirmed=True)
            return
        cleanup_error = None
        try:
            if self.peer is not None and not self.peer.closed.is_set():
                await self.invoke("stop", None, timeout=self.hub.settings.shutdown_timeout)
                self.observe(cleanup_confirmed=True)
        except Exception as exc:
            self.observe(reason=f"Cleanup not confirmed: {exc}", cleanup_confirmed=False)
            if isinstance(exc, RemoteError) and exc.remote_type != "CancelledError":
                cleanup_error = exc
        finally:
            if self.peer is not None:
                await self.peer.close()
            if self.process is not None:
                try:
                    async with asyncio.timeout(self.hub.settings.shutdown_timeout):
                        await self.process.wait()
                except TimeoutError:
                    self.observe(reason="Core shutdown deadline exceeded; cleanup unconfirmed", cleanup_confirmed=False)
                    try:
                        self.process.kill()
                    except ProcessLookupError:
                        # Still reap and join the monitor before storage closes.
                        pass
                    await self.process.wait()
            if self.monitor is not None:
                await self.monitor
            self.observe(state="stopped", returncode=None if self.process is None else self.process.returncode)
        if cleanup_error is not None:
            raise cleanup_error


class HybridGroup(ModuleGroup):
    def __init__(self, settings: HybridSettings, store):
        super().__init__()
        if not isinstance(settings, HybridSettings):
            raise TypeError("settings must be HybridSettings")
        self.settings = settings
        self.connections = Connections(self, store)
        self.attach_connections(self.connections)
        self.modules = {}
        self.local_nodes = {}
        self.server = None
        self._control_tasks = set()
        self._fatal = None
        self._stopping = False
        self._routes = {}
        self._route_lock = asyncio.Lock()
        self._route_task = None
        self.activities = None

    def enable_activities(self, *, clock_check_interval, max_running=None):
        from .hybrid_tasks import HybridTaskManager
        manager = HybridTaskManager(self, clock_check_interval=clock_check_interval, max_running=max_running)
        self.attach_task_manager(manager)
        self.activities = manager
        return manager

    def register_module(self, spec, advertisement, factory, config, placement):
        config = validate_module_registration(spec, advertisement, factory, config, placement)
        service = _Service(self, spec, advertisement, factory, config, placement)
        update = self.register(spec, service)
        handlers = {}
        for contract in advertisement.contracts:
            handlers[contract.key] = {}
            for operation in contract.operations:
                async def handler(*args, _key=contract.key, _op=operation.name, **kwargs):
                    try:
                        return await service.invoke("invoke", {"contract": _key, "operation": _op, "args": args, "kwargs": kwargs})
                    except (CapacityExceeded, RemoteError) as exc:
                        if isinstance(exc, CapacityExceeded) or exc.remote_type == "CapacityExceeded":
                            return TemporaryUnavailable(str(exc))
                        raise
                handlers[contract.key][operation.name] = handler
        try:
            self.connections.declare(advertisement, handlers)
        except Exception:
            self.unregister(spec.module_id)
            raise
        self.modules[spec.module_id] = service
        return update

    def unregister(self, module_id):
        update = super().unregister(module_id)
        self.modules.pop(module_id, None)
        self.local_nodes.pop(module_id, None)
        if self.connections.state == RuntimeState.NEW:
            self.connections._modules.pop(module_id, None)
            self.connections._specs = {c.key: c for m in self.connections._modules.values()
                                       for c in m.advertisement.contracts}
        return update

    @property
    def port(self):
        return self.server.sockets[0].getsockname()[1]

    def process(self, module_id):
        return self.modules[module_id].snapshot

    async def diagnostics(self, module_id):
        return await self.modules[module_id].invoke("diagnostics", None)

    def client(self, module_id):
        """A local caller uses the same CoreClient without a network hop to its own Core."""
        return self.local_nodes[module_id].context.core

    def fail(self, error):
        if self._fatal is not None and not self._fatal.done() and not self._stopping:
            self._fatal.set_exception(error)

    def _extra_watchers(self):
        return () if self._fatal is None else (self._fatal,)

    def _accept(self, reader, writer):
        task = asyncio.create_task(self._control(reader, writer))
        self._control_tasks.add(task)
        task.add_done_callback(self._control_tasks.discard)

    async def _control(self, reader, writer):
        peer = None
        try:
            async with asyncio.timeout(self.settings.startup_timeout):
                hello = await read_frame(reader, self.settings.max_frame_bytes)
                service = self.modules[hello["module_id"]]
                if (hello.get("version") != VERSION or hello.get("generation") != service.generation
                        or service.placement != Placement.PROCESS or service.peer is not None):
                    raise ProtocolError("Child handshake mismatch")
                await write_frame(writer, encode({"spec": service.spec, "advertisement": service.advertisement,
                                  "factory": service.factory, "config": service.config, "settings": self.settings,
                                  "generation": service.generation}), self.settings.max_frame_bytes)
                async def handle(operation, payload):
                    if operation == "event":
                        return await self._event(service.spec.module_id, payload["kind"], payload["data"])
                    if operation == "core":
                        return await self._core(service.spec.module_id, payload["operation"], payload["payload"])
                    raise ProtocolError("Unknown control request")
                peer = RpcPeer(reader, writer, generation=service.generation, module_id="core",
                               settings=self.settings, handler=handle)
                service.peer = peer
            await peer.closed.wait()
            if not self._stopping:
                self.fail(PeerClosed(f"{service.spec.module_id} lost its Core management channel"))
                if not service.ready.done():
                    service.ready.set_exception(PeerClosed("Child initialization connection lost"))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.fail(exc)
        finally:
            if peer is not None:
                await peer.close()
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _event(self, module_id, kind, data):
        service = self.modules[module_id]
        if kind == "ready":
            if (data["advertisement"] != service.advertisement
                    or os.path.normcase(os.path.realpath(data["executable"])) != os.path.normcase(os.path.realpath(sys.executable))
                    or os.path.normcase(data["prefix"]) != os.path.normcase(sys.prefix)
                    or type(data["port"]) is not int or not 0 < data["port"] < 65536):
                raise ProtocolError("Child environment or contract mismatch")
            service.port, service.executors = data["port"], data["executors"]
            service.observe(state="ready")
            if not service.ready.done():
                service.ready.set_result(None)
        elif kind == "run_finished":
            if not service.finished.done():
                if data["error"] is not None:
                    service.finished.set_exception(data["error"])
                else:
                    service.finished.set_result(data["result"])
        elif kind == "activity":
            if self.activities is None:
                raise ProtocolError("TaskManager is not attached")
            return await self.activities._remote_event(module_id, data)
        elif kind == "start_failed":
            if not service.ready.done():
                service.ready.set_exception(data)
        else:
            raise ProtocolError("Unknown module event")

    async def start(self):
        self._fatal = _future()
        self.server = await start_server(self._accept, "127.0.0.1", 0)
        self.connections.store.append("hybrid_configuration", {"modules": [
            {"module_id": name, "placement": s.placement.value, "factory": s.factory, "config": s.config,
             "implementation_version": s.advertisement.implementation_version}
            for name, s in sorted(self.modules.items())]})
        await super().start()
        self._route_task = asyncio.create_task(self._watch_routes(), name="ntk-route-updates")

    async def _watch_routes(self):
        try:
            while not self._stopping:
                changed, storage = self.connections._changed, self.connections.store._changed
                await self._sync_routes()
                await self.connections._wait_changes(changed, storage)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.fail(exc)

    async def _sync_routes(self):
        async with self._route_lock:
            for key, route in self._routes.items():
                binding = self.connections._bindings.get(key)
                valid = binding is not None and self.connections._is_ready(binding) and not self._stopping
                if route["valid"] != valid:
                    route["valid"] = valid
                    for module_id in {key.requester_id, route["provider_id"]}:
                        await self.modules[module_id].invoke("route", dict(route))

    async def _core(self, module_id, operation, payload):
        core = self.connections
        if operation == "stream_event":
            core.store.append("hybrid_stream", {"module_id": module_id, **payload})
            return None
        if operation == "candidates":
            return core.candidates(payload)
        if operation == "usage":
            core.publish_usage(module_id, payload["usage"], contracts=payload["contracts"])
            return None
        if operation == "bind":
            return await core.bind(module_id, payload["contract"], payload["provider_id"], wait_timeout=payload["timeout"])
        if operation == "prepare":
            key = BindingKey(module_id, payload["contract"])
            prepared = await core.prepare(key, wait_timeout=payload["timeout"])
            async with self._route_lock:
                route = self._routes.get(key)
                if route is None:
                    provider = self.modules[prepared.snapshot.provider_id]
                    contract = next(c for c in provider.advertisement.contracts if c.key == key.contract)
                    route = {"token": uuid4().hex, "generation": provider.generation, "port": provider.port,
                             "requester_id": module_id, "provider_id": provider.spec.module_id,
                             "contract": key.contract, "operations": tuple(op.name for op in contract.operations), "valid": True}
                    self._routes[key] = route
                route["valid"] = True
                for owner in {module_id, route["provider_id"]}:
                    await self.modules[owner].invoke("route", dict(route))
                return dict(route)
        if operation == "invoke":
            prepared = await core.prepare(BindingKey(module_id, payload["contract"]), wait_timeout=payload["timeout"])
            prepared._handler(payload["operation"], OperationMode.ASYNC)
            try:
                return await self.modules[prepared.snapshot.provider_id].invoke("invoke", {
                    k: payload[k] for k in ("contract", "operation", "args", "kwargs")}, timeout=payload["timeout"])
            except (OutcomeUnknown, TimeoutError, ProtocolError):
                raise
            except (CapacityExceeded, RemoteError) as exc:
                if isinstance(exc, CapacityExceeded) or exc.remote_type == "CapacityExceeded":
                    return TemporaryUnavailable(str(exc))
                result = prepared._failed(exc)
            except Exception as exc:
                result = prepared._failed(exc)
            await self._sync_routes()
            return result
        if operation == "health":
            result = await core.health_check(**payload)
            await self._sync_routes()
            return result
        if operation == "notice":
            return await core.next_notice(module_id)
        if operation == "acknowledge":
            result = core.acknowledge_interruption(module_id, payload)
            await self._sync_routes()
            return result
        if operation == "link_error":
            result = core.report_link_error(BindingKey(module_id, payload["contract"]), payload["error"])
            await self._sync_routes()
            return result
        if operation.startswith("activity_"):
            if self.activities is None:
                raise ProtocolError("TaskManager is not enabled")
            return await self.activities._client(module_id, operation, payload)
        raise ProtocolError("Unknown Core operation")

    async def stop(self):
        self._stopping = True
        if self.server is not None:
            self.server.close()
        guardians = [asyncio.create_task(s.force_after_deadline()) for s in self.modules.values() if s.process is not None]
        if self._route_task is not None:
            self._route_task.cancel()
            await asyncio.gather(self._route_task, return_exceptions=True)
        try:
            await super().stop()
        finally:
            for task in guardians:
                task.cancel()
            await asyncio.gather(*guardians, return_exceptions=True)
            for task in tuple(self._control_tasks):
                task.cancel()
            await asyncio.gather(*tuple(self._control_tasks), return_exceptions=True)
            if self.server is not None:
                await self.server.wait_closed()
            if self._fatal is not None and not self._fatal.done():
                self._fatal.cancel()
