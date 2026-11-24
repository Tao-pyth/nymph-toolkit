"""Sleep activity progress and explicit reconciliation; see ADR 0038."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

SLEEP_ACTIVITY_KEY = ContractKey("ntk.sleep.activities", "1")
SLEEP_ACTIVITY_CONTRACT = ContractSpec(SLEEP_ACTIVITY_KEY, tuple(
    OperationSpec(name, OperationMode.ASYNC) for name in ("get", "reconcile", "apply")
))

__all__ = ["SLEEP_ACTIVITY_KEY", "SLEEP_ACTIVITY_CONTRACT"]
