# Core APIと利用上の契約

本書はv0.9の完成確認で整理した、実装済みCore・Contractsの入口である。仕様の根拠はADR 0014〜0025。公開名は `nymph_toolkit.core` の14件、`nymph_toolkit.contracts` の92件で、[実装一覧](api-reference.md)に構築引数・メソッド・型・列挙値を収録する。v1.0の接続契約体系化・互換性保証の範囲は別目標であり、本書だけで採用しない。

## 入口と返却値

| 入口 | 入力と結果 | 利用・所有期間 |
|---|---|---|
| Runtime | `Runtime(service)`。`start()`は初期化を待ちNone、`wait()`はrunの値または停止時のNone、`stop()`は後処理を待ちNone | 一度だけ起動し同じイベントループで操作。stopは繰返し可能。失敗時は保持したRuntimeFailureを再通知 |
| Registry | `register(ModuleSpec)` / `unregister(id)`→RegistryUpdate。`get(id)`→RegistryEntry、`entries()`→ID順タプル | 作成スレッドで使用。世代・revision・依存の充足を返し、実行中や通信可能という意味を持たない |
| ModuleGroup | `register(spec, service)`→RegistryUpdate。get/entries/unregisterはRegistryと同じ観測 | 起動前に構成。Runtimeがstart/run/stopを所有し、依存順初期化・逆順後処理。停止後の解除は可能、再登録・再起動には新しいGroup |
| Connections | `declare(advertisement, handlers)`と`publish_usage`→None。`candidates(contract)`→Candidateタプル | 機能が状態を通知し、要求側が候補を選ぶ。Groupに一度取り付け、保存を含むライフサイクルを所有させる |
| Connections.bind | 要求元・契約ID/版・提供先・wait_timeout→ConnectionSnapshot | 稼働中の初回接続を保存。確定先の変更不可。接続の返却と今すぐ呼べることを区別 |
| Connections.prepare / invoke | BindingKeyと準備期限→PreparedConnection / 操作結果 | 確認中・中断中は期限まで待機。期限は操作本体の時間制限ではない |
| PreparedConnection | prepareが返す窓口。callはSYNC、acallはASYNCの宣言と引数→提供側の値 | 直接構築しない。許可済み接続を使用し、ローカルの無効状態を確認。毎回の候補選定・許可再審査は行わない |
| FileStore | 主・予備ディレクトリ、retention、batch_size、flush_interval。`append(kind, data)`→None、`flush()`→None | Group/Connectionsが所有。appendはメモリ受付、flushはその時点までの保存。主保存先はCore間で共用しない |
| TaskManager | Connections、時計監視間隔、任意のmax_running。`submit(request, execute, supports_pause=...)`→ActivitySnapshot | Groupが所有する。状態と結果は起動内で保持。実行関数はActivityContextを受け取る |
| HybridGroup | settingsとstore。`register_module(spec, advertisement, factory, config, placement)`→RegistryUpdate | factoryはimport可能なmodule:attribute。既存Groupと同じライフサイクル、稼働中構成は固定 |
| HybridTaskManager | `enable_activities(...)`で取り付け。`submit_remote(request, module_id, executor_id, arguments)`→ActivitySnapshot | 登録済み実行処理IDを使用。関数・継続状態の転送や再起動後の自動復元なし |
| ModuleContext | factoryに渡される機能用コンテキスト。provide / provide_stream / provide_executor→None | 直接構築しない。初期化中に宣言と一致するハンドラーを登録。coreから管理へ操作を届ける |
| CoreClient | `context.core`、親のLOCAL機能は`group.client(id)` | 直接構築しない。candidates/bind/prepare/invoke/usage/health/notice/活動操作を親Coreへ届ける |
| DirectLink | `await core.prepare(...)`で取得。acall→操作結果、open_stream→StreamSender | closeで通信資源を回収。失敗後のprepareは機能側の明示操作、自動再送・接続先切替なし |
| StreamSender / StreamReceiver | open_stream / 受信ハンドラー引数として取得。send→連番、receive→StreamEvent | 直接構築しない。利用機能がclose/abort/acloseと、活動中断・終了時の扱いを担当 |

詳細は[Runtime](runtime.md)、[Registry](registry.md)、[Connectionsと保存](connections.md)、[活動管理](task-manager.md)、[ハイブリッド実行](hybrid.md)を参照する。公開一覧に現れるGroupのstart/run/stopや基盤用補助入口を、Runtimeの所有中に別途呼び出さない。

## 値の定義と配置差

