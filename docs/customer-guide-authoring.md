# 顧客向け主要Docsの更新・同期・配布

R36・[ADR 0030](adr/0030-customer-docs-as-primary.md)により、[customer-guide.md](customer-guide.md)・PDF・HTMLは主要Docsである。対象ブランチ/コミットの実装と同時に更新する。現在は対象v1.8.0の開発候補と公開v1.2.0を区別して説明する。読者は導入担当者・開発担当者の両方。

## 正本と同期対象

Markdownを本文・表・Mermaid図の正本とし、`<!-- pagebreak -->`でA4のページを区切る。PDF/HTMLを直接編集しない。対象版・公開状態・公開版・確認日は[確認証跡](customer-guide.sources.json)と表紙へ記録する。生成側は証跡から版と日付を読み、pyprojectの対象版と一致させる。

check_customer_docs.pyはpyproject、全src/examplesのPython、ルートMarkdown、Docs（validationと生成引継ぎ書を除く）、contracts-v1.jsonをハッシュで照合する。追加・削除も検出する。検証記録と生成引継ぎ書は循環更新を避けて除外し、通常のcheck_docsで検査する。機能/文書の差分を本文・図へ反映、または説明に変更不要と判断した理由を記録してから証跡を更新する。CIは自動承認・自動更新しない。

## 更新手順

1. 対象マイルストーンと親子Issueを確認する。初回の主要Docs化は親#13の#124/#125。v1.4の更新・検証は親#14・子#130へコード変更前に範囲を登録した。
2. 主要Docs・公開API・ADR・実装と本文/図を照合する。未公開機能を公開済みと表示しない。版が変わる場合は証跡と表紙も更新する。
3. 内容レビューの理由を記録して証跡を更新し、引継ぎ書を再生成する。
4. 同じMarkdownからPDF/HTMLを生成し、全文抽出・ページ数・ハッシュ・配置を検査する。PDF全ページのPNGを目視し、文字欠け・重なり・図の可読性・余白を確認する。
5. 結果をIssue/PRへ記録しコミットする。配布用はcleanな同一コミットで再生成・検査する。Python製品CIとCustomer Docs CIの成功後にレビュー/公開判定へ進む。

```powershell
python tools/check_customer_docs.py --write --review-note '変更内容を本文・図・公開状態と照合した理由'
python tools/build_handoff.py
python tools/check_docs.py
python tools/check_api.py
python tools/check_contracts.py
python tools/check_completion.py
```

証跡だけの更新は内容レビューの代わりにならない。検査は変更の見落とし・版の不一致・古い生成物を止める仕組みであり、説明の意味が正しいかはレビューする。

## 生成環境とコマンド

Node.js 24、pnpm 11.25.0、Playwright管理Chromium（または実在するChromium系ブラウザー）、日本語フォントを使う。package.json/lockで依存を固定する。PDF検査は専用requirementsを使い、製品の実行時依存に追加しない。

```powershell
pnpm --dir tools/customer-docs install --frozen-lockfile
pnpm --dir tools/customer-docs exec playwright install chromium
python -m pip install -r tools/customer-docs/requirements.txt
node tools/customer-docs/build.mjs
python tools/check_customer_docs.py --artifacts output/pdf --render-dir output/pdf/pages
```

別のPythonを使う場合は生成に`--python .venv/Scripts/python.exe`等を指定する。WindowsのEdgeを使う場合は`--browser 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'`を追加できる。Linux CIはPlaywrightの`install --with-deps chromium`と`fonts-noto-cjk`を使う。ブラウザー/フォント変更時も全ページを確認する。

配布前は`python tools/check_customer_docs.py --artifacts output/pdf --require-clean`で確認する。未コミットのpreviewは配布対象外。`--ref`は現在のcheckoutへ解決できる参照に限り、異なるコミットのリンクを付けない。

## 成果物と取得先

出力先は`output/pdf/`。ファイル名は`NTK-v<対象版>-Customer-Guide-ja`に`.md`・`.pdf`・`.html`・`.json`を付ける。原稿とPDF/HTML、JSONの4点を一式として扱う。JSONには原稿・確認証跡・生成入力・成果物のSHA-256、参照コミット、dirty状態、ブラウザー、ページ/図数・配置検査を記録する。

PDFはA4、HTMLはCSSと描画済みSVGを内包する。本文と図の閲覧はオフラインで可能だが、GitHubの参照リンクはネット接続を使う。PDFメタデータやSVG ID等によりバイト単位の再現を約束せず、内容とハッシュ・生成条件で識別する。

[Core checks workflow](https://github.com/Tao-pyth/nymph-toolkit/actions/workflows/ci.yml)の**Customer Docs**を全push/PRで実行し、成功したrunの`customer-docs-<SHA>` artifactから一式とページPNGを取得する。対象SHAを確認して取得する。CI artifactの保持は90日で、期限切れ後は同コミットから再生成する。正式公開時は同タグから生成・検証した一式をReleaseへ保存する。公開済みタグ/添付は置換しない。

Git管理対象は原稿・証跡・生成/検査コードで、重複する生成PDF/HTMLとnode_modulesは対象外。引継ぎ書には原稿・本手順・ADR・検証記録を収録する。検証結果は[顧客資料の検証記録](validation/customer-guide.md)へ残す。

失敗したCIの生成物は調査用の`customer-docs-diagnostics-<SHA>`へ7日間だけ保存する。これは配布用の検証合格を意味しない。PDFのページ数/寸法はpypdf、原文タイトル/本文の照合とPNG化はPDFiumを用いる。ブラウザーとCJKフォントによる抽出文字の差を、タイトル検査の省略で回避しない。

CI環境の参考：[PlaywrightのCI手順](https://playwright.dev/docs/ci)、[GitHub artifact保存](https://github.com/actions/upload-artifact)。
