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

この運用ルールは採用済みである。v0.2はR11・ADR 0014、v0.3はR13・ADR 0016、v0.4はR16・ADR 0019で実施範囲を具体化した。v0.5はR17・ADR 0020で設計判断へ着手しており、未決事項を実装要件へ含めない。v0.6〜v0.8とv1.1.0〜v1.10.0の機能配分、Subsystem・Adapterの名称や実装順序、契約詳細などは既存の提案状態を維持する。登録だけでは採用や着手の宣言にならない。計画を変更する場合は理由・依存関係・受入への影響を記録し、ロードマップ、Issue、関連ADRを整合させる。

v0.1.0＝GitHub公開、v0.9.0＝合意したCore機能の完成、v1.0.0＝CoreとSubsystem・Adapterの接続契約整備という確定目標と、NymphとCoreの責務分離を維持する。通信方針はR12・[ADR 0015](adr/0015-core-authorized-direct-communication.md)で更新し、Coreが管理・許可した直接通信を採用した。詳細な許可条件・APIなどは実装前に判断する。

## 登録したマイルストーンと親Issue

2026年11月20日に既存ロードマップを以下のように整理した。進捗の最新状態はGitHubを参照する。v0.1.0は公開結果を記録した完了済みの段階であり、新ルールを公開前に実施したという意味ではない。

| マイルストーン | 親Issue | 計画の位置付け |
|---|---|---|
| [v0.1.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/1) | [#1 GitHub公開](https://github.com/Tao-pyth/nymph-toolkit/issues/1) | 確定目標・公開済み |
| [v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/2) | [#2 Runtime](https://github.com/Tao-pyth/nymph-toolkit/issues/2) | R11・ADR 0014で実施範囲を具体化 |
| [v0.3.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/3) | [#3 Registry](https://github.com/Tao-pyth/nymph-toolkit/issues/3) | R13・ADR 0016で実施範囲を具体化 |
| [v0.4.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/4) | [#4 Connections](https://github.com/Tao-pyth/nymph-toolkit/issues/4) | R16・ADR 0019で実施範囲を具体化 |
| [v0.5.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/5) | [#5 TaskManager基本](https://github.com/Tao-pyth/nymph-toolkit/issues/5) | R17・ADR 0020で設計判断に着手 |
| [v0.6.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/6) | [#6 活動変更](https://github.com/Tao-pyth/nymph-toolkit/issues/6) | 機能配分案 |
| [v0.7.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/7) | [#7 ハイブリッド実行](https://github.com/Tao-pyth/nymph-toolkit/issues/7) | 機能配分案 |
| [v0.8.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/8) | [#8 統合検証](https://github.com/Tao-pyth/nymph-toolkit/issues/8) | 機能配分案 |
| [v0.9.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/9) | [#9 Core機能完成](https://github.com/Tao-pyth/nymph-toolkit/issues/9) | 確定目標・詳細範囲は要合意 |
| [v1.0.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/10) | [#10 Core接続契約](https://github.com/Tao-pyth/nymph-toolkit/issues/10) | 確定目標・契約詳細は提案 |
| [v1.1.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/11) | [#11 Memory Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/11) | 名称・機能配分・実装順序は提案 |
| [v1.2.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/12) | [#12 Document Adapter](https://github.com/Tao-pyth/nymph-toolkit/issues/12) | 名称・機能配分・実装順序は提案 |
| [v1.3.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/13) | [#13 Cognition Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/13) | 名称・機能配分・実装順序は提案 |
| [v1.4.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/14) | [#14 Text Interaction / Web Adapter](https://github.com/Tao-pyth/nymph-toolkit/issues/14) | 名称・機能配分・実装順序は提案 |
| [v1.5.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/15) | [#15 Agency Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/15) | 名称・機能配分・実装順序は提案 |
| [v1.6.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/16) | [#16 TaskManager連携強化](https://github.com/Tao-pyth/nymph-toolkit/issues/16) | 名称・機能配分・実装順序は提案 |
| [v1.7.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/17) | [#17 Persona Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/17) | 名称・機能配分・実装順序は提案 |
| [v1.8.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/18) | [#18 Persona連携強化](https://github.com/Tao-pyth/nymph-toolkit/issues/18) | 名称・機能配分・実装順序は提案 |
| [v1.9.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/19) | [#19 Sleep Subsystem](https://github.com/Tao-pyth/nymph-toolkit/issues/19) | 名称・機能配分・実装順序は提案 |
| [v1.10.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/20) | [#20 Sleep連携・Discord Voice Adapter](https://github.com/Tao-pyth/nymph-toolkit/issues/20) | 名称・機能配分・実装順序は提案 |

[マイルストーン一覧](https://github.com/Tao-pyth/nymph-toolkit/milestones)と[Issue一覧](https://github.com/Tao-pyth/nymph-toolkit/issues)からも参照できる。将来段階の子Issueは対応単位が具体化した時点で追加し、各コード変更の開始前に登録する。

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

現在は#45の設計判断と#50の資料同期を進める。時間到達時の通知・継続はユーザー回答で採用した。再起動時の活動等は要決定であり、依存するコード変更やIssueの完了を先行しない。各Issueに目的・対象範囲・完了条件・検証方法・先行課題を記録した。

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
