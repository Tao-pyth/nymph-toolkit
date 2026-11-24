# Architecture

## 最終ビジョンとの関係

NTKは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格Nymphを支える基盤を目指す。[Project Vision](vision.md)を長期目標の本文とし、[ADR 0010](adr/0010-project-vision.md)で現在の実装範囲との関係を記録する。

記憶・言語獲得・機能的な自己認識・活動選択・人格・睡眠はNymph側の長期能力として扱う。内部状態・動機・情動やSelf-Modelの具体的な配置は未決であり、Coreへ認知・価値判断を追加する根拠にしない。再起動後の記憶・発達状態の維持は長期目標で、Coreの永続化方式と実装時期は別途判断する。

言語理解・文章生成の中核を既存LLMに代行させず、経験からの獲得過程を研究する。ASR・音声合成・形態素解析・文書解析などの補助技術は利用を許容する。PC環境の観測・操作は将来のAdapterを通じ、明示的な権限管理と必要に応じた承認を設計する。Desktop Adapterの時期や権限管理の配置・APIは未決である。

## 採用された構成

v0.2でRuntime、v0.3でRegistry・ModuleGroup、v0.4でConnections・FileStore、v0.5でTaskManagerと必要なContractsを実装した。[Runtimeの使い方](runtime.md)と[Registryの使い方](registry.md)、ADR 0014・0016にライフサイクル、登録・依存管理、失敗通知と後処理を記録する。接続・保存は[Connections](connections.md)とADR 0019、活動管理は[TaskManager](task-manager.md)とADR 0020・0021を参照する。v1.1でMemory、v1.2でDocumentを公開し、v1.3候補ではCognitionの初期学習を実装し、v1.4候補ではText/Web入力と注釈訂正を追加した。[機能と公開状態](../README.md)を現在の入口とする。

Coreを中心にSubsystem・Adapterを着脱する構成と、Core Runtime・Registry・Connections・TaskManagerの4責務は確定している。v0.xの初期実装はCoreを対象とし、Nymph・Subsystem・Adapterの役割は検証用ダミーで再現した。R31でv1.1 Memoryを最初の実Subsystemとして追加した。現行の実行例も要求側はダミーで、Nymphの自律的な意思決定は未実装。根拠はR2、判断記録はADR 0001・0005と後続の0027〜0029。

| 構成要素 | 責務の整理 | 採用状況・今後具体化する点 |
|---|---|---|
| Core Runtime | Coreの起動、実行、停止を取りまとめる | ADR 0014のRuntimeとADR 0016のModuleGroupを実装 |
| Registry | Subsystem・Adapterの登録状態と識別を管理する | ADR 0016でID・必須依存・スナップショット・着脱範囲を採用して実装 |
| Connections | 採用した経路で接続と通信を管理する | ADR 0015・0017・0018の方針をADR 0019で具体化。候補・接続固定・操作・中断・ヘルス、非同期保存・救命を実装しA04を確認 |
| TaskManager | Nymphが決めた活動の予定、実行状態、変更を管理する | ADR 0020で予定・実行追跡、到達通知、安全な終了、履歴参照、ADR 0021で時刻・期間・優先度変更と中断再開を実装。別プロセスへの適用は0022・0023で具体化しHybridTaskManagerとして実装 |
| Subsystem | 着脱する機能単位 | Memoryを公開、Cognitionをv1.3候補に実装。Core共通接続契約と個別業務契約を利用 |
| Adapter | 外部環境との接点を担う着脱可能な構成要素 | Documentを公開、Text/Webをv1.4候補に実装。将来のPC状況取得Adapterは未実装 |

4責務の採用と、上表の詳細なAPI分担は別々に状態を管理する。TaskManagerの活動決定権に関する境界は確定事項である。

R13のv0.3実施に伴い、登録・ID単位の必須依存・変更結果の通知・不変スナップショットを[ADR 0016](adr/0016-v0.3-registry.md)で具体化する。Runtime側のModuleGroupが複数のダミーを一つのRuntimeServiceとして束ね、依存順の初期化と逆順の後処理を行う。Registryのavailableは登録された依存先の有無を表し、実行状態や通信許可とは区別する。実体の着脱は実行前に行い、起動から停止完了まで構成を固定する。稼働中の実体交換はConnectionsの解除・失効契約と合わせて後続で判断する。

## 活動と実行の境界

