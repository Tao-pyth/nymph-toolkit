# v1.3候補までの実装機能と資料の整合点検

2026年11月23日の「ここまでの実装機能の内容で最新化されているか点検」という依頼に対応する。親#13・v1.3.0の子[#122](https://github.com/Tao-pyth/nymph-toolkit/issues/122)へ、引継ぎ書生成ヘッダーの変更前に範囲・完了条件・検証方法を追記した。新しい製品仕様を採用する作業ではない。

## 基点と確認範囲

点検開始時のブランチは`codex/v1.3-cognition`、コミットは`57bb26382710ddbac5a36318fecbe8b72155ee34`。GitHubのmainは公開v1.2.0の`1bc2173`、[PR #123](https://github.com/Tao-pyth/nymph-toolkit/pull/123)は未マージ、親#13とマイルストーンはopenである。公開済みの[v1.2.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.2.0)と4添付の存在、公開後確認の[#117](https://github.com/Tao-pyth/nymph-toolkit/issues/117)の完了を確認した。今回、添付の再ダウンロードによる公開後試験は行っていない。

| 機能・境界 | 実装との照合先 | 判定 |
|---|---|---|
| Core・共通接続契約 | core-api、module-contracts、api-reference、v1基準、64項目の証拠対応 | 公開名Core 15件・Contracts 98件、基準・参照が一致 |
| Memory | contracts/memory.py、subsystems/memory/、ADR 0027、memory.md | records/1のput/get/query、4096 JSON bytes、出典区分、保存/再起動の範囲が一致 |
| Document | contracts/document.py、adapters/document/、ADR 0028、document.md | import/1のingest、UTF-8 txt/md・65536 bytes、1記録保存、Memory制限と失敗/取消の範囲が一致 |
| Cognition | contracts/cognition.py、subsystems/cognition/、関連単体/統合試験、ADR 0029、cognition.md | learning/1のlearn/inspect、注釈入力、256例・上位8件・根拠ページ、冪等/競合が一致。障害説明を下記のとおり補正 |
| 実行・配布 | pyproject.toml、CI、check_dist、10個のdemo、開発手順 | 公開1.2.0と候補1.3.0を区別。版・実行例の説明を補正 |
| 判断履歴 | ADR索引・0029、R35根拠、Issue/PR、引継ぎ書ヘッダー | 初期入力方式のユーザー採用と詳細実装判断を分離。ヘッダーの更新漏れを補正 |

## 見つけた更新漏れと対応

1. **導入手順の根拠が旧版を参照**：v1.2.0の末尾がR32・#110・B01を指していた。R34・#117・B02へ訂正した。
2. **構成資料の現状が古い**：Memoryを今後追加する記述、実装済みConnections/時計を未実装・着手前とする判断表、v1.1/8例のフォルダ注釈、Memory以降の例と検証資料の掲載漏れを更新した。
3. **Docsへの入口が不足**：Document/B02、共通接続契約・移行・B00の索引を補い、READMEにCore/Memory/Document/Cognitionの機能・操作・公開状態を一覧化した。
4. **開発手順に旧版の件数が混在**：冒頭を公開v1.2/候補v1.3へ更新し、10例と現行検査を記載した。v0.9の14＋92件・6例は当時のcheckoutの手順として区別した。
5. **採用済み回答の同期不足**：ADR本文・Docsには入力方式のユーザー採用が反映されていたが、生成ツールの固定ヘッダーは一律に実装判断と記述していた。初期入力方式と詳細API・具体値を分離して再生成した。
6. **Cognitionの障害説明が広すぎた**：LinkFailureの中断IDを使う完了報告と、OutcomeUnknown等でIDのない例外経路を分けた。停止中にhealthを申請しない点も実装に合わせた。製品コードは変更していない。
7. **公開済みと候補・旧版資料の混同**：v1.2公開後の確認先と状態を明示し、v1.0共通接続契約が現在も維持されていることを補記した。旧v0.9の顧客図解を「現行の全機能」の資料として案内しないよう入口を修正した。
8. **CIの記録が進行中のまま**：補足回答コミット57bb263の[PR CI](https://github.com/Tao-pyth/nymph-toolkit/actions/runs/45129483891)・[push CI](https://github.com/Tao-pyth/nymph-toolkit/actions/runs/45129477830)が各8環境で成功したことを確認した。今回の点検コミットの結果とは分け、#122とPRに追記する。

## 検証と限界

点検開始時にcheck_docs（76文書・1316リンク・引継ぎ書）、check_api、check_contracts、check_completion（64項目・7群・299参照）が成功した。57bb263のCIでは、Windows/Linux × CPython 3.12〜3.15で既存の全378テスト、10例、通常wheel/sdist等を確認済み（LinuxのWindows専用6件skip）。

点検修正後は77文書・1344ローカルリンク・引継ぎ書の一致を確認した。Docs索引への掲載漏れはなく、実在する10個のdemoが開発手順・CI・通常配布検査に揃っている。Windows / CPython 3.15.2で既存のCognition障害3テスト（LinkFailure、結果不明と二次障害、Memory形式違反）が0.285秒で成功し、Memory・Document・Cognitionの3実行例もPASSで終了した。Core/API基準・64項目とgit diff --checkも確認する。今回のコミットと追加CIの結果は#122・PRへ記録し、このローカル再確認だけで全動作・長時間性能を再測定したと扱わない。

```text
python tools/check_api.py
python tools/check_contracts.py
python tools/check_completion.py
python tools/build_handoff.py
python tools/check_docs.py
git diff --check
```

製品ソース・契約・版・テスト・配布/CI設定は変更しない。生成ツールの変更は固定説明文のみ。ADRの過去判断、版別validationの当時の結果、公開済みタグ/Release添付は履歴として保持する。

顧客向けMarkdown/PDF/HTMLは**v0.9の既存版**であり、v1.0のAPI変更・Memory・Document・Cognitionを統合した最新版ではない。今回の点検で同資料を再発行・再描画していない。現在の説明はREADMEの機能表、architecture、module-contracts、各機能ガイドを参照する。統合した顧客資料の新版作成は残る文書課題である。

v1.3.0のレビュー・マージ・公開後確認は未完了。Cognitionの完全な言語理解、訂正/忘却/会話生成、Agency等の将来機能を実装済みにはしていない。採用判断・実装検証・公開完了を分けて追跡する。
