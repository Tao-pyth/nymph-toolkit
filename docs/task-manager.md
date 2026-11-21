# TaskManagerの操作契約と活動履歴

v0.5で採用したCore実装。[ADR 0020](adr/0020-v0.5-task-manager.md)のD1〜D4がユーザー回答、D5〜D8が実施指示に基づく実装判断である。実装と受入全体の完了は区別し、[検証記録](validation/v0.5.md)で現在の証拠と残作業を確認する。

v0.6の変更・中断再開・優先度は[ADR 0021](adr/0021-v0.6-activity-changes.md)で設計として採用した。以下の実装済みv0.5の操作と、v0.6で追加予定のAPIを混同しない。特に同じ実行関数からの再開、累積実行時間、任意の実行枠、要求ID・版番号による変更はまだ製品コードに含まれない。

## NymphとCoreの担当

Nymphが活動内容・時刻・期間と終了・継続を決める。Coreは要求を受け付け、時刻を監視し、渡された実行関数を所有して状態を記録する。活動名の「睡眠」「調査」から優先度や実行関数を選ばない。

22時開始・2時間の予定なら、実開始が22時10分でも翌0時に到達を通知する。Coreはその通知だけで終了・中断・延長しない。Nymphの終了指示は実行側へ渡し、安全な区切りでの返却・後処理を待つ。再起動時は以前の履歴をNymphへ渡し、自動再登録・再開は行わない。

## 組み立て

既存のModuleGroupとConnectionsを準備し、開始前に同じConnectionsを使うTaskManagerを装着する。次の値は説明用の設定例で、製品の既定値ではない。

```python
from nymph_toolkit.core import TaskManager

manager = TaskManager(connections, clock_check_interval=0.01)
group.attach_connections(connections)
group.attach_task_manager(manager)
```

機能の`start`と接続の起動時検証が終わってからTaskManagerが開始し、その後のNymph役の`run`から活動を登録する。TaskManager・FileStoreをSubsystemとして登録せず、FileStoreの開始・停止はConnectionsが所有する。TaskManagerを追加しない既存の構成も利用できる。

## 要求と実行

```python
from datetime import timedelta
from nymph_toolkit.contracts import ActivityKey, ActivityRequest

request = ActivityRequest(
    ActivityKey("nymph", "research"),
    content="資料を調査する",
    start_at=None,  # Nymphによる明示的な「今すぐ」の要求
    duration=timedelta(hours=2),
    parameters={"topic": "example"},
)

async def execute(context):
    # 自分の処理で他機能を使う場合は許可済みConnectionsを利用する。
    await context.wait_for_finish()
    # 実行側が安全な区切りで資源を解放してから返却する。
    return {"finished": True}

pending = manager.submit(request, execute)
```

明示した開始時刻にはタイムゾーン付き`datetime`を使う。CoreはUTCへ正規化し、受付時点ですでに過去なら`ActivityStartInPastError`で元の要求と観測時刻を返す。活動を登録せず、同じIDで開始時刻を再指定できる。受理後のキーは完了後も同じ起動中には再利用できない。`None`へ書き換えて勝手に即時開始させることはない。

期間は正の`timedelta`。開始前の待機を含む予定と、実際の開始・終了・実行中の経過秒を分ける。実行中の経過秒は単調時計で測り、I/O待ちと後処理を含む。CPU使用時間ではない。時刻補正に追随するため壁時計を設定間隔以内で再確認するが、時刻ぴったりの開始は保証しない。

入力パラメータと結果はJSON互換の不変データとしてコピーする。文字列キーの辞書、配列、文字列、有限数、真偽値、nullを使える。循環参照、非有限数、任意のPythonオブジェクトは受け付けない。実行関数そのものは現在のプロセスだけの呼出先で、履歴から復元・評価しない。

## 通知・終了・失敗