| 入力 | 検証・意味 |
|---|---|
| ModuleSpec | module_id、ModuleKind（SUBSYSTEM/ADAPTER）、依存ID集合。重複・循環を拒否し、不足依存を観測する |
| ContractKey / ContractSpec / OperationSpec | 契約IDと版の完全一致。操作名とSYNC/ASYNCを明示。同じ契約を配置で暗黙に読み替えない |
| ModuleAdvertisement / Usage | 実装版・契約・タグ・属性、現在のstate/accepting/active/capacity。候補順は最適順ではなく、容量情報は予約ではない |
| ActivityKey / ActivityRequest | 要求元と活動ID、内容、開始時刻または即時のNone、期間、JSON互換パラメータ、整数優先度（bool不可） |
| 時刻・期間 | offset付きdatetimeをUTCへ正規化。期間は正のtimedelta。受付時点の過去開始は拒否。予定到達は通知して継続し、実開始が遅れてもCoreが予定を繰り延べない |
| ActivityChange | 未指定はUNCHANGED。start_at=Noneは即時変更で、未指定と異なる。durationは現在の予定開始からの新しい合計期間 |
| Connections.wait_timeout | 0以上の有限秒。準備・受付待ちに使い、0なら即時準備可能な場合だけ進む |
| HybridSettingsと通信timeout | 正の有限秒。フレーム・同時要求・ストリーム数は正整数。明示値またはCoreClientのcall_timeoutを使う |
| StreamOptions | 送受信それぞれのバイト・件数上限、WAIT/DROP_OLDEST。開設後は固定。本文はbytes/bytearray/memoryviewからコピーしたバイト列 |

既存のModuleGroup/Connectionsによる同一プロセスの操作入力をJSONへ制限しない。HybridGroupの設定・CoreClient経由の転送入力・別プロセスの引数と結果にはJSON値および許可したContractsを用いる。Pythonオブジェクトの同一性、例外オブジェクトの同一性はプロセスを越えて保証しない。内部wire形式を任意Python型の転送契約へ広げない。

## 活動要求と観測

Nymphが内容・時刻・期間・優先度・変更を決定する。Coreは機械的な実行枠・状態整合・通知を担当する。

| TaskManagerの操作 | 結果と意味 |
|---|---|
| snapshot(key) / activities(requester_id=None) | ActivitySnapshot / タプル。初回requestとcurrent_request、revision、scheduled_revisionを区別 |
| change(key, change, command_id, expected_revision) | ActivityCommandResult。全項目を一括検証。拒否で元の入力を変更しない |
| request_pause / request_resume | ActivityCommandResult。acceptedは適用完了でなく、実行側の安全な区切り・報告を待つ |
| command_result / wait_command | 保持した命令結果 / 終端結果を待機。同じID・同じ内容は二重適用しない |
| request_finish(key, reason=NYMPH) | 現在のActivitySnapshot。終了受理と実終了・後処理完了を分ける |
| wait(key) | 終端のActivitySnapshot。活動失敗はsnapshot.failureに保持 |
| next_notice(requester_id) | 要求元別FIFOのActivityNotice。Coreが活動の価値を判断した通知ではない |
| history(requester_id) | 過去起動のActivityHistory。読出し問題をissuesへ返し、活動を自動再登録しない |

CoreClient.activityのoperationはsnapshot/change/pause/resume/finish/wait/command/notice/history。`command`はwait_commandに対応し、`command_id`を渡す。changeには`change`、変更・中断再開には`command_id / expected_revision`を渡す。notice/historyは呼出元を用い、keyを省略する。自身の要求元IDの活動を対象とする。

ActivityStateはPENDING、STARTING（遠隔の実開始待ち）、RUNNING、PAUSING、PAUSED、RESUME_PENDING、FINISHINGと各終了状態を持つ。正確な列挙値は[API一覧](api-reference.md)に示す。状態・通知の時点を先取りせず、実行側の報告が届くまで確定させない。elapsed_secondsは実開始後の経過、execution_secondsは実際の中断を除いた実行側単調時計の値で、CPU時間ではない。遠隔ではtiming_confirmed/cleanup_confirmedを確認する。

## 失敗の種類と呼出側の対応

例外が返る入口と、通常の値として失敗を返す入口を分ける。配置を越える例外の型はRemoteErrorのremote_type等に記録され、元の例外クラスのインスタンスとは限らない。

