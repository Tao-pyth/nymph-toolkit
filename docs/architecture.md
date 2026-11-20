# Architecture

## 最終ビジョンとの関係

NTKは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格Nymphを支える基盤を目指す。[Project Vision](vision.md)を長期目標の本文とし、[ADR 0010](adr/0010-project-vision.md)で現在の実装範囲との関係を記録する。

記憶・言語獲得・機能的な自己認識・活動選択・人格・睡眠はNymph側の長期能力として扱う。内部状態・動機・情動やSelf-Modelの具体的な配置は未決であり、Coreへ認知・価値判断を追加する根拠にしない。再起動後の記憶・発達状態の維持は長期目標で、Coreの永続化方式と実装時期は別途判断する。

言語理解・文章生成の中核を既存LLMに代行させず、経験からの獲得過程を研究する。ASR・音声合成・形態素解析・文書解析などの補助技術は利用を許容する。PC環境の観測・操作は将来のAdapterを通じ、明示的な権限管理と必要に応じた承認を設計する。Desktop Adapterの時期や権限管理の配置・APIは未決である。

## 採用された構成

Coreを中心にSubsystem・Adapterを着脱する構成と、Core Runtime・Registry・Connections・TaskManagerの4責務は確定している。初期実装の対象はCoreで、Nymph・Subsystem・Adapterの役割は検証用ダミーで再現する。根拠はR2、判断記録はADR 0001・0005。

| 構成要素 | 責務の整理案 | 実装前に具体化する点 |
|---|---|---|
| Core Runtime | Coreの起動、実行、停止を取りまとめる | ライフサイクルAPI、イベントループの所有者、停止時の後処理 |
| Registry | Subsystem・Adapterの登録状態と識別を管理する | 登録ID、重複登録、依存関係、着脱の可能な時点 |
| Connections | 採用した経路で接続と通信を管理する | 通信経路ADR、要求と結果、同期・非同期境界、失敗通知 |
| TaskManager | Nymphが決めた活動の予定、実行状態、変更を管理する | 時刻・期間、状態遷移、変更や取消、競合の扱い |
| Subsystem | 着脱する機能単位 | Coreとの接続契約とライフサイクル |
| Adapter | 外部環境との接点を担う着脱可能な構成要素 | 接続契約。将来のPC状況取得はここに配置 |

4責務の採用と、上表の詳細なAPI分担は別々に状態を管理する。TaskManagerの活動決定権に関する境界は確定事項である。

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

着脱は確定方針である。R4を受けた設計案として、実装を交換できる接続契約を設け、他Subsystemへの機能的依存を許容する方向で検討する。具体的な相手実装への依存を避け、単体での完全動作を必須条件にしない。

依存先の解除による機能の利用不能をCoreが検出し、状態を利用側へ伝える方法をV0.3で決める。代替機能の提供は必須条件にしない案とする。依存の宣言形式、解除を許可する条件、進行中活動への影響は要決定。データの複製・移植は初期スコープ外である。詳細はADR 0001。

## 実行配置と通信経路

ハイブリッド実行は確定方針であり、同一プロセスと別プロセスの配置を想定する。Python `asyncio` と軽量なメソッド呼び出しは方向性確定。Core経由の処理もメソッド呼び出しで構成できる。

通信経路の最後の正式採用はCore経由のみである。直接接続の緩和案は未採用。Connectionsの実装前にADR 0003へ判断を記録する。メソッド呼び出しという実装方法から直接接続の許可を推定しない。

維持・緩和の後続判断が確定するまではCore経由のみを実装上の暫定基準とし、直接通信を前提とするコードを書かない。Coreによる毎回の呼び出し、または通信をCoreへ仲介するProxyはこの原則に整合する。Coreが接続・許可した後にSubsystem間で直接呼び出す方式や直接音声ストリームは、原則変更の判断を要する。Proxyの具体的な実装採用は未決である。

配置間で通信契約を共通化するか、その共通範囲、IPC方式、シリアライズ方式、同期・非同期境界は要決定。別プロセス対応をV0.7で実装する配分は提案である。

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

各連携はADR 0003の採用経路を使う。Discord音声の取得・保存・学習は告知、適切な同意、権限、保持・削除方針を設計時に扱う。名称・順序・配分と検証範囲の判断は[ADR 0007](adr/0007-v1-release-roadmap.md)、研究方針・責務・音声の扱いは[ADR 0008](adr/0008-subsystem-adapter-boundaries.md)に記録する。複製・移植・伝播機構は初期開発の対象外である。

## 配布方針とフォルダ構成

R6で、単一リポジトリを維持し、CoreとContractsを一つの配布パッケージから始め、Subsystem・Adapterは必要に応じて分割する方針を採用した。[ADR 0009](adr/0009-package-distribution.md)に判断を記録する。

配布パッケージはインストール・配布の単位を指す。初期はルートの `pyproject.toml` でCoreとContractsを同梱し、ソース上では `src/nymph_toolkit/core/` と `src/nymph_toolkit/contracts/` に分ける。リポジトリ名、配布パッケージ名、Pythonのimport名は区別し、配布パッケージの正式名称は実装開始時に決める。

