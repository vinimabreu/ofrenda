"""Turn the measurement JSON files into the Markdown tables in measurements/ and the README.

    python scripts/summarize.py measurements/2026-10-26 > measurements/2026-10-26-summary.md

Reads PREFIX-blame-options.json, PREFIX-gemma4-12b-cards.json and PREFIX-gemma4-12b-seeds.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def blame_tables(data: dict[str, Any]) -> list[str]:
    out = [f"Blame over every kept file at HEAD, median of {data['repeats']} runs with {data['default_jobs']} "
           f"parallel jobs on a machine with {data['cpu_count']} CPUs, and one run with a single job. "
           "\"Other person\" counts the lines that the option gives to someone other than plain `git blame` does.",
           ""]
    out += ["| repository | commits | files | lines | option | seconds | one job | lines to another person | "
            "people who moved on |", "|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for repo in data["repos"]:
        first = True
        for label, v in repo["variants"].items():
            lead = (f"| {repo['repo']} | {repo['commits_reachable']:,} | {repo['files_kept']} | {v['lines']:,} "
                    if first else "| | | | ")
            other = v.get("lines_to_another_person_vs_plain")
            moved = "" if other is None else f"{other:,} ({pct(other, v['lines'])})"
            out.append(f"{lead}| {label} | {v['seconds_median']:.2f} | {v['seconds_one_job']:.2f} | "
                       f"{moved} | {v['moved_on_730']} |")
            first = False
    return out


def cards_tables(data: dict[str, Any]) -> list[str]:
    out = [f"Model {data['model']} (digest {str(data['model_digest'])[:12]}), top {data['top']} people per "
           f"repository, ofrenda {data['ofrenda']} (code {data['code']}), Python {data['python']}.", ""]
    out += ["| repository | lines read | people with lines | moved on | cards | first try | after retry | "
            "from git alone | quotes checked |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in data["repos"]:
        out.append(f"| {r['repo']} | {r['lines_read']:,} | {r['people_with_lines']} | {r['moved_on_730_days']} | "
                   f"{r['cards']} | {r['first_try']} | {r['after_retry']} | {r['fallback']} | "
                   f"{r['quotes_verified']} |")
    t = data["totals"]
    out.append(f"| total | | | | {t['cards']} | {t['first_try']} | {t['after_retry']} | {t['fallback']} | "
               f"{t['quotes_verified']} |")
    out += ["", "| repository | blame | model calls | model time | per call | prompt (median chars) | first run | "
            "second run | no model | second run identical |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in data["repos"]:
        out.append(f"| {r['repo']} | {r['blame_seconds']:.2f} s | {r['model_calls_cold']} | "
                   f"{r['model_seconds_cold']:.1f} s | {r['model_seconds_per_call']:.2f} s | "
                   f"{r['prompt_chars_median']:,} | {r['wall_seconds_cold']:.2f} s | {r['wall_seconds_warm']:.2f} s | "
                   f"{r['wall_seconds_no_model']:.2f} s | {'yes' if r['warm_output_identical'] else 'NO'} |")
    out += ["", "| repository | second readings | refused by them | reading time | per reading |",
            "|---|---:|---:|---:|---:|"]
    for r in data["repos"]:
        per = r.get("tone_seconds_per_call")
        out.append(f"| {r['repo']} | {r.get('tone_calls_cold', 0)} | {r.get('tone_refused_cold', 0)} | "
                   f"{r.get('tone_seconds_cold', 0):.1f} s | {'' if per is None else f'{per:.2f} s'} |")
    reasons: dict[str, int] = {}
    for r in data["repos"]:
        for reason, n in r["rejection_reasons"].items():
            reasons[reason] = reasons.get(reason, 0) + n
    if reasons:
        out += ["", "Why answers were rejected (quoted text left out):", ""]
        out += [f"- {n} x {reason}" for reason, n in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))]
    return out


def seeds_table(data: dict[str, Any]) -> list[str]:
    out = [f"{data['answers']} answers from {data['model']} that passed the check, broken on purpose into "
           f"{data['seeds']} seeds; seeds that still passed the check: {data['passed_the_check']}.", "",
           "| seed | made | passed the check |", "|---|---:|---:|"]
    for kind, v in data["by_kind"].items():
        out.append(f"| {kind} | {v['seeds']} | {v['passed']} |")
    return out


def repeat_table(first: dict[str, Any], second: dict[str, Any], same: dict[str, Any]) -> list[str]:
    out = ["A second cold run, same code and same model, right after the first. At temperature 0 the cards came "
           "out the same; the time per model call did not. Other programs were open on the machine during both "
           "runs, and the cause of the spread was not isolated.", "",
           "| repository | per call, first run | per call, second run | first run | second run | cards identical |",
           "|---|---:|---:|---:|---:|---:|"]
    again = {r["repo"]: r for r in second["repos"]}
    for r in first["repos"]:
        s = again[r["repo"]]
        identical = same.get(r["repo"], {})
        out.append(f"| {r['repo']} | {r['model_seconds_per_call']:.2f} s | {s['model_seconds_per_call']:.2f} s | "
                   f"{r['wall_seconds_cold']:.2f} s | {s['wall_seconds_cold']:.2f} s | "
                   f"{identical.get('identical', '?')} of {identical.get('cards', '?')} |")
    return out


def heldout_table(data: dict[str, Any]) -> list[str]:
    names = {"death": "death and mourning", "judgment": "judging the person", "gendered": "gendered wording"}
    out = ["Sentences from `tests/heldout`, written before the word lists and never added to them, each put on "
           f"every one of the {data['answers']} people above with their real quotes. Rejected for any reason, and "
           "for the reason the set is about:", "",
           "| held-out set | sentences | trials | rejected | for that reason | sentences never rejected |",
           "|---|---:|---:|---:|---:|---:|"]
    for key, v in data.get("heldout", {}).items():
        out.append(f"| {names.get(key, key)} | {v['sentences']} | {v['trials']} | {v['rejected']} "
                   f"({pct(v['rejected'], v['trials'])}) | {v['rejected_for_this_reason']} "
                   f"({pct(v['rejected_for_this_reason'], v['trials'])}) | {v['never_rejected']} |")
    return out


def tone_table(data: dict[str, Any]) -> list[str]:
    out = [f"The second reading, frozen before the independent set was opened: {data['judge_calls']:,} calls, "
           f"median {data['judge_seconds_median']} s each. Lists on all {data['people_passing']} people; the "
           f"reading and both on {data['sample_people']} of them (two per repository).", "",
           "| set | sentences | lists | lists (sample) | second reading | both |", "|---|---:|---:|---:|---:|---:|"]
    for label, v in data["sets"].items():
        out.append(f"| {label} | {v['sentences']} | {v['lists_refused_pct']}% | {v['sample_lists_refused_pct']}% | "
                   f"{v['judge_refused_pct']}% | {v['both_refused_pct']}% |")
    real = data["real_cards"]
    out.append(f"| real cards that passed the lists | {real['sentences']} | 0.0% | 0.0% | "
               f"{real['judge_refused_pct']}% | {real['judge_refused_pct']}% |")
    return out


def main() -> int:
    prefix = sys.argv[1]
    blame = load(Path(f"{prefix}-blame-options.json"))
    cards = load(Path(f"{prefix}-gemma4-12b-cards.json"))
    seeds = load(Path(f"{prefix}-gemma4-12b-seeds.json"))
    lines = ["# Measurements", "", "Counts and timings only; the raw output (with real names) stays outside the "
             "repository.", "", "## Blame options", "", *blame_tables(blame), "", "## Cards", "",
             *cards_tables(cards), ""]
    repeat, same = Path(f"{prefix}-gemma4-12b-cards-repeat.json"), Path(f"{prefix}-gemma4-12b-determinism.json")
    if repeat.exists() and same.exists():
        lines += ["### The same run again", "", *repeat_table(cards, load(repeat), load(same)), ""]
    lines += ["## Seeds", "", *seeds_table(seeds), ""]
    if seeds.get("heldout"):
        lines += ["## Held-out wording", "", *heldout_table(seeds), ""]
    tone_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    if tone_path and tone_path.exists():
        lines += ["## The second reading", "", "Refused, in percent of trials (good sets: false refusals).", "",
                  *tone_table(load(tone_path)), ""]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
