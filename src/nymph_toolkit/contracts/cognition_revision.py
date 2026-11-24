"""Explicit annotation revision, independent of the stable learning/1 contract."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

COGNITION_REVISION_KEY = ContractKey("ntk.cognition.revision", "1")
COGNITION_REVISION_CONTRACT = ContractSpec(COGNITION_REVISION_KEY, (
    OperationSpec("correct", OperationMode.ASYNC),
    OperationSpec("get_revision", OperationMode.ASYNC),
))

__all__ = ["COGNITION_REVISION_KEY", "COGNITION_REVISION_CONTRACT"]
