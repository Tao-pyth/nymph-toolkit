"""A dummy module with observable shared lifecycle order and controllable failures."""

# SPDX-License-Identifier: Apache-2.0
from .service import Service


class Module(Service):
    def __init__(self, module_id, trace, **kwargs):
        super().__init__(**kwargs)
        self.module_id = module_id
        self.trace = trace

    async def _phase(self, phase):
        self.trace.append((self.module_id, phase))
        await super()._phase(phase)

    async def run(self):
        await super().run()
        return self.module_id
