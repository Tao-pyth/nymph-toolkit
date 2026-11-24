"""Consented, transient voice observations; see ADR 0038."""

# SPDX-License-Identifier: Apache-2.0
from .connections import ContractKey, ContractSpec, OperationMode, OperationSpec

VOICE_KEY = ContractKey("ntk.voice.observation", "1")
VOICE_CONTRACT = ContractSpec(VOICE_KEY, tuple(
    OperationSpec(name, OperationMode.ASYNC)
    for name in ("start_session", "stop_session", "status", "read", "revoke")
))

__all__ = ["VOICE_KEY", "VOICE_CONTRACT"]
