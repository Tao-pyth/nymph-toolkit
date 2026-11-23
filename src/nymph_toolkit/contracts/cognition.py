"""Initial evidence-backed learning contract; distinct from natural-language understanding."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

COGNITION_KEY = ContractKey("ntk.cognition.learning", "1")
COGNITION_CONTRACT = ContractSpec(COGNITION_KEY, (
    OperationSpec("learn", OperationMode.ASYNC), OperationSpec("inspect", OperationMode.ASYNC),
))

__all__ = ["COGNITION_KEY", "COGNITION_CONTRACT"]
