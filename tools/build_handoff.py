"""Regenerate the standalone Japanese handoff, or check its exact contents."""

# SPDX-License-Identifier: Apache-2.0
import argparse
from pathlib import Path
import posixpath
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/NTK-Core-v0.1-Handoff-ja.md"
HEADER = """# Nymph Toolkit（NTK）最終ビジョン・初期設計・開発ロードマップ・Codex引継ぎ書

初稿2026年11月19日 ｜ R1〜R15を収録 ｜ 統合リポジトリ `nymph-toolkit`

本書は個別Docs・ADRを全文収録した単一配布用文書である。Nymphは、経験から言葉と世界を学び、記憶を積み重ね、自ら考え、行動し、成長する人工人格を目指す。最終ビジョンは収録したProject Visionに従う。

GitHub公開をv0.1.0、合意したCore機能の完成をv0.9.0、接続契約整備をv1.0.0の目標とする。R11に伴うv0.2の実装判断はADR 0014に記録し、過去に確定していた方針と区別する。現在の実装・公開状況は収録したREADME・release・受入記録で確認する。

Nymphが活動を決定し、Coreが実行を管理する。R12・ADR 0015により、Coreが管理・許可した接続で直接通信を認める。Core経由も利用でき、具体的な許可範囲・API・解除時の動作は実装前に判断する。後続バージョンの名称・順序・機能配分と契約詳細は採用状態を確認して読む。

R14・ADR 0017の接続管理方針を、R15・ADR 0018で具体化した。Coreが契約に合致する候補・属性・稼働情報を返し、要求側が選定する。接続設定を永続保存し、稼働中の接続先固定・再審査省略を維持する。協調的中断、期限付き待機、個別のヘルス申請、期間別の履歴保存、保存失敗時のCore内蔵の救命措置を採用方針として記録する。容量不足には即時応答し、ヘルス確認中の待機と区別する。Connections未実装・A04未検証であり、API・保存形式・設定値などの未採用案を採用済み事項へ含めない。

R10により、コード変更はマイルストーン、親Issue、対応単位の子Issue登録の順に前提を整えてから行う。元会話の確認範囲と各指示の根拠はDocs索引に記録する。

本書にもApache-2.0を適用し、末尾にLICENSEの公式本文を収録する。第三者成果物と個体データの条件は別途扱う。ファイル名のv0.1は初稿の識別子であり、リポジトリ内の本文は更新する。公開済みRelease添付は各公開時点のスナップショットとして保持する。

"""


def sources():
    result = [
        "README.md", "CONTRIBUTING.md", "AGENTS.md", "docs/README.md",
        "docs/vision.md", "docs/architecture.md", "docs/runtime.md", "docs/registry.md", "docs/adr/README.md",
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
