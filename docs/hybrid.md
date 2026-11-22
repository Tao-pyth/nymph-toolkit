# v0.7 ハイブリッド実行と通信

[ADR 0022](adr/0022-v0.7-v0.9-hybrid-and-completion.md)の採用方針を、[ADR 0023](adr/0023-v0.7-implementation-contracts.md)で実装契約へ具体化した。実行可能な例は[hybrid_demo.py](../examples/hybrid_demo.py)、試験結果は[v0.7受入記録](validation/v0.7.md)にある。v0.7で導入した機能に、v0.8で統合検証と通信結果・受付枠の回収を追加した。

## 構成と起動

`HybridGroup(settings, store)`はModuleGroupを拡張する。親CoreだけがRegistry・Connections・TaskManager・FileStoreを所有し、`Runtime(group)`で起動・停止する。`register_module(spec, advertisement, factory, config, placement)`で機能を登録する。`Placement.LOCAL`は同一プロセス、`PROCESS`は機能ごとにCore所有の子を起動する。

`factory`は共有Python環境からimportできる`module:attribute`、`config`はJSON値である。factoryは`ModuleContext`と設定を受け取り、非同期の`start/run/stop`を持つサービスを返す。通常は機能を同じ環境にインストールする。ダミー例は例のディレクトリだけを親・子からimport可能にする。子はCoreと同じ`sys.executable`を使用し、標準出力・標準エラーをIPCに流用しない。

`HybridSettings(startup_timeout, shutdown_timeout, call_timeout, max_frame_bytes, max_requests, max_streams)`はすべて明示指定する。期限は正の有限秒、個数・長さは正整数。`max_requests`はRPC窓口と機能の同時操作を制限する。活動の実行枠、ストリーム転送量、上限なしの通常履歴バッファとは別である。起動bootstrapの上限は1 MiBと設定フレーム上限の小さい方。

Windowsでは子プロセスに対応するイベントループが必要で、標準の`asyncio.run`を使う。非対応ループでは起動に失敗する。同一PCの127.0.0.1・OS割当ポートだけを使う。稼働中構成は固定。停止後の解除は可能だが同じGroupの再起動はできず、新しいGroupとRuntimeを作る。

## 機能と接続

初期化中に次を宣言する。操作名は`ModuleAdvertisement`の契約宣言と一致させる。同じ操作に通常ハンドラーとストリーム受信を重複登録できない。

| ModuleContextの入口 | 内容 |
|---|---|
| `provide(contract, handlers)` | 非同期操作名と関数の対応 |
| `provide_stream(contract, operation, handler)` | `(receiver, metadata)`を受け取る非同期受信処理 |
| `provide_executor(id, handler, supports_pause=False)` | `(activity_context, arguments)`を受け取る登録済み活動実行処理 |
| `core` | 親管理へのCoreClient |

`context.core.publish_usage(usage, contracts=...)`で機能が現在の稼働状況を通知する。起動時も機能から取り直し、保存された過去の稼働状態を現在値にしない。

CoreClientの主な操作は次のとおり。期限省略可能な管理操作は`call_timeout`を使う。

| 非同期入口 | 内容 |
|---|---|
| `candidates(contract)` | 候補・属性・稼働情報。要求側が利用先を決める |
| `bind(contract, provider_id, timeout=...)` | 要求元＋契約ID・版の接続を保存。稼働中の変更は不可 |
| `prepare(contract, timeout=...)` | 確認中・中断中は期限まで待ち、許可済みDirectLinkを返す |
| `invoke(contract, operation, *args, timeout=..., **kwargs)` | Core経由の通常操作 |
| `health_check(module_ids=..., bindings=...)` | 個別ヘルス申請。定期実行・申請の統合なし |
| `next_notice(timeout=...)` / `acknowledge_interruption(id)` | 要求元が中断・後処理し、完了を報告 |

