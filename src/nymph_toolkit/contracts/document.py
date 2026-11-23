"""Document import declaration; payload semantics are specified by ADR 0028."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

DOCUMENT_KEY = ContractKey("ntk.document.import", "1")
DOCUMENT_CONTRACT = ContractSpec(DOCUMENT_KEY, (OperationSpec("ingest", OperationMode.ASYNC),))

__all__ = ["DOCUMENT_KEY", "DOCUMENT_CONTRACT"]
