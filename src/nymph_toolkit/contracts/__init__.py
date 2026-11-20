"""The minimal in-process lifecycle contract adopted for v0.2."""

# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class RuntimeState(StrEnum):
    NEW = "new"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class LifecyclePhase(StrEnum):
    START = "start"
    RUN = "run"
    STOP = "stop"


class RuntimeService(Protocol[T_co]):
    """One execution entry point, not the complete future module contract."""

    async def start(self) -> None:
        """Initialize resources; stop must also handle partial initialization."""
        ...

    async def run(self) -> T_co:
        """Perform work, yielding to the event loop and honoring cancellation."""
        ...

    async def stop(self) -> None:
        """Release owned resources, including any tasks created by the service."""
        ...


@dataclass(frozen=True)
class LifecycleFailure:
    phase: LifecyclePhase
    exception: BaseException


class RuntimeFailure(RuntimeError):
    """Retain all ordinary lifecycle failures, including cleanup failures."""

    def __init__(self, failures: tuple[LifecycleFailure, ...]) -> None:
        if not failures:
            raise ValueError("RuntimeFailure requires at least one failure")
        self.failures = tuple(failures)
        super().__init__(
            "; ".join(f"{f.phase}: {type(f.exception).__name__}: {f.exception}" for f in failures)
        )


class RuntimeStateError(RuntimeError):
    """A lifecycle operation was requested in an unsupported state or context."""


__all__ = [
    "LifecycleFailure",
    "LifecyclePhase",
    "RuntimeFailure",
    "RuntimeService",
    "RuntimeState",
    "RuntimeStateError",
]
