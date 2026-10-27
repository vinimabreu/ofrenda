"""How much death, judgment and gendered wording the check catches, and how much good text it refuses:
the word lists alone, the second reading (``ofrenda.tone``) alone, and both.

    python scripts/measure_tone.py CLONE.git [...] --cache RAW/cache --heldout tests/heldout \\
        --heldout OTHER_DIR --clean OTHER_DIR/clean.txt --raw RAW --out measurements/tone.json

Run after ``scripts/measure.py``: it reads the facts and the passing answers of that run from
its cache. Every held-out sentence is put on a person with that person's real quotes, so it
goes through the whole check:

- lists: ``check_card`` on all the people whose answers passed (the word lists and every other
  rule);
- second reading: the tone question to the model, on a sample of those people (``--per-repo``
  per repository, the ones with the most lines), one call per sentence and person;
- both: refused by either, on the same sample.

Bad wording counts as caught when it is refused, for any reason and for its own reason. Good
wording (the clean set, and the real sentences that passed) counts as a false refusal when it
is refused. Counts go to ``--out``; every sentence with its verdicts goes to ``--raw``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ofrenda import model  # noqa: E402
from ofrenda.cards import Answer, Material, check_card  # noqa: E402
from ofrenda.tamper import read_heldout  # noqa: E402
from ofrenda.tone import read_tone  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from measure_seeds import passing_answers  # noqa: E402

TONE_REASONS = {"death": "as if the person died", "judgment": "judges the person", "gendered": "gender"}
JUDGE_FLAG = {"death": "death", "judgment": "judgment", "gendered": "gender"}


def fill(template: str, name: str) -> str:
    return template.replace("{name}", name)


def pct(a: int, b: int) -> float:
    return round(100 * a / b, 1) if b else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clones", nargs="+", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--heldout", type=Path, action="append", required=True,
                        help="a folder with death.txt, judgment.txt and gendered.txt; can be repeated")
    parser.add_argument("--clean", type=Path, action="append", default=[], help="a file of good sentences")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default=model.DEFAULT_MODEL)
    parser.add_argument("--per-repo", type=int, default=2)
    args = parser.parse_args()

    pairs: list[tuple[Answer, Material]] = []
    sample: list[tuple[Answer, Material]] = []
    for clone in args.clones:
        found = passing_answers(clone, args.cache / clone.name.removesuffix(".git"), args.model, 10)
        pairs += found
        sample += found[:args.per_repo]
    ask = model.asker(model=args.model)
    timings: list[float] = []
    raw: dict[str, Any] = {}

    def judge(sentence: str, name: str) -> tuple[tuple[str, ...], str]:
        started = time.perf_counter()
        verdict, _ = read_tone(ask, name, sentence)
        timings.append(time.perf_counter() - started)
        return verdict.flags, verdict.error

    def measure_set(label: str, templates: list[str], kind: str | None) -> dict[str, Any]:
        """``kind`` is the wording the set is about, or None for good sentences."""
        rows = []
        lists_any = lists_own = 0
        for template in templates:
            for answer, material in pairs:
                reason = check_card(Answer(fill(template, material.name), answer.quotes), material)
                lists_any += reason is not None
                lists_own += reason is not None and kind is not None and TONE_REASONS[kind] in reason
        s_lists = s_judge = s_judge_own = s_both = 0
        for template in templates:
            for answer, material in sample:
                sentence = fill(template, material.name)
                reason = check_card(Answer(sentence, answer.quotes), material)
                flags, error = judge(sentence, material.name)
                judged = bool(flags) or bool(error)
                s_lists += reason is not None
                s_judge += judged
                s_judge_own += kind is not None and JUDGE_FLAG[kind] in flags
                s_both += reason is not None or judged
                rows.append({"sentence": sentence, "lists": reason, "judge": list(flags), "judge_error": error})
        raw[label] = rows
        trials, sample_trials = len(templates) * len(pairs), len(templates) * len(sample)
        return {"sentences": len(templates), "lists_trials": trials, "lists_refused": lists_any,
                "lists_refused_pct": pct(lists_any, trials), "lists_refused_for_its_reason": lists_own,
                "sample_trials": sample_trials, "sample_lists_refused": s_lists,
                "sample_lists_refused_pct": pct(s_lists, sample_trials), "judge_refused": s_judge,
                "judge_refused_pct": pct(s_judge, sample_trials), "judge_flagged_its_own_kind": s_judge_own,
                "both_refused": s_both, "both_refused_pct": pct(s_both, sample_trials)}

    result: dict[str, Any] = {"model": args.model, "model_digest": model.digest(args.model),
                              "people_passing": len(pairs), "sample_people": len(sample), "sets": {}}
    for folder in args.heldout:
        for kind in ("death", "judgment", "gendered"):
            path = folder / f"{kind}.txt"
            if path.exists():
                label = f"{folder.name}/{kind}"
                result["sets"][label] = measure_set(label, read_heldout(path), kind)
                print(label, result["sets"][label], file=sys.stderr)
    for path in args.clean:
        label = f"{path.parent.name}/{path.stem}"
        result["sets"][label] = measure_set(label, read_heldout(path), None)
        print(label, result["sets"][label], file=sys.stderr)
    # the real sentences: every one that passed the check, read once with its own person
    real_refused = 0
    rows = []
    for answer, material in pairs:
        flags, error = judge(answer.text, material.name)
        real_refused += bool(flags) or bool(error)
        rows.append({"sentence": answer.text, "judge": list(flags), "judge_error": error})
    raw["real-cards"] = rows
    result["real_cards"] = {"sentences": len(pairs), "lists_refused": 0, "judge_refused": real_refused,
                            "judge_refused_pct": pct(real_refused, len(pairs))}
    result["judge_calls"] = len(timings)
    result["judge_seconds_median"] = round(statistics.median(timings), 3) if timings else None
    result["judge_seconds_mean"] = round(statistics.mean(timings), 3) if timings else None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    args.raw.mkdir(parents=True, exist_ok=True)
    (args.raw / "tone-readings.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    print("real cards refused by the second reading:", real_refused, "of", len(pairs), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
