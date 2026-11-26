"""Check reviewed source hashes and the current customer Markdown/PDF/HTML set."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
RECORD = "docs/customer-guide.sources.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_text(text):
    # Chromium's CJK fonts may extract Kangxi radicals for equivalent ideographs.
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def inputs(root):
    paths = [root / "pyproject.toml"]
    paths += list(root.glob("*.md"))
    paths += [p for p in (root / "docs").rglob("*.md")
              if "validation" not in p.relative_to(root / "docs").parts
              and p.name != "NTK-Core-v0.1-Handoff-ja.md"]
    for folder in ("src", "examples"):
        paths += [p for p in (root / folder).rglob("*")
                  if p.is_file() and p.suffix in {".py", ".mjs", ".json", ".yaml"}
                  and "node_modules" not in p.relative_to(root / folder).parts]
    paths += [root / "docs/contracts-v1.json"]
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(set(paths))}


def validate(root=ROOT):
    record = json.loads((root / RECORD).read_text(encoding="utf-8"))
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert record["schema"] == 1 and record["version"] == version, "Customer guide target version is stale"
    assert record["status"] in ("development", "released")
    assert re.fullmatch(r"\d+\.\d+\.\d+", record["published_version"])
    if record["status"] == "released":
        assert record["published_version"] == version
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["reviewed_on"])
    assert record["review_note"].strip(), "Record the content review before refreshing hashes"
    status = "開発候補" if record["status"] == "development" else "公開済み"
    heading = f"**Nymph Toolkit / 対象 v{version}（{status}） / 公開版 v{record['published_version']} / {record['reviewed_on']}**"
    assert heading in (root / "docs/customer-guide.md").read_text(encoding="utf-8"), "Customer cover metadata is stale"
    current = inputs(root)
    changed = sorted(p for p in current.keys() | record["sources"].keys() if current.get(p) != record["sources"].get(p))
    assert not changed, "Customer guide review required for: " + ", ".join(changed)
    return record


def artifacts(directory, root=ROOT, *, render_dir=None, require_clean=False):
    record = validate(root)
    stem = f"NTK-v{record['version']}-Customer-Guide-ja"
    manifest = json.loads((directory / (stem + ".json")).read_text(encoding="utf-8"))
    assert manifest["source_sha256"] == digest(root / "docs/customer-guide.md")
    assert manifest["review_sha256"] == digest(root / RECORD)
    assert manifest["version"] == record["version"] and manifest["status"] == record["status"]
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["reference"]), "Artifacts must refer to an immutable commit"
    if require_clean:
        assert manifest["working_tree_dirty"] is False, "Uncommitted preview is not a distributable artifact"
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        assert manifest["reference"] == head, "Artifacts do not refer to the checked-out commit"
        assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip(), "Checkout has uncommitted changes"
    generator = ("tools/customer-docs/build.mjs", "tools/customer-docs/print.css",
                 "tools/customer-docs/package.json", "tools/customer-docs/pnpm-lock.yaml")
    assert manifest["generator_inputs"] == {p: digest(root / p) for p in generator}, "Generator inputs changed"
    assert set(manifest["files"]) == {stem + ext for ext in (".md", ".pdf", ".html")}
    for name, expected in manifest["files"].items():
        assert digest(directory / name) == expected, f"Artifact missing or modified: {name}"
    assert (directory / (stem + ".md")).read_bytes() == (root / "docs/customer-guide.md").read_bytes()
    html = (directory / (stem + ".html")).read_text(encoding="utf-8")
    assert '<script' not in html.lower(), "Saved HTML must be self-contained"
    assert f'content="{manifest["source_sha256"]}"' in html
    assert f'content="{manifest["reference"]}"' in html
    from pypdf import PdfReader
    import pypdfium2
    pdf = PdfReader(directory / (stem + ".pdf"))
    assert len(pdf.pages) == manifest["pages"] == len(manifest["inspection"]["pages"])
    assert manifest["inspection"]["diagrams"] == manifest["diagrams"]
    sections = (root / "docs/customer-guide.md").read_text(encoding="utf-8").split("\n<!-- pagebreak -->\n")
    assert len(sections) == len(pdf.pages)
    if render_dir is not None:
        render_dir.mkdir(parents=True, exist_ok=True)
    with pypdfium2.PdfDocument(directory / (stem + ".pdf")) as rendered:
        assert len(rendered) == len(pdf.pages)
        for i, (page, section, measured) in enumerate(zip(pdf.pages, sections, manifest["inspection"]["pages"]), 1):
            assert measured["availableGap"] >= 10 and not measured["outside"]
            title = re.search(r"^#{1,2} (.+)$", section, re.M).group(1)
            assert abs(float(page.mediabox.width) - 595.28) < 2 and abs(float(page.mediabox.height) - 841.89) < 2
            rendered_page = rendered[i - 1]
            try:
                # PDFium preserves Chromium/Noto CJK punctuation; pypdf can
                # substitute U+2027 for U+30FB when decoding these font maps.
                text_page = rendered_page.get_textpage()
                try:
                    text = text_page.get_text_range()
                finally:
                    text_page.close()
                assert compact_text(title) in compact_text(text), f"PDF page {i} title missing: expected {title!r}, extracted {text[:400]!r}"
                assert len(text.strip()) > 80 and "\ufffd" not in text, f"PDF page {i} text is missing/corrupt"
                if render_dir is not None:
                    bitmap = rendered_page.render(scale=1.4)
                    try:
                        bitmap.to_pil().save(render_dir / f"page-{i:02}.png")
                    finally:
                        bitmap.close()
            finally:
                rendered_page.close()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="After reviewing content, refresh input hashes")
    parser.add_argument("--review-note")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    if args.write:
        if not args.review_note or not args.review_note.strip():
            parser.error("--write requires --review-note describing the content review")
        record = json.loads((ROOT / RECORD).read_text(encoding="utf-8"))
        record["sources"] = inputs(ROOT)
        record["review_note"] = args.review_note
        (ROOT / RECORD).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.render_dir and not args.artifacts:
        parser.error("--render-dir requires --artifacts")
    record = validate()
    if args.artifacts:
        result = artifacts(args.artifacts, render_dir=args.render_dir, require_clean=args.require_clean)
        print(f"PASS: customer Markdown/PDF/HTML v{record['version']}, {result['pages']} pages, {result['diagrams']} diagrams")
    else:
        print(f"PASS: customer guide v{record['version']} matches {len(record['sources'])} reviewed inputs")


if __name__ == "__main__":
    main()
