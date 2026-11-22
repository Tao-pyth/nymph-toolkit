# 公開APIの実装一覧

この一覧は明示された公開import（core / contractsの__all__）を実装から生成する。
引数、列挙値、データ型、継承したメソッド・プロパティの存在を照合するための資料であり、入力検証・返却値・所有期間・失敗時動作は[Core API](core-api.md)と各操作資料を併読する。
型注釈がない入口から新しい型保証を推測しない。内部補助メソッドを含む実体の一覧は、全メソッドの安定保証を意味しない。安定対象は[接続契約](module-contracts.md)とcontracts-v1.json、移行は[migration-v1](migration-v1.md)を参照する。

再生成：python tools/check_api.py --write。照合：python tools/check_api.py。

## nymph_toolkit.core（15件）

<a id="core-Connections"></a>

### Connections

基底：object。

```text
Connections(catalog, store: 'FileStore') -> None
  def acknowledge_interruption(self, module_id: str, notice_id: int) -> bool
  async activate(self) -> None
  def begin_shutdown(self) -> None
  async bind(self, requester_id: str, contract: nymph_toolkit.contracts.connections.ContractKey, provider_id: str, *, wait_timeout: float) -> nymph_toolkit.contracts.connections.ConnectionSnapshot
  def candidates(self, contract: nymph_toolkit.contracts.connections.ContractKey) -> tuple[nymph_toolkit.contracts.connections.Candidate, ...]
  def connection(self, key: nymph_toolkit.contracts.connections.BindingKey) -> nymph_toolkit.contracts.connections.ConnectionSnapshot
  def declare(self, advertisement: nymph_toolkit.contracts.connections.ModuleAdvertisement, handlers: collections.abc.Mapping | None = None) -> None
  async health_check(self, *, module_ids=None, bindings=None) -> nymph_toolkit.contracts.connections.HealthResult
  async invoke(self, key: nymph_toolkit.contracts.connections.BindingKey, operation: str, *, wait_timeout: float, args=(), kwargs=None)
  def module_state(self, module_id: str) -> nymph_toolkit.contracts.connections.ModuleExecutionState
  async next_notice(self, module_id: str) -> nymph_toolkit.contracts.connections.ConnectionNotice
  async prepare(self, key: nymph_toolkit.contracts.connections.BindingKey, *, wait_timeout: float) -> nymph_toolkit.core.connections.PreparedConnection
  def publish_usage(self, module_id: str, usage: nymph_toolkit.contracts.connections.Usage, *, contracts: collections.abc.Mapping[nymph_toolkit.contracts.connections.ContractKey, nymph_toolkit.contracts.connections.Usage] | None = None) -> None
  def report_link_error(self, key: nymph_toolkit.contracts.connections.BindingKey, exception: Exception) -> int
  async run(self) -> None
  async start(self, *, defer_activation: bool = False) -> None
  property state(self) -> nymph_toolkit.contracts.RuntimeState
  async stop(self) -> None
```

<a id="core-CoreClient"></a>

### CoreClient

基底：object。

```text
CoreClient(context, dispatch)
  async acknowledge_interruption(self, notice_id, *, timeout=None)
  async activity(self, operation, key=None, *, timeout=None, **arguments)
  async bind(self, contract, provider_id, *, timeout)
  async candidates(self, contract, *, timeout=None)
  async health_check(self, *, module_ids=None, bindings=None, timeout=None)
  async invoke(self, contract, operation, *args, timeout, **kwargs)
  async next_notice(self, *, timeout)
  property pending_requests(self)
  async prepare(self, contract, *, timeout)
  async publish_usage(self, usage, *, contracts=None, timeout=None)
  def release(self, request_id)
  def result(self, request_id)
  async submit_remote(self, request, module_id, executor_id, arguments=None, *, timeout=None)
```

<a id="core-DirectLink"></a>

### DirectLink

基底：object。

```text
DirectLink(client, route)
  async acall(self, operation, *args, timeout, **kwargs)
  async close(self)
  async open_stream(self, operation, options, metadata=None, *, timeout)
  property pending_requests(self)
  def release(self, request_id)
  def result(self, request_id)
```

<a id="core-FileStore"></a>

### FileStore

基底：object。

```text
FileStore(root: pathlib.Path, archive: pathlib.Path, *, retention: datetime.timedelta, batch_size: int, flush_interval: float) -> None
  property admitting(self) -> bool
  def append(self, kind: str, data: dict) -> None
  property changed(self) -> asyncio.locks.Event
  property failure(self) -> nymph_toolkit.contracts.connections.StorageFailure | None
  async flush(self) -> None
  async load_bindings(self) -> tuple[nymph_toolkit.contracts.connections.BindingRecord, ...]
  async read_activity_history(self, requester_id: str)
  async save_bindings(self, bindings: tuple[nymph_toolkit.contracts.connections.BindingRecord, ...]) -> None
  async start(self) -> None
  property state(self) -> nymph_toolkit.contracts.RuntimeState
  async stop(self) -> None
  property unsaved_events(self) -> int
  async wait_failure(self) -> nymph_toolkit.contracts.connections.StorageFailure
  async wait_ready(self) -> None
```

<a id="core-HybridGroup"></a>

### HybridGroup

基底：ModuleGroup。