`link.acall(operation, *args, timeout=..., **kwargs)`は許可済み直接経路を使う。双方が同一プロセスなら通常のメソッド呼出し、別配置なら専用RPCで実行する。親Coreへ利用ごとの許可照会をしない。Coreの管理変更はキャッシュした窓口へ通知され、新規利用を制限する。途中の業務処理は利用機能が協調的に整理する。

別プロセスの操作引数・結果はJSON値と明示したContractsに限定する。pickle・任意型のimportは行わない。HybridGroupの遠隔宣言はASYNCのみとし、既存のModuleGroup/Connectionsの同期操作・ローカル入力を変更しない。

業務失敗は`OperationFailure`、受付容量不足は`TemporaryUnavailable`。通常の連携失敗は`LinkFailure`と要求元への中断通知で扱う。予想外例外の情報は`RemoteError(module_id, remote_type, message)`。通信切断は`PeerClosed`。送信ロック待ちで書込み開始前に期限切れとなった場合は`TimeoutError`として未送信の枠を回収します（#80）。書込み開始後の期限切れは協調的取消を送り`OutcomeUnknown(request_id)`を返し、タイムアウトだけで提供先の障害と判断しない。直接RPCの遅い結果は`link.result(id)`で照会し、確認後`link.release(id)`で一時保持を解放できる。`link.close()`は窓口の通信資源を閉じる。自動再送・自動再接続をせず、復帰後の新規処理には機能が明示的にprepareする。

## 通信結果の保持と解放

v0.8の子Issue #78で、上記の一時結果の保持を管理RPCにも具体化した。子の`context.core.pending_requests`は未完了または完了後に保持中のIDのタプルを返す。`core.result(id)`で元の管理要求の結果・例外を照会し、確認後に`core.release(id)`を呼ぶ。`prepare`の遅い結果は経路情報でありDirectLinkではない。未完了の解放は`OutcomeUnknown`となる。待機取消では例外からIDを受け取れないため、一覧から照合する。直接RPCも`link.pending_requests`を使える。IDは窓口・起動世代内に限り、別の窓口へ渡さない。同一プロセス入口にはRPC結果がなく一覧は空である。

内部のライフサイクル操作・子の報告は、呼出し所有者が完了後の解放を指定する。期限切れだけで未完了の容量枠を解放せず、結果または切断の確認後に一時結果を回収する。活動・変更結果・履歴の保持は変わらない。根拠は[ADR 0024](adr/0024-v0.8-integration-validation.md)と[検証記録](validation/v0.8.md)。

## ストリーム

`link.open_stream(operation, StreamOptions(send_bytes, send_chunks, receive_bytes, receive_chunks, overflow), metadata=None, timeout=...)`で片方向のStreamSenderを得る。`overflow`は`WAIT`か`DROP_OLDEST`。双方向は独立した2本を開く。ストリームごとにIDとTCP接続を持ち、管理RPCとデータ用の待機列を分ける。

| 操作・観測 | 契約 |
|---|---|
| `sender.send(data, timeout=...)` | コピーしたバイト列をローカル転送キューへ受付し連番を返す。相手の受信や処理の完了ではない |
| `receiver.receive(timeout=...)` | `StreamEvent`のdata / end / errorを返す。空バイト列もdata |
| `event.sequence / missing / missing_count` | 連番、欠落範囲、欠落件数 |
| `sender.close(timeout=...)` | 未破棄データと終端の通信上の受信確認まで待つ。内容処理完了は含まない |
| `state / reason` | OPEN / CLOSING / CLOSED / ABORTED / FAILEDと理由 |
| `abort(reason)` | 双方からの明示打切り。未転送分を破棄し待機を解除 |
| `buffered_bytes / buffered_chunks / dropped_chunks` | アプリケーションのキュー量、送信側の破棄数 |
| `aclose()` | 所有者が通信タスク・ソケットを回収する |

受信可能量を返すため、送信側だけを制限して受信側が増え続ける構造にはしない。上限はアプリケーションのキューを指し、OS内部のTCPバッファを含まない。チャンク超過は`ChunkTooLarge`で拒否し自動分割しない。古い未転送チャンクだけを丸ごと破棄する。

