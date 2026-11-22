# v1.1.0のトラブルシューティング

対象は、[通常導入](getting-started.md)・[実行例](tutorials.md)で問題が起きた人と、同版のCoreを呼び出す開発者。ここでは既存の契約に沿って原因を切り分ける。変更を伴う修正へ進む場合は[Issue運用](issue-workflow.md)に従う。

## 最初に記録する情報

PowerShellでは導入時の作業フォルダで次を実行する。LinuxではPythonのパスを`.venv/bin/python`へ置き換える。

```powershell
.\.venv\Scripts\python.exe -I -c "import sys, platform, importlib.metadata as m, nymph_toolkit.core as c; print(platform.platform()); print(sys.version); print(sys.executable); print(m.version('nymph-toolkit')); print(c.__file__)"
.\.venv\Scripts\python.exe -m pip show nymph-toolkit
```

実行したコマンド、終了コード、最初の例外から最後までのTraceback、`logs/`の該当出力を残す。import自体が失敗する場合は、`python --version`と`python -m pip --version`を仮想環境の実行ファイルで個別に確認する。

## 導入・実行例の問題

| 症状 | 確認 | 対処 | 回復の確認 |
|---|---|---|---|
| `Requires-Python`で拒否、構文やimportで失敗 | 実際に呼んだPythonが3.12以上か。OSの既存3.8等ではないか | 対応Pythonで新しいvenvを作り、wheelを導入する | 上の版・import元確認後、Runtime例を実行 |
| `venv` / `ensurepip` / `pip`がない | そのPythonの導入元とvenv構成 | 同じ版のPythonに対応するvenv/pipを公式・OSの手順で用意する | 仮想環境の`-m pip --version`が通る |
| ダウンロード失敗、SHA256不一致 | HTTPエラー、途中取得、ファイル名とRelease版、checksum一覧の2件 | 同じReleaseから対象と一覧を再取得し、一致を確認してから使う | wheelとsdistの両方が一致 |
| `No module named nymph_toolkit` | pipを実行したPythonと、例を実行したPythonのパス | 同じvenvの`python -m pip`でwheelを導入し、同じ実行ファイルで例を動かす | import元がvenvのsite-packagesになる |
| 版が1.1.0と違う、`src`からimportされる | `pip show`の版・Location・Editable project location、`sys.executable` | 通常導入の確認なら新しいvenvに公開wheelを入れる。開発環境ならメタデータ変更後に`pip install -e .`をやり直す | 版とimport元が選んだ導入方法に一致 |
| `examples/...`が見つからない | wheelだけを取得していないか、現在の作業フォルダ | 同版sdistを展開し、導入ガイドのパスで実行する | まずRuntime例が終了コード0 |
| `No module named hybrid_dummy` | `hybrid_demo.py`だけをコピーしていないか | 同版の`examples/`を一式使う。独自機能のfactoryは共有venvからimport可能にする | Hybrid例のPASSと子の終了確認 |
| `NotImplementedError`等で子が起動しない | Windowsのイベントループが子プロセスに対応するか、Notebook等で別ループを使っていないか | まず端末から同梱例の`asyncio.run`で実行する。独自ホストは対応ループを使う | Hybrid例が起動・通信・停止まで通る |
| 子の起動期限切れ、`RuntimeFailure` | 元の例外、子の標準エラー、factory名、Pythonパス、127.0.0.1の通信可否 | import・初期化・ローカル通信の原因を解消する。独自設定の期限は根拠を記録して調整する | `Runtime.wait/stop`で失敗・後処理を確認後、新しいRuntimeで試す |
| 実行後すぐ端末へ戻る | 出力がstopped/PASS、終了コード0、残存タスク0か | その場合は正常終了。常駐アプリとしての起動ではない | [次の例](tutorials.md)へ進む |
| PASSの後に未回収例外や警告が出る | 全ログにTraceback、`Task exception was never retrieved`等がないか | PASSだけで合格とせず、版・コマンド・ログを残して報告する | 同じ条件で異常出力なしに正常終了する |

子の起動に失敗した際、PC全体のPythonプロセスを一括終了したり、通信保護を一括解除したりする必要はない。対象のCore・子と元のエラーを特定する。

## 期限・接続・活動を混同しない

以下は独自の利用コードで確認する入口。6例に新しい機能を追加する指示ではない。型・戻り値の詳細は[Core API](core-api.md)と[ハイブリッド実行](hybrid.md)にある。