| 種類 | 公開型・結果 | 対応 |
|---|---|---|
| 入力の型・値 | TypeError / ValueError | 宣言・値を修正。勝手な補正や自動再試行を期待しない |
| Runtime・Group | RuntimeStateError、RuntimeFailure / LifecycleFailure、ModuleGroupFailure / ModuleFailure | stateと各失敗phaseを確認。後処理失敗を実行失敗とともに保持 |
| Registry | RegistryError、RegistryStateError、DuplicateModuleError、UnknownModuleError、DependencyCycleError、DependencyUnavailableError | 登録の不整合・構成固定・依存不足を解消。登録失敗で部分的な登録を成功扱いしない |
| 接続API | ConnectionsError、ConnectionsStateError、ContractDeclarationError、UnknownConnectionError、ConnectionConflictError、ConnectionUnavailableError、ConnectionNotReadyError、PreparationTimeoutError | 対象・宣言・状態・待機期限を確認。異なる提供先への稼働中切替をしない |
| 通常業務・容量 | OperationFailure / TemporaryUnavailable（値） | 機能が次の活動を判断。Coreの全体停止や自動再送を起こさない |
| 連携の想定外失敗 | LinkFailure（値）、ConnectionNotice | 要求元が中断・後処理・完了報告。ヘルス確認後は新規要求だけ再開 |
| 接続・保存基盤 | ConnectionsLifecycleFailure、StorageError、StorageCorruptionError、StorageFailure | 新規受付停止・古い履歴退避・回復または未保存報告と終了。破損原本を保全 |
| 活動入力・状態 | ActivityError、ActivityStateError、ActivityAdmissionError、ActivityStartInPastError、DuplicateActivityError、UnknownActivityError | Nymphへ返して再指定を待つ。実行途中の価値判断をCoreへ移さない |
| 活動の結果・基盤 | ActivityFailure、ActivityCommandResult、TaskManagerLifecycleFailure | 活動失敗、要求のrejected/failed/superseded、基盤失敗を区別 |
| IPC | HybridError、ProtocolError、PeerClosed、RemoteError | 不正形式・切断・遠隔失敗を区別。子の予期しない終了はRuntime停止 |
| RPC容量・結果不明 | CapacityExceeded、OutcomeUnknown、TimeoutError | 未送信期限切れと送信開始後の結果不明を区別。IDを照会して完了後にrelease |
| ストリーム | StreamClosed、ChunkTooLarge、TimeoutError、StreamEventのerror | 待機だけの期限切れとストリーム障害を区別。大きすぎるチャンクは送信側で分割 |

`Runtime.wait`、活動のwait/wait_command、受付済み管理要求の待機取消で、所有する処理自体が取り消されたと推測しない。Runtime.startの取消は停止を要求し、通常RPCの取消は協調的に伝える。停止待機が取り消されてもCoreは後処理を継続するため、所有者は再度stop/waitで終了を確認する。

## 結果・資源・保存の所有

- CoreClientとDirectLinkのpending_requestsはその窓口の未完了・保持結果ID。期限切れ・取消後の結果はresultで確認し、完了後にreleaseする。未完了の解放はOutcomeUnknown。通常どおり応答を受け取ったRPCの一時結果は呼出し内で回収される。ローカルでRPCを使わない入口は空一覧となる。
- 通信結果の解放で活動・命令結果・保存履歴は消さない。過去履歴、現在の活動、未保存イベント、一時RPC結果は別の所有物である。
- sendの成功はローカル受付。closeの成功は先行データ・終端の通信上の受信確認。受信機能の内容処理完了は独自契約で確認する。
- Core停止では活動・機能・所有通信資源・保存を後処理する。通常の活動終了には強制終了期限を適用しない。Core所有の子だけはCore停止期限後に強制終了し、後処理未確認を記録できる。
- FileStoreの通常バッファは上限なし。保持活動・通知・未保存が増え続ければメモリも増える。新しい上限や自動削除をこの資料で追加しない。

## 検証と制限

[64項目の対応表](validation/core-coverage.md)と[v0.9の検証記録](validation/v0.9.md)からダミー・実装・各ADRを追跡できる。API一覧の機械的な一致は振る舞いの合格を意味しない。既存テスト・4配置統合・通常配布と組み合わせて判定する。

同一PC、同じPython環境、Core所有子、起動前・停止後の着脱を対象とする。同一プロセスでは協調しない処理を強制停止できない。失効は連携上の不整合回避を目的とし、敵対する機能を遮断するセキュリティ境界ではない。本番機能、Desktop Adapter、複製・移植・伝播、分散、活動継続状態の永続復元は含めない。
