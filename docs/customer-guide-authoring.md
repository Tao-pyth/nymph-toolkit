# 顧客向け契約・利用ガイドの更新と配布

## 編集元と対象版

[customer-guide.md](customer-guide.md)を本文と図の編集元とする。対象は公開済みv0.9.0、読者は導入担当者と機能を接続する開発担当者の両方。現在の契約を説明する資料であり、v1.0の正式な契約区分や互換性を新たに採用する文書ではない。

MarkdownはGitHubで図を含めて読める。配布用PDFとHTMLは同じ本文から生成する。`<!-- pagebreak -->`が印刷時のページ境界、`mermaid`コードブロックが図の編集元である。説明・表・図を同時に更新し、正確な署名は[API一覧](api-reference.md)、意味は[Core API](core-api.md)、採用状態は[ADR索引](adr/README.md)に照合する。

今回の文書は親[#90](https://github.com/Tao-pyth/nymph-toolkit/issues/90)・子[#95](https://github.com/Tao-pyth/nymph-toolkit/issues/95)、生成と同期は子[#96](https://github.com/Tao-pyth/nymph-toolkit/issues/96)で扱う。全てv1.0.0マイルストーンに属する準備作業。生成ツール・設定の変更も[Issue運用](issue-workflow.md)の対象になる。

## 任意の文書生成環境

生成ツールは[tools/customer-docs](../tools/customer-docs/package.json)へ分離している。Node.js・pnpm・ブラウザーは文書作成時だけに使い、NTKのPython実行時依存には含めない。確認環境はWindows、Node.js 24.22.3、pnpm 11.25.0、Microsoft Edge。依存版はpackage.jsonとpnpm-lock.yamlに固定する。

リポジトリ直下で、Node.js 24系とpnpm 11.25.0を利用できる状態にして実行する。

```powershell
node --version
pnpm --version
pnpm --dir tools/customer-docs install --frozen-lockfile
node tools/customer-docs/build.mjs --browser 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
```

`--browser`には実際のChromium系ブラウザー実行ファイルを指定する。別の場所にインストールした場合は変更する。Playwright管理のChromiumを使う場合は、次のように取得してから生成する。

```powershell
pnpm --dir tools/customer-docs exec playwright install chromium
node tools/customer-docs/build.mjs
```

日本語フォントが必要で、CSSはYu Gothic、Meiryo、Noto Sans CJK JPの順に参照する。フォント・ブラウザーが異なると改行やページ内の配置が変わるため、環境変更時も全ページを確認する。上記のPlaywright管理ブラウザーおよびLinuxでの生成は今回の実測対象外。

## 生成物と参照先

生成先は`output/pdf/`。以下の3点を出力する。生成物とnode_modulesはGit対象外とする。

| ファイル | 内容 |
|---|---|
| NTK-Core-v0.9.0-Customer-Guide-ja.pdf | A4の日本語配布資料。本文・図・リンク・ページ番号を収録 |
| NTK-Core-v0.9.0-Customer-Guide-ja.html | CSSとSVG図を内包。外部スクリプトを必要としない閲覧用 |
| NTK-Core-v0.9.0-Customer-Guide-ja.json | MarkdownのSHA-256、参照コミット、ブラウザー版、ページ・図の数、配置検査結果 |

文書内の相対リンクは、生成時の`git rev-parse HEAD`に対するGitHubのファイルURLへ変換する。変更をコミットして、そのコミットをGitHubへ反映してから配布版を作る。レビュー中に別の参照先を使う場合は次のように指定できる。

```powershell
node tools/customer-docs/build.mjs --browser 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' --ref codex/91-docs-onboarding
```

配布時は移動するブランチよりコミットSHAを使う。JSONに記録した参照先と本文の版を確認する。HTMLの図・本文はオフラインでも表示できるが、参照先のGitHubを開く操作にはネット接続が必要。PDFの作成日時やSVGの識別子等が変わるため、生成物のバイト単位の一致は保証しない。本文SHAと生成条件で版を識別する。

## 同期と検証

1. 本文・図・表を、現行の個別Docs・公開API・ADR・実装と照合する。過去の実装段階と現在の制約を区別する。
2. 生成ツールを実行する。Mermaidの描画数、JavaScriptエラー、本文の横方向のはみ出し、フッターとの余白を自動確認し、異常時は失敗する。
3. PDFを開き、全ページを画像にして確認する。日本語の欠け、図の線・文字の重なり、小さすぎるラベル、表の分割、空白ページ、ページ番号を確認する。HTMLの配置検査だけで完了しない。
4. PDFの実ページ数とJSONのページ数、抽出できる本文、参照リンクを確認する。今回の成果は20ページ・図10点。PDFビューアーや任意のPDF描画ツールで確認できる。今回の描画・抽出にはpypdfium2・pypdfを使用したが、必須の生成依存には追加していない。
5. 実行例を変更した場合は、対象版を通常導入した独立環境で動かし、結果と終了を確認する。現在の本文にある最小Runtime例は公開v0.9.0 wheelで確認している。
6. 引継ぎ書を再生成し、次の検査を実行する。結果・環境・未確認範囲を[検証記録](validation/customer-guide.md)と子Issueへ残す。

```powershell
python tools/build_handoff.py
python tools/build_handoff.py --check
python tools/check_docs.py
python tools/check_api.py
python tools/check_completion.py
git diff --check
```

引継ぎ書には本文・本書・検証記録を全文収録する。PDFの改ページ指示も収録されるが、引継ぎ書そのものを本ツールでPDF化するわけではない。既存CIではDocs・API・証拠参照の検査を継続し、ブラウザーを使うPDF生成は任意の作業として分ける。公開済みタグ・Release添付は更新せず、配布資料の新しい版は別の成果物として扱う。
