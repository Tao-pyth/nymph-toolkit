"""Adapt registered services to one RuntimeService with explicit task ownership."""

# SPDX-License-Identifier: Apache-2.0
import asyncio

from nymph_toolkit.contracts import (
    ConnectionsLifecycleFailure, ConnectionsStateError, LifecycleFailure,
    DependencyUnavailableError, LifecyclePhase, ModuleFailure, ModuleGroupFailure,
    ModuleSpec, RegistryEntry, RegistryStateError, RegistryUpdate,
    RuntimeService, RuntimeStateError,
)
from .registry import Registry


class ModuleGroup:
    """Configure before execution, run through Runtime, then explicitly unregister."""

    def __init__(self) -> None:
        self._registry = Registry()
        self._services: dict[str, RuntimeService[object]] = {}
        self._entered: list[str] = []
        self._tasks: dict[str, asyncio.Task[object]] = {}
        self._reported_run: set[str] = set()
        self._used = False
        self._started = False
        self._run_entered = False
        self._frozen = False
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._controller: asyncio.Task | None = None
        self._connections = None
        self._connections_started = False
        self._connections_task: asyncio.Task | None = None
        self._connections_reported = False

    def attach_connections(self, connections) -> None:
        """Own connection infrastructure without registering it as a user module."""
        from .connections import Connections
        self._registry._check_thread()
        if self._used or self._connections is not None:
            raise RegistryStateError("Connections must be attached once, before start")
        if not isinstance(connections, Connections) or connections.catalog is not self:
            raise TypeError("Connections must use this ModuleGroup as its catalog")
        self._connections = connections

    @property
    def revision(self) -> int:
        return self._registry.revision

    def get(self, module_id: str) -> RegistryEntry:
        return self._registry.get(module_id)

    def entries(self) -> tuple[RegistryEntry, ...]:
        return self._registry.entries()

    def register(self, spec: ModuleSpec, service: RuntimeService[object]) -> RegistryUpdate:
        self._registry._check_thread()
        if self._used:
            raise RegistryStateError("A ModuleGroup only accepts registrations before start")
        if not all(callable(getattr(service, method, None)) for method in ("start", "run", "stop")):
            raise TypeError("service must provide start, run and stop methods")
        update = self._registry.register(spec)
        self._services[spec.module_id] = service
        return update

    def unregister(self, module_id: str) -> RegistryUpdate:
        self._registry._check_thread()
        if self._frozen:
            raise RegistryStateError("ModuleGroup configuration is frozen until cleanup completes")
        update = self._registry.unregister(module_id)
        del self._services[module_id]
        return update

    def _check_controller(self) -> None:
        self._registry._check_thread()
        if self._loop is not None:
            if asyncio.get_running_loop() is not self._loop or asyncio.current_task() is not self._controller:
                raise RuntimeStateError("ModuleGroup lifecycle belongs to its original Runtime task")

    async def start(self) -> None:
        self._check_controller()
        if self._used:
            raise RuntimeStateError("ModuleGroup cannot be restarted")
        self._loop = asyncio.get_running_loop()
        self._controller = asyncio.current_task()
        self._used = self._frozen = True
        entries = self._registry._dependency_order()
        missing = frozenset().union(*(entry.missing_dependencies for entry in entries))
        if missing:
            raise DependencyUnavailableError(missing)
        if self._connections is not None:
            self._connections_started = True
            await self._connections.start(defer_activation=True)
        for entry in entries:
            module_id = entry.spec.module_id
            self._entered.append(module_id)
            try:
                await self._services[module_id].start()
            except asyncio.CancelledError as exc:
                # Runtime distinguishes a requested cancellation from a service failure.
                exc.add_note(f"ModuleGroup was initializing {module_id}")
                raise
            except Exception as exc:
                raise ModuleGroupFailure((ModuleFailure(module_id, LifecyclePhase.START, exc),)) from exc
        if self._connections is not None:
            await self._connections.activate()
        self._started = True

    async def _run_service(self, module_id: str) -> object:
        return await self._services[module_id].run()

    async def run(self) -> dict[str, object]:
        self._check_controller()
        if not self._started or self._run_entered or self._closed:
            raise RuntimeStateError("ModuleGroup is not ready to run")
        self._run_entered = True
        if self._connections is not None:
            coroutine = self._connections.run()
            try:
                self._connections_task = asyncio.create_task(coroutine, name="ntk-connections")
            except Exception:
                coroutine.close()
                raise
        for module_id in self._entered:
            coroutine = self._run_service(module_id)
            try:
                self._tasks[module_id] = asyncio.create_task(coroutine, name=f"ntk-module:{module_id}")
            except Exception as exc:
                coroutine.close()
                raise ModuleGroupFailure((ModuleFailure(module_id, LifecyclePhase.RUN, exc),)) from exc
        pending = set(self._tasks.values())
        while pending:
            watched = pending | ({self._connections_task} if self._connections_task is not None else set())
            done, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
            pending -= done
            failures = []
            for module_id, task in sorted(self._tasks.items()):
                if task in done:
                    failure = self._run_failure(module_id, task)
                    if failure is not None:
                        self._reported_run.add(module_id)
                        failures.append(failure)
            if failures:
                raise ModuleGroupFailure(tuple(failures))
            if self._connections_task is not None and self._connections_task in done:
                try:
                    self._connections_task.result()
                except (Exception, asyncio.CancelledError) as exc:
                    self._connections_reported = True
                    raise ConnectionsLifecycleFailure((LifecycleFailure(LifecyclePhase.RUN, exc),)) from exc
                raise ConnectionsStateError("Connections processing ended while modules were still running")
        return {module_id: task.result() for module_id, task in sorted(self._tasks.items())}

    @staticmethod
    def _run_failure(module_id: str, task: asyncio.Task) -> ModuleFailure | None:
        try:
            task.result()
        except (Exception, asyncio.CancelledError) as exc:
            return ModuleFailure(module_id, LifecyclePhase.RUN, exc)
        return None

    async def stop(self) -> None:
        self._check_controller()
        if self._closed:
            return
        self._used = self._frozen = True
        failures = []
        infrastructure_failures = []
        try:
            if self._connections_started:
                try:
                    self._connections.begin_shutdown()
                except (Exception, asyncio.CancelledError) as exc:
                    infrastructure_failures.append(LifecycleFailure(LifecyclePhase.STOP, exc))
            if self._connections_task is not None:
                cancelled = not self._connections_task.done()
                if cancelled:
                    self._connections_task.cancel()
                await asyncio.gather(self._connections_task, return_exceptions=True)
                if not self._connections_reported:
                    try:
                        self._connections_task.result()
                    except (Exception, asyncio.CancelledError) as exc:
                        if not (cancelled and isinstance(exc, asyncio.CancelledError)):
                            infrastructure_failures.append(LifecycleFailure(LifecyclePhase.RUN, exc))
            requested_cancellation = set()
            for module_id, task in self._tasks.items():
                if not task.done():
                    requested_cancellation.add(module_id)
                    task.cancel()
            if self._tasks:
                await asyncio.gather(*self._tasks.values(), return_exceptions=True)
            for module_id, task in sorted(self._tasks.items()):
                if module_id in self._reported_run:
                    continue
                failure = self._run_failure(module_id, task)
                if failure is not None:
                    if module_id in requested_cancellation and isinstance(failure.exception, asyncio.CancelledError):
                        continue
                    failures.append(failure)
            for module_id in reversed(self._entered):
                try:
                    await self._services[module_id].stop()
                except (Exception, asyncio.CancelledError) as exc:
                    failures.append(ModuleFailure(module_id, LifecyclePhase.STOP, exc))
            if self._connections_started:
                try:
                    await self._connections.stop()
                except (Exception, asyncio.CancelledError) as exc:
                    infrastructure_failures.append(LifecycleFailure(LifecyclePhase.STOP, exc))
        finally:
            self._closed = True
            self._frozen = False
        if failures and infrastructure_failures:
            raise ExceptionGroup("Module and Connections cleanup failures", [
                ModuleGroupFailure(tuple(failures)),
                ConnectionsLifecycleFailure(tuple(infrastructure_failures)),
            ])
        if failures:
            raise ModuleGroupFailure(tuple(failures))
        if infrastructure_failures:
            raise ConnectionsLifecycleFailure(tuple(infrastructure_failures))
