"""How many broken answers ``check_card`` lets through, on answers the real model gave.

    python scripts/measure_seeds.py CLONE.git [...] --cache RAW_DIR/cache --raw RAW_DIR --out measurements/seeds.json

Run after ``scripts/measure.py``: it reads the facts and the model's replies from
that run's cache (no model call here), keeps every answer that passed the check,
breaks each one in every way ``ofrenda.tamper`` knows, and counts how many of the
broken answers still pass. The target is zero. Seeds that got through, if any, go
to RAW_DIR (they hold real names); ``--out`` gets counts only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ofrenda.cards import (Answer, Material, ReplyCache, check_card, material_for, parse_answer,  # noqa: E402
                           prompt_for, reply_key, retry_prompt)
from ofrenda.gitread import Git  # noqa: E402
from ofrenda.ledger import read_ledger  # noqa: E402
from ofrenda.tamper import measure  # noqa: E402


def passing_answers(clone: Path, cache: Path, model: str, top: int) -> list[tuple[Answer, Material]]:
    with Git(clone) as git:
        ledger = read_ledger(git, cache_dir=cache)
    if not ledger.cached:
        raise SystemExit(f"{clone}: no cached facts in {cache}; run scripts/measure.py first")
    replies = ReplyCache(cache, model)
    pairs = []
    for person in ledger.ghosts(730)[:top]:
        material = material_for(ledger, person)
        prompt = prompt_for(material)
        first = replies.get(reply_key(model, ledger.commit, person.key, prompt))
        if first is None:
            continue
        answer = parse_answer(first)
        reason = check_card(answer, material)
        if reason is not None:
            second = replies.get(reply_key(model, ledger.commit, person.key, retry_prompt(prompt, reason)))
            answer = parse_answer(second or "")
            if check_card(answer, material) is not None:
                continue
        pairs.append((answer, material))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clones", nargs="+", type=Path)
    parser.add_argument("--cache", type=Path, required=True, help="the cache folder scripts/measure.py used")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    pairs: list[tuple[Answer, Material]] = []
    for clone in args.clones:
        pairs += passing_answers(clone, args.cache / clone.name.removesuffix(".git"), args.model, args.top)
    report = measure(pairs)
    data = {"model": args.model, "answers": report.answers, "seeds": report.seeds, "passed_the_check": report.passed,
            "by_kind": {kind: {"seeds": n, "passed": p} for kind, (n, p) in sorted(report.by_kind.items())}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    args.raw.mkdir(parents=True, exist_ok=True)
    (args.raw / "seed-leaks.json").write_text(json.dumps(report.leaks, indent=1, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    print(f"answers {report.answers}, seeds {report.seeds}, passed the check {report.passed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
