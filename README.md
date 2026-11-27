# Nymph Toolkit（NTK）

Nymph Toolkit（NTK）は、人間との継続的な交流や外部環境での経験を通じて、知識・言語・行動能力・人格を発達させる人工人格「Nymph」を構築するためのソフトウェア基盤です。Apache-2.0で開発資料を公開し、オープンソースでの実装を進めます。GitHubの統合リポジトリは [Tao-pyth/nymph-toolkit](https://github.com/Tao-pyth/nymph-toolkit) です。

**Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指します。** 限定的な能力から「赤ちゃんを育てるような感覚」で成長を支え、自然な日本語で交流し、権限の範囲でPC環境を観測・操作できる姿を最終目標とします。

基本機構と経験から獲得する知識を区別し、言語獲得そのものを研究します。既存LLMを言語理解・文章生成の中核にする方式は採らず、音声認識などの補助技術は利用できます。記憶・自己理解・自律活動・人格・睡眠の長期構想と評価領域は[Project Vision](docs/vision.md)にまとめています。最終的な完成を特定のバージョンに固定せず、各段階で実装範囲と到達基準を具体化します。

構成は、Nymphが決めた活動を実行管理するCoreを中心に、Subsystem・Adapterを着脱するPython基盤です。

配布方針は、単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterを必要に応じて分割するものです。個別の分割は依存関係・独立更新・単独配布の必要性に基づいて判断します。[採用した配布方針](docs/adr/0009-package-distribution.md)

## 現在使える機能と公開状態

2026年11月25日の作業時点で、公開版は **v1.2.0**、このブランチは **v1.10.0開発候補** です。未マージのv1.3〜v1.9候補（PR #123 / #131 / #137 / #143 / #149 / #156 / #162）へ積み重ねて実装・検証しています。機能実装版、接続契約の版、配布パッケージの版を区別します。

| 機能 | 実装した範囲・操作 | 利用できる版・資料 |
|---|---|---|
| Core・Contracts | Runtime / Registry / Connections / TaskManager、LOCALと子プロセスの併用、6区分の共通接続契約 | 公開v1.2.0に同梱。[Core API](docs/core-api.md)・[接続契約](docs/module-contracts.md) |
| Memory Subsystem | 出典付き記録のSQLite保存、`put` / `get` / `query`（`ntk.memory.records/1`） | v1.1.0から同梱。[Memory](docs/memory.md) |
| Document Adapter | ローカルUTF-8 txt/mdを1記録としてMemoryへ保存、`ingest`（`ntk.document.import/1`） | v1.2.0から同梱。[Document](docs/document.md) |
| Cognition Subsystem | 区切り・概念ラベル付き例の統計学習と根拠照会、`learn` / `inspect`（`ntk.cognition.learning/1`） | v1.3候補から継続。[Cognition](docs/cognition.md) |
| Text Interaction・Cognition訂正 | 観測・教師情報・照会の5操作、revisionと命令ID付き注釈訂正 | v1.4開発候補。[入力・訂正ガイド](docs/interaction.md) |
| Web Adapter | 許可originのHTTP文章取得・HTML本文抽出・Memory保存 | v1.4開発候補。[入力・訂正ガイド](docs/interaction.md) |
| Agency | 根拠と内部状態からの決定・保存、Coreへの適用と活動循環 | v1.5/1.6開発候補。[判断](docs/agency.md)・[実行](docs/agency-execution.md) |
| Persona | 長期特性の参照、外部差分、現在値/修正履歴の原子的保存 | v1.7開発候補。[Persona](docs/persona.md) |
| 睡眠活動の実行側 | 周期・人格案適用・永続結果照合、協調中断/再開 | v1.10開発候補。[睡眠活動](docs/sleep-activity.md) |
| Discord Voice | 明示同意の受信・ASR・音響特徴・期限付き観測。実受信・通常停止と観測0件の退出停止を確認、残る受入は検証中 | v1.10開発候補。[音声](docs/voice.md) |
| Sleep | 根拠の統合/減衰・現在夢の再結合/失効・人格修正案 | v1.9開発候補。[Sleep](docs/sleep.md) |

Agencyの初期決定・保存・照会に加え、v1.6候補で活動登録・変更・中断再開・結果を使う継続判断を実装しています。Personaの保持・参照・外部修正をv1.7候補で追加しました。v1.8候補でPersonaの特性をAgencyの選択へ反映します。v1.9候補でSleepの統合根拠/忘却・夢/人格修正案を追加しました。v1.10候補で睡眠活動の循環とDiscord Voice Adapterを追加し検証中です。実Discord受信の初回成功を確認しましたが、最終受入は未完了、Desktop Adapterは将来課題です。v1.5の実装受入は[B05記録](docs/validation/v1.5.md)、v1.10までの残作業は[進捗](docs/implementation-progress.md)へ記録します。将来案と各段階の採用範囲は[ロードマップ](docs/roadmap.md)にあります。

## v1.10.0開発候補 — 睡眠活動と音声観測

Agencyの睡眠活動からSleep周期とPersona適用を接続し、結果不明を照会する実行側を追加しました。音声側は明示同意・期限付き観測・日本語ASR・所有helper/workerの後処理を実装しています。2026年11月28日の利用者提供ログで、実Discord受信と通常停止に加え、観測0件での参加者変更停止・Bot退出・後処理を確認しました。受信済みデータがある状態での退出・消去、話者照合・参加・撤回・切断などの実機確認は残ります。[各実行の結果と限界](docs/validation/v1.10.md#live-voice-followup)

[睡眠活動](docs/sleep-activity.md)・[音声導入/契約](docs/voice.md)・[ADR 0038](docs/adr/0038-v1.10-sleep-cycle-and-voice.md)・[B10記録](docs/validation/v1.10.md)。音声は任意依存です。v1.9のCIで見つかった終了確認失敗も[#169](https://github.com/Tao-pyth/nymph-toolkit/issues/169)で調査中であり、v1.10全体の完成とはしません。

実音声の残る受入には、本文や個人IDを出さない[ケース別検証ツール](docs/voice.md#voice-live-acceptance)を用意しています。各ケースへの同意と手動操作を確認して明示実行し、合成音声によるツール試験と実Discordの結果を区別します。

## v1.9で追加したSleepの初期統合

Memory原本とCognitionの教師注釈から根拠を統合し、使わない根拠を成功周期ごとに減衰させます。夢の再結合/失効と、初めて評価する実経験から小さな人格修正案を生成します。忘却対象はSleepの現在統合状態で、Memory原本/Cognitionの学習は保持します。Personaへの適用は利用側の明示操作です。

[Sleepガイド](docs/sleep.md)・[ADR 0037](docs/adr/0037-v1.9-sleep.md)・[B09記録](docs/validation/v1.9.md)を参照してください。規則/保存/サービスと実4配置/両経路/再起動、17番目の実行例を確認。全回帰・配布・CI・主要Docsの最終受入は継続中です。

## v1.8で追加したPersonaとAgencyの連携

任意のpersona設定で、人格特性を活動の得点へ反映し、どの版・値・規則で選んだかを判断履歴へ残します。特性の外部更新後に再観測すると、Agencyが選択を見直し、Coreへ中断・切替・再開を依頼します。設定省略時は旧動作を維持し、有効時は別のAgency DB形式2を使用します。

[連携ガイド](docs/persona-agency.md)・[ADR 0036](docs/adr/0036-v1.8-persona-agency.md)・[B08記録](docs/validation/v1.8.md)を参照してください。PR #156 / 9d690eaで全485件・通常配布/16例・9ジョブCI、顧客32ページ/20図のWindows/Linux全表示・全形式照合を確認済みです。未マージです。

## v1.7で追加したPersonaの人格特性

業務契約は`ntk.persona.traits/1`（get/apply/get_update/history）。初期値を再起動で再適用せず、未知形式・破損・設定違いを拒否します。

1〜32の名前付き特性を整数0〜1000で保持し、外部からの差分を観測版・命令ID・根拠付きで適用します。現在値と修正履歴を同一トランザクションで保存し、再起動後も照会できます。Persona自身は更新を開始しません。

[Personaガイド](docs/persona.md)・[ADR 0035](docs/adr/0035-v1.7-persona.md)・[B07記録](docs/validation/v1.7.md)を参照してください。PR #149 / 2acecefで開始競合の修正を含む全469件・通常配布/15例・9ジョブCI、顧客30ページ/19図の全形式/表示を確認済みです。未マージです。

## 前段v1.6.0 — AgencyとTaskManagerの活動循環

Agencyが観測と学習根拠から活動を選び、Coreへ登録・変更・中断/再開・終了を依頼します。実行状態と予定到達を使って継続判断し、明示有効化前や再起動直後には活動を開始しません。14番目の例では実際のCognition学習と、休息への切替・元の活動の再開を確認できます。

[活動循環ガイド](docs/agency-execution.md)・[ADR 0034](docs/adr/0034-v1.6-agency-execution.md)・[B06記録](docs/validation/v1.6.md)で範囲と検証進捗を追います。PR #143 / d0f22ebは全450テスト・通常配布/14例・9ジョブCIが成功。顧客29ページ/18図をWindows/Linuxで確認済みです。未マージです。

## 前段v1.5.0開発候補 — Agencyの活動決定

内部状態・目標とMemory/Cognitionの根拠から活動内容・時刻・期間・優先度・変更案を選び、専用SQLiteへ決定を保存します。同じ決定IDは元の結果を返し、学習後の再評価には新しいIDを使います。[Agencyガイド](docs/agency.md)・[ADR 0032](docs/adr/0032-v1.5-agency-decisions.md)・[B05検証記録](docs/validation/v1.5.md)を参照してください。`python examples/agency_demo.py`が13番目の例です。

v1.5は決定・保存・照会まで。PR #137 / 30f2639は全432テスト・通常配布/13例・9ジョブCI成功、顧客28ページ/17図を確認済みです。TaskManager適用は後続v1.6で具体化しました。公開済みではありません。

## v1.4.0から継承 — 対話・Web入力と学習訂正

R37・[ADR 0031](docs/adr/0031-v1.4-text-web-and-correction.md)で初期範囲を具体化し、親#14・子#126〜#130をコード変更前に登録しました。出典付き観測と明示学習を分け、Memory原本を維持した注釈訂正、命令の重複適用防止、DB形式1→2の移行を追加しています。Web取得は許可origin・UTF-8・上限付きGETです。自由会話や未分割文の自律学習は含みません。

Windows/Python 3.15.2で全411テスト、通常wheel導入・12例・sdist再構築が成功しました。Core API/契約基準と顧客資料27ページ・16図も確認済みです。6ace316の8環境CIとCustomer Docsは全9ジョブ成功し、Linux生成の27ページ/16図も照合しました。[B04記録](docs/validation/v1.4.md)と親#14で追跡します。公開済みではありません。

## 前段v1.3.0開発候補 — Cognition Subsystem

R35により、Memoryの記録へ語の区切りと概念ラベルを添え、語彙頻度・例内の隣接語順・語とラベルの関連を学ぶ最小機構を実装しました。[利用ガイド](docs/cognition.md)、[ADR 0029](docs/adr/0029-v1.3-cognition-learning.md)、[B03検証記録](docs/validation/v1.3.md)に初期スコープ・未採用範囲・結果をまとめています。親[#13](https://github.com/Tao-pyth/nymph-toolkit/issues/13)に子#119〜#122をコード変更前に登録しました。 Cognition実装時に全378テスト・10例・8環境CI・通常wheel/sdistを確認し、[PR #123](https://github.com/Tao-pyth/nymph-toolkit/pull/123)でレビューします。最終SHAと結果は[#122](https://github.com/Tao-pyth/nymph-toolkit/issues/122)に記録します。

v1.3の初期実装をこのcheckoutの1.7.0候補へ継承しています。`python examples/cognition_demo.py`が10番目の開発用例です。根拠ID/hash・出典区分を保持し、専用SQLiteで最大256例を保存、再起動後に同じ統計を再現します。区切りとラベルは要求側の教師情報であり、未分割日本語の分節・完全な構文/意味理解・自律的な概念形成・会話生成は含めません。Core/Memory/Documentの既存契約は維持します。通常導入先は公開済みv1.2.0のままで、v1.3.0のタグ/Releaseは未作成です。

## 公開済みv1.2.0 — Document Adapter

R33により、ローカルUTF-8テキスト/Markdownの取込とMemory連携を実装しました。[Document利用ガイド](docs/document.md)、[ADR 0028](docs/adr/0028-v1.2-document-adapter.md)、[B02検証記録](docs/validation/v1.2.md)に契約・範囲・結果をまとめています。親[#12](https://github.com/Tao-pyth/nymph-toolkit/issues/12)・子#112〜#115をコード変更前に登録しました。R34の[PR #116](https://github.com/Tao-pyth/nymph-toolkit/pull/116)レビューで二重障害時の結果不明保持を修正し、全357テスト・9例・8環境CI・通常wheel/sdistを確認して公開しました。最終SHAと公開後確認は[#117](https://github.com/Tao-pyth/nymph-toolkit/issues/117)に記録済みです。

公開済み配布版は1.2.0です。`python examples/document_demo.py`が9番目の実行例です。1ファイルを1記録に保存し、Memory上限超過は保存せず返します。PDF・URL・分割取込・学習は含めません。[v1.2.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.2.0)から取得できます。

## v1.1.0で追加したMemory Subsystem

R31により経験・知識と出典の最小保存/取得を実装しました。[Memory利用ガイド](docs/memory.md)に3操作・設定・障害時の扱い、[ADR 0027](docs/adr/0027-v1.1-memory.md)に今回の設計判断、[B01記録](docs/validation/v1.1.md)に検証結果をまとめています。親[#11](https://github.com/Tao-pyth/nymph-toolkit/issues/11)、コード変更前に登録した子#105〜#108で追跡します。

全334テスト、8例、Windows/Linux × Python 3.12〜3.15のCI、通常wheel/sdistを確認しました（LinuxはWindows専用6件skip）。Memoryは同じ配布物に同梱し、専用SQLiteへ保存します。v1のCore APIは維持します。学習・記憶統合・忘却・Document Adapterは含めません。8番目の実行例`python examples/memory_demo.py`で保存・再起動取得を試せます。公開先は[v1.1.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.1.0)、公開後確認の記録は[#110](https://github.com/Tao-pyth/nymph-toolkit/issues/110)です。

## Core接続契約と動作基盤

CoreとSubsystem・Adapterをつなぐ6区分の[接続契約](docs/module-contracts.md)を整備しました。公開ContractsのProtocol、登録前検証、安定API基準、両種別・4配置の契約試験を提供します。v0.9から必要なAPI整理を含むため、[移行手順](docs/migration-v1.md)を確認してください。[ADR 0026](docs/adr/0026-v1.0-core-connection-contracts.md)に判断を記録しています。

配布先は[v1.2.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.2.0)。wheel・sdist・引継ぎ書・SHA256SUMSを公開しています。CPython 3.12以上、実行時の外部Python依存はありません。Windows／Linux × CPython 3.12〜3.15で検証しています。公開後の取得確認と完了結果は[公開課題 #117](https://github.com/Tao-pyth/nymph-toolkit/issues/117)に記録済みです。

公開v1.2.0の成果物はCore・Contracts、最小MemoryとDocument Adapterのライブラリです。9つの実行例で起動・接続・活動・別プロセス実行・文書取込を試せます。開発候補v1.10.0はCognition・Text/Web・訂正・Agencyの判断/活動循環・Persona連携・Sleepと睡眠活動・音声を含み、通常の実行例は19例です。音声依存と実Discord接続は[音声ガイド](docs/voice.md)の明示手順を使い、初回成功と未確認の受入項目を区別します。Text例には明示指示を受けるJSON-linesモードもあります。各例は後処理を終えると終了します。会話相手としてのNymph、常駐アプリ、GUIは未実装です。

| 実装済みの責務 | 主な機能 |
|---|---|
| Runtime | 起動・実行・停止、失敗と後処理の管理 |
| Registry | 機能の登録・識別・依存確認。ModuleGroupで複数機能を実行 |
| Connections | 契約に合う候補の照会、要求側が選んだ接続の管理、直接／Core経由通信、FileStoreによる保存 |
| TaskManager | Nymphが指定する活動の時刻・期間・変更・実行状態の管理 |

HybridGroup・HybridTaskManagerにより、同一PC・同じPython環境でLOCAL／Core所有の子プロセスを組み合わせられます。機能の構成は起動前に決め、稼働中は固定します。接続の初回追加はできますが、確定済みの接続先は稼働中に変更しません。

**Nymphが活動内容・時刻・期間・優先度・変更を決め、Coreが実行を管理します。** 予定時間に達すると通知して活動を継続し、終了指示後は実行側の安全な区切りと後処理を待ちます。再起動後の活動の再登録・再開もNymphが判断します。

通信はCoreが管理・許可した直接接続とCore経由を利用できます。Coreは候補・属性・稼働情報を返し、要求側が利用先を選びます。採用した契約は[Core API](docs/core-api.md)、判断履歴は[ADR索引](docs/adr/README.md)で確認できます。

## 目的から読む

| やりたいこと | 最初に読む資料 | 確認できること |
|---|---|---|
| 導入・接続の全体像を説明する | [顧客向け契約・利用ガイド](docs/customer-guide.md) → [PDF/HTMLの取得・同期手順](docs/customer-guide-authoring.md) | Core・6契約・Memory・Document・Cognition・Text/Web・訂正・Agencyの図解。公開版と開発候補を区別 |
| 公開版を試す | [インストールと最初の実行](docs/getting-started.md) → [9つの実行例](docs/tutorials.md) | Windows/Linuxの通常導入、期待出力、正常終了、ログ |
| 機能を接続する | [Architecture](docs/architecture.md) → [Core API](docs/core-api.md) | 責務と配置、現在の契約、各機能Docsへの入口 |
| 開発に参加する | [参加方針](CONTRIBUTING.md) → [Issue運用](docs/issue-workflow.md) → [開発手順](docs/development.md) | 着手前の課題管理、editable環境、テストと配布検証 |
| 問題を調べる | [トラブルシューティング](docs/troubleshooting.md) | 症状からの確認・対処・回復確認、報告に必要な情報 |
| 設計と経緯を追う | [Docs索引](docs/README.md) → [ADR](docs/adr/README.md)・[ロードマップ](docs/roadmap.md) | 採用済み事項、提案、過去の判断と受入 |
| 一つの文書で引き継ぐ | [日本語引継ぎ書](docs/NTK-Core-v0.1-Handoff-ja.md) | 現在のREADME・Docs・ADR・検証記録の全文 |

通常導入は公開wheelを使います。開発手順の `pip install -e .` は作業ツリーを読む開発用導入です。wheelには実行例が入っていないため、導入ガイドでは同じ版のsdistから例を取得します。

## 検証結果と今後の範囲

v1.0.0は316テスト（製品304件＋検査12件）、7実行例、全8環境CI、通常wheelとsdistの再現を確認しています。LinuxではWindows専用6件をskipします。[B00検証記録](docs/validation/v1.0.md)と[採用64項目](docs/validation/core-coverage.md)を参照してください。最終コミット・マージ後CI・タグ・公開添付の照合結果は[#104](https://github.com/Tao-pyth/nymph-toolkit/issues/104)で追跡します。

30分の負荷測定はv0.8の特定コミットに対する結果です。後続修正の検証範囲とともに[v0.8検証記録](docs/validation/v0.8.md)へ記録しており、現在の全環境で同じ長時間性能を保証するものではありません。

v0.1.0はGitHub公開、v0.9.0は合意したCore機能完成の節目です。v1.0.0はCoreとSubsystem・Adapterの接続契約整備の節目です。v1.1 MemoryはR31・ADR 0027で初期範囲を具体化しました。v1.2はR33・ADR 0028でDocumentの初期範囲を具体化しました。v1.3はR35・ADR 0029で初期学習の範囲を具体化しました。v1.4はR37・ADR 0031で範囲を具体化しました。v1.5はADR 0032、v1.6はADR 0034、v1.7はADR 0035で具体化しました。v1.8はADR 0036で具体化しました。v1.9はADR 0037で具体化しました。後続v1.10.0の名称・実装順・機能配分、奇数／偶数マイナーの運用は提案段階です。最終ビジョンと各版の実装範囲を区別します。

将来のPC全体の状況取得はAdapterが担当します。Desktop Adapterはv1.10.0までの配分に含めず将来課題とし、複製・移植・伝播機構は初期スコープ外です。

顧客向けMarkdown・PDF・HTMLも主要Docsとして、対象コミットの実装と同時に更新します。[ADR 0030](docs/adr/0030-customer-docs-as-primary.md)に基づき、同期検査・CI生成・表示確認を必須にしました。最新コミットの一式は[Customer Docsの取得手順](docs/customer-guide-authoring.md)を参照してください。公開済みタグ・Release添付は当時の記録として保持します。過去の変更は[CHANGELOG](CHANGELOG.md)にあります。

## ライセンス

NTKの自作コード、Contracts、設計文書には **Apache License 2.0（SPDX: `Apache-2.0`）** を適用します。設計文書にはREADME、Docs・ADR、配布用引継ぎ書を含みます。将来の自作Subsystem・Adapterにもこの方針を適用し、パッケージ分割後も各配布物にライセンスを含めます。

ライセンス本文は[LICENSE](LICENSE)、採用理由と適用範囲は[ADR 0011](docs/adr/0011-apache-2.0-license.md)を参照してください。第三者のコード・依存ライブラリ・モデル・文書・音声などは各権利者の条件に従います。Nymphの会話・記憶・人格データへ、このソフトウェアライセンスを一律に適用するものではありません。