`next_notice(requester_id)`で要求元別の状態変化と予定時間到達をFIFOで取得する。到達通知は一つの予定につき一度で、完了した活動に後から発行しない。通知はConnectionsの中断通知と別に受け取る。

`request_finish(key)`は実行中ならFINISHINGにし、実行側の`finish_requested`と`wait_for_finish()`へ伝える。未開始なら実行せずSTOPPEDへ進む。`await wait(key)`は後処理完了後の観測値を返す。待機者の取消は活動を取り消さない。終了要求を繰り返しても実行側を重ねて取り消さない。

| 状態 | 意味 |
|---|---|
| PENDING | 受理済みで未開始。予定や保存受付の回復を待つ |
| RUNNING | 実行関数を開始した |
| FINISHING | 終了要求済みで、実行側の終了・後処理を待つ |
| COMPLETED | 実行関数が通常返却し、後処理が終わった |
| FAILED | 実行開始不能、不正な結果、未処理例外等を観測した |
| STOPPED | 明示終了やRuntime停止に伴う後処理が終わった |

`snapshot(key)`と`activities(requester_id=...)`は不変の現在観測値を返す。通常返却は業務上の成功をCoreが保証する意味ではなく、結果の解釈はNymphが行う。活動の例外は`ActivityFailure.exception`へ保持し、失敗した活動を自動再実行しない。TaskManager内部の基盤障害はRuntimeへ通知して停止する。

Connectionsの連携エラーでは、要求元機能が自身の活動へ終了要求を送り、必要な後処理の完了後にConnectionsへ中断完了を報告する。`reason=ActivityFinishReason.CONNECTION_INTERRUPTION`で原因を区別できる。TaskManagerは中断完了を勝手に報告せず、接続先を切り替えず、失敗した活動を再開しない。新しい活動を始める前に要求元の中断処理を完了させる。

Runtime全体の停止では既存の協調的取消に従い、所有する活動の後処理を待つ。機能runの後処理と活動停止を並行して進め、完了後に機能stop、最後に保存停止へ進む。Nymphの終了要求とRuntime停止は履歴で区別する。

## 再起動後の履歴

```python
history = await manager.history("nymph")
for issue in history.issues:
    print(issue.path, issue.line, issue.message)
for record in history.records:
    print(record.run_id, record.sequence, record.kind, record.data)
# Nymphが判断し、必要な場合だけ新しいActivityRequestを登録する。
```

主保存先と予備先の過去起動の活動履歴を読み、現在起動は除外する。型・形式とファイルとの対応を検証し、同じ起動ID・連番の同内容コピーは一件にする。内容が競合した記録は選択せず、問題として返す。異なる起動IDの並び順は実時間順を表さない。

不完全な末尾行、未知形式、読出し失敗等は`issues`へ返す。原本を変更せず、読み出せた保存済みの記録を返す。履歴の欠落や急な終了時の未保存分は復元できず、`issues`が空でも全履歴の完全性を保証しない。最後の状態がRUNNINGでも、それを現在の実行として復元しない。

通常の履歴バッファは上限なしで、新規受付を継続する。保存障害時は既存の救命手順に従って新規受付を停止する。履歴読出しの問題を保存容量不足と混同せず、読出しで退避・修復処理を行わない。

## 実行例と残る範囲

[実行例](../examples/task_manager_demo.py)は一時ディレクトリ内で二回起動し、通知後の継続→Nymphの終了要求→後処理→再起動時の履歴参照と明示登録を示す。

```powershell
.venv/Scripts/python.exe examples/task_manager_demo.py
```

活動の途中変更、期間延長後の再通知、優先度・専用実行枠、中断箇所からの再開、IPC、本番Subsystemはこの段階の実装に含めない。実行側が終了要求やRuntimeの取消に協調しない場合、Coreは後処理完了を偽装しない。現在の活動観測値・通知は同一起動中に保持するため、大量の活動や未取得通知を蓄積し続ける運用には別途保持方針が必要である。
