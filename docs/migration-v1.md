# v0.9からv1.0候補への移行

R29で「必要な破壊的API整理も今回に含める」と明示されたため、[ADR 0026](adr/0026-v1.0-core-connection-contracts.md)で以下を具体化した。既存の通信・活動動作を変える変更ではない。公開v0.9.0のタグ・添付は維持し、本書は開発中の1.0.0候補に対応する。

| v0.9で利用していたもの | v1.0での扱い・移行先 | 理由 |
|---|---|---|
| CoreClient.request | 公開APIから除外。candidates/bind/prepare/invoke/publish_usage/health_check/next_notice/acknowledge_interruption/submit_remote/activityを使う | 内部メッセージの任意送信を安定APIにしない |
| ModuleContext.check_stream_capacity / reserve_stream / own_sender / reject | 公開APIから除外。DirectLink.open_streamと返されたstreamの公開操作を使う | 予約・所有・内部要求の拒否はCore管理。機能側で資源台帳を操作しない |
| start完了後のprovide / provide_stream / provide_executor | ProtocolError。factoryまたはasync start内へ移す | 宣言と実体の対応を起動時に確定し、稼働中の構成固定を守る |
| Core側の具象型を機能の型注釈としてimport | ContractsのModuleContextProtocol等に置き換え可能 | Coreと独立して機能の接続窓口を記述できる。具象型の公開export自体は保持 |

内部名への呼び替えは移行方法ではない。管理目的の要求は名付きAPIに移し、独自の業務メッセージはContractSpecの操作として宣言する。具象窓口を直接構築せず、factoryのcontext、prepare、open_streamから取得する。

事前検証関数は追加機能。従来の有効なregister_module入力を変更する必要はない。非ModuleSpecのような不正入力は明確なTypeErrorとなる。ModuleFactoryはサービスまたはAwaitableを許容する。ローカルSYNC契約をHybridへ移す場合はASYNC/JSON制約に合わせた機能設計が必要であり、暗黙には変換しない。

移行時は[6契約](module-contracts.md)、[API一覧](api-reference.md)、[B00結果](validation/v1.0.md)を照合し、通常wheelを用いた契約テストを実行する。採用64項目、要求側による選定、確定先の固定、ヘルス・保存・活動の責務分離は維持する。1.x公開後の破壊的変更はmajorを含む互換性判断が必要であり、奇数/偶数minorの開発案で上書きしない。
