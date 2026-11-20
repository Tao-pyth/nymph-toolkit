# Architecture

## 最終ビジョンとの関係

NTKは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格Nymphを支える基盤を目指す。[Project Vision](vision.md)を長期目標の本文とし、[ADR 0010](adr/0010-project-vision.md)で現在の実装範囲との関係を記録する。

記憶・言語獲得・機能的な自己認識・活動選択・人格・睡眠はNymph側の長期能力として扱う。内部状態・動機・情動やSelf-Modelの具体的な配置は未決であり、Coreへ認知・価値判断を追加する根拠にしない。再起動後の記憶・発達状態の維持は長期目標で、Coreの永続化方式と実装時期は別途判断する。

言語理解・文章生成の中核を既存LLMに代行させず、経験からの獲得過程を研究する。ASR・音声合成・形態素解析・文書解析などの補助技術は利用を許容する。PC環境の観測・操作は将来のAdapterを通じ、明示的な権限管理と必要に応じた承認を設計する。Desktop Adapterの時期や権限管理の配置・APIは未決である。

## 採用された構成

v0.2でRuntime、v0.3でRegistry・ModuleGroupと必要なContractsを実装した。[Runtimeの使い方](runtime.md)と[Registryの使い方](registry.md)、ADR 0014・0016にライフサイクル、登録・依存管理、失敗通知と後処理を記録する。mainではv0.4のConnectionsを開発中で、[操作契約](connections.md)とADR 0019に実装済み部分・未完了部分を区別する。TaskManagerと本番Subsystem・Adapterは後続段階で扱う。

Coreを中心にSubsystem・Adapterを着脱する構成と、Core Runtime・Registry・Connections・TaskManagerの4責務は確定している。初期実装の対象はCoreで、Nymph・Subsystem・Adapterの役割は検証用ダミーで再現する。根拠はR2、判断記録はADR 0001・0005。

| 構成要素 | 責務の整理 | 採用状況・今後具体化する点 |
|---|---|---|
| Core Runtime | Coreの起動、実行、停止を取りまとめる | ADR 0014のRuntimeとADR 0016のModuleGroupを実装 |
| Registry | Subsystem・Adapterの登録状態と識別を管理する | ADR 0016でID・必須依存・スナップショット・着脱範囲を採用して実装 |
| Connections | 採用した経路で接続と通信を管理する | ADR 0015・0017・0018の方針をADR 0019で具体化し開発中。候補・接続固定・操作・中断・ヘルス、非同期保存・救命を実装。性能・配布を含むA04全体は継続中 |
| TaskManager | Nymphが決めた活動の予定、実行状態、変更を管理する | 時刻・期間、状態遷移、変更や取消、競合の扱い |
| Subsystem | 着脱する機能単位 | Coreとの接続契約とライフサイクル |
| Adapter | 外部環境との接点を担う着脱可能な構成要素 | 接続契約。将来のPC状況取得はここに配置 |

4責務の採用と、上表の詳細なAPI分担は別々に状態を管理する。TaskManagerの活動決定権に関する境界は確定事項である。

R13のv0.3実施に伴い、登録・ID単位の必須依存・変更結果の通知・不変スナップショットを[ADR 0016](adr/0016-v0.3-registry.md)で具体化する。Runtime側のModuleGroupが複数のダミーを一つのRuntimeServiceとして束ね、依存順の初期化と逆順の後処理を行う。Registryのavailableは登録された依存先の有無を表し、実行状態や通信許可とは区別する。実体の着脱は実行前に行い、起動から停止完了まで構成を固定する。稼働中の実体交換はConnectionsの解除・失効契約と合わせて後続で判断する。

## 活動と実行の境界

Nymphが活動内容・時刻・期間・変更を決め、Coreが実行管理を担う。例えばNymph役のダミーが活動A、開始時刻T、期間Dを指定し、その後に期間をD2へ変更する。Coreで入力、予定、実行結果を照合する。このT・D・D2は検証用の値で、既定値や公開APIの型は要決定である。

活動の価値評価、睡眠・調査の選択、人格に基づく優先度の生成はNymphが担う。Coreは指定時刻の監視、実行状態の追跡、変更要求の適用可否の判定、実行上の競合や障害の通知を担う。優先度・実行枠を採用する場合、Nymphが入力した優先度と採用済み規則に従って、Coreが実行枠の割り当てや待機順序を機械的に処理する。優先度機能、枠数、割り当て方式、同順位の処理は要決定である。根拠はR2・R4、詳細はADR 0004。

