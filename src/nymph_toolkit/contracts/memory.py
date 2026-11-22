"""Memory record RPC declarations; payload semantics are specified by ADR 0027."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

MEMORY_KEY = ContractKey("ntk.memory.records", "1")
MEMORY_CONTRACT = ContractSpec(MEMORY_KEY, tuple(
    OperationSpec(name, OperationMode.ASYNC) for name in ("put", "get", "query")
))

__all__ = ["MEMORY_KEY", "MEMORY_CONTRACT"]