ContractsにはCoreと接続側が共有する契約を、v0.xの実装で必要なものから配置する。v1.0.0で公開接続契約として体系化する。依存方向の設計案として、Core・Subsystem・Adapterが公開Contractsを参照し、Contractsを具体的な実装から独立させる。契約の型やAPIはADR 0006で具体化する。

### 初期の配置

文書・Git設定・Apache-2.0の `LICENSE` は公開準備資料として配置済みである。自作コード・Contracts・設計文書への適用は[ADR 0011](adr/0011-apache-2.0-license.md)で採用した。以下の `pyproject.toml`、`src/`、`tests/` は実装着手時に作成する予定である。

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
├─ docs/
│  ├─ README.md
│  ├─ NTK-Core-v0.1-Handoff-ja.md
│  ├─ vision.md
│  ├─ architecture.md
│  ├─ roadmap.md
│  ├─ acceptance.md
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
│     └─ 0013-milestone-issue-workflow.md
├─ src/
│  └─ nymph_toolkit/
│     ├─ core/
│     └─ contracts/
└─ tests/
   ├─ core/
   ├─ contracts/
   └─ doubles/
```

R3の文書・開発配置案へ、R5のADR 0006〜0008、R6のContracts・ADR 0009、R7のvision・ADR 0010を反映した。4責務は `core/` 内のモジュールとして始める案とし、クラス名と公開API名は実装時に決定する。ダミーは `tests/doubles/`、Coreの検証は `tests/core/`、共有契約の検証は `tests/contracts/` に置く案とする。テスト用ディレクトリも対象の実装・検証が必要になった段階で作成する。

### Subsystem・Adapterを追加する際の配置案

同梱する場合と、別配布にする場合の例を以下に示す。将来の配置・名称は提案であり、個別の分割を決定したものではない。

| 扱い | ソースの配置例 | 配布設定・検証の配置例 |
|---|---|---|
| 初期配布物へ同梱するSubsystem | `src/nymph_toolkit/subsystems/<名称>/` | ルートの `pyproject.toml`、`tests/subsystems/` |
| 初期配布物へ同梱するAdapter | `src/nymph_toolkit/adapters/<名称>/` | ルートの `pyproject.toml`、`tests/adapters/` |
| 別配布にするSubsystem・Adapter | `packages/<配布ディレクトリ>/src/<import名>/` | 対象ディレクトリ内の `pyproject.toml`、`tests/` |

別配布の場合も同じ `nymph-toolkit` リポジトリで管理する。CoreとContractsは初期のルート配下を基準とし、分割対象ごとに依存関係、Core・Contractsの対応バージョン、公開import名、ビルド・検証手順を記録する。共有の設計・ADRは引き続き `docs/` と `docs/adr/` に置く。

依存ライブラリや対応OS、更新頻度、単独導入の必要性を基に分割を判断する。任意依存による同梱も比較対象とし、分割後のバージョンを同期するか独立させるかは後続ADRで決める。配布単位は実行プロセスと通信経路を決定しない。同梱・別配布のいずれも、実行配置はADR 0002、通信経路はADR 0003に従う。

## 実装前の判断一覧

R10・[ADR 0013](adr/0013-milestone-issue-workflow.md)により、コード変更前に対象バージョンのマイルストーン、親Issue、対応単位の子Issueを整備する。以下の設計判断は対象のIssueから追跡し、必要な判断を記録してから実装へ進む。具体的な運用は[issue-workflow.md](issue-workflow.md)を参照する。

| 判断 | 判断する時点の案 | 記録先 |
|---|---|---|
| Python対応版、配布パッケージの正式名称、ビルド・テストツール、Runtimeのライフサイクル | V0.2着手時 | development、ADR 0009と後続ADR |
| Subsystem・Adapterの同梱・分割対象、任意依存、公開import名、バージョン管理 | 各対象の実装・配布を設計する時点 | ADR 0009に関連付ける後続ADR |
| 登録ID、重複、稼働中の着脱、機能的依存の採否・宣言、解除による利用不能の検出と通知 | V0.3着手時 | ADR 0001と後続ADR |
| Core経由維持・直接接続緩和、経路別の許可条件 | Connections実装前 | ADR 0003 |
| 呼び出し契約、同期・非同期境界、失敗通知 | V0.4着手時 | 後続ADR |
| 時計、時刻・期間・経過時間・実行時間の意味、状態遷移、期間終了の意味 | V0.5着手時 | ADR 0004に関連付ける後続ADR |
| 繰り上げ・延期、期間変更、優先度変更、中断・再開、取消・終了の採否、競合と取り外し | V0.6着手時 | ADR 0004と後続ADR |
| IPC、配置間契約の共通範囲、切断時処理 | V0.7着手時 | ADR 0002に関連付ける後続ADR |
| 永続化、再試行、自動復旧の必要性と採否 | 必要な設計段階、遅くともV0.8の検証範囲確定前 | 後続ADR |

未決項目は担当する段階で具体化する。決定記録には採用内容、理由、適用範囲と検証への影響を残す。

v1.xでは、各Contractの公開範囲・互換性、Subsystemの正式名称と学習・意思決定方式、Adapterの対応形式と権限、Personaへの修正値、Sleepの処理範囲、音声受信・ASRの実現方法を追加の判断対象とする。具体化はroadmapとADR 0006〜0008に従う。
