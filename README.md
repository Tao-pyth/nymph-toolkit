# Nymph Toolkit（NTK）

Nymph Toolkit（NTK）は、人間との継続的な交流や外部環境での経験を通じて、知識・言語・行動能力・人格を発達させる人工人格「Nymph」を構築するためのソフトウェア基盤です。Apache-2.0で開発資料を公開し、オープンソースでの実装を進めます。GitHubの統合リポジトリは [Tao-pyth/nymph-toolkit](https://github.com/Tao-pyth/nymph-toolkit) です。

**Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指します。** 限定的な能力から「赤ちゃんを育てるような感覚」で成長を支え、自然な日本語で交流し、権限の範囲でPC環境を観測・操作できる姿を最終目標とします。

基本機構と経験から獲得する知識を区別し、言語獲得そのものを研究します。既存LLMを言語理解・文章生成の中核にする方式は採らず、音声認識などの補助技術は利用できます。記憶・自己理解・自律活動・人格・睡眠の長期構想と評価領域は[Project Vision](docs/vision.md)にまとめています。最終的な完成を特定のバージョンに固定せず、各段階で実装範囲と到達基準を具体化します。

構成は、Nymphが決めた活動を実行管理するCoreを中心に、Subsystem・Adapterを着脱するPython基盤です。

配布方針は、単一リポジトリでCoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterを必要に応じて分割するものです。個別の分割は依存関係・独立更新・単独配布の必要性に基づいて判断します。[採用した配布方針](docs/adr/0009-package-distribution.md)

## 現在の段階

**v0.6.0：活動の予定変更・中断再開・優先度。** CoreとContractsの単一パッケージにRuntime・Registry・ModuleGroup・Connections・FileStore・TaskManagerを含みます。CPython 3.12以上、実行時の外部依存はありません。

予定時間に達するとNymphへ通知して活動を継続し、終了指示を受けた実行側が安全な区切りで終了します。受付時点で過去の開始時刻なら開始せず返し、再起動後は過去履歴を渡してNymphが再登録・再開を判断します。Coreによる活動の価値判断、自動延長、自動再実行は行いません。[操作契約](docs/task-manager.md)と[ADR 0020](docs/adr/0020-v0.5-task-manager.md)に採用範囲を記録しています。

A06では219テスト、5実行例、Windows／Linux・Python 3.12〜3.15の全8環境、wheelの通常インストールとsdist再ビルドを確認しました。時刻・期間・優先度変更、同じ処理の続きからの再開、任意の実行枠、要求ID・観測版による競合処理を含みます。[v0.6受入記録](docs/validation/v0.6.md)に証拠と制約をまとめています。IPC・本番Subsystemは後続段階です。

v0.1.0は初期資料・開発基盤、v0.2.0は最小Runtime、v0.3.0はRegistry・ModuleGroup、v0.4.0はConnections・非同期保存と救命処理の公開です。v0.9.0は合意したCore機能の完成を目標とします。v0.7〜v0.8の機能配分は開発計画案です。

採用範囲のA04では129件のテスト、3実行例、Windows／Linux・Python 3.12〜3.15、通常インストール・sdist再ビルドと性能測定を確認しました。[Connectionsの操作契約](docs/connections.md)と[v0.4受入記録](docs/validation/v0.4.md)に、使い方・結果・制約を記載しています。

v0.3では実行開始前にSubsystem・Adapterのダミーを着脱し、起動から停止完了まで構成を固定します。停止後は明示解除できます。実体の稼働中着脱は、接続の解除・失効契約を設計する後続段階へ残しています。利用方法は[RegistryとModuleGroup](docs/registry.md)を参照してください。

[v0.6.0のリリース](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.6.0)にwheel・sdist・引継ぎ書・チェックサムを掲載します。最終SHA・CI・公開後の取得確認は[公開課題 #59](https://github.com/Tao-pyth/nymph-toolkit/issues/59)で追跡します。過去の[v0.5.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.5.0)・[v0.4.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.4.0)・[v0.3.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.3.0)・[v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.2.0)・[v0.1.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.1.0)は各公開時点の記録として保持します。

V0.1・V0.9は、それぞれv0.1.0・v0.9.0の節目を表します。v1.0.0はCoreとSubsystem・Adapterの接続契約を大きく形作る目標です。v1.1.0〜v1.10.0のSubsystem・Adapter開発、奇数・偶数マイナーのリリース運用は設計提案としてロードマップに追記しています。記載するSubsystem名・Adapter名は暫定名称で、実装順序と機能配分も変更される可能性があります。

Nymphが活動内容・時刻・期間・変更を決め、Coreが実行を管理します。初期開発ではCore Runtime、Registry、Connections、TaskManagerを実装し、周辺をダミーで検証します。ハイブリッド実行を採用し、Python `asyncio` と軽量なメソッド呼び出しを技術の方向性とします。

活動の価値や優先度はNymphが判断します。R18により、**開始時刻変更・期間変更・優先度・中断再開の4項目すべてをv0.6の対象として採用**しました。一問一答の回答と、残事項をCodexが決定してよいという委任に基づき、対応状態・計時・優先度と任意の実行枠・競合・API・受入条件を設計しました。[ADR 0021](docs/adr/0021-v0.6-activity-changes.md)と[設計Issue #52](https://github.com/Tao-pyth/nymph-toolkit/issues/52)に判断元を分けて記録しています。子Issue #53〜#58で採用範囲の実装・A06・配布を確認しました。#59で最終公開と匿名取得を追跡します。設計採用と各検証・公開の完了を区別します。

通信は、**Coreが管理・許可した接続ではSubsystem間の直接通信を認める**方針を採用しました。Core経由の通信も利用できます。方針の採用履歴は[ADR 0015](docs/adr/0015-core-authorized-direct-communication.md)、現在の公開入口・状態・失効の実装判断はADR 0019に記録しています。

接続管理では、Coreが契約に合致する候補一覧を返し、要求側の機能が属性・稼働状況を評価して利用先を選びます。接続設定を永続保存し、稼働中の初回追加を認めつつ確定済み接続先を固定します。起動時・申請されたヘルスチェックで存在・稼働状態・宣言契約の互換性を確認し、確立後は利用ごとの再審査を省きます。[ADR 0017](docs/adr/0017-connection-binding-and-health.md)の方針を、[ADR 0018](docs/adr/0018-connection-selection-health-and-recovery.md)で具体化しています。

稼働情報は機能側から変更時に通知し、実際の受付は提供側が判断します。容量不足には即時応答し、ヘルス確認中・中断中の新規要求は要求側指定の期限まで待機します。連携エラーでは要求元機能が通知に従って中断・後処理し、同じ相手の正常確認後に新規要求から再開します。履歴は期間別ファイルへ非同期にまとめて保存します。通常のバッファには上限を設けず受付を継続し、保存障害時は新規受付を停止して古い履歴の退避による救命措置を行います。

失効は接続の不整合によるエラー回避を目的とし、機能側がCoreの管理結果に従うことを前提とします。望まない参照の継続を強制遮断する仕組みは、この接続管理の要件に含めません。

## 開発を始める方へ

CPython 3.12以上で、リポジトリ直下から次を実行できます（PowerShell）。LinuxではPythonのパスを `.venv/bin/python` に置き換えてください。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe examples/runtime_demo.py
.venv/Scripts/python.exe examples/registry_demo.py
.venv/Scripts/python.exe examples/connections_demo.py
.venv/Scripts/python.exe examples/task_manager_demo.py
.venv/Scripts/python.exe -W error -m unittest discover -s tests -t . -v
```

Runtimeのダミーはstart → run → stopを表示します。Registryのダミーは登録・解除と依存順の実行を、Connectionsのダミーは選定・操作・接続保存・再起動後の再利用を確認します。TaskManagerのダミーは予定到達後の継続、安全な終了、再起動後の履歴参照と明示再登録を確認します。いずれも終了後の残存タスク0件を確認します。[Runtimeの使い方](docs/runtime.md)と[ビルド・配布検証](docs/development.md)も参照してください。

コード変更は、**対象バージョンのマイルストーン → 親Issue → 対応単位の子Issue登録 → 対応**の順を必須とします。[Issue運用と登録済み課題](docs/issue-workflow.md)を確認してから着手してください。登録した計画案は、仕様の採用と区別します。

- 全体を一つの文書で読む場合は、[日本語初期設計・Codex引継ぎ書](docs/NTK-Core-v0.1-Handoff-ja.md)を参照してください。
- 個別の設計や判断を更新する場合は、[Docs一覧と根拠の扱い](docs/README.md)から進んでください。
- 開発の段階と完了条件は、[ロードマップ](docs/roadmap.md)と[受入基準案](docs/acceptance.md)にあります。
- Gitの用意は[開発手順](docs/development.md)、公開先と公開手順は[リリース手順](docs/release.md)にあります。
- 提案・修正への参加方法は[CONTRIBUTING](CONTRIBUTING.md)を参照してください。公開先は個人アカウント配下の `Tao-pyth/nymph-toolkit`（public）に決定しています。

将来のPC状況取得はAdapterで扱います。Desktop Adapterはv1.10.0までの配分に含めず将来課題とします。複製・移植・伝播機構は初期スコープ外です。

## ライセンス

NTKの自作コード、Contracts、設計文書には **Apache License 2.0（SPDX: `Apache-2.0`）** を適用します。設計文書にはREADME、Docs・ADR、配布用引継ぎ書を含みます。将来の自作Subsystem・Adapterにもこの方針を適用し、パッケージ分割後も各配布物にライセンスを含めます。

ライセンス本文は[LICENSE](LICENSE)、採用理由と適用範囲は[ADR 0011](docs/adr/0011-apache-2.0-license.md)を参照してください。第三者のコード・依存ライブラリ・モデル・文書・音声などは各権利者の条件に従います。Nymphの会話・記憶・人格データへ、このソフトウェアライセンスを一律に適用するものではありません。
