"""Explicit textual observations and teaching, connected through public Contracts."""

# SPDX-License-Identifier: Apache-2.0
from nymph_toolkit.contracts import ModuleContextProtocol, OperationFailure, RuntimeService
from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT
from nymph_toolkit.contracts.cognition_revision import COGNITION_REVISION_CONTRACT
from nymph_toolkit.contracts.memory import MEMORY_CONTRACT
from nymph_toolkit.contracts.text_interaction import TEXT_INTERACTION_CONTRACT
from .._interaction import InputAdapter, provider_id, snapshot

__all__ = ["factory"]


class _TextInteraction(InputAdapter):
    def __init__(self, context, config):
        if type(config) is not dict or set(config) != {"memory_module_id", "cognition_module_id"}:
            raise ValueError("Text Interaction requires memory_module_id and cognition_module_id")
        memory, cognition = (provider_id(config[k]) for k in ("memory_module_id", "cognition_module_id"))
        super().__init__(context, TEXT_INTERACTION_CONTRACT,
                         {name: getattr(self, name) for name in ("observe", "learn", "inspect", "correct", "get_revision")},
                         {MEMORY_CONTRACT.key: memory, COGNITION_CONTRACT.key: cognition,
                          COGNITION_REVISION_CONTRACT.key: cognition})

    async def _request(self, contract, operation, *args, **kwargs):
        try:
            args, kwargs = snapshot([list(args), kwargs])
        except (TypeError, ValueError, RecursionError) as error:
            return OperationFailure("text.invalid", str(error))
        return await self.submit(self.forward, contract, operation, args, kwargs)

    async def observe(self, record):
        return await self._request(MEMORY_CONTRACT, "put", record)

    async def learn(self, record_id, *, tokens, concepts):
        return await self._request(COGNITION_CONTRACT, "learn", record_id, tokens=tokens, concepts=concepts)

    async def inspect(self, token, *, source_kind=None, after=0, limit=8):
        return await self._request(COGNITION_CONTRACT, "inspect", token, source_kind=source_kind, after=after, limit=limit)

    async def correct(self, record_id, *, command_id, expected_revision, tokens, concepts):
        return await self._request(COGNITION_REVISION_CONTRACT, "correct", record_id, command_id=command_id,
                                   expected_revision=expected_revision, tokens=tokens, concepts=concepts)

    async def get_revision(self, record_id):
        return await self._request(COGNITION_REVISION_CONTRACT, "get_revision", record_id)


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _TextInteraction(context, config)