```text
HybridGroup(settings: nymph_toolkit.contracts.hybrid.HybridSettings, store)
  def attach_connections(self, connections) -> None
  def attach_task_manager(self, manager) -> None
  def entries(self) -> tuple[nymph_toolkit.contracts.registry.RegistryEntry, ...]
  def get(self, module_id: str) -> nymph_toolkit.contracts.registry.RegistryEntry
  def register(self, spec: nymph_toolkit.contracts.registry.ModuleSpec, service: nymph_toolkit.contracts.RuntimeService[object]) -> nymph_toolkit.contracts.registry.RegistryUpdate
  property revision(self) -> int
  async run(self) -> dict[str, object]
  async start(self)
  async stop(self)
  def unregister(self, module_id)
  def client(self, module_id)
  async diagnostics(self, module_id)
  def enable_activities(self, *, clock_check_interval, max_running=None)
  def fail(self, error)
  property port(self)
  def process(self, module_id)
  def register_module(self, spec, advertisement, factory, config, placement)
```

<a id="core-HybridTaskManager"></a>

### HybridTaskManager

基底：TaskManager。

```text
HybridTaskManager(group, *, clock_check_interval, max_running=None)
  def change(self, key, change, *, command_id, expected_revision)
  def command_result(self, key, command_id)
  def request_pause(self, key, *, command_id, expected_revision)
  def request_resume(self, key, *, command_id, expected_revision)
  async wait_command(self, key, command_id)
  def activities(self, requester_id=None)
  def begin_shutdown(self)
  async history(self, requester_id)
  async next_notice(self, requester_id)
  def request_finish(self, key, *, reason=<ActivityFinishReason.NYMPH: 'nymph'>)
  async run(self)
  def snapshot(self, key)
  async start(self)
  property state(self)
  async stop(self)
  def submit(self, request: nymph_toolkit.contracts.activities.ActivityRequest, execute: collections.abc.Callable, *, supports_pause=False)
  async wait(self, key)
  def submit_remote(self, request, module_id, executor_id, arguments=None)
```

<a id="core-ModuleContext"></a>

### ModuleContext

基底：object。

```text
ModuleContext(module_id, generation, settings, dispatch, local_hub=None)
  def provide(self, contract, handlers)
  def provide_executor(self, executor_id, handler, *, supports_pause=False)
  def provide_stream(self, contract, operation, handler)
```

<a id="core-ModuleGroup"></a>

### ModuleGroup

基底：object。

```text
ModuleGroup() -> None
  def attach_connections(self, connections) -> None
  def attach_task_manager(self, manager) -> None
  def entries(self) -> tuple[nymph_toolkit.contracts.registry.RegistryEntry, ...]
  def get(self, module_id: str) -> nymph_toolkit.contracts.registry.RegistryEntry
  def register(self, spec: nymph_toolkit.contracts.registry.ModuleSpec, service: nymph_toolkit.contracts.RuntimeService[object]) -> nymph_toolkit.contracts.registry.RegistryUpdate
  property revision(self) -> int
  async run(self) -> dict[str, object]
  async start(self) -> None
  async stop(self) -> None
  def unregister(self, module_id: str) -> nymph_toolkit.contracts.registry.RegistryUpdate
```

<a id="core-PreparedConnection"></a>

### PreparedConnection

基底：object。

```text
PreparedConnection(owner: 'Connections', binding: nymph_toolkit.core.connections._Binding) -> None
  async acall(self, operation: str, *args, **kwargs)
  def call(self, operation: str, *args, **kwargs)
  property snapshot(self) -> nymph_toolkit.contracts.connections.ConnectionSnapshot
```

<a id="core-Registry"></a>

### Registry

基底：object。

```text
Registry() -> None
  def entries(self) -> tuple[nymph_toolkit.contracts.registry.RegistryEntry, ...]
  def get(self, module_id: str) -> nymph_toolkit.contracts.registry.RegistryEntry
  def register(self, spec: nymph_toolkit.contracts.registry.ModuleSpec) -> nymph_toolkit.contracts.registry.RegistryUpdate
  property revision(self) -> int
  def unregister(self, module_id: str) -> nymph_toolkit.contracts.registry.RegistryUpdate
```

<a id="core-Runtime"></a>

### Runtime

基底：Generic。

```text
Runtime(service: nymph_toolkit.contracts.RuntimeService[~T]) -> None
  async start(self) -> None
  property state(self) -> nymph_toolkit.contracts.RuntimeState
  async stop(self) -> None
  async wait(self) -> ~T | None
```

<a id="core-StreamReceiver"></a>

### StreamReceiver

基底：_Stream。

```text
StreamReceiver(reader, writer, options)
  async abort(self, reason='Explicit stream abort')
  async aclose(self)
  property buffered_chunks(self)
  async fail(self, reason)
  async receive(self, *, timeout)
```

<a id="core-StreamSender"></a>

### StreamSender

基底：_Stream。

```text
StreamSender(reader, writer, options)
  async abort(self, reason='Explicit stream abort')
  async aclose(self)
  property buffered_chunks(self)
  async fail(self, reason)
  async close(self, *, timeout)
  async send(self, data, *, timeout)
```

<a id="core-TaskManager"></a>

### TaskManager

基底：_Slots, _Commands。