Coreが管理する活動状態はNymph自身の活動を対象とする。外部アプリの稼働状況は将来のAdapterが取得する。認知・学習アルゴリズムはCoreの実行管理の範囲外とする。タイムアウトの条件や障害通知の契約は実装前に判断する。

ダミーの役割は、Nymphの決定を入力するもの、活動を実行して結果を観測できるもの、Adapterの装着を模擬するものとする案を用いる。Nymphの配置先や継承関係は未確定である。

## 時間管理で具体化する概念

以下はR4を受けた用語整理案である。V0.5で意味・計測条件を決め、V0.6の変更や中断・再開の判断に引き継ぐ。

| 概念 | 整理案 | 判断する内容 |
|---|---|---|
| 時刻 | 開始などの時点 | タイムゾーン、時計の補正、指定時刻と実際の開始の関係 |
| 期間 | Nymphが指定する活動の長さ | 終了判定にどの時間を使うか、期間満了の動作 |
| 経過時間 | 基準時点からの時間差 | 基準時点、待機・中断を含めるか、使用する時計 |
| 実行時間 | 実際に活動を実行した時間の累積を候補とする | 開始・停止の計測点、中断分、CPU時間との関係 |

開始時刻の繰り上げ・延期、期間の延長・短縮、優先度変更、中断・再開、取消・終了はV0.6で採否を明示する。具体的な計時方法や対応機能は未確定である。

## Subsystemの独立性の整理案

着脱は確定方針である。R4の整理案を受け、R13・ADR 0016でID単位の必須依存を採用した。具体的な相手実装への依存を避け、依存先不在・解除による利用不能を変更結果として通知する。単体での完全動作や代替機能の提供は必須条件にしない。

Registry単独では依存先解除を許可する。ModuleGroupでは起動から停止完了まで構成変更を拒否する。進行中の通信・活動に関わる実体着脱と、Capability単位の依存などは後続判断に残す。データの複製・移植は初期スコープ外である。履歴はADR 0001、現在の採用範囲はADR 0016を参照する。

## 実行配置と通信経路

ハイブリッド実行は確定方針であり、同一プロセスと別プロセスの配置を想定する。Python `asyncio` と軽量なメソッド呼び出しは方向性確定。Core経由の処理もメソッド呼び出しで構成できる。

R12・[ADR 0015](adr/0015-core-authorized-direct-communication.md)により、Coreが管理・許可した接続でSubsystem間の直接通信を認める。Coreは接続の管理・許可を担い、許可した直接経路の通信ごとにCoreを経由することは必須としない。Core経由のみという旧判断はADR 0003に履歴として保持する。

Coreによる毎回の呼び出しも利用できる。Proxy、直接参照、ストリーム等の具体的な方式、接続元・先、許可条件の詳細、解除・許可撤回と通信中の処理は実装前に決める。Registryへの登録・照会や軽量なメソッド呼び出し方式を、直接通信の許可と同一視しない。Adapter経路や直接音声ストリームへの個別適用は未決である。

R14・[ADR 0017](adr/0017-connection-binding-and-health.md)の方針を、R15・[ADR 0018](adr/0018-connection-selection-health-and-recovery.md)で具体化した。Coreは契約ID・版に合致する候補一覧を返し、要求側の機能が追加条件・属性・稼働状況を手元で評価して利用先を選ぶ。Coreへ選定関数を渡さず、Coreが候補を独自に順位付けしない。提供側は対応する契約ID・版と操作を宣言し、実装バージョンの一致やSemVerメジャー番号による推定で互換性を代用しない。

候補情報には静的なタグ・属性、稼働中／停止／異常、受付可否、機能全体と契約単位の処理数・空き枠を含める。停止・異常・満杯の候補も状態付きで提示する。機能側から変更時に情報を通知し、Coreが一覧生成のたびに問い合わせる方式にしない。実際の受付可否は提供側が最新の容量で判断し、満杯なら直ちに一時利用不可を返す。容量待ちや、それだけを理由とする中断・ヘルス申請は行わない。

確立した接続は利用ごとの候補検索・選定・許可条件の再審査を省く。稼働中の初回接続追加を認めるが、確定済み接続先は同じRuntimeの稼働中に変更しない。初回追加はサービス実体の稼働中着脱の採用を意味しない。

接続設定は再起動を越えて保存し、Runtime起動時に存在・稼働状態・宣言契約の適合を確認して、有効な接続を再利用する。無効な保存済み接続は失効させ、次の要求で要求側が選び直す。無効な接続だけを理由にCore全体を起動失敗にしない。初回に選んだ相手が停止・異常なら接続を確定・保存せず利用不可を返す。一部の契約のみ異常なら、その契約の接続だけを失効対象とする。登録世代`generation`は契約版とは別概念である。

