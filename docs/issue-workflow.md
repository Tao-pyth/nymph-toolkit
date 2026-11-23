# マイルストーンと親子Issueの運用

## 必須の順序

R10・[ADR 0013](adr/0013-milestone-issue-workflow.md)により、コード変更を伴う対応は、**バージョン別マイルストーン → 親Issue → 対応単位の子Issue登録 → 対応**の順で進める。

新規実装、不具合修正、リファクタリング、テストコード、実行・ビルド・配布に影響する設定の変更も対象とする。親Issueだけを作って実装を始めたり、実装後に子Issueを作成したりしない。文書のみの修正はこの必須条件の対象外だが、設計変更は従来どおり議論とADR記録を行う。

## 管理する単位

| 単位 | 記載・確認する内容 |
|---|---|
| マイルストーン | 対象バージョン、段階の目標、確定・提案の区別、関連ロードマップ・受入項目。期限は個別に合意しない限り設定しない |
| 親Issue | 機能・成果のまとまり、目的と範囲、採用済み事項と判断対象、関連Docs・ADR、完了条件、子Issue |
| 子Issue | 一つの対応単位、親Issue、対象マイルストーン、目的・変更範囲・完了条件・検証方法、先行課題と必要な判断 |

マイルストーンはリリース段階、親Issueは成果のまとまり、子Issueは実際の対応単位を表す。初回は既存ロードマップの各段階に一つの親Issueを設け、必要に応じて同じマイルストーンへ複数の親Issueを追加できる。

親子関係はGitHubのsub-issue機能で設定する。本文の参照だけで済ませず、子Issue自身にも対象マイルストーンを設定して確認する。先行する子Issueは本文で参照し、着手前に完了状況を確認する。[GitHubのsub-issue説明](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)

## 対応開始から完了まで

1. 既存のマイルストーン・親Issueを確認する。対象バージョンや機能が新しい場合は、先に目標と確定・提案の区別を記録して追加する。
2. 対応する子Issueを作成し、親子関係・マイルストーンと上表の項目を揃える。設計判断を先に行う必要があれば、その判断を別の子Issueに切り出せる。
3. 実装に必要な未決事項を判断し、関連Docs・ADRと子Issueへ結果を記録する。依存先の未完了や未決事項が実装を妨げる場合は、その範囲の実装を開始しない。
4. 子Issueの範囲で変更し、コミットまたはPRに子Issue番号を記載する。対応範囲が広がったら、追加範囲のコード変更前に子Issueを更新するか別の子Issueを登録する。
5. 子Issueへ変更コミットまたはPR、検証内容・結果、関連Docs・ADR、残課題を記録する。採用範囲の対応・検証・文書更新が完了してから閉じる。
6. 親Issueでは採用した子Issueの完了と受入結果を確認する。延期・不採用は理由と移管先を記録し、未実装を実装済みとして扱わない。
7. マイルストーンの目標・受入条件・リリース条件を確認して完了とする。Issueがすべて閉じたことだけで自動的にリリースしない。

通常の作業ブランチ名は、例えば `feat/24-runtime-lifecycle` のように子Issue番号を含めると追跡しやすい。ブランチ命名の例を製品仕様や必須の命名規約としては扱わない。

## 計画と仕様の区別

この運用ルールは採用済みである。v0.2はR11・ADR 0014、v0.3はR13・ADR 0016、v0.4はR16・ADR 0019で実施範囲を具体化した。v0.5はR17・ADR 0020で実施範囲を具体化した。後続の未決事項を実装要件へ含めない。v0.6はR18・ADR 0021で全4項目の範囲と詳細契約を設計採用した。製品コードを実装した。最終A06・公開は[検証記録](validation/v0.6.md)で追跡する。v0.7〜v0.8の配分は後続R19・ADR 0022で採用した。v1.1.0〜v1.10.0の機能配分、Subsystem・Adapterの名称や実装順序、契約詳細などは既存の提案状態を維持する。登録だけでは採用や着手の宣言にならない。計画を変更する場合は理由・依存関係・受入への影響を記録し、ロードマップ、Issue、関連ADRを整合させる。

