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

この運用ルールは採用済みである。一方、v0.2〜v0.8とv1.1.0〜v1.10.0の機能配分、Subsystem・Adapterの名称や実装順序、契約詳細などは既存の提案状態を維持する。登録は採用や着手の宣言ではない。計画を変更する場合は理由・依存関係・受入への影響を記録し、ロードマップ、Issue、関連ADRを整合させる。

v0.1.0＝GitHub公開、v0.9.0＝合意したCore機能の完成、v1.0.0＝CoreとSubsystem・Adapterの接続契約整備という確定目標を維持する。NymphとCoreの責務分離、Core経由のみという最後の正式な通信方針も変更しない。

## 登録したマイルストーンと親Issue

2026年11月20日に既存ロードマップを以下のように整理した。進捗の最新状態はGitHubを参照する。v0.1.0は公開結果を記録した完了済みの段階であり、新ルールを公開前に実施したという意味ではない。

| マイルストーン | 親Issue | 計画の位置付け |
|---|---|---|
| [v0.1.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/1) | [#1 GitHub公開](https://github.com/Tao-pyth/nymph-toolkit/issues/1) | 確定目標・公開済み |
| [v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/2) | [#2 Runtime](https://github.com/Tao-pyth/nymph-toolkit/issues/2) | 機能配分案 |
| [v0.3.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/3) | [#3 Registry](https://github.com/Tao-pyth/nymph-toolkit/issues/3) | 機能配分案 |
| [v0.4.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/4) | [#4 Connections](https://github.com/Tao-pyth/nymph-toolkit/issues/4) | 機能配分案 |
| [v0.5.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/5) | [#5 TaskManager基本](https://github.com/Tao-pyth/nymph-toolkit/issues/5) | 機能配分案 |
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
