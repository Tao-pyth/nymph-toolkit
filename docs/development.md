# 開発準備とGit運用

本書はコード・Docsを編集して検証する人向けの開発環境の手順である。公開v1.2.0を試す場合は[通常導入](getting-started.md)と[実行例ガイド](tutorials.md)を先に読む。現在の開発候補はv1.6.0。開発用editable環境と公開wheelの確認環境を分け、版とimport元を記録する。

## 公開準備時の環境

2026年11月19日の公開準備環境にはGit 2.56.0.windows.4とPython 3.8が存在した。v0.2ではADR 0014によりCPython 3.12以上を採用した。既存のPython 3.8は変更せず、開発用のPythonと仮想環境を別に用意する。

## Coreの環境構築

CPython 3.12以上を用意し、リポジトリ直下で実行する。以下はPowerShellの例。仮想環境のactivateは不要である。

```powershell
python --version
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -W error -m unittest discover -s tests -t . -v
.venv/Scripts/python.exe examples/runtime_demo.py
.venv/Scripts/python.exe examples/registry_demo.py
.venv/Scripts/python.exe examples/connections_demo.py
.venv/Scripts/python.exe examples/task_manager_demo.py
.venv/Scripts/python.exe examples/activity_changes_demo.py
.venv/Scripts/python.exe examples/hybrid_demo.py
.venv/Scripts/python.exe examples/module_contract_demo.py
.venv/Scripts/python.exe examples/memory_demo.py
.venv/Scripts/python.exe examples/document_demo.py
.venv/Scripts/python.exe examples/cognition_demo.py
.venv/Scripts/python.exe -W error tools/validate_hybrid_load.py --output .git/v08-short.json
.venv/Scripts/python.exe tools/check_api.py
.venv/Scripts/python.exe tools/check_contracts.py
.venv/Scripts/python.exe tools/check_completion.py
.venv/Scripts/python.exe tools/check_docs.py
.venv/Scripts/python.exe -m build
.venv/Scripts/python.exe tools/check_dist.py
```

Linuxでは `.venv/Scripts/python.exe` を `.venv/bin/python` に置き換える。Pythonの下限はpyproject.tomlにも記録する。実行時の外部依存はなく、build 1.6.1とHatchling 1.33.0をビルド時だけ使う。テストは標準unittestを用いる。

distには対象版のwheelとsdistを一つずつ置く。古い版が残っている場合は対象を確認して作業フォルダ外へ保管する。check_distは新規仮想環境を作り、wheelの通常インストール、公開import・LICENSE・メタデータ、sdistから同一wheelへの再ビルドを確認する。開発用のeditable installだけで配布検証を済ませない。

CIはWindowsとLinux、Python 3.12〜3.15で全テスト、Core/接続契約/Memory/Document/Cognitionの10実行例、短い4配置負荷、API・契約基準・64項目・文書同期、ビルドと通常配布検証を行う。Runtimeの操作・キャンセル・失敗通知は[runtime.md](runtime.md)、登録・依存管理と複数対象の実行は[registry.md](registry.md)、接続・保存は[connections.md](connections.md)、活動管理は[task-manager.md](task-manager.md)に記載する。v0.5は[当時の検証記録](validation/v0.5.md)、v0.6の変更・中断再開は[v0.6の検証記録](validation/v0.6.md)を参照する。

接続の性能測定は `python tools/benchmark_connections.py --iterations 5000 --initial-connections 20 --samples 3` で行う。実行環境・生の各標本・中央値をJSONで表示する。初回確立の設定保存、継続直接呼出し、Core経由、稼働通知と履歴排出、ヘルス申請を分ける。測定値は環境依存で、合否を固定の速度閾値で判定しない。

## v0.9の完成監査（当時の手順）

