"""Side-effect-free validation shared by tooling and real registration."""

# SPDX-License-Identifier: Apache-2.0
from nymph_toolkit.contracts import ModuleAdvertisement, ModuleSpec, OperationMode, Placement
from ._wire import json_value


def validate_module_registration(spec, advertisement, factory, config, placement):
    """Validate a Hybrid module description and return an independent JSON config.

    Does not import the factory, register modules, open resources or check live
    availability. Start and contract tests must verify the actual implementation.
    """
    if not isinstance(spec, ModuleSpec):
        raise TypeError("spec must be ModuleSpec")
    if not isinstance(advertisement, ModuleAdvertisement) or advertisement.module_id != spec.module_id:
        raise ValueError("Advertisement must match module ID")
    if not isinstance(placement, Placement):
        raise TypeError("placement must be explicit")
    if not isinstance(factory, str) or factory.count(":") != 1 or not all(factory.split(":")):
        raise ValueError("factory must be an importable module:attribute")
    if any(op.mode != OperationMode.ASYNC for c in advertisement.contracts for op in c.operations):
        raise ValueError("Hybrid declarations require ASYNC; existing sync declarations must not be reinterpreted")
    return json_value(config)
