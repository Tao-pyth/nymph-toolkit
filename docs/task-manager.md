# TaskManagerの操作契約と活動履歴

v0.5で採用したCore実装。[ADR 0020](adr/0020-v0.5-task-manager.md)のD1〜D4がユーザー回答、D5〜D8が実施指示に基づく実装判断である。実装と受入全体の完了は区別し、[検証記録](validation/v0.5.md)で現在の証拠と残作業を確認する。

v0.6は[ADR 0021](adr/0021-v0.6-activity-changes.md)に従い、同じ実行関数からの再開、累積実行時間、任意の実行枠、要求ID・版番号による変更を実装した。以下の基本操作は維持し、追加操作を後半に記載する。現在の受入・公開の証拠は[v0.6検証記録](validation/v0.6.md)を参照する。

v0.7では[HybridTaskManager](hybrid.md)が遠隔実行処理IDを使う入口を追加した。STARTING、実行側報告による状態確定、計時・後処理確認フラグとv0.7履歴は同資料に記載する。本書の既存ローカル入口とNymphの判断権限は維持する。

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

## v0.6の変更要求と結果

```python
from datetime import timedelta
from nymph_toolkit.contracts import ActivityChange

observed = manager.snapshot(key)
result = manager.change(
    key, ActivityChange(duration=timedelta(hours=3), priority=2),
    command_id="extend-1", expected_revision=observed.revision,
)
print(result.status, result.reason, result.snapshot.current_request)
```

`start_at / duration / priority`を一括検証して適用する。未指定は`UNCHANGED`、`start_at=None`は明示的な即時変更。期間は現在の予定開始から数えた合計期間であり、追加時間ではない。開始時刻を変えられるのは未開始だけ。過去時刻・状態不整合・古い版などの拒否は元の予定を維持する。型・値の不正は例外、形式の正しい要求の拒否は`rejected`と理由で返す。

`request`は初回入力、`current_request`は現在の実効入力で、どちらも不変。状態・実効値・通知フラグが変わると`revision`が進み、実効予定が変わると`scheduled_revision`も進む。短縮後の到達が過去なら直ちに通知して継続し、延長後は新しい予定で再通知する。同値・優先度だけの変更では予定版や通知をリセットしない。

新しい変更・中断・再開には観測した`expected_revision`と活動内で一意の`command_id`が必要。同じID・同じ内容・同じ期待版の再送は元の要求の最新結果を返し、二重適用しない。IDの内容衝突は元結果を保持して拒否する。`command_result(key, id)`で結果を照会し、`await wait_command(key, id)`で終端結果を待つ。`accepted`だけが未完了で、`applied / no_change / rejected / superseded / failed`は終端。待機の取消は要求を取り消さない。

`COMMAND_RESULT`通知は既存と同じ要求元別FIFOへ流れ、`notice.command`に不変の要求結果が入る。別IDによる進行中の同じ中断・再開への要求は同じ遷移を待つが、個別に結果を保持する。

## v0.6の中断・再開と時間

```python
async def execute(context):
    position = 0
    while True:
        await context.wait_for_control()
        # 実行側が共有資源を解放した安全な区切りで呼ぶ。
        if await context.checkpoint() is not None:
            break
        position += 1
    return {"position": position}

manager.submit(request, execute, supports_pause=True)
# Nymphが中断を決めた時点で、現在のsnapshot.revisionを使って要求する。
pause = manager.request_pause(key, command_id="pause-1",
                              expected_revision=manager.snapshot(key).revision)
paused = await manager.wait_command(key, "pause-1")
# 再開もNymphが明示する。再開待ちを経て同じexecuteの続きへ戻る。
resume = manager.request_resume(key, command_id="resume-1",
                                expected_revision=manager.snapshot(key).revision)
resumed = await manager.wait_command(key, "resume-1")
```

`RUNNING → PAUSING → PAUSED`と進み、実行側がcheckpointへ入るまで枠を保持する。`supports_pause=False`が既定で、非対応の要求は理由付きで拒否する。通常の中断に取消を使わない。`PAUSED → RESUME_PENDING → RUNNING`では実行枠・保存受付・要求元の条件を確認する。再開待ちへの中断要求は待機を撤回する。作業状態や共有資源の扱いは実行側が所有し、Coreは任意の処理を保存・復元しない。

`elapsed_seconds`は実開始から後処理完了まで、`execution_seconds`はそのうち中断完了から実再開までを除いた秒数。再開待ちも除外し、通常のI/O待ち・中断準備・終了後処理は含める。CPU時間ではない。中断中も予定到達は動かさず通知し、Nymphの指示を待つ。

終了要求は変更・中断・再開に優先し、未完了の要求へ`superseded`を返す。実行側の自然完了も中断完了とは扱わない。中断中の終了は通常の実行枠を待たず起こして後処理する。終了状態と終了時刻は後処理完了後に確定する。

## v0.6の優先度・実行枠・保存

`ActivityRequest.priority`はboolを除く整数で、既定0、大きい値を先にする。`TaskManager(..., max_running=None)`は上限なしで、正の整数を指定した場合だけ同時実行枠を制限する。予定到来済みの開始と明示再開を同じ待機列で扱い、同順位は待機に入った順。待機中の優先度変更では順番を維持し、開始延期で列から外れた場合は到来時に新しい順番を得る。

実行中を優先度だけで中断せず、Coreによる優先度生成や自動引上げは行わない。実行側が枠内で互いの開始を待つような依存は構成者が避ける。Connectionsの容量不足への即時応答を待機列に入れない。

保存救命中は新しい変更・再開を拒否する。受付済みの開始・再開は回復まで待ち、中断・終了や進行中の通知は記録する。接続中断は既存の要求元による終了・後処理・完了報告で処理し、活動の一時停止とは区別する。

履歴の外枠は`ntk.history.v1`を維持し、新しい観測は`activity_v06_state_changed / activity_v06_planned_end / activity_v06_command`で識別する。v0.5の過去履歴も読めるが、新しい計時値などを補完しない。旧v0.5読出しによる新形式の互換性は保証しない。再起動時の自動復元・再実行は行わない。

## 実行例と残る範囲

[実行例](../examples/task_manager_demo.py)は一時ディレクトリ内で二回起動し、通知後の継続→Nymphの終了要求→後処理→再起動時の履歴参照と明示登録を示す。

```powershell
.venv/Scripts/python.exe examples/task_manager_demo.py
.venv/Scripts/python.exe examples/activity_changes_demo.py
```

本書のv0.5/v0.6の同一プロセス入口に対し、後続v0.7では[ハイブリッド実行](hybrid.md)を追加した。本番Subsystem、稼働中の機能取り外し、プロセス消失後の中断状態の復元は含めない。実行側が終了要求やRuntimeの取消に協調しない場合、Coreは後処理完了を偽装しない。現在の活動観測値・通知は同一起動中に保持するため、大量の活動や未取得通知を蓄積し続ける運用には別途保持方針が必要である。

[v0.6実行例](../examples/activity_changes_demo.py)は開始の繰上げ、期間短縮・延長、優先度、有限枠での中断再開を通し、同じ処理の継続位置・後処理・再起動履歴・残存タスク0・未保存履歴0を確認する。