Nymphが活動内容・時刻・期間・変更を決め、Coreが実行管理を担う。例えばNymph役のダミーが活動A、開始時刻T、期間Dを指定し、その後に期間をD2へ変更する。Coreで入力、予定、実行結果を照合する。このT・D・D2は検証用の値である。v0.5の時刻・期間はADR 0020、v0.6の変更APIはADR 0021で具体化した。

活動の価値評価、睡眠・調査の選択、人格に基づく優先度の生成はNymphが担う。Coreは指定時刻の監視、実行状態の追跡、変更要求の適用可否の判定、実行上の競合や障害の通知を担う。R18・ADR 0021により、指定優先度の降順・同順位は待機順とし、開始と明示再開を処理する。実行中の活動を自動中断しない。通常実行枠は任意設定で、未指定は上限なし、正の整数を指定したときだけTaskManager全体で制限する。中断完了で枠を解放し、再開時に改めて割り当てる。根拠はR2・R4・R18、詳細はADR 0004・0021。

Coreが管理する活動状態はNymph自身の活動を対象とする。外部アプリの稼働状況は将来のAdapterが取得する。認知・学習アルゴリズムはCoreの実行管理の範囲外とする。タイムアウトの条件や障害通知の契約は実装前に判断する。

ダミーの役割は、Nymphの決定を入力するもの、活動を実行して結果を観測できるもの、Adapterの装着を模擬するものとする案を用いる。Nymphの配置先や継承関係は未確定である。

## 時間管理で具体化する概念

R17・[ADR 0020](adr/0020-v0.5-task-manager.md)により、22時開始・2時間の予定なら翌0時にNymphが判断する。Coreは予定時間到達を通知し、活動を継続して次の指示を待つ。実開始の遅れだけで予定を延長したり、到達だけで終了・中断したりしない。期間はCoreの強制終了タイムアウトではない。受付時点で過去の開始時刻なら開始せず返す。Nymphの終了指示は実行側へ渡し、安全な区切りと後処理を待つ。再起動後は保存済み履歴を返し、再登録・再開はNymphが決める。活動の自動復元・再実行は行わない。

以下はR4を受けた用語整理案である。V0.5で意味・計測条件を決め、V0.6の変更や中断・再開の判断に引き継ぐ。

| 概念 | 整理案 | 判断する内容 |
|---|---|---|
| 時刻 | 開始などの時点 | タイムゾーン、時計の補正、指定時刻と実際の開始の関係 |
| 期間 | Nymphが指定する活動の長さ | 終了判定にどの時間を使うか、期間満了の動作 |
| 経過時間 | 基準時点からの時間差 | 基準時点、待機・中断を含めるか、使用する時計 |
| 実行時間 | 実際に活動を実行した時間の累積を候補とする | 開始・停止の計測点、中断分、CPU時間との関係 |

R18・[ADR 0021](adr/0021-v0.6-activity-changes.md)で、開始時刻の繰り上げ・延期、期間の延長・短縮、優先度とその変更、中断・再開の全4項目をv0.6の対象として採用した。個別回答と残事項の判断委任により、対応状態・計時・優先度・任意実行枠・競合・応答を設計採用した。実行側が中断位置を保持し、経過時間と中断を除く累積実行時間を分ける。v0.5の最小終了操作を維持し、設計と実装の完了を区別する。

## Subsystemの独立性の整理案

着脱は確定方針である。R4の整理案を受け、R13・ADR 0016でID単位の必須依存を採用した。具体的な相手実装への依存を避け、依存先不在・解除による利用不能を変更結果として通知する。単体での完全動作や代替機能の提供は必須条件にしない。

Registry単独では依存先解除を許可する。ModuleGroupでは起動から停止完了まで構成変更を拒否する。進行中の通信・活動に関わる実体着脱と、Capability単位の依存などは後続判断に残す。データの複製・移植は初期スコープ外である。履歴はADR 0001、現在の採用範囲はADR 0016を参照する。

## 実行配置と通信経路

ハイブリッド実行は確定方針であり、同一プロセスと別プロセスの配置を想定する。Python `asyncio` と軽量なメソッド呼び出しは方向性確定。Core経由の処理もメソッド呼び出しで構成できる。

R12・[ADR 0015](adr/0015-core-authorized-direct-communication.md)により、Coreが管理・許可した接続でSubsystem間の直接通信を認める。Coreは接続の管理・許可を担い、許可した直接経路の通信ごとにCoreを経由することは必須としない。Core経由のみという旧判断はADR 0003に履歴として保持する。