v0.1.0＝GitHub公開、v0.9.0＝合意したCore機能の完成、v1.0.0＝CoreとSubsystem・Adapterの接続契約整備という確定目標と、NymphとCoreの責務分離を維持する。通信方針はR12・[ADR 0015](adr/0015-core-authorized-direct-communication.md)で更新し、Coreが管理・許可した直接通信を採用した。詳細な許可条件・APIなどは実装前に判断する。

## 登録したマイルストーンと親Issue

2026年11月20日に既存ロードマップを以下のように整理した。進捗の最新状態はGitHubを参照する。v0.1.0は公開結果を記録した完了済みの段階であり、新ルールを公開前に実施したという意味ではない。

| マイルストーン | 親Issue | 計画の位置付け |
|---|---|---|
| [v0.1.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/1) | [#1 GitHub公開](https://github.com/Tao-pyth/nymph-toolkit/issues/1) | 確定目標・公開済み |
| [v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/2) | [#2 Runtime](https://github.com/Tao-pyth/nymph-toolkit/issues/2) | R11・ADR 0014で実施範囲を具体化 |
| [v0.3.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/3) | [#3 Registry](https://github.com/Tao-pyth/nymph-toolkit/issues/3) | R13・ADR 0016で実施範囲を具体化 |
| [v0.4.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/4) | [#4 Connections](https://github.com/Tao-pyth/nymph-toolkit/issues/4) | R16・ADR 0019で実施範囲を具体化 |
| [v0.5.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/5) | [#5 TaskManager基本](https://github.com/Tao-pyth/nymph-toolkit/issues/5) | R17・ADR 0020で実施範囲を具体化 |
| [v0.6.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/6) | [#6 活動変更](https://github.com/Tao-pyth/nymph-toolkit/issues/6) | R18・ADR 0021に従い実装。受入・公開を別途確認 |
| [v0.7.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/7) | [#7 ハイブリッド実行](https://github.com/Tao-pyth/nymph-toolkit/issues/7) | R19・ADR 0022で設計採用。R20・#61〜#68で実装・A07・配布を確認。R21でPR #69レビュー修正#70、マージ・公開#71を追跡 |
| [v0.8.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/8) | [#8 統合検証](https://github.com/Tao-pyth/nymph-toolkit/issues/8) | R22・ADR 0024で#72〜#78・#80を実施。PR #79・validation/v0.8で追跡。R23の公開#81を追加 |
| [v0.9.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/9) | [#9 Core機能完成](https://github.com/Tao-pyth/nymph-toolkit/issues/9) | R24・ADR 0025で完成監査、R25・#88/#89でレビュー修正・公開後照合まで完了。親#9・マイルストーンは終了済み |
| [v1.0.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/10) | [#10 Core接続契約](https://github.com/Tao-pyth/nymph-toolkit/issues/10)、[#90 利用者向けDocs整備](https://github.com/Tao-pyth/nymph-toolkit/issues/90) | R29・ADR 0026で実装、R30・#104で公開後確認・終了済み。#90はv0.9利用ガイド |
| [v1.1.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/11) | [#11 Memory Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/11) | R31・ADR 0027で実装、R32・#110で公開後確認・終了済み |
| [v1.2.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/12) | [#12 Document Adapter](https://github.com/Tao-pyth/nymph-toolkit/issues/12) | R33・ADR 0028で初期範囲・B02を具体化。子#112〜#115・PR #116で実装受入を追跡。公開は別工程 |
| [v1.3.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/13) | [#13 Cognition Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/13) | 名称・機能配分・実装順序は提案 |
| [v1.4.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/14) | [#14 Text Interaction / Web Adapter](https://github.com/Tao-pyth/nymph-toolkit/issues/14) | 名称・機能配分・実装順序は提案 |
| [v1.5.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/15) | [#15 Agency Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/15) | 名称・機能配分・実装順序は提案 |
| [v1.6.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/16) | [#16 TaskManager連携強化](https://github.com/Tao-pyth/nymph-toolkit/issues/16) | 名称・機能配分・実装順序は提案 |
| [v1.7.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/17) | [#17 Persona Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/17) | 名称・機能配分・実装順序は提案 |
| [v1.8.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/18) | [#18 Persona連携強化](https://github.com/Tao-pyth/nymph-toolkit/issues/18) | 名称・機能配分・実装順序は提案 |
| [v1.9.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/19) | [#19 Sleep Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/19) | 名称・機能配分・実装順序は提案 |
| [v1.10.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/20) | [#20 Sleep連携・Discord Voice Adapter](https://github.com/Tao-pyth/nymph-toolkit/issues/20) | 名称・機能配分・実装順序は提案 |

[マイルストーン一覧](https://github.com/Tao-pyth/nymph-toolkit/milestones)と[Issue一覧](https://github.com/Tao-pyth/nymph-toolkit/issues)からも参照できる。将来段階の子Issueは対応単位が具体化した時点で追加し、各コード変更の開始前に登録する。

## v0.6の設計判断

以下はv0.6時点の記録である。v0.7以降の後続判断は本書のR19節を参照する。

R18により、開始時刻変更・期間変更・優先度・中断再開の全4項目を対象として採用した。親Issue [#6](https://github.com/Tao-pyth/nymph-toolkit/issues/6)・マイルストーンv0.6.0配下へ、設計子Issue [#52](https://github.com/Tao-pyth/nymph-toolkit/issues/52)を登録し、GitHubの親子関係と同一マイルストーンを確認した。

#52はADR 0021、関連Docs、引継ぎ書と生成ヘッダーの同期、詳細契約・A06の設計判断を扱う。生成ヘッダーを更新する前に登録した。個別回答と残事項の判断委任を受け、振る舞い・API・A06-01〜12・実装単位を設計採用した。判断元はADR 0021 D1・D2とD3〜D10へ分ける。後続の子Issue分割はD10に記録し、製品コード変更前に各Issueを登録する。#52の設計完了を親#6・v0.6の実装完了と扱わない。

## R25：v0.9.0のレビュー・公開

公開子Issue [#88](https://github.com/Tao-pyth/nymph-toolkit/issues/88)を親#9・v0.9.0へ登録してから、公開状態の資料と生成ヘッダーを更新する。レビューで再現した停止競合は、製品・テスト変更前に追加した[#89](https://github.com/Tao-pyth/nymph-toolkit/issues/89)で修正する。PR #86のClosesは実装子Issueと#89に適用し、公開#88はマージだけで閉じない。マージコミットのCI・タグ・4添付の匿名取得・通常配布再現によるA09-04合格を記録してから、#88・親#9・マイルストーンを完了する。

## R24：v0.9の完成確認

CIで検出した通常終了試験の停止期限は、変更前に追加子[#87](https://github.com/Tao-pyth/nymph-toolkit/issues/87)を親#9・マイルストーンv0.9.0へ登録して扱う。正常終了と強制終了の検証条件を分け、採用した製品契約を維持する。

親#9・v0.9.0の子Issueをコード変更前に登録し、GitHubの親子関係と同じマイルストーンを確認した。

| 子Issue | 対応単位 |
|---|---|
| [#82](https://github.com/Tao-pyth/nymph-toolkit/issues/82) | 完成判定・64項目と既存受入の証拠・ADR 0025 |
| [#83](https://github.com/Tao-pyth/nymph-toolkit/issues/83) | 公開API資料と生成一覧・整合検査 |
| [#84](https://github.com/Tao-pyth/nymph-toolkit/issues/84) | 全採用機能監査・ダミー再現・証拠検査の拒否試験 |
| [#85](https://github.com/Tao-pyth/nymph-toolkit/issues/85) | 配布候補0.9.0・全8環境CI・結果と引継ぎ書 |
| [#87](https://github.com/Tao-pyth/nymph-toolkit/issues/87) | 通常終了と強制終了の試験条件を分離・snapshot診断 |

A09-01〜03は全8環境の297テスト・通常配布・資料照合で合格した。変更と結果は[PR #86](https://github.com/Tao-pyth/nymph-toolkit/pull/86)、[validation/v0.9.md](validation/v0.9.md)で追跡し、子IssueはPRのマージ時に閉じる。A09-04の公開後確認は別工程であり、親#9・マイルストーンを公開前に閉じない。

## R23：v0.8.0のレビュー・公開

公開子Issue [#81](https://github.com/Tao-pyth/nymph-toolkit/issues/81)を親#8・v0.8.0配下へ先に登録し、生成ヘッダー変更前に親子関係を確認した。最終CI・通常配布・マージ・新しいタグ/Release・4添付・匿名取得を検証し、結果を#81へ記録してから閉じる。PR #79のClosesで閉じる実装子Issueとは区別し、公開課題#81をマージだけで閉じない。

## R22：v0.8の検証単位

親#8・マイルストーンv0.8.0に、コード変更前に以下の子Issueを登録しGitHubの親子関係を確認した。

| 子Issue | 対応単位 |
|---|---|
| [#72](https://github.com/Tao-pyth/nymph-toolkit/issues/72) | A08条件・ADR・根拠と文書同期 |
| [#73](https://github.com/Tao-pyth/nymph-toolkit/issues/73) | 4配置統合・ライフサイクル障害 |
| [#74](https://github.com/Tao-pyth/nymph-toolkit/issues/74) | 通信・ストリーム・活動変更の競合 |
| [#75](https://github.com/Tao-pyth/nymph-toolkit/issues/75) | 保存障害・最終通知・再起動 |
| [#76](https://github.com/Tao-pyth/nymph-toolkit/issues/76) | 性能・継続負荷・資源保持 |
| [#77](https://github.com/Tao-pyth/nymph-toolkit/issues/77) | A08受入・CI・配布・資料 |

不具合修正[#78](https://github.com/Tao-pyth/nymph-toolkit/issues/78)は管理通信の期限・取消後の結果解放を対象とし、製品コード変更前に追加登録した。送信前の期限・取消で枠が残る不具合も、製品修正前に[#80](https://github.com/Tao-pyth/nymph-toolkit/issues/80)を登録して対応する。変更全体は[PR #79](https://github.com/Tao-pyth/nymph-toolkit/pull/79)に紐付ける。

採用条件はADR 0022、具体的な検証条件はADR 0024、結果は[validation/v0.8.md](validation/v0.8.md)で管理する。公開済みのタグ・添付を変更せず、Release作成とは別にPRでレビューする。

## R21：v0.7のレビュー・公開

コード変更前に、[#70 レビュー修正](https://github.com/Tao-pyth/nymph-toolkit/issues/70)と[#71 マージ・公開・匿名取得](https://github.com/Tao-pyth/nymph-toolkit/issues/71)を親#7・マイルストーンv0.7.0のsub-issueとして登録した。#70は取消・完了報告の境界不具合と回帰検証、#71は生成ヘッダーを含む公開資料・最終CI・マージ・タグ・Release・配布物・匿名再現を扱う。#71の公開後確認が終わってから親#7・マイルストーンを閉じる。

## R20：v0.7の実装単位

資料コミットc3f0868をGitHub mainへ反映した。コード変更前に、親#7・マイルストーンv0.7.0の子Issue #61〜#68を登録し、GitHubの親子関係と同じマイルストーンを確認した。[ADR 0023](adr/0023-v0.7-implementation-contracts.md)に実装判断を先に記録する。

| 子Issue | 対応単位 |
|---|---|
| [#61](https://github.com/Tao-pyth/nymph-toolkit/issues/61) | 詳細設計と公開契約 |
| [#62](https://github.com/Tao-pyth/nymph-toolkit/issues/62) | Contracts・IPC符号化 |
| [#63](https://github.com/Tao-pyth/nymph-toolkit/issues/63) | 非同期RPC・ループバック通信 |
| [#64](https://github.com/Tao-pyth/nymph-toolkit/issues/64) | 連続ストリーム |
| [#65](https://github.com/Tao-pyth/nymph-toolkit/issues/65) | 子プロセス管理 |
| [#66](https://github.com/Tao-pyth/nymph-toolkit/issues/66) | Core統合・直接通信 |
| [#67](https://github.com/Tao-pyth/nymph-toolkit/issues/67) | 遠隔活動 |
| [#68](https://github.com/Tao-pyth/nymph-toolkit/issues/68) | A07・例・配布・CI・文書 |

R19でv0.7〜v0.9の配分を採用済みである。本書のR18以前の「提案」はその時点の履歴を示す。各子Issueの完了と親#7・マイルストーン全体の完了、公開を区別する。

## R19：v0.9までの設計採用と資料同期

2026年11月21日に[設計子Issue #60](https://github.com/Tao-pyth/nymph-toolkit/issues/60)を親#7のGitHub sub-issueとして登録し、親子のマイルストーンv0.7.0への所属を確認した。引継ぎ書生成ツールのヘッダー変更前に登録している。対象はADR 0022・根拠表・関連Docs・A07〜A09・引継ぎ書と生成ヘッダーであり、製品コード・API・版番号・新規リリースは含まない。

1〜18は個別回答、19〜64は一覧の推奨設定に対する明示一括採用である。親#7〜#9にも採用判断を記録する。設計の反映をv0.7〜v0.9の実装・受入・公開完了と扱わず、親Issueは開いたままとする。各製品実装は別の子Issueを登録し、ADR 0022の残る実装詳細を対応単位で記録してから進める。

検証は引継ぎ書再生成、文書確認、差分確認、64項目と受入IDの対応確認を行い、#60に変更と結果・残課題を記録する。

## v0.6の対応単位

v0.6の実装子Issueは、コード変更前に親#6・マイルストーン6への所属を確認して登録した。

| 子Issue | 対応単位 | 先行成果 |
|---|---|---|
| [#53](https://github.com/Tao-pyth/nymph-toolkit/issues/53) | Contracts・履歴形式 | #52 |
| [#54](https://github.com/Tao-pyth/nymph-toolkit/issues/54) | 予定変更・競合・要求結果 | #53 |
| [#55](https://github.com/Tao-pyth/nymph-toolkit/issues/55) | 協調的中断再開・計時 | #53・#54 |
| [#56](https://github.com/Tao-pyth/nymph-toolkit/issues/56) | 優先度・実行枠 | #54・#55 |
| [#57](https://github.com/Tao-pyth/nymph-toolkit/issues/57) | Runtime・Connections・FileStore統合 | #53〜#56 |
| [#58](https://github.com/Tao-pyth/nymph-toolkit/issues/58) | A06・例・配布・CI・文書 | #53〜#57 |
| [#59](https://github.com/Tao-pyth/nymph-toolkit/issues/59) | 公開と匿名取得確認 | #58・最終CI |

## v0.5の対応単位

2026年11月21日のR17により、次の子Issueをコード変更前に登録し、親Issue #5のsub-issueとマイルストーンv0.5.0への所属を確認した。[ADR 0020](adr/0020-v0.5-task-manager.md)の採用範囲と未決事項を各実装前に確認する。

| 子Issue | 対応単位 | 先行する判断・成果 |
|---|---|---|
| [#45](https://github.com/Tao-pyth/nymph-toolkit/issues/45) | TaskManagerの時間・状態・実行境界と受入範囲 | v0.4の採用契約とR17の回答 |
| [#46](https://github.com/Tao-pyth/nymph-toolkit/issues/46) | 活動要求・状態・時間到達通知のContracts | #45の型・状態の判断 |
| [#47](https://github.com/Tao-pyth/nymph-toolkit/issues/47) | 予定・実行追跡と時間到達通知 | #45・#46 |
| [#48](https://github.com/Tao-pyth/nymph-toolkit/issues/48) | Runtime・ModuleGroup・Connectionsとの統合 | #45・#46・#47 |
| [#49](https://github.com/Tao-pyth/nymph-toolkit/issues/49) | 活動履歴と再起動時の扱い | #45の再起動判断・#46 |
| [#50](https://github.com/Tao-pyth/nymph-toolkit/issues/50) | A05、実行例、配布・CI、Docs・引継ぎ書 | 各採用範囲の判断と実装 |
| [#51](https://github.com/Tao-pyth/nymph-toolkit/issues/51) | v0.5.0公開と公開後の確認 | #50の受入・配布・CI成功 |

R17の時間到達・再起動・過去時刻・終了指示への回答を#45とADR 0020へ採用として記録した。D5〜D8の実装判断を対応Issueへ先に記録し、#46〜#49の実装と#50の採用範囲の検証・資料同期を確認した。各Issueに目的・対象範囲・完了条件・検証方法・先行課題を記録し、最終コミットのCI・公開後取得の結果は#51へ記録する。

## v0.2に向けた最初の対応単位

親Issueは[#2 Runtime](https://github.com/Tao-pyth/nymph-toolkit/issues/2)、マイルストーンは[v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/2)である。

| 子Issue | 対応単位 | 先行課題 |
|---|---|---|
| [#21](https://github.com/Tao-pyth/nymph-toolkit/issues/21) | 今回の運用ルール・資料整備 | なし |
| [#22](https://github.com/Tao-pyth/nymph-toolkit/issues/22) | 開発環境とRuntimeライフサイクルの設計判断 | #21 |
| [#23](https://github.com/Tao-pyth/nymph-toolkit/issues/23) | 採用判断に基づくCore・Contracts開発環境 | #22 |
| [#24](https://github.com/Tao-pyth/nymph-toolkit/issues/24) | 採用した最小Runtimeとダミー実行 | #22・#23 |
| [#25](https://github.com/Tao-pyth/nymph-toolkit/issues/25) | A02の受入と再現手順の確認 | #24 |
| [#26](https://github.com/Tao-pyth/nymph-toolkit/issues/26) | R11に伴うv0.2.0公開と配布物の取得確認 | #25 |

この分割は対応を追跡するための初期計画である。R11の実施に伴い、#22でPython版・ツール・APIなどをADR 0014へ記録し、後続の範囲と検証条件を更新する。#26は受入後の公開を独立した対応単位として追加した。

## v0.3に向けた通信方針の後続判断

R12の直接通信緩和の採用記録と資料・引継ぎ書生成ツールの同期は、親Issue #3・マイルストーンv0.3.0に属する子Issue [#34](https://github.com/Tao-pyth/nymph-toolkit/issues/34)で追跡する。生成ツールの説明文を変更する前に、この子Issueを登録した。

Registryの設計判断は[#27](https://github.com/Tao-pyth/nymph-toolkit/issues/27)、通信の具体的な許可範囲・API・解除時の動作はv0.4の親Issue [#4](https://github.com/Tao-pyth/nymph-toolkit/issues/4)へ引き継ぐ。#34は採用判断の反映を扱い、RegistryやConnectionsの実装完了とは区別する。

## v0.3の実施範囲と対応単位

R13・ADR 0016で設計判断を具体化し、以下の対応単位で実装・受入・公開を進める。すべて親Issue #3とマイルストーンv0.3.0に属する。

| 子Issue | 対応単位 |
|---|---|
| [#27](https://github.com/Tao-pyth/nymph-toolkit/issues/27) | Registry・依存・着脱とModuleGroupの設計判断 |
| [#28](https://github.com/Tao-pyth/nymph-toolkit/issues/28) | 不変の登録情報・変更通知・失敗を表すContracts |
| [#29](https://github.com/Tao-pyth/nymph-toolkit/issues/29) | 同期Registry、登録・照会・解除・再登録・原状維持 |
| [#30](https://github.com/Tao-pyth/nymph-toolkit/issues/30) | 必須依存、推移的不足と解除・再登録の変更通知 |
| [#31](https://github.com/Tao-pyth/nymph-toolkit/issues/31) | 既存RuntimeとModuleGroupの連携、失敗・取消・後処理 |
| [#32](https://github.com/Tao-pyth/nymph-toolkit/issues/32) | A03、回帰・配布・CI、文書と引継ぎ書の同期 |
| [#33](https://github.com/Tao-pyth/nymph-toolkit/issues/33) | v0.3.0公開と公開後の取得・実行確認 |

#29・#30は依存評価と登録状態の確定が同じ内部処理を使うため、一つの対応コミットで両Issueを追跡する。稼働中実体着脱・Connections・TaskManager・IPCは後続に残し、採用範囲と制限を受入記録・Releaseで明示する。

## v0.4の接続管理方針の具体化

R14の方針と補足回答を、親Issue [#4](https://github.com/Tao-pyth/nymph-toolkit/issues/4)・マイルストーンv0.4.0に属する子Issue [#35](https://github.com/Tao-pyth/nymph-toolkit/issues/35)で追跡する。引継ぎ書生成ツールの説明を編集する前に、子IssueとGitHub親子関係を登録した。

対応範囲はADR 0017、関連Docs・受入案・引継ぎ書への採用方針の反映である。要求時の候補選定とCore上への保存、確立後の利用ごとの再審査省略、稼働中の初回追加と確定済み接続先固定、起動時・ヘルスチェック時の検証と失効、連携エラー時の中断・申請を扱う。

上記はR14時点の記録である。選定担当・永続化・互換性・中断範囲・ヘルスチェック等は後続のR15・ADR 0018で具体化した。Connectionsの実装やv0.4公開は#35に含めず、対応単位の子Issueと必要な判断を先に登録する。

## R15の一問一答を反映する資料更新

親Issue [#4](https://github.com/Tao-pyth/nymph-toolkit/issues/4)・マイルストーンv0.4.0配下の子Issue [#36](https://github.com/Tao-pyth/nymph-toolkit/issues/36)で、ADR 0018、根拠R15、関連Docs・A04・引継ぎ書を同期する。生成ツールの固定ヘッダーを更新する前に、子Issue・GitHubの親子関係・同一マイルストーンを登録した。

採用済みの振る舞いと、API・保存形式・接続識別キー・競合規則・バッファ数値等の未採用案を区別する。Coreが候補一覧を返し要求側が選ぶという最終訂正を反映する。履歴保存・救命措置まで記録するが、今回の範囲は資料と生成ヘッダーの同期であり、製品コード・公開API・版情報・公開済みタグ/Releaseを変更しない。

文書検証・変更コミット・残課題は#36へ記録する。親Issue #4は実装・A04の課題として継続し、資料更新の完了で閉じない。後続の実装単位はロードマップの案を基に、それぞれ必要な判断と子Issue登録を先行する。

## R16によるv0.4の着手

v0.4着手指示に基づき、以下をすべて親Issue #4・マイルストーンv0.4.0の子課題としてコード変更前に登録した。判断は[ADR 0019](adr/0019-v0.4-connections.md)へ段階的に記録する。

| 子Issue | 対応単位 |
|---|---|
| [#37](https://github.com/Tao-pyth/nymph-toolkit/issues/37) | 公開契約・状態・保存・競合規則の設計判断 |
| [#38](https://github.com/Tao-pyth/nymph-toolkit/issues/38) | 契約宣言、候補・稼働情報、通知・失敗型 |
| [#39](https://github.com/Tao-pyth/nymph-toolkit/issues/39) | 候補照会、要求側選定、接続固定・永続設定 |
| [#40](https://github.com/Tao-pyth/nymph-toolkit/issues/40) | 協調的中断・期限付き準備・操作入口 |
| [#41](https://github.com/Tao-pyth/nymph-toolkit/issues/41) | 個別ヘルス申請・部分失効と復帰 |
| [#42](https://github.com/Tao-pyth/nymph-toolkit/issues/42) | 履歴の非同期保存・Core内蔵の救命措置 |
| [#43](https://github.com/Tao-pyth/nymph-toolkit/issues/43) | A04統合・性能・回帰・配布・資料 |
| [#44](https://github.com/Tao-pyth/nymph-toolkit/issues/44) | 受入後のv0.4.0公開準備・取得確認 |

登録だけで未決の仕様を採用したものとせず、各範囲の実装前に必要な判断を記録する。既存の#35・#36は資料更新の完了記録として保持する。

## R27：顧客向けの契約・利用説明

親[#90](https://github.com/Tao-pyth/nymph-toolkit/issues/90)をv0.9.0の利用ガイドと顧客向け契約説明へ拡張した。文書・図解は[#95](https://github.com/Tao-pyth/nymph-toolkit/issues/95)、任意のPDF/HTML生成と引継ぎ書同期・検証は[#96](https://github.com/Tao-pyth/nymph-toolkit/issues/96)に分け、コード変更前にGitHubのsub-issue関係と同じv1.0.0マイルストーンへの所属を確認した。

導入担当者と開発担当者の両方を読者とし、公開済みv0.9.0の契約と利用を説明する。R26のD01〜D04に追加する範囲として、既存[PR #93](https://github.com/Tao-pyth/nymph-toolkit/pull/93)でまとめてレビューする。製品ソース・API・実行例・版は変更せず、新しい契約採用やReleaseを含めない。本文・図・生成条件・表示検証の結果を子Issueへ記録し、関連する#94の終了時調査は完了扱いにしない。

## R28：Windows終了時エラーの修正

親[#10](https://github.com/Tao-pyth/nymph-toolkit/issues/10)・v1.0.0配下の既存子[#94](https://github.com/Tao-pyth/nymph-toolkit/issues/94)について、コード変更前に対応範囲・完了条件・検証方法を更新し、原因を確認した段階で内部修正判断を追記した。NTK所有TCPの終了処理、関連回帰試験・ダミー、検証記録と引継ぎ書同期を扱う。公開API・採用64項目は変更せず、新規ADR・Releaseを作らない。修正前後の制御再現と自然発生の確認範囲を[検証記録](validation/windows-shutdown.md)で区別し、PR・確認結果を#94へ紐付ける。

## R29のv1.0 Core接続契約

親#10・マイルストーンv1.0.0。コード変更前に子#98（設計/B00）、#99（Contracts/登録検証/API整理）、#100（安定API/例）、#101（統合）、#102（配布/CI/資料）を登録し、GitHubの親子関係を設定した。必要な破壊的整理も含める回答を範囲へ反映済み。判断はADR 0026、結果はvalidation/v1.0、レビュー用PRへ紐付ける。親・マイルストーンの公開完了は今回の実装完了とは区別する。

## R30のv1.0.0レビュー・公開

親#10・マイルストーンv1.0.0配下に、[#104](https://github.com/Tao-pyth/nymph-toolkit/issues/104)を公開用文書/生成ヘッダー変更前に登録し、実親子関係を確認した。PR #103のレビューと最終CI、マージ、タグ/Release、4添付の匿名取得・通常導入を記録する。#98〜#102の採用範囲の完了と、#104の公開後確認を分けて追跡し、その後に親#10とマイルストーンを閉じる。

## R31のv1.1 Memory

親[#11](https://github.com/Tao-pyth/nymph-toolkit/issues/11)・マイルストーンv1.1.0を確認し、コード変更前に以下を実親子関係付きで登録した。各Issueへ目的・範囲・完了条件・検証・先行課題と実装判断を記録した。

| 子Issue | 対応単位 |
|---|---|
| [#105](https://github.com/Tao-pyth/nymph-toolkit/issues/105) | 初期スコープ・未決/延期・ADR 0027・B01 |
| [#106](https://github.com/Tao-pyth/nymph-toolkit/issues/106) | Memory契約・SQLite保存/取得・単体/障害検証 |
| [#107](https://github.com/Tao-pyth/nymph-toolkit/issues/107) | 公開契約での接続・4配置・実行例 |
| [#108](https://github.com/Tao-pyth/nymph-toolkit/issues/108) | v1.1候補・配布・CI・Docs/引継ぎ書・PR |

今回の到達点はレビュー用PR。タグ/Release、公開後確認、親/マイルストーン終了は後続指示で扱う。

## R32のv1.1レビュー・公開

親#11・マイルストーンv1.1.0配下に[#110](https://github.com/Tao-pyth/nymph-toolkit/issues/110)を公開用文書・生成ヘッダー変更前に登録した。PR #109のレビュー・最終CI・マージ・公開・匿名取得と通常導入の結果を記録し、完了後に実装子#105〜#108と親・マイルストーンを閉じる。

公開前CIのMemory統合失敗は子[#111](https://github.com/Tao-pyth/nymph-toolkit/issues/111)をテスト/例の変更前に登録し、全体期限・診断・制御再現を扱った。Core/Memoryの製品仕様は維持する。

## R33：v1.2 Document Adapter

親[#12](https://github.com/Tao-pyth/nymph-toolkit/issues/12)・マイルストーンv1.2.0を確認し、コード変更前に子#112（設計/B02）、#113（入力契約/読込）、#114（Memory接続/ライフサイクル/4配置/例）、#115（配布/CI/Docs/生成）を登録し、実親子関係と同じマイルストーンを確認した。未決事項の具体化はADR 0028に記録する。結果とPRを各子へ紐付け、親/マイルストーンと公開後確認は後続段階へ残す。

## R34：v1.2レビュー・公開

親#12・v1.2.0配下に、公開/生成ヘッダーの[#117](https://github.com/Tao-pyth/nymph-toolkit/issues/117)と、Documentの二重障害修正/回帰の[#118](https://github.com/Tao-pyth/nymph-toolkit/issues/118)を変更前に登録し、実親子関係を確認した。PR #116の最終CI・レビュー・マージ、タグ/Release、4添付の匿名取得と通常導入を追跡する。公開後確認の結果を記録してから実装子#112〜#115、#117/#118、親/マイルストーンを閉じる。