ヘルスチェックは起動時と機能側の申請で行い、機能・接続の指定と全体指定を認める。同じ対象でも申請は統合せず個別に処理し、Coreが保持する存在・稼働状態・宣言契約を確認する。自己診断操作は呼び出さない。Core・Runtime自身に定期申請を持たせず、将来のSleep等から周期的に申請する構成を認める。

連携エラーではCoreが要求元機能Aへ中断を通知し、A自身が機能全体の実行を中断・後処理して完了を報告する。巻戻し・途中状態の扱いは機能・操作ごとに決める。提供側Bや無関係な機能を自動的に止めず、Bが異常なら他の利用側には接続失効を通知してB依存の処理を避ける。宣言済みの通常の失敗は結果として扱い、想定外例外や接続・契約不整合と区別する。

確認中・中断中に届く新規要求は、要求側が必ず指定する期限まで待機する。途中で異常と判定されても期限まで後続の外部申請による正常確認を待つ。待機のためのCore定期チェックは追加しない。同じ接続先の正常確認後は次の要求・待機中の新規要求から再開し、元の失敗処理は再実行しない。同期・非同期を操作ごとに明示し、同期操作でも必要な待機は非同期準備で扱う。

R14追補により、失効の目的は接続の不整合によるエラー回避とする。機能側はCoreの管理結果に従う前提であり、望まない参照の継続を強制遮断する要件は設けない。毎回のアクセス禁止判定を追加せず、接続状態の管理と連携エラー時の中断・申請を具体化する。

接続設定に加え、稼働情報の変更や連携エラーの履歴を期間別ファイルへ記録し、非同期・別処理でまとめて書く。急な終了時の未保存分の損失は許容するが、検出した保存エラーを無視して通常受付を続けない。再起動時の現在状態・処理数は機能から取り直す。

保存失敗時は新規受付を停止し、Core内蔵の救命手順として保持期間を過ぎた古い履歴を指定済み予備先へ退避する。退避保存を確認してから元を除去し、主保存先への書込みが回復すれば再開、回復不能なら未保存分を報告して終了する。終了時の追加バッファ退避は行わず、接続設定の保存失敗にも同じ手順を適用する。形式・設定値・既存処理の停止順序等はADR 0018の残課題である。

これらは方針採用済み・未実装であり、既存Runtime・Registry・ModuleGroupの実装済み契約を変更した記述ではない。配置間の契約共通範囲、IPC・シリアライズ、具体的な公開APIと同期・非同期操作の対応は要決定。別プロセス対応をV0.7で実装する配分は提案である。

## v1.0.0以降の構成案

R5でv1.0.0の目標として、CoreとSubsystem・Adapterの接続契約を大きく形作ることを追加する。v0.9.0のCore完成を踏まえ、Module、Lifecycle、Capability、Communication、Task、Errorの各Contractを検討する。公開API、接続用の開発補助機能、ダミーによる契約テストを整備する案で、本番Subsystemの完成は必須条件としない。具体的な契約は[ADR 0006](adr/0006-core-connection-contracts.md)で判断対象を管理する。

以下はv1.xの設計提案で、Subsystem名・Adapter名はすべて暫定名称である。実装順序、各バージョンへの機能配分、契約の型やAPIは未確定。Subsystem・Adapter向けの共通接続契約を作る目標から、配置間のIPC統一や直接通信の許可を推定しない。

| 構成案 | 役割と境界 |
|---|---|
| MemoryとDocument Adapter | 経験・知識の最小保存・取得と文書入力。複雑な知識グラフ・高度な記憶統合は初期の必須条件にしない |
| CognitionとText Interaction / Web Adapter | 語彙・構文・概念の初期学習、文章観測・出力・ユーザー訂正。既存LLMを言語理解・文章生成の中核とする方式は現在の研究方針に含めない |
| AgencyとTaskManager | AgencyがNymph側の活動内容・開始時刻・期間・優先度・変更を決め、Coreが登録・実行・状態追跡・変更要求の適用を担当 |
| PersonaとAgency | Personaが人格特性を保持・返却し、外部の修正値を契約に沿って適用する。自発的な人格修正の開始は行わず、Agencyが参照した特性を行動選択へ反映 |
| SleepとMemory・Persona | 経験統合・忘却・夢・人格修正値の生成を段階的に検討。Personaへ接続契約を通じて修正値を渡し、内部状態を直接変更しない基本案 |
| Discord Voice Adapter | 他者同士の音声会話の観測。ASRによる文字起こしと音響特徴の併用を基本案とする |
| Desktop Adapter | PC全体の稼働状況取得・操作の将来候補。v1.10.0までの配分外 |

