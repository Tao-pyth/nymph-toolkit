# Architecture

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

ダミーの役割は、Nymphの決定を入力するもの、活動を実行して結果を観測できるもの、Adapterの装着を模擬するものとする案を用いる。Nymphの配置先や継承関係は未確定である。

## 実行配置と通信経路

ハイブリッド実行は確定方針であり、同一プロセスと別プロセスの配置を想定する。Python `asyncio` と軽量なメソッド呼び出しは方向性確定。Core経由の処理もメソッド呼び出しで構成できる。

通信経路の最後の正式採用はCore経由のみである。直接接続の緩和案は未採用。Connectionsの実装前にADR 0003へ判断を記録する。メソッド呼び出しという実装方法から直接接続の許可を推定しない。

配置間で通信契約を共通化するか、その共通範囲、IPC方式、シリアライズ方式、同期・非同期境界は要決定。別プロセス対応をV0.7で実装する配分は提案である。

## フォルダ構成

文書とGit設定は公開準備時に配置する。以下の `LICENSE` はライセンス決定後、`pyproject.toml`、`src/`、`tests/` は実装着手時に作成する予定である。

```text
nymph-toolkit/
├─ README.md
├─ .gitignore
├─ .gitattributes
├─ LICENSE
├─ CHANGELOG.md
├─ pyproject.toml
├─ docs/
│  ├─ README.md
│  ├─ NTK-Core-v0.1-Handoff-ja.md
│  ├─ architecture.md
│  ├─ roadmap.md
│  ├─ acceptance.md
│  ├─ development.md
│  ├─ release.md
│  └─ adr/
│     ├─ README.md
│     ├─ 0001-core-and-repository.md
│     ├─ 0002-execution-model.md
│     ├─ 0003-communication-routing.md
│     ├─ 0004-activity-authority.md
│     └─ 0005-initial-scope.md
├─ src/
│  └─ nymph_toolkit/
│     └─ core/
└─ tests/
   ├─ core/
   └─ doubles/
```

この配置はR3で指定された文書・開発配置案である。4責務は `core/` 内のモジュールとして始める案とし、クラス名と公開API名は実装時に決定する。ダミーは `tests/doubles/`、単体・結合・受入シナリオは `tests/core/` に置く案とする。

## 実装前の判断一覧

| 判断 | 判断する時点の案 | 記録先 |
|---|---|---|
| Python対応版、パッケージ・テストツール、Runtimeのライフサイクル | V0.2着手時 | developmentと後続ADR |
| 登録ID、重複、稼働中の着脱、解除時の状態 | V0.3着手時 | 後続ADR |
| Core経由維持・直接接続緩和、経路別の許可条件 | Connections実装前 | ADR 0003 |
| 呼び出し契約、同期・非同期境界、失敗通知 | V0.4着手時 | 後続ADR |
| 時計、時刻・期間の表現、状態遷移、期間終了の意味 | V0.5着手時 | ADR 0004に関連付ける後続ADR |
| 開始前・実行中の変更、停止・取消、競合と取り外し | V0.6着手時 | 後続ADR |
| IPC、配置間契約の共通範囲、切断時処理 | V0.7着手時 | ADR 0002に関連付ける後続ADR |
| 永続化、再試行、自動復旧の必要性と採否 | 必要な設計段階、遅くともV0.8の検証範囲確定前 | 後続ADR |

未決項目は担当する段階で具体化する。決定記録には採用内容、理由、適用範囲と検証への影響を残す。