```text
TaskManager(connections: nymph_toolkit.core.connections.Connections, *, clock_check_interval: float, clock=None, max_running=None)
  def change(self, key, change, *, command_id, expected_revision)
  def command_result(self, key, command_id)
  def request_pause(self, key, *, command_id, expected_revision)
  def request_resume(self, key, *, command_id, expected_revision)
  async wait_command(self, key, command_id)
  def activities(self, requester_id=None)
  def begin_shutdown(self)
  async history(self, requester_id)
  async next_notice(self, requester_id)
  def request_finish(self, key, *, reason=<ActivityFinishReason.NYMPH: 'nymph'>)
  async run(self)
  def snapshot(self, key)
  async start(self)
  property state(self)
  async stop(self)
  def submit(self, request: nymph_toolkit.contracts.activities.ActivityRequest, execute: collections.abc.Callable, *, supports_pause=False)
  async wait(self, key)
```

<a id="core-validate_module_registration"></a>

### validate_module_registration

```text
validate_module_registration(spec, advertisement, factory, config, placement)
```

## nymph_toolkit.contracts（98件）

<a id="contracts-ActivityAdmissionError"></a>

### ActivityAdmissionError

基底：ActivityError。

```text
ActivityAdmissionError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ActivityChange"></a>

### ActivityChange

基底：object。

```text
ActivityChange(start_at: datetime.datetime | None | nymph_toolkit.contracts.activities._Unchanged = <_Unchanged.VALUE: 'unchanged'>, duration: datetime.timedelta | nymph_toolkit.contracts.activities._Unchanged = <_Unchanged.VALUE: 'unchanged'>, priority: int | nymph_toolkit.contracts.activities._Unchanged = <_Unchanged.VALUE: 'unchanged'>) -> None
  start_at: datetime.datetime | None | nymph_toolkit.contracts.activities._Unchanged
  duration: datetime.timedelta | nymph_toolkit.contracts.activities._Unchanged
  priority: int | nymph_toolkit.contracts.activities._Unchanged
  def as_dict(self)
```

<a id="contracts-ActivityCommandResult"></a>

### ActivityCommandResult

基底：object。

```text
ActivityCommandResult(key: nymph_toolkit.contracts.activities.ActivityKey, command_id: str, operation: str, received_at: datetime.datetime, status: nymph_toolkit.contracts.activities.ActivityCommandStatus, reason: str | None, snapshot: nymph_toolkit.contracts.activities.ActivitySnapshot) -> None
  key: nymph_toolkit.contracts.activities.ActivityKey
  command_id: str
  operation: str
  received_at: datetime.datetime
  status: nymph_toolkit.contracts.activities.ActivityCommandStatus
  reason: str | None
  snapshot: nymph_toolkit.contracts.activities.ActivitySnapshot
```

<a id="contracts-ActivityCommandStatus"></a>

### ActivityCommandStatus

基底：StrEnum。

```text
ACCEPTED = 'accepted'
APPLIED = 'applied'
NO_CHANGE = 'no_change'
REJECTED = 'rejected'
SUPERSEDED = 'superseded'
FAILED = 'failed'
```

<a id="contracts-ActivityContext"></a>

### ActivityContext

基底：Protocol。

```text
ActivityContext(*args, **kwargs)
  async checkpoint(self) -> nymph_toolkit.contracts.activities.ActivityFinishReason | None
  property current_request(self) -> nymph_toolkit.contracts.activities.ActivityRequest
  property finish_reason(self) -> nymph_toolkit.contracts.activities.ActivityFinishReason | None
  property finish_requested(self) -> bool
  property pause_requested(self) -> bool
  property planned_end_at(self) -> datetime.datetime
  property planned_start_at(self) -> datetime.datetime
  property request(self) -> nymph_toolkit.contracts.activities.ActivityRequest
  async wait_for_control(self) -> nymph_toolkit.contracts.activities.ActivityControlKind
  async wait_for_finish(self) -> nymph_toolkit.contracts.activities.ActivityFinishReason
```

<a id="contracts-ActivityControlKind"></a>

### ActivityControlKind

基底：StrEnum。

```text
PAUSE = 'pause'
FINISH = 'finish'
```

<a id="contracts-ActivityError"></a>

### ActivityError

基底：RuntimeError。

```text
ActivityError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ActivityExecutor"></a>

### ActivityExecutor

値：`collections.abc.Callable[[nymph_toolkit.contracts.activities.ActivityContext], collections.abc.Awaitable[object]]`。

<a id="contracts-ActivityFailure"></a>

### ActivityFailure

基底：object。

```text
ActivityFailure(exception: BaseException) -> None
  exception: BaseException
```

<a id="contracts-ActivityFinishReason"></a>

### ActivityFinishReason

基底：StrEnum。

```text
NYMPH = 'nymph'
RUNTIME = 'runtime'
CONNECTION_INTERRUPTION = 'connection_interruption'
```

<a id="contracts-ActivityHistory"></a>

### ActivityHistory

基底：object。

```text
ActivityHistory(records: tuple[nymph_toolkit.contracts.activities.ActivityHistoryRecord, ...], issues: tuple[nymph_toolkit.contracts.activities.ActivityHistoryIssue, ...]) -> None
  records: tuple[nymph_toolkit.contracts.activities.ActivityHistoryRecord, ...]
  issues: tuple[nymph_toolkit.contracts.activities.ActivityHistoryIssue, ...]
```

