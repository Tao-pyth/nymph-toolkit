"""Function-side Core requests and cached, authorized direct data endpoints."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from uuid import uuid4

from nymph_toolkit.contracts import (BindingKey, CapacityExceeded, ConnectionNotReadyError, LinkFailure,
                                    OutcomeUnknown, PeerClosed, ProtocolError, RemoteError, TemporaryUnavailable)
from ._rpc import RpcPeer
from ._net import open_connection
from ._streams import StreamSender
from ._wire import VERSION, encode, json_value, read_frame, write_frame
from nymph_toolkit.contracts.hybrid import seconds


class CoreClient:
    def __init__(self, context, dispatch):
        self.context, self._dispatch = context, dispatch
        self._result_peer = None

    @property
    def pending_requests(self):
        """RPC IDs owned by this client, including completed retained results."""
        return () if self._result_peer is None else tuple(self._result_peer._pending)

    def result(self, request_id):
        if self._result_peer is None:
            raise KeyError(request_id)
        return self._result_peer.result(request_id)

    def release(self, request_id):
        if self._result_peer is None:
            raise KeyError(request_id)
        self._result_peer.release(request_id)

    async def request(self, operation, payload=None, *, timeout=None):
        timeout = self.context.settings.call_timeout if timeout is None else timeout
        seconds(timeout)
        return await self._dispatch(operation, payload, timeout)

    async def candidates(self, contract, *, timeout=None):
        return await self.request("candidates", contract, timeout=timeout)

    async def bind(self, contract, provider_id, *, timeout):
        return await self.request("bind", {"contract": contract, "provider_id": provider_id, "timeout": timeout}, timeout=timeout)

    async def prepare(self, contract, *, timeout):
        route = await self.request("prepare", {"contract": contract, "timeout": timeout}, timeout=timeout)
        current = self.context.routes.setdefault(route["token"], route)
        current.update(route)
        return DirectLink(self, current)

    async def invoke(self, contract, operation, *args, timeout, **kwargs):
        return await self.request("invoke", {"contract": contract, "operation": operation,
                                             "args": json_value(args), "kwargs": json_value(kwargs), "timeout": timeout}, timeout=timeout)

    async def publish_usage(self, usage, *, contracts=None, timeout=None):
        return await self.request("usage", {"usage": usage, "contracts": contracts}, timeout=timeout)

    async def health_check(self, *, module_ids=None, bindings=None, timeout=None):
        return await self.request("health", {"module_ids": module_ids, "bindings": bindings}, timeout=timeout)

    async def next_notice(self, *, timeout):
        return await self.request("notice", timeout=timeout)

    async def acknowledge_interruption(self, notice_id, *, timeout=None):
        return await self.request("acknowledge", notice_id, timeout=timeout)

    async def submit_remote(self, request, module_id, executor_id, arguments=None, *, timeout=None):
        return await self.request("activity_submit", {"request": request, "module_id": module_id,
                                   "executor_id": executor_id, "arguments": json_value(arguments)}, timeout=timeout)

    async def activity(self, operation, key=None, *, timeout=None, **arguments):
        """snapshot/change/pause/resume/finish/wait/command/notice/history; no decisions."""
        return await self.request("activity_" + operation, {"key": key, **arguments}, timeout=timeout)


class DirectLink:
    def __init__(self, client, route):
        self.client, self.route = client, route
        self._peer = None
        self._connect_lock = asyncio.Lock()

    def _check(self, operation):
        if not self.route["valid"]:
            raise ConnectionNotReadyError("Core marked this binding unavailable; prepare again")
        if operation not in self.route["operations"]:
            raise ValueError("Operation is not in the prepared contract")

    async def _connect(self, kind, *, timeout, **extra):
        context = self.client.context
        async with asyncio.timeout(timeout):
            reader, writer = await open_connection("127.0.0.1", self.route["port"])
            try:
                await write_frame(writer, {"version": VERSION, "generation": self.route["generation"],
                                          "token": self.route["token"], "kind": kind, **extra}, context.settings.max_frame_bytes)
                response = await read_frame(reader, context.settings.max_frame_bytes)
                if response != {"ready": True}:
                    if isinstance(response, dict) and response.get("error") == "CapacityExceeded":
                        raise CapacityExceeded(response.get("message", "Stream capacity exhausted"))
                    raise ConnectionNotReadyError(str(response))
            except BaseException:
                writer.close()
                await writer.wait_closed()
                raise
        return reader, writer

    async def acall(self, operation, *args, timeout, **kwargs):
        seconds(timeout)
        self._check(operation)
        context = self.client.context
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            if context.local_hub is not None and self.route["provider_id"] in context.local_hub.local_nodes:
                node = context.local_hub.local_nodes[self.route["provider_id"]]
                async with asyncio.timeout(timeout):
                    return await node.invoke(self.route["contract"], operation, args, kwargs)
            async with asyncio.timeout(timeout):
                async with self._connect_lock:
                    if self._peer is None:
                        reader, writer = await self._connect("rpc", timeout=timeout)
                        self._peer = RpcPeer(reader, writer, generation=self.route["generation"], module_id=context.module_id,
                                             settings=context.settings, handler=context.reject)
                        context.peers.add(self._peer)
                    elif self._peer.closed.is_set():
                        raise PeerClosed("Direct channel closed; explicitly prepare after health recovery")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Call deadline expired before dispatch")
            return await self._peer.call(operation, {"args": json_value(args), "kwargs": json_value(kwargs)}, timeout=remaining)
        except asyncio.CancelledError:
            raise
        except (OutcomeUnknown, TimeoutError, ProtocolError):
            raise
        except Exception as exc:
            if isinstance(exc, CapacityExceeded) or isinstance(exc, RemoteError) and exc.remote_type == "CapacityExceeded":
                return TemporaryUnavailable(str(exc))
            notice = await self.client.request("link_error", {"contract": self.route["contract"], "error": exc})
            return LinkFailure(BindingKey(context.module_id, self.route["contract"]), exc, notice)

    async def open_stream(self, operation, options, metadata=None, *, timeout):
        seconds(timeout)
        self._check(operation)
        context = self.client.context
        context.reserve_stream()
        sender = None
        try:
            stream_id = uuid4().hex
            reader, writer = await self._connect("stream", timeout=timeout, operation=operation,
                                                 options=encode(options), metadata=json_value(metadata), stream_id=stream_id)
            sender = StreamSender(reader, writer, options)
            await context.own_sender(sender, self.route, stream_id)
            return sender
        except BaseException:
            if sender is not None:
                await sender.aclose()
                context.streams.discard(sender)
            raise
        finally:
            context.opening_streams -= 1

    @property
    def pending_requests(self):
        return () if self._peer is None else tuple(self._peer._pending)

    def result(self, request_id):
        if self._peer is None:
            raise KeyError(request_id)
        return self._peer.result(request_id)

    def release(self, request_id):
        if self._peer is None:
            raise KeyError(request_id)
        self._peer.release(request_id)

    async def close(self):
        if self._peer is not None:
            await self._peer.close()
            self.client.context.peers.discard(self._peer)
