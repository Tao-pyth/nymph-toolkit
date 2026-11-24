"""Explicit HTTP text acquisition into Memory records/1; ADR 0031."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

WEB_KEY = ContractKey("ntk.web.import", "1")
WEB_CONTRACT = ContractSpec(WEB_KEY, (OperationSpec("ingest", OperationMode.ASYNC),))

__all__ = ["WEB_KEY", "WEB_CONTRACT"]