<a id="contracts-ActivityHistoryIssue"></a>

### ActivityHistoryIssue

基底：object。

```text
ActivityHistoryIssue(path: str, line: int | None, message: str) -> None
  path: str
  line: int | None
  message: str
```

<a id="contracts-ActivityHistoryRecord"></a>

### ActivityHistoryRecord

基底：object。

```text
ActivityHistoryRecord(run_id: str, sequence: int, at: datetime.datetime, kind: str, data: collections.abc.Mapping[str, object]) -> None
  run_id: str
  sequence: int
  at: datetime.datetime
  kind: str
  data: collections.abc.Mapping[str, object]
```

<a id="contracts-ActivityKey"></a>

### ActivityKey

基底：object。

```text
ActivityKey(requester_id: str, activity_id: str) -> None
  requester_id: str
  activity_id: str
```

<a id="contracts-ActivityNotice"></a>

### ActivityNotice

基底：object。

```text
ActivityNotice(sequence: int, kind: nymph_toolkit.contracts.activities.ActivityNoticeKind, at: datetime.datetime, snapshot: nymph_toolkit.contracts.activities.ActivitySnapshot, command: nymph_toolkit.contracts.activities.ActivityCommandResult | None = None) -> None
  sequence: int
  kind: nymph_toolkit.contracts.activities.ActivityNoticeKind
  at: datetime.datetime
  snapshot: nymph_toolkit.contracts.activities.ActivitySnapshot
  command: nymph_toolkit.contracts.activities.ActivityCommandResult | None
```

<a id="contracts-ActivityNoticeKind"></a>

### ActivityNoticeKind

基底：StrEnum。

```text
STATE_CHANGED = 'state_changed'
PLANNED_END = 'planned_end'
COMMAND_RESULT = 'command_result'
```

<a id="contracts-ActivityRequest"></a>

### ActivityRequest

基底：object。

```text
ActivityRequest(key: nymph_toolkit.contracts.activities.ActivityKey, content: str, start_at: datetime.datetime | None, duration: datetime.timedelta, parameters: collections.abc.Mapping[str, object] = <factory>, priority: int = 0) -> None
  key: nymph_toolkit.contracts.activities.ActivityKey
  content: str
  start_at: datetime.datetime | None
  duration: datetime.timedelta
  parameters: collections.abc.Mapping[str, object]
  priority: int
  def as_dict(self) -> dict
  def planned_times(self, accepted_at: datetime.datetime) -> tuple[datetime.datetime, datetime.datetime]
```

<a id="contracts-ActivitySnapshot"></a>

### ActivitySnapshot

基底：object。

```text
ActivitySnapshot(request: nymph_toolkit.contracts.activities.ActivityRequest, state: nymph_toolkit.contracts.activities.ActivityState, accepted_at: datetime.datetime, planned_start_at: datetime.datetime, planned_end_at: datetime.datetime, started_at: datetime.datetime | None = None, ended_at: datetime.datetime | None = None, elapsed_seconds: float = 0.0, finish_reason: nymph_toolkit.contracts.activities.ActivityFinishReason | None = None, finish_requested_at: datetime.datetime | None = None, planned_end_notified: bool = False, result: object = None, failures: tuple[nymph_toolkit.contracts.activities.ActivityFailure, ...] = (), revision: int = 0, scheduled_revision: int = 0, current_request: nymph_toolkit.contracts.activities.ActivityRequest | None = None, execution_seconds: float = 0.0, timing_confirmed: bool = True, cleanup_confirmed: bool = True) -> None
  request: nymph_toolkit.contracts.activities.ActivityRequest
  state: nymph_toolkit.contracts.activities.ActivityState
  accepted_at: datetime.datetime
  planned_start_at: datetime.datetime
  planned_end_at: datetime.datetime
  started_at: datetime.datetime | None
  ended_at: datetime.datetime | None
  elapsed_seconds: float
  finish_reason: nymph_toolkit.contracts.activities.ActivityFinishReason | None
  finish_requested_at: datetime.datetime | None
  planned_end_notified: bool
  result: object
  failures: tuple[nymph_toolkit.contracts.activities.ActivityFailure, ...]
  revision: int
  scheduled_revision: int
  current_request: nymph_toolkit.contracts.activities.ActivityRequest | None
  execution_seconds: float
  timing_confirmed: bool
  cleanup_confirmed: bool
```

<a id="contracts-ActivityStartInPastError"></a>

### ActivityStartInPastError

基底：ActivityError。

```text
ActivityStartInPastError(request: nymph_toolkit.contracts.activities.ActivityRequest, observed_at: datetime.datetime) -> None
```

<a id="contracts-ActivityState"></a>

### ActivityState

基底：StrEnum。

```text
PENDING = 'pending'
STARTING = 'starting'
RUNNING = 'running'
PAUSING = 'pausing'
PAUSED = 'paused'
RESUME_PENDING = 'resume_pending'
FINISHING = 'finishing'
COMPLETED = 'completed'
FAILED = 'failed'
STOPPED = 'stopped'
```

<a id="contracts-ActivityStateError"></a>

### ActivityStateError

基底：ActivityError。

```text
ActivityStateError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-BindingHealth"></a>

### BindingHealth

基底：object。

```text
BindingHealth(key: nymph_toolkit.contracts.connections.BindingKey, provider_id: str, healthy: bool, reason: str = '') -> None
  key: nymph_toolkit.contracts.connections.BindingKey
  provider_id: str
  healthy: bool
  reason: str