各連携はADR 0015と後続判断による採用経路を使う。Discord音声の取得・保存・学習は告知、適切な同意、権限、保持・削除方針を設計時に扱う。名称・順序・配分と検証範囲の判断は[ADR 0007](adr/0007-v1-release-roadmap.md)、研究方針・責務・音声の扱いは[ADR 0008](adr/0008-subsystem-adapter-boundaries.md)に記録する。複製・移植・伝播機構は初期開発の対象外である。

## 配布方針とフォルダ構成

R6で、単一リポジトリを維持し、CoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて分割する方針を採用した。[ADR 0009](adr/0009-package-distribution.md)に判断を記録する。

配布パッケージはインストール・配布の単位を指す。ルートの `pyproject.toml` でCoreとContractsを同梱し、ソース上では `src/nymph_toolkit/core/` と `src/nymph_toolkit/contracts/` に分ける。ADR 0014で配布名を `nymph-toolkit`、import名を `nymph_toolkit` として採用した。

ContractsにはCoreと接続側が共有する契約を、v0.xの実装で必要なものから配置する。v1.0.0で公開接続契約として体系化する。依存方向の設計案として、Core・Subsystem・Adapterが公開Contractsを参照し、Contractsを具体的な実装から独立させる。契約の型やAPIはADR 0006で具体化する。

### 初期の配置

文書・Git設定・Apache-2.0の `LICENSE` に加え、v0.2で `pyproject.toml`、`src/`、`tests/`、ダミー例、検証ツールとCIを配置した。自作コード・Contracts・設計文書へのライセンス適用は[ADR 0011](adr/0011-apache-2.0-license.md)に従う。

```text
nymph-toolkit/
├─ README.md
├─ CONTRIBUTING.md
├─ AGENTS.md
├─ .gitignore
├─ .gitattributes
├─ LICENSE
├─ CHANGELOG.md
├─ pyproject.toml
├─ requirements-dev.txt
├─ .github/workflows/ci.yml
├─ examples/runtime_demo.py
├─ examples/registry_demo.py
├─ examples/connections_demo.py
├─ tools/check_dist.py
├─ tools/benchmark_connections.py
├─ tools/check_docs.py
├─ tools/build_handoff.py
├─ docs/
│  ├─ README.md
│  ├─ NTK-Core-v0.1-Handoff-ja.md
│  ├─ vision.md
│  ├─ architecture.md
│  ├─ runtime.md
│  ├─ registry.md
│  ├─ connections.md                # v0.4開発中の操作契約
│  ├─ roadmap.md
│  ├─ acceptance.md
│  ├─ validation/v0.2.md
│  ├─ validation/v0.3.md
│  ├─ validation/v0.4.md             # 開発中の検証経過・未完了項目
│  ├─ development.md
│  ├─ issue-workflow.md
│  ├─ release.md
│  └─ adr/
│     ├─ README.md
│     ├─ 0001-core-and-repository.md
│     ├─ 0002-execution-model.md
│     ├─ 0003-communication-routing.md
│     ├─ 0004-activity-authority.md
│     ├─ 0005-initial-scope.md
│     ├─ 0006-core-connection-contracts.md
│     ├─ 0007-v1-release-roadmap.md
│     ├─ 0008-subsystem-adapter-boundaries.md
│     ├─ 0009-package-distribution.md
│     ├─ 0010-project-vision.md
│     ├─ 0011-apache-2.0-license.md
│     ├─ 0012-v0.1-publication.md
│     ├─ 0013-milestone-issue-workflow.md
│     ├─ 0014-v0.2-runtime.md
│     ├─ 0015-core-authorized-direct-communication.md
│     ├─ 0016-v0.3-registry.md
│     ├─ 0017-connection-binding-and-health.md
│     ├─ 0018-connection-selection-health-and-recovery.md
│     └─ 0019-v0.4-connections.md
├─ src/
│  └─ nymph_toolkit/
│     ├─ core/
│     └─ contracts/
└─ tests/
   ├─ core/
   └─ doubles/
```

R3の配置案をR11・R13の実装に合わせて具体化した。Runtimeは `core/runtime.py`、Registryは `core/registry.py`、複数対象の実行入口は `core/module_group.py` に置く。契約は `contracts/__init__.py` と `contracts/registry.py`、ダミーは `tests/doubles/`、検証は `tests/core/` に置く。Connections・TaskManagerのモジュール・APIはその実装時に判断する。

### Subsystem・Adapterを追加する際の配置案

