# Connectionsの操作契約（v0.4開発中）

本書は[ADR 0019](adr/0019-v0.4-connections.md)に基づく、現在の接続APIの説明である。**v0.4全体の受入・公開は継続中。** 接続制御に加え、非同期FileStoreと実ファイルによるRuntime結合を実装した。公開済みv0.3.0のAPI説明ではなく、main上の開発状況として読む。

検証対象と未完了項目は[検証経過](validation/v0.4.md)、採用方針は[ADR 0018](adr/0018-connection-selection-health-and-recovery.md)を参照する。ここでいう契約IDは接続用の識別子であり、Nymphの活動内容や価値の判断をCoreへ移すものではない。

## 起動と所有

`Connections`と`PreparedConnection`は`nymph_toolkit.core`、共有する型・結果・例外は`nymph_toolkit.contracts`からimportする。

Connectionsは一つの作成スレッド・イベントループで利用する。一度開始したインスタンスを再起動せず、次の起動では新しいインスタンスを作る。構成は次の順序に従う。

1. RegistryまたはModuleGroupへ機能を登録する。実体の登録と接続設定の追加は別操作である。
2. Connectionsへ`declare`で機能の宣言と提供する操作ハンドラーを登録する。宣言は開始前に固定する。
3. ModuleGroupを使う場合、同じModuleGroupを照会元とするConnectionsを`attach_connections`で一度だけ取り付ける。接続管理をダミーSubsystemとして登録しない。
4. Runtimeが保存の初期化、各機能の`start`と現在状態の通知、保存済み接続の検証、`run`を順に進める。機能の`start`で通常の接続利用を待たず、要求は`run`以降に行う。
5. 終了時は新規要求・準備待機を終了させ、各機能の停止と後処理、保存の終了を行う。ライフサイクルはRuntime・ModuleGroupに所有させる。

Connectionsを単独のRuntimeServiceとして扱うテストでは、開始前に各機能の現在状態を通知する。`run`はヘルス申請処理と保存障害監視を担い、単なる初期化関数ではない。独自の所有者で使う場合も、`run`タスクの取消・回収と`stop`の順序を担当する必要がある。

## 宣言・候補・選定

| 型・入口 | 扱い |
|---|---|
| `ContractKey(contract_id, version)` | 契約IDと明示版。文字列の完全一致で照合し、提供側の実装版から推定しない |
| `ContractSpec(key, operations)` | `OperationSpec(name, OperationMode.SYNC / ASYNC)`の集合。同じ契約ID・版に異なる操作宣言を登録しない |
| `ModuleAdvertisement(module_id, implementation_version, contracts, tags, attributes)` | 静的な宣言。属性はJSONスカラー値で、関数や可変オブジェクトを条件として渡さない |
| `declare(advertisement, handlers)` | 提供契約から操作名と関数への対応を渡す。契約を提供しない要求元の宣言ではhandlersを省略できる |
| `publish_usage(module_id, usage, contracts=...)` | `Usage(state, accepting, active, capacity)`を開始時・変更時に通知する。契約ごとの状態は明示した項目を更新する |
| `candidates(contract)` | 対応する候補と属性・登録情報・機能全体および契約の稼働情報を、不変スナップショットで返す |

候補には停止・異常・満杯・未通知の機能も含まれる。ID順は一覧を安定させるための順序であり、最適な候補順ではない。要求側がタグ・属性・稼働情報などから選び、そのIDをCoreへ渡す。Coreへ選定関数を預ける方式は使わない。

Registryの`available`は登録依存の充足、`Usage.state`は通知された稼働状態、`accepting`と`free`は受付と容量の情報である。未通知は`UNKNOWN`。これらを相互に推測せず、現在の候補情報を処理枠の予約保証として扱わない。実際の受付は提供側が判断し、満杯なら直ちに`TemporaryUnavailable`を返す。

## 接続の確立と固定

`await connections.bind(requester_id, contract, provider_id, wait_timeout=...)`で、要求側が選んだ接続先を確立する。`BindingKey(requester_id, contract)`ごとに1接続で、用途別の複数接続は設けない。

同じキー・相手への再要求は既存の`ConnectionSnapshot`を返す。同じキーで別の相手を指定すると`ConnectionConflictError`。初回に相手が停止・異常・未通知なら`ConnectionUnavailableError`となり、設定を確定しない。保存完了後に確立済みとして公開する。

`bind`の既存接続の返却は、直ちに操作を開始できるという保証ではない。失効・検証中・機能の中断中などは`prepare`で扱う。初回の確立待ちには必須の期限を使うが、開始済みの保存トランザクションをその期限で強制打切りにしない。保存開始後の取消は保存とメモリ反映の完了を待って返るため、取消後でも接続が確立している場合がある。同じ指定の再要求または`connection(key)`で確認できる。

稼働中に失効しても接続先を切り替えない。起動時だけは、保存設定を現在の宣言・登録・稼働状態で確認し、有効なら再利用、無効なら除外して次の要求で選び直せる。同一IDへの再登録は世代が異なるため、古い実体の宣言を引き継がない。運用履歴から現在の稼働値を復元しない。

## 操作と期限

