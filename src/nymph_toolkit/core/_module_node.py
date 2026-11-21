"""A function's local execution state; authoritative Core state stays in the parent."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import importlib
import inspect

from nymph_toolkit.contracts import CapacityExceeded, ProtocolError, RemoteError, StreamOptions, StreamState
from ._hybrid_client import CoreClient
from ._rpc import RpcPeer
from ._streams import StreamReceiver
from ._wire import VERSION, decode, read_frame, write_frame


class ModuleContext:
    def __init__(self, module_id, generation, settings, dispatch, local_hub=None):
        self.module_id, self.generation, self.settings = module_id, generation, settings
        self.local_hub = local_hub
        self.core = CoreClient(self, dispatch)
        self.handlers, self.stream_handlers, self.executors = {}, {}, {}
        self.routes = {}
        self.peers, self.streams = set(), set()
        self.owned = set()
        self.opening_streams = 0

    def provide(self, contract, handlers):
        for name, handler in handlers.items():
            if not callable(handler) or (contract, name) in self.handlers:
                raise ValueError("Invalid or duplicate operation handler")
            self.handlers[contract, name] = handler

    def provide_stream(self, contract, operation, handler):
        if not callable(handler) or (contract, operation) in self.stream_handlers:
            raise ValueError("Invalid or duplicate stream handler")
        self.stream_handlers[contract, operation] = handler

    def provide_executor(self, executor_id, handler, *, supports_pause=False):
        if not isinstance(executor_id, str) or not executor_id or executor_id in self.executors or not callable(handler):
            raise ValueError("Invalid or duplicate executor ID")
        if type(supports_pause) is not bool:
            raise TypeError("supports_pause must be bool")
        self.executors[executor_id] = (handler, supports_pause)

    def check_stream_capacity(self):
        active = sum(s.state in (StreamState.OPEN, StreamState.CLOSING) for s in self.streams)
        if active + self.opening_streams >= self.settings.max_streams:
            raise CapacityExceeded("Open stream limit reached")

    def reserve_stream(self):
        self.check_stream_capacity()
        self.opening_streams += 1

    async def own_sender(self, sender, route, stream_id):
        self.streams.add(sender)
        def record(phase):
            return {"stream_id": stream_id, "provider_id": route["provider_id"],
                    "contract_id": route["contract"].contract_id, "contract_version": route["contract"].version,
                    "phase": phase, "state": sender.state.value, "reason": sender.reason,
                    "accepted_chunks": sender._last, "dropped_chunks": sender.dropped_chunks,
                    "buffered_bytes": sender.buffered_bytes, "buffered_chunks": sender.buffered_chunks}
        await self.core.request("stream_event", record("opened"))
        async def watch():
            try:
                while sender.state in (StreamState.OPEN, StreamState.CLOSING):
                    await sender._changed.wait()
                if sender.state == StreamState.FAILED:
                    await self.core.request("link_error", {"contract": route["contract"],
                                            "error": RemoteError(route["provider_id"], "StreamFailure", sender.reason)})
            finally:
                await sender.aclose()
                try:
                    await self.core.request("stream_event", record("ended"))
                finally:
                    self.streams.discard(sender)
        task = asyncio.create_task(watch(), name="ntk-stream-owner")
        self.owned.add(task)
        def done(t):
            self.owned.discard(t)
            if not t.cancelled():
                t.exception()
        task.add_done_callback(done)

    async def reject(self, operation, payload):
        raise ProtocolError("Unsolicited data request")


class ModuleNode:
    def __init__(self, spec, advertisement, factory, config, generation, settings, dispatch, event, local_hub=None,
                 *, report_failed=None):
        self.spec, self.advertisement = spec, advertisement
        self.factory, self.config = factory, config
        self.generation, self.settings, self.event = generation, settings, event
        self.report_failed = report_failed if report_failed is not None else local_hub.fail
        self.context = ModuleContext(spec.module_id, generation, settings, dispatch, local_hub)
        self.service = self.server = self.run_task = None
        self.tasks = set()
        self.started = False
        self.stopped = False
        self.activity_runner = None
        self.active_calls = 0

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        def done(t):
            self.tasks.discard(t)
            if not t.cancelled():
                t.exception()
        task.add_done_callback(done)
        return task

    async def start(self):
        module, attribute = self.factory.split(":", 1)
        factory = getattr(importlib.import_module(module), attribute)
        self.service = factory(self.context, self.config)
        if inspect.isawaitable(self.service):
            self.service = await self.service
        if not all(callable(getattr(self.service, key, None)) for key in ("start", "run", "stop")):
            raise TypeError("Factory must return a lifecycle service")
        self.server = await asyncio.start_server(lambda r, w: self.spawn(self._accept(r, w)), "127.0.0.1", 0)
        await self.service.start()
        declared = {(spec.key, operation.name) for spec in self.advertisement.contracts for operation in spec.operations}
        actual = set(self.context.handlers) | set(self.context.stream_handlers)
        if declared != actual or set(self.context.handlers) & set(self.context.stream_handlers):
            raise ProtocolError("Declared operations must match exactly one operation or stream handler")
        self.started = True

    @property
    def port(self):
        return self.server.sockets[0].getsockname()[1]

    async def invoke(self, contract, operation, args, kwargs):
        if self.active_calls >= self.settings.max_requests:
            raise CapacityExceeded("Function operation limit reached")
        handler = self.context.handlers[contract, operation]
        self.active_calls += 1
        try:
            result = handler(*args, **kwargs)
            if not inspect.isawaitable(result):
                raise TypeError("Hybrid operations must be async")
            return await result
        finally:
            self.active_calls -= 1

    async def _accept(self, reader, writer):
        peer = receiver = None
        reserved = False
        try:
            async with asyncio.timeout(self.settings.startup_timeout):
                message = await read_frame(reader, self.settings.max_frame_bytes)
                if not isinstance(message, dict) or message.get("version") != VERSION or message.get("generation") != self.generation:
                    raise ProtocolError("Invalid data handshake")
                route = self.context.routes.get(message.get("token"))
                if route is None or not route["valid"] or route["provider_id"] != self.spec.module_id:
                    raise ProtocolError("Binding has not been permitted by Core")
                if message.get("kind") == "rpc":
                    async def operation(name, payload):
                        if not route["valid"] or name not in route["operations"]:
                            raise ProtocolError("Prepared route is unavailable")
                        return await self.invoke(route["contract"], name, payload["args"], payload["kwargs"])
                    await write_frame(writer, {"ready": True}, self.settings.max_frame_bytes)
                    peer = RpcPeer(reader, writer, generation=self.generation, module_id=self.spec.module_id,
                                   settings=self.settings, handler=operation)
                    self.context.peers.add(peer)
                elif message.get("kind") == "stream":
                    stream_id = message.get("stream_id")
                    if not isinstance(stream_id, str) or len(stream_id) != 32:
                        raise ProtocolError("Invalid stream ID")
                    self.context.reserve_stream()
                    reserved = True
                    options = decode(message["options"])
                    if not isinstance(options, StreamOptions):
                        raise ProtocolError("Invalid stream options")
                    handler = self.context.stream_handlers[route["contract"], message["operation"]]
                    await write_frame(writer, {"ready": True}, self.settings.max_frame_bytes)
                    receiver = StreamReceiver(reader, writer, options)
                    self.context.streams.add(receiver)
                    self.context.opening_streams -= 1
                    reserved = False
                else:
                    raise ProtocolError("Unknown data channel")
            if peer is not None:
                await peer.closed.wait()
            else:
                await handler(receiver, message.get("metadata"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if receiver is None and peer is None:
                try:
                    await write_frame(writer, {"error": type(exc).__name__, "message": str(exc)}, self.settings.max_frame_bytes)
                except (Exception, asyncio.CancelledError):
                    pass
            elif receiver is not None:
                await receiver.fail(str(exc)[:512] or type(exc).__name__)
        finally:
            if reserved:
                self.context.opening_streams -= 1
            if receiver is not None:
                await receiver.aclose()
                self.context.streams.discard(receiver)
            if peer is not None:
                await peer.close()
                self.context.peers.discard(peer)
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ConnectionError):
                pass

    async def _run(self):
        try:
            result = await self.service.run()
            await self.event("run_finished", {"result": result, "error": None})
        except asyncio.CancelledError:
            if not self.stopped:
                await self.event("run_finished", {"result": None, "error": RemoteError(self.spec.module_id, "CancelledError", "Unexpected service cancellation")})
        except Exception as exc:
            await self.event("run_finished", {"result": None, "error": RemoteError(self.spec.module_id, type(exc).__name__, str(exc))})

    async def dispatch(self, operation, payload):
        if operation == "run_start":
            if self.run_task is not None or not self.started:
                raise ProtocolError("Invalid run transition")
            self.run_task = self.spawn(self._run())
        elif operation == "route":
            self.context.routes.setdefault(payload["token"], {}).update(payload)
        elif operation == "invoke":
            return await self.invoke(payload["contract"], payload["operation"], payload["args"], payload["kwargs"])
        elif operation == "stop":
            await self.stop()
        elif operation == "diagnostics":
            return {"active_calls": self.active_calls, "opening_streams": self.context.opening_streams,
                    "pending_calls": sum(sum(not f.done() for f in p._pending.values()) for p in self.context.peers),
                    "streams": [{"state": s.state.value, "buffered_bytes": s.buffered_bytes,
                                 "buffered_chunks": s.buffered_chunks, "dropped_chunks": getattr(s, "dropped_chunks", 0)}
                                for s in self.context.streams]}
        elif operation.startswith("activity_"):
            if self.activity_runner is None:
                from ._remote_activity import ExecutorHost
                self.activity_runner = ExecutorHost(self)
            return await self.activity_runner.dispatch(operation, payload)
        else:
            raise ProtocolError("Unknown module operation")

    async def stop(self):
        if self.stopped:
            return
        self.stopped = True
        if self.server is not None:
            self.server.close()
        tasks = self.tasks - {asyncio.current_task()}
        for task in tasks:
            task.cancel()
        if self.activity_runner is not None:
            await self.activity_runner.stop()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(p.close() for p in tuple(self.context.peers)), return_exceptions=True)
        await asyncio.gather(*(s.aclose() for s in tuple(self.context.streams)), return_exceptions=True)
        for task in tuple(self.context.owned):
            task.cancel()
        await asyncio.gather(*tuple(self.context.owned), return_exceptions=True)
        if self.service is not None:
            await self.service.stop()
        if self.server is not None:
            await self.server.wait_closed()
