# WindowsのTCP終了処理の修正・検証（#94）

対象は[R28の修正課題 #94](https://github.com/Tao-pyth/nymph-toolkit/issues/94)。親#10・v1.0.0マイルストーンへの所属とGitHubの親子関係を確認し、コード変更前に範囲・完了条件・検証方法を追記した。起点は`bf57b3251d4afb562dac481cc79beb747d33187a`。未リリースの内部修正であり、公開v0.9.0のタグ・Release添付・版番号を変更しない。

## 観測と原因の確認範囲

初回はPR #93の`d84bb303feb1620a08517595eff827ac2a018f36`、[Windows／Python 3.15のCIログ](https://github.com/Tao-pyth/nymph-toolkit/actions/runs/44977471181/job/137070475736)で観測した。製品コードは公開v0.9.0と同じだった。`test_four_placements_direct_calls_and_streams`のPROCESS/PROCESSで次の順に発生した。

1. `02:45:04.869 UTC`：`_ProactorBasePipeTransport._call_connection_lost()`内の`socket.shutdown(SHUT_RDWR)`がWinError 10054を送出。
2. 約3秒後：providerの`cleanup_confirmed=False`、終了コード1、`Cleanup not confirmed: [WinError 64] ...`で失敗。

手元のWindows／CPython 3.15.2でも、同じ終了コールバックに`shutdown`のConnectionErrorを扱う処理がないことを確認した。この例外が起きると後続のsocket.close、serverからのtransport登録解除、終了済みフラグ更新へ到達せず、`Server.wait_closed()`が残る。上流の[CPython #160429](https://github.com/python/cpython/issues/160429)と[修正 #160909](https://github.com/python/cpython/pull/160909)にも同じ欠陥と解放処理の修正が記録されている。

**確定したのは、観測された終了エラーによって解放が抜ける原因と、その条件への対処である。** 初回NTK CIでTCPリセットが発生したパケット順・タイミングは未確定。初回ログだけでは対象ソケットも特定できない。修正前の通常4配置試験50回はすべて成功し、標準エラーも空だった。自然発生を再現したとは扱わず、以下の制御されたエラー注入と区別する。Python 3.15だけの不具合とも断定しない。

## 内部修正の判断

[コード変更前の判断記録](https://github.com/Tao-pyth/nymph-toolkit/issues/94#issuecomment-7080713996)に沿い、[内部TCP窓口](../../src/nymph_toolkit/core/_net.py)へ互換処理を隔離した。管理接続の親・子と、直接RPC・ストリームの接続側・受信側をすべてこの窓口へ通す。接続確立時に設定するため、初期ハンドシェイク失敗時も対象になる。

- Windows ProactorのNTK所有TCP transportだけに適用する。asyncioのクラス、アプリケーションの例外ハンドラ、イベントループ方針は変更しない。
- 同期的な終了コールバックの間だけソケットを委譲オブジェクトで包み、`shutdown`のConnectionErrorだけを扱う。socket.close、protocol通知、server登録解除などは元のCPythonコールバックへ委譲する。
- 読書き中の切断、停止フックの失敗、想定外のOSError、プロトコル例外を成功へ読み替えない。期限・強制終了・後処理未確認の判定は変更しない。
- 通常のデータ転送経路、公開API、通信契約、採用64項目、NymphとCoreの責務境界は維持する。新しい仕様採用のADRは作成しない。

`_ProactorSocketTransport`、`_sock`、`_call_connection_lost`というCPython内部への依存は残る。対応Python更新時は本回帰試験で確認する。上流修正を含む実装でも元の後処理に委譲できる構成とし、将来すべての対応環境で不要になった際は互換処理の削除を検討する。

## 再現と回帰

| 検証 | 修正前 | 修正後の条件 |
|---|---|---|
| 実TCPの接続側・受信側でshutdownに10054を注入 | コールバック例外、実ソケットが開いたまま、終了フラグ未設定、server終了待ちが期限切れ | コールバック例外なし、実ソケットfileno=-1、transport解放、server終了待ち完了 |
| protocol例外とshutdownのresetを同時注入 | resetがprotocol例外を覆い、解放も抜ける | 元のprotocol例外を通知し、ソケットを解放 |
| shutdownの想定外OSError | 例外を通知 | 通知を維持。試験側で残ったソケットを回収 |
| 読込み中のConnectionResetError | 通信失敗 | readerとwait_closedへ失敗を伝播。成功扱いしない |
| 所有子2つで直接RPC・ストリームを双方向実行し終了時resetを注入 | 子のコールバック例外・回帰試験失敗 | 子のstderrが空、両子の終了コード0、後処理確認済み、管理タスク回収 |
| NTKと同じループの通常asyncio接続 | 標準の処理 | クラス・通常接続のコールバック・ループ例外ハンドラが変更されない |

再現用ダミーのsocket差替えは試験用の所有子プロセスだけで行う。製品コードがグローバルなsocket/asyncio差替えを行うわけではない。単体回帰の修正前試験では、失敗を記録した後に試験自身が残ったソケットを回収する。回収によって合格にはしない。

```powershell
python -W error -m unittest tests.core.test_windows_shutdown tests.core.test_hybrid_group -v
python -W error -m unittest discover -s tests -t . -v
python tools/check_completion.py
python tools/build_handoff.py
python tools/check_docs.py
python tools/check_api.py
python -m build
python tools/check_dist.py
```

試験の実体は[Windows終了回帰](../../tests/core/test_windows_shutdown.py)、[ハイブリッド統合](../../tests/core/test_hybrid_group.py)、[子プロセス用注入ダミー](../../tests/doubles/windows_shutdown.py)。Windows専用6件はLinuxでskipとし、実行成功数と区別する。既存の異常切断、stop例外、所有子の強制終了・後処理未確認も全回帰で確認する。

## 結果と残る範囲

手元Windows／CPython 3.15.2で、新規6件の修正後成功と修正前の失敗を確認した。全306件の回帰は81.450秒で成功し、公開API一覧14＋92件、採用64項目・7群・299件の証拠参照、63文書の引継ぎ書同期とリンク検査も成功した。通常導入、4配置反復、Windows/Linux × Python 3.12〜3.15のCI結果は最終検証後に本節と#94へ追記する。

公開済みv0.9.0に本修正が含まれるとは扱わない。自然発生の初回TCPリセットの詳細、他のCPython内部実装・独自イベントループすべての保証、30分負荷の再測定は今回の確認結果に含めない。