Coreによる毎回の呼び出しも利用できる。R12時点では具体的な方式・許可条件・解除等が未決だったが、同一プロセスはADR 0019、配置間の通信と汎用ストリームはR19・ADR 0022で具体化した。Registryへの登録・照会や軽量なメソッド呼び出し方式を、直接通信の許可と同一視しない。本番Adapterや音声固有の処理への適用は引き続き対象機能の設計事項である。

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

上記はR15時点の採用方針を説明したもので、その後R16・[ADR 0019](adr/0019-v0.4-connections.md)で同一プロセスの公開API・同期/非同期操作・状態・非同期保存を具体化し、v0.4.0として実装・検証した。現在の契約は[Connections](connections.md)を参照する。配置間の共通範囲、IPC・シリアライズとv0.7〜v0.9の配分は、R19・[ADR 0022](adr/0022-v0.7-v0.9-hybrid-and-completion.md)で設計採用した。既存契約を暗黙に変更せず、R20・ADR 0023でv0.7を実装した。結果は[検証記録](validation/v0.7.md)、操作は[hybrid.md](hybrid.md)に分ける。

### v0.9までに採用したハイブリッド構成

R19の1〜18は個別回答、19〜64は推奨設定の明示一括採用である。全項目と受入IDはADR 0022を正本とする。親CoreがRegistry・Connections・TaskManager・保存を一元管理し、同じPC・同じPython環境で機能ごとの子プロセスを起動する。配置は起動設定で明示し、機能の着脱は起動前・停止後、稼働中の構成は固定する。子は実行・状態報告を担い、Nymphの判断とCoreの管理の境界は配置によって変えない。

管理通信と許可済み機能間のデータ通信を分け、127.0.0.1・OS割当ポートのTCPを使う。データは直接通信を基本としCore経由も可能。要求・結果・通知はJSONで表現できる値、ストリーム本文はバイト列とする。別プロセス操作は非同期契約と明示し、同じ契約ID・版の既存同期操作を読み替えない。任意のPythonオブジェクトや関数は転送せず、活動実行は登録済み処理IDと引数で指定する。

1ストリームは片方向、双方向は2本。利用機能が両端の転送バッファ上限を明示し、バイト数・チャンク数の上限と待機／古い未転送チャンク破棄を扱う。方針は開設時に固定し、欠落範囲・件数を通知する。送信成功はローカルキュー受付、通常終了は先行データ・終端を受信側の通信機構が受け取った確認までで、内容処理の完了を意味しない。終了待機の期限切れ後も終了処理を継続し、明示打切りと区別する。管理通知はデータ混雑で滞留させない。転送上限を通常履歴バッファへ適用しない。

通常の連携エラーは要求元の協調的中断で扱う。子の予期しない終了は既存の未処理機能障害と同様にRuntimeを停止する。Core停止時に設定期限を超えたCore所有の子だけを強制終了でき、後処理未確認を記録する。同一プロセスの協調的停止、Nymphの通常の終了要求、活動期間の到達へ強制終了を広げない。子だけの再起動・自動再送・接続先切替は採用しない。

活動の開始・中断・再開・終了は実行側の適用報告で確定し、命令ID・版管理を維持する。実行時間は実行側の単調時計で測り、通信遅延や未確認の結果を実行完了に置き換えない。親Coreが保存を集約し、子での発生・Core受付・保存済み・未送信不明を区別する。構成・接続設定・活動変更履歴を保存し、PID・ストリーム途中・実行中処理は復元しない。Nymphが履歴を基に再登録・再開を決める。

v0.7で基本機能、v0.8で統合・障害・負荷・配布、v0.9で全採用範囲の受入と文書・実装の一致を確認する。v0.7のAPI・形式・設定はADR 0023とhybrid.mdへ記録した。R22でA08の統合・障害・負荷検証を進め、条件を[ADR 0024](adr/0024-v0.8-integration-validation.md)、結果を[v0.8検証記録](validation/v0.8.md)に分ける。管理・直接RPCの一時結果を明示解放でき、内部報告は完了後に回収する。活動・命令・保存履歴は維持する。A08の結果だけでCore全体の完成とせず、A09はR24の完成監査とR25の公開確認を[v0.9記録](validation/v0.9.md)・公開課題#88で照合する。

R24では構成と責務を維持したまま、[公開APIの入力・結果・失敗・所有](core-api.md)と[採用64項目の証拠](validation/core-coverage.md)を整理する。生成API一覧は現在の実装との照合に用い、v1.0の安定契約体系や本番機能を新たに採用しない。

## v1.0.0の接続契約と後続構成案

