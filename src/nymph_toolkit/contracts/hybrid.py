"""Explicit limits and observations for same-PC hybrid execution."""

# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from enum import StrEnum
import math


def seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be finite positive seconds")
    return float(value)


def positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError("limit must be a positive integer")
    return value


class Placement(StrEnum):
    LOCAL = "local"
    PROCESS = "process"


@dataclass(frozen=True)
class HybridSettings:
    startup_timeout: float
    shutdown_timeout: float
    call_timeout: float
    max_frame_bytes: int
    max_requests: int
    max_streams: int

    def __post_init__(self):
        for name in ("startup_timeout", "shutdown_timeout", "call_timeout"):
            seconds(getattr(self, name))
        for name in ("max_frame_bytes", "max_requests", "max_streams"):
            positive(getattr(self, name))


class OverflowPolicy(StrEnum):
    WAIT = "wait"
    DROP_OLDEST = "drop_oldest"


@dataclass(frozen=True)
class StreamOptions:
    send_bytes: int
    send_chunks: int
    receive_bytes: int
    receive_chunks: int
    overflow: OverflowPolicy

    def __post_init__(self):
        for name in ("send_bytes", "send_chunks", "receive_bytes", "receive_chunks"):
            positive(getattr(self, name))
        if not isinstance(self.overflow, OverflowPolicy):
            raise TypeError("overflow must be an OverflowPolicy")


class StreamState(StrEnum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    sequence: int
    data: bytes = b""
    missing: tuple[int, int] | None = None
    reason: str = ""

    @property
    def missing_count(self):
        return 0 if self.missing is None else self.missing[1] - self.missing[0] + 1


@dataclass(frozen=True)
class ProcessSnapshot:
    module_id: str
    placement: Placement
    generation: str
    state: str
    pid: int | None = None
    returncode: int | None = None
    cleanup_confirmed: bool = False
    reason: str = ""


class HybridError(RuntimeError):
    pass


class ProtocolError(HybridError):
    pass


class PeerClosed(HybridError):
    pass


class CapacityExceeded(HybridError):
    pass


class OutcomeUnknown(HybridError, TimeoutError):
    def __init__(self, request_id, message="Request outcome is not confirmed"):
        self.request_id = request_id
        super().__init__(message)


class RemoteError(HybridError):
    def __init__(self, module_id, remote_type, message):
        self.module_id, self.remote_type, self.message = module_id, remote_type, message
        super().__init__(f"{module_id}: {remote_type}: {message}")


class StreamClosed(HybridError):
    pass


class ChunkTooLarge(HybridError, ValueError):
    pass
