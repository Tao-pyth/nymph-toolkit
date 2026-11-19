# ADR 0001 Coreと統合リポジトリ

## 状態

確定。記録日2026年11月19日。置換元・置換先なし。

## 背景

Nymphの活動を支える基盤を、着脱する機能とともに段階的に開発する。

## 決定

Coreを中心にSubsystem・Adapterを着脱する。Core Runtime、Registry、Connections、TaskManagerの4責務を設ける。GitHubの統合リポジトリ名は `nymph-toolkit` とする。

## 影響

Coreの初期開発、設計、ADR、検証を統合リポジトリで管理する。具体的なコード配置はarchitectureの案を用いる。

## 未決事項

Subsystem・Adapterの公開API、登録ID、依存関係、稼働中着脱の可否、取り外し時の処理。公開先アカウントとライセンスはreleaseの判断欄で管理する。

## 根拠

R2の確定事項と統合リポジトリの指定、R3の文書・配置計画。元会話全文の確認状況は[Docsの根拠表](../README.md)を参照する。