R29・[ADR 0026](adr/0026-v1.0-core-connection-contracts.md)でv1.0目標を具体化した。[接続契約](module-contracts.md)に公開Protocol・登録前検証・初期化中の提供登録・安定対象を定義し、[移行資料](migration-v1.md)に必要なAPI整理を記す。4責務、Core+Contracts同梱、既存64項目は維持する。Contractsのmodules.pyはCoreをimportせず、Coreの実体がその構造を満たす。Memory・Document・Cognitionの初期範囲はADR 0027〜0029で具体化した。それ以外の後続機能の名称・配分は引き続き提案。

R5でv1.0.0の目標として、CoreとSubsystem・Adapterの接続契約を大きく形作ることを追加する。v0.9.0のCore完成を踏まえ、Module、Lifecycle、Capability、Communication、Task、Errorの各Contractを検討する。公開API、接続用の開発補助機能、ダミーによる契約テストを整備する案で、本番Subsystemの完成は必須条件としない。当初の判断対象は[ADR 0006](adr/0006-core-connection-contracts.md)、R29の採用詳細はADR 0026で管理する。

Cognitionの初期学習は[ADR 0029](adr/0029-v1.3-cognition-learning.md)・[利用ガイド](cognition.md)に従う。Documentの採用部分は[ADR 0028](adr/0028-v1.2-document-adapter.md)・[利用ガイド](document.md)に従う。Memoryの採用部分は[ADR 0027](adr/0027-v1.1-memory.md)・[利用ガイド](memory.md)に従う。以下はその基となったv1.xの設計提案で、Subsystem名・Adapter名はすべて暫定名称である。後続の実装順序・機能配分・業務契約の型やAPIは未確定。v1.0の共通接続契約はADR 0026に従う。Subsystem・Adapter向けの共通接続契約を作る目標から、配置間のIPC統一や直接通信の許可を推定しない。

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

ContractsにはCoreと接続側が共有する契約を配置する。R29・ADR 0026でv1.0の共通接続契約を体系化した。Core・Subsystem・Adapterが公開Contractsを参照し、ContractsはCoreの実装をimportしない。将来の業務契約や配布分割は別途具体化する。

