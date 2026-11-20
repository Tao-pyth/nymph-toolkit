# Nymph Toolkit（NTK）最終ビジョン・初期設計・開発ロードマップ・Codex引継ぎ書

初稿2026年11月19日 ｜ R1〜R13を収録 ｜ 統合リポジトリ `nymph-toolkit`

本書は個別Docs・ADRを全文収録した単一配布用文書である。Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指す。最終ビジョンは収録したProject Visionに従う。

GitHub公開をv0.1.0、合意したCore機能の完成をv0.9.0、接続契約整備をv1.0.0の目標とする。R11に伴うv0.2の実装判断はADR 0014に記録し、過去に確定していた方針と区別する。現在の実装・公開状況は収録したREADME・release・受入記録で確認する。

Nymphが活動を決定し、Coreが実行を管理する。R12・ADR 0015により、Coreが管理・許可した接続で直接通信を認める。Core経由も利用でき、具体的な許可範囲・API・解除時の動作は実装前に判断する。後続バージョンの名称・順序・機能配分と契約詳細は採用状態を確認して読む。

R10により、コード変更はマイルストーン、親Issue、対応単位の子Issue登録の順に前提を整えてから行う。元会話の確認範囲と各指示の根拠はDocs索引に記録する。

本書にもApache-2.0を適用し、末尾にLICENSEの公式本文を収録する。第三者成果物と個体データの条件は別途扱う。ファイル名のv0.1は初稿の識別子であり、リポジトリ内の本文は更新する。公開済みRelease添付は各公開時点のスナップショットとして保持する。

## 収録文書

