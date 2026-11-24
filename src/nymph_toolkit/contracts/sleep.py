"""Sleep-owned consolidation and traceable cycle results; see ADR 0037."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

SLEEP_KEY = ContractKey("ntk.sleep.consolidation", "1")
SLEEP_CONTRACT = ContractSpec(SLEEP_KEY, tuple(
    OperationSpec(name, OperationMode.ASYNC) for name in ("cycle", "get", "state", "inspect")
))

__all__ = ["SLEEP_KEY", "SLEEP_CONTRACT"]