### 現在の配置（公開v1.2と開発候補v1.9）

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
├─ examples/task_manager_demo.py
├─ examples/activity_changes_demo.py
├─ examples/hybrid_demo.py
├─ examples/hybrid_dummy.py
├─ examples/module_contract_demo.py  # v1接続契約の起動例
├─ examples/contract_dummy.py        # 公開Contractsだけを使う機能
├─ examples/memory_demo.py           # 8番目：Memory保存・取得・再起動
├─ examples/memory_requester.py
├─ examples/document_demo.py         # 9番目：Document取込・Memory連携
├─ examples/document_requester.py
├─ examples/cognition_demo.py        # 10番目：v1.3からの初期学習
├─ examples/text_interaction_demo.py # 11番目：観測・教師入力・訂正/CLI
├─ examples/web_demo.py              # 12番目：HTTP文章と明示学習
├─ examples/agency_demo.py           # 13番目：活動判断・決定保存
├─ examples/agency_execution_demo.py # 14番目：活動循環・実学習
├─ examples/persona_demo.py          # 15番目：人格特性の外部修正・保存
├─ examples/persona_agency_demo.py   # 16番目：特性更新と活動選択・再開
├─ examples/sleep_demo.py             # 17番目：統合・夢失効・人格案と明示適用
├─ examples/persona_requester.py
├─ examples/cognition_requester.py
├─ tools/check_dist.py
├─ tools/benchmark_connections.py
├─ tools/check_api.py              # 公開export・署名・型の一致
├─ tools/check_contracts.py        # v1安定API基準の照合
├─ tools/check_completion.py       # 64項目・既存受入の証拠参照
├─ tools/validate_hybrid_load.py
├─ tools/check_docs.py
├─ tools/build_handoff.py
├─ tools/check_customer_docs.py     # 顧客資料の同期・PDF/HTML検査
├─ tools/customer-docs/             # 必須のPDF/HTML生成。製品実行時とは分離
│  ├─ package.json
│  ├─ pnpm-lock.yaml
│  ├─ requirements.txt             # PDF検査・描画専用
│  ├─ build.mjs
│  └─ print.css
├─ docs/
│  ├─ README.md
│  ├─ NTK-Core-v0.1-Handoff-ja.md
│  ├─ customer-guide.md             # 主要Docs：現在の実装と契約の顧客向け図解
│  ├─ customer-guide.sources.json   # レビュー済み入力・対象版・公開状態
│  ├─ customer-guide-authoring.md   # 配布用PDF/HTMLの作成手順
│  ├─ validation/customer-guide.md # 顧客資料の照合・表示検証
│  ├─ getting-started.md            # 公開v1.2.0通常導入・初回実行
│  ├─ tutorials.md                  # 公開9例と候補17例
│  ├─ troubleshooting.md            # 症状別の確認と対処
│  ├─ vision.md
│  ├─ architecture.md
│  ├─ runtime.md
│  ├─ registry.md
│  ├─ connections.md                # v0.4の操作契約
│  ├─ task-manager.md                # v0.5基本・v0.6変更と中断再開
│  ├─ hybrid.md                      # v0.7の操作・配置・制約
│  ├─ core-api.md                    # 公開入口の意味と制限
│  ├─ api-reference.md               # 実装から生成する型・署名
│  ├─ module-contracts.md            # 6契約と接続開発
│  ├─ migration-v1.md                # v0.9からの移行
│  ├─ contracts-v1.json              # レビュー済み安定API基準
│  ├─ cognition.md                   # v1.3初期学習とMemory根拠
│  ├─ interaction.md                 # v1.4入力・訂正・CLI・DB移行
│  ├─ agency.md                     # v1.5判断・根拠・決定保存/照会
│  ├─ agency-execution.md            # v1.6活動循環とCore適用
│  ├─ persona.md                     # v1.7特性・外部修正・履歴
│  ├─ persona-agency.md              # v1.8人格特性と選択への反映
│  ├─ sleep.md                       # v1.9統合根拠/忘却・夢・人格案
│  ├─ validation/v1.9.md             # B09の確認状況
│  ├─ validation/v1.5.md             # B05の実装受入
│  ├─ validation/v1.6.md             # B06の実装受入
│  ├─ validation/v1.7.md             # B07の確認状況
│  ├─ validation/v1.8.md             # B08の確認状況
│  ├─ implementation-progress.md     # v1.10までの実施状況
│  ├─ validation/v1.4.md             # B04検証と未完了の受入
│  ├─ document.md                    # v1.2文書入力とMemory連携
│  ├─ memory.md                      # v1.1保存・取得と運用
│  ├─ validation/v1.3.md             # 開発候補のB03受入結果
│  ├─ validation/v1.2.md             # B02受入結果
│  ├─ validation/v1.1.md              # B01受入結果
│  ├─ validation/v1.0.md             # B00受入結果
│  ├─ validation/core-coverage.json  # 証拠対応の編集元
│  ├─ validation/core-coverage.md    # 64項目・既存受入の索引
│  ├─ validation/v0.9.md             # A09の公開前判定・公開後結果の参照先
│  ├─ validation/docs-onboarding.md  # D01〜D04・D09の検証
│  ├─ validation/docs-current.md     # 実装機能と資料の整合点検
│  ├─ roadmap.md
│  ├─ acceptance.md
│  ├─ validation/v0.2.md
│  ├─ validation/v0.3.md
│  ├─ validation/v0.4.md             # A04・配布・性能と制約
│  ├─ validation/v0.5.md             # A05・配布・制約
│  ├─ validation/v0.6.md             # A06・活動変更・中断再開
│  ├─ validation/v0.7.md             # A07・ハイブリッド実行
│  ├─ validation/v0.8.md             # A08・統合障害・負荷・配布と測定結果
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
│     ├─ 0019-v0.4-connections.md
│     ├─ 0020-v0.5-task-manager.md
│     ├─ 0021-v0.6-activity-changes.md
│     ├─ 0022-v0.7-v0.9-hybrid-and-completion.md
│     ├─ 0023-v0.7-implementation-contracts.md
│     ├─ 0024-v0.8-integration-validation.md
│     ├─ 0025-v0.9-core-completion.md
│     ├─ 0026-v1.0-core-connection-contracts.md
│     ├─ 0027-v1.1-memory.md
│     ├─ 0028-v1.2-document-adapter.md
│     ├─ 0029-v1.3-cognition-learning.md
│     ├─ 0030-customer-docs-as-primary.md
│     ├─ 0031-v1.4-text-web-and-correction.md
│     ├─ 0032-v1.5-agency-decisions.md
│     ├─ 0033-input-candidate-contract.md # 別件の入力前処理提案。未採用
│     ├─ 0034-v1.6-agency-execution.md
│     ├─ 0035-v1.7-persona.md
│     ├─ 0036-v1.8-persona-agency.md
│     └─ 0037-v1.9-sleep.md
├─ src/
│  └─ nymph_toolkit/
│     ├─ core/
│     ├─ contracts/                  # Core共通型とMemory/Cognition/Agency/Persona/Sleep/Adapter業務契約
│     ├─ adapters/document/          # ローカル文書入力とMemory連携
│     ├─ adapters/text_interaction/  # 観測・教師入力・訂正・照会
│     ├─ adapters/web/               # 許可originのHTTP文章取得
│     ├─ adapters/_interaction.py    # 新規入力Adapterの所有・接続補助
│     ├─ subsystems/memory/           # 同梱する最小Memory
│     ├─ subsystems/cognition/        # 明示区切り/ラベルの初期学習
│     ├─ subsystems/agency/           # 根拠付き判断・活動循環と専用履歴
│     ├─ subsystems/persona/          # 長期特性・外部差分・専用履歴
│     └─ subsystems/sleep/            # 統合根拠/減衰・夢・人格案と周期履歴
└─ tests/                            # subsystems/にMemory/Cognition/Agency/Persona/Sleepの単体・統合試験
   ├─ core/
   ├─ adapters/                     # Document単体・4配置・障害試験
   ├─ subsystems/
   └─ doubles/
