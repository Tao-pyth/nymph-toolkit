# 公開準備とリリース手順

GitHub公開をV0.1、Core機能完成をV0.9とする目標は確定している。2026年11月20日に初期資料・開発基盤のv0.1.0と、最小Runtimeのv0.2.0を公開した。v0.1.0欄は初回公開時の記録として保持する。

2026年11月23日の点検時点では、最新公開版は[v1.2.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.2.0)。公開後確認は[#117](https://github.com/Tao-pyth/nymph-toolkit/issues/117)で完了している。v1.3.0は[PR #123](https://github.com/Tao-pyth/nymph-toolkit/pull/123)のレビュー用候補で、未マージ・未公開。以下の過去版の手順や当時の未完了条件を、現在の未実施事項とは読み替えない。

## v0.9.0の公開手順と記録

R24・ADR 0025に基づき#82〜#85・#87でCore完成監査と配布候補を整備した。R25でユーザーがPR #86のレビュー後のマージ・公開と、A09-04完了後の親#9・マイルストーン終了を指示した。公開#88、レビュー修正#89を各変更前に追加し、公開対象を0.9.0とする。A09-01〜03の結果、API・64項目の証拠、全8環境CIは[v0.9検証記録](validation/v0.9.md)へ記録する。タグ・Releaseの作成と実際の取得物の照合を行う前は、A09-04を合格としない。

公開前レビューで子の終了競合を修正し、全300テストを対象とする。公開工程では対応子Issueを先に登録し、レビュー済みPRのマージ後コミット・CIを確認する。同じコミットのwheel・sdist・単一引継ぎ書・SHA256SUMSを新しいv0.9.0タグとReleaseへ添付し、認証なしでタグ・4添付を取得してSHA・API・全テスト・6実行例・短負荷・再ビルド・文書を再確認する。結果を[公開課題 #88](https://github.com/Tao-pyth/nymph-toolkit/issues/88)と[v0.9.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.9.0)へ記録した後に親#9とマイルストーンを完了する。公開済みv0.1.0〜v0.8.0は差し替えない。

## v0.8.0の公開手順と記録

R22の統合・障害・負荷検証は親#8の子#72〜#78・#80、[PR #79](https://github.com/Tao-pyth/nymph-toolkit/pull/79)、[ADR 0024](adr/0024-v0.8-integration-validation.md)、[A08検証記録](validation/v0.8.md)で追跡した。R23でユーザーがレビュー後のマージ・v0.8.0公開を明示指示した。公開子Issue [#81](https://github.com/Tao-pyth/nymph-toolkit/issues/81)を先に登録し、公開対象を配布メタデータ0.8.0とする。

1. 公開前レビュー・関連42テストの再実行結果、288テスト・6実行例・通常配布・A08証拠・文書同期を確認する。製品コードに追加修正が必要な問題は見つからなかった。
2. マージ対象headのWindows/Linux × CPython3.12〜3.15の全8環境CIを確認し、SHAを指定してPR #79をマージする。マージコミットのツリーが検証済みheadと同一であることと、そのコミットのCI成功を確認する。
3. マージコミットからwheel・sdist・単一引継ぎ書・SHA256SUMSを作り、新しい`v0.8.0`タグと[Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.8.0)へ4件を添付して公開する。
4. 認証情報を使わずにタグをcloneし、添付を取得してチェックサム・タグ内文書・製品コードを照合する。作業ツリー外の新規環境へwheelを通常インストールし、全テスト・6実行例・短い負荷・sdist同一wheel再ビルド・Docsを再現する。
5. 最終SHA・CI・レビュー・公開後の匿名取得結果を#81とReleaseへ記録してから、公開課題・親#8・マイルストーンv0.8.0を完了する。

30分測定は`cb0cf61`、後続#80は専用回帰・通常配布・短い負荷・全環境CIでの再検証であり、最終コード全体の30分測定とは表現しない。R22時点で公開を含めなかった判断は履歴として保持し、R23を今回の公開根拠とする。公開済みv0.1.0〜v0.7.0のタグ・Release・添付は差し替えない。A09のCore完成判定は別段階である。

## v0.7.0の公開手順と記録

R20の実装は[PR #69](https://github.com/Tao-pyth/nymph-toolkit/pull/69)、親#7、子#61〜#68で追跡した。R21でユーザーがレビュー後のマージ・v0.7.0公開を明示指示した。修正[#70](https://github.com/Tao-pyth/nymph-toolkit/issues/70)・公開[#71](https://github.com/Tao-pyth/nymph-toolkit/issues/71)を着手前に登録し、配布メタデータ0.7.0、[A07検証記録](validation/v0.7.md)、[操作契約](hybrid.md)に従う。

1. レビュー指摘を解消し、267テスト・6実行例・通常wheel・sdist再ビルド・文書同期と、PR最終headのWindows/Linux × Python3.12〜3.15全8環境CIを確認する。
2. 確認したhead SHAを指定してPR #69をマージする。マージコミットそのものの全8環境CIが成功したことを確認する。
3. 同じコミットからwheel・sdist・単一引継ぎ書・SHA256SUMSを作成する。新しい`v0.7.0`タグを付け、[Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.7.0)へ4件を添付して公開する。
4. 認証情報を使わずにタグをcloneし、4添付をdownload・ハッシュ照合する。新規venvへの通常インストールで全試験・6実行例・Docs・sdist再ビルドを確認し、タグ本文と添付引継ぎ書の一致も確認する。
5. 最終SHA・CI・レビュー結果・チェックサム・匿名取得の結果をReleaseと#71へ記録し、対応子Issue・親#7・マイルストーンv0.7.0を完了する。

R20時点で新規Releaseを含めなかった判断は履歴として保持する。今回の公開根拠はR21である。公開済みv0.1.0〜v0.6.0のタグ・Release・添付は変更しない。v0.8のA08・v0.9のA09の完了は含めない。

## v0.6.0の公開手順と記録

親Issue #6、設計#52、実装#53〜#57、受入#58、公開[#59](https://github.com/Tao-pyth/nymph-toolkit/issues/59)で追跡する。採用範囲の実装・A06・全8環境のCIを確認した。公開対象版は0.6.0で、[ADR 0021](adr/0021-v0.6-activity-changes.md)と[A06検証記録](validation/v0.6.md)に従う。

1. 予定変更・期間通知・優先度・中断再開の全採用範囲、既存回帰、5実行例、通常インストール・sdist再ビルド、文書同期を確認する。
2. 公開するコミットそのもののWindows/Linux × Python3.12〜3.15の全8環境が成功したことを確認する。
3. 同じコミットへ`v0.6.0`タグを付け、wheel・sdist・単一引継ぎ書・SHA256SUMSを添付する。公開済みv0.1.0〜v0.5.0のタグ・本文・添付を変更しない。
4. 認証情報を使わずにタグをcloneし、添付をdownload・照合する。新規環境へwheelを通常インストールし、公開import・全テスト・5実行例・Docsを確認する。
5. 最終SHA・CI・チェックサム・匿名取得の結果をReleaseと#59へ記録してから、親Issueとマイルストーンを完了する。

## v0.5.0の公開手順と記録

R17によりTaskManager基本機能へ着手した。公開課題は[#51](https://github.com/Tao-pyth/nymph-toolkit/issues/51)、先行する設計・実装・受入は親Issue #5・子Issue #45〜#50で管理する。採用範囲の実装・A05・配布検証を確認した。公開対象版は0.5.0。最終コミットのCI確認後、タグ・Releaseを作成する。公開後の結果は[Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.5.0)と#51へ記録する。

公開前に[ADR 0020](adr/0020-v0.5-task-manager.md)で必要な判断を確定し、A05の要件ごとの証拠、採用したAPI、未対応範囲、実行例、ソース・wheel・sdistの検証結果、最終コミットのCIを確認する。予定時間到達時の通知・継続とNymphの意思決定の境界を受入に含める。再起動時の履歴提供とNymphによる再登録、過去時刻の返却、安全な終了も確認する。公開結果は#51へ記録し、既存v0.1.0〜v0.4.0のタグ・添付を保持する。

受入後は同じ確定コミットからwheel・sdist・単一配布用引継ぎ書・チェックサムを用意し、タグとReleaseの対応を記録する。認証なしの取得と新しい環境からの実行・テストを確認してから公開課題を完了する。既存v0.1.0〜v0.4.0のタグ・Release本文・添付を差し替えない。

## v0.4.0の公開手順と記録

R16・ADR 0019のConnections・FileStore・共有Contractsとダミー、A04受入資料をv0.4.0として公開する。通常のバッファ上限なし・受付継続と、保存失敗時の受付停止・救命を区別する。

| 項目 | 内容 |
|---|---|
| 公開先 | [GitHub Release v0.4.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.4.0)。PyPI公開は対象外 |
| 配布物 | `nymph_toolkit-0.4.0-py3-none-any.whl`、`nymph_toolkit-0.4.0.tar.gz`、単一引継ぎ書、SHA256SUMS |
| 受入 | [A04記録](validation/v0.4.md)。129テスト、3実行例、Windows/Linux・CPython 3.12〜3.15、通常インストール・sdist再ビルド、区間別性能測定 |
| 公開前の条件 | 最終コミットで文書・ビルド・配布チェックと8環境のCIが成功。コード・文書・配布物・タグが同じコミットに対応 |
| 公開後の条件 | 認証なしのタグclone・添付4件の取得・ハッシュ照合。取得したwheelを新規環境へ導入し、3実行例と129テストを再現 |
| 実際の結果 | 最終SHA・CI・各配布物のハッシュ・公開後検証をReleaseと[子Issue #44](https://github.com/Tao-pyth/nymph-toolkit/issues/44)に記録 |

実装受入と公開確認を分け、公開後検証まで終えてから親Issue #4・マイルストーンv0.4.0を完了する。公開済みv0.1.0・v0.2.0・v0.3.0のタグ、Release本文、添付のID・サイズ・ハッシュが作業前の記録と一致することを確認する。受入記録にある同一プロセス・協調的中断・バッファ増加と突然の終了時の限界をReleaseにも掲載する。

## v0.3.0の公開手順と記録

R13の実施指示に基づき、ADR 0016のRegistry・ModuleGroup・Contractsとダミー、A03受入資料をv0.3.0として公開する。R12・ADR 0015の直接通信の採用記録も含めるが、通信実装は含めない。

| 項目 | 内容 |
|---|---|
| 公開先 | [GitHub Release v0.3.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.3.0)。PyPI公開は対象外 |
| 配布物 | `nymph_toolkit-0.3.0-py3-none-any.whl`、`nymph_toolkit-0.3.0.tar.gz`、単一引継ぎ書、SHA256SUMS |
| 受入 | [A03記録](validation/v0.3.md)。63テスト、両実行例、Windows/Linux・CPython 3.12〜3.15、通常インストール・sdist再ビルド |
| 公開前の条件 | 最終コミットで文書・テスト・ビルド・配布チェックと8構成のCIが成功。コード・文書・配布物・タグが同じコミットに対応 |
| 公開後の条件 | 認証なしのタグclone・添付取得・ハッシュ照合、取得したwheelの新規環境への導入、両実行例と63テストの再現 |
| 実際の結果 | 対象SHA・CI・配布物ハッシュ・公開後の検証をReleaseと[子Issue #33](https://github.com/Tao-pyth/nymph-toolkit/issues/33)へ記録 |

公開手順は、確認済みmainへの `v0.3.0` タグ付与、Releaseへの同じコミットの配布物添付、公開後確認の順に行う。確認後に親Issue #3・マイルストーンv0.3.0を完了とする。v0.1.0・v0.2.0のタグ・Release添付は保持する。

## v0.2.0の公開記録

| 項目 | 内容 |
|---|---|
| 対象 | ADR 0014の最小RuntimeとContracts、ダミー、テスト、開発・受入資料 |
| Python・依存 | CPython 3.12以上、実行時の外部依存なし |
| 公開先 | [GitHub Release v0.2.0](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.2.0)。PyPIへの公開は行わない |
| 配布物 | `nymph_toolkit-0.2.0-py3-none-any.whl`、`nymph_toolkit-0.2.0.tar.gz`、単一引継ぎ書、SHA256SUMS |
| 受入 | [A02の結果](validation/v0.2.md)、Windows/LinuxとPython 3.12〜3.15のCI |
| 実際の公開結果 | 対象SHA・最終CI・公開後の取得確認・各配布物のハッシュはReleaseと子Issue #26へ記録 |

リリース対象コミットで `python tools/check_docs.py`、テスト、`python -m build`、`python tools/check_dist.py` を実行し、CIを確認する。同じコミットへ `v0.2.0` タグを付けてpushし、検証した配布物と同じタグの引継ぎ書をReleaseへ添付する。公開後は認証なしでタグ・添付を取得し、ハッシュ照合とwheelからのダミー・テスト実行を確認する。結果を記録して親Issue・マイルストーンを完了とする。

## v0.1.0の公開記録

| 項目 | 現在の状態 | 記録 |
|---|---|---|
| リポジトリ名 | 確定 | `nymph-toolkit` |
| 公開先アカウント | 採用済み（R9） | 個人アカウント `Tao-pyth`。GitHub接続でも確認済み |
| 公開範囲 | publicを確認済み | R9に従い最初からpublicで公開 |
| ライセンス | 採用済み（R8、2026年11月20日） | 自作コード・Contracts・設計文書へApache-2.0を適用。[LICENSE](../LICENSE)と[ADR 0011](adr/0011-apache-2.0-license.md)を配置済み |
| 公開対象 | 資料中心で確定（R9） | README、CONTRIBUTING、Docs・ADR、CHANGELOG、Git設定、LICENSE。Core未実装を明記 |
| 公開URL・remote | 設定済み | [Tao-pyth/nymph-toolkit](https://github.com/Tao-pyth/nymph-toolkit)、`origin` は `https://github.com/Tao-pyth/nymph-toolkit.git` |
| V0.1タグ・公開日 | 初回公開の対象 | `v0.1.0`、2026年11月20日。対象コミットSHAと公開後の検証結果は[GitHub Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v0.1.0)に記録 |

公開先の接続確認と、公開先の選定はそれぞれ記録する。ライセンスはR8でApache-2.0、公開先と公開範囲はR9で `Tao-pyth/nymph-toolkit` のpublic公開へ確定した。判断記録は[ADR 0012](adr/0012-v0.1-publication.md)。公開・タグ・Releaseの完了は実際の結果を確認して記録する。

## 公開前チェックリスト

- [x] Apache-2.0の採用・適用範囲を記録し、公式本文のLICENSEを追加する。
- [x] 公開先アカウント・公開範囲の判断欄を埋める。
- [x] 簡潔な参加方針をCONTRIBUTINGに記載する。
- [x] 公開する成果物にLICENSEを含め、第三者成果物がある場合は元の許諾・帰属表示・NOTICE等の要件を確認する。
- [x] READMEにその時点の実装状況を記載する。
- [x] Docs・ADRの確定事項、未決事項、根拠を確認する。
- [x] 単一配布用引継ぎ書を個別Docsと同期する。
- [x] ステージした一覧と差分を読み、公開対象を確認する。
- [x] 初回コミットとローカルGitの作成者設定を確認する。
- [x] 文書リンク、文字コード、改行、受入IDの対応を確認する。
- [x] README・CHANGELOG・本書の公開時の更新を準備する。

ローカルでの公開前確認は2026年11月20日に実施した。文書リンク、引継ぎ書と収録元の一致、LICENSE原文、公開対象とGit履歴を確認した。初回push後にpublic設定とローカル・remoteのコミット一致を確認した。以下はタグ・Release作成と公開後の取得確認を含む手順である。最終結果は上記Releaseに記録する。

## ライセンスと配布内容の確認

自作コード（Core、Contracts、将来の自作Subsystem・Adapter）と設計文書（README、Docs・ADR、引継ぎ書）にApache-2.0を適用する。第三者のコード・依存ライブラリ・モデル・文書・音声等は各権利者の条件を維持し、会話・記憶・人格などの個体データの利用条件も別途扱う。

LICENSEは[Apache公式テキスト](https://www.apache.org/licenses/LICENSE-2.0.txt)を変更せず収録する。付録の著作権表示の記入例は公式本文の一部として保持する。実際の成果物の著作権・帰属表示は正確な権利関係に基づいて別途記載し、第三者の表示を保持する。

単一配布用引継ぎ書にはLICENSE原文を収録する。将来のPython配布物や分割したパッケージでも、各配布物にLICENSEと必要な表示が含まれることを確認する。NOTICEは収録物の表示要件に応じて整備する。採用状態の記録は[ADR 0011](adr/0011-apache-2.0-license.md)を参照する。

## GitHubへの接続とpush

GitHubで、決定済みの所有者の配下に `nymph-toolkit` を作成する。ローカル履歴から開始する場合はREADME・LICENSE・gitignoreの自動作成を選ばず、空のリポジトリを用意する。既存リポジトリがある場合は内容と履歴を確認してから接続する。

以下は採用した公開先に対するPowerShellの例。認証には設定済みのGit認証手段を使う。

```powershell
git remote -v
git remote add origin https://github.com/Tao-pyth/nymph-toolkit.git
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
git add -- LICENSE README.md CONTRIBUTING.md CHANGELOG.md docs
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

## 配布パッケージとリリースの対応

R10以降は[Issue運用](issue-workflow.md)に従い、対象マイルストーン・親Issue・子Issueから変更と検証結果を追跡する。リリース前に採用範囲の受入結果と残課題の扱いを確認する。コード変更は子Issue登録後に行い、Issueやマイルストーンを閉じただけで自動的に公開・タグ付けは行わない。公開済みv0.1.0のタグ・Release添付は保持し、その後の資料更新は未リリースの変更として記録する。

R6・[ADR 0009](adr/0009-package-distribution.md)で、単一リポジトリと、Core・Contractsを一つの配布パッケージから始める方針を採用した。Subsystem・Adapterは必要に応じて同じリポジトリ内で分割する。GitHub公開のv0.1.0は資料と開発基盤を中心とする節目で、Python配布物の公開を必須条件に加えない。

配布パッケージの正式名称、配布先、ビルド手段は別途決める。将来分割する際は、対象とCore・Contractsの対応バージョン、各配布物のバージョンを同期するか独立させるか、リポジトリのタグ・ロードマップの節目との対応を後続ADRへ記録する。これらの決定と検証結果を基に、そのリリースで公開する配布物を明示する。

## v1.x以降のリリース運用案

R5に基づく未確定の運用案をADR 0007に記録する。v1.0.0の接続契約整備という目標はADR 0006を参照する。

| 区分 | 主目的の案 |
|---|---|
| v1.0.0 | CoreとSubsystem・Adapterの接続契約確立 |
| 奇数マイナーバージョン | 新規Subsystemの実装 |
| 偶数マイナーバージョン | Subsystem間連携の見直し・強化、Adapterの実装・拡張 |
| パッチバージョン | 不具合修正、小規模改善、互換性を維持した個別修正 |

必要な補助実装や最低限の統合テストは各区分に含められる。偶数マイナーで必ず新しいAdapterを追加する必要はない。名称・実装順序・バージョンへの機能配分は暫定であり、変更理由と受入への影響を記録して調整する。

### 公開API互換性の判断

公開するAPIと互換性の境界をv1.0.0の契約設計で具体化する。Semantic Versioningでは、後方互換性のある修正をパッチ、公開APIへの後方互換性のある機能追加をマイナー、非互換な公開API変更をメジャーとして扱う。NTKでの適用範囲と採番は変更内容を確認して別途判断する。[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)

「小規模改善」という作業量だけでパッチと決めず、公開APIへの機能追加や互換性への影響を確認する。破壊的変更が必要になった場合は、影響、移行方法、Semantic Versioningとの整合性、採番とロードマップの調整を後続ADRへ記録する。奇数・偶数の予定だけを根拠に破壊的変更をマイナーへ割り当てない。

実際のリリース時には、その段階で採用した契約と受入結果、互換性判断、既知の制約をREADME・CHANGELOG・リリース記録へ反映する。

## v1.0.0候補と公開前の残確認

R29の開発指示では新規Releaseを作成しない。1.0.0候補は[ADR 0026](adr/0026-v1.0-core-connection-contracts.md)と[B00結果](validation/v1.0.md)に従い、移行資料・全テスト・7例・通常配布・8環境CI・引継ぎ書を照合する。レビュー後の公開指示で、対象コミットとCIを再確認し、タグ/Release・添付checksum・匿名取得による公開後確認を行う。その結果を親#10へ記録して親とマイルストーンの終了を判断する。公開済みv0.9.0は差し替えない。

## R30：v1.0.0の公開実施

R30でレビュー後のマージ・v1.0.0公開・公開後確認・課題終了が明示指示された。公開子[#104](https://github.com/Tao-pyth/nymph-toolkit/issues/104)で、最終head・マージ後8環境CI・タグ・wheel/sdist/引継ぎ書/SHA256SUMSを追跡する。匿名取得でchecksumを照合し、公開wheelを新規venvへ通常導入して版・import元・7例・契約基準を確認する。完了結果を#104とReleaseへ記録してから親#10とマイルストーンを閉じる。

## v1.1 Memoryの公開前条件

R31は実装・B01・配布候補・PRまでを扱う。公開時は[B01記録](validation/v1.1.md)の全6項目、最終SHAの8環境CI、Memoryを含む通常wheel/sdistと8例、同期済み引継ぎ書を確認する。公開用の子Issueを先行登録し、READMEの開発候補表記・導入手順を公開対象版に合わせ、タグ/Release・4添付・匿名取得・再起動例を照合してから親#11とマイルストーンを閉じる。公開済みv1.0以前のタグ/添付は差し替えない。

## R32：v1.1.0の公開実施

R32で公開までの進行が指示された。公開子[#110](https://github.com/Tao-pyth/nymph-toolkit/issues/110)でレビュー、最終head・マージ後・タグの8環境CI、4添付のchecksum、匿名取得・通常導入・8例とMemory再起動確認を記録する。最終結果を確認してから親#11とマイルストーンを閉じる。公開済みv1.0.0以前のタグ・Release添付を差し替えない。

## v1.2 Documentの公開前条件

R33は子#112〜#115による実装・B02・配布候補・PRまで。公開時は[B02記録](validation/v1.2.md)、最終SHAの8環境CI、Document/Memoryを含む通常wheel/sdistと9例、同期済み引継ぎ書を確認する。公開用の子Issueを先行登録し、導入/例ガイドを公開版へ更新してからタグ/Release・添付checksum・匿名取得・文書取込/Memory再起動を確認する。公開前に親#12/マイルストーンを閉じない。公開済みv1.1.0以前は差し替えない。

## R34：v1.2.0の公開実施

R34でレビュー後のマージ・公開・公開後確認・課題終了が指示された。公開子[#117](https://github.com/Tao-pyth/nymph-toolkit/issues/117)で最終head、マージ、タグの各8環境CIを確認する。wheel/sdist/引継ぎ書/SHA256SUMSの4添付を匿名取得し、checksum、公開タグとの一致、新規venvへの通常導入、9例、Memory/Document回帰を確認する。B02の結果と残る制約を記録し、完了後に子#112〜#115とレビュー修正#118・公開#117、親#12・マイルストーンを閉じる。公開済みv1.1.0以前のタグ・添付は変更しない。

## v1.3 Cognitionの公開前条件

R35は子#119〜#122の実装・B03・配布候補・PRまで。公開時は[B03記録](validation/v1.3.md)、確定SHAの8環境CI、Cognition/Memory/Documentを含む通常wheel/sdistと10例、同期済み引継ぎ書を確認する。公開用の子Issueを先行登録して導入/例ガイドを公開版に合わせ、タグ/Release・checksum・匿名取得・学習/再起動を確認する。初期学習の制約をReleaseにも明記し、公開前に親#13/マイルストーンを閉じない。公開済みv1.2.0以前は差し替えない。

## R36：顧客向け主要Docsの公開条件

各リリースで顧客Markdown・PDF・HTMLを同じ対象版/タグへ同期する。Customer Docs CI成功、原稿/証跡/生成物・参照SHAの一致、cleanな生成、全ページ表示確認を完了条件に含める。対象版・公開状態を証跡と表紙へ記録し、同じタグから生成・検証したMD/PDF/HTML/JSON一式をReleaseへ保存する。CI artifactだけは期限付きのため正式公開物の代用にしない。過去の公開添付は置換しない。[ADR 0030](adr/0030-customer-docs-as-primary.md)・[手順](customer-guide-authoring.md)を参照する。

## R37：v1.4開発候補

基点は未マージのv1.3 PR #123で、v1.4候補を積み重ねて開発する。今回の目標はv1.10までの実装・検証の反復であり、新規タグ/Release・過去公開物の差替えを自動実施しない。親#14・子#126〜#130、ADR 0031・[B04](validation/v1.4.md)の受入結果、形式1→2移行と旧バイナリ非互換、12例・通常配布・CI・主要Docs一式をレビュー可能に整える。公開を行う時点で専用の公開課題と取得/通常導入の確認を行う。