| 症状・結果 | 確認すること | 対応と再確認 |
|---|---|---|
| `TemporaryUnavailable` | 提供側の受付・容量。候補スナップショットは予約保証ではない | 次の要求を機能側が判断する。容量不足だけでヘルス申請・全体停止・自動再送にしない |
| `PreparationTimeoutError` | 接続の確認中、要求元の協調的中断、保存側の受付停止、指定した準備期限 | Connectionsの状態・通知を確認し、必要な後処理とヘルス確認後に新しい要求を行う。稼働中に提供先を差し替えない |
| `ConnectionConflictError` | 同じ要求元＋契約ID・版の既存接続先 | 同一起動内は確定先を使う。異なる先への切替を回復策として自動化しない |
| `OutcomeUnknown` | 送信開始後の期限切れ・取消で、処理の成否が未確定か。窓口と要求IDを保存したか | 対象のCoreClient/DirectLinkの`pending_requests`・`result(id)`で確認し、完了後`release(id)`する。不明を失敗確定として再送しない |
| ストリームの`send`成功後、処理結果がない | sendはローカル転送受付。closeは通信上の受信確認まで | 内容処理の完了は受信機能の契約で確認する。closeの期限切れだけなら排出は継続し、照会・再待機・明示abortを使い分ける |
| 予定終了時刻を過ぎても活動が続く | `PLANNED_END`通知と、Nymphからの終了指示の有無 | 正常な契約。Nymphが継続・変更・終了を決める。Coreが自動終了したと見なさない |
| 終了要求を出してもまだ動く | 終了受付、実行側の安全な区切り、後処理の完了を区別 | 活動の`wait`等で終端結果を確認する。通常の活動終了に子の強制終了期限を流用しない |
| Core再起動後に活動がない | 履歴と現在の活動は別。継続状態を自動復元しない | 履歴をNymphへ渡し、Nymphが必要な再登録・再開を決める |

通信期限、Connectionsの準備期限、活動期間、Coreの停止期限は別の値である。期限切れをすべて「処理が終了した」と解釈しない。同一プロセスで協調しない処理はCoreから強制終了できず、Core所有子の強制終了はCore停止時の契約に限る。

## 保存・履歴の問題

| 症状 | 確認と対処 | 回復の確認 |
|---|---|---|
| デモ終了後に履歴がない | FileStoreを使う例は一時フォルダを通常終了時に削除する。出力を残すにはガイドの`logs/`を使う | ログの未保存0・終了確認を読む。永続運用は独自のFileStore保存先を明示する |
| `StorageError` / `StorageFailure`、受付停止 | 主・予備保存先の空き容量、書込権限、同一主保存先を使う別Core、元の例外と未保存件数を確認する | Core内蔵の退避・再試行で回復したか、未保存報告を伴って終了したかを区別する |
| `StorageCorruptionError` | 原本を保全して破損箇所と発生条件を調べる。空設定に置換して成功扱いしない | 原因・保全データ・復旧判断を記録し、次回起動時の接続検証結果を確認する |
| `unsaved_events`やメモリ使用量が増える | 履歴生成と書込み速度、保存障害、保持中の活動・通知・RPC結果を分けて調べる | 保存が追い付くか、通常停止後に排出できるかを確認する。`batch_size`をバッファ上限と解釈しない |

保存失敗では新規受付停止→古い履歴の予備先への退避→保存再試行→回復または未保存報告と終了という既存の手順を使う。独自の履歴破棄・自動修復を追加しない。急なプロセス終了では未保存分が失われ得るため、正常停止の確認と区別する。詳細は[Connectionsの保存契約](connections.md)。

Memoryの`memory.invalid`・`memory.conflict`・`memory.storage`や容量不足は[Memoryの失敗一覧](memory.md)で確認する。SQLiteはCore履歴の救命手順の対象ではなく、保存先・権限・ロックと要求IDを分けて調べる。

## 解消しない場合の報告

Windowsで`_ProactorBasePipeTransport._call_connection_lost()`内の`shutdown`がWinError 10054になり、終了時の後処理が未確認になる事象は[#94](https://github.com/Tao-pyth/nymph-toolkit/issues/94)で追跡する。[原因と修正の検証](validation/windows-shutdown.md)では、ソケット解放が抜ける条件を制御再現した。修正はv1.0.0から含む。公開v0.9.0の配布物は変更していない。コールバックの警告を抑止するだけで終了成功とせず、子の終了コード・後処理確認・残存接続を確認する。

[GitHub Issues](https://github.com/Tao-pyth/nymph-toolkit/issues)に、次を記載する。新規実装や修正の着手は[参加方針](../CONTRIBUTING.md)に従う。

- NTKの版・取得したRelease、OS・Python版、実行ファイルとimport元、通常導入かeditableか。
- 対象の例・再現コマンド、期待結果と実際の結果、終了コード。
- 関係するTraceback・状態・要求ID・子PID・未保存件数など、取得できた範囲。
- 発生頻度と最後に正常だった条件。共有できるダミーで再現する手順。

公開ログには認証情報や他者の非公開データを含めず、必要ならパス等を伏せる。今回のガイドの検証範囲は[文書整備の記録](validation/docs-onboarding.md)を参照する。

## v1.2開発候補のDocument取込

公開v1.1のwheelではDocumentをimportできない。開発checkoutのeditable導入と版/import元を確認する。`document.too_large`は本文だけでなく出典URI/hash等を含む4096 JSON bytes制限の場合もある。切捨て・部分保存は行わない。kind/source_kind/時刻・IDは要求元が指定し、再取込で変えるとmemory.conflictになる。失敗/取消/結果不明の判断とMemory照合、接続中断後の再prepareは[Document利用ガイド](document.md)を参照する。
