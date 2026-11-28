"""Candidate preparation through a Core-authorized connection (ADR 0033)."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

INPUT_CANDIDATE_KEY = ContractKey("ntk.input.prepare", "1")
INPUT_CANDIDATE_CONTRACT = ContractSpec(
    INPUT_CANDIDATE_KEY, (OperationSpec("prepare", OperationMode.ASYNC),)
)

__all__ = ["INPUT_CANDIDATE_KEY", "INPUT_CANDIDATE_CONTRACT"]
