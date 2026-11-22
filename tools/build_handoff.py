"""Regenerate the standalone Japanese handoff, or check its exact contents."""

# SPDX-License-Identifier: Apache-2.0
import argparse
from pathlib import Path
import posixpath
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/NTK-Core-v0.1-Handoff-ja.md"
HEADER = """# Nymph Toolkit（NTK）最終ビジョン・初期設計・開発ロードマップ・Codex引継ぎ書

初稿2026年11月19日 ｜ R1〜R28を収録 ｜ 統合リポジトリ `nymph-toolkit`

本書は個別Docs・ADRを全文収録した単一配布用文書である。Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指す。最終ビジョンは収録したProject Visionに従う。

GitHub公開をv0.1.0、合意したCore機能の完成をv0.9.0、接続契約整備をv1.0.0の目標とする。R11に伴うv0.2の実装判断はADR 0014に記録し、過去に確定していた方針と区別する。現在の実装・公開状況は収録したREADME・release・受入記録で確認する。

Nymphが活動を決定し、Coreが実行を管理する。R12・ADR 0015により、Coreが管理・許可した接続で直接通信を認める。Core経由も利用でき、具体的な許可範囲・API・解除時の動作は実装前に判断する。後続バージョンの名称・順序・機能配分と契約詳細は採用状態を確認して読む。

R14・ADR 0017の接続管理方針を、R15・ADR 0018で具体化した。Coreが契約に合致する候補・属性・稼働情報を返し、要求側が選定する。接続設定を永続保存し、稼働中の接続先固定・再審査省略を維持する。協調的中断、期限付き待機、個別のヘルス申請、期間別の履歴保存、保存失敗時のCore内蔵の救命措置を採用方針として記録する。容量不足には即時応答し、ヘルス確認中の待機と区別する。R15反映時点ではConnections未実装・A04未検証であり、API・保存形式・設定値などの未採用案を採用済み事項へ含めなかった。後続の実装判断と現在の進捗はR16・ADR 0019を参照する。

R10により、コード変更はマイルストーン、親Issue、対応単位の子Issue登録の順に前提を整えてから行う。元会話の確認範囲と各指示の根拠はDocs索引に記録する。

R16でv0.4を実装し、ADR 0019で公開契約・状態・保存等の判断を記録した。要求元＋契約ID・版につき1接続とする固定単位、通常バッファの上限なし・新規受付継続はユーザー回答で採用した。保存エラー時の受付停止・救命は維持する。実装・A04・性能・配布の証拠と、最終公開の状態は個別資料で確認する。

R17でv0.5に着手し、ADR 0020へ判断を記録した。予定時間到達は通知して継続し、終了は安全な区切りを待つ。過去の開始時刻は返却し、再起動時の再登録・再開はNymphが判断する。D1〜D4のユーザー回答とD5〜D8の実装判断、実装・A05・公開の進捗を分けて記録する。

本書にもApache-2.0を適用し、末尾にLICENSEの公式本文を収録する。第三者成果物と個体データの条件は別途扱う。ファイル名のv0.1は初稿の識別子であり、リポジトリ内の本文は更新する。公開済みRelease添付は各公開時点のスナップショットとして保持する。

R18で、開始時刻変更・期間変更・優先度・中断再開の全4項目をv0.6の対象として採用した。ADR 0021のD1・D2へユーザーの範囲採用と個別回答を記録し、残事項を決める委任に基づくCodexの設計判断をD3〜D10へ分けた。子Issue #53〜#59をコード変更前に登録し、振る舞い・API・A06条件に従って実装した。実装、最終受入、配布・CI、公開後の取得確認の結果を個別に記録する。

R19でv0.9までの64項目をADR 0022へ採用記録した。1〜18は一問一答の個別回答、19〜64は一覧の推奨設定に対する明示一括採用である。同一PCの子プロセス管理、ループバックTCP、許可済み直接通信、連続ストリーム、活動管理、保存、受入・完成条件とv0.7〜v0.9の配分を設計採用した。A07〜A09へ全項目を対応付け、設計子Issue #60で資料を同期する。R19時点では製品コードは未実装だった。R20でv0.7を実装し、A07の結果を検証記録へ分離した。R20時点でA08・A09は未完了だった。具体的なAPI・形式・設定はADR 0023に記録する。v1.xの配分案と公開済みのタグ・添付は変更しない。

R20で資料をGitHub mainへ反映し、v0.7の実装に着手する。子Issue #61〜#68を先に登録し、ADR 0023に具体的な契約を記録した。実装・A07・配布・CIの結果は各子Issueと検証記録で追跡し、R20時点の作業を新規Release作成と区別する。

R21でPR #69のレビュー、問題解消後のマージ、v0.7.0公開が指示された。#70・#71をコード変更前に登録し、境界不具合の修正・回帰確認、最終CI・タグ・Release・4配布物・匿名取得を追跡する。最終SHAと公開後の結果は#71へ記録する。

R22でv0.8の統合・障害・負荷検証を実施する。親#8・マイルストーンv0.8.0に#72〜#77を先に登録し、検出した管理通信の結果解放不具合を#78で修正した。ADR 0024に試験・測定・30分の継続負荷とCIの条件を記録する。採用済み64項目を維持し、A08の結果は検証記録へ分離する。新規Release作成とA09の完成判定は別段階である。

R23でPR #79のレビュー、問題がなければマージとv0.8.0公開まで進めることが指示された。公開#81を親#8・同じマイルストーンへ先に登録し、公開状態の文書・最終CI・マージ・タグ・Release・4添付・匿名取得を追跡する。製品コードに追加修正が必要な問題は見つからず、関連42テストを再確認した。公開対象SHAと公開後の結果は#81・Releaseへ記録し、30分測定と後続修正の検証範囲を維持する。

R24でv0.9のCore機能完成に向けた実装・検証・資料整備が指示された。親#9・同じマイルストーンへ#82〜#85を先に登録し、ADR 0025で64項目と既存受入の証拠照合、公開APIの意味と生成一覧、新しい環境での配布検証を具体化する。実装・受入の結果と、A09-04のタグ・Release・公開後照合は分けて記録する。採用64項目とNymph/Core境界を維持し、v1.0の接続契約整備を前倒ししない。

R25でPR #86のレビュー・問題解消後のマージ・v0.9.0公開・A09-04完了後の親#9とマイルストーン終了が指示された。公開#88、停止競合の修正#89を各変更前に登録し、最終CI・マージ・タグ・4添付の匿名取得を追跡する。公開後結果は#88とReleaseへ記録し、公開済みスナップショットを差し替えない。

R26でv0.9.0利用者向けの入口・導入・6実行例・トラブルシューティングと引継ぎ書同期が指示された。親#90・子#91/#92を生成ツール変更前に登録し、3つの利用ガイドを全文収録する。v0.9.0の公開は完了済みであり、公開後の文書改善を未リリースの変更として記録する。製品仕様・API・版と過去の公開物は維持する。

R27で導入担当者・開発担当者の両方に向けた契約・利用の図解資料が指示された。親#90を拡張し、本文#95と任意のPDF/HTML生成・同期#96を変更前に登録した。現行v0.9.0の説明と開発者向け付録、作成手順・検証記録を全文収録する。製品設計の新たな採用はなく、公開済みタグ・添付を維持する。

R28で既知課題#94のWindows終了時エラーの調査・修正・回帰検証が指示された。親#10・v1.0.0配下で範囲・完了条件・内部修正判断をコード変更前に記録し、NTK所有TCPの解放を妨げる終了時resetへ対処する。制御再現と自然発生の確認範囲は検証記録へ分け、公開API・採用64項目・版と公開済み配布物は維持する。

"""