| 操作 | 結果・制限 |
|---|---|
| `await prepare(key, wait_timeout=...)` | 確認・中断・保存側の受付停止が解けるまで待ち、準備済み接続を返す |
| `handle.call(operation, *args, **kwargs)` | SYNC宣言の操作を保持したハンドラーで直接呼ぶ |
| `await handle.acall(operation, *args, **kwargs)` | ASYNC宣言の操作を保持したハンドラーで直接呼ぶ |
| `await invoke(key, operation, wait_timeout=..., args=(), kwargs=None)` | Core経由で同じ準備・操作契約を利用する |

`wait_timeout`は0以上の有限秒数を必ず指定し、イベントループの単調時計で準備期限を測る。0は直ちに準備できる場合だけ進む。期限切れは`PreparationTimeoutError`、終了中は`ConnectionsStateError`。この期限は操作本体の実行時間制限ではない。

準備後に状態が変わったハンドルは、操作を開始せず`ConnectionNotReadyError`を返すため、新しい準備へ戻る。要求元・提供側のどちらかが協調的中断中でも新規操作を始めない。このローカル状態の確認と、毎回の候補検索・許可条件の再審査は別である。

提供側が返す`OperationFailure`は宣言した通常失敗、`TemporaryUnavailable`は容量などの一時利用不可であり、これだけでは中断・ヘルス申請を起こさない。提供側の想定外例外・宣言モード違反は`LinkFailure`として元例外と中断通知IDを保持する。未知の操作名・呼出側のモード間違いは`ContractDeclarationError`というAPI誤用として区別する。

要求側の準備取消はその待機だけを取り消す。async操作中の呼出側の取消は操作へ伝播し、それだけを提供側障害と判定しない。Coreの実行管理から外れた任意のPython参照を強制遮断する仕組みではない。

## 協調的中断と復帰

要求元AがBへの連携エラーを起こした場合、CoreはAの機能全体を`INTERRUPTING`として通知する。Aは`next_notice("A")`で通知を受け、自身の操作契約に従う巻戻し・後処理を完了してから、`acknowledge_interruption("A", notice_id)`で報告する。古い通知IDへの完了報告は新しい中断を解除しない。

完了報告後は`SUSPENDED`。原因接続の正常確認と、新規の準備要求が揃って`RUNNING`へ戻る。Aが提供する操作への新規要求も復帰の契機となる。原因接続が異常・検証中のままなら、後処理完了だけで復帰しない。ヘルス結果が異常でも準備待機は各要求の期限まで続き、後続の外部申請による正常確認を待つ。

Aの機能全体の中断には、Aからの送信だけでなくAが受ける新規操作も含まれる。既に進行中の操作や機能内部の作業はA自身が協調して停止する。Coreは汎用的な`task.cancel()`で中断完了を偽装しない。

Bの異常を確認したら、Bを利用するC・Dへ該当接続の`INVALIDATED`を通知する。C・D自身の全体中断にはせず、その依存処理を避けられるようにする。Bの別の正常契約・無関係なEを一律停止しない。`RECOVERED`は接続の正常化、`RESUMED`は中断機能の新規要求に伴う復帰であり、元の失敗操作の再生を意味しない。

`OperatingState`と`ModuleExecutionState`は区別する。サービスの存在・稼働が正常でも協調的中断中は操作できない。中断だけを理由に稼働情報を`STOPPED`へ書き換える必要はなく、実際の停止・障害を機能から通知する。

## ヘルス申請と保存の残課題

`health_check(module_ids=..., bindings=...)`で機能・接続を指定し、両方を省略すると全体を確認する。受付ごとに異なる申請IDでFIFO処理し、申請者が待機を取り消しても受付済み申請は処理する。機能固有の自己診断を呼ばず、保持している登録世代・宣言契約・稼働状態を確認する。Coreの定期申請や自動再選定は行わない。

`HealthResult`の`BindingHealth`はその申請の観測結果。`connection(key)`の`ConnectionSnapshot`は保留中の別申請も含む現在状態で、別の確認が残っていれば`CHECKING`になり得る。

履歴・接続設定は`nymph_toolkit.core.FileStore`で保存する。主保存先・予備先、`retention`（0以上のtimedelta）、`batch_size`（正の整数）、`flush_interval`（正の有限秒数）を構築時に明示する。主保存先と予備先は相互に包含しない専用ディレクトリとし、同じ主保存先を複数Coreで同時使用しない。

ユーザー回答により、通常の未保存バッファには上限を設けず、新規受付を継続する。`batch_size`は一回の書込件数であり受付停止の閾値ではない。`unsaved_events`で未保存件数を参照でき、生成が書込みを上回り続けるとメモリ使用量も増える。件数または間隔を契機に別スレッドでまとめて書き、明示的な`flush`はその時点までの履歴を保存する。

保存I/Oが失敗したときは受付を停止し、古い履歴を予備先へ検証付きで退避してから元の保存を一回再試行する。回復すれば受付を再開し、回復不能なら`StorageFailure`に原因・未保存件数・未保存設定の有無を残してRuntimeを終了する。終了時の追加バッファ退避は行わない。破損設定を空の設定へ置き換えず、原本を保全して失敗を報告する。

通常停止では進行中のI/Oと未保存履歴を回収する。呼出側による保存・停止の取消でも開始済みI/Oの完了まで所有し、停止完了後にスレッドだけが書込みを続ける状態を作らない。急なプロセス終了による未保存分の損失は許容される限界であり、履歴から現在の稼働状態を復元しない。

公開APIの最終照合、構築・実行例、性能・配布を含む受入が完了するまでは、本書をv0.4の完成済み利用手順として扱わない。
