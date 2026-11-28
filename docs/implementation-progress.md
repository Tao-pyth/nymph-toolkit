# v1.10.0までの実装・検証の進捗

R37（2026年11月24日）の目標は、既存ロードマップに沿ってv1.10.0まで実装と検証を反復すること。途中版の完成を全体の達成としない。各段階の具体値/APIは実装前にADRへ記録する。Nymph/Core境界と研究方針を維持し、マージ/公開済みと開発候補を区別する。

| 段階 | 実施・確認する範囲 | 現在の証拠・残作業 |
|---|---|---|
| 基点v1.3 | Cognition/Memory・顧客主要Docs | PR #123 / 24f5917、385テスト・PR CI 9ジョブ成功、未マージ |
| v1.4 | Text Interaction・Web取込・学習訂正 | 親#14、子#126〜#130、ADR 0031。訂正・Text/Web・CLI・12例、Windows全411テスト・通常配布を確認。27ページ/16図の顧客資料を確認。6ace316 / PR #131、push/PR CI全成功、Linux顧客27ページ/16図の取得・全ページ照合済み。未マージ |
| v1.5 | Agencyの活動計画・意思決定 | 親#15・子#132〜#136・ADR 0032。PR #137 / 30f2639、432テスト/通常配布/13例、9ジョブCI成功。顧客28ページ/17図の全表示・artifact照合済み。未マージ |
| v1.6 | Agency/TaskManagerの実行・変更・状態把握 | 子#138〜#142・ADR 0034。PR #143 / d0f22eb、全450テスト/通常配布/14例・9ジョブCI成功。顧客29ページ/18図をWindows/Linuxで全表示・照合済み。未マージ |
| v1.7 | Personaの保持・参照・外部更新 | 親#17・子#144〜#148/#150・ADR 0035。PR #149 / 2acecef、全469件/通常配布/15例・9ジョブCI成功。顧客30ページ/19図をWindows/Linuxで全表示・照合済み。未マージ |
| v1.8 | Persona/Agencyの選択への反映 | 親#18・子#151〜#155・ADR 0036。PR #156 / 9d690ea、全485件/通常配布/16例・9ジョブCI成功。顧客32ページ/20図をWindows/Linuxで全表示・照合済み。未マージ |
| v1.9 | Sleepの経験統合・忘却・夢・人格修正 | 親#19・子#157〜#161・ADR 0037。全506回帰/通常配布・17例、PR #162 / 315b3ffのCI全9件成功。7c5f494ではWindows3.13の追加診断20反復80ケース成功、顧客33ページ/21図をWindows/Linuxで照合。元のCognition終了確認失敗は#169で原因未特定。最新CIは[検証記録](validation/v1.9.md)で追跡し、再成功だけで最終受入完了としない |
| v1.10 | 睡眠循環・Discord音声受信/ASR/音響特徴 | 親#20・子#163〜#168/#171/#172・ADR 0038、Draft PR #170/#173。721bcdd・9a779c0・21cc034の全560件/通常配布・8環境・音声依存2環境・顧客Docs CI成功。顧客36ページ/23図をWindows/Linuxで照合。11月28日の利用者ログで実受信/通常停止と、2件受信後の参加者変更停止・停止後観測0件・Bot退出を確認。**Discord Bot確認は[ADR 0040](adr/0040-discord-bot-acceptance.md)によりクリア、追加実機確認は不要**。先行#169と資料更新を含む全体の最終確認は別途残る。[要求別の証拠と残作業](validation/v1.10.md) |

各段階で正常系だけでなく失敗・取消・停止・保存/再起動・契約互換性を確認する。顧客Markdown/PDF/HTMLと引継ぎ書も同時に更新する。テストや代替入力だけを、外部サービスで未確認の動作の証明に使わない。

v1.10の追加子[#172](https://github.com/Tao-pyth/nymph-toolkit/issues/172)で、実音声確認の補助ツールと[ケース別手順](voice.md#voice-live-acceptance)を整備した。ADR 0040以降は任意の診断用とし、利用者への追加試験依頼は不要。721bcddの[実装検証](https://github.com/Tao-pyth/nymph-toolkit/issues/172#issuecomment-7223476441)と9a779c0の[文書更新後CI](https://github.com/Tao-pyth/nymph-toolkit/issues/172#issuecomment-7225680762)を区別する。退出停止は観測0件の実行と、後続の2件受信した実行を別々に記録した。現在利用中の受信環境と未採用ADR 0039の変更を保護するため、cf9e39dを基点とする隔離checkoutで作業する。

## v1.11・v1.12の候補

v1.11の入力候補は親[#174](https://github.com/Tao-pyth/nymph-toolkit/issues/174)、契約実装#177、B11・配布・主要Docsは[#178](https://github.com/Tao-pyth/nymph-toolkit/issues/178)で追跡する。v1.12の診断は親[#175](https://github.com/Tao-pyth/nymph-toolkit/issues/175)で追跡する。標準は各版の公開後確認で発効する。
