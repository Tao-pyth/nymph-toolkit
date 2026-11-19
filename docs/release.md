# 公開準備とリリース手順

GitHub公開をV0.1、Core機能完成をV0.9とする目標は確定している。現在は公開準備段階である。以下は実際に公開する際の手順と判断欄である。

## 公開前の判断欄

| 項目 | 現在の状態 | 公開前に記録する内容 |
|---|---|---|
| リポジトリ名 | 確定 | `nymph-toolkit` |
| 公開先アカウント | 要決定 | 所有者のアカウントまたは組織。接続アカウント `Tao-pyth` は確認済み |
| 公開範囲 | 要決定 | publicで公開するか、private準備を経てpublicにするか。private準備はV0.1公開前として扱う案 |
| ライセンス | 要決定 | 採用ライセンスまたは利用許諾の扱いを明示的に決め、必要な文書を配置 |
| 公開対象 | 準備済み資料を確認する段階 | README、Docs・ADR、CHANGELOG、Git設定、決定後のLICENSE等 |
| 公開URL・remote | 未設定 | 実際の所有者・リポジトリURLと `origin` |
| V0.1タグ・公開日 | 未作成・未記入 | `v0.1.0`、対象コミットSHA、実際の公開日 |

公開先の接続確認と、公開先の選定はそれぞれ記録する。ライセンスは所有者が決定する。文書中の候補や作業者の便宜から採用を推定しない。

## 公開前チェックリスト

- [ ] 公開先アカウント・公開範囲・ライセンスの判断欄を埋める。
- [ ] READMEにその時点の実装状況を記載する。
- [ ] Docs・ADRの確定事項、未決事項、根拠を確認する。
- [ ] 単一配布用引継ぎ書を個別Docsと同期する。
- [ ] ステージした一覧と差分を読み、公開対象を確認する。
- [ ] 初回コミットとローカルGitの作成者設定を確認する。
- [ ] 文書リンク、文字コード、改行、受入IDの対応を確認する。
- [ ] README・CHANGELOG・本書の公開時の更新を準備する。

## GitHubへの接続とpush

GitHubで、決定済みの所有者の配下に `nymph-toolkit` を作成する。ローカル履歴から開始する場合はREADME・LICENSE・gitignoreの自動作成を選ばず、空のリポジトリを用意する。既存リポジトリがある場合は内容と履歴を確認してから接続する。

以下はPowerShellの例。`OWNER` は決定した所有者へ置き換える。認証には設定済みのGit認証手段を使う。

```powershell
git remote -v
git remote add origin https://github.com/OWNER/nymph-toolkit.git
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

## V0.1のタグとリリース

公開内容を確認したら、READMEの状態を「V0.1公開済み」に更新し、実装状況を具体的に記す。CHANGELOGの未リリース項目に実際の公開日を記録し、本書の判断欄・公開URLを埋める。単一配布用引継ぎ書も同期してコミット・pushする。

```powershell
git add -- README.md CHANGELOG.md docs
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

## 公開後の確認と次の段階

新しい作業フォルダへcloneし、READMEからDocs・ADRをたどる。公開前にローカルで行った確認に加え、GitHubの表示と取得可能性をA01として記録する。private準備中ならV0.1の公開完了は保留する。

V0.2以降は対応する受入結果、READMEの実装状況、CHANGELOG、文書を更新してからタグ・リリースを記録する案を用いる。V0.9では全採用機能の結果と残課題を記載し、Core完成の判定根拠を示す。