def sources():
    result = [
        "README.md", "CONTRIBUTING.md", "AGENTS.md", "docs/README.md",
        "docs/customer-guide.md", "docs/customer-guide-authoring.md",
        "docs/getting-started.md", "docs/tutorials.md", "docs/troubleshooting.md",
        "docs/vision.md", "docs/architecture.md", "docs/runtime.md", "docs/registry.md",
        "docs/connections.md", "docs/task-manager.md", "docs/hybrid.md",
        "docs/core-api.md", "docs/api-reference.md", "docs/adr/README.md",
    ]
    result += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "docs/adr").glob("[0-9]*.md"))]
    result += ["docs/roadmap.md", "docs/acceptance.md"]
    result += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "docs/validation").glob("*.md"))]
    result += ["docs/development.md", "docs/issue-workflow.md", "docs/release.md", "CHANGELOG.md", "LICENSE"]
    return result


def convert(source):
    raw = (ROOT / source).read_text(encoding="utf-8")
    if source == "LICENSE":
        return "## Apache License 2.0（原文）\n\n```text\n" + raw + "```\n"
    lines, in_fence = [], False
    for line in raw.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            if re.match(r"^#{1,5} ", line):
                line = "#" + line
            def replace_link(match):
                label, target = match.groups()
                if "://" in target or target.startswith("#"):
                    return match.group(0)
                path = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
                return label + "（`" + path + "`）"
            line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, line)
        lines.append(line)
    if in_fence:
        raise ValueError(f"Unclosed code fence: {source}")
    return "\n".join(lines).strip() + "\n"


def render():
    documents = sources()
    content = HEADER + "## 収録文書\n\n"
    for index, source in enumerate(documents, 1):
        title = "Apache License 2.0（原文）" if source == "LICENSE" else (ROOT / source).read_text(encoding="utf-8").splitlines()[0][2:]
        content += f"{index}. [{title}](#section-{index})\n"
    for index, source in enumerate(documents, 1):
        content += f'\n---\n\n<a id="section-{index}"></a>\n\n収録元 `{source}`\n\n{convert(source)}'
    return content.encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if TARGET.read_bytes() != expected:
            raise SystemExit("Handoff is stale: run python tools/build_handoff.py")
    else:
        TARGET.write_bytes(expected)
    print(f"PASS: handoff matches {len(sources())} complete source documents")


if __name__ == "__main__":
    main()
