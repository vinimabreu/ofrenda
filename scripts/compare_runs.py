"""Did two cold runs write the same cards? Compares the cold JSON of two scripts/measure.py runs.

    python scripts/compare_runs.py RAW_A RAW_B --out measurements/determinism.json

Only counts go to ``--out``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def cards(path: Path) -> list[tuple[str, list[str], str]]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return [(c["text"], [q["text"] for q in c["quotes"]], c["source"]) for c in data["cards"]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result: dict[str, dict[str, int]] = {}
    for cold in sorted(args.first.glob("*-cold.json")):
        a, b = cards(cold), cards(args.second / cold.name)
        same = sum(1 for x, y in zip(a, b, strict=True) if x == y)
        result[cold.name.removesuffix("-cold.json")] = {"cards": len(a), "identical": same}
    args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
