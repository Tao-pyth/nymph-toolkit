"""Validate adopted decisions and evidence references; this does not run product tests."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/validation/core-coverage.json"
TARGET = ROOT / "docs/validation/core-coverage.md"
ADR = "docs/adr/0022-v0.7-v0.9-hybrid-and-completion.md"
DOCUMENT_ONLY = {58, 61, 62, 63, 64}


def adopted_rows(root):
    result = {}
    for line in (root / ADR).read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 4 and cells[0].isdigit():
            number = int(cells[0])
            if number in result:
                raise ValueError(f"Duplicate ADR decision {number}")
            result[number] = cells[1:]
    if set(result) != set(range(1, 65)):
        raise ValueError("ADR must contain decisions 1..64 exactly once")
    return result


def test_ids(root):
    result = set()
    for path in (root / "tests").rglob("test_*.py"):
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test_"):
                        result.add(f"{module}.{node.name}.{member.name}")
    return result


def file_reference(root, reference):
    path = (root / reference).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or out-of-tree evidence: {reference}")


def validate(data, root=ROOT):
    if data.get("schema") != 1:
        raise ValueError("Unknown completion evidence schema")
    rows = data["decisions"]
    numbers = [row["number"] for row in rows]
    if numbers != list(range(1, 65)):
        raise ValueError("Evidence must list decisions 1..64 once in order")
    adopted = adopted_rows(root)
    known = test_ids(root)
    used = set()
    for row in rows:
        number = row["number"]
        if [row["topic"], row["decision"], row["acceptance"]] != adopted[number]:
            raise ValueError(f"Adopted decision {number} differs from its evidence record")
        if not row["tests"] and number not in DOCUMENT_ONLY:
            raise ValueError(f"No behavioral evidence for decision {number}")
        if len(row["tests"]) != len(set(row["tests"])) or not set(row["tests"]) <= known:
            raise ValueError(f"Invalid test references for decision {number}")
        used.update(row["tests"])
        for field in ("implementation", "documents"):
            if not row[field]:
                raise ValueError(f"Missing {field} for decision {number}")
            for reference in row[field]:
                file_reference(root, reference)
        if not row["note"].strip():
            raise ValueError(f"Missing qualification for decision {number}")
    baseline = data["baseline"]
    if [row["acceptance"] for row in baseline] != [f"A0{i}" for i in range(2, 9)]:
        raise ValueError("Baseline acceptance must cover A02..A08")
    for row in baseline:
        file_reference(root, row["document"])
        if not row["modules"]:
            raise ValueError(f"Missing baseline tests for {row['acceptance']}")
        for module in row["modules"]:
            matches = {test for test in known if test.startswith(module + ".")}
            if not matches:
                raise ValueError(f"Missing baseline module: {module}")
            used.update(matches)
    return used


def render(data):
    lines = [
        "# Core採用事項と検証証拠の対応", "",
        "この表は[ADR 0022](../adr/0022-v0.7-v0.9-hybrid-and-completion.md)の64項目と、"
        "既存A02〜A08の実装・試験を照合する索引である。1〜18は個別採用、19〜64は一括採用。"
        "実行結果と公開前後の判定は[v0.9検証記録](v0.9.md)に分ける。参照先の存在だけを合格としない。", "",
        "編集元は[core-coverage.json](core-coverage.json)。"
        "python tools/check_completion.py --writeで本表を再生成し、引数なしで採用文・番号・参照・本文の一致を検査する。"
        "テストIDの検査は静的な実在確認であり、実際の成功・skip・実行環境は別途テスト結果で確認する。", "",
        "## 既存機能の回帰", "",
        "| 受入 | 対象テストモジュール | 既存結果 |",
        "|---|---|---|",
    ]
    def link(path, label=None):
        return f"[{label or path}](../../{path})"
    for row in data["baseline"]:
        modules = "<br>".join(link(module.replace(".", "/") + ".py", module) for module in row["modules"])
        lines += [f"| {row['acceptance']} | {modules} | {link(row['document'])} |"]
    lines += ["", "## ADR 0022の64項目", "",
              "| 番号・項目 | 受入 | 実装・試験 | 資料・範囲 |", "|---|---|---|---|"]
    for row in data["decisions"]:
        sources = [link(path) for path in row["implementation"]]
        for test in row["tests"]:
            module, owner, method = test.rsplit(".", 2)
            sources += [link(module.replace(".", "/") + ".py", f"{owner}.{method}")]
        docs = [link(path) for path in row["documents"]] + [row["note"]]
        lines += [f"| {row['number']} {row['topic']} | {row['acceptance']} | {'<br>'.join(sources)} | {'<br>'.join(docs)} |"]
    lines += ["", "v1.xの案、本番Subsystem/Adapter、分散実行や複製・移植・伝播は本表の完成対象に含めない。", ""]
    return "\n".join(lines).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    used = validate(data)
    expected = render(data)
    if args.write:
        TARGET.write_bytes(expected)
    elif not TARGET.is_file() or TARGET.read_bytes() != expected:
        raise SystemExit("Completion evidence table is stale: run python tools/check_completion.py --write")
    print(f"PASS: 64 adopted decisions, 7 baseline groups, {len(used)} referenced tests (execution checked separately)")


if __name__ == "__main__":
    main()