1. [Nymph Toolkit（NTK）](#section-1)
2. [NTKへの参加](#section-2)
3. [NTKの作業ルール](#section-3)
4. [Docsの読み方と根拠](#section-4)
5. [Project Vision — 人工人格Nymphの最終到達目標](#section-5)
6. [Architecture](#section-6)
7. [v0.2 Runtimeの使い方](#section-7)
8. [RegistryとModuleGroup](#section-8)
9. [ADR索引と更新方法](#section-9)
10. [ADR 0001 Coreと統合リポジトリ](#section-10)
11. [ADR 0002 実行モデル](#section-11)
12. [ADR 0003 通信経路](#section-12)
13. [ADR 0004 活動の決定権](#section-13)
14. [ADR 0005 初期実装の範囲](#section-14)
15. [ADR 0006 v1.0.0のCore接続契約](#section-15)
16. [ADR 0007 v1.x以降のリリース運用と開発順序](#section-16)
17. [ADR 0008 v1.xのSubsystem・Adapter責務案](#section-17)
18. [ADR 0009 単一リポジトリと段階的な配布パッケージ分割](#section-18)
19. [ADR 0010 Nymphの最終ビジョンと実装範囲の区別](#section-19)
20. [ADR 0011 自作コード・Contracts・設計文書へのApache-2.0適用](#section-20)
21. [ADR 0012 個人アカウントでのv0.1.0公開と参加方針](#section-21)
22. [ADR 0013 マイルストーン・親子Issueを前提とするコード変更](#section-22)
23. [ADR 0014 v0.2の開発環境と最小Runtime](#section-23)
24. [ADR 0015 Coreが許可する直接通信の採用](#section-24)
25. [ADR 0016 v0.3のRegistryと複数対象のライフサイクル](#section-25)
26. [NTK開発ロードマップ](#section-26)
27. [受入基準案と検証記録](#section-27)
28. [v0.2 Runtime受入記録](#section-28)
29. [v0.3受入記録](#section-29)
30. [開発準備とGit運用](#section-30)
31. [マイルストーンと親子Issueの運用](#section-31)
32. [公開準備とリリース手順](#section-32)
33. [変更履歴](#section-33)
34. [Apache License 2.0（原文）](#section-34)

---

<a id="section-1"></a>

収録元 `README.md`

## Nymph Toolkit（NTK）

Nymph Toolkit（NTK）は、人間との継続的な交流や外部環境での経験を通じて、知識・言語・行動能力・人格を発達させる人工人格「Nymph」を構築するためのソフトウェア基盤です。Apache-2.0で開発資料を公開し、オープンソースでの実装を進めます。GitHubの統合リポジトリは [Tao-pyth/nymph-toolkit](https://github.com/Tao-pyth/nymph-toolkit) です。

**Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指します。** 限定的な能力から「赤ちゃんを育てるような感覚」で成長を支え、自然な日本語で交流し、権限の範囲でPC環境を観測・操作できる姿を最終目標とします。

基本機構と経験から獲得する知識を区別し、言語獲得そのものを研究します。既存LLMを言語理解・文章生成の中核にする方式は採らず、音声認識などの補助技術は利用できます。記憶・自己理解・自律活動・人格・睡眠の長期構想と評価領域はProject Vision（`docs/vision.md`）にまとめています。最終的な完成を特定のバージョンに固定せず、各段階で実装範囲と到達基準を具体化します。

構成は、Nymphが決めた活動を実行管理するCoreを中心に、Subsystem・Adapterを着脱するPython基盤です。

配布方針は、単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterを必要に応じて分割するものです。個別の分割は依存関係・独立更新・単独配布の必要性に基づいて判断します。採用した配布方針（`docs/adr/0009-package-distribution.md`）

### 現在の段階

**v0.3.0：Registry・依存管理・ModuleGroup。** CoreとContractsの単一パッケージに、登録・照会・解除、不変スナップショット、依存先の利用可否と変更通知、複数対象の初期化・実行・後処理を含みます。CPython 3.12以上、実行時の外部依存はありません。Connections・TaskManager・別プロセス実行は今後の段階で扱います。

v0.1.0では初期資料・開発基盤、v0.2.0では最小Runtimeを2026年11月20日に公開しました。合意したCore機能の完成をv0.9.0の目標とします。v0.2の採用範囲はADR 0014（`docs/adr/0014-v0.2-runtime.md`）、v0.3はADR 0016（`docs/adr/0016-v0.3-registry.md`）で具体化し、v0.4〜v0.8の配分は開発計画案です。

v0.3では実行開始前にSubsystem・Adapterのダミーを着脱し、起動から停止完了まで構成を固定します。停止後は明示解除できます。実体の稼働中着脱は、接続の解除・失効契約を設計する後続段階へ残しています。利用方法はRegistryとModuleGroup（`docs/registry.md`）を参照してください。

[v0.3.0のリリース](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.3.0)にwheel・sdist・引継ぎ書・チェックサムと公開結果を掲載します。v0.3受入記録（`docs/validation/v0.3.md`）には検証環境・結果・制約を記載しています。過去の[v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.2.0)・[v0.1.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.1.0)は各公開時点の記録として保持します。

V0.1・V0.9は、それぞれv0.1.0・v0.9.0の節目を表します。v1.0.0はCoreとSubsystem・Adapterの接続契約を大きく形作る目標です。v1.1.0〜v1.10.0のSubsystem・Adapter開発、奇数・偶数マイナーのリリース運用は設計提案としてロードマップに追記しています。記載するSubsystem名・Adapter名は暫定名称で、実装順序と機能配分も変更される可能性があります。

Nymphが活動内容・時刻・期間・変更を決め、Coreが実行を管理します。初期開発ではCore Runtime、Registry、Connections、TaskManagerを実装し、周辺をダミーで検証します。ハイブリッド実行を採用し、Python `asyncio` と軽量なメソッド呼び出しを技術の方向性とします。

活動の価値や優先度はNymphが判断します。優先度機能を採用する場合、Coreは与えられた値と採用済み規則に基づいて実行順序を処理します。時間変更、優先度変更、中断・再開などの具体的な採否はV0.6の判断対象です。

通信は、**Coreが管理・許可した接続ではSubsystem間の直接通信を認める**方針を採用しました。Core経由の通信も利用できます。許可対象・API・解除時の動作などはConnections実装前に具体化します。採用履歴と未決事項はADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）に記録しており、直接通信の実装は今後の段階です。

### 開発を始める方へ

CPython 3.12以上で、リポジトリ直下から次を実行できます（PowerShell）。LinuxではPythonのパスを `.venv/bin/python` に置き換えてください。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe examples/runtime_demo.py
.venv/Scripts/python.exe examples/registry_demo.py
.venv/Scripts/python.exe -W error -m unittest discover -s tests -t . -v
```

Runtimeのダミーはstart → run → stopを表示します。Registryのダミーは依存先の登録・解除による変更通知、依存順の初期化と逆順の後処理、結果・残存タスク0件を表示します。Runtimeの使い方（`docs/runtime.md`）とビルド・配布検証（`docs/development.md`）も参照してください。

コード変更は、**対象バージョンのマイルストーン → 親Issue → 対応単位の子Issue登録 → 対応**の順を必須とします。Issue運用と登録済み課題（`docs/issue-workflow.md`）を確認してから着手してください。登録した計画案は、仕様の採用と区別します。

- 全体を一つの文書で読む場合は、日本語初期設計・Codex引継ぎ書（`docs/NTK-Core-v0.1-Handoff-ja.md`）を参照してください。
- 個別の設計や判断を更新する場合は、Docs一覧と根拠の扱い（`docs/README.md`）から進んでください。
- 開発の段階と完了条件は、ロードマップ（`docs/roadmap.md`）と受入基準案（`docs/acceptance.md`）にあります。
- Gitの用意は開発手順（`docs/development.md`）、公開先と公開手順はリリース手順（`docs/release.md`）にあります。
- 提案・修正への参加方法はCONTRIBUTING（`CONTRIBUTING.md`）を参照してください。公開先は個人アカウント配下の `Tao-pyth/nymph-toolkit`（public）に決定しています。

将来のPC状況取得はAdapterで扱います。Desktop Adapterはv1.10.0までの配分に含めず将来課題とします。複製・移植・伝播機構は初期スコープ外です。

### ライセンス

NTKの自作コード、Contracts、設計文書には **Apache License 2.0（SPDX: `Apache-2.0`）** を適用します。設計文書にはREADME、Docs・ADR、配布用引継ぎ書を含みます。将来の自作Subsystem・Adapterにもこの方針を適用し、パッケージ分割後も各配布物にライセンスを含めます。

ライセンス本文はLICENSE（`LICENSE`）、採用理由と適用範囲はADR 0011（`docs/adr/0011-apache-2.0-license.md`）を参照してください。第三者のコード・依存ライブラリ・モデル・文書・音声などは各権利者の条件に従います。Nymphの会話・記憶・人格データへ、このソフトウェアライセンスを一律に適用するものではありません。

---

<a id="section-2"></a>

収録元 `CONTRIBUTING.md`

## NTKへの参加

NTKは、人工人格Nymphの成長を支える基盤を開発するプロジェクトです。現在はCoreのRuntime・Registry・ModuleGroupと必要なContractsを実装し、ダミーで検証する初期段階です。実装状況はREADME（`README.md`）を参照してください。

### 提案・報告

質問、文書の誤り、設計提案は[GitHub Issues](https://github.com/Tao-pyth/nymph-toolkit/issues)へお願いします。関連する文書・ADR、現状の問題、提案する変更とその理由を記載してください。日本語での投稿を歓迎します。

実装に着手する前にREADME（`README.md`）、Project Vision（`docs/vision.md`）、ロードマップ（`docs/roadmap.md`）、ADR索引（`docs/adr/README.md`）を確認してください。確定事項と提案・未決事項を区別し、設計や開発範囲を変える場合は先にIssueで相談してください。

### コード変更の前提

コードの新規作成・修正を伴う対応は、**バージョン別マイルストーン → 親Issue → 対応単位の子Issue登録 → 対応**の順を必須とします。親子関係はGitHubのsub-issueで設定し、親・子の両方に対象マイルストーンを設定してください。

子Issueに目的・範囲・完了条件・検証方法・先行課題を記載し、実装に必要な未決事項を判断してから着手します。新規実装、不具合修正、リファクタリング、テスト・実行・配布設定の変更も対象です。Issueの登録だけで提案が採用済みになることはありません。

具体的な運用と登録済み課題はIssue運用（`docs/issue-workflow.md`）、採用記録はADR 0013（`docs/adr/0013-milestone-issue-workflow.md`）を参照してください。

### Pull Request

- 文書修正は小さな単位で送れます。変更した内容と理由、確認した項目を記載してください。
- 設計変更はメンテナーと議論し、採用された判断をADRへ記録します。提案段階の内容を確定仕様として記載しないでください。
- 実装変更は合意した段階・範囲に合わせ、対応する子Issue、必要な検証結果と関連Docsの更新を含めてください。完了時は子IssueへコミットまたはPR・検証結果・残課題を記録します。
- Docsを変更した場合は文書の更新方法（`docs/README.md`）に従い、単一配布用引継ぎ書との整合を確認してください。

変更の採否とマージはメンテナーが判断します。提案やPRの提出だけで採用とはなりません。

### ライセンスと投稿内容

自作コード・Contracts・設計文書への貢献は、プロジェクトのApache-2.0ライセンス（`LICENSE`）を前提とします。第三者の成果物を含める場合は、出典と利用条件を示し、元の権利表示を保持してください。

IssueやPRには、認証情報や他者の非公開データを含めないでください。再現にデータが必要な場合は、共有できるダミーデータを使用してください。

---

<a id="section-3"></a>

収録元 `AGENTS.md`

## NTKの作業ルール

このリポジトリで作業するCodexなどの開発エージェントは、参加方針（`CONTRIBUTING.md`）とIssue運用（`docs/issue-workflow.md`）に従う。

### コード変更に着手する前

1. 対象バージョンのGitHubマイルストーンがあることを確認する。
2. 対象範囲をまとめた親Issueがあり、そのマイルストーンに属することを確認する。
3. 今回の対応単位の子Issueを登録し、GitHubの親子関係と同じマイルストーンを設定する。
4. 子Issueの目的、対象範囲、完了条件、検証方法、先行課題・未決事項を確認する。実装に必要な判断を記録してからコードを変更する。

親Issueだけで実装を始めず、コード変更後に子Issueを後付けしない。新規実装、不具合修正、リファクタリング、テストや実行・配布に影響する設定変更もこの順序で扱う。文書だけの修正は対象外だが、設計判断の変更は関連Issue・ADRへ記録する。

マイルストーンやIssueの作成は仕様採用を意味しない。確定事項・提案・要決定を区別し、既存ADRを確認する。Nymphの意思決定とCoreの実行管理の境界を維持する。通信はADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）によりCoreが管理・許可した接続で直接通信を認める。Core経由も利用できる。許可範囲・API・解除時の動作などの詳細は、対象の実装前に記録する。

変更を関連する子Issueへ紐付け、コミットまたはPR、確認結果、残課題を記録する。採用範囲の対応・検証・文書更新が完了してから子Issueを閉じる。対象が広がる場合は、追加範囲のコード変更前に子Issueを更新するか別の子Issueを登録する。

Docs更新時は文書の更新方法（`docs/README.md`）に従って単一配布用引継ぎ書を同期する。公開済みのタグやRelease添付を後続の文書修正で差し替えない。

---

<a id="section-4"></a>

収録元 `docs/README.md`

## Docsの読み方と根拠

初稿の文書整備日は2026年11月19日。対象はNymph Toolkit（NTK）の最終ビジョン、Core初期開発、公開準備からV0.9までの計画、およびv1.0.0以降のロードマップ案である。

### 読み順と格納場所

| 文書 | 用途 |
|---|---|
| ルートREADME（`README.md`） | プロジェクト概要と現在の実装状況 |
| CONTRIBUTING（`CONTRIBUTING.md`） | Issue・Pull Requestによる参加と設計判断の扱い |
| AGENTS.md（`AGENTS.md`） | Codexなどの開発エージェントが守る着手前・完了時のルール |
| 単一配布用の引継ぎ書（`docs/NTK-Core-v0.1-Handoff-ja.md`） | 以下のDocs・ADRを一つに収録したスナップショット |
| vision.md（`docs/vision.md`） | 人工人格Nymphの最終ビジョン・研究方針・長期評価領域 |
| architecture.md（`docs/architecture.md`） | Coreの責務、境界、フォルダ構成、未決事項 |
| runtime.md（`docs/runtime.md`） | v0.2の実装済みRuntime・Contractsの使い方と制約 |
| registry.md（`docs/registry.md`） | v0.3のRegistry・ModuleGroup契約、着脱・依存管理の境界 |
| ADR索引（`docs/adr/README.md`） | 判断履歴と採用状態 |
| roadmap.md（`docs/roadmap.md`） | 各段階の着手条件、作業、成果物、完了条件 |
| acceptance.md（`docs/acceptance.md`） | バージョン別の検証シナリオと結果の記録方法 |
| validation/v0.2.md（`docs/validation/v0.2.md`） | v0.2の受入結果、環境・再現手順、制約 |
| validation/v0.3.md（`docs/validation/v0.3.md`） | v0.3のA03、回帰・配布検証、後続へ残す範囲 |
| development.md（`docs/development.md`） | Git、環境構築、日常開発、文書更新 |
| issue-workflow.md（`docs/issue-workflow.md`） | マイルストーン・親子Issueによるコード変更の前提と登録済み課題 |
| release.md（`docs/release.md`） | 公開前の判断欄、GitHub公開、タグ・リリースの手順 |
| LICENSE（`LICENSE`） | 自作コード・Contracts・設計文書に適用するApache-2.0の公式本文 |

### 根拠と確認範囲

| 根拠ID | 資料 | 確認できる範囲 |
|---|---|---|
| R1 | 会話「構想整理」の提示プレビュー。会話ID `6afe67b5-b89c-83ec-af64-a9eb8bc285d6` | ユーザーのPC状況取得Adapterへの言及、リポジトリに関する質問、引継ぎ資料の依頼。アシスタントの本文は参照記号のみで、会話全文は未取得 |
| R2 | 本チャットの最初の引継ぎ依頼 | 確定方針、通信経路の採用履歴、Coreだけの初期実装とダミー検証、統合リポジトリ名の明示 |
| R3 | 本チャットの追加依頼と実装指定された計画 | 公開準備とGitの用意、V0.1＝GitHub公開、V0.9＝Core機能完成、Docs・ADRの配置、段階別ロードマップの作成 |
| R4 | 本チャットで提示された「NTK Coreロードマップの整合性レビュー」 | 意思決定と実行管理の境界の再確認、通信経路の解釈、時間・優先度・活動変更・Subsystem独立性の明確化案。個々の機能の実装採用は未確定 |
| R5 | 本チャットの「Codex編集依頼書：NTK v1.0.0以降の開発ロードマップ案」 | v1.0.0の接続契約整備という目標と既存方針の維持、v1.1.0〜v1.10.0の推奨配分、暫定名称、研究方針・責務境界、リリース運用案の明示 |
| R6 | 本チャットの配布方針の採用・資料反映指示 | 単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて分割する方針を明示的に採用 |
| R7 | 添付「Project Vision — 人工人格Nymphの最終到達目標」と反映指示 | 添付本文全16節とVision Statementを確認。最終ビジョンは同内容に沿う。完成像・研究方針として扱い、各能力を確定した実装要件へ一括追加しない |
| R8 | 本チャットのApache-2.0採用・資料反映指示 | 自作コード・Contracts・設計文書へのApache-2.0適用、LICENSE追加、README・ADR・公開準備資料・引継ぎ書への反映を明示的に指示 |
| R9 | 本チャットの個人アカウントでのpublic公開指示 | `Tao-pyth/nymph-toolkit` を資料中心にpublic公開し、簡潔な参加方針とv0.1.0タグ・リリースを整える方針を採用 |
| R10 | 本チャットのコード変更に先立つ課題管理の指示 | バージョン別マイルストーン、親Issue、対応単位の子Issue登録の順に整備してから対応することを、コード変更の前提として採用 |
| R11 | 本チャットの「v0.2までの作業」指示 | 登録済みのv0.2課題を設計判断・環境構築・実装・受入・公開の順に進める実施指示。具体的な実装判断はADR 0014へ記録し、過去に確定済みだった仕様と区別する |
| R12 | 本チャットの「直接通信の緩和は採用ください」という指示 | Coreが管理・許可した接続で直接通信を認める既存の緩和案を採用。許可対象・API・解除時の動作などの詳細は今回の指示では未決 |
| R13 | 本チャットの「v 0.3まで進行してください」という実施指示 | 登録済みのv0.3課題を設計・実装・受入・公開まで進める。具体的な実装判断はADR 0016へ記録し、過去の確定事項と区別する |

初稿作成時の環境では `read_thread` が利用できず、元会話全文との照合は未実施である。確定事項の記述はR2・R3の明示指示を根拠にし、R4で責務境界の説明と判断対象を補う。R4のレビュー本文が述べる過去の経緯と、元会話の直接確認は確認範囲を区別する。既存稿だけにある断定は根拠として採用しない。原文確認後に追加する場合は、発言と採用状況を照合してからADRへ記録する。

R5は今回の明示的な編集根拠として扱う。v1.0.0で接続契約を大きく形作る目標は確定事項として追加する。契約詳細、Subsystem・Adapterの正式名称・実装順序・機能配分、奇数・偶数マイナーとパッチの運用は提案・要決定として記録する。R5が指定した研究方針と責務境界を各提案の前提にする。

R6の配布方針はADR 0009で採用として記録する。前段で提示されたフォルダ構成案のうち、将来の個別パッケージ名や分割対象、Capability照合の担当などは引き続き具体化する事項として扱う。

R7の最終ビジョンはvisionに収録し、ADR 0010で長期ビジョンとして採用する。元の本文にある具体的な構想は長期目標として位置付け、現行バージョンへの割当や受入条件は後続判断へ残す。本文には現在の通信方針、ロードマップの採用状態、公開準備の状態を補って既存資料と整合させる。

R8によりApache-2.0を採用し、ADR 0011に適用範囲を記録する。R7反映時点では未決だったライセンス選定は解消済みである。第三者成果物と個体データの条件、公開先・公開範囲の判断は別途扱う。

R9により公開先を個人アカウント `Tao-pyth`、公開範囲をpublicへ確定し、ADR 0012へ記録する。公開の判断と作業の完了は区別し、実際の状態はreleaseで管理する。

R10の着手前ルールはADR 0013へ採用として記録する。既存の各段階をマイルストーンと親Issueへ展開し、コード変更は対応単位の子Issueを登録してから行う。課題への登録を仕様採用と混同しない。

R11に伴うv0.2のPython・配布・Runtimeの実装判断はADR 0014に記録する。残りのバージョンの機能配分案や通信緩和案を採用する指示ではない。

R12による後続判断で直接通信の緩和を採用し、ADR 0015へ記録する。ADR 0003のCore経由のみという旧判断は履歴として保持する。Coreが管理・許可した経路での直接通信とCore経由の通信を認め、具体的な許可範囲・接続契約は実装前に判断する。採用判断と通信機能の実装状況を区別する。

R13に伴うv0.3の登録・依存・着脱・Runtime連携の判断はADR 0016に記録する。v0.4以降の通信契約・活動管理・IPCや本番Subsystem・Adapterを先行採用する指示とは扱わない。

### 状態の読み方

| 表記 | 扱い |
|---|---|
| 確定・採用 | R2・R3の設計・開発目標、R5のv1.0.0目標、R6の配布方針、R8のApache-2.0、R9の公開・参加方針、R10のコード変更前の課題登録、R12のCoreが許可する直接通信など、明示的に決めた事項 |
| 方向性確定 | 技術の方向が採用済み。具体的なAPI・内部方式は要設計 |
| 提案 | 実装順、検証方法、責務の詳細整理などの案 |
| 要決定 | 対象の実装や公開に先立ち、判断を記録する事項 |
| 長期ビジョン | R7で示された最終到達目標・研究方針。具体的な実装要件・時期・合格基準は段階ごとに判断する |
| 初期スコープ外 | 今回計画するCore初期開発の対象から除く事項 |

計画の整備を依頼されたことと、計画内の製品仕様案が採用されたことは、それぞれ状態を記録する。v0.2はR11・ADR 0014、v0.3はR13・ADR 0016で具体化し、v0.4〜v0.8への機能配分と受入方法は提案として扱う。

R4で列挙された時間・優先度の変更、中断・再開、取消・終了は採否を判断する対象として追記する。Subsystemの機能的依存と独立性の整理案のうち、v0.3の採用範囲はR13・ADR 0016で具体化した。Coreが扱う機械的な実行順序と、Nymphが決める活動の価値・優先度の境界を明示し、優先度機能や実行枠の方式は後続判断へ残す。

既存のV0.1〜V0.9という表記はv0.1.0〜v0.9.0の節目を指す。v1.xの名称・配分の変更時には、roadmap、architecture、関連ADR、acceptance、releaseと単一配布用引継ぎ書を照合する。

### 文書の更新

判断履歴は個別ADR、実装状況はルートREADME、実装手順と検証条件は各Docsで管理する。矛盾を見つけた場合は根拠表と後続の採用記録を確認し、関係する文書を同じ変更で整合させる。

単一配布用の引継ぎ書は、ルートREADME、CONTRIBUTING、AGENTS、本書、vision、architecture、runtime、registry、ADR索引と各ADR、roadmap、acceptance、validation配下の記録、development、issue-workflow、release、CHANGELOG、LICENSEの順に全文を収録する。再作成時はMarkdown文書の見出しを一段下げ、ローカルリンクを表示名とリポジトリ直下からのパス表記へ展開する。LICENSEは原文を変更せずtextコードブロックに収録する。収録元のファイル名を各章に付ける。

Python 3.12以上で `python tools/build_handoff.py` を実行して再生成し、`python tools/check_docs.py` で本文一致・ローカルリンク・文字コード・改行・LICENSEを確認する。再生成ツール（`tools/build_handoff.py`）と文書確認ツール（`tools/check_docs.py`）はCIでも使用する。

リポジトリ内の引継ぎ書は最新の資料へ同期し、公開済みReleaseの添付とタグはその時点のスナップショットとして保持する。v0.1.0以降の更新内容はCHANGELOGの未リリース欄で区別する。

---

<a id="section-5"></a>

収録元 `docs/vision.md`

## Project Vision — 人工人格Nymphの最終到達目標

**文書区分：** プロジェクトビジョン・長期構想

**対象：** Nymph Toolkit / Nymph

**位置付け：** これまでの設計方針に基づく長期目標の整理

**注意：** 本文は完成像を示すものであり、すべてを確定した実装要件とするものではない。

**根拠・状態：** R7の添付文書と「NTKの最終ビジョンは本内容に沿って記述する」という指示に基づき、2026年11月20日に長期ビジョンとして採用。判断記録はADR 0010（`docs/adr/0010-project-vision.md`）。本文の「初期状態」は将来のNymphの発達開始時点を指し、Coreのみを実装するv0.xの範囲とは区別する。

**実装との関係：** 各能力の方式・配置・時期・定量的な受入条件は、段階ごとの設計・ADRで具体化する。再起動後の継続性、Self-Model、内部状態、夢の保持・失効などを、現行Coreの必須機能へ一括追加しない。ライセンスはR8・ADR 0011（`docs/adr/0011-apache-2.0-license.md`）で自作コード・Contracts・設計文書へのApache-2.0適用を採用した。v0.1.0は初期資料・開発基盤の公開である。現在の状態はREADME（`README.md`）、公開判断はrelease（`docs/release.md`）を参照する。

---

### 1. プロジェクトの目的

Nymph Toolkit（NTK）は、経験を通じて知識・言語・行動能力・人格を発達させる人工人格「Nymph」を構築するための、オープンソースのソフトウェア基盤を目指す。

最終的な目標は、**人間との継続的な交流や外部環境での経験を通じて成長し、自ら考え、学び、活動できる人工人格を実現すること**にある。

Nymphは、あらかじめ完成された知識や人格を与えられたチャットボットではない。

初期状態では限定的な能力しか持たず、ユーザーとの交流、他者の会話の観測、文章の読解、PC環境との相互作用などを通じて、徐々に能力を獲得していく。

その育成体験は、**「赤ちゃんを育てるような感覚」**を基本的な方向性とする。

ただし、人間の発達過程を生物学的に再現することが目的ではない。人工的な学習・認知・記憶・意思決定の機構を組み合わせ、経験によって変化する個体を実現することが目的である。

### 2. 最終的なNymphの姿

最終的なNymphは、次のような存在を目指す。

- 日本語を理解し、自然な会話を行える。
- 自分自身と他者を区別し、会話の文脈を理解できる。
- 経験を記憶し、過去の出来事から学習できる。
- 知らないことを認識し、自ら調査・質問できる。
- 自分の活動内容や予定を決定できる。
- PCの状況を観測し、許可された操作を実行できる。
- 経験によって行動傾向や人格特性が徐々に変化する。
- 睡眠に相当する内部処理によって経験を整理・統合できる。
- ユーザーとの関係を継続的な経験として蓄積できる。

これらの能力は、単一の巨大なAIモデルに依存して実現するのではなく、独立した機能を持つSubsystemの協調によって成立させる。

最終的なNymphは、単なる質問応答プログラムではなく、**継続した活動履歴と内部状態を持ち、経験によって行動が変化するPCアシスタント**となることを目指す。

### 3. 基本思想

#### 3.1 生得的な機構と後天的な知識

NTKでは、学習や活動に必要な基本機構を実装によって提供する。

一方、語彙、言葉の意味、世界に関する知識、好み、習慣、自己理解などは、可能な限り経験によって獲得する。

例えば、Nymphは初期状態から睡眠処理を実行する機構を持つことができる。

しかし、「眠る」という日本語の意味を最初から理解している必要はない。

内部状態と経験を通じて、後からその概念や言葉を結び付けることを目指す。

**機構を持っていることと、その機構を言語的・概念的に理解していることは区別する。**

#### 3.2 既存LLMに依存しない言語獲得

Nymphの言語理解と文章生成は、既存の大規模言語モデルを会話の中核として利用する方式ではなく、独自の学習機構によって構築することを目標とする。

これは、既存のLLMを否定するためではない。

Nymphが経験から言語を獲得する過程そのものを研究対象とするためである。

ただし、音声認識、音声合成、形態素解析、文書解析などの補助技術については、既存のライブラリやモデルの利用を許容する。

知覚技術の利用と、意味理解を外部モデルに代行させることは区別する。

#### 3.3 継続的な成長

Nymphの学習は、単発の訓練処理で完結しない。

日常的な観測、対話、行動、訂正、記憶の再利用を通じて、長期間にわたって能力を発達させる。

成長は必ずしも単調ではない。

誤った仮説を形成することも、過去の理解を修正することも、知識を忘れることもあり得る。

そのため、学習結果には根拠、不確実性、訂正可能性を持たせる。

### 4. 言語能力の最終目標

Nymphは、日本語を単なる文字列として処理するだけでなく、意味や会話の目的を理解し、状況に応じて適切に使用できることを目指す。

#### 4.1 言語の獲得経路

言語学習には、主に4つの経路を利用する。

##### Reading — 読む

テキストファイル、Markdown、Web記事などを観測し、語彙、表現、文法、文章構造を学習する。

##### Listening — 聞く

Discordの音声通話などを通じて、他者同士の会話を観測する。

初期段階ではASRによる文字起こしを活用し、音響特徴も補助的に保持する。

##### Interaction — 対話する

ユーザーとの会話によって、意味の確認、質問、模倣、発話の試行、訂正を行う。

##### Grounding — 経験と結び付ける

言葉を、PC操作、観測結果、自身の内部状態などと関連付ける。

#### 4.2 到達したい言語能力

- 日本語の語彙を獲得する。
- 文法や構文の規則性を学習する。
- 発話者・聞き手・指示対象を区別する。
- 文脈に応じて省略された情報を推定する。
- 質問、回答、説明、提案などの発話意図を理解する。
- 自分の考えや状態を文章として表現する。
- 不明な表現について質問する。
- 訂正を受け、次の会話へ反映する。

最終的には、**ユーザーがNymphの内部構造を意識せず、自然な日本語で日常的に交流できる状態**を目指す。

ただし、この能力の実現はNTKにおける最大級の研究課題であり、現在の構想だけで達成が保証されるものではない。

### 5. 記憶と知識

Nymphは、過去の経験を継続的に利用できることを目指す。

記憶は単なる会話ログの蓄積ではなく、経験、知識、手続き、根拠などを区別して管理する。

主な記憶領域は次のとおりである。

- Working Memory：現在の活動や会話の文脈
- Episodic Memory：実際に経験した出来事
- Semantic Memory：概念、知識、関係
- Procedural Memory：行動方法や技能
- Evidence / Provenance：知識の根拠と出典

また、直接観測した事実、他者から聞いた情報、自分で推論した内容、夢の中の仮想経験を混同しない。

記憶は、必要に応じて修正、統合、圧縮、忘却できることを目指す。

最終的には、Nymphが自分の過去の経験を参照し、それを現在の判断や会話へ活用できる状態を目標とする。

### 6. 自己認識

Nymphは、機能的なSelf-Modelを持つことを目指す。

これは、自分自身をほかの人物や外部環境と区別し、自分の能力、内部状態、経験、行動履歴を把握するための仕組みである。

例えば、次のような認識を可能にする。

- 自分が何を知っているか。
- 自分が何を知らないか。
- 自分が現在何をしているか。
- 自分が過去に何を経験したか。
- 自分に何ができるか。
- 自分が誰と会話しているか。
- 発話中の「私」「あなた」が誰を指すか。

自己識別のための内部機構は初期状態から存在してよいが、自己についての言語的理解や自伝的知識は経験から発達することを目指す。

なお、機能的な自己認識は、主観的な意識や感覚の存在を証明するものではない。

NTKは主観的意識の実現を完成条件とはしない。

### 7. 自律性と活動

Nymphは、外部から命令された処理を実行するだけでなく、自分の状態や目的に応じて活動を選択できることを目指す。

例えば、次のような判断を行う。

- 新しい話題について調べる。
- 不明な情報をユーザーへ質問する。
- 一定時間、学習活動を続ける。
- 指定時刻に睡眠する。
- 状況に応じて予定を変更する。
- 実行中の活動を中断・再開する。

これらの活動内容、時刻、期間、優先度、変更の判断はNymph側が担当する。

Coreは、その決定を受けて実行管理を行う。

**Nymphが意思決定し、Coreが実行を管理する。**

この責務分離を基本原則とする。

### 8. 内部状態・動機・情動

Nymphには、活動選択に影響する内部状態を持たせる。

検討している状態には、睡眠圧、認知負荷、不確実性、刺激量、社会的交流状態などがある。

これらの状態から、休息、探索、問題解決、交流、安定化などの動機が形成される。

複数の動機が競合する場合は、現在の状況、目的、人格特性などを考慮して行動を選択する。

情動は短期的に変化する状態として扱い、長期的な人格特性とは区別する。

これらは人工的な制御・評価機構であり、人間の生理的欲求や感情と同一であることを前提としない。

### 9. 人格形成

Nymphは、長期的に変化する人格特性を持つことを目指す。

初期の検討対象には、好奇心、慎重さ、社交性、粘り強さ、新規性への選好、表現性などがある。

人格は、日々の経験によって少しずつ変化する。

ただし、瞬間的な情動変化によって長期人格が頻繁に書き換わる構成にはしない。

現在の設計案では、Persona Subsystemが人格特性を保持し、外部から与えられた修正値を検証・適用する。

Persona自身は人格修正を自発的に開始しない。

長期人格の変化は、原則としてSleepによる経験統合の結果を反映する方式を想定する。

最終的には、同じ基本機構を持つNymphであっても、経験の違いによって異なる行動傾向や人格を形成することを目指す。

### 10. 睡眠と夢

Nymphには、活動中に蓄積された経験を整理するための睡眠機構を設ける構想である。

睡眠は、単なる処理停止ではない。

記憶統合、知識の再評価、忘却、夢生成、人格更新などを行う内部処理として位置付ける。

睡眠の開始時刻や期間は、Nymph自身の判断によって決定されることを目指す。

夢は、過去の経験の再演、記憶の自由な再結合、将来の状況の仮想的な予行などを含む。

ただし、夢で起きた出来事を現実の経験として扱わない。

また、夢そのものが長期人格を直接変更する構成にはしない。

夢の内部記憶は次の睡眠時に失効させる方針である。

一方、夢についてユーザーと実際に会話した場合、その会話は通常の現実の経験として扱う。

### 11. PCアシスタントとしての最終目標

Nymphは、最終的にユーザーのPC環境で活動できるアシスタントとなることを目指す。

そのため、外部環境との接続にはAdapterを利用する。

想定する接続対象には、次のようなものがある。

- テキスト・文書
- Web
- Discord音声通話
- PCのウィンドウやプロセス
- ファイルシステム
- ユーザーとの対話インターフェース

これらの名称や構成は暫定であり、今後変更される可能性がある。

Nymphは、Adapterから得られる情報によって外部環境を観測し、許可された範囲で操作できるようになる。

例えば、ユーザーの作業を妨げないよう活動を調整したり、必要な情報を調査したり、許可されたPC操作を実行したりすることを目指す。

ただし、操作可能であることと、操作が許可されていることは別である。

外部環境への操作には、明示的な権限管理と必要に応じたユーザー承認を設ける。

### 12. Nymph Toolkitのアーキテクチャ

NTKは、Coreを中心としてSubsystemを接続し、その総体によってNymphを構成する。

外部環境との接点は、任意に接続されるAdapterが担当する。

### Core

Coreは、主に次の機能を提供する。

- Runtime
- Registry
- Connections
- TaskManager

Coreは、Nymphの知識や人格を直接実装しない。

また、Nymphの活動内容や目的を自律的に決定する主体にもならない。

### Subsystem

Subsystemは、記憶、認知、意思決定、人格、睡眠などの内部能力を実装する。

現在検討している名称は次のとおりである。

- Memory
- Cognition
- Agency
- Persona
- Sleep

これらの名称および責務境界は、今後の設計によって変更される可能性がある。

### Adapter

Adapterは、Nymphと外部環境の入出力を担当する。

CoreはSubsystem・Adapterの接続と実行環境を管理する。

実行方式は、同一プロセスでの軽量なPythonメソッド呼び出しと、必要に応じた別プロセス実行を組み合わせるハイブリッド方式を採用する。

R12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）により、Coreが管理・許可した接続で直接通信を認める。Core経由の通信も利用できる。許可範囲・API・解除時の動作などの詳細は対象の実装前に判断し、旧来のCore経由のみという判断はADR 0003（`docs/adr/0003-communication-routing.md`）の履歴として保持する。この採用は長期ビジョンを変更するものではない。

配布は単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterを必要に応じて分割する。ADR 0009（`docs/adr/0009-package-distribution.md`）の採用方針に従い、名称・分割対象・時期は個別に判断する。

### 13. 開発ロードマップとの関係

NTKは、基盤の完成と人工人格の能力開発を段階的に進める。

| 段階 | 目標・主目的 | 状態 |
|---|---|---|
| v0.1.0 | GitHub公開 | 確定目標 |
| v0.9.0 | 合意したCore機能の完成 | 確定目標 |
| v1.0.0 | Subsystem・Adapterとの接続契約を大きく形作る | 確定目標。契約詳細は要決定 |
| v1.1.0以降の奇数マイナー | 新規Subsystemの実装 | 運用案・未採用 |
| v1.2.0以降の偶数マイナー | 連携強化・Adapterの実装と拡張 | 運用案・未採用 |
| パッチリリース | 個別修正・互換性を維持する改善 | 運用案。APIの互換性と採番は別途判断 |

v1.x以降の具体的なSubsystem実装順序や機能配分は、現時点では提案である。必要な補助実装・統合テストは各段階に含められ、偶数マイナーの新規Adapter追加は必須としない。詳細はroadmap（`docs/roadmap.md`）とADR 0007（`docs/adr/0007-v1-release-roadmap.md`）を参照する。

最終的な人工人格の完成は、特定のバージョン番号に固定しない。

開発の進展に応じて、能力の到達基準と研究課題を更新する。

### 14. 最終目標の評価基準

Nymphの最終的な到達度は、単に実装された機能の数ではなく、次の観点から評価する。

| 評価領域 | 到達目標 |
|---|---|
| 言語 | 自然な日本語で継続的に会話できる |
| 学習 | 新しい語彙・知識・規則を経験から獲得できる |
| 記憶 | 過去の経験を保持・検索・再利用できる |
| 自己認識 | 自己と他者、内部状態、能力を区別できる |
| 自律性 | 自分で活動を計画し、実行・変更できる |
| 人格 | 経験によって安定的かつ緩やかに変化する |
| 睡眠 | 経験を統合・再評価し、必要な忘却を行える |
| PC操作 | 権限の範囲で外部環境を観測・操作できる |
| 継続性 | 再起動後も記憶や発達状態を維持できる |
| 安全性 | 権限・承認・実行制約を守れる |

これらは最終的な評価領域であり、定量的な合格基準は今後の研究・実装を通じて定義する。

### 15. 対象外とする事項

現時点では、次の事項を初期開発の必須要件としない。

- 人間の脳や生理機構の厳密な再現
- 主観的意識の存在の証明
- 既存LLMと同等の汎用性能を初期段階から達成すること
- 人格データや記憶の複製・移植・伝播機構
- すべての外部サービスとの接続
- 完全に自律した無制限のPC操作

特に、複製・移植・伝播については、必要になった段階で各Subsystemに出力処理を追加し、伝播用資産を整備する長期構想とする。採否・方式・時期は後続判断とし、初期Coreの要件には加えない。

これらの機能を実現するために、初期のCoreを過度に複雑化させない。

### 16. プロジェクトの最終的な意義

NTKの目標は、単に便利なAIアシスタントを作ることではない。

**経験によって知識を獲得し、内部状態を持ち、自分で活動を選び、長期的に変化する人工人格を、理解可能なソフトウェア機構として構築すること**にある。

そのため、Nymphの学習、推論、行動、人格変化を可能な限り観測・検証できる設計を重視する。

また、SubsystemとAdapterを組み合わせる構成によって、特定の外部サービスや単一のAIモデルに依存しない開発基盤を目指す。

最終的なNymphは、最初から何でも知っている存在ではない。

知らないことを知り、理解できなかったことを理解し、失敗から学び、ユーザーとの経験を重ねながら、自分自身の能力と行動傾向を発達させていく存在である。

---

### Vision Statement

**Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格である。**

**Nymph Toolkitは、その成長を可能にする仕組みを、独立したSubsystemとAdapterから構築するためのオープンソース基盤を目指す。**

---

<a id="section-6"></a>

収録元 `docs/architecture.md`

## Architecture

### 最終ビジョンとの関係

NTKは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格Nymphを支える基盤を目指す。Project Vision（`docs/vision.md`）を長期目標の本文とし、ADR 0010（`docs/adr/0010-project-vision.md`）で現在の実装範囲との関係を記録する。

記憶・言語獲得・機能的な自己認識・活動選択・人格・睡眠はNymph側の長期能力として扱う。内部状態・動機・情動やSelf-Modelの具体的な配置は未決であり、Coreへ認知・価値判断を追加する根拠にしない。再起動後の記憶・発達状態の維持は長期目標で、Coreの永続化方式と実装時期は別途判断する。

言語理解・文章生成の中核を既存LLMに代行させず、経験からの獲得過程を研究する。ASR・音声合成・形態素解析・文書解析などの補助技術は利用を許容する。PC環境の観測・操作は将来のAdapterを通じ、明示的な権限管理と必要に応じた承認を設計する。Desktop Adapterの時期や権限管理の配置・APIは未決である。

### 採用された構成

v0.2でRuntime、v0.3でRegistry・ModuleGroupと必要なContractsを実装した。Runtimeの使い方（`docs/runtime.md`）とRegistryの使い方（`docs/registry.md`）、ADR 0014・0016にライフサイクル、登録・依存管理、失敗通知と後処理を記録する。Connections・TaskManagerと本番Subsystem・Adapterは今後の段階で扱う。

Coreを中心にSubsystem・Adapterを着脱する構成と、Core Runtime・Registry・Connections・TaskManagerの4責務は確定している。初期実装の対象はCoreで、Nymph・Subsystem・Adapterの役割は検証用ダミーで再現する。根拠はR2、判断記録はADR 0001・0005。

| 構成要素 | 責務の整理 | 採用状況・今後具体化する点 |
|---|---|---|
| Core Runtime | Coreの起動、実行、停止を取りまとめる | ADR 0014のRuntimeとADR 0016のModuleGroupを実装 |
| Registry | Subsystem・Adapterの登録状態と識別を管理する | ADR 0016でID・必須依存・スナップショット・着脱範囲を採用して実装 |
| Connections | 採用した経路で接続と通信を管理する | 通信経路ADR、要求と結果、同期・非同期境界、失敗通知 |
| TaskManager | Nymphが決めた活動の予定、実行状態、変更を管理する | 時刻・期間、状態遷移、変更や取消、競合の扱い |
| Subsystem | 着脱する機能単位 | Coreとの接続契約とライフサイクル |
| Adapter | 外部環境との接点を担う着脱可能な構成要素 | 接続契約。将来のPC状況取得はここに配置 |

4責務の採用と、上表の詳細なAPI分担は別々に状態を管理する。TaskManagerの活動決定権に関する境界は確定事項である。

R13のv0.3実施に伴い、登録・ID単位の必須依存・変更結果の通知・不変スナップショットをADR 0016（`docs/adr/0016-v0.3-registry.md`）で具体化する。Runtime側のModuleGroupが複数のダミーを一つのRuntimeServiceとして束ね、依存順の初期化と逆順の後処理を行う。Registryのavailableは登録された依存先の有無を表し、実行状態や通信許可とは区別する。実体の着脱は実行前に行い、起動から停止完了まで構成を固定する。稼働中の実体交換はConnectionsの解除・失効契約と合わせて後続で判断する。

### 活動と実行の境界

Nymphが活動内容・時刻・期間・変更を決め、Coreが実行管理を担う。例えばNymph役のダミーが活動A、開始時刻T、期間Dを指定し、その後に期間をD2へ変更する。Coreで入力、予定、実行結果を照合する。このT・D・D2は検証用の値で、既定値や公開APIの型は要決定である。

活動の価値評価、睡眠・調査の選択、人格に基づく優先度の生成はNymphが担う。Coreは指定時刻の監視、実行状態の追跡、変更要求の適用可否の判定、実行上の競合や障害の通知を担う。優先度・実行枠を採用する場合、Nymphが入力した優先度と採用済み規則に従って、Coreが実行枠の割り当てや待機順序を機械的に処理する。優先度機能、枠数、割り当て方式、同順位の処理は要決定である。根拠はR2・R4、詳細はADR 0004。

Coreが管理する活動状態はNymph自身の活動を対象とする。外部アプリの稼働状況は将来のAdapterが取得する。認知・学習アルゴリズムはCoreの実行管理の範囲外とする。タイムアウトの条件や障害通知の契約は実装前に判断する。

ダミーの役割は、Nymphの決定を入力するもの、活動を実行して結果を観測できるもの、Adapterの装着を模擬するものとする案を用いる。Nymphの配置先や継承関係は未確定である。

### 時間管理で具体化する概念

以下はR4を受けた用語整理案である。V0.5で意味・計測条件を決め、V0.6の変更や中断・再開の判断に引き継ぐ。

| 概念 | 整理案 | 判断する内容 |
|---|---|---|
| 時刻 | 開始などの時点 | タイムゾーン、時計の補正、指定時刻と実際の開始の関係 |
| 期間 | Nymphが指定する活動の長さ | 終了判定にどの時間を使うか、期間満了の動作 |
| 経過時間 | 基準時点からの時間差 | 基準時点、待機・中断を含めるか、使用する時計 |
| 実行時間 | 実際に活動を実行した時間の累積を候補とする | 開始・停止の計測点、中断分、CPU時間との関係 |

開始時刻の繰り上げ・延期、期間の延長・短縮、優先度変更、中断・再開、取消・終了はV0.6で採否を明示する。具体的な計時方法や対応機能は未確定である。

### Subsystemの独立性の整理案

着脱は確定方針である。R4の整理案を受け、R13・ADR 0016でID単位の必須依存を採用した。具体的な相手実装への依存を避け、依存先不在・解除による利用不能を変更結果として通知する。単体での完全動作や代替機能の提供は必須条件にしない。

Registry単独では依存先解除を許可する。ModuleGroupでは起動から停止完了まで構成変更を拒否する。進行中の通信・活動に関わる実体着脱と、Capability単位の依存などは後続判断に残す。データの複製・移植は初期スコープ外である。履歴はADR 0001、現在の採用範囲はADR 0016を参照する。

### 実行配置と通信経路

ハイブリッド実行は確定方針であり、同一プロセスと別プロセスの配置を想定する。Python `asyncio` と軽量なメソッド呼び出しは方向性確定。Core経由の処理もメソッド呼び出しで構成できる。

R12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）により、Coreが管理・許可した接続でSubsystem間の直接通信を認める。Coreは接続の管理・許可を担い、許可した直接経路の通信ごとにCoreを経由することは必須としない。Core経由のみという旧判断はADR 0003に履歴として保持する。

Coreによる毎回の呼び出しも利用できる。Proxy、直接参照、ストリーム等の具体的な方式、接続元・先、許可条件、状態把握、解除・許可撤回と通信中の処理は実装前に決める。Registryへの登録・照会や軽量なメソッド呼び出し方式を、直接通信の許可と同一視しない。Adapter経路や直接音声ストリームへの個別適用は未決である。

配置間で通信契約を共通化するか、その共通範囲、IPC方式、シリアライズ方式、同期・非同期境界は要決定。別プロセス対応をV0.7で実装する配分は提案である。

### v1.0.0以降の構成案

R5でv1.0.0の目標として、CoreとSubsystem・Adapterの接続契約を大きく形作ることを追加する。v0.9.0のCore完成を踏まえ、Module、Lifecycle、Capability、Communication、Task、Errorの各Contractを検討する。公開API、接続用の開発補助機能、ダミーによる契約テストを整備する案で、本番Subsystemの完成は必須条件としない。具体的な契約はADR 0006（`docs/adr/0006-core-connection-contracts.md`）で判断対象を管理する。

以下はv1.xの設計提案で、Subsystem名・Adapter名はすべて暫定名称である。実装順序、各バージョンへの機能配分、契約の型やAPIは未確定。Subsystem・Adapter向けの共通接続契約を作る目標から、配置間のIPC統一や直接通信の許可を推定しない。

| 構成案 | 役割と境界 |
|---|---|
| MemoryとDocument Adapter | 経験・知識の最小保存・取得と文書入力。複雑な知識グラフ・高度な記憶統合は初期の必須条件にしない |
| CognitionとText Interaction / Web Adapter | 語彙・構文・概念の初期学習、文章観測・出力・ユーザー訂正。既存LLMを言語理解・文章生成の中核とする方式は現在の研究方針に含めない |
| AgencyとTaskManager | AgencyがNymph側の活動内容・開始時刻・期間・優先度・変更を決め、Coreが登録・実行・状態追跡・変更要求の適用を担当 |
| PersonaとAgency | Personaが人格特性を保持・返却し、外部の修正値を契約に沿って適用する。自発的な人格修正の開始は行わず、Agencyが参照した特性を行動選択へ反映 |
| SleepとMemory・Persona | 経験統合・忘却・夢・人格修正値の生成を段階的に検討。Personaへ接続契約を通じて修正値を渡し、内部状態を直接変更しない基本案 |
| Discord Voice Adapter | 他者同士の音声会話の観測。ASRによる文字起こしと音響特徴の併用を基本案とする |
| Desktop Adapter | PC全体の稼働状況取得・操作の将来候補。v1.10.0までの配分外 |

各連携はADR 0015と後続判断による採用経路を使う。Discord音声の取得・保存・学習は告知、適切な同意、権限、保持・削除方針を設計時に扱う。名称・順序・配分と検証範囲の判断はADR 0007（`docs/adr/0007-v1-release-roadmap.md`）、研究方針・責務・音声の扱いはADR 0008（`docs/adr/0008-subsystem-adapter-boundaries.md`）に記録する。複製・移植・伝播機構は初期開発の対象外である。

### 配布方針とフォルダ構成

R6で、単一リポジトリを維持し、CoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて分割する方針を採用した。ADR 0009（`docs/adr/0009-package-distribution.md`）に判断を記録する。

配布パッケージはインストール・配布の単位を指す。ルートの `pyproject.toml` でCoreとContractsを同梱し、ソース上では `src/nymph_toolkit/core/` と `src/nymph_toolkit/contracts/` に分ける。ADR 0014で配布名を `nymph-toolkit`、import名を `nymph_toolkit` として採用した。

ContractsにはCoreと接続側が共有する契約を、v0.xの実装で必要なものから配置する。v1.0.0で公開接続契約として体系化する。依存方向の設計案として、Core・Subsystem・Adapterが公開Contractsを参照し、Contractsを具体的な実装から独立させる。契約の型やAPIはADR 0006で具体化する。

#### 初期の配置

文書・Git設定・Apache-2.0の `LICENSE` に加え、v0.2で `pyproject.toml`、`src/`、`tests/`、ダミー例、検証ツールとCIを配置した。自作コード・Contracts・設計文書へのライセンス適用はADR 0011（`docs/adr/0011-apache-2.0-license.md`）に従う。

```text
nymph-toolkit/
├─ README.md
├─ CONTRIBUTING.md
├─ AGENTS.md
├─ .gitignore
├─ .gitattributes
├─ LICENSE
├─ CHANGELOG.md
├─ pyproject.toml
├─ requirements-dev.txt
├─ .github/workflows/ci.yml
├─ examples/runtime_demo.py
├─ examples/registry_demo.py
├─ tools/check_dist.py
├─ tools/check_docs.py
├─ tools/build_handoff.py
├─ docs/
│  ├─ README.md
│  ├─ NTK-Core-v0.1-Handoff-ja.md
│  ├─ vision.md
│  ├─ architecture.md
│  ├─ runtime.md
│  ├─ registry.md
│  ├─ roadmap.md
│  ├─ acceptance.md
│  ├─ validation/v0.2.md
│  ├─ validation/v0.3.md
│  ├─ development.md
│  ├─ issue-workflow.md
│  ├─ release.md
│  └─ adr/
│     ├─ README.md
│     ├─ 0001-core-and-repository.md
│     ├─ 0002-execution-model.md
│     ├─ 0003-communication-routing.md
│     ├─ 0004-activity-authority.md
│     ├─ 0005-initial-scope.md
│     ├─ 0006-core-connection-contracts.md
│     ├─ 0007-v1-release-roadmap.md
│     ├─ 0008-subsystem-adapter-boundaries.md
│     ├─ 0009-package-distribution.md
│     ├─ 0010-project-vision.md
│     ├─ 0011-apache-2.0-license.md
│     ├─ 0012-v0.1-publication.md
│     ├─ 0013-milestone-issue-workflow.md
│     ├─ 0014-v0.2-runtime.md
│     ├─ 0015-core-authorized-direct-communication.md
│     └─ 0016-v0.3-registry.md
├─ src/
│  └─ nymph_toolkit/
│     ├─ core/
│     └─ contracts/
└─ tests/
   ├─ core/
   └─ doubles/
```

R3の配置案をR11・R13の実装に合わせて具体化した。Runtimeは `core/runtime.py`、Registryは `core/registry.py`、複数対象の実行入口は `core/module_group.py` に置く。契約は `contracts/__init__.py` と `contracts/registry.py`、ダミーは `tests/doubles/`、検証は `tests/core/` に置く。Connections・TaskManagerのモジュール・APIはその実装時に判断する。

#### Subsystem・Adapterを追加する際の配置案

同梱する場合と、別配布にする場合の例を以下に示す。将来の配置・名称は提案であり、個別の分割を決定したものではない。

| 扱い | ソースの配置例 | 配布設定・検証の配置例 |
|---|---|---|
| 初期配布物へ同梱するSubsystem | `src/nymph_toolkit/subsystems/<名称>/` | ルートの `pyproject.toml`、`tests/subsystems/` |
| 初期配布物へ同梱するAdapter | `src/nymph_toolkit/adapters/<名称>/` | ルートの `pyproject.toml`、`tests/adapters/` |
| 別配布にするSubsystem・Adapter | `packages/<配布ディレクトリ>/src/<import名>/` | 対象ディレクトリ内の `pyproject.toml`、`tests/` |

別配布の場合も同じ `nymph-toolkit` リポジトリで管理する。CoreとContractsは初期のルート配下を基準とし、分割対象ごとに依存関係、Core・Contractsの対応バージョン、公開import名、ビルド・検証手順を記録する。共有の設計・ADRは引き続き `docs/` と `docs/adr/` に置く。

依存ライブラリや対応OS、更新頻度、単独導入の必要性を基に分割を判断する。任意依存による同梱も比較対象とし、分割後のバージョンを同期するか独立させるかは後続ADRで決める。配布単位は実行プロセスと通信経路を決定しない。同梱・別配布のいずれも、実行配置はADR 0002、通信経路はADR 0015と後続判断に従う。

### 実装前の判断一覧

R10・ADR 0013（`docs/adr/0013-milestone-issue-workflow.md`）により、コード変更前に対象バージョンのマイルストーン、親Issue、対応単位の子Issueを整備する。以下の設計判断は対象のIssueから追跡し、必要な判断を記録してから実装へ進む。具体的な運用はissue-workflow.md（`docs/issue-workflow.md`）を参照する。

| 判断 | 判断する時点の案 | 記録先 |
|---|---|---|
| Python対応版、配布パッケージの正式名称、ビルド・テストツール、Runtimeのライフサイクル | v0.2で採用済み | development、ADR 0014 |
| Subsystem・Adapterの同梱・分割対象、任意依存、公開import名、バージョン管理 | 各対象の実装・配布を設計する時点 | ADR 0009に関連付ける後続ADR |
| 登録ID、重複、必須依存・解除による利用不能の通知、スナップショット、ModuleGroup | v0.3で採用。稼働中実体着脱は延期 | ADR 0016 |
| Coreが許可する直接通信の採否 | R12で採用済み | ADR 0003の履歴とADR 0015 |
| 経路別の許可条件・API、接続状態と解除・許可撤回の具体的な扱い | Connectionsの対象経路の実装前 | ADR 0015と後続ADR |
| 呼び出し契約、同期・非同期境界、失敗通知 | V0.4着手時 | 後続ADR |
| 時計、時刻・期間・経過時間・実行時間の意味、状態遷移、期間終了の意味 | V0.5着手時 | ADR 0004に関連付ける後続ADR |
| 繰り上げ・延期、期間変更、優先度変更、中断・再開、取消・終了の採否、競合と取り外し | V0.6着手時 | ADR 0004と後続ADR |
| IPC、配置間契約の共通範囲、切断時処理 | V0.7着手時 | ADR 0002に関連付ける後続ADR |
| 永続化、再試行、自動復旧の必要性と採否 | 必要な設計段階、遅くともV0.8の検証範囲確定前 | 後続ADR |

未決項目は担当する段階で具体化する。決定記録には採用内容、理由、適用範囲と検証への影響を残す。

v1.xでは、各Contractの公開範囲・互換性、Subsystemの正式名称と学習・意思決定方式、Adapterの対応形式と権限、Personaへの修正値、Sleepの処理範囲、音声受信・ASRの実現方法を追加の判断対象とする。具体化はroadmapとADR 0006〜0008に従う。

---

<a id="section-7"></a>

収録元 `docs/runtime.md`

## v0.2 Runtimeの使い方

Runtimeは、一つの実行入口を同一プロセスで起動・実行・停止する。v0.2の仕様判断はADR 0014（`docs/adr/0014-v0.2-runtime.md`）、環境構築と検証はdevelopment（`docs/development.md`）にある。v0.3ではこのAPIを維持し、ModuleGroup（`docs/registry.md`）を実行入口にして複数対象を動かせる。Connections・TaskManager、別プロセス実行はまだ含まない。

### 実行例

インストール済みのPythonでダミー例（`examples/runtime_demo.py`）を実行する。

```powershell
.venv/Scripts/python.exe examples/runtime_demo.py
```

正常時には次を表示する。

```json
{"state": "stopped", "result": "dummy-result", "events": ["start", "run", "stop"], "remaining_tasks": 0}
```

利用側はRuntimeServiceの三つの非同期メソッドを実装する。継承は必須ではなく、同じ契約を満たすオブジェクトを渡せる。

```python
import asyncio
from nymph_toolkit.core import Runtime

class Service:
    async def start(self):
        pass  # 初期化

    async def run(self):
        await asyncio.sleep(0)
        return "completed"

    async def stop(self):
        pass  # 部分初期化も考慮してリソースを解放

async def main():
    runtime = Runtime(Service())
    await runtime.start()
    try:
        print(await runtime.wait())
    finally:
        await runtime.stop()

asyncio.run(main())
```

イベントループは利用側が用意する。既存のasyncioアプリでは、そのループ内からstart・wait・stopをawaitする。Runtimeはループの作成や終了、活動内容の選択を行わない。

### 公開インターフェース

| import | 用途 |
|---|---|
| `nymph_toolkit.core.Runtime` | 一回のライフサイクルを管理する。start、wait、stopとstateを公開 |
| `nymph_toolkit.contracts.RuntimeService` | start・run・stopを定義する型契約 |
| `RuntimeState` | NEW / STARTING / RUNNING / STOPPING / STOPPED / FAILED |
| `RuntimeFailure`、`LifecycleFailure`、`LifecyclePhase` | 初期化・実行・後処理の失敗通知。後二者と例外はcontractsからimport |
| `RuntimeStateError` | 二重起動、別ループからの制御、自己待機などの不正な操作 |

waitはrunの結果を返す。停止要求によってrunがキャンセルされた場合はNoneである。自然終了と停止のどちらでも、初期化を開始していればstopを一度呼び出す。waitとstopは後処理まで待つ。インスタンスは再起動せず、次の実行には新しいRuntimeを作る。

開始・実行の失敗も後処理を経てFAILEDとなる。RuntimeFailure.failuresにはphaseと元例外が順に保持される。例えばrunとstopが両方失敗しても、runの原因は失われない。後からstopやwaitを再度呼んだ場合も失敗を通知する。タスク生成そのものの失敗は初期化失敗として通知し、サービスのフックは呼ばない。

### 停止とキャンセル

stopは実行中または初期化中の処理へキャンセルを要求する。後処理中の重複stopで後処理を再キャンセルしない。サービスが自分で作ったタスクや接続は、そのサービスのstopが終了させる。Runtimeは無関係な呼出側タスクを停止しない。

waitを待つ側がキャンセルされてもサービスは実行を続ける。startを待つ側がキャンセルされた場合は停止を要求する。stopを待つ側がキャンセルされても後処理は継続する。必要に応じて再びstopまたはwaitをawaitして、終了を確認する。

キャンセルに応答しないサービスは強制終了できない。待機の期限は呼出側でasyncio.timeoutを使って設定できるが、TimeoutErrorはRuntimeの停止完了を意味しない。ブロッキングI/OやCPU処理をそのままイベントループへ置かない。

### 適用範囲

RuntimeServiceはv0.2の実行入口であり、Subsystem・Adapterの登録や通信の契約全体ではない。APIは初期開発中であり、v1.0の公開契約へ向けて変更を判断する。活動の開始時刻・期間・優先度や価値判断をRuntimeへ追加しない。

---

<a id="section-8"></a>

収録元 `docs/registry.md`

## RegistryとModuleGroup

v0.3の採用契約はADR 0016（`docs/adr/0016-v0.3-registry.md`）に記録する。実装・公開の状態はREADME（`README.md`）を参照する。CoreとContractsは一つのパッケージに含める。

実行例は examples/registry_demo.py（`examples/registry_demo.py`）。インストール後に `python examples/registry_demo.py` を実行すると、ダミーAdapterとSubsystemの登録、依存先の追加・解除による変更通知、依存順の初期化・逆順の後処理、残存タスク0件を確認できる。ダミーの名称は将来の本番Subsystem・Adapterの実装を示すものではない。

### 登録情報と依存関係

`nymph_toolkit.core.Registry` に `nymph_toolkit.contracts.ModuleSpec` を登録する。ModuleKind.SUBSYSTEMとModuleKind.ADAPTERを同じ契約で扱う。IDは利用側が指定する、前後空白のない空でない文字列である。

| 操作・情報 | 契約 |
|---|---|
| `ModuleSpec(module_id, kind, requires=frozenset())` | 不変の登録情報。requiresをID集合へコピー。自己依存はRegistryで拒否 |
| `registry.register(spec)` | 登録しRegistryUpdateを返す。重複・循環は変更せず拒否 |
| `registry.unregister(module_id)` | 解除しRegistryUpdateを返す。未登録IDは変更せず拒否 |
| `registry.get(module_id)` | 不変のRegistryEntry。実体や通信ハンドルは返さない |
| `registry.entries()` | ID順のEntryのtuple |
| `registry.revision` | 成功した変更の通し番号。失敗では進めない |
| `entry.generation` | 登録時のrevision。同じIDの再登録を区別できる |
| `entry.available` | 推移的な不足依存がないこと。稼働状態・正常性・通信許可を意味しない |
| `entry.missing_dependencies` | 直接・間接に不足しているIDのfrozenset |
| `update.changes` | ID順のRegistryChange。before/afterは変更前後のEntry。登録前・解除後はNone |

依存先が未登録でも登録できる。不足先を登録すれば利用可能となり、解除すれば依存元が利用不能になる。その変化は操作結果に同梱して通知する。継続購読や通知の永続保存は提供しないため、利用側は返された変更結果を処理する。

すべての操作はRegistryを作成したスレッドで呼ぶ。awaitやコールバックは含まれない。返されたスナップショットは後続の登録・解除で書き換わらない。最新情報は再照会する。

### Runtimeから複数対象を動かす

`nymph_toolkit.core.ModuleGroup` に、ModuleSpecとRuntimeServiceを満たすダミーを `register(spec, service)` で登録する。ModuleGroupを既存の `Runtime(group)` に渡し、通常のstart・wait・stopで制御する。

ModuleGroupのregister・unregister・get・entries・revisionはRegistryと同じ情報を扱う。実体は内部に保持し、外部へ返さない。不足依存があれば初期化を始める前に失敗する。依存順（同順位はID順）にstartし、全初期化が成功してから各runをタスクとして実行する。正常時はwaitがID別の戻り値を返す。

startに入ってからstopの完了まで構成を固定する。この期間の登録・解除はRegistryStateErrorとする。実体の稼働中着脱はConnectionsの解除・失効契約を扱う後続段階へ延期する。停止後も登録情報は残り、明示的にunregisterできる。開始後の追加登録と再起動は拒否し、再実行には新しいModuleGroupとRuntimeを使う。

### 失敗と後処理

RegistryErrorの派生としてDuplicateModuleError、UnknownModuleError、DependencyCycleError、DependencyUnavailableError、RegistryStateErrorを使う。不正な型・IDはTypeError／ValueErrorで通知する。

ModuleGroup内のサービス失敗は、対象ID・LifecyclePhase・元例外を持つModuleFailureへ記録し、ModuleGroupFailureにまとめる。外側のRuntimeFailureの各LifecycleFailure.exceptionから確認できる。初期化失敗時も、その対象を含めて初期化に入った順の逆順でstopする。実行中の失敗は他対象の停止につながり、複数失敗も保持する。

呼出側の取消・Runtimeの状態・停止完了はRuntimeの契約（`docs/runtime.md`）に従う。ModuleGroupが作るタスクを完了させ、サービスのstopは各サービスが所有するタスク・接続を終了させる。stopの通常の失敗があっても他対象の後処理を続ける。無関係な呼出側タスクは停止しない。

初期化中のCancelledErrorはRuntimeへそのまま伝播し、対象IDを例外のnoteへ残す。停止要求による取消と予期しないサービス側取消の区別を既存Runtimeに委ねるためである。ModuleGroupのライフサイクルメソッドは一つのRuntimeの監督タスクから呼び、別Runtimeで同じGroupを同時に実行しない。

### 通信・活動管理との境界

ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）でCoreが管理・許可した直接通信は採用済みである。Registryの登録・照会は通信の許可操作ではなく、v0.3ではConnections・許可API・直接通信を実装しない。依存IDの宣言も、他の具体的実装への参照を与えるものではない。

Nymphが活動を決定し、Coreが実行管理する。ModuleGroupのライフサイクル管理に、活動の価値評価・時間指定・優先度生成を追加しない。

---

<a id="section-9"></a>

収録元 `docs/adr/README.md`

## ADR索引と更新方法

ADRは設計判断の根拠と履歴を保存する。初稿の記録日は2026年11月19日。元会話内での決定日は未確認である。R1〜R13の説明はDocsの根拠表（`docs/README.md`）にある。

| ADR | 状態 | 根拠 |
|---|---|---|
| 0001 Coreと統合リポジトリ（`docs/adr/0001-core-and-repository.md`） | 基本構成は確定。独立性整理案のv0.3採用範囲は0016、配布方針は0009、ライセンスは0011で具体化 | R2・R3・R4・R6・R8・R13 |
| 0002 実行モデル（`docs/adr/0002-execution-model.md`） | ハイブリッドは確定、Python asyncio・軽量なメソッド呼び出しは方向性確定 | R2・R5 |
| 0003 通信経路（`docs/adr/0003-communication-routing.md`） | 当初判断の履歴。Core経由のみという制約と緩和の未採用状態は0015で置換 | R2・R4・R5・R12 |
| 0004 活動の決定権（`docs/adr/0004-activity-authority.md`） | 決定権の境界は確定。時間・優先度・変更操作の具体策は要決定 | R2・R4・R5 |
| 0005 初期実装の範囲（`docs/adr/0005-initial-scope.md`） | 確定。R5で適用段階と伝播機構の除外を補足 | R2・R3・R5 |
| 0006 v1.0.0のCore接続契約（`docs/adr/0006-core-connection-contracts.md`） | 目標は確定。契約詳細・公開API・補助機能・契約テストは提案・要決定。初期配布は0009で採用 | R5・R6 |
| 0007 v1.x以降のリリース運用と開発順序（`docs/adr/0007-v1-release-roadmap.md`） | 提案・未採用。名称・順序・機能配分は暫定。配布方針の後続判断を0009へ参照 | R5・R6 |
| 0008 v1.xのSubsystem・Adapter責務案（`docs/adr/0008-subsystem-adapter-boundaries.md`） | 設計提案。R5の研究方針・責務境界を前提とし、R7の長期構想を補足 | R5・R7 |
| 0009 単一リポジトリと段階的な配布パッケージ分割（`docs/adr/0009-package-distribution.md`） | 採用。CoreとContractsを同梱して開始し、Subsystem・Adapterを必要に応じて分割。ライセンスは0011で採用 | R6・R8 |
| 0010 Nymphの最終ビジョンと実装範囲の区別（`docs/adr/0010-project-vision.md`） | 長期ビジョンとして採用。具体的な実装方式・時期・受入条件は後続判断。ライセンスは0011で採用 | R7・R8 |
| 0011 自作コード・Contracts・設計文書へのApache-2.0適用（`docs/adr/0011-apache-2.0-license.md`） | 採用。第三者成果物と個体データの条件は別途扱う | R8 |
| 0012 個人アカウントでのv0.1.0公開と参加方針（`docs/adr/0012-v0.1-publication.md`） | 採用。Tao-pyth配下で資料を中心にpublic公開し、参加方針・v0.1.0を整える | R9 |
| 0013 マイルストーン・親子Issueを前提とするコード変更（`docs/adr/0013-milestone-issue-workflow.md`） | 採用。マイルストーン、親Issue、対応単位の子Issue登録後にコード変更へ着手 | R10 |
| 0014 v0.2の開発環境と最小Runtime（`docs/adr/0014-v0.2-runtime.md`） | R11の実施に伴う実装判断として採用。Python・配布・Runtimeライフサイクル・失敗と後処理を具体化 | R11・#22 |
| 0015 Coreが許可する直接通信の採用（`docs/adr/0015-core-authorized-direct-communication.md`） | 採用。Coreが管理・許可した接続で直接通信を認める。許可範囲・API・解除時の動作等は要決定 | R12・#34 |
| 0016 v0.3のRegistryと複数対象のライフサイクル（`docs/adr/0016-v0.3-registry.md`） | R13の実施に伴う実装判断として採用。登録・スナップショット・必須依存・変更通知・ModuleGroupを具体化。稼働中実体着脱は延期 | R13・#27 |

### 記録方法

各ADRに背景、状態、決定、影響、未決事項、根拠を記載する。新しい判断は次の連番のファイルに記録し、関連する既存ADRから参照する。案の段階では「提案」または「要決定」と表記し、採用時に採用日・判断者・適用範囲を記録する。

採用済み判断を変更する場合は旧内容と根拠を残し、新しいADRへの置換関係を記録する。ADR 0003は当初の方針と緩和案の履歴を保持し、現在の採用判断はADR 0015に記録する。実装の都合で未決事項を採用済みとして扱わない。

判断後はarchitecture、roadmap、acceptance、単一配布用引継ぎ書の該当箇所を更新する。実装上の選択も、その選択が公開APIや受入条件を変える場合は判断記録へ残す。

---

<a id="section-10"></a>

収録元 `docs/adr/0001-core-and-repository.md`

## ADR 0001 Coreと統合リポジトリ

### 状態

基本構成と統合リポジトリは確定。Subsystem独立性の詳細整理は当初提案として記録し、v0.3の採用範囲をR13・ADR 0016（`docs/adr/0016-v0.3-registry.md`）で具体化した。初稿の記録日2026年11月19日。R4による整理案は履歴として保持する。

### 背景

Nymphの活動を支える基盤を、着脱する機能とともに段階的に開発する。

### 決定

Coreを中心にSubsystem・Adapterを着脱する。Core Runtime、Registry、Connections、TaskManagerの4責務を設ける。GitHubの統合リポジトリ名は `nymph-toolkit` とする。

### 影響

Coreの初期開発、設計、ADR、検証を統合リポジトリで管理する。具体的なコード配置はarchitectureの案を用いる。

R6で配布方針を具体化した。CoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて同じリポジトリ内で分割する。採用内容と分割時の判断事項はADR 0009（`docs/adr/0009-package-distribution.md`）に記録する。

### Subsystem独立性の整理案

R4を受け、次の点をV0.3の設計判断に追加する。着脱可能性に関する既存決定を補う提案として記録する。

| 性質 | 状態・扱い |
|---|---|
| 登録・解除 | 確定した着脱方針に含む |
| 実装交換 | 接続契約を通じて可能にする設計案 |
| 他Subsystemへの機能的依存 | 許容する方向で検討。宣言・検出方法は要決定 |
| 相手の具体的実装への依存 | 避ける設計案 |
| 単体での完全動作 | 必須条件にしない案 |
| 依存先解除後の機能 | 利用不能をCoreが検出・通知する案。代替機能の提供は必須条件にしない |
| 永続データの複製・移植 | 初期スコープ外。ADR 0005を参照 |

### 未決事項

当初の判断対象だった登録ID・必須依存の宣言と解除時通知・ModuleGroupの着脱範囲はADR 0016で採用した。稼働中の実体着脱、通信中・活動中の取り外し、公開接続契約全体、Capability単位の依存などは後続判断とする。

公開先の後続判断はR9・ADR 0012（`docs/adr/0012-v0.1-publication.md`）で確定し、`Tao-pyth/nymph-toolkit` をpublicで公開する。実際の状態はreleaseで管理する。

### ライセンスの後続判断

初稿で未決だったライセンスは、R8の明示指示によりADR 0011（`docs/adr/0011-apache-2.0-license.md`）でApache-2.0を採用した。適用範囲は自作コード・Contracts・設計文書とし、公開先の選定とは別に記録する。

### 根拠

R2の確定事項と統合リポジトリの指定、R3の文書・配置計画。R4を根拠に独立性の整理案を追記した。元会話全文の確認状況はDocsの根拠表（`docs/README.md`）を参照する。

---

<a id="section-11"></a>

収録元 `docs/adr/0002-execution-model.md`

## ADR 0002 実行モデル

### 状態

ハイブリッド実行は確定。Python `asyncio` と軽量なメソッド呼び出しは方向性確定。記録日2026年11月19日。置換元・置換先なし。

### 背景

Coreと着脱する機能の実行配置を扱い、軽量な呼び出しを活かす方向が指定された。

### 決定

ハイブリッド実行を採用する。実装技術はPython `asyncio` と軽量なメソッド呼び出しの方向で設計する。

### 影響

同一プロセスと別プロセスの検証範囲を記録する。ロードマップでは同一プロセスから進め、V0.7で別プロセスを検証する案を置く。通信の許可経路はADR 0003の履歴を引き継いだADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）と後続判断に従う。

R5のv1.0.0目標であるSubsystem・Adapter向け共通接続基盤はADR 0006に記録する。実行配置間の通信契約の共通範囲、IPC方式、同期・非同期境界は、本ADRの未決事項として引き続き具体化する。

### 未決事項

後続判断：v0.2の対応Python、呼出側のイベントループを使う非同期API、起動・停止の範囲はADR 0014（`docs/adr/0014-v0.2-runtime.md`）で具体化した。別プロセス実行と通信契約については引き続き未決である。

対応Python版、イベントループの所有者、同期・非同期APIの境界、IPC方式、通信契約の共通化の有無と範囲、シリアライズ、切断時の動作。ハイブリッド実行の採用から、これらの具体策を確定事項として導かない。

### 根拠

R2のハイブリッド実行と技術の方向性、R5の接続契約整備の目標。旧稿の「配置間の通信契約共通化は確定」という記載はR2で確認できる範囲を超えるため、今回の整理では要決定とした。Docsの根拠表（`docs/README.md`）

---

<a id="section-12"></a>

収録元 `docs/adr/0003-communication-routing.md`

## ADR 0003 通信経路

### 状態

**一部置換済み。2026年11月20日のR12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）で、Coreが管理・許可した接続での直接通信を採用した。** 初稿記録日2026年11月19日。本ADRの当初の「Core経由のみ」と「緩和は未採用」は旧判断として保持し、現在の方針・残る判断はADR 0015を参照する。

### 背景と履歴

| 順序 | 内容 | 採用状態 |
|---|---|---|
| 1 | 通信をCore経由のみとする | 当時の正式採用済み方針 |
| 2 | 直接接続を認める緩和案が出た | 当時は未採用。許可条件と管理責任を含めて要決定 |
| 3 | 今回の引継ぎ依頼で、実装前決定事項として残すよう指定された | R2による記録方針 |
| 4 | 整合性レビューで、維持・緩和の判断までCore経由のみを暫定基準とする旨を明確化 | R4による既存方針の再確認。緩和は未採用 |
| 5 | ユーザーが「直接通信の緩和は採用ください」と指示 | R12・ADR 0015で採用。具体的な許可範囲とAPI等は要決定 |

元会話内の各発言日時は未確認である。

### 当初の決定（ADR 0015による置換前）

正式採用済みの方針を「Core経由のみ」として保持する。緩和案の存在だけでは採用状態を変更しない。Connectionsの経路と経路別受入テストを固定する前に、従来方針の維持または条件付き緩和を判断し、記録する。

### 当初の影響と比較（履歴）

経路に依存しないRuntime・Registryなどの検討を進められる。経路を使う検証は採用済み方針を根拠にする。ダミーへの相互参照の受け渡しや軽量な呼び出し方式によって、未採用の直接接続を既定動作にしない。

維持・緩和の後続判断が確定するまでは、Core経由のみを実装上の暫定基準とし、直接通信を前提としたコードを書かない。

| 方式 | Core経由のみとの関係 |
|---|---|
| Coreが毎回メソッドを呼び出す | 整合 |
| Coreが提供し、通信をCoreへ仲介するProxyを介する | 整合。Proxy方式の採用自体は未決 |
| Coreが接続したSubsystem同士が直接呼び出す | 原則変更が必要 |
| Coreが許可した直接音声ストリーム | 原則変更が必要 |

Proxyが相手への直接参照を返すだけの構成は、実際の通信経路に基づいて判断する。接続の許可・確立と、個々の通信の仲介を区別して記録する。

R5に基づくv1.xの接続契約とSubsystem連携案（ADR 0006・0008）にも本ADRを適用する。直接通信の許可範囲は未確定であり、音声受信・ASRの先行試験案からSubsystem間の直接通信許可を導かない。

### 当初の実装前判断欄（履歴）

以下はR12より前の記録である。現在は緩和の採否を解決済みとし、具体的な未決事項をADR 0015へ引き継ぐ。

| 項目 | 現在の記録 |
|---|---|
| 維持または緩和 | 要決定 |
| 対象となる接続元・接続先 | 要決定 |
| 緩和時の許可条件 | 要決定。維持の場合は該当なしと記録 |
| 接続の確立・解除・状態把握の責任 | 要決定 |
| Adapterを経由する経路の具体的な扱い | 要確認・要決定 |
| 許可・拒否を確認する公開手段とテスト | 要決定 |
| 採用日、判断者、理由、後続ADR | 未記入 |

### 根拠

R2に記載された正式採用と後発提案の関係、R4の通信方式の区別と実装時の暫定基準、R5の未決事項の維持。旧稿の「Adapterを中継した迂回通信は禁止」という個別断定は元発言を確認できていないため、当初の確認事項へ移した。初稿時点の正式方針は上記の履歴に保持し、後続のR12による採用判断をADR 0015に記録する。Docsの根拠表（`docs/README.md`）

---

<a id="section-13"></a>

収録元 `docs/adr/0004-activity-authority.md`

## ADR 0004 活動の決定権

### 状態

活動の決定権と実行管理の境界は確定。時間・優先度・変更操作の具体策は要決定。初稿の記録日2026年11月19日。R4による境界の補足と判断対象を追記。置換元・置換先なし。

### 背景

活動の判断主体と実行管理の担当を明示する必要がある。

### 決定

Nymphが活動内容・時刻・期間・変更を決定し、Coreが実行管理を担う。

R4でこの境界を再確認した。活動の価値や人格に基づく優先度はNymphが決める。優先度・実行枠を採用する場合、Nymphから与えられた優先度と採用済み規則に基づく割り当て・待機順序の機械的な処理はCoreが担う。優先度機能や割り当て方式の採用は後続判断で具体化する。

### 影響

TaskManagerに渡す活動と変更はNymph側の入力として追跡できるようにする案を用いる。ダミーNymphで判断の入力を代行し、実行結果と照合する。Core独自の活動選択を初期機能へ追加しない。

| 判断・処理 | 担当 |
|---|---|
| 睡眠・調査の選択、活動の価値評価、期間延長の判断 | Nymph |
| 活動の優先度の生成・変更 | Nymph。優先度機能の採否は要決定 |
| 指定時刻の監視、起動、実行状態の追跡 | Core |
| 実行枠不足・変更要求の実行可否・競合の検出と通知 | Core。検出条件と通知契約は要決定 |
| 指定された優先度に基づく割り当て・待機順序 | Core。機能採用時の機械的処理 |
| タイムアウト・障害の通知 | Core。適用条件と方式は要決定 |

CoreはNymph自身の活動状態を管理する。外部アプリの稼働状況は将来のAdapterが取得する。認知・学習アルゴリズムと人格に基づく優先度生成はCoreの実行管理の範囲外である。

R5ではAgency Subsystem（暫定名称）がNymph側の活動決定を担う配置案を示す。v1.5.0〜v1.6.0で、活動内容・開始時刻・期間・優先度・変更の決定とCore TaskManagerの実行管理を連携させる案をADR 0008に記録する。v0.xの変更操作・優先度機能の採否と対応範囲を確認して具体化する。

### V0.6で採否を判断する操作

以下はR4による検討対象の追加であり、全操作の実装採用を意味しない。各操作について、採用・見送り・継続検討、理由、対応する活動状態、期待する応答を後続ADRに記録する。継続検討の項目を実装済み・検証済みとして扱わない。

| 操作 | 現在の状態 | 採用時に決める点 |
|---|---|---|
| 開始時刻の変更 | 要決定 | 繰り上げ・延期、開始との競合 |
| 実行期間の変更 | 要決定 | 延長・短縮、既に経過・実行した時間との関係 |
| 優先度の変更 | 要決定 | Nymphの入力形式、待機順序と実行枠への反映 |
| 中断・再開 | 要決定 | 中断中の計時、再開可否、状態と実行枠の扱い |
| 取消・終了 | 要決定 | 開始前・実行中・終了後の意味、通知と後処理 |

### 未決事項

活動のデータ型、時計とタイムゾーン、時刻・期間・経過時間・実行時間の区別、期間満了に使う時間、中断時の計時、状態遷移、上表の各操作、同時実行、競合、永続化、失敗通知。Coreで扱う機械的な順序規則、同順位、変更要求の競合と、Nymphによる価値判断の境界を維持して具体化する。各項目の対応範囲を決めてから受入条件を具体化する。

### 根拠

R2の活動内容・時刻・期間・変更の決定権とCoreの実行管理に関する明示。R4を根拠に責務境界を補足し、時間概念と変更操作の検討対象を追記した。R5を根拠にAgency配置案との関係を補足した。Docsの根拠表（`docs/README.md`）

---

<a id="section-14"></a>

収録元 `docs/adr/0005-initial-scope.md`

## ADR 0005 初期実装の範囲

### 状態

確定。記録日2026年11月19日。置換元・置換先なし。

### 背景

Coreを先に実装してダミーで検証し、GitHub公開からCore機能完成まで段階的に進める。

### 決定

初期実装はCoreだけとし、周辺はダミーで検証する。将来のPC上の他アプリの稼働状況取得はAdapterで扱う。複製・移植・伝播機構は初期スコープ外とする。伝播機構の扱いはR5の明示に基づく補足である。

GitHub公開をV0.1、Core機能完成をV0.9の目標とする。公開前の段階を公開準備と呼ぶ。

### 影響

V0.1では資料・開発基盤と実装状況を公開する。Coreの実装をV0.2以降へ配分する案をroadmapに記載する。V0.9では合意したCore機能を、実機Adapterや人格実装を準備せずにダミーで検証できることを目指す。

本ADRのCore単体・ダミー検証の範囲はv0.9.0までのCore初期開発に適用する。R5によるv1.0.0の接続契約整備と、その後のSubsystem・Adapter開発案はADR 0006〜0008で扱う。Desktop AdapterによるPC全体の状況取得・操作はv1.10.0までに割り当てず、将来課題とする。

### 未決事項

V0.2〜V0.8への機能配分、各段階の受入方法、Core完成の具体的なAPI・障害時動作。これらは計画案・後続判断として扱う。PC状況取得と複製・移植の実装時期は今回設定しない。

### 根拠

R2の初期スコープ、R3のバージョン目標、R5のv1.x計画との適用範囲と伝播機構の除外。R1の提示プレビューでもPC状況取得を将来のAdapterで扱う意向を確認できる。Docsの根拠表（`docs/README.md`）

---

<a id="section-15"></a>

収録元 `docs/adr/0006-core-connection-contracts.md`

## ADR 0006 v1.0.0のCore接続契約

### 状態

R5で明示されたv1.0.0の目標は確定。契約の詳細、公開API、開発補助機能、契約テストの構成は提案・要決定。既存ADRの置換なし。ADR 0001・0002・0003・0004・0005を前提として追加する。

記録日2026年11月20日。目標の判断根拠はR5のユーザー明示指示。

### 背景

v0.9.0で合意したCore機能を完成させ、その成果をSubsystem・Adapterが接続する共通基盤として整える。v1.0.0でCoreとSubsystem・Adapterの接続契約を大きく形作る目標がR5で明示された。

### 決定と検討案

v1.0.0はCore接続契約の確立を目指す。本番Subsystemの完成はこの段階の必須条件としない。以下の契約区分を検討対象とする。区分名は検討用であり、Pythonクラスやファイルの名称を確定するものではない。

| 検討対象 | 具体化する内容の案 |
|---|---|
| Module Contract | Subsystem・Adapterの識別、登録、接続要件 |
| Lifecycle Contract | 初期化、起動、停止、解除と状態の扱い |
| Capability Contract | 提供機能と必要機能の表明、利用可能性の確認 |
| Communication Contract | 要求・結果の受け渡し、採用した通信経路との整合 |
| Task Contract | 活動の登録、実行、状態追跡、採用した変更操作 |
| Error Contract | 接続・実行失敗の表現、通知、後処理の責任 |

公開APIの文書化、接続用の開発補助機能、ダミーによる契約テストの整備を検討する。v0.9.0までのAPI・受入結果を確認し、契約として公開する範囲を定める。

R6で採用した初期配布方針に従い、CoreとContractsは一つの配布パッケージに含める。ソースは `core/` と `contracts/` に分け、v0.xで必要な契約から用意し、v1.0.0で体系化する。配布方針の詳細はADR 0009（`docs/adr/0009-package-distribution.md`）を参照する。

### 影響

CoreはRuntime、Registry、Connections、TaskManagerを中心とする実行・接続・活動管理の基盤である。認知・意思決定はNymph側が担当する。軽量なPythonメソッド呼び出しとasyncioの方向性、およびハイブリッド実行を前提とする。

Subsystem・Adapter向け共通接続契約と、同一・別プロセス間でどこまで通信契約を共通化するかは、それぞれ判断を記録する。本ADRの初稿時点では通信の直接接続許可はADR 0003の未決事項であり、本ADRによる緩和の採用はなかった。後続のR12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）でCoreが管理・許可した直接通信を採用した。個別の許可範囲と契約詳細は引き続き要決定である。

### 未決事項

各契約の必須項目、型・メソッド、状態遷移、Capabilityの表現、依存の確認、実行配置ごとの適用範囲、公開APIの互換性境界、補助機能の範囲、契約テストの具体的な合格条件。検討結果と採用範囲は後続ADRで記録する。

### 根拠

R5「Codex編集依頼書：NTK v1.0.0以降の開発ロードマップ案」の確定方針とv1.0.0の設計意図。Docsの根拠表（`docs/README.md`）

---

<a id="section-16"></a>

収録元 `docs/adr/0007-v1-release-roadmap.md`

## ADR 0007 v1.x以降のリリース運用と開発順序

### 状態

提案・未採用。R5の編集依頼に基づく開発計画案。既存ADRの置換なし。v0.1.0・v0.9.0の目標はADR 0005、v1.0.0の目標はADR 0006を参照する。

記録日2026年11月20日。運用案の採用日・判断者は未記入。

### 背景

Core接続契約を基盤に、新しいSubsystemの導入と連携・Adapterの整備を段階的に進める。

### 提案内容

| リリース区分 | 主目的の案 |
|---|---|
| v1.0.0 | CoreとSubsystem・Adapterの接続契約確立 |
| 奇数マイナーバージョン | 新規Subsystemの実装 |
| 偶数マイナーバージョン | Subsystem間連携の見直し・強化、Adapterの実装・拡張 |
| パッチバージョン | 不具合修正、小規模改善、互換性を維持した個別修正 |

奇数・偶数はリリースの主目的を表す。各段階で必要な補助実装と最低限の統合テストを行える。偶数マイナーの新規Adapter追加は任意とする案である。公開APIの互換性とSemantic Versioningとの整合性は、変更内容に基づいて別途判断する。判断方法はreleaseに記載する。

推奨するSubsystemの順序はMemory、Cognition、Agency、Persona、Sleep。Adapterの順序はDocument、Text Interaction、Web、Discord Voice、Desktopとする。**名称、順序、バージョンへの機能配分はすべて暫定案**で、変更できる。具体的な配分はroadmapのv1.0.0以降の表で管理する。

### 影響

保存・取得を先に用意して言語・概念学習を検証し、活動決定、人格の反映、経験統合と人格変化の循環へ進む案とする。技術的な依存関係や研究上の優先順位、検証結果に応じて、理由と受入条件への影響を記録して順序を調整できる。日付・開発期間・工数の見積もりは設定しない。

未完成のSubsystemがある場合は、利用できる能力またはダミーで対応範囲を限定して検証する。Discord Voice Adapterの音声受信・ASRは必要に応じた先行試験実装を認める案とする。Desktop Adapterはv1.10.0までの配分に含めず、将来課題として記録する。

### 未決事項

運用案の採否、Subsystem・Adapterの正式名称、実装順序、依存関係、各リリースの具体的範囲、公開APIの互換性判断、パッチに含める改善の範囲、分割後のバージョン管理単位。各段階の実装内容と受入条件は設計・後続ADRで具体化する。

初稿で未決としていた配布単位の方針は、R6に基づくADR 0009（`docs/adr/0009-package-distribution.md`）で具体化した。単一リポジトリでCoreとContractsを同梱して開始し、Subsystem・Adapterは必要に応じて分割する。個別の分割対象・時期と、ロードマップのバージョンを各配布物へどう対応させるかは要決定である。

### 根拠

R5のリリース運用案、推奨ロードマップ、実装順序とAdapter開発方針。Docsの根拠表（`docs/README.md`）

---

<a id="section-17"></a>

収録元 `docs/adr/0008-subsystem-adapter-boundaries.md`

## ADR 0008 v1.xのSubsystem・Adapter責務案

### 状態

設計提案。R5が指定する研究方針・責務境界を前提とし、名称、実装方式、順序、機能配分、受入条件は未確定。本ADRによる既存ADRの置換なし。接続契約はADR 0006、通信経路はADR 0015と後続判断、活動の決定権はADR 0004に従う。

記録日2026年11月20日。具体的な設計案の採用日・判断者は未記入。

### 背景

Core初期開発後に、Nymphの保存・学習・意思決定・人格・睡眠循環と外部入力を段階的に検証する。

### 責務と設計制約

以下のSubsystem名・Adapter名はすべて暫定名称である。

| 要素 | 設計意図・境界 |
|---|---|
| Memory Subsystem | 経験・知識の最小保存と取得。初期段階の複雑な知識グラフや高度な記憶統合は必須としない |
| Document Adapter | 文書取得とMemoryへの入力を接続契約に沿って検討 |
| Cognition Subsystem | 語彙・構文・概念の初期学習を検討。既存LLMを言語理解・文章生成の中核に使うことは現在の研究方針に含めない |
| Text Interaction / Web Adapter | 文章観測、学習、出力、ユーザーからの訂正を検証する接点 |
| Agency Subsystem | Nymph側で活動内容、開始時刻、期間、優先度、変更を決定。Core TaskManagerが登録・実行・状態追跡・変更要求の適用を担当 |
| Persona Subsystem | 人格特性をパラメータとして保持し、参照に応じて返す。外部の修正値を契約に従って適用し、自発的に人格修正処理を開始する構成にはしない |
| Sleep Subsystem | 経験統合、忘却、夢生成、人格修正値の生成を段階的に検討。Personaへは接続契約を通じて修正値を提供する基本案とし、内部状態の直接変更は行わない |
| Discord Voice Adapter | 他者同士の音声会話を観測する外部接続。ASRによる文字起こしと音響特徴の併用を基本案とし、音声からの直接意味理解は初期要件にしない |
| Desktop Adapter | 将来のPC全体の稼働状況取得・操作を担う候補。v1.10.0までの配分には含めない |

### 影響

AgencyはNymphの意思決定を担う配置案であり、Coreの責務を認知・価値判断へ広げない。Core側で扱う活動変更や優先度は、既存ADRと採用契約の対応範囲を確認して連携する。Personaの参照・外部更新とSleepによる修正値の生成を、通信契約に沿って検証する。

Subsystem間の連携には採用した通信経路を適用する。後続のR12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）でCoreが管理・許可した直接通信を採用した。個別の経路の許可は契約で具体化し、「接続契約を通じる」という表現だけから推定しない。データの複製・移植・伝播機構は初期開発の対象外である。

音声の取得・保存・学習では、参加者への告知、適切な同意、アクセス権限、保持・削除方針を設計時に扱う。先行試験でも、扱う音声・文字起こし・音響特徴の範囲と、取得・保存・学習それぞれの利用条件を明確にする。具体的な保持期間や利用サービスは未決である。

### 長期ビジョンとの関係

R7のProject Vision（`docs/vision.md`）とADR 0010（`docs/adr/0010-project-vision.md`）が最終到達目標を補う。読む・聞く・対話する・経験と結び付ける言語獲得、記憶の根拠・不確実性・訂正可能性、機能的なSelf-Model、内部状態・動機・情動を長期の検討対象とする。ASR・音声合成・形態素解析・文書解析などの補助技術の利用は許容される。これらの能力領域は、新たなSubsystem名や配置を確定するものではない。

睡眠による経験統合を長期人格の変化へ反映する構想を維持する。夢を現実の経験と区別し、夢そのものから人格を直接変更せず、内部の夢記憶を次の睡眠時に失効させる方針を長期構想として記録する。夢について実際に対話した経験は通常の現実の経験として扱う。実装上の対象・契約・時期・受入条件は後続ADRで決め、v1.9.0・v1.10.0の必須機能へ一括追加しない。

### 未決事項

Memoryの保存形式、Cognitionの学習方式と評価方法、Agencyの意思決定方式、Personaのパラメータと修正値の契約、Sleepの処理範囲、各Adapterの対応形式・権限・失敗時動作。Discord音声受信の実現方法、ASRの選択、音響特徴、告知・同意・保持・削除の手順は実装前に検証・判断する。

### 根拠

R5の各段階の設計意図とAdapter開発方針、R7の最終ビジョンによる長期構想の補足。Docsの根拠表（`docs/README.md`）

---

<a id="section-18"></a>

収録元 `docs/adr/0009-package-distribution.md`

## ADR 0009 単一リポジトリと段階的な配布パッケージ分割

### 状態

採用。採用日2026年11月20日。判断者はプロジェクト所有者（R6のユーザー明示指示）。適用範囲はNTKの初期配布構成と、将来のSubsystem・Adapterの分割方針。

ADR 0001の統合リポジトリ方針を具体化し、ADR 0006の接続契約の初期配置と、ADR 0007で未決だった配布単位の方針を補う。既存ADRの全面置換なし。個別の分割対象とバージョン管理方式は後続判断とする。

### 背景

Core先行開発を進めながら、将来のSubsystem・Adapterごとの依存関係、独立した公開・更新の必要性に対応する。フォルダ構成案の検討を経て、CoreとContractsを一つの配布パッケージから始め、拡張は必要に応じて分割する方針が採用された。

### 決定

- GitHubの単一リポジトリ `nymph-toolkit` でCore・Contracts・Subsystem・Adapterを管理する。
- 初期の配布パッケージはCoreとContractsを含む一つとする。実装上は `core/` と `contracts/` に責務を分ける。
- Subsystem・Adapterは依存関係、独立更新、単独配布の必要性に応じて、同じリポジトリ内で別の配布パッケージへ分割する。
- 実装と配布に必要な段階でフォルダと設定を追加する。v0.xではCoreと検証用ダミーを先行させる。

ここで配布パッケージはインストール・配布する単位を指す。Pythonのimportに使う名前と、リポジトリ内のフォルダはそれぞれ区別して設計する。配布パッケージの正式名称は未決である。

### 配置の具体化

初期配置はルートの `pyproject.toml` で一つの配布物を定義し、`src/nymph_toolkit/core/` と `src/nymph_toolkit/contracts/` を含める構成とする。Contractsはv0.xで必要なものから追加し、v1.0.0で公開接続契約として体系化する。

将来、同梱するSubsystem・Adapterは `src/nymph_toolkit/subsystems/` と `src/nymph_toolkit/adapters/`、別配布にするものは `packages/<配布ディレクトリ>/` に配置する案をarchitectureに示す。後者には対象の `pyproject.toml` とソース・テストを置く案とする。これらの将来配置例と個別名称は、対象の分割判断時に具体化する。

### 分割時に確認すること

依存ライブラリ・対応OSの違い、Coreと異なる更新頻度、利用者が単独導入する必要性を確認する。分割対象、理由、Core・Contractsの対応バージョン、依存宣言、公開import名、テスト・配布手順を後続ADRへ記録する。依存追加だけが目的の場合は、任意依存による同梱も比較対象とする。

### 影響

初期のCoreとContractsは同じ配布物としてビルド・検証する。拡張を分割した場合は、それぞれの配布物とCore・Contractsの組み合わせを検証する。

R8・ADR 0011（`docs/adr/0011-apache-2.0-license.md`）で、自作コード・Contracts・設計文書へのApache-2.0適用を採用した。将来分割する自作Subsystem・Adapterも各配布物にLICENSEと必要な表示を含める。第三者成果物の条件は別途扱う。

責務分離の設計案として、Core・Subsystem・Adapterが公開Contractsを参照し、Contractsを具体的な実装から独立させる依存方向を用いる。配布単位とは別に、同一・別プロセスの実行配置はADR 0002、許可する通信経路はADR 0015と後続判断で管理する。

### 未決事項

後続判断：v0.2の配布名 `nymph-toolkit`、Hatchlingによるビルド、GitHub Releaseでのwheel・sdist配布はADR 0014（`docs/adr/0014-v0.2-runtime.md`）で具体化した。PyPI公開と将来の分割方針の詳細は今回の対象外である。

配布パッケージの正式名称、配布先、ビルドツール、個別の分割対象・時期、任意依存の構成、分割後の公開import名・名前空間、バージョンを同期するか独立させるか、リポジトリのリリースと配布物の対応。契約のAPI・型・必須項目はADR 0006、直接通信の許可範囲はADR 0003の履歴を引き継いだADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）と後続判断に従う。

### 根拠

R6の「単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて分割する」採用指示。Docsの根拠表（`docs/README.md`）

---

<a id="section-19"></a>

収録元 `docs/adr/0010-project-vision.md`

## ADR 0010 Nymphの最終ビジョンと実装範囲の区別

### 状態

長期ビジョンとして採用。採用日2026年11月20日。判断者はプロジェクト所有者（R7の添付文書と反映指示）。具体的な能力の実装方式・時期・受入条件を一括採用するものではない。既存ADRの置換なし。

### 背景

Core先行の開発計画に加え、NTKが支える人工人格Nymphの最終到達目標を明確にする。ユーザーが提示したProject Visionに沿って目的・研究方針・評価領域を記録し、現在の実装範囲と区別する。

### 決定

最終ビジョンの本文をvision.md（`docs/vision.md`）に置く。Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指す。NTKは、その成長をSubsystemとAdapterの協調によって実現するオープンソース基盤を目指す。

次の考え方を長期の設計・研究方針とする。

- 限定的な能力から経験によって育つことを目指し、基本機構の実装と、語彙・概念・知識・自己理解の獲得を区別する。
- 既存LLMを言語理解・文章生成の中核にせず、経験からの独自の言語獲得を研究する。音声認識・音声合成・形態素解析・文書解析などの補助技術は利用を許容し、意味理解の外部モデルへの代行と区別する。
- 読む・聞く・対話する・経験と結び付ける経路を通じた継続的な成長を目指す。知識の根拠、不確実性、訂正可能性を重視する。
- 記憶、機能的なSelf-Model、自律活動、内部状態・動機・情動、長期的な人格、睡眠・夢を長期の能力領域として扱う。主観的意識の証明を完成条件にしない。
- Nymphが活動を決定し、Coreが実行管理する。PC環境の観測・操作はAdapterを介し、操作には明示的な権限管理と必要に応じたユーザー承認を設ける方向で設計する。
- 学習・推論・行動・人格変化を可能な限り観測・検証できる構成を重視する。

### 具体化する長期構想

記憶領域の分け方、Self-Modelの配置、動機・情動の制御、人格パラメータは設計・研究対象であり、追加Subsystemや公開APIを確定しない。

Sleepによる経験統合を長期人格の変化へ反映し、Personaは外部の修正値を適用する構想を維持する。夢と現実の経験を区別し、夢そのものから長期人格を直接変更しない。夢の内部記憶を次の睡眠時に失効させ、夢についての実際の会話は現実の経験として扱う方針を長期構想に含める。失効対象・時点・保存方式などの実装契約は後続ADRで具体化する。

### 影響

READMEはCoreの現在の実装状況と併せて、人工人格の成長という目的を示す。architecture・roadmap・acceptanceからvisionを参照し、最終目標の達成を特定のバージョン番号へ固定しない。v0.1.0の公開、v0.9.0の合意したCore完成、v1.0.0の接続契約整備という目標と、既存の機能配分案を維持する。

再起動後も記憶・発達状態を維持する継続性は長期目標として扱う。これによってCoreの永続化方式を決定せず、複製・移植・伝播を初期要件へ追加しない。Desktop Adapterも将来課題として扱う。CoreとContractsの配布方針はADR 0009に従う。

本ADRの初稿時点ではCore経由のみが正式採用され、直接接続緩和はADR 0003の実装前判断だった。後続のR12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）でCoreが管理・許可した直接通信を採用し、具体的な許可範囲・契約は未決事項として残す。オープンソースを目指すことと、公開先・公開範囲・ライセンスの具体的な選定は分けて記録する。

後続のR8により、ライセンスはADR 0011（`docs/adr/0011-apache-2.0-license.md`）でApache-2.0を採用した。自作コード・Contracts・設計文書に適用し、第三者成果物やNymphの個体データの条件は別途扱う。公開先・公開範囲の選定と公開作業は引き続き公開準備資料で管理する。

### 未決事項

長期能力の方式・担当・開発時期、定量的な到達基準、言語獲得の評価方法、根拠・訂正・不確実性の表現、夢の保持・失効の契約、継続性を支える保存範囲と復元方法、外部操作の権限・承認の仕組み。各段階の採用範囲と受入条件を後続ADRへ記録する。

### 根拠

R7の添付「Project Vision — 人工人格Nymphの最終到達目標」と、最終ビジョンを同内容に沿って記述するユーザー指示。Docsの根拠表（`docs/README.md`）

---

<a id="section-20"></a>

収録元 `docs/adr/0011-apache-2.0-license.md`

## ADR 0011 自作コード・Contracts・設計文書へのApache-2.0適用

### 状態

採用。採用日2026年11月20日。判断者はプロジェクト所有者（R8のユーザー明示指示）。公開前のライセンス未決事項を解消する。ADR 0009の配布方針とADR 0010の長期ビジョンを補い、既存ADRの全面置換は行わない。

### 背景

人工人格Nymphの成長を支えるオープンソース基盤として、第三者が利用・研究・拡張しやすい条件を用意する。初期はCoreとContractsを一つの配布パッケージとし、Subsystem・Adapterは必要に応じて分割する。

候補の比較を経て、ユーザーがApache-2.0を明示的に選択した。改変ソースの提供を必須としない利用の自由と、貢献者による一定範囲の明示的な特許許諾を採用理由とする。再配布時の条件は公式本文に従う。[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

### 決定

- NTKの自作コード、Contracts、設計文書にApache License 2.0を適用する。SPDX識別子は `Apache-2.0` とする。
- 自作コードにはCoreと将来の自作Subsystem・Adapterを含む。設計文書にはREADME、Docs・ADR、配布用引継ぎ書を含む。
- リポジトリ直下のLICENSE（`LICENSE`）に、Apache Software Foundationが提供する公式英語本文を変更せず収録する。付録の説明・記入例も公式本文のまま保持する。
- READMEと公開準備資料に採用済みの状態と適用範囲を記載する。単一配布用引継ぎ書にもライセンス原文を収録し、一つのファイルで利用条件を確認できるようにする。
- パッケージを分割する際も、自作の対象部分には同じ方針を適用し、各配布物にLICENSEと必要な権利表示を含める。

### 適用対象との境界

第三者のコード・ライブラリ・モデル・学習用文書・音声等の権利を、この決定によってApache-2.0へ変更しない。導入・同梱時に元のライセンス、利用条件、必要な表示を確認する。

Nymphが扱う会話・記憶・人格などの個体データへ、本ライセンスを一律適用する決定ではない。取得・保存・学習・共有の条件はデータごとに別途扱う。

既存LLMを言語理解・文章生成の中核にしない研究方針はNTK本体の開発方針として維持する。ライセンス本文へ研究目的限定や商用禁止などの独自条件を付け加えない。

### 影響

ライセンス選定は公開前判断欄で「採用済み」とする。公開先アカウント・公開範囲・remote・タグ・公開日はそれぞれ従来の状態を維持し、ライセンスの採用だけでV0.1公開完了とはしない。

将来の実装・配布では、配布メタデータのライセンス表示とLICENSEの収録を確認する。必要な著作権・帰属表示、変更表示を保持し、第三者のNOTICEを含む場合は本文第4条に従って扱う。独立したNOTICEファイルの必要性は、収録物と表示要件に応じて確認する。[公式の適用方法](https://www.apache.org/foundation/license-faq.html)

Coreの責務、通信経路、契約の具体的なAPI、各段階の実装範囲を変更する決定ではない。

### 残る判断事項

新たな第三者成果物の導入時の互換性・利用条件・帰属表示、実装開始時のビルド設定、各配布物へのライセンス収録方法。ライセンス種別そのものは確定済みである。

公開先・公開範囲は後続のR9・ADR 0012（`docs/adr/0012-v0.1-publication.md`）で、個人アカウント `Tao-pyth` 配下のpublic公開へ確定した。release（`docs/release.md`）で実際の公開状況を管理する。

### 根拠

R8の「Apache-2.0で進めてください。自作コード・Contracts・設計文書に適用する方針」という明示指示。Docsの根拠表（`docs/README.md`）

本文の取得元：[Apache License 2.0公式テキスト](https://www.apache.org/licenses/LICENSE-2.0.txt)。2026年11月20日確認。

---

<a id="section-21"></a>

収録元 `docs/adr/0012-v0.1-publication.md`

## ADR 0012 個人アカウントでのv0.1.0公開と参加方針

### 状態

採用。採用日2026年11月20日。判断者はプロジェクト所有者（R9のユーザー明示指示）。ADR 0001・0005の初回公開を具体化する。実際の公開・タグ・リリースの完了状況はrelease（`docs/release.md`）で管理する。

### 背景

最終ビジョン、Core初期設計、配布方針とApache-2.0の採用が記録された。資料を中心としたv0.1.0の公開先・公開方法を決め、外部からの提案・修正の入口を用意する。

### 決定

- 接続確認済みの個人アカウント `Tao-pyth` 配下に、単一リポジトリ `nymph-toolkit` をpublicで公開する。
- 初回公開は現在の設計・ビジョン・ロードマップ・開発資料とGit設定、LICENSEを中心とする。Core未実装をREADMEとリリース記録に明記する。
- ルートの `CONTRIBUTING.md` に簡潔な参加方針を置き、質問・提案・報告はGitHub Issues、変更の提出はPull Requestを入口とする。
- 設計変更は議論し、メンテナーが採用した判断をADRへ記録する。既存の未決事項を公開作業の都合で確定しない。
- 公開内容を確認したコミットに `v0.1.0` タグを付け、同じタグのGitHub Releaseに実装状況・検証結果・未決事項・次の段階を記録する。

### 影響

GitHub公開がV0.1という既存目標を実施する。公開のために本番Subsystem・Adapterや動作デモを追加する要件は設けない。CoreとContractsの初期配布方針はADR 0009、ライセンスはADR 0011に従う。

リポジトリの作成、既存Git履歴のpush、タグ・Releaseの公開を行い、publicで取得できることを確認する。公開済みタグを移動せず、その後の変更は次のコミット・リリースで記録する。

### 残る判断事項

後続判断：R10・ADR 0013（`docs/adr/0013-milestone-issue-workflow.md`）で、今後のコード変更に先立つマイルストーン・親子Issueの登録順序を採用した。公開済みv0.1.0の記録は維持する。

Python対応版・開発ツール・Core API・通信経路の維持または緩和など、各実装段階の未決事項は従来のADRとロードマップで扱う。詳細な参加手順や検証の自動化は、開発・参加状況に応じて追加する。

### 根拠

R9の「個人アカウント配下で、現在の資料を中心にpublic公開し、簡潔な参加方針を添えてv0.1.0とする」というユーザー指示。Docsの根拠表（`docs/README.md`）

---

<a id="section-22"></a>

収録元 `docs/adr/0013-milestone-issue-workflow.md`

## ADR 0013 マイルストーン・親子Issueを前提とするコード変更

### 状態

採用。採用日2026年11月20日。判断者はプロジェクト所有者（R10のユーザー明示指示）。ADR 0012の参加方針に、今後のコード変更へ適用する着手条件を追加する。

### 背景

v0.1.0の資料公開を終えた。段階別ロードマップを実装へ移す前に、対象バージョン、親課題、個々の対応単位を追跡できる状態にする。実装を始めてから課題を登録する進め方を避ける。

### 決定

コードの新規作成・修正を伴う変更は、次の順序を必須とする。

1. 各バージョン情報をGitHubマイルストーンに整理する。
2. そのマイルストーンに親課題Issueを設定する。
3. 対応単位ごとの子課題Issueを登録し、親子関係とマイルストーンを設定する。
4. 対象の子Issueに沿って対応し、検証結果と変更コミットまたはPRを記録する。

登録時に確定目標と機能配分案を区別する。子Issueの登録だけで未決仕様を採用したことにはしない。実装に必要な設計判断は従来どおり関連Docs・ADRへ記録する。

### 影響

新規実装、不具合修正、リファクタリング、テスト・実行・配布設定の変更を含め、対応する子Issueの登録前にコードを変更しない。親Issueだけの状態では実装へ進めない。文書のみの修正はこの必須条件の対象外だが、設計変更の議論・ADR記録という既存方針は維持する。

GitHubのsub-issue機能で親子関係を保持し、子Issueにも対象マイルストーンを設定する。具体的な記載項目と完了時の確認はIssue運用（`docs/issue-workflow.md`）、エージェント向けの要点はルートのAGENTS.md（`AGENTS.md`）に記載する。

既存ロードマップのv0.1.0〜v0.9.0、v1.0.0〜v1.10.0を期限なしのマイルストーンと親Issueに整理する。公開済みのv0.1.0は完了記録として扱い、このルールを過去に実施したという記録を作らない。先の段階の子Issueは対応単位を具体化してから登録する。

### 未決事項

各バージョンの詳細な作業分割と機能配分、API・実装方式などは従来の採用状態を維持する。GitHub Actionsによる自動チェックやブランチ保護は今回の必須要件に追加しない。

### 根拠

R10の「コードの修正を行うような変更」には「各バージョン情報をマイルストーンとして整理」「親課題issueを設定」「対応単位ごとに子課題issueを登録→対応」を前提とするというユーザー指示。Docsの根拠表（`docs/README.md`）

---

<a id="section-23"></a>

収録元 `docs/adr/0014-v0.2-runtime.md`

## ADR 0014 v0.2の開発環境と最小Runtime

### 状態

採用。記録日2026年11月20日。R11「v0.2までの作業」の実施に伴う実装判断としてCodexが記録する。過去の会話で確定していた仕様とは区別する。対象は親Issue #2、設計判断 #22、環境構築 #23、実装 #24、受入 #25。ADR 0002・0006・0009の一部をv0.2に限って具体化する。

### 背景

v0.2で最小Runtimeをダミーにより検証する。Coreの他の責務やv1.0の接続契約全体を先に固定せず、起動・実行・停止の契約と検証可能な失敗通知を用意する。

### 決定：環境と配布

- CPython 3.12以上を対象とし、3.12〜3.15を検証範囲とする。Python 3.8は対象外。既存環境のPythonを上書きせず、仮想環境を用いる。
- 配布名は `nymph-toolkit`、import名は `nymph_toolkit`。Coreと必要なContractsを一つのwheel・sdistに含める。GitHub Releaseで配布し、PyPIへの公開は今回行わない。
- `venv` と `pip`、ビルドフロントエンド `build`、バックエンド `hatchling` を使う。実行時の外部依存は設けない。ビルド用の版と依存は設定・検証記録へ記載する。
- テストは標準の `unittest.IsolatedAsyncioTestCase` を使う。asyncioのキャンセルと後処理を実際に検証し、時刻待ちに依存せずEventで同期する。
- WindowsとLinuxのCIでテスト・ビルド・配布物からの実行を確認する。自動公開は行わない。

Python 3.12を下限とするのは、保守中のPythonで標準asyncio・型定義を利用し、古い版への互換対応を初期開発へ持ち込まないためである。標準テストを選ぶのは外部テスト実行基盤を追加せずに今回の非同期シナリオを再現できるためである。ビルド専用ツールは実行時依存と分離する。

### 決定：Runtimeの責務

`Runtime[T]` は、一つの `RuntimeService[T]` を同一プロセスで動かす。サービスは `async start() -> None`、`async run() -> T`、`async stop() -> None` を提供する。Runtimeがこの順に軽量なメソッド呼び出しで実行する。

Runtimeは呼出側の稼働中イベントループを使い、ループの生成・終了を行わない。Runtimeの制御操作は開始時と同じイベントループ上で行う。サービス内部から自身のRuntimeのwait・stopを待機する操作は、自己待機となるため拒否する。

| 公開操作 | 契約 |
|---|---|
| `await runtime.start()` | 初期化完了まで待ち、実行を開始する。初期化失敗時はstopによる後処理を済ませてからRuntimeFailureを通知する |
| `await runtime.wait()` | 実行と後処理の完了を待ち、正常なrunの戻り値を返す。停止要求による中断時はNone。待機側のキャンセルは実行側へ伝播させない |
| `await runtime.stop()` | 実行中・初期化中のサービスへキャンセルを要求し、後処理の完了まで待つ。停止済みなら再度後処理しない。失敗記録がある場合は再度通知する |
| `runtime.state` | NEW、STARTING、RUNNING、STOPPING、STOPPED、FAILEDを返す |

インスタンスは一回の実行に用いる。二重起動と停止後の再起動はRuntimeStateErrorとし、再実行には新しいインスタンスを使う。開始前のstopはサービスを呼び出さずSTOPPEDへ移す。NEWでのwaitはRuntimeStateErrorとする。

runが自然終了した場合もstopを呼び出し、後処理後にSTOPPEDへ移す。初期化に入った場合は、初期化失敗・キャンセルを含めてstopを一度呼び出す。サービスのstopは部分的な初期化にも対応する。実行開始前に停止要求が届いた場合はサービスを呼び出さない。

開始を待つ呼出側がキャンセルされた場合は停止を要求する。呼出側へCancelledErrorを返した後も後処理はRuntimeが保持するタスクで継続するため、終了の確認にはstopまたはwaitを再度待機する。stopの待機側がキャンセルされた場合も後処理は継続する。STOPPING中の重複停止要求で後処理を再キャンセルしない。

### 決定：失敗と後処理

初期化・実行・後処理の通常の例外をLifecycleFailure（phaseと元例外）へ記録し、RuntimeFailureとして呼出側へ通知する。実行と後処理の両方が失敗した場合は両方を保持し、片方を失わない。要求していないサービス側のCancelledErrorも失敗として扱う。KeyboardInterrupt・SystemExitなどのプロセス制御例外は通常の失敗契約の対象外とする。

Runtimeが作成する監督タスクの完了と、サービスのstop完了を停止完了とする。サービスが独自に作るタスク・接続はサービスのstopが終了させる。無関係な呼出側タスクは停止しない。

キャンセルは協調的である。キャンセルを無視する処理や停止しない後処理を強制終了する機能は追加しない。待機時間を制限したい呼出側はasyncio.timeout等を使い、時間切れを停止完了と誤認しない。自動再試行・自動復旧・永続化は導入しない。

### 受入と影響

A02を、正常実行、実行中停止、初期化失敗と部分後処理、実行失敗、後処理失敗、複数失敗、二重制御・キャンセル、終了後の残存タスク、新規環境への配布物インストールで具体化する。公開import、メタデータ、LICENSE収録も確認する。

RuntimeServiceはv0.2の実行入口の契約であり、Subsystem・Adapter共通契約全体の確定を意味しない。Registry、Connections、TaskManager、別プロセス実行は未実装のまま段階を分ける。Nymphの活動決定、Core経由のみの通信原則、ハイブリッド実行の将来対応は従来方針を維持する。

上段はv0.2採用時点の記録である。その後のR12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）で通信原則を更新し、Coreが管理・許可した直接通信を採用した。この後続判断はv0.2のRuntime契約・実装・受入結果を変更しない。

### 残る判断事項

v0.3以降の登録・着脱、通信・IPC、活動の時刻・期間・優先度、契約全体の互換性と配布分割。今回の状態はRuntimeのライフサイクル状態であり、将来のTaskManagerの活動状態を定めるものではない。

### 根拠

R11の実施指示、ロードマップV0.2、Issue #22〜#25。技術的な参照：[Python保守状況](https://devguide.python.org/versions/)、[asyncioのタスクとキャンセル](https://docs.python.org/3.12/library/asyncio-task.html)、[非同期unittest](https://docs.python.org/3.12/library/unittest.html#unittest.IsolatedAsyncioTestCase)、[Hatchのビルド設定](https://hatch.pypa.io/latest/config/build/)。

---

<a id="section-24"></a>

収録元 `docs/adr/0015-core-authorized-direct-communication.md`

## ADR 0015 Coreが許可する直接通信の採用

### 状態

採用。採用日2026年11月20日。判断者はプロジェクト所有者（ユーザー）。R12「直接通信の緩和は採用ください」に基づき、既存の緩和案である「Coreが管理・許可した接続ではSubsystem間の直接通信を認める」を採用する。記録・資料同期は子Issue [#34](https://github.com/Tao-pyth/nymph-toolkit/issues/34)で追跡する。

ADR 0003（`docs/adr/0003-communication-routing.md`）の「通信はCore経由のみ」という制約と「緩和は未採用」という状態を置き換える。ADR 0003の当初判断・経緯は履歴として保持する。具体的な許可範囲・API・通信方式の採用や実装完了を意味しない。

### 背景

当初はCore経由のみを採用し、その後、軽量性やリアルタイム処理を考慮してCoreが許可する直接通信を検討した。R2・R4・R5の時点では緩和案を正式採用していなかったため、ADR 0003で実装前の判断として残した。R12で緩和の採用指示があり、採否の未決状態を解消する。

### 決定

- Core中心構成を維持し、Coreが接続を管理・許可した範囲でSubsystem間の直接通信を認める。
- Coreによる接続の管理・許可と、個々のデータや呼び出しの仲介を区別する。許可した直接経路では、通信のたびにCoreを経由することを必須としない。
- Core経由の通信も引き続き利用できる。どの用途にどの経路を使うかは、対象の契約と許可条件を具体化して決める。
- 登録・照会や相手への参照を得たことだけでは、直接通信を許可されたことにならない。接続の許可とその適用範囲を契約として明示する。
- Nymphの活動決定とCoreの実行管理の境界、Subsystem・Adapterの着脱、ハイブリッド実行、軽量なメソッド呼び出しとasyncioの方向性は維持する。

### 影響と適用

| 対象 | 今回の採用による扱い |
|---|---|
| Coreが毎回メソッドを呼ぶ経路 | 引き続き選択可能 |
| 通信をCoreへ仲介するProxy | 引き続き候補。Proxyの具体的な採用は未決 |
| Coreが管理・許可したSubsystem間の直接呼び出し | 緩和の対象として採用。接続対象・許可条件・APIの詳細を決めてから実装する |
| 直接ストリーム、Adapterを含む経路 | 個別の適用範囲と契約は未決。音声やAdapterの全経路を一括承認したものではない |
| Coreの許可を経ない任意の相互接続 | 今回の採用範囲に含めない |

Registryは登録・識別と利用可否、Connectionsは接続・通信の管理という既存の責務整理を基に、両者の境界を具体化する。v0.3の設計課題 [#27](https://github.com/Tao-pyth/nymph-toolkit/issues/27)では、照会と接続許可を区別し、解除・再登録による接続への影響をv0.4へ引き継げるようにする。v0.4の親課題 [#4](https://github.com/Tao-pyth/nymph-toolkit/issues/4)で許可条件と通信契約を具体化する。

今回の変更は設計判断と資料の同期であり、Connectionsの実装をv0.3へ前倒ししない。公開済みv0.2のRuntime・Contractsと受入結果は変更しない。直接通信の実装・性能検証は未実施である。

v1.xの接続契約とSubsystem連携にもこの採用方針を適用する。配布パッケージの同梱・分割から経路の許可を推定しない。

### 実装前に残る判断

| 判断対象 | 状態・判断時点 |
|---|---|
| 接続元・接続先、許可する操作・用途・経路 | 要決定。Connectionsの対象経路を実装する前 |
| 許可の申請・判定・記録・参照方法とAPI | 要決定。静的設定・動的処理などの方式は未採用 |
| 接続確立、状態把握、解除・許可撤回の具体的な責任分担 | 要決定。Coreの管理方針に沿って各契約へ割り当てる |
| 解除・再登録後の参照、通信中の取り外し、切断時の通知 | 要決定。Registryとの境界をv0.3で整理し、通信動作をv0.4以降で具体化 |
| 同期・非同期境界、失敗・タイムアウト、通知方法 | 要決定。Connectionsの対象範囲を実装する前 |
| 同一・別プロセスへの適用範囲、IPC方式 | 要決定。ハイブリッド実行の既存方針に沿って段階ごとに判断 |
| Adapter経路、直接音声ストリーム等への適用 | 要決定。対象機能の設計時 |
| 公開手段での許可・拒否確認、解除後の検証方法 | 要決定。A04などの対象受入を具体化する時 |

任意のPythonコードやOS通信を遮断する隔離機能の採用は、本判断に含めない。接続契約による許可管理と、実行環境全体の隔離を区別する。

### 検証への反映

A04では、具体化したCore経由・許可された直接経路の通信、許可条件の内外、解除・切断・相手側失敗を検証する案を用いる。許可条件や期待する失敗結果を先に記録し、未決事項をテストの中で暗黙に確定しない。経路別の性能優位は実測するまで断定しない。

### 根拠

R12の明示的な採用指示、R4の「Coreが許可した直接通信」という既存提案、ADR 0003の判断履歴。Docsの根拠表（`docs/README.md`）。許可条件・API等の詳細はユーザーの今回の指示だけでは決定していないため、上表へ残す。

---

<a id="section-25"></a>

収録元 `docs/adr/0016-v0.3-registry.md`

## ADR 0016 v0.3のRegistryと複数対象のライフサイクル

### 状態・根拠

採用。記録日2026年11月20日。R13「v 0.3まで進行してください」の実施に伴う設計・実装判断としてCodexが記録する。過去の会話で既に確定していた仕様とは区別する。親Issue #3、設計 #27、Contracts #28、Registry #29、依存管理 #30、Runtime連携 #31、受入 #32、公開 #33を対象とする。

ADR 0001・0005のv0.3範囲を具体化する。ADR 0014のRuntime APIを維持し、ADR 0015のCoreが許可する直接通信の採用を前提とする。Connectionsの許可API・経路実装は本ADRで決定しない。

### 背景

v0.2のRuntimeは一つのRuntimeServiceを実行する。v0.3では登録情報の管理と、登録対象の初期化・実行・後処理を分離する。複数対象はRuntimeServiceを満たすModuleGroupで束ね、既存Runtimeから実行できるようにする。

### RegistryとContracts

- `ModuleKind` は `SUBSYSTEM` と `ADAPTER`。`ModuleSpec(module_id, kind, requires)` は不変の登録情報で、requiresは必須依存先のID集合へコピーする。IDは前後空白のない空でない文字列で、大文字小文字を区別する。呼出側が指定し、自動生成しない。
- `Registry` は作成したスレッドで使う同期APIとする。操作中にawaitや利用側コールバックを呼ばず、イベントループの生成・所有を行わない。別スレッドでの操作・照会は `RegistryStateError` とする。
- `register(spec)` と `unregister(module_id)` は成功時に `RegistryUpdate(revision, changes)` を返す。各 `RegistryChange` はIDと変更前・変更後の `RegistryEntry` を含む。新規登録のbefore、解除のafterはNone。影響を受けた依存先利用可否の変化も同じ結果に含め、ID順で返す。これを呼出側への変更通知とし、イベントバス・永続キュー・購読APIは追加しない。
- `get(module_id)` と `entries()` は不変のスナップショットを返す。entriesはID順。実体・通信ハンドルを返さない。`revision` は成功した変更ごとに増え、失敗では変えない。
- Entryの `generation` は登録時のrevisionで、解除後に同じIDを再登録すると変わる。過去のEntryは取得時点の情報として保持され、現在の照会結果と混同しない。通信許可の失効方式はv0.4へ残す。
- 重複登録は `DuplicateModuleError`、未登録IDの照会・解除は `UnknownModuleError`。自己依存・循環依存は `DependencyCycleError`。いずれもRegistryErrorの派生とし、失敗時は登録状態・revisionを変更しない。型やIDなど不正な登録値はTypeError／ValueErrorで通知する。

### 機能的依存の採用範囲

依存はモジュールID単位の必須依存として採用する。Capability単位、任意依存、バージョン条件、自動代替は後続判断とする。具体的な相手実装へ依存しない。

依存先が未登録でも登録できる。Entryの `missing_dependencies` に推移的に不足するIDを含め、空なら `available` がTrueになる。availableは「必要な依存先が登録されている」ことを表し、起動済み・稼働中・通信許可済み・正常稼働を意味しない。

Registry単独では依存先の解除を許可する。解除によって直接・間接の依存元を利用不能とし、操作結果へ変化を含める。依存先を再登録した場合も再計算して通知する。登録済み部分の依存グラフに循環を作る登録は拒否する。例えばA→BをB不在のまま登録することはできるが、続けてB→Aを登録することはできない。

### ModuleGroupとRuntimeの連携

`ModuleGroup` はRuntimeServiceを満たすCore Runtime側の構成要素であり、第5のCore責務を追加しない。内部にRegistryとID別のサービス実体を保持し、`register(spec, service)`、`unregister(id)`、`get(id)`、`entries()`、`revision` を公開する。Registryの変更結果はそのまま返す。サービス実体や変更可能な内部Registryを公開しない。

1. Runtimeの起動前にダミーSubsystem・Adapterを登録する。依存先不在の登録はできるが、起動前に全依存が揃う必要がある。
2. ModuleGroup.startで構成を固定し、不足依存を検査する。不足時は `DependencyUnavailableError` を通知し、サービスのフックを一つも実行しない。
3. 依存先から順にstartを呼ぶ。同順位はID順。startに入った対象は部分初期化の後処理対象に含める。すべての初期化が成功してからrunへ進む。start内で他対象のrun開始を待ってはならない。
4. ModuleGroup.runは各対象のrunを同一イベントループのタスクとして実行する。全対象が正常終了したらID別の戻り値をdictで返す。一つが失敗した場合はRuntimeへ通知し、Runtimeのstop経由で残りを停止する。対象自身による予期しないCancelledErrorも失敗に含める。
5. ModuleGroup.stopは所有する実行タスクを取消して完了を待ち、初期化に入った対象のstopを逆順に一度ずつ呼ぶ。途中の通常の失敗があっても他対象の後処理を続ける。サービス自身が所有するタスク・接続はサービスのstopが終了させる。

失敗は `ModuleFailure(module_id, phase, exception)` を `ModuleGroupFailure` にまとめ、外側のRuntimeFailureから追跡できる。先に通知したrun失敗をstopで重複報告せず、後から発生したrun失敗・後処理失敗も失わない。プロセス制御例外はv0.2と同様に通常の失敗契約の対象外とする。

初期化中のCancelledErrorは、要求された停止か否かを既存Runtimeが判断できるよう、そのまま伝播させる。元例外のnoteへ初期化中の対象IDを付け、予期しない取消の場合は外側のRuntimeFailureから確認できる。ModuleGroupのstart・run・stopは同じRuntimeの監督タスクで呼ぶ。別のRuntimeによる共有・二重起動を拒否し、その失敗の後処理が元の実行を停止しないようにする。

### 着脱・取消・状態の境界

稼働中の実体着脱はv0.3で採用しない。Connectionsの解除・許可撤回・通信中処理を未決のまま実体交換に組み込まないためである。ModuleGroupはstartに入ってからstopが終わるまで登録・解除を `RegistryStateError` で拒否する。Registry単独は同期の登録情報管理として利用できる。

ModuleGroupは一回の実行に用いる。停止後は明示的な解除ができ、登録情報は解除するまで残る。実行開始後の追加登録と再起動は拒否し、次の実行には新しいModuleGroupとRuntimeを用意する。登録状態を稼働状態と混同しない。

Runtimeの開始待機・停止待機が取消された場合もADR 0014の後処理契約に従う。開始・停止と着脱が競合した場合は、同期の構成固定を境に操作を許可・拒否する。stop完了までは固定を解除しない。協調的停止の制約は維持し、無応答の処理を強制終了する機能は追加しない。

### 受入と具体例

| シナリオ | 期待結果 |
|---|---|
| A→B、B→Cを先に登録しCが不在 | A・Bのmissing_dependenciesにC、available=False |
| Cを登録／解除／再登録 | A・Bの利用可否変化を各RegistryUpdateで通知し、Cの再登録generationは変わる |
| 重複・未登録解除・循環を作る登録 | 例外、状態とrevisionは不変 |
| 過去の照会結果を保持して変更 | 旧スナップショットは不変、最新照会で変化を観察できる |
| 不足依存のあるModuleGroupを起動 | 初期化フック0回で失敗を通知 |
| A→Bの正常起動と停止 | B→Aで初期化、A→Bで後処理。残存所有タスク0件 |
| 初期化途中失敗／実行失敗／複数後処理失敗 | 対象ID・段階・元例外を保持し、初期化に入った対象を後処理 |
| 起動中・実行中・停止中の着脱 | 状態を変えず拒否。停止完了後は明示解除できる |

これらとv0.2の回帰、wheel・sdistからのダミー実行、Windows/Linux・CPython 3.12〜3.15をA03の検証対象とする。時刻待ちに依存せずEventで同期する。

### 未採用・延期事項

稼働中の実体着脱、Capability・任意依存・版制約、永続化、自動探索・自動復旧・代替機能、スレッド間同期、IPC、Connections、TaskManager、本番Subsystem・Adapterを追加しない。Coreが管理・許可した直接通信はADR 0015で採用済みだが、その実装・許可契約はv0.4以降に残す。Nymphの意思決定、PC状況取得Adapter、複製・移植・伝播の初期対象外という境界を維持する。

---

<a id="section-26"></a>

収録元 `docs/roadmap.md`

## NTK開発ロードマップ

最終目標は、経験を通じて知識・言語・行動能力・人格を発達させ、自ら考え、学び、活動できる人工人格Nymphである。R7のProject Vision（`docs/vision.md`）を到達像とし、完成を特定のバージョンへ固定しない。以下の各段階は、その基盤と能力を検証する開発計画である。

**GitHub公開＝V0.1、Core機能完成＝V0.9は確定目標。未着手段階の機能配分、作業順、完了条件の具体化は提案である。** v0.2はR11・ADR 0014、v0.3はR13・ADR 0016で採用範囲を具体化した。予定日や所要期間は設定せず、完了条件と判断記録に基づいて進める。根拠はR3。v0.1〜v0.9のCore検証では本番Subsystem・Adapterの代わりにダミーを使う。

既存のV0.1・V0.9はv0.1.0・v0.9.0の節目を表す。R5で示されたv1.0.0の接続契約整備という目標と、v1.1.0〜v1.10.0の未確定の開発計画案を後半に追記する。v1.xのSubsystem名・Adapter名は暫定名称であり、名称・順序・機能配分は今後変更される可能性がある。

全体原則は、Nymphが活動内容・時刻・期間・変更と活動の価値・優先度を判断し、Coreが実行を管理することである。Coreの実行可否判定、競合検出、採用した優先度規則に基づく機械的な順序処理を、この境界に従って設計する。R4で境界を再確認し、具体的な優先度機能や変更操作は採否の判断対象として追記した。

未着手のv0.4〜v0.8の機能配分は、理由と依存関係・受入条件への影響を記録して再配分できる。V0.1とV0.9の確定目標に対応する完了条件を維持して計画を更新する。

R6で採用した配布方針は、単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて分割することである。各拡張の設計時に依存関係・独立更新・単独配布の必要性を確認する。個別の分割対象・時期と、ロードマップの節目を分割後の各配布物のバージョンへどう対応させるかは未決である。ADR 0009（`docs/adr/0009-package-distribution.md`）

### マイルストーンとIssueへの展開

R10・ADR 0013（`docs/adr/0013-milestone-issue-workflow.md`）により、各バージョンをマイルストーンに整理し、親Issueを設定したうえで、対応単位ごとの子Issueを登録してからコード変更へ進む。各段階の着手条件に、この運用上の前提を加える。登録済みの対応表と手順はIssue運用（`docs/issue-workflow.md`）にある。

マイルストーン化は機能配分案や未決の仕様を採用する手続ではない。将来段階の子Issueは範囲を具体化してから追加し、実装に必要な判断を先に記録する。公開済みv0.1.0は完了記録として扱い、以降の段階には期限を設定しない。

### 段階の一覧

| 段階 | 主な成果物 | 関連ADR | 受入項目 |
|---|---|---|---|
| 公開準備 | Docs、Git設定、初回コミット、公開前判断欄 | 0001・0005 | P0 |
| V0.1 GitHub公開 | 公開リポジトリ、タグ、リリース記録 | 0001・0005 | A01 |
| V0.2 Runtime | Python開発環境、起動・停止、ダミー実行 | 0002・0005・0009 | A02 |
| V0.3 Registry | 登録、識別、解除、必須依存・変更通知、ModuleGroup | 0001・0005・0016 | A03 |
| V0.4 Connections | 許可契約の具体化、同一プロセスの通信 | 0002・0015と後続判断 | A04 |
| V0.5 TaskManager基本 | 活動入力、時間概念の整理、予定と実行状態の管理 | 0004 | A05 |
| V0.6 活動変更 | 時間・優先度変更、中断・再開、取消・終了の採否と採用範囲の実装 | 0004 | A06 |
| V0.7 ハイブリッド実行 | 別プロセス通信・活動実行 | 0002・0003 | A07 |
| V0.8 統合検証 | 4責務を通す検証、失敗時の後処理 | 0001〜0005 | A08 |
| V0.9 Core機能完成 | 公開API資料、受入結果、リリース記録 | 0001〜0005とv0.9対象の後続ADR | A09 |

受入項目の手順と期待結果はacceptance.md（`docs/acceptance.md`）に記載する。各段階の判断はADR索引（`docs/adr/README.md`）から追跡する。

### 公開準備

- **着手条件** — R2・R3を根拠とした資料と既存ファイルを確認できる。
- **作業** — 確定事項と未決事項を記載し、Docs・ADRを配置する。除外・改行設定を整え、Gitを `main` で初期化し、作成者設定、差分確認、初回コミットを行う。
- **成果物** — 単一配布用引継ぎ書、個別Docs・ADR、Git履歴、公開前判断欄。
- **判断事項** — 公開先はR9・ADR 0012で `Tao-pyth/nymph-toolkit` のpublic公開、ライセンスはR8・ADR 0011でApache-2.0を採用済み。公開対象へのLICENSE収録と適用範囲を確認し、作業結果をreleaseへ記録する。
- **完了条件** — P0を確認でき、公開前判断欄が埋まっている。未記入項目がある間は公開準備として扱う。

### V0.1 GitHub公開

- **着手条件** — 公開準備の完了条件を満たし、公開するコミットが確認済み。
- **作業** — `nymph-toolkit` をGitHubへ公開し、remoteを確認してpushする。READMEに実装状況を明記し、CHANGELOG、`v0.1.0` タグ、リリース記録を整える。
- **成果物** — GitHubから読める資料一式、公開URL、リリース対象コミット。
- **判断事項** — R9で採用したpublic公開と、資料中心・Core未実装という公開内容が一致することを確認する。
- **完了条件** — A01を満たす。Core未実装の状態で公開する場合はその状態を明記する。

### V0.2 Runtime

R11の実施指示により、この段階の範囲をADR 0014（`docs/adr/0014-v0.2-runtime.md`）で具体化した。CPython 3.12以上、Core・Contractsの単一配布、Runtimeの一回のライフサイクルと失敗・後処理を採用する。以降の段階の配分案は維持する。

受入記録（`docs/validation/v0.2.md`）と[v0.2.0リリース](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.2.0)に完了結果を記載する。後続のv0.3は親Issue #3とADR 0016に従う。

- **着手条件** — V0.1の記録とCore初期実装の範囲を確認できる。
- **作業** — 対応Python版、依存・テストツール、イベントループ所有者、起動・停止APIを決める。ルートの `pyproject.toml` でCoreとContractsを一つの配布パッケージとして扱い、契約は必要なものから追加する。実装・テスト用ディレクトリを作り、asyncio上でダミーを開始・終了する。
- **成果物** — 最小Runtime、ダミー、テスト、再現可能なセットアップ・検証コマンド。
- **判断事項** — 起動失敗や停止要求を呼出側へ伝える方法と停止完了の意味。
- **完了条件** — A02を満たす。READMEとdevelopmentのコマンドで実行できる。

### V0.3 Registry

R13の実施指示により、この段階の契約をADR 0016（`docs/adr/0016-v0.3-registry.md`）で具体化した。同期Registry、ID単位の必須依存、不変スナップショットと変更通知、既存Runtimeから複数対象を動かすModuleGroupを採用する。実体の稼働中着脱はConnectionsの解除・失効契約を設計する後続段階へ残し、v0.3では実行前の着脱と、起動から停止完了までの構成固定を検証する。

実装と検証結果はRegistryの使い方（`docs/registry.md`）・受入記録（`docs/validation/v0.3.md`）に記載する。

- **着手条件** — Runtimeを起動・停止できる。
- **作業** — ADR 0016に従い、ダミーSubsystem・Adapterの登録、識別、状態照会、解除、必須依存の再計算と変更通知を実装する。
- **成果物** — Registry、Contracts、ModuleGroup、着脱・失敗・取消シナリオ、配布検証と資料。
- **採用判断** — ID単位の必須依存と不変スナップショット、操作結果による利用不能の通知を採用。実体の稼働中着脱は延期し、ModuleGroup起動から停止完了まで構成を固定する。単体完全動作や代替機能は必須としない。
- **完了条件** — 具体化したA03を満たし、登録・依存先解除・再登録の結果と、複数対象の初期化・実行・後処理を採用契約どおり検証できる。

### V0.4 Connections

- **着手条件** — Registryが利用でき、ADR 0015の採用方針を基に、対象経路の許可条件・管理契約を実装前に具体化する。
- **採用済みの通信方針** — R12・ADR 0015でCoreが管理・許可した接続の直接通信を認める。Core経由も利用できる。接続の管理・許可と通信の仲介を区別し、許可対象・API・解除時の動作は後続判断へ残す。Proxyや直接音声ストリームの具体的な採用は未決である。
- **作業** — 許可経路、呼び出し契約、同期・非同期境界、要求・結果・失敗通知を決め、同一プロセスで実装する。軽量なメソッド呼び出しを活かす。
- **成果物** — Connections、入力と受信・結果の照合テスト、経路条件の検証。
- **判断事項** — 接続元・先、許可条件と許可管理API、接続状態の把握、許可撤回、相手の解除・再登録、接続失敗、受信側例外の扱い。通信中の解除と通知、タイムアウト・再試行の必要性を判断する。
- **完了条件** — A04を満たす。具体化したCore経由・許可された直接経路、許可条件の内外、解除・撤回後の動作と失敗通知を採用記録に基づいて確認できる。

### V0.5 TaskManager基本

- **着手条件** — Runtime・Registry・Connectionsの採用範囲が確認できる。
- **作業** — ダミーNymphから活動内容、開始時刻、期間を受け取り、予定と実行状態を管理する。時刻・期間・経過時間・実行時間の意味と計測条件、期間終了時の動作、状態遷移を決める。
- **成果物** — 活動管理の最小実装、入力と状態・実行結果を照合するテスト。
- **判断事項** — 過去の時刻、不正な期間、実行側の早期終了や失敗を扱う契約。期間満了に使う時間、待機時間の扱い、中断・再開を採用する場合の計時との関係。
- **完了条件** — A05を満たす。Nymphの決定からCoreの実行結果まで追跡でき、Coreの処理が指定値・実行状態に基づくことを確認できる。優先度機能を採用する場合はNymphの入力に従う機械的処理として検証する。

### V0.6 活動変更

- **着手条件** — 基本的な活動の入力・開始・終了を検証できる。
- **作業** — 開始時刻の繰り上げ・延期、実行期間の延長・短縮、優先度変更、中断・再開、取消・終了を採否の判断対象として列挙する。各操作の採用・見送り・継続検討と理由、対応状態を記録し、採用範囲を実装してNymphの指示と結果を照合する。
- **成果物** — 変更処理、競合や解除との関係を定めるADR、検証シナリオ。
- **判断事項** — 開始との競合、同じ活動への複数変更、終了後の変更、活動中の取り外し。Nymphが指定する優先度に基づく実行枠・待機順序、同順位や競合時の機械的処理、取消・終了の状態遷移を実装前に決める。活動の価値評価と優先度の生成・変更はNymphが担う。
- **完了条件** — A06を満たす。各操作の採否と対応範囲、範囲外の入力への応答を説明できる。採用した優先度変更はNymphの入力に従い、実行不能や競合を採用契約に従って通知できる。

### V0.7 ハイブリッド実行

- **着手条件** — 同一プロセスで通信・活動・変更を確認できる。
- **作業** — IPC方式、シリアライズ、配置間契約の共通化の有無と範囲、子プロセスの管理責任を決める。別プロセスのダミーで通信と活動を実行する。
- **成果物** — 別プロセス実装、配置ごとの契約、切断・終了シナリオ。
- **判断事項** — 切断中の要求、プロセス終了時の活動状態、再接続・再試行の採否。
- **完了条件** — A07を満たす。両配置がそれぞれ採用契約を満たし、差異と未対応範囲を説明できる。

### V0.8 統合検証

- **着手条件** — 4責務と両実行配置が利用でき、失敗時動作の採用範囲が記録されている。
- **作業** — 起動から着脱、接続、活動、変更、終了までを通す。部分失敗、停止時の後処理、再実行を確認する。永続化・再試行・自動復旧は採否を記録し、採用した範囲を検証する。
- **成果物** — 統合シナリオ、受入結果、修正済み不具合と残課題。
- **判断事項** — 未達項目の修正方針とV0.9の具体的な受入範囲。固定の性能値は必要性と測定条件を決めてから設定する。
- **完了条件** — A08を満たす。タスク・プロセス・接続の残存状態を採用した停止仕様と照合できる。

### V0.9 Core機能完成

- **着手条件** — V0.8までの採用機能の検証結果があり、完了判定を妨げる未決事項が解消されている。
- **作業** — 公開APIの入出力・失敗通知・ライフサイクルを文書化し、実装と照合する。新しい作業環境でダミー検証を再実行し、リリース対象の結果と残課題を記録する。
- **成果物** — 合意したCore機能、再現手順、API資料、受入結果、CHANGELOGとリリース記録。
- **判断事項** — 既知の制約が合意した完成条件を妨げる場合は修正または範囲の再合意を行い、履歴を残す。
- **完了条件** — A09を満たす。ハイブリッド実行、着脱、通信、Nymphが決めた活動と変更の実行管理をダミーだけで検証できる。

V0.9の完成対象は合意したCore機能である。将来のPC状況取得Adapterと複製・移植は、この初期ロードマップの対象外とする。

### v1.0.0以降のロードマップ案

**以下はR5に基づく設計提案である。** v1.0.0でCoreとSubsystem・Adapterの接続契約を大きく形作る目標は確定している。契約詳細、Subsystem・Adapterの名称、実装順序、各バージョンへの機能配分、受入条件は未確定である。日付・開発期間・工数の見積もりは設定しない。

#### リリース運用案

| リリース区分 | 主目的 |
|---|---|
| v1.0.0 | CoreとSubsystem・Adapterの接続契約確立 |
| 奇数マイナーバージョン | 新規Subsystemの実装 |
| 偶数マイナーバージョン | Subsystem間連携の見直し・強化、Adapterの実装・拡張 |
| パッチバージョン | 不具合修正、小規模改善、互換性を維持した個別修正 |

奇数・偶数の区分は主目的を示す開発規則案で、必要な補助実装や最低限の統合テストを各段階に含められる。偶数マイナーでの新規Adapter追加は必須としない。公開APIの破壊的変更や新機能の扱いは、Semantic Versioningとの整合性を別途判断する。運用案の状態はADR 0007（`docs/adr/0007-v1-release-roadmap.md`）、互換性の判断はrelease.md（`docs/release.md`）を参照する。

#### 推奨する機能配分

| バージョン | 主な開発対象（暫定名称） | 開発目標の案 | 検証案 |
|---|---|---|---|
| v1.0.0 | Core接続契約 | Subsystem・Adapter向け共通接続基盤 | B00 |
| v1.1.0 | Memory Subsystem | 経験・知識の最小保存と取得 | B01 |
| v1.2.0 | Document Adapter | 文書取得とMemory連携 | B02 |
| v1.3.0 | Cognition Subsystem | 初期の言語・概念学習 | B03 |
| v1.4.0 | Text Interaction / Web Adapter | 学習・訂正・文章観測の統合 | B04 |
| v1.5.0 | Agency Subsystem | 自律的な活動計画・意思決定 | B05 |
| v1.6.0 | TaskManager連携強化 | 自律活動の実行・変更・状態把握 | B06 |
| v1.7.0 | Persona Subsystem | 人格特性の保持・参照・修正 | B07 |
| v1.8.0 | Persona連携強化 | Agencyとの統合・人格特性の反映 | B08 |
| v1.9.0 | Sleep Subsystem | 記憶統合・忘却・夢・人格更新の初期機能 | B09 |
| v1.10.0 | Sleep連携・Discord Voice Adapter | 睡眠循環の統合と音声観測の導入 | B10 |

各段階の実装内容と受入条件は設計・ADRで具体化する。上表の検証IDはacceptance.md（`docs/acceptance.md`）の案に対応し、機能完成を宣言するものではない。

#### v1.0.0 — Core接続契約

- **着手時に確認すること** — v0.9.0のCore受入結果、既存API、ADR 0015と後続の通信経路判断を確認する。
- **検討・成果物の案** — Module Contract、Lifecycle Contract、Capability Contract、Communication Contract、Task Contract、Error Contractを具体化する。Coreと同じ配布物のContractsを公開接続契約として体系化し、公開API資料、接続用の開発補助機能、ダミーを用いた契約テストを整備する。本番Subsystemの完成は必須条件としない。
- **判断と検証** — 必須の契約項目、実行配置ごとの適用範囲、互換性境界、補助機能を決める。Subsystem・Adapterの接続、ライフサイクル、能力、通信、活動、失敗通知を採用範囲で検証する。ADR 0006・B00へ記録する。

#### v1.1.0〜v1.2.0 — Memoryと文書入力

- **着手時に確認すること** — 保存・取得に必要な接続契約と検証可能なCore機能を確認する。
- **検討・成果物の案** — v1.1.0では経験・知識の最小保存・取得を実装する。v1.2.0ではDocument Adapterから文書を取得し、Memoryとの連携を検証する。複雑な知識グラフや高度な記憶統合は初期の必須条件にしない。
- **判断と検証** — 保存対象・形式、取得方法、文書形式、取り込み失敗時の扱いを決める。小さな経験・知識と文書入力から保存結果・取得結果を照合する。ADR 0008・B01・B02を基に後続ADRで具体化する。

#### v1.3.0〜v1.4.0 — Cognitionと言語観測

- **着手時に確認すること** — Memoryの保存・取得と、語彙・構文・概念の初期学習を検証する入力範囲を確認する。
- **検討・成果物の案** — v1.3.0でCognitionの初期学習機構を検討する。v1.4.0でText InteractionおよびWeb Adapterを通じ、文章観測、学習、出力、ユーザーからの訂正を検証できる構成を目指す。既存LLMを言語理解・文章生成の中核に利用することは現在のNTKの研究方針に含めない。
- **判断と検証** — 学習方式、評価に用いる入力と観測結果、訂正の反映方法、Webの取得範囲を決める。能力が未完成の場合は対応する範囲を明示して試す。ADR 0008・B03・B04を基に記録する。

#### v1.5.0〜v1.6.0 — Agencyと活動管理

- **着手時に確認すること** — 活動決定に利用できる情報と、Task Contract・TaskManagerの採用機能を確認する。
- **検討・成果物の案** — v1.5.0でAgencyが活動内容、開始時刻、期間、優先度、変更を決める機構を検討する。v1.6.0でCore TaskManagerとの連携を強化し、登録・実行・状態追跡・変更要求の適用を検証する。
- **判断と検証** — Agencyの決定方式と、Coreへの入力・結果・競合通知の契約を具体化する。v0.xの変更操作・優先度機能の対応範囲を確認し、必要な拡張をADRに記録する。Coreが活動の価値を判断しない境界をADR 0004・0008とB05・B06で確認する。

#### v1.7.0〜v1.8.0 — Personaと人格特性

- **着手時に確認すること** — 人格特性の参照と外部からの修正値を受け取る接続契約を確認する。
- **検討・成果物の案** — v1.7.0でPersonaが人格特性をパラメータとして保持・返却し、外部の修正値を契約に沿って適用する機構を検討する。Persona自身が自発的に人格修正処理を開始する構成にはしない。v1.8.0でAgencyなどとの連携を強化し、行動選択への反映を検証する。
- **判断と検証** — パラメータ、修正値の形式、参照・更新の適用条件を決める。修正要求から値の更新、Agencyの参照・行動選択までを追跡する。ADR 0008・B07・B08を基に記録する。

#### v1.9.0〜v1.10.0 — Sleepと音声観測

- **着手時に確認すること** — Memory、Agency、Personaと採用した接続契約、および音声観測の技術的な成立条件を確認する。
- **検討・成果物の案** — v1.9.0で経験統合、忘却、夢生成、人格修正値の生成を段階的に検討する。SleepはPersonaの内部状態を直接変更せず、契約を通じて修正値を提供する構成を基本案とする。v1.10.0で睡眠循環を統合し、Discord Voice Adapterによる他者同士の音声会話の観測を導入する案とする。
- **判断と検証** — Sleepの初期処理範囲、修正値の生成・適用、睡眠循環との関係を決める。音声観測はASRによる文字起こしと音響特徴の併用を基本案とし、音声の直接意味理解を初期要件にしない。音声受信・ASRは必要に応じて先行試験実装できる案とする。
- **音声の扱い** — 取得・保存・学習について、参加者への告知、適切な同意、権限、保持・削除方針を考慮する。先行試験も扱う音声と利用条件を明確にし、具体的手順を設計・ADRへ記録する。ADR 0008・B09・B10を基に検証する。

#### 実装順序とAdapter追加の考え方

推奨するSubsystemの順序は、Memoryで保存基盤を用意し、Cognitionで経験からの言語・概念学習、Agencyで活動決定、Personaで人格特性の行動への反映、Sleepで統合・忘却・人格変化の循環へ進むものである。依存関係、技術検証結果、研究上の優先順位に応じて段階の入れ替えを提案できる。

Adapterの推奨順序は、Document Adapter、Text Interaction Adapter、Web Adapter、Discord Voice Adapter、Desktop Adapterとする。各名称は暫定である。必要なSubsystemの能力に応じて段階的に実装し、未完成の機能がある場合は対応範囲を限定して検証する。

Desktop AdapterによるPC全体の稼働状況取得・操作は将来課題とし、v1.10.0までのロードマップには割り当てない。データの複製・移植・伝播機構は初期開発の対象外である。配分や名称を変更する際は、理由・依存関係・検証への影響をADRと関連Docsへ記録する。

### 長期ビジョンへ向けた判断

R7で示す自然な日本語での継続的な交流、Self-Model、内部状態・動機・情動、経験に基づく人格変化、睡眠・夢、権限下のPC操作、再起動後の継続性は長期の到達目標である。v1.10.0で人工人格が完成するという意味にはしない。

各能力について、研究上の仮説、必要な接続契約、観測・評価方法を具体化し、後続ADRで段階の採用範囲を決める。夢の記憶を次の睡眠時に失効させる構想や、記憶・発達状態を復元する方法も、この判断に含める。現行のCore完成条件とv1.xの機能配分を一括して拡張しない。最終的な評価領域はvision、段階ごとの受入はacceptanceで管理する。

---

<a id="section-27"></a>

収録元 `docs/acceptance.md`

## 受入基準案と検証記録

以下は各段階の**受入案**である。v0.2のA02はADR 0014、v0.3のA03はADR 0016で具体化する。他の段階の操作例や観察方法は引き続き提案とし、対象のAPI・失敗時動作を判断してから期待結果を具体化する。

### バージョン別シナリオ

今後のコード変更は、R10・ADR 0013（`docs/adr/0013-milestone-issue-workflow.md`）の運用上の前提も確認する。対象マイルストーン・親Issue・子Issueが変更前に登録され、親子関係と対象範囲を追跡できること、完了時に変更コミットまたはPR・検証結果・残課題を子Issueへ記録することを確認する。公開済みv0.1.0へ遡及して適用しない。

| ID・段階 | 根拠 | 入力・操作と検証手順 | 合格と判断できる結果 |
|---|---|---|---|
| P0 公開準備 | R3・R8・ADR 0011 | DocsとADRの状態表示・リンクを確認。Gitの対象ファイルと初回コミットを確認し、releaseの判断欄と照合する。LICENSE原文とApache-2.0の適用範囲を確認する | 単一文書と個別Docsの内容が整合し、公開対象が説明できる。公開先・公開範囲が決定済みで、採用したライセンスと必要な表示が公開対象に含まれる |
| A01 V0.1 | ADR 0001・0005 | 公開URLとタグを開き、READMEから各Docsへ進む。対象コミットを新しいフォルダへcloneする | 資料が取得でき、実装状況と未決事項が読める。`v0.1.0` とリリース記録が同じコミットを指す |
| A02 V0.2 | ADR 0002・0005 | development記載の環境構築後、Runtimeを起動し、ダミー処理を一度実行して停止する。採用した起動失敗も再現する | 開始・処理結果・停止完了を確認できる。失敗が契約どおり呼出側へ通知される |
| A03 V0.3 | ADR 0001・0005・0016 | ダミーSubsystemとAdapterの登録・照会・解除・再登録、必須依存の変化、ModuleGroupの初期化・実行・後処理を試す | スナップショット・変更通知・失敗時の状態が契約に一致する。構成固定を守り、失敗・取消でも必要な後処理と失敗情報を保持する。下記の具体化に従う |
| A04 V0.4 | ADR 0003の履歴・0015と後続判断 | 具体化したCore経由・許可された直接経路で要求と結果を照合。許可条件の内外を公開手段で試す。相手の解除・許可撤回・受信側失敗を採用契約に沿って再現する | 許可経路で受信を確認できる。許可条件の内外、解除・撤回後の動作、失敗通知が採用ADRに一致する |
| A05 V0.5 | ADR 0004 | ダミーNymphが活動A、開始T、期間Dを指定。時刻・期間・経過時間・実行時間を採用した定義で観察し、下記の責務境界も確認する | Nymphの入力と予定・実行結果を対応付けられる。期間満了の処理と計時が採用定義に一致し、Coreが活動の価値に基づいて指定値を変更しない |
| A06 V0.6 | ADR 0004と変更の後続ADR | 各操作の採否表を確認。採用した繰り上げ・延期、延長・短縮、優先度変更、中断・再開、取消・終了をダミーNymphから入力し、競合や終了後の要求も試す | 入力と変更結果を照合できる。優先度の処理はNymphの指定と採用規則に一致し、実行可否・競合の通知と時間計測を確認できる。範囲外入力への応答が契約に一致する |
| A07 V0.7 | ADR 0002・0015と後続判断 | 同一・別プロセスで通信・活動・変更を再現する。子プロセス終了や切断を起こす | 各配置が採用契約を満たす。共通部分と差異が記録され、失敗時の活動・接続状態を確認できる |
| A08 V0.8 | ADR 0001〜0005・0015と後続判断 | 起動→登録→接続→活動→変更→解除→停止のシナリオを両配置で行う。途中の失敗と、採用した再実行手順を試す | タスク・プロセス・接続の後処理が停止仕様に一致する。再実行時の状態が一貫し、採用した失敗時処理を再現できる |
| A09 V0.9 | v0.9対象の採用ADR | 新しい環境でv0.9対象の全採用シナリオを再現し、API資料・実装・結果を照合する | 合意したCore機能がダミーで検証できる。受入未達が解消され、既知の制約と残課題が明記されている |

A04の経路検証はCoreが提供する接続手段を対象とする。任意のPythonコードやOS通信を遮断する隔離機能の要件は未決である。

R12・ADR 0015でCoreが管理・許可した接続での直接通信を採用した。受入では、Coreによる接続の管理・許可と個々の通信の仲介を区別し、登録・照会だけを直接通信許可として扱っていないことを確認する。具体的な許可対象・API・解除時の期待結果は実装前の後続判断に基づく。直接通信の実装・実行検証は現時点では未実施であり、今回の採用判断をA04合格として扱わない。

テスト用の時計や短い期間を利用する方法は提案である。時刻、待機の許容差、入力形式は時計の採用記録に合わせる。未検証の実行配置や項目は「未検証」と明記し、全体合格に含めない。

### A02 v0.2の具体化

採用範囲の結果・再現手順・制約は受入記録（`docs/validation/v0.2.md`）にある。

ADR 0014（`docs/adr/0014-v0.2-runtime.md`）に従い、起動・ダミー実行・停止を検証する。正常終了と明示停止、開始前の停止、二重起動の拒否、初期化中の停止、待機側キャンセルと後処理継続、初期化・実行・後処理の各失敗と複数失敗を確認する。サービス内部からの自己待機と別イベントループからの制御を拒否し、無関係な呼出側タスクを停止しないことも確認する。

失敗時はphaseと元例外を照合する。部分初期化時もstopが一度実行され、終了後にRuntimeとダミーが所有するタスクが残らないことを、実際のイベントループ上で確認する。キャンセルに応答しないサービスを強制終了できるという合格条件は設けない。

wheelとsdistをビルドし、新しい仮想環境へwheelを通常インストールする。リポジトリ外の作業ディレクトリから公開importとダミーを実行し、ソースツリーの参照に依存しないことを確認する。sdistからの再ビルド、同梱LICENSE、配布名・版・Python下限・依存メタデータも照合する。

### A03 v0.3の具体化

ADR 0016（`docs/adr/0016-v0.3-registry.md`）に従い、次を検証する。

実施結果・再現手順・制限はv0.3受入記録（`docs/validation/v0.3.md`）にまとめる。

- Subsystem・Adapterの登録・ID順照会・解除・同一ID再登録とgeneration更新。
- 重複、未登録照会・解除、不正値、自己依存・循環登録の拒否と、失敗時の状態・revision維持。
- 直接・推移的な不足依存、依存先登録・解除・再登録による利用可否変化の通知。不変スナップショットと、稼働状態・通信許可との区別。
- 所有スレッド以外での操作・照会の拒否。
- ModuleGroupと既存Runtimeによる依存順初期化、全対象の実行、戻り値、逆順後処理。依存不足時はフックを実行しない。
- 初期化途中失敗、実行失敗、予期しないサービス側取消、複数の失敗、後処理途中の失敗でも、必要な後処理と失敗の保持を行う。
- 起動中・実行中・停止中の構成変更を拒否し、停止後に解除できる。開始待機・停止待機の取消や重複停止でも後処理を完了し、所有する残存タスクがない。
- v0.2の既存Runtimeテスト、Windows/Linux・CPython 3.12〜3.15、wheel・sdistのメタデータ・LICENSE・新規環境へのインストール・ダミー再現。

稼働中の実体交換とConnectionsの通信許可・直接通信は、この受入の対象外として記録する。登録・利用可否の管理と、実行・通信の状態を混同しない。

### A05・A06の責務境界と時間の確認案


| 観点 | 操作・観察 | 期待結果 |
|---|---|---|
| 活動の価値判断 | 指定値・実行条件を固定し、活動名だけを睡眠・調査などへ変えるダミーケースを比較 | Coreが活動名の価値判断で時刻・期間・優先度を生成・変更しない |
| 指定優先度の適用 | 優先度・実行枠を採用した場合、Nymph役が優先度を入力・変更し、枠不足時の待機順序を確認 | 採用した機械的規則に従う。優先度の決定元をNymphの入力として追跡できる |
| 変更の実行可否と競合 | 採用した状態制約に抵触する変更要求と、競合する要求を入力 | Coreが可否と競合を通知し、結果と状態が契約に一致する |
| 時間の区別 | 待機を含む活動を観察し、中断・再開の採用時は中断区間も含めて比較 | 時刻・期間・経過時間・実行時間を採用定義に従って記録し、期間満了の計算根拠を説明できる |

上表は検証方法の提案である。優先度・実行枠、中断・再開などを見送る場合は、後続ADRと結果表に対象外とする理由を記録する。未決の機能を受入の前提に加えない。

### 配布構成の検証案

配布方針はR6・ADR 0009（`docs/adr/0009-package-distribution.md`）で採用済み。以下の手順は実装後に具体化する検証案である。

| 対象 | 検証内容の案 | 判断に用いる結果 |
|---|---|---|
| 初期配布物（A02以降） | Coreとその時点で実装したContractsを含む一つの配布物をビルドし、新しい環境でインストールする | 採用した公開importとダミー実行を確認できる。開発用ソースに依存せず、実装済みの契約が配布物から利用できる |
| 公開接続契約（B00） | 配布物に含む公開ContractsとCoreを用いて、ダミーSubsystem・Adapterの接続契約を検証する | API資料、配布内容、契約テストの対象が一致する |
| 拡張の分割時 | 分割判断・依存宣言・対応バージョンを確認し、対象配布物をCore・Contractsと組み合わせる | 決定した範囲で個別インストールと接続・実行を再現できる。各配布物に意図したファイルと依存関係が含まれる |

個別の分割と検証範囲は、対象の設計・後続ADRで決める。同梱・別配布のいずれでもADR 0015の通信方針・後続契約とADR 0004の責務境界を確認する。v0.1.0は資料・開発基盤の公開であり、これらの実行検証は未実施である。

### 結果の記録方法

v0.2から `docs/validation/` に結果を記録する。v0.xの結果は `v0.x.md`、v1.x以降は対象バージョンを示すファイルに残す。

| 記録欄 | 内容 |
|---|---|
| 対象 | バージョン、コミットSHA、受入ID、根拠ADR |
| 環境 | OS、Python版、依存版、同一・別プロセスの区別 |
| 再現 | 実行コマンド、ダミー入力、時計条件、失敗の起こし方 |
| 結果 | 期待結果、観測結果、合格・不合格・未検証 |
| 残課題 | 原因、対応方針、次の検証対象 |

### v1.0.0以降の受入検討案

以下はR5のロードマップを具体化するための検証案で、正式な受入基準は各段階の設計・ADRで決める。Subsystem名・Adapter名は暫定名称、順序とバージョンへの機能配分は未確定である。共通の根拠はADR 0006〜0008。通信経路はADR 0015と後続判断、意思決定と実行管理の境界はADR 0004に従う。

| ID・想定段階 | 検証する能力の案 | 操作と観察結果の案 |
|---|---|---|
| B00 v1.0.0 | Core接続契約 | ダミーSubsystem・AdapterでModule、Lifecycle、Capability、Communication、Task、Errorの採用契約を試し、公開API資料と観察結果を照合する。各実行配置の対応範囲を記録する。本番Subsystemの完成は必須条件にしない |
| B01 v1.1.0 | Memoryの最小保存・取得 | 少量の経験・知識を保存し、採用した取得契約で結果を照合する。複雑な知識グラフや高度な統合を受入の前提にしない |
| B02 v1.2.0 | Document入力とMemory連携 | 対応する文書を取得・取り込みし、保存・取得結果までを追う。未対応形式と取得失敗の扱いは採用契約に沿って確認する |
| B03 v1.3.0 | Cognitionの初期学習 | 語彙・構文・概念の検証用入力を用い、採用した学習方式の変化を観察する。既存LLMを言語理解・文章生成の中核としない研究方針との整合を確認する |
| B04 v1.4.0 | Text Interaction / Web連携 | 対応する文章の観測・学習・出力とユーザー訂正を試し、訂正の反映を採用した方法で観察する。対応能力の範囲を記録する |
| B05 v1.5.0 | Agencyの活動決定 | 活動内容、開始時刻、期間、優先度、変更の決定元をAgencyの入力・出力から追跡する。意思決定方式と評価条件は後続ADRで決める |
| B06 v1.6.0 | AgencyとTaskManager | 決定された活動の登録・実行・状態追跡・変更要求の適用と失敗通知を照合する。Coreが指定値と採用規則に従い、活動の価値判断を代行しないことを確認する |
| B07 v1.7.0 | Personaの保持・参照・外部更新 | 人格特性の参照値と外部からの修正値の適用結果を確認する。自発的に人格修正処理を開始しない責務境界を確認する |
| B08 v1.8.0 | PersonaとAgency | 人格特性の参照・修正後にAgencyが採用した選択方式で特性を反映することを確認する。特定の行動結果は方式と評価条件の採用後に定める |
| B09 v1.9.0 | Sleepの初期機能 | 採用した範囲の経験統合、忘却、夢、人格修正値生成を観察する。Personaの更新は接続契約を通じた修正値の適用として追跡する |
| B10 v1.10.0 | 睡眠循環と音声観測 | Sleep連携による記憶・人格の更新循環と、Discord Voice Adapterの観測音声・文字起こし・音響特徴を検証する。告知・同意・権限・保持・削除の採用手順と実際のデータの扱いを照合する |

B09・B10は、各機能の採用範囲と評価条件を確定してから合否判定に使う。Discord音声受信・ASRの先行試験を行う場合は、対象能力とデータ利用条件を記録する。先行試験の結果だけでB10全体を完了扱いにしない。Desktop Adapterと複製・移植・伝播機構をこの受入案の要件へ追加しない。

リリース区分の確認では、奇数・偶数の主目的と補助実装・統合テストの範囲、互換性の影響を記録する。名称・順序・機能配分を変更した場合は、roadmapと本表の対応も更新する。

### 長期目標の評価との関係

R7のProject Vision（`docs/vision.md`）にある、言語・学習・記憶・自己認識・自律性・人格・睡眠・PC操作・継続性・安全性の10領域は、最終的な到達度を評価する観点である。定量的な合格基準と実装時期は未決で、A01〜A09・B00〜B10の合格条件へ一括追加しない。

長期能力を段階の開発対象に採用する際は、観測できる入力・内部状態・出力、評価方法、限界を後続ADRと受入記録に具体化する。機能的な自己認識の検証から主観的意識の存在を判定せず、主観的意識を完成条件にしない。再起動後の継続性の評価も、保存・復元の担当と対象を判断してから具体化する。

### 資料整備時の確認

- R8のApache-2.0採用がREADME・ADR 0011・公開準備資料で一致し、LICENSEが公式本文と一致することを確認する。引継ぎ書のLICENSE原文も照合する。
- 第三者成果物・個体データの条件を一律にApache-2.0へ変更していないことと、将来の分割配布時のLICENSE収録方針を確認する。
- R2・R3の確定事項とR4の責務境界を照合し、追加仕様には状態を付ける。
- Subsystem独立性の整理案、4つの時間概念、V0.6の各操作の採否をADR・roadmap・受入案の間で照合する。
- ADR 0003の当初判断からADR 0015の緩和採用までの履歴と、具体的な許可範囲・契約の未決事項を追える。
- V0.1の公開条件、V0.9の完成条件、各段階の成果物・判断・検証を記載する。
- Git未初期化から公開までの手順と公開前判断欄を掲載する。
- READMEからDocs・ADRへ到達でき、単一配布用引継ぎ書に各文書の本文を収録する。
- R5のv1.0.0目標と、v1.1.0〜v1.10.0の配分・名称・リリース運用案の状態を照合する。
- 既存LLMの扱い、AgencyとCore、PersonaとSleepの責務、音声データの扱いをarchitecture・ADR・検証案で照合する。
- R6の初期配布方針がREADME・architecture・ADR 0009で一致し、将来の配置例と個別の分割判断を提案・未決として区別していることを確認する。
- R7の最終ビジョンと研究方針をREADME・vision・ADR 0010で照合し、長期構想を現行Coreの確定要件へ一括追加していないことを確認する。

---

<a id="section-28"></a>

収録元 `docs/validation/v0.2.md`

## v0.2 Runtime受入記録

### 対象と結果

2026年11月20日、A02とADR 0014の採用範囲を検証した。親Issueは[#2](https://github.com/Tao-pyth/nymph-toolkit/issues/2)、受入は[#25](https://github.com/Tao-pyth/nymph-toolkit/issues/25)、公開後の取得は[#26](https://github.com/Tao-pyth/nymph-toolkit/issues/26)で追跡する。

Runtime実装の基準コミットは[fa00e1b](https://github.com/Tao-pyth/nymph-toolkit/commit/fa00e1bb81ca3117e01ac8665905b7e2b384b3cb)。[CI run 44659437167](https://github.com/Tao-pyth/nymph-toolkit/actions/runs/44659437167)でWindows・LinuxとPython 3.12〜3.15の8環境すべてが成功した。各環境で23件の非同期テスト、ダミー実行、ビルド・新規環境へのwheel導入、sdist再ビルドを行った。

後続の受入ツール・文書更新を含む最終コミットのCIと公開後の取得結果は、#25・#26および[リリース記録](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.2.0)に実際のコミットSHA・CI URL・配布物ハッシュを記載する。本書の基準コミットと最終公開コミットを混同しない。

### 環境と手順

- ローカル：Windows 11（10.0.26200）、CPython 3.15.2。既存Python 3.8と分離したvenvを使用。
- CI：ubuntu-latest / windows-latest、CPython 3.12・3.13・3.14・3.15。同一プロセスの検証。
- ローカルの開発用依存：pip 26.3、build 1.6.1、packaging 26.3、pyproject_hooks 1.3.3、colorama 0.4.6。隔離ビルドのHatchlingは1.33.0に固定。
- 実行時依存：なし。配布物にはCoreとContracts、Apache-2.0のLICENSEを収録。

リポジトリ直下からdevelopment（`docs/development.md`）の環境構築を行い、以下を実行する。

```powershell
.venv/Scripts/python.exe -W error -m unittest discover -s tests -t . -v
.venv/Scripts/python.exe examples/runtime_demo.py
.venv/Scripts/python.exe tools/check_docs.py
.venv/Scripts/python.exe -m build
.venv/Scripts/python.exe tools/check_dist.py
```

LinuxではPythonパスを `.venv/bin/python` に置き換える。check_distはリポジトリ外の一時venvへwheelをインストールし、公開importがそのvenv内にあることを確認する。さらにダミーと同じ23件のテストをwheel上で実行し、sdistからの再ビルド結果をwheelとバイト比較する。テストソースはリポジトリから読み、対象ライブラリは通常インストールした配布物から読む。

### A02との対応

| 観点 | 操作・観測 | 判定 |
|---|---|---|
| 正常起動・実行・停止 | ダミーのstart/run/stopが一度ずつ順番に実行され、runの戻り値を取得 | 合格 |
| 明示停止 | runをEventで待機させ、stopでキャンセル。後処理の完了前はSTOPPING、完了後はSTOPPED | 合格 |
| 起動失敗 | startで例外を発生。部分初期化で作成した子タスクをstopで終了してからSTARTの失敗を通知 | 合格 |
| 実行・後処理の失敗 | runとstopの単独失敗・同時失敗、startとstopの同時失敗を再現。phaseと元例外を保持 | 合格 |
| キャンセル | start・wait・stopの待機側キャンセル、サービスからの未要求キャンセル、停止待機のタイムアウトを再現 | 合格 |
| 重複・競合 | 二重起動・再起動拒否、開始前・初期化中の停止、重複stop、監督タスク開始前の停止を確認 | 合格 |
| 実行コンテキスト | 別イベントループと自己待機を拒否。eager task factoryでも動作・自己待機拒否を確認 | 合格 |
| 残存タスク | ダミー所有の子タスクを終了。各非同期テストの終了時とダミー例で残存タスク0件。無関係なタスクは維持 | 合格 |
| 配布 | wheelの新規環境インストール、公開import、ダミー・非同期テスト、sdist再ビルド、LICENSE・メタデータ照合 | 合格 |
| 文書 | Runtime API、採用ADR、受入基準、READMEの実装範囲、リンク、引継ぎ書と元文書の一致を照合 | 合格 |
| 意思決定の境界 | Runtimeの入力は実行入口のみ。時刻・期間・優先度・活動価値の生成や選択を実装していない | 適合 |

ローカルのダミー出力は `state=stopped`、`result=dummy-result`、`events=[start, run, stop]`、`remaining_tasks=0`。非同期テストは23件成功し、警告をエラーとして実行した。

### 検証中の修正

初回の環境CIではWindowsの短縮パス（RUNNER~1）と実パスの比較によって、インストール先の検証が誤判定した。双方のパスをresolveする修正を[e28278d](https://github.com/Tao-pyth/nymph-toolkit/commit/e28278d49300c4975460c402901080605ab1eee0)で行い、[再検証8環境](https://github.com/Tao-pyth/nymph-toolkit/actions/runs/44659084738)の成功を確認した。検証項目は省略していない。

### 制約と残る範囲

v0.2採用範囲に受入未達はない。以下は今回の完成対象に含めない。

- キャンセルに応答しないサービスの強制終了。タイムアウト後も実行・後処理が続き得るため、STOPPINGを停止完了として扱わない。
- Registry、Connections、TaskManager、別プロセス実行、本番Subsystem・Adapter。後続ロードマップと各親Issueで追跡する。
- 公開契約全体の安定化、直接通信の緩和、永続化・自動再試行・自動復旧。各段階の判断を要する。

上記はv0.2受入時点の対象外・残課題の記録である。その後のR12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）で直接通信の緩和を設計方針として採用した。具体的な許可範囲と実装・検証は今後の課題であり、本受入結果に直接通信の検証を追加したものではない。
- PC全体の状況取得、個体データの複製・移植・伝播。今回の初期実装要件へ追加しない。

Windows・Linuxの上記Python版以外、macOS、別Python実装、別プロセス実行は今回未検証。将来の全Core機能や人工人格の完成を宣言するものではない。

---

<a id="section-29"></a>

収録元 `docs/validation/v0.3.md`

## v0.3受入記録

### 対象・根拠

R13・ADR 0016（`docs/adr/0016-v0.3-registry.md`）で採用したRegistry、Contracts、ModuleGroupと、A03（`docs/acceptance.md`）の具体化を対象とする。親Issue #3、実装 #28〜#31、受入 #32、公開 #33。直接通信の採用判断はADR 0015に記録し、その実装は含めない。

実装コミット `fbb170afcf0f55d94b5e9492befeb004e4593e41` までの63件のテストは[8構成のCI](https://github.com/Tao-pyth/nymph-toolkit/actions/runs/44666494952)で成功した。その後のv0.3.0配布設定・Registry実行例・資料を含む最終コミットのCI、タグ・公開後の確認は[Issue #32](https://github.com/Tao-pyth/nymph-toolkit/issues/32)・[Issue #33](https://github.com/Tao-pyth/nymph-toolkit/issues/33)とReleaseへSHA付きで記録する。公開対象は最終CI成功後の同一コミットとする。

### ローカル環境と結果

2026年11月20日、Windows NT 10.0.26200.0、CPython 3.15.2、venv・pip、build 1.6.1、Hatchling 1.33.0で確認した。実行時の外部依存はない。

| 対象 | 結果・証拠 |
|---|---|
| 全テスト | 63件成功。既存Runtime23、Contracts5、Registry13、ModuleGroup22 |
| 実行例 | RuntimeとRegistryの両方で停止・結果・所有する残存タスク0件を確認 |
| wheel | v0.3.0の通常インストール、Core・Contracts公開import、Python下限、依存なし、LICENSEを確認 |
| 配布物からの再現 | ソース外の作業ディレクトリ、新規venv、隔離モードで両実行例と全63テストが成功 |
| sdist | 新規フォルダへ展開し、同じ内容のwheelへ再ビルドできることをバイト比較 |
| 文書 | 個別Docs・ADRと引継ぎ書を同期。リンク・UTF-8/LF・LICENSEを既存ツールで確認 |

### A03との対応

| 受入観点 | 主な確認箇所 |
|---|---|
| 両kindの登録・照会・解除 | test_registryのboth_kinds、unknown_operations。registry_demoでもSubsystem・Adapterを使用 |
| 不変スナップショット・再登録識別 | test_registry_contractsのcollectionコピー、test_registryのreregistration・generation |
| 重複・不正値・循環の原状維持 | duplicate、unknown_operations、self_cycle、cycle_through_previously_missing_target |
| 必須依存・利用可否と通知 | missing_dependencies、dependency_registration_removal_and_recovery、diamond、100段chain |
| スレッド所有 | cross_thread_reads_and_writesの読み書き・revision照会拒否 |
| 依存順初期化・逆順後処理 | test_module_groupのdependency_order、independent_initialization_order。正常戻り値も照合 |
| 依存不足と部分初期化 | missing_dependencies_prevent_all_initialization、partial_start_failure |
| 失敗の保持と停止 | run_failure_stops_other_runs、simultaneous_run_failures、run_failure_during_cancellation、all_cleanup_failures |
| 取消と構成固定 | configuration_is_frozen、cancelled_start_waiter、cancelled_stop_waiter、unrequested_run_cancellation |
| 所有タスクと再実行の境界 | 各非同期テストの終了時に残存タスクを確認。共有Runtimeによる誤停止拒否、再起動拒否、eager factory、タスク生成途中失敗 |
| 既存挙動の回帰 | v0.2のRuntime23件を変更せず継続実行 |

### 再現コマンド

リポジトリ直下、CPython 3.12以上で実行する。PowerShellの例。distには対象版のwheel・sdistだけを置く。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -W error -m unittest discover -s tests -t . -v
.venv/Scripts/python.exe examples/runtime_demo.py
.venv/Scripts/python.exe examples/registry_demo.py
.venv/Scripts/python.exe tools/check_docs.py
.venv/Scripts/python.exe -m build
.venv/Scripts/python.exe tools/check_dist.py
```

CIではWindows/Linux × CPython 3.12・3.13・3.14・3.15で同じ確認を行う。タイミングはEventで制御し、実時間の待機長を合否の基準にしない。

### 制限と後続事項

- ModuleGroupの実体着脱は起動前と停止後の解除に限定する。稼働中実体交換はConnectionsの解除・失効契約と合わせて後続判断とする。
- availableは依存先の登録充足であり、稼働・正常性・通信許可を意味しない。変更通知は操作の戻り値で、継続購読・永続保存を行わない。
- 依存はID単位の必須依存。Capability単位・任意依存・版制約、自動代替・自動復旧・永続化は対象外。
- 協調的取消を無視する処理を強制終了しない。サービス自身の資源はサービスのstopが後処理する。
- Connections、直接通信の許可API・経路実装、TaskManager、IPC、本番Subsystem・Adapterは後続段階の対象。複製・移植・伝播は初期スコープ外を維持する。

上記を採用範囲の制限として記録し、未実装機能を合格項目へ含めない。公開後の取得・ハッシュ・インストール結果は対象SHAとともにReleaseとIssue #33へ記録する。

---

<a id="section-30"></a>

収録元 `docs/development.md`

## 開発準備とGit運用

### 公開準備時の環境

2026年11月19日の公開準備環境にはGit 2.56.0.windows.4とPython 3.8が存在した。v0.2ではADR 0014によりCPython 3.12以上を採用した。既存のPython 3.8は変更せず、開発用のPythonと仮想環境を別に用意する。

### v0.3の環境構築

CPython 3.12以上を用意し、リポジトリ直下で実行する。以下はPowerShellの例。仮想環境のactivateは不要である。

```powershell
python --version
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -W error -m unittest discover -s tests -t . -v
.venv/Scripts/python.exe examples/runtime_demo.py
.venv/Scripts/python.exe examples/registry_demo.py
.venv/Scripts/python.exe tools/check_docs.py
.venv/Scripts/python.exe -m build
.venv/Scripts/python.exe tools/check_dist.py
```

Linuxでは `.venv/Scripts/python.exe` を `.venv/bin/python` に置き換える。Pythonの下限はpyproject.tomlにも記録する。実行時の外部依存はなく、build 1.6.1とHatchling 1.33.0をビルド時だけ使う。テストは標準unittestを用いる。

distには対象版のwheelとsdistを一つずつ置く。古い版が残っている場合は対象を確認して作業フォルダ外へ保管する。check_distは新規仮想環境を作り、wheelの通常インストール、公開import・LICENSE・メタデータ、sdistから同一wheelへの再ビルドを確認する。開発用のeditable installだけで配布検証を済ませない。

CIはWindowsとLinux、Python 3.12〜3.15で全テスト、Runtime・Registryのダミー実行、ビルドと配布検証を行う。Runtimeの操作・キャンセル・失敗通知はruntime.md（`docs/runtime.md`）、登録・依存管理と複数対象の実行はregistry.md（`docs/registry.md`）に記載する。

### 実装開始時の配布構成

v0.2での採用結果はADR 0014（`docs/adr/0014-v0.2-runtime.md`）に記録する。CPython 3.12以上、配布名 `nymph-toolkit`、venv・pip、build・Hatchling、標準unittestを使用する。実行時依存は追加しない。Core・Contractsの単一wheel・sdistをGitHub Releaseから配布する。以下にある「実装開始時に記録する」項目のうち、これらは本ADRで具体化した。

ADR 0009（`docs/adr/0009-package-distribution.md`）に従い、CoreとContractsを一つの配布パッケージとして扱う。ルートの `pyproject.toml` に配布設定を置き、`src/nymph_toolkit/core/` と `src/nymph_toolkit/contracts/` を同梱する。v0.2のライフサイクル契約に加え、v0.3で登録・依存・変更通知の契約を実装した。残る通信・活動契約は後続段階で具体化する。

ビルドした配布物をcheck_distで新しい環境へインストールし、採用したCore・Contractsの公開importとダミー実行を確認する。結果はacceptanceの記録形式で残す。

Subsystem・Adapterは必要に応じて同じリポジトリ内で別配布にする。分割時は対象の `pyproject.toml`、ソース・テストを配置する案とし、依存宣言、Core・Contractsの対応バージョン、公開import名、ビルド・インストール・組合せ検証の手順を後続ADRへ記録する。配置例はarchitecture.md（`docs/architecture.md`）を参照する。

### ライセンスの適用と配布確認

R8・ADR 0011（`docs/adr/0011-apache-2.0-license.md`）により、自作コード・Contracts・設計文書へApache-2.0を適用する。ルートのLICENSE（`LICENSE`）を維持し、実装開始時に採用するビルドツールに合わせてライセンス識別子 `Apache-2.0` とライセンスファイルの収録を配布設定へ記載する。

ソースファイルへライセンスを表示する場合は、ファイル形式に応じたコメントで `SPDX-License-Identifier: Apache-2.0` を記す方法を用いる。著作権表示を付す場合は実際の権利者・年を記載し、第三者の権利表示やライセンスを上書きしない。[Apache公式の適用方法](https://www.apache.org/foundation/license-faq.html)

ビルドした配布物を確認し、LICENSEと必要な帰属表示が含まれることを検証する。分割した自作Subsystem・Adapterも各配布物で同じ確認を行う。第三者成果物の同梱時は、その許諾条件と必要なNOTICE等を確認する。具体的なビルド・検証コマンドは実装後に追加する。

### Git未初期化からの準備

以下はPowerShellでリポジトリ直下から実行する手順である。各コマンドの結果を確認し、失敗した場合は原因を解消してから次へ進む。作業フォルダは利用環境に合わせる。

```powershell
Set-Location -LiteralPath 'D:\NYMPH-toolkit'
git --version
git rev-parse --show-toplevel
```

`rev-parse` がリポジトリを返した場合は、そのルートを確認して既存Gitを使用する。未初期化の場合は以下を実行する。

```powershell
git init -b main
git config --show-origin --get user.name
git config --show-origin --get user.email
```

名前・メールが未設定の場合は、作成者本人の情報を確認してこのリポジトリに設定する。以下の仮の値を実際の値に置き換える。

```powershell
git config --local user.name 'YOUR_NAME'
git config --local user.email 'YOUR_COMMIT_EMAIL'
```

GitHubのnoreplyアドレスを使う場合は、GitHubのメール設定で値を確認できる。ID形式は `ID+USERNAME@users.noreply.github.com` である。今回のローカル設定は、許可されたGitHubプラグインで確認した表示名 `Tao` とID・ユーザー名から構成した `54444867+Tao-pyth@users.noreply.github.com` を使用する。GitHubへのコミット帰属は公開後に確認する。[GitHubのメールアドレス仕様](https://docs.github.com/en/account-and-profile/reference/email-addresses-reference)

### 対象確認と初回コミット

`.gitignore` で仮想環境、Python生成物、キャッシュ、ローカル設定を除外する。`.gitattributes` でMarkdown・Python・設定ファイル・LICENSEをLFに統一する。Apache-2.0の公式本文を収録した `LICENSE` をコミット対象に含める。

```powershell
git status --short --untracked-files=all
git add -- .gitignore .gitattributes LICENSE README.md CONTRIBUTING.md CHANGELOG.md docs
git diff --cached --stat
git diff --cached --check
git diff --cached
```

差分を読み、公開する資料と設定が揃っていること、認証情報・ローカル環境・意図しない生成物を含まないことを確認する。除外設定は既に追跡しているファイルには適用されないため、ステージした一覧も確認する。

```powershell
git commit -m 'docs: prepare NTK Core design and release roadmap'
git log -1 --format=fuller
git status --short --branch
```

この手順は初回コミット用である。既に履歴がある場合は変更対象と履歴を確認し、その変更に対応するコミットを作る。

### コード変更前の必須条件

R10・ADR 0013（`docs/adr/0013-milestone-issue-workflow.md`）により、コード変更前に対象バージョンのマイルストーン、親Issue、対応単位の子Issueをこの順で整える。親子関係と双方のマイルストーンを確認し、子Issueの範囲・完了条件・検証方法・先行課題を記録する。実装に必要な判断を残したまま、その範囲のコードを書き始めない。

具体的な登録・完了手順と現在の課題はIssue運用（`docs/issue-workflow.md`）、エージェント向けの要点はAGENTS.md（`AGENTS.md`）を参照する。以後のコミットまたはPRには対応する子Issue番号を記載し、子Issueへ検証結果と残課題を記録する。文書のみの修正はこの必須条件の対象外だが、関連する設計判断をDocs・ADRへ記録する。

### 日常の作業案

設計判断・文書更新・実装を目的が分かる単位でコミットする。関連するADR・実装・受入条件は同じ作業で整合させる。変更が複数に分かれる場合は作業ブランチを使用する案とする。

```powershell
git status --short --branch
git switch -c docs/refine-core-design
# ファイル編集後、対象パスを指定してgit addする
git diff --cached --check
git diff --cached
```

各段階で本書の環境構築、テスト、ダミー受入シナリオを更新する。新しい作業環境で再現し、OS・Python版・依存版と結果をacceptanceの記録形式で残す。

### 文書更新時の確認

Docs編集後は `python tools/build_handoff.py` で引継ぎ書を再生成し、`python tools/check_docs.py` で収録元との一致・ローカルリンクを確認する。CIは再生成を自動保存せず、一致していない場合に失敗する。検証結果はvalidation/v0.2.md（`docs/validation/v0.2.md`）とvalidation/v0.3.md（`docs/validation/v0.3.md`）に記録する。

ローカルリンク先の存在、ADRの状態と根拠、ロードマップと受入IDの対応、READMEの実装状況を確認する。単一配布用引継ぎ書はDocs索引に示した順序・変換方法で再作成し、収録元の本文と照合する。将来の配置予定はarchitectureのツリーに記載し、リンクは実在するファイルへ向ける。

公開準備と公開後の状態はrelease.md（`docs/release.md`）で確認する。

---

<a id="section-31"></a>

収録元 `docs/issue-workflow.md`

## マイルストーンと親子Issueの運用

### 必須の順序

R10・ADR 0013（`docs/adr/0013-milestone-issue-workflow.md`）により、コード変更を伴う対応は、**バージョン別マイルストーン → 親Issue → 対応単位の子Issue登録 → 対応**の順で進める。

新規実装、不具合修正、リファクタリング、テストコード、実行・ビルド・配布に影響する設定の変更も対象とする。親Issueだけを作って実装を始めたり、実装後に子Issueを作成したりしない。文書のみの修正はこの必須条件の対象外だが、設計変更は従来どおり議論とADR記録を行う。

### 管理する単位

| 単位 | 記載・確認する内容 |
|---|---|
| マイルストーン | 対象バージョン、段階の目標、確定・提案の区別、関連ロードマップ・受入項目。期限は個別に合意しない限り設定しない |
| 親Issue | 機能・成果のまとまり、目的と範囲、採用済み事項と判断対象、関連Docs・ADR、完了条件、子Issue |
| 子Issue | 一つの対応単位、親Issue、対象マイルストーン、目的・変更範囲・完了条件・検証方法、先行課題と必要な判断 |

マイルストーンはリリース段階、親Issueは成果のまとまり、子Issueは実際の対応単位を表す。初回は既存ロードマップの各段階に一つの親Issueを設け、必要に応じて同じマイルストーンへ複数の親Issueを追加できる。

親子関係はGitHubのsub-issue機能で設定する。本文の参照だけで済ませず、子Issue自身にも対象マイルストーンを設定して確認する。先行する子Issueは本文で参照し、着手前に完了状況を確認する。[GitHubのsub-issue説明](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)

### 対応開始から完了まで

1. 既存のマイルストーン・親Issueを確認する。対象バージョンや機能が新しい場合は、先に目標と確定・提案の区別を記録して追加する。
2. 対応する子Issueを作成し、親子関係・マイルストーンと上表の項目を揃える。設計判断を先に行う必要があれば、その判断を別の子Issueに切り出せる。
3. 実装に必要な未決事項を判断し、関連Docs・ADRと子Issueへ結果を記録する。依存先の未完了や未決事項が実装を妨げる場合は、その範囲の実装を開始しない。
4. 子Issueの範囲で変更し、コミットまたはPRに子Issue番号を記載する。対応範囲が広がったら、追加範囲のコード変更前に子Issueを更新するか別の子Issueを登録する。
5. 子Issueへ変更コミットまたはPR、検証内容・結果、関連Docs・ADR、残課題を記録する。採用範囲の対応・検証・文書更新が完了してから閉じる。
6. 親Issueでは採用した子Issueの完了と受入結果を確認する。延期・不採用は理由と移管先を記録し、未実装を実装済みとして扱わない。
7. マイルストーンの目標・受入条件・リリース条件を確認して完了とする。Issueがすべて閉じたことだけで自動的にリリースしない。

通常の作業ブランチ名は、例えば `feat/24-runtime-lifecycle` のように子Issue番号を含めると追跡しやすい。ブランチ命名の例を製品仕様や必須の命名規約としては扱わない。

### 計画と仕様の区別

この運用ルールは採用済みである。v0.2はR11・ADR 0014、v0.3はR13・ADR 0016で実施範囲を具体化した。一方、v0.4〜v0.8とv1.1.0〜v1.10.0の機能配分、Subsystem・Adapterの名称や実装順序、契約詳細などは既存の提案状態を維持する。登録は採用や着手の宣言ではない。計画を変更する場合は理由・依存関係・受入への影響を記録し、ロードマップ、Issue、関連ADRを整合させる。

v0.1.0＝GitHub公開、v0.9.0＝合意したCore機能の完成、v1.0.0＝CoreとSubsystem・Adapterの接続契約整備という確定目標と、NymphとCoreの責務分離を維持する。通信方針はR12・ADR 0015（`docs/adr/0015-core-authorized-direct-communication.md`）で更新し、Coreが管理・許可した直接通信を採用した。詳細な許可条件・APIなどは実装前に判断する。

### 登録したマイルストーンと親Issue

2026年11月20日に既存ロードマップを以下のように整理した。進捗の最新状態はGitHubを参照する。v0.1.0は公開結果を記録した完了済みの段階であり、新ルールを公開前に実施したという意味ではない。

| マイルストーン | 親Issue | 計画の位置付け |
|---|---|---|
| [v0.1.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/1) | [#1 GitHub公開](https://github.com/Tao-pyth/nymph-toolkit/issues/1) | 確定目標・公開済み |
| [v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/2) | [#2 Runtime](https://github.com/Tao-pyth/nymph-toolkit/issues/2) | R11・ADR 0014で実施範囲を具体化 |
| [v0.3.0](https://github.com/Tao-pyth/nymph-toolkit/milestone/3) | [#3 Registry](https://github.com/Tao-pyth/nymph-toolkit/issues/3) | R13・ADR 0016で実施範囲を具体化 |
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

### v0.2に向けた最初の対応単位

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

### v0.3に向けた通信方針の後続判断

R12の直接通信緩和の採用記録と資料・引継ぎ書生成ツールの同期は、親Issue #3・マイルストーンv0.3.0に属する子Issue [#34](https://github.com/Tao-pyth/nymph-toolkit/issues/34)で追跡する。生成ツールの説明文を変更する前に、この子Issueを登録した。

Registryの設計判断は[#27](https://github.com/Tao-pyth/nymph-toolkit/issues/27)、通信の具体的な許可範囲・API・解除時の動作はv0.4の親Issue [#4](https://github.com/Tao-pyth/nymph-toolkit/issues/4)へ引き継ぐ。#34は採用判断の反映を扱い、RegistryやConnectionsの実装完了とは区別する。

### v0.3の実施範囲と対応単位

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

---

<a id="section-32"></a>

収録元 `docs/release.md`

## 公開準備とリリース手順

GitHub公開をV0.1、Core機能完成をV0.9とする目標は確定している。2026年11月20日に初期資料・開発基盤のv0.1.0と、最小Runtimeのv0.2.0を公開した。v0.1.0欄は初回公開時の記録として保持する。

### v0.3.0の公開手順と記録

R13の実施指示に基づき、ADR 0016のRegistry・ModuleGroup・Contractsとダミー、A03受入資料をv0.3.0として公開する。R12・ADR 0015の直接通信の採用記録も含めるが、通信実装は含めない。

| 項目 | 内容 |
|---|---|
| 公開先 | [GitHub Release v0.3.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.3.0)。PyPI公開は対象外 |
| 配布物 | `nymph_toolkit-0.3.0-py3-none-any.whl`、`nymph_toolkit-0.3.0.tar.gz`、単一引継ぎ書、SHA256SUMS |
| 受入 | A03記録（`docs/validation/v0.3.md`）。63テスト、両実行例、Windows/Linux・CPython 3.12〜3.15、通常インストール・sdist再ビルド |
| 公開前の条件 | 最終コミットで文書・テスト・ビルド・配布チェックと8構成のCIが成功。コード・文書・配布物・タグが同じコミットに対応 |
| 公開後の条件 | 認証なしのタグclone・添付取得・ハッシュ照合、取得したwheelの新規環境への導入、両実行例と63テストの再現 |
| 実際の結果 | 対象SHA・CI・配布物ハッシュ・公開後の検証をReleaseと[子Issue #33](https://github.com/Tao-pyth/nymph-toolkit/issues/33)へ記録 |

公開手順は、確認済みmainへの `v0.3.0` タグ付与、Releaseへの同じコミットの配布物添付、公開後確認の順に行う。確認後に親Issue #3・マイルストーンv0.3.0を完了とする。v0.1.0・v0.2.0のタグ・Release添付は保持する。

### v0.2.0の公開記録

| 項目 | 内容 |
|---|---|
| 対象 | ADR 0014の最小RuntimeとContracts、ダミー、テスト、開発・受入資料 |
| Python・依存 | CPython 3.12以上、実行時の外部依存なし |
| 公開先 | [GitHub Release v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.2.0)。PyPIへの公開は行わない |
| 配布物 | `nymph_toolkit-0.2.0-py3-none-any.whl`、`nymph_toolkit-0.2.0.tar.gz`、単一引継ぎ書、SHA256SUMS |
| 受入 | A02の結果（`docs/validation/v0.2.md`）、Windows/LinuxとPython 3.12〜3.15のCI |
| 実際の公開結果 | 対象SHA・最終CI・公開後の取得確認・各配布物のハッシュはReleaseと子Issue #26へ記録 |

リリース対象コミットで `python tools/check_docs.py`、テスト、`python -m build`、`python tools/check_dist.py` を実行し、CIを確認する。同じコミットへ `v0.2.0` タグを付けてpushし、検証した配布物と同じタグの引継ぎ書をReleaseへ添付する。公開後は認証なしでタグ・添付を取得し、ハッシュ照合とwheelからのダミー・テスト実行を確認する。結果を記録して親Issue・マイルストーンを完了とする。

### v0.1.0の公開記録

| 項目 | 現在の状態 | 記録 |
|---|---|---|
| リポジトリ名 | 確定 | `nymph-toolkit` |
| 公開先アカウント | 採用済み（R9） | 個人アカウント `Tao-pyth`。GitHub接続でも確認済み |
| 公開範囲 | publicを確認済み | R9に従い最初からpublicで公開 |
| ライセンス | 採用済み（R8、2026年11月20日） | 自作コード・Contracts・設計文書へApache-2.0を適用。LICENSE（`LICENSE`）とADR 0011（`docs/adr/0011-apache-2.0-license.md`）を配置済み |
| 公開対象 | 資料中心で確定（R9） | README、CONTRIBUTING、Docs・ADR、CHANGELOG、Git設定、LICENSE。Core未実装を明記 |
| 公開URL・remote | 設定済み | [Tao-pyth/nymph-toolkit](https://github.com/Tao-pyth/nymph-toolkit)、`origin` は `https://github.com/Tao-pyth/nymph-toolkit.git` |
| V0.1タグ・公開日 | 初回公開の対象 | `v0.1.0`、2026年11月20日。対象コミットSHAと公開後の検証結果は[GitHub Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.1.0)に記録 |

公開先の接続確認と、公開先の選定はそれぞれ記録する。ライセンスはR8でApache-2.0、公開先と公開範囲はR9で `Tao-pyth/nymph-toolkit` のpublic公開へ確定した。判断記録はADR 0012（`docs/adr/0012-v0.1-publication.md`）。公開・タグ・Releaseの完了は実際の結果を確認して記録する。

### 公開前チェックリスト

- [x] Apache-2.0の採用・適用範囲を記録し、公式本文のLICENSEを追加する。
- [x] 公開先アカウント・公開範囲の判断欄を埋める。
- [x] 簡潔な参加方針をCONTRIBUTINGに記載する。
- [x] 公開する成果物にLICENSEを含め、第三者成果物がある場合は元の許諾・帰属表示・NOTICE等の要件を確認する。
- [x] READMEにその時点の実装状況を記載する。
- [x] Docs・ADRの確定事項、未決事項、根拠を確認する。
- [x] 単一配布用引継ぎ書を個別Docsと同期する。
- [x] ステージした一覧と差分を読み、公開対象を確認する。
- [x] 初回コミットとローカルGitの作成者設定を確認する。
- [x] 文書リンク、文字コード、改行、受入IDの対応を確認する。
- [x] README・CHANGELOG・本書の公開時の更新を準備する。

ローカルでの公開前確認は2026年11月20日に実施した。文書リンク、引継ぎ書と収録元の一致、LICENSE原文、公開対象とGit履歴を確認した。初回push後にpublic設定とローカル・remoteのコミット一致を確認した。以下はタグ・Release作成と公開後の取得確認を含む手順である。最終結果は上記Releaseに記録する。

### ライセンスと配布内容の確認

自作コード（Core、Contracts、将来の自作Subsystem・Adapter）と設計文書（README、Docs・ADR、引継ぎ書）にApache-2.0を適用する。第三者のコード・依存ライブラリ・モデル・文書・音声等は各権利者の条件を維持し、会話・記憶・人格などの個体データの利用条件も別途扱う。

LICENSEは[Apache公式テキスト](https://www.apache.org/licenses/LICENSE-2.0.txt)を変更せず収録する。付録の著作権表示の記入例は公式本文の一部として保持する。実際の成果物の著作権・帰属表示は正確な権利関係に基づいて別途記載し、第三者の表示を保持する。

単一配布用引継ぎ書にはLICENSE原文を収録する。将来のPython配布物や分割したパッケージでも、各配布物にLICENSEと必要な表示が含まれることを確認する。NOTICEは収録物の表示要件に応じて整備する。採用状態の記録はADR 0011（`docs/adr/0011-apache-2.0-license.md`）を参照する。

### GitHubへの接続とpush

GitHubで、決定済みの所有者の配下に `nymph-toolkit` を作成する。ローカル履歴から開始する場合はREADME・LICENSE・gitignoreの自動作成を選ばず、空のリポジトリを用意する。既存リポジトリがある場合は内容と履歴を確認してから接続する。

以下は採用した公開先に対するPowerShellの例。認証には設定済みのGit認証手段を使う。

```powershell
git remote -v
git remote add origin https://github.com/Tao-pyth/nymph-toolkit.git
git remote -v
git ls-remote origin
```

既に `origin` がある場合はURLを確認し、追加コマンドを省略する。`ls-remote` の認証失敗は空のリポジトリと区別する。既存のブランチがある場合はfetchして履歴を確認し、統合方法を決める。履歴を上書きするforce pushはこの初期手順に含めない。

```powershell
git push -u origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

ローカルとremoteのSHAが一致することを確認する。GitHub上でREADMEから各Docs・ADRを開き、公開範囲とファイル一覧を確認する。GitHubプラグインの接続とローカルGitの認証は別に確認する。

### V0.1のタグとリリース

公開内容を確認したら、READMEの状態を「V0.1公開済み」に更新し、実装状況を具体的に記す。CHANGELOGの未リリース項目に実際の公開日を記録し、本書の判断欄・公開URLを埋める。単一配布用引継ぎ書も同期してコミット・pushする。

```powershell
git add -- LICENSE README.md CONTRIBUTING.md CHANGELOG.md docs
git diff --cached --check
git diff --cached
git commit -m 'docs: record v0.1.0 publication'
git push origin main
git tag -a v0.1.0 -m 'NTK v0.1.0 initial publication'
git push origin v0.1.0
git rev-parse 'v0.1.0^{commit}'
git ls-remote origin 'refs/tags/v0.1.0*'
```

タグが既にある場合は対象コミットを確認して再作成を省略する。公開済みタグを移動せず、修正は次のコミット・リリースで記録する。

GitHubのReleasesから既存タグ `v0.1.0` を選び、公開目的、収録資料、実装状況、未決事項、検証結果を記載してリリースを公開する。タグの対象コミットとリリース表示が一致することを確認する。単一配布用引継ぎ書はリポジトリから取得でき、必要なら同じタグのファイルをリリース添付に使う。

### 公開後の確認と次の段階

新しい作業フォルダへcloneし、READMEからDocs・ADRをたどる。公開前にローカルで行った確認に加え、GitHubの表示と取得可能性をA01として記録する。private準備中ならV0.1の公開完了は保留する。

V0.2以降は対応する受入結果、READMEの実装状況、CHANGELOG、文書を更新してからタグ・リリースを記録する案を用いる。V0.9では全採用機能の結果と残課題を記載し、Core完成の判定根拠を示す。

### 配布パッケージとリリースの対応

R10以降はIssue運用（`docs/issue-workflow.md`）に従い、対象マイルストーン・親Issue・子Issueから変更と検証結果を追跡する。リリース前に採用範囲の受入結果と残課題の扱いを確認する。コード変更は子Issue登録後に行い、Issueやマイルストーンを閉じただけで自動的に公開・タグ付けは行わない。公開済みv0.1.0のタグ・Release添付は保持し、その後の資料更新は未リリースの変更として記録する。

R6・ADR 0009（`docs/adr/0009-package-distribution.md`）で、単一リポジトリと、Core・Contractsを一つの配布パッケージから始める方針を採用した。Subsystem・Adapterは必要に応じて同じリポジトリ内で分割する。GitHub公開のv0.1.0は資料と開発基盤を中心とする節目で、Python配布物の公開を必須条件に加えない。

配布パッケージの正式名称、配布先、ビルド手段は別途決める。将来分割する際は、対象とCore・Contractsの対応バージョン、各配布物のバージョンを同期するか独立させるか、リポジトリのタグ・ロードマップの節目との対応を後続ADRへ記録する。これらの決定と検証結果を基に、そのリリースで公開する配布物を明示する。

### v1.x以降のリリース運用案

R5に基づく未確定の運用案をADR 0007に記録する。v1.0.0の接続契約整備という目標はADR 0006を参照する。

| 区分 | 主目的の案 |
|---|---|
| v1.0.0 | CoreとSubsystem・Adapterの接続契約確立 |
| 奇数マイナーバージョン | 新規Subsystemの実装 |
| 偶数マイナーバージョン | Subsystem間連携の見直し・強化、Adapterの実装・拡張 |
| パッチバージョン | 不具合修正、小規模改善、互換性を維持した個別修正 |

必要な補助実装や最低限の統合テストは各区分に含められる。偶数マイナーで必ず新しいAdapterを追加する必要はない。名称・実装順序・バージョンへの機能配分は暫定であり、変更理由と受入への影響を記録して調整する。

#### 公開API互換性の判断

公開するAPIと互換性の境界をv1.0.0の契約設計で具体化する。Semantic Versioningでは、後方互換性のある修正をパッチ、公開APIへの後方互換性のある機能追加をマイナー、非互換な公開API変更をメジャーとして扱う。NTKでの適用範囲と採番は変更内容を確認して別途判断する。[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)

「小規模改善」という作業量だけでパッチと決めず、公開APIへの機能追加や互換性への影響を確認する。破壊的変更が必要になった場合は、影響、移行方法、Semantic Versioningとの整合性、採番とロードマップの調整を後続ADRへ記録する。奇数・偶数の予定だけを根拠に破壊的変更をマイナーへ割り当てない。

実際のリリース時には、その段階で採用した契約と受入結果、互換性判断、既知の制約をREADME・CHANGELOG・リリース記録へ反映する。

---

<a id="section-33"></a>

収録元 `CHANGELOG.md`

## 変更履歴

### v0.3.0 — 2026年11月20日

- R13・ADR 0016に基づくv0.3のRegistryを実装。登録・照会・解除、IDとgeneration、不変スナップショット、推移的な不足依存と変更通知を追加。
- ModuleGroupで複数のダミーSubsystem・Adapterを既存Runtimeから実行し、依存順初期化・逆順後処理・失敗情報の保持を実装。稼働中実体着脱は延期し、実行中は構成を固定。
- 全63件のテスト、Registryの実行例、配布物からの実行検証、A03受入資料を整備。Core・Contractsの単一配布と既存Runtime APIを維持。
- R12・ADR 0015により、Coreが管理・許可した接続での直接通信を採用。旧来のCore経由のみという制約を置き換え、ADR 0003に履歴を保持。
- README・設計・ロードマップ・受入基準・関連ADR・Issueの採用状態と、単一引継ぎ書・生成ツールの説明を同期。許可範囲・API・解除時の動作は未決として残す。
- R12の変更は設計判断の更新であり、直接通信の実装は含まない。R13でRegistryを実装したが、Connections・TaskManager・IPCは後続段階に残す。公開済みv0.1.0・v0.2.0タグ、Release添付は保持する。

### v0.2.0 — 2026年11月20日

- v0.2のRuntimeと最小Contractsを実装。起動・実行・停止、自然終了とキャンセル時の後処理、失敗の保持・通知を追加。
- CPython 3.12以上、Core・Contractsの単一wheel・sdist、実行時依存なしの構成をADR 0014へ記録。
- 非同期ライフサイクルテスト、ダミー例、Windows・LinuxのCI、配布物を新規環境で検証する手順を追加。

- R10・ADR 0013により、コード変更前にマイルストーン・親Issue・対応単位の子Issueを登録する運用を採用。
- 既存ロードマップの20段階をGitHubマイルストーンと親Issueに整理し、v0.2に向けた5件の子Issueを登録。
- Issue運用資料とAGENTS.mdを追加し、参加方針・開発手順・関連Docs・引継ぎ書へ反映。機能配分案と未決仕様の状態は維持。

### v0.1.0 — 2026年11月20日

- 日本語の初期設計・Codex引継ぎ書と個別Docs・ADRを整備。
- GitHub公開をV0.1、Core機能完成をV0.9とするロードマップ案と受入基準案を掲載。
- Git初期設定、公開準備、リリース手順、除外・改行設定を追加。
- 整合性レビューR4に基づき、Nymphの価値判断とCoreの機械的な実行管理、通信経路の暫定基準、Subsystem独立性の整理案を明確化。
- V0.5の時間概念と、V0.6の時間・優先度変更、中断・再開、取消・終了の採否判断および受入案を追記。
- R5に基づき、v1.0.0の接続契約整備の目標と、v1.1.0〜v1.10.0のSubsystem・Adapterロードマップ案を追加。
- ADR 0006〜0008に接続契約の検討対象、未採用のリリース運用案、Subsystem・Adapterの責務案と研究方針を記録。
- v1.xの受入検討案、互換性判断、音声データの扱い、Desktop Adapterの将来課題を追記。名称・順序・機能配分は暫定と明記。
- R6に基づき、単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて分割する方針をADR 0009へ採用として記録。
- 初期のCore・Contracts配置と将来の同梱・別配布の配置例を区別し、関連する開発・受入・リリース資料へ反映。個別の分割対象・時期・正式なパッケージ名・分割後のバージョン管理は未決として記載。
- R7の添付Project Vision全16節を `docs/vision.md` に収録し、経験から学び、活動し、成長する人工人格Nymphという最終目標をREADME・設計資料へ反映。
- ADR 0010で長期ビジョンを採用し、言語獲得、記憶、Self-Model、内部状態・人格・睡眠・夢、権限下のPC操作、継続性の目標と、段階ごとの実装・受入範囲を区別。最終完成のバージョンは固定しない。
- R8により、自作コード・Contracts・設計文書へApache-2.0を採用。公式本文のLICENSEとADR 0011を追加し、README・公開準備資料・関連Docsの採用状態を更新。
- 第三者成果物と個体データの条件を適用範囲から区別し、分割後の配布物にもLICENSEを含める方針を記録。単一配布用引継ぎ書へライセンス原文を収録。
- R9・ADR 0012で `Tao-pyth/nymph-toolkit` のpublic公開を採用し、Issue・Pull Requestでの参加方針をCONTRIBUTINGへ追加。

資料・設計・開発基盤を中心とした初回public公開。Coreコード・本番Subsystem・Adapter・実行テストは未実装である。[リリース記録](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.1.0)に対象コミットと確認結果を記載する。

---

<a id="section-34"></a>

収録元 `LICENSE`

## Apache License 2.0（原文）

```text

                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```
