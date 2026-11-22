# Nymph Toolkit（NTK）

Nymph Toolkit（NTK）は、人間との継続的な交流や外部環境での経験を通じて、知識・言語・行動能力・人格を発達させる人工人格「Nymph」を構築するためのソフトウェア基盤です。Apache-2.0で開発資料を公開し、オープンソースでの実装を進めます。GitHubの統合リポジトリは [Tao-pyth/nymph-toolkit](https://github.com/Tao-pyth/nymph-toolkit) です。

**Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指します。** 限定的な能力から「赤ちゃんを育てるような感覚」で成長を支え、自然な日本語で交流し、権限の範囲でPC環境を観測・操作できる姿を最終目標とします。

基本機構と経験から獲得する知識を区別し、言語獲得そのものを研究します。既存LLMを言語理解・文章生成の中核にする方式は採らず、音声認識などの補助技術は利用できます。記憶・自己理解・自律活動・人格・睡眠の長期構想と評価領域は[Project Vision](docs/vision.md)にまとめています。最終的な完成を特定のバージョンに固定せず、各段階で実装範囲と到達基準を具体化します。

構成は、Nymphが決めた活動を実行管理するCoreを中心に、Subsystem・Adapterを着脱するPython基盤です。

配布方針は、単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterを必要に応じて分割するものです。個別の分割は依存関係・独立更新・単独配布の必要性に基づいて判断します。[採用した配布方針](docs/adr/0009-package-distribution.md)

## v1.2.0開発候補 — Document Adapter

R33により、ローカルUTF-8テキスト/Markdownの取込とMemory連携を実装しています。[Document利用ガイド](docs/document.md)、[ADR 0028](docs/adr/0028-v1.2-document-adapter.md)、[B02検証記録](docs/validation/v1.2.md)に契約・範囲・結果をまとめています。親[#12](https://github.com/Tao-pyth/nymph-toolkit/issues/12)・子#112〜#115をコード変更前に登録しました。

このcheckoutの配布候補は1.2.0です。`python examples/document_demo.py`が9番目の開発用実行例です。1ファイルを1記録に保存し、Memory上限超過は保存せず返します。PDF・URL・分割取込・学習は含めません。公開済みの通常導入先は引き続きv1.1.0で、v1.2.0のタグ/Releaseは未作成です。

## 公開済みv1.1.0 — Memory Subsystem

R31により経験・知識と出典の最小保存/取得を実装しました。[Memory利用ガイド](docs/memory.md)に3操作・設定・障害時の扱い、[ADR 0027](docs/adr/0027-v1.1-memory.md)に今回の設計判断、[B01記録](docs/validation/v1.1.md)に検証結果をまとめています。親[#11](https://github.com/Tao-pyth/nymph-toolkit/issues/11)、コード変更前に登録した子#105〜#108で追跡します。

全334テスト、8例、Windows/Linux × Python 3.12〜3.15のCI、通常wheel/sdistを確認しました（LinuxはWindows専用6件skip）。Memoryは同じ配布物に同梱し、専用SQLiteへ保存します。v1のCore APIは維持します。学習・記憶統合・忘却・Document Adapterは含めません。8番目の実行例`python examples/memory_demo.py`で保存・再起動取得を試せます。公開先は[v1.1.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.1.0)、公開後確認の記録は[#110](https://github.com/Tao-pyth/nymph-toolkit/issues/110)です。

## Core接続契約と動作基盤

CoreとSubsystem・Adapterをつなぐ6区分の[接続契約](docs/module-contracts.md)を整備しました。公開ContractsのProtocol、登録前検証、安定API基準、両種別・4配置の契約試験を提供します。v0.9から必要なAPI整理を含むため、[移行手順](docs/migration-v1.md)を確認してください。[ADR 0026](docs/adr/0026-v1.0-core-connection-contracts.md)に判断を記録しています。

配布先は[v1.1.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.1.0)。wheel・sdist・引継ぎ書・SHA256SUMSを公開対象とします。CPython 3.12以上、実行時の外部Python依存はありません。Windows／Linux × CPython 3.12〜3.15で検証しています。公開後の取得確認と完了結果は[公開課題 #110](https://github.com/Tao-pyth/nymph-toolkit/issues/110)に記録します。

成果物はCore・Contractsと最小Memoryのライブラリです。8つの実行例で起動・接続・活動・別プロセス実行を試せます。各例は後処理を終えると終了します。本番の会話・学習Subsystem、常駐アプリ、GUIは含まれません。

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
| 導入・接続の全体像を説明する | [顧客向け契約・利用ガイド（v0.9版）](docs/customer-guide.md) | 図解付きの現行契約・設定・運用と開発者向けAPI付録 |
| 公開版を試す | [インストールと最初の実行](docs/getting-started.md) → [8つの実行例](docs/tutorials.md) | Windows/Linuxの通常導入、期待出力、正常終了、ログ |
| 機能を接続する | [Architecture](docs/architecture.md) → [Core API](docs/core-api.md) | 責務と配置、現在の契約、各機能Docsへの入口 |
| 開発に参加する | [参加方針](CONTRIBUTING.md) → [Issue運用](docs/issue-workflow.md) → [開発手順](docs/development.md) | 着手前の課題管理、editable環境、テストと配布検証 |
| 問題を調べる | [トラブルシューティング](docs/troubleshooting.md) | 症状からの確認・対処・回復確認、報告に必要な情報 |
| 設計と経緯を追う | [Docs索引](docs/README.md) → [ADR](docs/adr/README.md)・[ロードマップ](docs/roadmap.md) | 採用済み事項、提案、過去の判断と受入 |
| 一つの文書で引き継ぐ | [日本語引継ぎ書](docs/NTK-Core-v0.1-Handoff-ja.md) | 現在のREADME・Docs・ADR・検証記録の全文 |

通常導入は公開wheelを使います。開発手順の `pip install -e .` は作業ツリーを読む開発用導入です。wheelには実行例が入っていないため、導入ガイドでは同じ版のsdistから例を取得します。

## 検証結果と今後の範囲

v1.0.0は316テスト（製品304件＋検査12件）、7実行例、全8環境CI、通常wheelとsdistの再現を確認しています。LinuxではWindows専用6件をskipします。[B00検証記録](docs/validation/v1.0.md)と[採用64項目](docs/validation/core-coverage.md)を参照してください。最終コミット・マージ後CI・タグ・公開添付の照合結果は[#104](https://github.com/Tao-pyth/nymph-toolkit/issues/104)で追跡します。

30分の負荷測定はv0.8の特定コミットに対する結果です。後続修正の検証範囲とともに[v0.8検証記録](docs/validation/v0.8.md)へ記録しており、現在の全環境で同じ長時間性能を保証するものではありません。

v0.1.0はGitHub公開、v0.9.0は合意したCore機能完成の節目です。v1.0.0はCoreとSubsystem・Adapterの接続契約整備の節目です。v1.1 MemoryはR31・ADR 0027で初期範囲を具体化しました。v1.2はR33・ADR 0028でDocumentの初期範囲を具体化しました。v1.3.0〜v1.10.0の名称・実装順・機能配分、奇数／偶数マイナーの運用は提案段階です。最終ビジョンと各版の実装範囲を区別します。

将来のPC全体の状況取得はAdapterが担当します。Desktop Adapterはv1.10.0までの配分に含めず将来課題とし、複製・移植・伝播機構は初期スコープ外です。

公開済みタグ・Release添付は公開時点の記録として保持します。顧客向け図解・PDFはv0.9版の資料です。v1.0では接続契約と移行手順を併読してください。過去の変更は[CHANGELOG](CHANGELOG.md)を参照してください。

## ライセンス

NTKの自作コード、Contracts、設計文書には **Apache License 2.0（SPDX: `Apache-2.0`）** を適用します。設計文書にはREADME、Docs・ADR、配布用引継ぎ書を含みます。将来の自作Subsystem・Adapterにもこの方針を適用し、パッケージ分割後も各配布物にライセンスを含めます。

ライセンス本文は[LICENSE](LICENSE)、採用理由と適用範囲は[ADR 0011](docs/adr/0011-apache-2.0-license.md)を参照してください。第三者のコード・依存ライブラリ・モデル・文書・音声などは各権利者の条件に従います。Nymphの会話・記憶・人格データへ、このソフトウェアライセンスを一律に適用するものではありません。