```

<a id="contracts-BindingKey"></a>

### BindingKey

基底：object。

```text
BindingKey(requester_id: str, contract: nymph_toolkit.contracts.connections.ContractKey) -> None
  requester_id: str
  contract: nymph_toolkit.contracts.connections.ContractKey
```

<a id="contracts-BindingRecord"></a>

### BindingRecord

基底：object。

```text
BindingRecord(key: nymph_toolkit.contracts.connections.BindingKey, provider_id: str) -> None
  key: nymph_toolkit.contracts.connections.BindingKey
  provider_id: str
```

<a id="contracts-BindingState"></a>

### BindingState

基底：StrEnum。

```text
VALID = 'valid'
INVALID = 'invalid'
CHECKING = 'checking'
```

<a id="contracts-Candidate"></a>

### Candidate

基底：object。

```text
Candidate(registration: nymph_toolkit.contracts.registry.RegistryEntry, advertisement: nymph_toolkit.contracts.connections.ModuleAdvertisement, contract: nymph_toolkit.contracts.connections.ContractKey, module_usage: nymph_toolkit.contracts.connections.Usage, contract_usage: nymph_toolkit.contracts.connections.Usage) -> None
  registration: nymph_toolkit.contracts.registry.RegistryEntry
  advertisement: nymph_toolkit.contracts.connections.ModuleAdvertisement
  contract: nymph_toolkit.contracts.connections.ContractKey
  module_usage: nymph_toolkit.contracts.connections.Usage
  contract_usage: nymph_toolkit.contracts.connections.Usage
```

<a id="contracts-CapacityExceeded"></a>

### CapacityExceeded

基底：HybridError。

```text
CapacityExceeded（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ChunkTooLarge"></a>

### ChunkTooLarge

基底：HybridError, ValueError。

```text
ChunkTooLarge（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ConnectionConflictError"></a>

### ConnectionConflictError

基底：ConnectionsError。

```text
ConnectionConflictError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ConnectionNotReadyError"></a>

### ConnectionNotReadyError

基底：ConnectionsError。

```text
ConnectionNotReadyError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ConnectionNotice"></a>

### ConnectionNotice

基底：object。

```text
ConnectionNotice(notice_id: int, module_id: str, kind: nymph_toolkit.contracts.connections.NoticeKind, binding: nymph_toolkit.contracts.connections.BindingKey | None, reason: str = '') -> None
  notice_id: int
  module_id: str
  kind: nymph_toolkit.contracts.connections.NoticeKind
  binding: nymph_toolkit.contracts.connections.BindingKey | None
  reason: str
```

<a id="contracts-ConnectionSnapshot"></a>

### ConnectionSnapshot

基底：object。

```text
ConnectionSnapshot(key: nymph_toolkit.contracts.connections.BindingKey, provider_id: str, state: nymph_toolkit.contracts.connections.BindingState, reason: str = '') -> None
  key: nymph_toolkit.contracts.connections.BindingKey
  provider_id: str
  state: nymph_toolkit.contracts.connections.BindingState
  reason: str
```

<a id="contracts-ConnectionUnavailableError"></a>

### ConnectionUnavailableError

基底：ConnectionsError。

```text
ConnectionUnavailableError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ConnectionsError"></a>

### ConnectionsError

基底：RuntimeError。

```text
ConnectionsError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ConnectionsLifecycleFailure"></a>

### ConnectionsLifecycleFailure

基底：ConnectionsError。

```text
ConnectionsLifecycleFailure(failures: tuple[nymph_toolkit.contracts.LifecycleFailure, ...]) -> None
```

<a id="contracts-ConnectionsStateError"></a>

### ConnectionsStateError

基底：ConnectionsError。

```text
ConnectionsStateError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ContractDeclarationError"></a>

### ContractDeclarationError

基底：ConnectionsError。

```text
ContractDeclarationError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ContractKey"></a>

### ContractKey

基底：object。

```text
ContractKey(contract_id: str, version: str) -> None
  contract_id: str
  version: str
```

<a id="contracts-ContractSpec"></a>

### ContractSpec

基底：object。

```text
ContractSpec(key: nymph_toolkit.contracts.connections.ContractKey, operations: tuple[nymph_toolkit.contracts.connections.OperationSpec, ...]) -> None
  key: nymph_toolkit.contracts.connections.ContractKey
  operations: tuple[nymph_toolkit.contracts.connections.OperationSpec, ...]
```

<a id="contracts-CoreClientProtocol"></a>

### CoreClientProtocol

基底：Protocol。

```text
CoreClientProtocol(*args, **kwargs)
  async acknowledge_interruption(self, notice_id, *, timeout=None)
  async activity(self, operation, key=None, *, timeout=None, **arguments)
  async bind(self, contract: 'ContractKey', provider_id: 'str', *, timeout)
  async candidates(self, contract: 'ContractKey', *, timeout=None)
  async health_check(self, *, module_ids=None, bindings=None, timeout=None)
  async invoke(self, contract: 'ContractKey', operation, *args, timeout, **kwargs)
  async next_notice(self, *, timeout)
  property pending_requests(self) -> 'tuple[str, ...]'
  async prepare(self, contract: 'ContractKey', *, timeout) -> 'DirectLinkProtocol'
  async publish_usage(self, usage: 'Usage', *, contracts=None, timeout=None)
  def release(self, request_id) -> 'None'
  def result(self, request_id)
  async submit_remote(self, request: 'ActivityRequest', module_id, executor_id, arguments=None, *, timeout=None)
