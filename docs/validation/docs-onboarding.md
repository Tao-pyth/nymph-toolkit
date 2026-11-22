# v0.9.0利用者向けDocsの検証記録

## 対象と判定の分け方

R26によるD01〜D04・D09の文書整備。親[#90](https://github.com/Tao-pyth/nymph-toolkit/issues/90)、文書[#91](https://github.com/Tao-pyth/nymph-toolkit/issues/91)、生成・検証[#92](https://github.com/Tao-pyth/nymph-toolkit/issues/92)をv1.0.0マイルストーンに登録し、生成ツール変更前に実際の親子関係と同じマイルストーンを確認した。作業基点は公開v0.9.0の`22d931982b9d9e3843025516d5f50047d10a7ff1`。

説明対象はv0.9.0で、今回の作業を製品の新規リリースやv1.0の接続契約採用と扱わない。製品コード・実行例・公開API・採用64項目・配布版を変更しない。新しい利用ガイドは公開後の文書改善であり、既存Releaseの添付Docs・引継ぎ書を差し替えない。A09-04自体の完了は[公開時の結果](https://github.com/Tao-pyth/nymph-toolkit/issues/88#issuecomment-7067230161)を参照する。

## 要件と確認先

| ID | 今回の成果 | 確認 |
|---|---|---|
| D01 | [README](../../README.md)・[Docs索引](../README.md)を目的別に整理。現行機能・将来ビジョン・過去記録を区別 | 公開済みv0.9.0と各版の履歴、通常導入と開発導入の入口を目視照合 |
| D02 | [getting-started](../getting-started.md)に版固定のwheel＋sdist取得、checksum、venv、版とimport元、初回実行 | 新しいWindows環境で掲載コマンドを実行 |
| D03 | [tutorials](../tutorials.md)に6例の前提・目的・期待出力・終了・保存物 | 公開sdistの例を変更せず、公開wheelで実行して出力を照合 |
| D04 | [troubleshooting](../troubleshooting.md)に導入・子起動・期限・活動・保存の確認と対応 | 既存Core API、機能Docs、実行例と契約を照合。全症状を新たに故障注入した結果ではない |
| D09 | 3ガイドと本検証記録を引継ぎ書へ全文収録 | 生成一致・ローカルリンク・形式・LICENSE・API・64項目の確認と再生成一致を検査 |

## Windowsの手順再現

2026年11月22日、WindowsのPC NYMPH、CPython 3.15.2・pip 26.3で確認した。Python 3.12以上が既に使えるというガイドの前提に合わせて、検証用PowerShellでは対応PythonのあるディレクトリをそのプロセスのPATH先頭へ指定した。システムの既存Pythonや設定を変更していない。

`getting-started.md`のPowerShellコードブロック4つと`tutorials.md`のPowerShellコードブロックを抽出し、順に実行した。作業先はGit管理外の`.git/docs-onboarding-check/ntk-v0.9.0`。新規venvに公開wheelを`--no-index --no-deps`で通常導入し、例は新たに取得した公開sdistから展開した。ローカルの作業ツリーや過去の実行用フォルダから例をコピーしていない。

| 確認 | 結果 |
|---|---|
| Releaseからの匿名取得 | wheel・sdist・SHA256SUMSを取得。ガイドの2件照合が成功 |
| wheel SHA256 | `84a241cc9d8c5d8696207d79405ffb522b0566721304ae0ad5f700d84bfdd81b` |
| sdist SHA256 | `10410a4e6c3506bf6e04eb42050fb40e445766408948143562a6280e72a0ff36` |
| インストール情報 | versionは0.9.0、import元は新規venvの`Lib/site-packages/nymph_toolkit/core/__init__.py` |
| 最初のRuntime例 | stopped、dummy-result、start/run/stop、remaining_tasks=0 |
| 6例の一括実行 | 全て終了コード0。掲載したPASS・状態・停止出力と一致 |
| Connections | 直接／Core経由呼出し、保存済み接続の再利用、残存タスク0 |
| 活動基本・変更 | 予定到達後の継続、Nymphの明示終了、保持した処理からの再開、再起動後の自動活動復元なし、残存タスク・未保存履歴0 |
| Hybrid | 直接RPC、stream、予定通知、Nymphの終了指示、子の終了コード0と後処理確認、残存タスク0 |
| 出力保存 | 6件の`logs/*.log`を確認。例の通常終了後もログは残る |

件数・PID・時間など変動する値はガイドの合格固定値にしない。活動履歴の今回の件数は参考として5件・23件だったが、ガイドでは2回目に履歴があることを確認点とした。

## 文書同期と照合

リポジトリの開発用Pythonで、以下を実行する。

```powershell
.venv/Scripts/python.exe tools/build_handoff.py
.venv/Scripts/python.exe tools/build_handoff.py --check
.venv/Scripts/python.exe tools/check_docs.py
.venv/Scripts/python.exe tools/check_api.py
.venv/Scripts/python.exe tools/check_completion.py
git diff --check
```

照合結果と最終コミット・CIは子Issue #92へ記録する。生成後に再生成し、引継ぎ書のハッシュが同じであることも確認する。生成API一覧・証拠対応表を説明文へ合わせて書き換える方法は使わない。

2026年11月22日のローカル照合結果：

| 検査 | 結果 |
|---|---|
| 引継ぎ書 | 59収録元と完全一致。新規3ガイドと本記録を各1回、全文収録。再生成はバイト単位で一致 |
| Docs | 59 Markdown、1,066ローカルリンク、UTF-8/LF、LICENSEが成功 |
| API | Core 14件＋Contracts 92件が生成一覧と一致 |
| 採用・証拠 | 64項目、7既存受入群、293の実在テスト参照が一致。参照検査とテスト実行は区別 |
| 保全 | 公開v0.9.0に対しsrc・tests・examples・pyproject・生成API・採用証拠・ADRの差分なし |
| ログ | 6件にTraceback・未回収例外・残存タスク警告・ResourceWarningなし |
| 差分形式 | `git diff --check`成功 |

## 確認範囲と残課題

- 今回のローカルでの手順再現はWindows / CPython 3.15.2。Linux/Bash版はコマンドと既存CIの導入・実行方式を照合したが、この作業環境にLinuxがないため、掲載した取得からの一連のコマンドはLinux上で再実行していない。
- v0.9.0公開時のWindows/Linux × CPython 3.12〜3.15の8環境・通常wheel各300テスト・6例と、今回の新しいガイドの手順確認を区別する。今回のコミットに対するCI結果は#92で追跡する。
- `check_docs.py`はローカルリンク・明示アンカー・文字コード・LF・末尾空白・コードフェンス数・LICENSE・引継ぎ書一致を検査する。外部URL全件の到達性、画面表示、各トラブル症状の再現試験は含まない。
- 6例の成功を長時間負荷・実環境運用・本番Nymphの完成とは扱わない。D05〜D08の全面整備、常駐起動・GUI・サービス化は後続の範囲である。
