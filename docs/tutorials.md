# v1.1.0の8つの実行例ガイド

対象は、[インストール手順](getting-started.md)を終え、NTK Coreの動きを確認したい人。使うのは公開v1.1.0と同版sdistの`examples/`で、Core用のダミー例に加え、8番目では実装した最小Memoryを要求側ダミーと接続する。Agencyなどの本番機能や会話相手としてのNymphは含まない。

## 共通の前提と実行方法

作業場所は導入手順で作った`ntk-v1.1.0`。`.venv`へwheelを通常インストール済みで、`nymph_toolkit-1.1.0/examples/`を展開していることを前提とする。外部サービスの認証やデータは不要。ハイブリッド例は同じPCのループバックTCPとCore所有の子プロセスを使う。

順に8例を実行し、標準出力と標準エラーを`logs/`へ保存する。失敗した例で止まり、原因を確認してから再実行する。既存の同名ログは上書きされるので、過去の結果を残す場合は先に別名で保管する。

PowerShell:

```powershell
New-Item -ItemType Directory -Path logs -Force | Out-Null
$demos = @('runtime', 'registry', 'connections', 'task_manager', 'activity_changes', 'hybrid', 'module_contract', 'memory')
foreach ($demo in $demos) {
    & .\.venv\Scripts\python.exe -I -W error ".\nymph_toolkit-1.1.0\examples\${demo}_demo.py" 2>&1 |
        Tee-Object -FilePath ".\logs\${demo}.log"
    if ($LASTEXITCODE -ne 0) { throw "Demo failed: $demo" }
}
```

Bash:

```bash
set -e
set -o pipefail
mkdir -p logs
for demo in runtime registry connections task_manager activity_changes hybrid module_contract memory; do
    .venv/bin/python -I -W error "nymph_toolkit-1.1.0/examples/${demo}_demo.py" 2>&1 |
        tee "logs/${demo}.log"
done
```

1例だけ動かす場合は、上のPythonに対象の`examples/<名前>_demo.py`を渡す。開発用cloneでは`.venv`に開発版を入れ、スクリプトのパスを`examples/<名前>_demo.py`へ置き換える。検証対象の版とimport元を先に確認する。

## 1. Runtime：起動から後処理まで

ソース：[runtime_demo.py](../examples/runtime_demo.py)。前提は共通の導入だけ。

`DummyService`が`start`→`run`→`stop`を実行し、`Runtime.wait()`が返した値と停止状態を照合する。

```text
"state": "stopped"
"result": "dummy-result"
"events": ["start", "run", "stop"]
"remaining_tasks": 0
```

実際には1行のJSONで出力する。終了コード0で戻れば、この例の後処理と残存タスク0を確認できる。ファイル保存はしない。契約の詳細は[Runtime](runtime.md)を参照する。

## 2. Registry：登録依存とライフサイクル

ソース：[registry_demo.py](../examples/registry_demo.py)。前提は共通の導入だけ。

ダミー`document`が`memory`に依存する。依存不足から充足への変化を確認し、依存先から起動、逆順に停止する。停止後に登録を解除し、依存不足を観測して全登録を取り除く。

```text
registry and dependency changes: PASS
state: stopped remaining tasks: 0
```

間に表示される`module lifecycle`のstart順はmemory→document、stop順はdocument→memory。`results`に両者の`:done`がある。実行中の実体着脱や、依存先を外しても全機能が動き続けることを示す例ではない。ファイル保存はしない。詳細は[RegistryとModuleGroup](registry.md)。

## 3. Connections：選定・直接通信・保存済み接続

ソース：[connections_demo.py](../examples/connections_demo.py)。一時フォルダへの書込みが必要。

要求側が契約、言語属性、稼働・受付状況を見て提供先を選ぶ。同じ許可済み接続で同期／非同期の直接呼出しとCore経由呼出しを確認する。同じ一時保存先でCoreを2回起動し、2回目は検証された保存済み接続を再利用する。

```text
requester selection, direct/sync/async and mediated calls: PASS
persisted binding reused after restart, fresh module state: PASS
history drained, remaining tasks: 0
```

内部では未保存履歴0、起動IDが2つ、接続の初回保存が1回であることも照合する。停止・再起動の区切りを持つ接続再利用であり、失敗操作の自動再送ではない。詳細は[Connections](connections.md)。

## 4. TaskManager：予定到達の通知とNymphによる終了

ソース：[task_manager_demo.py](../examples/task_manager_demo.py)。一時フォルダへの書込みが必要。

Nymph役ダミーが調査を登録する。予定時間の到達後も活動が続くことを確認し、ダミーが終了要求を出す。Coreは実行側の安全な区切りと後処理を待つ。2回目のCore起動で履歴を読み、ダミーが新たな活動を登録する。

```text
run 1: previous activity records=0, active activities=0
run 1: planned time reached; activity continues (running)
run 1: Nymph requested finish; cleanup completed (stopped)
run 1: remaining tasks=0, unsaved history=0
```

run 2では過去履歴の件数が正になり、登録前の活動は0。その後も同じ通知・終了確認が続く。履歴件数を固定値と見なさない。Coreによる活動の価値判断、予定到達での自動終了、再起動後の自動活動復元は行わない。詳細は[活動管理](task-manager.md)。

## 5. 活動変更：予定・優先度・中断と再開

ソース：[activity_changes_demo.py](../examples/activity_changes_demo.py)。一時フォルダへの書込みが必要。

