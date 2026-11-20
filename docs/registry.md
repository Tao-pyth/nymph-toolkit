# RegistryとModuleGroup

v0.3の採用契約は[ADR 0016](adr/0016-v0.3-registry.md)に記録する。実装・公開の状態は[README](../README.md)を参照する。CoreとContractsは一つのパッケージに含める。

実行例は [examples/registry_demo.py](../examples/registry_demo.py)。インストール後に `python examples/registry_demo.py` を実行すると、ダミーAdapterとSubsystemの登録、依存先の追加・解除による変更通知、依存順の初期化・逆順の後処理、残存タスク0件を確認できる。ダミーの名称は将来の本番Subsystem・Adapterの実装を示すものではない。

## 登録情報と依存関係

`nymph_toolkit.core.Registry` に `nymph_toolkit.contracts.ModuleSpec` を登録する。ModuleKind.SUBSYSTEMとModuleKind.ADAPTERを同じ契約で扱う。IDは利用側が指定する、前後空白のない空でない文字列である。

| 操作・情報 | 契約 |
|---|---|
| `ModuleSpec(module_id, kind, requires=frozenset())` | 不変の登録情報。requiresをID集合へコピー。自己依存はRegistryで拒否 |
| `registry.register(spec)` | 登録しRegistryUpdateを返す。重複・循環は変更せず拒否 |
| `registry.unregister(module_id)` | 解除しRegistryUpdateを返す。未登録IDは変更せず拒否 |
| `registry.get(module_id)` | 不変のRegistryEntry。実体や通信ハンドルは返さない |
| `registry.entries()` | ID順のEntryのtuple |
| `registry.revision` | 成功した変更の通し番号。失敗では進めない |
| `entry.generation` | 登録時のrevision。同じIDの再登録を区別できる |
| `entry.available` | 推移的な不足依存がないこと。稼働状態・正常性・通信許可を意味しない |
| `entry.missing_dependencies` | 直接・間接に不足しているIDのfrozenset |
| `update.changes` | ID順のRegistryChange。before/afterは変更前後のEntry。登録前・解除後はNone |

依存先が未登録でも登録できる。不足先を登録すれば利用可能となり、解除すれば依存元が利用不能になる。その変化は操作結果に同梱して通知する。継続購読や通知の永続保存は提供しないため、利用側は返された変更結果を処理する。

すべての操作はRegistryを作成したスレッドで呼ぶ。awaitやコールバックは含まれない。返されたスナップショットは後続の登録・解除で書き換わらない。最新情報は再照会する。

## Runtimeから複数対象を動かす

`nymph_toolkit.core.ModuleGroup` に、ModuleSpecとRuntimeServiceを満たすダミーを `register(spec, service)` で登録する。ModuleGroupを既存の `Runtime(group)` に渡し、通常のstart・wait・stopで制御する。

ModuleGroupのregister・unregister・get・entries・revisionはRegistryと同じ情報を扱う。実体は内部に保持し、外部へ返さない。不足依存があれば初期化を始める前に失敗する。依存順（同順位はID順）にstartし、全初期化が成功してから各runをタスクとして実行する。正常時はwaitがID別の戻り値を返す。

startに入ってからstopの完了まで構成を固定する。この期間の登録・解除はRegistryStateErrorとする。実体の稼働中着脱はConnectionsの解除・失効契約を扱う後続段階へ延期する。停止後も登録情報は残り、明示的にunregisterできる。開始後の追加登録と再起動は拒否し、再実行には新しいModuleGroupとRuntimeを使う。

## 失敗と後処理

RegistryErrorの派生としてDuplicateModuleError、UnknownModuleError、DependencyCycleError、DependencyUnavailableError、RegistryStateErrorを使う。不正な型・IDはTypeError／ValueErrorで通知する。

ModuleGroup内のサービス失敗は、対象ID・LifecyclePhase・元例外を持つModuleFailureへ記録し、ModuleGroupFailureにまとめる。外側のRuntimeFailureの各LifecycleFailure.exceptionから確認できる。初期化失敗時も、その対象を含めて初期化に入った順の逆順でstopする。実行中の失敗は他対象の停止につながり、複数失敗も保持する。

呼出側の取消・Runtimeの状態・停止完了は[Runtimeの契約](runtime.md)に従う。ModuleGroupが作るタスクを完了させ、サービスのstopは各サービスが所有するタスク・接続を終了させる。stopの通常の失敗があっても他対象の後処理を続ける。無関係な呼出側タスクは停止しない。

初期化中のCancelledErrorはRuntimeへそのまま伝播し、対象IDを例外のnoteへ残す。停止要求による取消と予期しないサービス側取消の区別を既存Runtimeに委ねるためである。ModuleGroupのライフサイクルメソッドは一つのRuntimeの監督タスクから呼び、別Runtimeで同じGroupを同時に実行しない。

## 通信・活動管理との境界

[ADR 0015](adr/0015-core-authorized-direct-communication.md)でCoreが管理・許可した直接通信は採用済みである。Registryの登録・照会は通信の許可操作ではなく、v0.3ではConnections・許可API・直接通信を実装しない。依存IDの宣言も、他の具体的実装への参照を与えるものではない。

Nymphが活動を決定し、Coreが実行管理する。ModuleGroupのライフサイクル管理に、活動の価値評価・時間指定・優先度生成を追加しない。