```

<a id="contracts-DependencyCycleError"></a>

### DependencyCycleError

基底：RegistryError。

```text
DependencyCycleError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-DependencyUnavailableError"></a>

### DependencyUnavailableError

基底：RegistryError。

```text
DependencyUnavailableError(missing_dependencies: frozenset[str]) -> None
```

<a id="contracts-DirectLinkProtocol"></a>

### DirectLinkProtocol

基底：Protocol。

```text
DirectLinkProtocol(*args, **kwargs)
  async acall(self, operation, *args, timeout, **kwargs)
  async close(self) -> 'None'
  async open_stream(self, operation, options: 'StreamOptions', metadata=None, *, timeout) -> 'StreamSenderProtocol'
  property pending_requests(self) -> 'tuple[str, ...]'
  def release(self, request_id) -> 'None'
  def result(self, request_id)
```

<a id="contracts-DuplicateActivityError"></a>

### DuplicateActivityError

基底：ActivityError。

```text
DuplicateActivityError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-DuplicateModuleError"></a>

### DuplicateModuleError

基底：RegistryError。

```text
DuplicateModuleError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-HealthResult"></a>

### HealthResult

基底：object。

```text
HealthResult(request_id: int, modules: tuple[nymph_toolkit.contracts.connections.ModuleHealth, ...], connections: tuple[nymph_toolkit.contracts.connections.BindingHealth, ...]) -> None
  request_id: int
  modules: tuple[nymph_toolkit.contracts.connections.ModuleHealth, ...]
  connections: tuple[nymph_toolkit.contracts.connections.BindingHealth, ...]
```

<a id="contracts-HybridError"></a>

### HybridError

基底：RuntimeError。

```text
HybridError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-HybridSettings"></a>

### HybridSettings

基底：object。

```text
HybridSettings(startup_timeout: float, shutdown_timeout: float, call_timeout: float, max_frame_bytes: int, max_requests: int, max_streams: int) -> None
  startup_timeout: float
  shutdown_timeout: float
  call_timeout: float
  max_frame_bytes: int
  max_requests: int
  max_streams: int
```

<a id="contracts-LifecycleFailure"></a>

### LifecycleFailure

基底：object。

```text
LifecycleFailure(phase: nymph_toolkit.contracts.LifecyclePhase, exception: BaseException) -> None
  phase: nymph_toolkit.contracts.LifecyclePhase
  exception: BaseException
```

<a id="contracts-LifecyclePhase"></a>

### LifecyclePhase

基底：StrEnum。

```text
START = 'start'
RUN = 'run'
STOP = 'stop'
```

<a id="contracts-LinkFailure"></a>

### LinkFailure

基底：object。

```text
LinkFailure(binding: nymph_toolkit.contracts.connections.BindingKey, exception: Exception, interruption_id: int | None) -> None
  binding: nymph_toolkit.contracts.connections.BindingKey
  exception: Exception
  interruption_id: int | None
```

<a id="contracts-ModuleAdvertisement"></a>

### ModuleAdvertisement

基底：object。

```text
ModuleAdvertisement(module_id: str, implementation_version: str, contracts: tuple[nymph_toolkit.contracts.connections.ContractSpec, ...] = (), tags: frozenset[str] = <factory>, attributes: collections.abc.Mapping[str, str | bool | int | float | None] = <factory>) -> None
  module_id: str
  implementation_version: str
  contracts: tuple[nymph_toolkit.contracts.connections.ContractSpec, ...]
  tags: frozenset[str]
  attributes: collections.abc.Mapping[str, str | bool | int | float | None]
```

<a id="contracts-ModuleContextProtocol"></a>

### ModuleContextProtocol

基底：Protocol。

```text
ModuleContextProtocol(*args, **kwargs)
  property core(self) -> 'CoreClientProtocol'
  property generation(self) -> 'str'
  property module_id(self) -> 'str'
  def provide(self, contract: 'ContractKey', handlers: 'Mapping[str, Callable[..., Awaitable[object]]]') -> 'None'
  def provide_executor(self, executor_id: 'str', handler: 'Callable[[ActivityContext, object], Awaitable[object]]', *, supports_pause=False) -> 'None'
  def provide_stream(self, contract: 'ContractKey', operation: 'str', handler: 'Callable[[StreamReceiverProtocol, object], Awaitable[None]]') -> 'None'
  property settings(self) -> 'HybridSettings'
```

<a id="contracts-ModuleExecutionState"></a>

### ModuleExecutionState

基底：StrEnum。

```text
RUNNING = 'running'
INTERRUPTING = 'interrupting'
SUSPENDED = 'suspended'
```

<a id="contracts-ModuleFactory"></a>

### ModuleFactory

基底：Protocol。

```text
ModuleFactory(*args, **kwargs)
  def __call__(self, context: 'ModuleContextProtocol', config: 'object') -> 'RuntimeService[object] | Awaitable[RuntimeService[object]]'
