"""Internal child entry point. Only Core supplies the bootstrap and lifecycle."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import sys

from nymph_toolkit.contracts import RemoteError
from ._module_node import ModuleNode
from ._rpc import RpcPeer
from ._wire import VERSION, decode, read_frame, write_frame


async def main(port, module_id, generation):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    # Bootstrap has a fixed ceiling; negotiated RPC limit follows immediately.
    await write_frame(writer, {"version": VERSION, "module_id": module_id, "generation": generation}, 1048576)
    bootstrap = decode(await read_frame(reader, 1048576))
    if bootstrap["generation"] != generation or bootstrap["spec"].module_id != module_id:
        raise ValueError("Bootstrap identity mismatch")
    peer = None
    async def dispatch(operation, payload, timeout):
        return await peer.call("core", {"operation": operation, "payload": payload}, timeout=timeout)
    async def event(kind, data):
        return await peer.call("event", {"kind": kind, "data": data}, timeout=bootstrap["settings"].call_timeout)
    node = ModuleNode(**bootstrap, dispatch=dispatch, event=event, report_failed=lambda error: writer.close())
    peer = RpcPeer(reader, writer, generation=generation, module_id=module_id,
                   settings=bootstrap["settings"], handler=node.dispatch)
    try:
        try:
            await node.start()
            await event("ready", {"advertisement": node.advertisement, "port": node.port,
                                  "executable": sys.executable, "prefix": sys.prefix,
                                  "executors": {k: pause for k, (_, pause) in node.context.executors.items()}})
        except Exception as exc:
            await event("start_failed", RemoteError(module_id, type(exc).__name__, str(exc)))
            return
        await peer.closed.wait()
    finally:
        await node.stop()
        await peer.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), sys.argv[2], sys.argv[3]))