```

R3の配置案を各段階の実装に合わせて具体化した。Runtimeは `core/runtime.py`、Registryは `core/registry.py`、複数対象の実行入口は `core/module_group.py`、接続・保存は `core/connections.py` と `core/storage.py`、活動管理は `core/task_manager.py`、履歴読出しは内部モジュール `core/_activity_history.py`、変更要求の仲裁は `core/_activity_commands.py`、開始・再開の共通待機列は `core/_activity_slots.py` に置く。ハイブリッド実行は `core/hybrid.py`、遠隔活動は `core/hybrid_tasks.py`、通信内部は `_wire.py`・`_rpc.py`・`_streams.py`、子入口は `_child.py`、機能側窓口は `_module_node.py`・`_hybrid_client.py`・`_remote_activity.py` に置く。追加共有型は `contracts/hybrid.py`。共有型は `contracts/registry.py`・`contracts/connections.py`・`contracts/activities.py` に置き、`contracts/__init__.py`から公開する。ダミーは `tests/doubles/`、検証は `tests/core/` に置く。

### Subsystem・Adapterを追加する際の配置案

Memory・Document・Cognitionは上記の場所へ同梱し、各ガイド・ADR 0027〜0029・版別validation・実行例を配置した。公開factoryは公開Contractsを利用し、Coreの履歴、Memoryの元記録、Cognitionの学習DBの所有を分ける。その他の同梱と別配布の例を以下に示す。将来の配置・名称は提案であり、個別の分割を決定したものではない。

| 扱い | ソースの配置例 | 配布設定・検証の配置例 |
|---|---|---|
| 初期配布物へ同梱するSubsystem | `src/nymph_toolkit/subsystems/<名称>/` | ルートの `pyproject.toml`、`tests/subsystems/` |
| 初期配布物へ同梱するAdapter | `src/nymph_toolkit/adapters/<名称>/` | ルートの `pyproject.toml`、`tests/adapters/` |
| 別配布にするSubsystem・Adapter | `packages/<配布ディレクトリ>/src/<import名>/` | 対象ディレクトリ内の `pyproject.toml`、`tests/` |

別配布の場合も同じ `nymph-toolkit` リポジトリで管理する。CoreとContractsは初期のルート配下を基準とし、分割対象ごとに依存関係、Core・Contractsの対応バージョン、公開import名、ビルド・検証手順を記録する。共有の設計・ADRは引き続き `docs/` と `docs/adr/` に置く。

依存ライブラリや対応OS、更新頻度、単独導入の必要性を基に分割を判断する。任意依存による同梱も比較対象とし、分割後のバージョンを同期するか独立させるかは後続ADRで決める。配布単位は実行プロセスと通信経路を決定しない。同梱・別配布のいずれも、実行配置はADR 0002、通信経路はADR 0015と後続判断に従う。

## 設計判断の現在の状態

R16でv0.4へ着手した。後続の公開型・接続制御・保存の実装判断は[ADR 0019](adr/0019-v0.4-connections.md)を参照する。R15時点の未実装という説明を現在の全体状況と混同せず、受入・公開の完了は個別に確認する。

R10・[ADR 0013](adr/0013-milestone-issue-workflow.md)により、コード変更前に対象バージョンのマイルストーン、親Issue、対応単位の子Issueを整備する。以下の設計判断は対象のIssueから追跡し、必要な判断を記録してから実装へ進む。具体的な運用は[issue-workflow.md](issue-workflow.md)を参照する。

| 判断 | 判断する時点の案 | 記録先 |
|---|---|---|
| Python対応版、配布パッケージの正式名称、ビルド・テストツール、Runtimeのライフサイクル | v0.2で採用済み | development、ADR 0014 |
| Subsystem・Adapterの同梱・分割対象、任意依存、公開import名、バージョン管理 | 各対象の実装・配布を設計する時点 | ADR 0009に関連付ける後続ADR |
| 登録ID、重複、必須依存・解除による利用不能の通知、スナップショット、ModuleGroup | v0.3で採用。稼働中実体着脱は延期 | ADR 0016 |
| Coreが許可する直接通信の採否 | R12で採用済み | ADR 0003の履歴とADR 0015 |
| 候補選定・保存、初回追加と確定済み接続先の固定、起動時・ヘルスチェック時の検証、連携エラー時の中断・申請 | R14の方針をR15/R16で具体化しv0.4に実装済み | ADR 0017〜0019 |
| 要求側選定、契約互換性、永続化、稼働通知、協調的中断・待機、ヘルス申請、履歴保存・救命措置 | R15の振る舞いをR16で具体化しv0.4に実装済み | ADR 0018・0019 |
| 公開API・型、接続識別と競合、通知・待機の競合、保存形式・設定値、救命の具体手順 | v0.4に採用・実装済み。v1.0の共通API基準も採用済み | ADR 0019・0026 |
| 時計、時刻・期間・経過時間・実行時間の意味、状態遷移、期間終了の意味 | v0.5・v0.6に採用・実装済み。到達通知後の判断はNymph | ADR 0004・0020・0021 |
| 開始時刻変更・期間変更・優先度・中断再開の詳細、競合・応答 | R18・ADR 0021に従って実装。最終受入・公開はv0.6検証記録を参照 | ADR 0004・0021 |
| IPC、配置間契約の共通範囲、ストリーム、切断・子終了、活動管理への適用 | R19で設計採用、R20・0023でv0.7を実装。API・制約はhybrid.md | ADR 0022・1〜53 |
| 保存対象・受付境界・結果保持・運用情報、自動再試行・復旧の範囲 | R19で採用。活動自動復元・子だけの再起動・自動再送・接続先切替は対象外 | ADR 0019〜0022・26・54〜57 |
| v0.7〜v0.9配分、配置4通り、障害・性能・長時間・配布、Core完成条件 | R19で設計採用、R22・ADR 0024でA08検証条件を具体化。A08はvalidation/v0.8、A09のR24監査はADR 0025・validation/v0.9 | ADR 0022・58〜64、acceptance |

未決項目は担当する段階で具体化する。決定記録には採用内容、理由、適用範囲と検証への影響を残す。

v1.0の共通Contract公開範囲・互換性はADR 0026、Memory/Document/Cognitionの初期業務契約はADR 0027〜0029で具体化した。Cognitionの区切り/概念ラベル付き入力はユーザー採用済み。Agency・Persona・その連携はADR 0032/0034〜0036、Sleepの初期統合/人格修正案はADR 0037で具体化した。後続の学習・意思決定方式、未実装Adapterの形式・権限、睡眠活動との循環、音声受信・ASRは追加の判断対象とする。roadmapとADR 0007〜0008に従い、必要な後続ADRへ記録する。

## R33：DocumentとMemoryの境界

`src/nymph_toolkit/adapters/document/`へ同梱し、`contracts/document.py`に宣言を置く。ModuleKind.ADAPTERでMemoryへの依存を宣言し、公開Contractsだけを参照する。ローカル文書読込と出典/hash作成をAdapter、commitと保存/取得をMemory、接続許可/実行管理をCoreが担当する。区分・ID・時刻・活動の選択は要求側に残す。

`docs/document.md`・ADR 0028・`docs/validation/v1.2.md`・`examples/document_demo.py`・`tests/adapters/`で仕様と証拠を追跡する。v1.2の単一パッケージへの追加であり、将来の独立配布を確定しない。

## R35：CognitionとMemoryの境界

Cognitionは`src/nymph_toolkit/subsystems/cognition/`、公開契約は`contracts/cognition.py`、ガイドは`docs/cognition.md`、判断はADR 0029、結果は`docs/validation/v1.3.md`、実行例は`examples/cognition_demo.py`、検証は`tests/subsystems/test_cognition*.py`に置く。学習の入力と実施を要求側、元記録の保存/取得をMemory、初期統計と根拠/専用保存をCognition、接続許可/実行管理をCoreが担当する。明示された区切り・ラベルの共起を、自律的な概念形成や文法の完成と扱わない。

## R37：対話・Web入力と訂正

[ADR 0031](adr/0031-v1.4-text-web-and-correction.md)に従い、Core既存APIを維持して業務契約3件を追加。TextはMemoryの原記録とCognitionの明示教師入力をつなぎ、WebはHTTP取得・本文抽出・出典保存を担う。Cognitionは専用DBの注釈と集計を訂正し、Memory原本を変更しない。入力の保存だけで学習や活動決定を始めない。構成・呼出図・配置・保存形式移行・取消/障害は[interaction](interaction.md)、全体の残作業は[進捗](implementation-progress.md)。docs/interaction.mdとvalidation/v1.4.md、examples/interaction_setup.py・text_interaction_demo.py・web_demo.py、tests/adapters/の単体・結合・CLI検証を追加した。

## R37：Agencyの意思決定と実行の境界

`src/nymph_toolkit/subsystems/agency/`（factory・判断モデル・専用保存）、`contracts/agency.py`（decisions/1）、`docs/agency.md`、ADR 0032、`validation/v1.5.md`、`examples/agency_demo.py`、`tests/subsystems/test_agency*.py`を追加した。単一配布に同梱する。Memory/Cognitionの公開契約で根拠を取得し、活動選択・時刻/期間/優先度/変更案をAgencyが決める。Coreの既存契約は維持する。

決定履歴と活動の実行履歴は別。決定の保存・照会は実行開始や変更適用の証拠にならない。v1.6で実行側の状態/版と結び、v1.5では4配置・両経路で判断と根拠・再起動照会を検証する。人格/Sleepは後続。

## R37のv1.6：Agencyが実行を判断しCoreが管理

`subsystems/agency/_execution.py`と任意execution_factoryが、観測/学習根拠/実行状態から決定して、公開CoreClientのTask操作へ適用する。Core内部をimportしない。`contracts/agency.py`の追加activities/1、`docs/agency-execution.md`、ADR 0034、`validation/v1.6.md`、`examples/agency_execution_demo.py`、`tests/subsystems/test_agency_execution.py`に実装/説明/検証を置く。

決定の保存、命令受付、適用完了、実行後処理の確認を分ける。実行結果を観測して次を判断するのはAgency。再起動はinactiveで、過去履歴を活動へ自動復元しない。接続固定・協調中断・Coreの64判断は維持する。

## v1.7 Personaの配置と責務

`src/nymph_toolkit/subsystems/persona/`に人格特性の保持・外部修正・保存を同梱し、`src/nymph_toolkit/contracts/persona.py`でtraits/1を宣言する。利用・検証は[Persona](persona.md)・[B07](validation/v1.7.md)、判断は[ADR 0035](adr/0035-v1.7-persona.md)。Coreは接続・ライフサイクルを管理するだけで、人格値や活動の価値を選ばない。初期値は初回のみ適用し、現在値と修正履歴を同一transactionで保存する。Agencyへの選択反映は後続のADR 0036で具体化した。

## v1.8 PersonaとAgencyの連携

[ADR 0036](adr/0036-v1.8-persona-agency.md)によりAgencyの任意設定でPersonaの公開traits/1を参照する。状態/学習根拠から得た候補得点を特性で補正し、取得した版・値・対応付けと基礎点・倍率を決定履歴へ保存する。Personaは保持/外部修正、Agencyは価値判断、Coreは実行管理を担当する。旧設定は形式1を維持し、有効時は新規DB形式2を使う。[利用と図解](persona-agency.md)・[B08](validation/v1.8.md)を参照。

## v1.9 Sleepの所有する統合状態

[ADR 0037](adr/0037-v1.9-sleep.md)により`contracts/sleep.py`と`subsystems/sleep/`を同梱する。Memory/注釈/Personaは公開契約で読み、専用SQLiteに周期と現在統合状態を保存する。忘却はこの状態への寄与だけで、原本/既存学習は保持する。現在夢と人格修正案も区別し、Sleep自身はPersonaを更新しない。Coreは価値判断を担当しない。[図解と使い方](sleep.md)・[B09](validation/v1.9.md)。