送信受付前の待機取消・期限切れは後から受付しない。受付後の内容は送信者の書換えで変わらない。終了待機がタイムアウトしてもCLOSINGの排出処理は続き、照会・再度のclose・明示abortが可能。受信期限切れもその待機だけを終了する。切断時は既受信データの後に異常終端を返し、自動再開しない。受信ハンドラーの想定外例外はFAILEDと要求元の連携エラー通知にし、明示打切りABORTEDと区別する。

所有機能は活動中断・終了時に必要なclose/abortを実施する。機能停止時は残存資源を回収する。受信処理が正常終端前に関数から戻れば所有終了による打切りになる。

## 遠隔活動と履歴

`group.enable_activities(clock_check_interval=..., max_running=...)`でHybridTaskManagerを付ける。ローカルの既存`submit`を維持し、`submit_remote(request, module_id, executor_id, arguments)`を追加する。機能側からはCoreClientの同名入口を使う。

CoreClientの`activity(operation, key, **arguments)`はsnapshot / change / pause / resume / finish / wait / command / notice / historyを提供する。変更・中断再開には既存の命令IDと期待revisionを指定する。自身の要求元IDの活動だけを対象とする。値や優先順位をCoreが生成することはない。

遠隔開始はSTARTINGを経て実開始報告でRUNNINGになる。中断は実行側の`checkpoint()`、再開は同じ継続処理への適用報告で確定する。再開許可が既に送られている時の再中断はPAUSINGとして次の安全な区切りを待ち、途中で実行枠を解放しない。実行側Contextには初回と現在の要求、予定時刻、終了・中断要求、`wait_for_control`・`wait_for_finish`・`checkpoint`がある。

予定到達は通知して継続しNymphの指示を待つ。終了要求は安全な区切りと後処理を待つ。活動期間を通信タイムアウトとして使用しない。経過・実行秒は子の単調時計による最新の報告値で、管理応答待ちを実行秒に足さない。`timing_confirmed`と`cleanup_confirmed`で確認範囲を表す。子消失時に実終了時刻・正常結果・後処理完了を作らず、実行枠は終了報告または子の終了確認後に解放する。

FileStoreが`hybrid_configuration`・`hybrid_process`・`hybrid_stream`、遠隔活動の`activity_v07_*`を保存する。ストリームは開設・終端状態・理由・破棄件数を記録し、本文を一律保存しない。旧v0.5/v0.6の活動履歴も読める。子で発生したが管理へ届かなかった情報は消失時に不明と記録し、Coreが受付済みの未保存履歴と区別する。通常の履歴バッファは引き続き上限なし。

`group.process(id)`でPID・起動世代・終了理由・後処理確認を、`await group.diagnostics(id)`で通信待ち・実行中操作・転送量を照会できる。FileStoreの未保存件数も従来どおり観測する。再起動では接続設定を検証し、活動履歴をNymphへ渡す。PID・ソケット・ストリーム途中データ・活動継続は復元しない。

## 停止と制約

runの正常復帰だけでは子を終了せず、stopまで提供窓口を保持する。未処理run例外・予期しない子終了はRuntimeの致命的障害。Core停止では活動と子の後処理を進め、設定期限後にCore所有の子だけを強制終了できる。後処理未確認を成功へ置き換えない。同一プロセス機能には従来どおり協調的終了が必要。

親管理接続を失った子も自分の後処理を行う。ただし親消失後の非協調的な子を必ず回収できる保証はない。敵対的な機能を遮断するセキュリティ境界ではない。後続のv0.8で行った統合・障害・負荷検証は[v0.8記録](validation/v0.8.md)、v0.9の完成確認は[v0.9記録](validation/v0.9.md)を参照する。長時間測定の対象コミット・環境と後続修正の検証範囲を区別する。本番Subsystem/Adapterは後続の開発対象である。
