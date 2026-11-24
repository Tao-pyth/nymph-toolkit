"""HTTP observations saved through a selected public Memory contract."""

# SPDX-License-Identifier: Apache-2.0
from nymph_toolkit.contracts import ModuleContextProtocol, OperationFailure, RuntimeService
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.contracts.web import WEB_CONTRACT
from .._interaction import InputAdapter, provider_id, snapshot
from ._reader import origins, read_record

__all__ = ["factory"]


class _Web(InputAdapter):
    def __init__(self, context, config):
        if type(config) is not dict or set(config) != {"memory_module_id", "allowed_origins"}:
            raise ValueError("Web requires memory_module_id and allowed_origins")
        self.allowed = origins(config["allowed_origins"])
        super().__init__(context, WEB_CONTRACT, {"ingest": self.ingest},
                         {MEMORY_CONTRACT.key: provider_id(config["memory_module_id"])}, worker=True)

    async def ingest(self, request):
        try:
            request = snapshot(request)
        except (TypeError, ValueError, RecursionError) as error:
            return OperationFailure("web.invalid", str(error))
        return await self.submit(self._ingest, request)

    async def _ingest(self, request):
        record = await self.work(read_record, request, self.allowed)
        if isinstance(record, OperationFailure):
            return record
        return await self.forward(MEMORY_CONTRACT, "put", [record], {})


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Web(context, config)
