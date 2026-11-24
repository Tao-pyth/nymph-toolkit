"""A public-contract client that reads and explicitly updates Persona traits."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import ContractKey, ContractSpec, OperationMode, OperationSpec, OperatingState, Usage
from nymph_toolkit.contracts.persona import PERSONA_KEY

CONTROL_KEY = ContractKey("example.persona.requester", "1")
CONTROL_CONTRACT = ContractSpec(CONTROL_KEY, (OperationSpec("exercise", OperationMode.ASYNC),))


def update_request():
    return dict(command_id="experience-1", expected_revision=0,
                deltas={"curiosity": 100, "sociability": -50}, reason="明示した経験の評価結果を反映する例",
                source={"actor_id": "example-client", "reference": "example:experience-1"})


class Requester:
    def __init__(self, context, config):
        self.context = context
        context.provide(CONTROL_KEY, {"exercise": self.exercise})

    async def start(self):
        usage = Usage(OperatingState.RUNNING, True, 0, 1)
        await self.context.core.publish_usage(usage, contracts={CONTROL_KEY: usage})

    async def run(self):
        await asyncio.Event().wait()

    async def stop(self):
        pass

    async def exercise(self, restored=False):
        core = self.context.core
        assert any(c.advertisement.module_id == "persona" for c in await core.candidates(PERSONA_KEY))
        await core.bind(PERSONA_KEY, "persona", timeout=5)
        link = await core.prepare(PERSONA_KEY, timeout=5)
        try:
            before = await link.acall("get", timeout=5)
            request = update_request()
            receipt = await core.invoke(PERSONA_KEY, "apply", request, timeout=5)
            assert isinstance(receipt, dict), receipt
            assert receipt["revision"] == 1 and receipt["status"] == "applied"
            assert receipt["before"] == {"curiosity": 500, "sociability": 400}
            assert receipt["after"] == {"curiosity": 600, "sociability": 350}
            assert await link.acall("apply", request, timeout=5) == receipt
            current = await core.invoke(PERSONA_KEY, "get", timeout=5)
            assert current["traits"] == receipt["after"] and current["revision"] == 1
            if restored:
                assert before == current
            else:
                assert before["revision"] == 0
            zero = dict(request, command_id="no-change", expected_revision=1, deltas={"curiosity": 0})
            unchanged = await link.acall("apply", zero, timeout=5)
            assert unchanged["status"] == "no_change" and unchanged["revision"] == 1
            assert await core.invoke(PERSONA_KEY, "get_update", request["command_id"], timeout=5) == receipt
            assert (await link.acall("apply", dict(request, reason="different"), timeout=5)).code == "persona.command_conflict"
            assert (await link.acall("apply", dict(request, command_id="stale"), timeout=5)).code == "persona.revision_conflict"
            assert (await link.acall("apply", dict(request, command_id="invalid", expected_revision=1,
                                                  deltas={"curiosity": 1000}), timeout=5)).code == "persona.invalid"
            page = await link.acall("history", timeout=5)
            assert page == await core.invoke(PERSONA_KEY, "history", timeout=5)
            assert page["updates"] == [receipt, unchanged]
            assert await link.acall("get", timeout=5) == current
            return dict(current=current, receipt=receipt, updates=2, restored=restored, routes="direct+core")
        finally:
            await link.close()


def factory(context, config):
    return Requester(context, config)
