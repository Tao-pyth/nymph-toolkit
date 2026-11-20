# 開発準備とGit運用

## 公開準備時の環境

2026年11月19日の作業環境ではGit 2.56.0.windows.4とPython 3.8が存在した。このPython版はNTKの対応版を意味しない。対応Python版、依存管理、テストツールはV0.2着手時に決め、`pyproject.toml` と本書に記録する。

現在の成果物は資料とGit設定である。Coreのインストール・起動・実行テストのコマンドは実装後に掲載する。

## 実装開始時の配布構成

[ADR 0009](adr/0009-package-distribution.md)に従い、初期はCoreとContractsを一つの配布パッケージとして扱う。ルートの `pyproject.toml` に配布設定を置き、`src/nymph_toolkit/core/` と `src/nymph_toolkit/contracts/` を同梱する。Contractsは必要な契約から追加する。配布パッケージの正式名称、ビルドツール、対応Python版、依存・テストツールは実装開始時に記録する。

検証手順案として、ビルドした配布物を新しい環境へインストールし、採用したCore・Contractsの公開importとダミー実行を確認する。開発用ソースへの参照だけで成功していないことを確認する。具体的なコマンドはツール採用・実装後に掲載し、結果をacceptanceの形式で残す。

Subsystem・Adapterは必要に応じて同じリポジトリ内で別配布にする。分割時は対象の `pyproject.toml`、ソース・テストを配置する案とし、依存宣言、Core・Contractsの対応バージョン、公開import名、ビルド・インストール・組合せ検証の手順を後続ADRへ記録する。配置例は[architecture.md](architecture.md)を参照する。

## ライセンスの適用と配布確認

R8・[ADR 0011](adr/0011-apache-2.0-license.md)により、自作コード・Contracts・設計文書へApache-2.0を適用する。ルートの[LICENSE](../LICENSE)を維持し、実装開始時に採用するビルドツールに合わせてライセンス識別子 `Apache-2.0` とライセンスファイルの収録を配布設定へ記載する。

ソースファイルへライセンスを表示する場合は、ファイル形式に応じたコメントで `SPDX-License-Identifier: Apache-2.0` を記す方法を用いる。著作権表示を付す場合は実際の権利者・年を記載し、第三者の権利表示やライセンスを上書きしない。[Apache公式の適用方法](https://www.apache.org/foundation/license-faq.html)

ビルドした配布物を確認し、LICENSEと必要な帰属表示が含まれることを検証する。分割した自作Subsystem・Adapterも各配布物で同じ確認を行う。第三者成果物の同梱時は、その許諾条件と必要なNOTICE等を確認する。具体的なビルド・検証コマンドは実装後に追加する。

## Git未初期化からの準備

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

## 対象確認と初回コミット

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

## 日常の作業案

設計判断・文書更新・実装を目的が分かる単位でコミットする。関連するADR・実装・受入条件は同じ作業で整合させる。変更が複数に分かれる場合は作業ブランチを使用する案とする。

```powershell
git status --short --branch
git switch -c docs/refine-core-design
# ファイル編集後、対象パスを指定してgit addする
git diff --cached --check
git diff --cached
```

実装開始後は、本書に環境構築、テスト、ダミー受入シナリオの実行コマンドを追加する。新しい作業環境で再現し、OS・Python版・依存版と結果をacceptanceの記録形式で残す。

## 文書更新時の確認

ローカルリンク先の存在、ADRの状態と根拠、ロードマップと受入IDの対応、READMEの実装状況を確認する。単一配布用引継ぎ書はDocs索引に示した順序・変換方法で再作成し、収録元の本文と照合する。将来の配置予定はarchitectureのツリーに記載し、リンクは実在するファイルへ向ける。

公開準備と公開後の状態は[release.md](release.md)で確認する。
