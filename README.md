# Nymph Toolkit（NTK）

Nymph Toolkit（NTK）は、人間との継続的な交流や外部環境での経験を通じて、知識・言語・行動能力・人格を発達させる人工人格「Nymph」を構築するためのソフトウェア基盤です。Apache-2.0で開発資料を公開し、オープンソースでの実装を進めます。GitHubの統合リポジトリは [Tao-pyth/nymph-toolkit](https://github.com/Tao-pyth/nymph-toolkit) です。

**Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指します。** 限定的な能力から「赤ちゃんを育てるような感覚」で成長を支え、自然な日本語で交流し、権限の範囲でPC環境を観測・操作できる姿を最終目標とします。

基本機構と経験から獲得する知識を区別し、言語獲得そのものを研究します。既存LLMを言語理解・文章生成の中核にする方式は採らず、音声認識などの補助技術は利用できます。記憶・自己理解・自律活動・人格・睡眠の長期構想と評価領域は[Project Vision](docs/vision.md)にまとめています。最終的な完成を特定のバージョンに固定せず、各段階で実装範囲と到達基準を具体化します。

構成は、Nymphが決めた活動を実行管理するCoreを中心に、Subsystem・Adapterを着脱するPython基盤です。

配布方針は、単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterを必要に応じて分割するものです。個別の分割は依存関係・独立更新・単独配布の必要性に基づいて判断します。[採用した配布方針](docs/adr/0009-package-distribution.md)

## 現在の段階

**v0.9.0を公開済みです。合意したCore機能の完成を、ダミーで検証しました。** [v0.9.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.9.0)からwheel・sdist・引継ぎ書・SHA256SUMSを取得できます。CPython 3.12以上、実行時の外部Python依存はありません。公開時の検証範囲はWindows／Linux × CPython 3.12〜3.15です。

現在の成果物はCoreとContractsのライブラリです。6つの実行例で起動・接続・活動・別プロセス実行を試せます。各例は後処理を終えると終了します。人工人格としての会話・学習を行う本番Subsystem、常駐アプリ、GUIはこの版に含まれません。

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
| 導入・接続の全体像を説明する | [顧客向け契約・利用ガイド](docs/customer-guide.md) | 図解付きの現行契約・設定・運用と開発者向けAPI付録 |
| 公開版を試す | [インストールと最初の実行](docs/getting-started.md) → [6つの実行例](docs/tutorials.md) | Windows/Linuxの通常導入、期待出力、正常終了、ログ |
| 機能を接続する | [Architecture](docs/architecture.md) → [Core API](docs/core-api.md) | 責務と配置、現在の契約、各機能Docsへの入口 |
| 開発に参加する | [参加方針](CONTRIBUTING.md) → [Issue運用](docs/issue-workflow.md) → [開発手順](docs/development.md) | 着手前の課題管理、editable環境、テストと配布検証 |
| 問題を調べる | [トラブルシューティング](docs/troubleshooting.md) | 症状からの確認・対処・回復確認、報告に必要な情報 |
| 設計と経緯を追う | [Docs索引](docs/README.md) → [ADR](docs/adr/README.md)・[ロードマップ](docs/roadmap.md) | 採用済み事項、提案、過去の判断と受入 |
| 一つの文書で引き継ぐ | [日本語引継ぎ書](docs/NTK-Core-v0.1-Handoff-ja.md) | 現在のREADME・Docs・ADR・検証記録の全文 |

通常導入は公開wheelを使います。開発手順の `pip install -e .` は作業ツリーを読む開発用導入です。wheelには実行例が入っていないため、導入ガイドでは同じ版のsdistから例を取得します。

## 検証結果と今後の範囲

v0.9.0は300テスト（製品293件＋資料検査7件）、6実行例、全8環境CI、通常配布の再現を確認しました。A09-04を含む公開後の照合と親Issue #9・マイルストーンの完了は[公開課題 #88の結果](https://github.com/Tao-pyth/nymph-toolkit/issues/88#issuecomment-7067230161)で確認できます。[v0.9検証記録](docs/validation/v0.9.md)は公開前の確認と公開後の参照先を区別し、[64項目の対応表](docs/validation/core-coverage.md)で採用範囲を追跡できます。

30分の負荷測定はv0.8の特定コミットに対する結果です。後続修正の検証範囲とともに[v0.8検証記録](docs/validation/v0.8.md)へ記録しており、現在の全環境で同じ長時間性能を保証するものではありません。

v0.1.0はGitHub公開、v0.9.0は合意したCore機能完成の節目です。次のv1.0.0はCoreとSubsystem・Adapterの接続契約を大きく形作る目標です。v1.1.0〜v1.10.0の名称・実装順・機能配分、奇数／偶数マイナーの運用は提案段階です。最終ビジョンと各版の実装範囲を区別します。

将来のPC全体の状況取得はAdapterが担当します。Desktop Adapterはv1.10.0までの配分に含めず将来課題とし、複製・移植・伝播機構は初期スコープ外です。

このREADMEと新しい利用ガイドはv0.9.0公開後も更新します。公開済みタグ・Release添付は公開時点の記録として保持します。今回のDocs整備は[導入資料の検証](docs/validation/docs-onboarding.md)・[顧客資料の検証](docs/validation/customer-guide.md)、過去の変更は[CHANGELOG](CHANGELOG.md)を参照してください。顧客資料は[配布用PDF・HTMLの再生成手順](docs/customer-guide-authoring.md)も用意しています。

## ライセンス

NTKの自作コード、Contracts、設計文書には **Apache License 2.0（SPDX: `Apache-2.0`）** を適用します。設計文書にはREADME、Docs・ADR、配布用引継ぎ書を含みます。将来の自作Subsystem・Adapterにもこの方針を適用し、パッケージ分割後も各配布物にライセンスを含めます。

ライセンス本文は[LICENSE](LICENSE)、採用理由と適用範囲は[ADR 0011](docs/adr/0011-apache-2.0-license.md)を参照してください。第三者のコード・依存ライブラリ・モデル・文書・音声などは各権利者の条件に従います。Nymphの会話・記憶・人格データへ、このソフトウェアライセンスを一律に適用するものではありません。
