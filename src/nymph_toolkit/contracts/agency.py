"""Agency-owned activity decisions, separate from Core execution and approval."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

AGENCY_KEY = ContractKey("ntk.agency.decisions", "1")
AGENCY_CONTRACT = ContractSpec(AGENCY_KEY, (
    OperationSpec("decide", OperationMode.ASYNC), OperationSpec("get", OperationMode.ASYNC),
))

__all__ = ["AGENCY_KEY", "AGENCY_CONTRACT"]
