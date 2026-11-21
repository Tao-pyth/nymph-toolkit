"""Check or regenerate the implementation inventory of explicit public exports."""

# SPDX-License-Identifier: Apache-2.0
import argparse
from dataclasses import fields, is_dataclass
from enum import Enum
import inspect
from pathlib import Path
import re
import types
import typing

import nymph_toolkit.core as core
import nymph_toolkit.contracts as contracts

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/api-reference.md"
MODULES = (core, contracts)


def stable(value):
    if value is contracts.UNCHANGED:
        return "UNCHANGED"
    return repr(value)


def annotation(value):
    # Python 3.12/3.13 render Optional[TypeVar] differently from 3.14+.
    # Preserve the contract while giving union annotations one spelling.
    if typing.get_origin(value) in (typing.Union, types.UnionType):
        return " | ".join("None" if part is type(None) else annotation(part)
                          for part in typing.get_args(value))
    return inspect.formatannotation(value)


class _Annotation:
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return annotation(self.value)


def signature(value):
    try:
        original = inspect.signature(value)
    except (ValueError, TypeError):
        return None
    parameters = [p if p.annotation is inspect.Parameter.empty
                  else p.replace(annotation=_Annotation(p.annotation))
                  for p in original.parameters.values()]
    returned = original.return_annotation
    if returned is not inspect.Signature.empty:
        returned = _Annotation(returned)
    sig = str(original.replace(parameters=parameters, return_annotation=returned))
    # UNCHANGED is an identity sentinel, whose address is not an API value.
    sig = re.sub(r"<object object at 0x[0-9a-fA-F]+>", "UNCHANGED", sig)
    return sig


def inventory():
    result = {}
    for module in MODULES:
        names = module.__all__
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate exports in {module.__name__}")
        exports = {}
        for name in sorted(names):
            value = getattr(module, name)  # missing export is a hard failure
            entry = {"kind": "constant", "value": stable(value)} if not inspect.isclass(value) else {}
            if inspect.isclass(value):
                entry["kind"] = "enum" if issubclass(value, Enum) else "class"
                entry["bases"] = [base.__name__ for base in value.__bases__]
                if issubclass(value, Enum):
                    entry["values"] = {key: member.value for key, member in value.__members__.items()}
                else:
                    entry["signature"] = signature(value)
                    if is_dataclass(value):
                        entry["fields"] = {f.name: annotation(f.type) for f in fields(value)}
                    members = {}
                    for base in reversed(value.__mro__):
                        if not base.__module__.startswith("nymph_toolkit."):
                            continue
                        for key, member in sorted(vars(base).items()):
                            if key.startswith("_") and key != "__call__":
                                continue
                            if isinstance(member, property):
                                members[key] = {"kind": "property", "signature": signature(member.fget)}
                            elif inspect.isfunction(member):
                                members[key] = {"kind": "async" if inspect.iscoroutinefunction(member) else "def",
                                                "signature": signature(member)}
                    entry["members"] = members
            exports[name] = entry
        result[module.__name__] = exports
    return result


def render():
    lines = [
        "# 公開APIの実装一覧", "",
        "この一覧は明示された公開import（core / contractsの__all__）を実装から生成する。",
        "引数、列挙値、データ型、継承したメソッド・プロパティの存在を照合するための資料であり、"
        "入力検証・返却値・所有期間・失敗時動作は[Core API](core-api.md)と各操作資料を併読する。",
        "型注釈がない入口から新しい型保証を推測しない。内部補助メソッドを含む実体の一覧は、"
        "全メソッドの安定保証やv1.0の接続契約採用を意味しない。直接構築しない窓口もCore APIで区別する。", "",
        "再生成：python tools/check_api.py --write。照合：python tools/check_api.py。", "",
    ]
    data = inventory()
    for module, exports in data.items():
        lines += [f"## {module}（{len(exports)}件）", ""]
        for name, entry in exports.items():
            lines += [f'<a id="{module.rsplit(".", 1)[-1]}-{name}"></a>', "", f"### {name}", ""]
            if entry["kind"] == "constant":
                lines += [f'値：`{entry["value"]}`。', ""]
                continue
            lines += [f'基底：{", ".join(entry["bases"])}。', "", "```text"]
            if entry["kind"] == "enum":
                lines += [f"{key} = {value!r}" for key, value in entry["values"].items()]
            else:
                if entry["signature"] is not None:
                    lines += [name + entry["signature"]]
                else:
                    lines += [name + "（構築署名はPython標準の基底例外に従う）"]
                for field, annotation in entry.get("fields", {}).items():
                    lines += [f"  {field}: {annotation}"]
                for member, info in entry["members"].items():
                    lines += [f'  {info["kind"]} {member}{info["signature"] or ""}']
            lines += ["```", ""]
    return "\n".join(lines).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate docs/api-reference.md")
    args = parser.parse_args()
    expected = render()
    if args.write:
        TARGET.write_bytes(expected)
    elif not TARGET.is_file() or TARGET.read_bytes() != expected:
        raise SystemExit("API inventory is stale: run python tools/check_api.py --write")
    data = inventory()
    print("PASS: public API inventory:", ", ".join(f"{k}={len(v)}" for k, v in data.items()))


if __name__ == "__main__":
    main()
