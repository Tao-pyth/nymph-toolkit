"""Compare the reviewed v1 public API baseline with the implementation."""

# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import difflib
import json
from pathlib import Path
import sys

# Works both as tools.check_contracts and as an isolated installed-package check.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_api import inventory

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/contracts-v1.json"
CORE_OWNED = {"ModuleContext", "CoreClient", "DirectLink", "StreamSender", "StreamReceiver", "PreparedConnection"}


def stable_surface(data):
    result = deepcopy(data)
    for name, entry in result["nymph_toolkit.core"].items():
        if name in CORE_OWNED:
            entry.pop("signature", None)
        if "bases" in entry:
            # Private implementation bases are not a supported import contract.
            entry["bases"] = [base for base in entry["bases"] if not base.startswith("_")]
    return result


def differences(baseline, current):
    expected = json.dumps(baseline["surface"], ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    actual = json.dumps(stable_surface(current), ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    return list(difflib.unified_diff(expected, actual, fromfile="reviewed v1", tofile="implementation", lineterm=""))


def main():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    if baseline["schema"] != 1 or baseline["api_version"] != "1.0.0":
        raise SystemExit("Unsupported contract baseline")
    diff = differences(baseline, inventory())
    if diff:
        print("\n".join(diff[:100]))
        raise SystemExit("Contract API changed: review compatibility and ADR before editing the baseline")
    print("PASS: v1 public contract baseline (behavior verified separately by B00 and regression tests)")


if __name__ == "__main__":
    main()