v0.9.0は公開済みで、[A09-04の公開後確認](https://github.com/Tao-pyth/nymph-toolkit/issues/88#issuecomment-7067230161)まで完了している。以下のコマンド、14＋92件・6例という件数はv0.9.0のcheckoutで使った当時の手順である。現在のcheckoutでは上の環境構築と末尾のv1.4節を使い、Core 15件・Contracts 98件・12例を照合する。現行の意味と証拠は[Core API](core-api.md)・[証拠対応表](validation/core-coverage.md)を参照する。

```powershell
.venv/Scripts/python.exe tools/check_api.py
.venv/Scripts/python.exe tools/check_completion.py
.venv/Scripts/python.exe tools/check_docs.py
.venv/Scripts/python.exe -W error -m unittest discover -s tests -t . -v
.venv/Scripts/python.exe -m build --outdir .git/v09-dist
.venv/Scripts/python.exe tools/check_dist.py --dist-dir .git/v09-dist
```

check_apiは公開Core 15＋Contracts 98件の一覧と実装を照合する。API変更時は--writeで一覧を更新する。core-coverage.jsonは64項目の採用文・実在テストID・実装・資料の対応を保持し、check_completion.py --writeで表示表を再生成する。両検査は全動作試験の代わりにはならない。変更後はbuild_handoff.pyで単一引継ぎ書を同期する。

配布検査は新規環境へ通常wheelを導入し、作業ツリーのsrcを含めず全試験・6実行例・API照合・4配置短負荷を実行して、sdist同一wheel再ビルドを確認する。--dist-dirは旧版のビルド成果物と混在させないための任意引数。CIは従来どおり空のdistを使う。A09の公開前の証拠と公開後結果の参照先は[検証記録](validation/v0.9.md)に記録する。

## v0.8の再現・負荷検証

[ADR 0024](adr/0024-v0.8-integration-validation.md)に測定条件、[検証記録](validation/v0.8.md)にA08対応表と実測を記載する。

```powershell
.venv/Scripts/python.exe -W error -m unittest tests.core.test_v08_integration tests.core.test_v08_contention tests.core.test_v08_storage tests.core.test_v08_result_ownership -v
.venv/Scripts/python.exe -W error tools/validate_hybrid_load.py --output .git/v08-short.json
.venv/Scripts/python.exe -W error tools/validate_hybrid_load.py --duration 1800 --output .git/v08-long.json
```

測定CLIはテスト専用ダミーを使用し、4配置を実TCP・実子で動かす。起動・遅延・転送・メモリ・管理応答・停止と資源数をJSONへ記録する。長時間試験は変更のないコミットから実施し、変更が入った場合はその影響と再検証を記録する。通常履歴は捨てず、活動結果の保持件数と不要資源を分ける。CIでは1秒の短い継続区間を使い、30分試験の代替にしない。機械・計測器・併走処理による影響を含む観測であり、速度保証ではない。

## 実装開始時の配布構成

v0.2での採用結果は[ADR 0014](adr/0014-v0.2-runtime.md)に記録する。CPython 3.12以上、配布名 `nymph-toolkit`、venv・pip、build・Hatchling、標準unittestを使用する。実行時依存は追加しない。Core・Contractsの単一wheel・sdistをGitHub Releaseから配布する。以下にある「実装開始時に記録する」項目のうち、これらは本ADRで具体化した。

[ADR 0009](adr/0009-package-distribution.md)に従い、CoreとContractsを一つの配布パッケージとして扱う。ルートの `pyproject.toml` に配布設定を置き、`src/nymph_toolkit/core/` と `src/nymph_toolkit/contracts/` を同梱する。v0.2のライフサイクル契約に加え、v0.3で登録・依存・変更通知の契約を実装した。v0.4で接続契約、v0.5で活動契約を具体化した。v0.6で変更操作・中断再開・優先度の契約を追加した。v0.7でIPC・ストリーム・遠隔活動を追加した。Windowsでは標準asyncio.runなど子プロセス対応ループを使う。APIと設定は[hybrid.md](hybrid.md)、結果は[v0.7検証記録](validation/v0.7.md)に記録する。

ビルドした配布物をcheck_distで新しい環境へインストールし、採用したCore・Contractsの公開importとダミー実行を確認する。結果はacceptanceの記録形式で残す。

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

## コード変更前の必須条件

R10・[ADR 0013](adr/0013-milestone-issue-workflow.md)により、コード変更前に対象バージョンのマイルストーン、親Issue、対応単位の子Issueをこの順で整える。親子関係と双方のマイルストーンを確認し、子Issueの範囲・完了条件・検証方法・先行課題を記録する。実装に必要な判断を残したまま、その範囲のコードを書き始めない。

具体的な登録・完了手順と現在の課題は[Issue運用](issue-workflow.md)、エージェント向けの要点は[AGENTS.md](../AGENTS.md)を参照する。以後のコミットまたはPRには対応する子Issue番号を記載し、子Issueへ検証結果と残課題を記録する。文書のみの修正はこの必須条件の対象外だが、関連する設計判断をDocs・ADRへ記録する。

## 日常の作業案

設計判断・文書更新・実装を目的が分かる単位でコミットする。関連するADR・実装・受入条件は同じ作業で整合させる。変更が複数に分かれる場合は作業ブランチを使用する案とする。

```powershell
git status --short --branch
git switch -c docs/refine-core-design
# ファイル編集後、対象パスを指定してgit addする
git diff --cached --check
git diff --cached
```

各段階で本書の環境構築、テスト、ダミー受入シナリオを更新する。新しい作業環境で再現し、OS・Python版・依存版と結果をacceptanceの記録形式で残す。

## 文書更新時の確認

Docs編集後は `python tools/build_handoff.py` で引継ぎ書を再生成し、`python tools/check_docs.py` で収録元との一致・ローカルリンクを確認する。CIは再生成を自動保存せず、一致していない場合に失敗する。API・採用範囲は `python tools/check_api.py` と `python tools/check_completion.py` で照合する。新規Docsの収録一覧更新は生成ツールのコード変更に当たるため、先に親子Issueを整える。今回の結果は[Docs整備の検証記録](validation/docs-onboarding.md)へ記録し、過去の各版の受入結果と区別する。

ローカルリンク先の存在、ADRの状態と根拠、ロードマップと受入IDの対応、READMEの実装状況を確認する。単一配布用引継ぎ書はDocs索引に示した順序・変換方法で再作成し、収録元の本文と照合する。将来の配置予定はarchitectureのツリーに記載し、リンクは実在するファイルへ向ける。

公開準備と公開後の状態は[release.md](release.md)で確認する。

## 顧客向け資料の配布版

[契約・利用ガイド](customer-guide.md)のMarkdown・PDF・HTMLは主要Docsであり、機能・契約・利用・制約変更時の同期・生成・検証を必須とする。生成依存はPython製品の実行環境とは分離する。[生成と表示確認の手順](customer-guide-authoring.md)に従い、本文・図・APIの照合、全ページの表示、引継ぎ書同期を確認する。Node依存をNTK実行時や通常のwheel検証へ追加しない。結果は[顧客資料の検証記録](validation/customer-guide.md)へ記録する。

## v1.0で確立した接続契約の確認

親#10・子#98〜#102とADR 0026に基づく。`python tools/check_contracts.py`で安定対象を照合する。差分が出たら互換性・移行・Issue/ADRを先に確認し、基準JSONだけを書き換えて通さない。`python examples/module_contract_demo.py`は7番目の実行例。[6契約](module-contracts.md)・[移行](migration-v1.md)・[B00検証](validation/v1.0.md)を参照する。

## v1.1 Memoryの開発・配布確認

[Memory](memory.md)と[ADR 0027](adr/0027-v1.1-memory.md)を読み、`python examples/memory_demo.py`、`python -W error -m unittest tests.subsystems.test_memory tests.subsystems.test_memory_integration -v`で確認する。Memoryは8番目の例。通常導入は公開版の導入ガイドに従い、開発環境の版とimport元を別途確認する。v1.1当時は`.git/v11-dist`を使ったが、現在の配布検査は末尾のv1.4節を使う。

## v1.2 Documentの開発確認

以下はv1.2開発時点の手順。現在の開発候補は末尾のv1.4節を参照する。checkoutをeditable導入して[Documentガイド](document.md)・[ADR 0028](adr/0028-v1.2-document-adapter.md)に従う。`python examples/document_demo.py`が9番目の例。`python -W error -m unittest discover -s tests/adapters -t . -v`で単体/統合、既存の全体discoverで回帰を確認する。

配布候補は`python -m build --outdir .git/v12-dist`、`python tools/check_dist.py --dist-dir .git/v12-dist`。v1.2当時の検査は1.2.0を期待し、Core/Memory/Documentのimport、9例、全テスト、sdist再構築を確認する。Docs更新はbuild_handoff/check_docs、安定APIと採用64項目も従来どおり照合する。

## v1.3 Cognitionの開発確認

v1.3当時はcheckoutを`python -m pip install -e .`で導入し、版1.3.0を確認した。現行checkoutは末尾のv1.4節を使う。[Cognitionガイド](cognition.md)・[ADR 0029](adr/0029-v1.3-cognition-learning.md)に従い、`python examples/cognition_demo.py`と`python -W error -m unittest tests.subsystems.test_cognition tests.subsystems.test_cognition_integration -v`を実行する。公開v1.2のwheelにはCognitionは含まれない。

v1.3当時の通常配布検査は`python -m build --outdir .git/v13-dist`、`python tools/check_dist.py --dist-dir .git/v13-dist`で1.3.0を期待する。全回帰、10例、短い4配置負荷、sdist同一wheel再構築、API/契約/64項目/Docs同期を確認する。公開済みタグ・添付と現行版向け導入ガイドを開発候補へ無断で置き換えない。

## v1.4候補の開発・検証

`python -m pip install -e .`後にimportlib.metadataで1.4.0を確認する。[入力・訂正ガイド](interaction.md)の例2件を含む12例、全回帰、`python tools/check_api.py`・`check_contracts.py`・`check_completion.py`を確認する。通常配布は`python -m build --outdir .git/v14-dist`、`python tools/check_dist.py --dist-dir .git/v14-dist`。顧客主要Docsは本文/図を実装へ照合して証跡を更新し、PDF/HTML生成・全ページ表示確認を行う。その後引継ぎ書を再生成し`python tools/check_docs.py`を通す。正確な結果と未完了は[B04](validation/v1.4.md)へ記録する。

## v1.5 Agency候補

`python -m pip install -e .`で1.5.0を導入し、`python examples/agency_demo.py`と全回帰を実行する。[Agencyガイド](agency.md)は初期判断と限界を説明する。通常配布は`python -m build --outdir .git/v15-dist`、`python tools/check_dist.py --dist-dir .git/v15-dist`で全テスト/13例とsdistを確認。既存Core API/契約/64判断、主要Docsと引継ぎ同期も必須。結果は[B05](validation/v1.5.md)。

## v1.6の活動循環

editable環境を1.6.0へ更新し、`python examples/agency_execution_demo.py`、`python -W error -m unittest tests.subsystems.test_agency_execution -v`を実行する。通常配布の検証先は`.git/v16-dist`とする。check_distは全回帰と14例・sdist再構築を行う。CLI/公開導入はv1.2.0と区別する。