```

<a id="contracts-ModuleFailure"></a>

### ModuleFailure

基底：object。

```text
ModuleFailure(module_id: str, phase: nymph_toolkit.contracts.LifecyclePhase, exception: BaseException) -> None
  module_id: str
  phase: nymph_toolkit.contracts.LifecyclePhase
  exception: BaseException
```

<a id="contracts-ModuleGroupFailure"></a>

### ModuleGroupFailure

基底：RuntimeError。

```text
ModuleGroupFailure(failures: tuple[nymph_toolkit.contracts.registry.ModuleFailure, ...]) -> None
```

<a id="contracts-ModuleHealth"></a>

### ModuleHealth

基底：object。

```text
ModuleHealth(module_id: str, healthy: bool, reason: str = '') -> None
  module_id: str
  healthy: bool
  reason: str
```

<a id="contracts-ModuleKind"></a>

### ModuleKind

基底：StrEnum。

```text
SUBSYSTEM = 'subsystem'
ADAPTER = 'adapter'
```

<a id="contracts-ModuleSpec"></a>

### ModuleSpec

基底：object。

```text
ModuleSpec(module_id: str, kind: nymph_toolkit.contracts.registry.ModuleKind, requires: frozenset[str] = <factory>) -> None
  module_id: str
  kind: nymph_toolkit.contracts.registry.ModuleKind
  requires: frozenset[str]
```

<a id="contracts-NoticeKind"></a>

### NoticeKind

基底：StrEnum。

```text
INTERRUPT = 'interrupt'
INVALIDATED = 'invalidated'
RECOVERED = 'recovered'
RESUMED = 'resumed'
SHUTDOWN = 'shutdown'
```

<a id="contracts-OperatingState"></a>

### OperatingState

基底：StrEnum。

```text
UNKNOWN = 'unknown'
RUNNING = 'running'
STOPPED = 'stopped'
FAILED = 'failed'
```

<a id="contracts-OperationFailure"></a>

### OperationFailure

基底：object。

```text
OperationFailure(code: str, message: str) -> None
  code: str
  message: str
```

<a id="contracts-OperationMode"></a>

### OperationMode

基底：StrEnum。

```text
SYNC = 'sync'
ASYNC = 'async'
```

<a id="contracts-OperationSpec"></a>

### OperationSpec

基底：object。

```text
OperationSpec(name: str, mode: nymph_toolkit.contracts.connections.OperationMode) -> None
  name: str
  mode: nymph_toolkit.contracts.connections.OperationMode
```

<a id="contracts-OutcomeUnknown"></a>

### OutcomeUnknown

基底：HybridError, TimeoutError。

```text
OutcomeUnknown(request_id, message='Request outcome is not confirmed')
```

<a id="contracts-OverflowPolicy"></a>

### OverflowPolicy

基底：StrEnum。

```text
WAIT = 'wait'
DROP_OLDEST = 'drop_oldest'
```

<a id="contracts-PeerClosed"></a>

### PeerClosed

基底：HybridError。

```text
PeerClosed（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-Placement"></a>

### Placement

基底：StrEnum。

```text
LOCAL = 'local'
PROCESS = 'process'
```

<a id="contracts-PreparationTimeoutError"></a>

### PreparationTimeoutError

基底：ConnectionsError, TimeoutError。

```text
PreparationTimeoutError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-ProcessSnapshot"></a>

### ProcessSnapshot

基底：object。

```text
ProcessSnapshot(module_id: str, placement: nymph_toolkit.contracts.hybrid.Placement, generation: str, state: str, pid: int | None = None, returncode: int | None = None, cleanup_confirmed: bool = False, reason: str = '') -> None
  module_id: str
  placement: nymph_toolkit.contracts.hybrid.Placement
  generation: str
  state: str
  pid: int | None
  returncode: int | None
  cleanup_confirmed: bool
  reason: str
```

<a id="contracts-ProtocolError"></a>

### ProtocolError

基底：HybridError。

```text
ProtocolError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-RegistryChange"></a>

### RegistryChange

基底：object。

```text
RegistryChange(module_id: str, before: nymph_toolkit.contracts.registry.RegistryEntry | None, after: nymph_toolkit.contracts.registry.RegistryEntry | None) -> None
  module_id: str
  before: nymph_toolkit.contracts.registry.RegistryEntry | None
  after: nymph_toolkit.contracts.registry.RegistryEntry | None
```

<a id="contracts-RegistryEntry"></a>

### RegistryEntry

基底：object。

```text
RegistryEntry(spec: nymph_toolkit.contracts.registry.ModuleSpec, generation: int, missing_dependencies: frozenset[str] = <factory>) -> None
  spec: nymph_toolkit.contracts.registry.ModuleSpec
  generation: int
  missing_dependencies: frozenset[str]
  property available(self) -> bool
```

<a id="contracts-RegistryError"></a>

### RegistryError

基底：RuntimeError。

```text
RegistryError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-RegistryStateError"></a>

### RegistryStateError

基底：RegistryError。

```text
RegistryStateError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-RegistryUpdate"></a>

### RegistryUpdate

基底：object。

```text
RegistryUpdate(revision: int, changes: tuple[nymph_toolkit.contracts.registry.RegistryChange, ...]) -> None
  revision: int
  changes: tuple[nymph_toolkit.contracts.registry.RegistryChange, ...]
```

<a id="contracts-RemoteError"></a>

