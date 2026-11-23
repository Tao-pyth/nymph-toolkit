# 顧客向け契約・利用ガイドの検証記録

## R36の主要Docs化（v1.3候補）

2026年11月23日、親#13・子#124/#125、ADR 0030で現在の原稿と必須同期/生成を更新した。25ページ・図14点にCoreの6契約とMemory/Document/Cognitionを収録し、公開v1.2と候補v1.3を区別する。

- Windows / Node 24.22.3 / pnpm 11.25.0 / EdgeでA4 PDF・HTML・原稿コピー・生成JSONを生成。25ページ・SVG図14点、全ページの本文とタイトル、A4寸法、配置、ハッシュの検査が成功した。CJKフォントが等価な部首文字で抽出される場合はNFKCで比較する。
- PDF全25ページをPNG化して目視し、表・図・コード・日本語・フッターを確認した。密なページ10・15・17・22も拡大して確認。保存HTMLはHTTP/HTTPSを遮断しても25ページ・図14点を表示し、外部要求0・スクリプト0・実行エラー0だった。
- 同期対象119ファイル。原稿はCore/API/共通接続契約、Memory・Document・Cognitionの各ガイドと実装を照合した。原稿/公開状態と既知課題#94の説明を更新し、採用済みと将来機能を区別した。
- 同期検査の回帰7件を追加。実装の追加/変更/削除、ADR変更、版/公開状態、古い表紙、改変した生成物・原稿、別コミットの配布物、日本語正規化を確認した。証跡の更新で本文レビューを代替しない。
- Windows / CPython 3.15.2、警告をエラーとする全385テストが158.276秒で成功。製品src・公開契約・pyprojectは今回変更していない。
- 78収録元の引継ぎ書、78 Markdown・1,370ローカルリンク・UTF-8/LF・LICENSE、Core 15/Contracts 98、v1契約基準、64項目/7群/299テスト参照を照合した。これらの件数は今回のローカル確認時点。

生成物はcleanな最終コミットで再生成する。最終SHA、Linux ChromiumでのCustomer Docs CIと製品8環境CI、通常wheel/sdistの結果、artifact取得の確認は[#125](https://github.com/Tao-pyth/nymph-toolkit/issues/125)と[PR #123](https://github.com/Tao-pyth/nymph-toolkit/pull/123)へ記録する。CIの自動検査は意味・可読性の人手確認を完全には代替しない。旧版の公開済み添付は変更しない。

以下はR27の旧v0.9版の記録であり、現在の未実装・未修正の一覧ではない。

## R27の初版記録（履歴）

確認日：2026年11月22日。対象は[customer-guide.md](../customer-guide.md)と任意のPDF生成ツール。親[#90](https://github.com/Tao-pyth/nymph-toolkit/issues/90)、文書子[#95](https://github.com/Tao-pyth/nymph-toolkit/issues/95)、生成・同期子[#96](https://github.com/Tao-pyth/nymph-toolkit/issues/96)で追跡する。成果は[PR #93](https://github.com/Tao-pyth/nymph-toolkit/pull/93)に含める。

## 対象と根拠

説明対象は公開v0.9.0。導入担当者と開発担当者の両方を読者とするR27に対応した。顧客資料の「契約」は入力・結果・状態・失敗・責任分界の意味であり、保証や新しい製品仕様を採用するものではない。

| 本文の対象 | 照合元 |
|---|---|
| 全体像・配置・起動停止 | [Architecture](../architecture.md)、[Runtime](../runtime.md)、[Hybrid](../hybrid.md)、Runtime／ModuleGroup／HybridGroup実装 |
| 登録・宣言・候補選択・固定接続 | [Registry](../registry.md)、[Connections](../connections.md)、ADR 0016・0019、Registry／Connections実装 |
| 呼出し・ストリーム・期限・結果保持 | [Core API](../core-api.md)、[Hybrid](../hybrid.md)、ADR 0022〜0024、ハイブリッド通信・転送実装 |
| 活動の計時・変更・中断再開・終了 | [TaskManager](../task-manager.md)、ADR 0020〜0023、TaskManager／HybridTaskManager実装 |
| 障害・保存・再起動 | [Connections](../connections.md)、[Core API](../core-api.md)、FileStore実装、[A08](v0.8.md)・[A09](v0.9.md)記録 |
| 設定値・公開名・型 | [API一覧](../api-reference.md)、実装の型・既定値・検証処理 |
| 通常導入・6実行例・適用限界 | [導入ガイド](../getting-started.md)、[実行例](../tutorials.md)、[既存の実行確認](docs-onboarding.md)、公開Release・既知課題#94 |

設計判断・ADR・採用64項目・製品API・ソース・既存実行例・版番号は変更しない。R27は資料作成と読者の確認を記録するもので、新規ADRは作成しない。文書生成用のNode依存は別ディレクトリへ分離する。

## 配布物の確認

- Windows上のNode.js 24.22.3、pnpm 11.25.0、ローカルMicrosoft Edgeで生成。依存版はpackage.jsonとlockに固定。実際のブラウザー版と本文SHA-256は出力JSONに記録する。
- 同じMarkdownからA4のPDF20ページ、SVG図10点を含むHTMLを生成。Mermaid描画・横幅・フッターとの余白の自動検査を通過した。
- pypdfで実ページ数20と各ページの本文抽出を確認し、pypdfium2で全20ページをPNG化して表示を確認した。表・コード・図がページ外へはみ出さず、日本語と矢印を読めることを確認した。
- 保存したHTMLには外部スクリプトがなく、HTTP要求を遮断したブラウザーでも10点のSVG図を表示できた。参照文書へのリンクはGitHub上の生成時参照先へ変換する。
- 本文の最小Runtimeコードを公開v0.9.0 wheelの独立venvで実行。`completed`を出力し、終了コード0、標準エラーなし。元の6実行例の確認は[先行記録](docs-onboarding.md)にある。
- 引継ぎ書は62収録元と一致。62 Markdown・1,129ローカルリンク・UTF-8/LF・LICENSEの検査、Core 14件／Contracts 92件のAPI一覧、採用64項目・既存受入7群・製品293テスト参照の照合が成功した。動作試験の代わりには扱わず、最終コミットとCIの結果を#95・#96へ記録する。

PDF・HTML・JSONは`output/pdf/`に生成し、Gitには含めない。再生成方法は[作成手順](../customer-guide-authoring.md)を参照。原稿の版とPDFの参照コミットが一致するよう、コミット後に最終配布物を生成する。公開済みv0.9.0 Releaseや添付の差替えは行わない。

## 限界と残課題

PDF生成は今回のWindows・Edge・日本語フォント環境で確認した。Linuxや別のフォント／ブラウザーで同じページ配置になることは未確認。HTMLは固定A4幅の配布用レイアウトで、スマートフォン用の専用レイアウトではない。

図は責任・代表的な経路の説明であり、全ての拒否条件や状態遷移を網羅しない。省略範囲を本文・図の説明へ記載し、正確な契約への参照を設けた。公開APIのv1.0以降の互換性や本番Subsystemの完成を保証しない。

Windows／Python 3.15の終了時通信切断・後処理未確認は[#94](https://github.com/Tao-pyth/nymph-toolkit/issues/94)で調査を継続する。先行Docs CIで一度観測され、再実行と手元10反復では再現しなかったが原因は未確定。今回の文書で修正済みと扱わず、製品の試験条件も変更しない。30分負荷試験はv0.8の特定コミットの記録であり、本資料や全環境の新しい測定とは扱わない。
