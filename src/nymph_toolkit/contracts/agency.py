"""Agency-owned activity decisions, separate from Core execution and approval."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

AGENCY_KEY = ContractKey("ntk.agency.decisions", "1")
AGENCY_CONTRACT = ContractSpec(AGENCY_KEY, (
    OperationSpec("decide", OperationMode.ASYNC), OperationSpec("get", OperationMode.ASYNC),
))

AGENCY_ACTIVITIES_KEY = ContractKey("ntk.agency.activities", "1")
AGENCY_ACTIVITIES_CONTRACT = ContractSpec(AGENCY_ACTIVITIES_KEY, tuple(
    OperationSpec(name, OperationMode.ASYNC)
    for name in ("activate", "observe", "status", "halt", "history")
))

__all__ = ["AGENCY_KEY", "AGENCY_CONTRACT", "AGENCY_ACTIVITIES_KEY", "AGENCY_ACTIVITIES_CONTRACT"]
