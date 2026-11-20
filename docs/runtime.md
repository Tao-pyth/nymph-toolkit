# v0.2 Runtimeの使い方

v0.2は、一つの実行入口を同一プロセスで起動・実行・停止する最小Runtimeである。仕様判断は[ADR 0014](adr/0014-v0.2-runtime.md)、環境構築と検証は[development](development.md)にある。Registry・Connections・TaskManager、別プロセス実行はまだ含まない。

## 実行例

インストール済みのPythonで[ダミー例](../examples/runtime_demo.py)を実行する。

```powershell
.venv/Scripts/python.exe examples/runtime_demo.py
```

正常時には次を表示する。

```json
{"state": "stopped", "result": "dummy-result", "events": ["start", "run", "stop"], "remaining_tasks": 0}
```

利用側はRuntimeServiceの三つの非同期メソッドを実装する。継承は必須ではなく、同じ契約を満たすオブジェクトを渡せる。

```python
import asyncio
from nymph_toolkit.core import Runtime

class Service:
    async def start(self):
        pass  # 初期化

    async def run(self):
        await asyncio.sleep(0)
        return "completed"

    async def stop(self):
        pass  # 部分初期化も考慮してリソースを解放

async def main():
    runtime = Runtime(Service())
    await runtime.start()
    try:
        print(await runtime.wait())
    finally:
        await runtime.stop()

asyncio.run(main())
```

イベントループは利用側が用意する。既存のasyncioアプリでは、そのループ内からstart・wait・stopをawaitする。Runtimeはループの作成や終了、活動内容の選択を行わない。

## 公開インターフェース

| import | 用途 |
|---|---|
| `nymph_toolkit.core.Runtime` | 一回のライフサイクルを管理する。start、wait、stopとstateを公開 |
| `nymph_toolkit.contracts.RuntimeService` | start・run・stopを定義する型契約 |
| `RuntimeState` | NEW / STARTING / RUNNING / STOPPING / STOPPED / FAILED |
| `RuntimeFailure`、`LifecycleFailure`、`LifecyclePhase` | 初期化・実行・後処理の失敗通知。後二者と例外はcontractsからimport |
| `RuntimeStateError` | 二重起動、別ループからの制御、自己待機などの不正な操作 |

waitはrunの結果を返す。停止要求によってrunがキャンセルされた場合はNoneである。自然終了と停止のどちらでも、初期化を開始していればstopを一度呼び出す。waitとstopは後処理まで待つ。インスタンスは再起動せず、次の実行には新しいRuntimeを作る。

開始・実行の失敗も後処理を経てFAILEDとなる。RuntimeFailure.failuresにはphaseと元例外が順に保持される。例えばrunとstopが両方失敗しても、runの原因は失われない。後からstopやwaitを再度呼んだ場合も失敗を通知する。タスク生成そのものの失敗は初期化失敗として通知し、サービスのフックは呼ばない。

## 停止とキャンセル

stopは実行中または初期化中の処理へキャンセルを要求する。後処理中の重複stopで後処理を再キャンセルしない。サービスが自分で作ったタスクや接続は、そのサービスのstopが終了させる。Runtimeは無関係な呼出側タスクを停止しない。

waitを待つ側がキャンセルされてもサービスは実行を続ける。startを待つ側がキャンセルされた場合は停止を要求する。stopを待つ側がキャンセルされても後処理は継続する。必要に応じて再びstopまたはwaitをawaitして、終了を確認する。

キャンセルに応答しないサービスは強制終了できない。待機の期限は呼出側でasyncio.timeoutを使って設定できるが、TimeoutErrorはRuntimeの停止完了を意味しない。ブロッキングI/OやCPU処理をそのままイベントループへ置かない。

## 適用範囲

RuntimeServiceはv0.2の実行入口であり、Subsystem・Adapterの登録や通信の契約全体ではない。APIは初期開発中であり、v1.0の公開契約へ向けて変更を判断する。活動の開始時刻・期間・優先度や価値判断をRuntimeへ追加しない。
