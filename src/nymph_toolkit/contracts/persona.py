"""Persona traits and externally requested changes; see ADR 0035."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

PERSONA_KEY = ContractKey("ntk.persona.traits", "1")
PERSONA_CONTRACT = ContractSpec(PERSONA_KEY, tuple(
    OperationSpec(name, OperationMode.ASYNC) for name in ("get", "apply", "get_update", "history")
))

__all__ = ["PERSONA_KEY", "PERSONA_CONTRACT"]
