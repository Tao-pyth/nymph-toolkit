"""Explicit observation, teaching, correction and evidence queries; ADR 0031."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

TEXT_INTERACTION_KEY = ContractKey("ntk.text.interaction", "1")
TEXT_INTERACTION_CONTRACT = ContractSpec(TEXT_INTERACTION_KEY, tuple(
    OperationSpec(name, OperationMode.ASYNC)
    for name in ("observe", "learn", "inspect", "correct", "get_revision")
))

__all__ = ["TEXT_INTERACTION_KEY", "TEXT_INTERACTION_CONTRACT"]