同梱する場合と、別配布にする場合の例を以下に示す。将来の配置・名称は提案であり、個別の分割を決定したものではない。

| 扱い | ソースの配置例 | 配布設定・検証の配置例 |
|---|---|---|
| 初期配布物へ同梱するSubsystem | `src/nymph_toolkit/subsystems/<名称>/` | ルートの `pyproject.toml`、`tests/subsystems/` |
| 初期配布物へ同梱するAdapter | `src/nymph_toolkit/adapters/<名称>/` | ルートの `pyproject.toml`、`tests/adapters/` |
| 別配布にするSubsystem・Adapter | `packages/<配布ディレクトリ>/src/<import名>/` | 対象ディレクトリ内の `pyproject.toml`、`tests/` |

別配布の場合も同じ `nymph-toolkit` リポジトリで管理する。CoreとContractsは初期のルート配下を基準とし、分割対象ごとに依存関係、Core・Contractsの対応バージョン、公開import名、ビルド・検証手順を記録する。共有の設計・ADRは引き続き `docs/` と `docs/adr/` に置く。

依存ライブラリや対応OS、更新頻度、単独導入の必要性を基に分割を判断する。任意依存による同梱も比較対象とし、分割後のバージョンを同期するか独立させるかは後続ADRで決める。配布単位は実行プロセスと通信経路を決定しない。同梱・別配布のいずれも、実行配置はADR 0002、通信経路はADR 0015と後続判断に従う。

## 実装前の判断一覧

R16でv0.4へ着手した。後続の公開型・接続制御・保存の実装判断は[ADR 0019](adr/0019-v0.4-connections.md)を参照する。R15時点の未実装という説明を現在の全体状況と混同せず、受入・公開の完了は個別に確認する。

R10・[ADR 0013](adr/0013-milestone-issue-workflow.md)により、コード変更前に対象バージョンのマイルストーン、親Issue、対応単位の子Issueを整備する。以下の設計判断は対象のIssueから追跡し、必要な判断を記録してから実装へ進む。具体的な運用は[issue-workflow.md](issue-workflow.md)を参照する。

| 判断 | 判断する時点の案 | 記録先 |
|---|---|---|
| Python対応版、配布パッケージの正式名称、ビルド・テストツール、Runtimeのライフサイクル | v0.2で採用済み | development、ADR 0014 |
| Subsystem・Adapterの同梱・分割対象、任意依存、公開import名、バージョン管理 | 各対象の実装・配布を設計する時点 | ADR 0009に関連付ける後続ADR |
| 登録ID、重複、必須依存・解除による利用不能の通知、スナップショット、ModuleGroup | v0.3で採用。稼働中実体着脱は延期 | ADR 0016 |
| Coreが許可する直接通信の採否 | R12で採用済み | ADR 0003の履歴とADR 0015 |
| 候補選定・保存、初回追加と確定済み接続先の固定、起動時・ヘルスチェック時の検証、連携エラー時の中断・申請 | R14で方針を採用。未実装 | ADR 0017 |
| 要求側選定、契約互換性、永続化、稼働通知、協調的中断・待機、ヘルス申請、履歴保存・救命措置 | R15で振る舞いを採用。未実装 | ADR 0018 |
| 公開API・型、接続識別と競合、通知・待機の競合、保存形式・設定値、救命の具体手順 | Connectionsの対象範囲の実装前。前の計画の方式・数値は未採用案 | ADR 0018と後続ADR |
| 時計、時刻・期間・経過時間・実行時間の意味、状態遷移、期間終了の意味 | V0.5着手時 | ADR 0004に関連付ける後続ADR |
| 繰り上げ・延期、期間変更、優先度変更、中断・再開、取消・終了の採否、競合と取り外し | V0.6着手時 | ADR 0004と後続ADR |
| IPC、配置間契約の共通範囲、切断時処理 | V0.7着手時 | ADR 0002に関連付ける後続ADR |
| 接続設定・運用履歴以外の永続化、接続先固定と両立する追加の再試行・復旧機能 | 必要な設計段階、遅くともV0.8の検証範囲確定前。R15採用範囲と区別 | ADR 0018と後続ADR |

未決項目は担当する段階で具体化する。決定記録には採用内容、理由、適用範囲と検証への影響を残す。

v1.xでは、各Contractの公開範囲・互換性、Subsystemの正式名称と学習・意思決定方式、Adapterの対応形式と権限、Personaへの修正値、Sleepの処理範囲、音声受信・ASRの実現方法を追加の判断対象とする。具体化はroadmapとADR 0006〜0008に従う。
