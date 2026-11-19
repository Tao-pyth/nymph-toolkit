# Nymph Toolkit（NTK）

Nymph Toolkitは、Nymphが決めた活動を実行管理するCoreを中心に、Subsystem・Adapterを着脱して利用するPython基盤です。GitHubの統合リポジトリ名は `nymph-toolkit` です。

## 現在の段階

**公開準備中。Coreコードと実行テストは未実装です。** GitHub公開をV0.1、合意したCore機能の完成をV0.9の目標とします。V0.2〜V0.8の機能配分は開発計画案です。

Nymphが活動内容・時刻・期間・変更を決め、Coreが実行を管理します。初期開発ではCore Runtime、Registry、Connections、TaskManagerを実装し、周辺をダミーで検証します。ハイブリッド実行を採用し、Python `asyncio` と軽量なメソッド呼び出しを技術の方向性とします。

活動の価値や優先度はNymphが判断します。優先度機能を採用する場合、Coreは与えられた値と採用済み規則に基づいて実行順序を処理します。時間変更、優先度変更、中断・再開などの具体的な採否はV0.6の判断対象です。

通信について最後に正式採用された方針はCore経由のみです。その後の直接接続を認める緩和案は未採用で、Connections実装前の判断事項です。

## 開発を始める方へ

- 全体を一つの文書で読む場合は、[日本語初期設計・Codex引継ぎ書](docs/NTK-Core-v0.1-Handoff-ja.md)を参照してください。
- 個別の設計や判断を更新する場合は、[Docs一覧と根拠の扱い](docs/README.md)から進んでください。
- 開発の段階と完了条件は、[ロードマップ](docs/roadmap.md)と[受入基準案](docs/acceptance.md)にあります。
- Gitの用意は[開発手順](docs/development.md)、公開先・ライセンスの未決事項と公開手順は[リリース手順](docs/release.md)にあります。

将来のPC状況取得はAdapterで扱います。複製・移植は初期スコープ外です。ライセンスは公開前の判断事項です。