Nymph役ダミーが未開始の活動を即時開始へ変更し、優先度を指定する。中断中に期間を短縮して予定到達を通知させ、次に延長する。例では実行枠を1に設定し、別活動が枠を使う間は再開を待機させる。枠が空くと保持した同じ処理の続きから再開し、終了要求で後処理する。

```text
run 1: shortened deadline notified while paused; Nymph extended the plan
run 1: resumed once from retained position, cleanup complete
run 1: remaining tasks=0, unsaved history=0
```

run 1の`previous evidence`は0、run 2では正。両回とも`restored activities=0`を確認する。内部では実行関数の起動が1回、元の要求と変更後の要求が別に保持されることも照合する。優先度による自動中断や、Core再起動を越えた継続状態の復元は示していない。詳細は[活動変更の契約](task-manager.md)と[ADR 0021](adr/0021-v0.6-activity-changes.md)。

## 6. ハイブリッド：Core所有の子・RPC・ストリーム・活動

ソース：[hybrid_demo.py](../examples/hybrid_demo.py)、同じフォルダの[hybrid_dummy.py](../examples/hybrid_dummy.py)。2ファイルを一緒に置き、子プロセス起動とループバックTCPを利用できる環境で実行する。

親のLOCAL配置にNymph役、PROCESS配置にworkerを置く。直接RPCの結果のPIDが親と異なること、バイト列の送受信、遠隔活動の予定到達後の継続と明示終了を照合する。最後に通信窓口を閉じてCoreを止め、子の終了コード0・後処理確認済み・残存タスク0を確認する。

```text
PASS: direct RPC, stream, period notification, Nymph finish, child cleanup; remaining tasks=0
```

例はダミーのimport用に`examples/`を親・子へ渡す処理を含む。通常の機能はCoreと同じPython環境へインストールする。例の`PYTHONPATH`調整を製品共通の配置要件にはしない。詳細は[ハイブリッド実行](hybrid.md)。

## 7. 接続契約：Contractsだけを参照する機能

ソース：[module_contract_demo.py](../examples/module_contract_demo.py)と[contract_dummy.py](../examples/contract_dummy.py)。同じフォルダに置く。起動側が事前検証・登録し、公開ContractsだけをimportするSubsystem/Adapterが直接/Core経由RPC、byte stream、予定時間通知後の継続、Nymphの終了指示と後処理を確認する。

```text
PASS: public Contracts, Subsystem/Adapter, direct/Core RPC, stream, Nymph activity, cleanup
```

前の行にrpc/stream/activity/registrationの結果を表示する。初期化後のprovide拒否も確認する。恒久保存や本番機能の実装例ではない。[6契約](module-contracts.md)と[移行手順](migration-v1.md)を参照する。

## 8. Memory：出典付き記録と再起動後の取得

ソース：[memory_demo.py](../examples/memory_demo.py)と[memory_requester.py](../examples/memory_requester.py)。MemoryをPROCESS、要求側ダミーをLOCALへ配置し、Coreが許可した直接通信とCore経由でput/get/queryを実行する。経験/知識・出典の保存、同一IDの冪等・競合・未発見/不正入力、8件ページを確認する。同じ保存先で2回起動し、同じID・sequence・保存時刻が返ることを照合する。

```text
{'restored': False, 'routes': 'direct+core', 'page_count': 8}
{'restored': True, 'routes': 'direct+core', 'page_count': 8}
PASS: Memory persistence, provenance, direct/Core RPC, restart, cleanup
```

Core履歴とMemoryのSQLiteを別の場所へ保存し、子の後処理と終了を確認する。例は一時ディレクトリを削除して終了するため、次のスクリプト実行へ記憶を保持する例ではない。保持する実利用では専用の絶対パスを指定する。[Memoryの契約・設定](memory.md)を参照する。記憶統合・忘却・学習は実装していない。

## 保存物と確認の限界

| 対象 | この例での扱い |
|---|---|
| Runtime・Registry | FileStoreの履歴を作らない |
| Connections・TaskManager・活動変更・Hybrid・接続契約 | OSの一時フォルダにFileStoreを作る。通常終了時に例がフォルダを削除する |
| Connections等の2回起動 | 1回のスクリプト実行内で同じ一時保存先を使う。次回スクリプト実行は新しい一時保存先になる |
| Memory | 同じ一時保存先で2回起動。専用SQLiteとCore履歴を別保存し、通常終了時に削除 |
| `logs/*.log` | 上のコマンドで保存した出力。例の終了後も作業フォルダに残る |
| 恒久保存先 | ライブラリ利用者がFileStore構築時に指定する。主・予備を分け、同じ主保存先を複数Coreで同時使用しない |

保持日数、バッチ件数、通知間隔、通信期限、実行枠、転送量などの例中の値はデモ用であり、ライブラリの既定値や性能保証ではない。ファイル保存の詳細は[Connectionsの保存契約](connections.md)を参照する。

全例が終了コード0で期待結果を示せば、導入と基本経路の確認は完了。未回収例外やTracebackが出た場合は、最後のPASSだけで成功と判断せず[トラブルシューティング](troubleshooting.md)へ進む。8例は障害・負荷を網羅するテストスイートの代替ではない。製品の受入範囲は[B01検証記録](validation/v1.1.md)と既存[B00](validation/v1.0.md)、本版の公開後再現は[#110](https://github.com/Tao-pyth/nymph-toolkit/issues/110)で追跡する。過去のv0.9版ガイドの確認範囲は[文書整備の検証記録](validation/docs-onboarding.md)に残す。