### RemoteError

基底：HybridError。

```text
RemoteError(module_id, remote_type, message)
```

<a id="contracts-RuntimeFailure"></a>

### RuntimeFailure

基底：RuntimeError。

```text
RuntimeFailure(failures: tuple[nymph_toolkit.contracts.LifecycleFailure, ...]) -> None
```

<a id="contracts-RuntimeService"></a>

### RuntimeService

基底：Protocol。

```text
RuntimeService(*args, **kwargs)
  async run(self) -> +T_co
  async start(self) -> None
  async stop(self) -> None
```

<a id="contracts-RuntimeState"></a>

### RuntimeState

基底：StrEnum。

```text
NEW = 'new'
STARTING = 'starting'
RUNNING = 'running'
STOPPING = 'stopping'
STOPPED = 'stopped'
FAILED = 'failed'
```

<a id="contracts-RuntimeStateError"></a>

### RuntimeStateError

基底：RuntimeError。

```text
RuntimeStateError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-StorageCorruptionError"></a>

### StorageCorruptionError

基底：StorageError。

```text
StorageCorruptionError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-StorageError"></a>

### StorageError

基底：RuntimeError。

```text
StorageError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-StorageFailure"></a>

### StorageFailure

基底：StorageError。

```text
StorageFailure(cause: Exception, unsaved_events: int, pending_configuration: bool) -> None
```

<a id="contracts-StreamClosed"></a>

### StreamClosed

基底：HybridError。

```text
StreamClosed（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-StreamEvent"></a>

### StreamEvent

基底：object。

```text
StreamEvent(kind: str, sequence: int, data: bytes = b'', missing: tuple[int, int] | None = None, reason: str = '') -> None
  kind: str
  sequence: int
  data: bytes
  missing: tuple[int, int] | None
  reason: str
  property missing_count(self)
```

<a id="contracts-StreamOptions"></a>

### StreamOptions

基底：object。

```text
StreamOptions(send_bytes: int, send_chunks: int, receive_bytes: int, receive_chunks: int, overflow: nymph_toolkit.contracts.hybrid.OverflowPolicy) -> None
  send_bytes: int
  send_chunks: int
  receive_bytes: int
  receive_chunks: int
  overflow: nymph_toolkit.contracts.hybrid.OverflowPolicy
```

<a id="contracts-StreamReceiverProtocol"></a>

### StreamReceiverProtocol

基底：Protocol。

```text
StreamReceiverProtocol(*args, **kwargs)
  async abort(self, reason='Explicit stream abort') -> 'None'
  async aclose(self) -> 'None'
  property buffered_bytes(self) -> 'int'
  property buffered_chunks(self) -> 'int'
  async fail(self, reason) -> 'None'
  property options(self) -> 'StreamOptions'
  property reason(self) -> 'str | None'
  async receive(self, *, timeout) -> 'StreamEvent'
  property state(self) -> 'StreamState'
```

<a id="contracts-StreamSenderProtocol"></a>

### StreamSenderProtocol

基底：Protocol。

```text
StreamSenderProtocol(*args, **kwargs)
  async abort(self, reason='Explicit stream abort') -> 'None'
  async aclose(self) -> 'None'
  property buffered_bytes(self) -> 'int'
  property buffered_chunks(self) -> 'int'
  async close(self, *, timeout) -> 'None'
  property dropped_chunks(self) -> 'int'
  async fail(self, reason) -> 'None'
  property options(self) -> 'StreamOptions'
  property reason(self) -> 'str | None'
  async send(self, data: 'bytes | bytearray | memoryview', *, timeout) -> 'int'
  property state(self) -> 'StreamState'
```

<a id="contracts-StreamState"></a>

### StreamState

基底：StrEnum。

```text
OPEN = 'open'
CLOSING = 'closing'
CLOSED = 'closed'
ABORTED = 'aborted'
FAILED = 'failed'
```

<a id="contracts-TaskManagerLifecycleFailure"></a>

### TaskManagerLifecycleFailure

基底：ActivityError。

```text
TaskManagerLifecycleFailure(failures: tuple[nymph_toolkit.contracts.LifecycleFailure, ...])
```

<a id="contracts-TemporaryUnavailable"></a>

### TemporaryUnavailable

基底：object。

```text
TemporaryUnavailable(message: str = 'Provider has no capacity or is not accepting work') -> None
  message: str
```

<a id="contracts-UNCHANGED"></a>

### UNCHANGED

値：`UNCHANGED`。

<a id="contracts-UnknownActivityError"></a>

### UnknownActivityError

基底：ActivityError。

```text
UnknownActivityError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-UnknownConnectionError"></a>

### UnknownConnectionError

基底：ConnectionsError。

```text
UnknownConnectionError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-UnknownModuleError"></a>

### UnknownModuleError

基底：RegistryError。

```text
UnknownModuleError（構築署名はPython標準の基底例外に従う）
```

<a id="contracts-Usage"></a>

### Usage

基底：object。

```text
Usage(state: nymph_toolkit.contracts.connections.OperatingState = <OperatingState.UNKNOWN: 'unknown'>, accepting: bool = False, active: int = 0, capacity: int = 0) -> None
  state: nymph_toolkit.contracts.connections.OperatingState
  accepting: bool
  active: int
  capacity: int
  property free(self) -> int
```
