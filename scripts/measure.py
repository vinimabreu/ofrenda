"""Cold and warm runs of the real command on bare clones, with the real model and the real prompt.

    python scripts/measure.py CLONE.git [CLONE.git ...] --raw RAW_DIR --out measurements/cards.json [--top 10]

For every clone it runs ``python -m ofrenda`` three times: with an empty cache
(cold: blame plus one model call per card, two when the first answer is
rejected), again with that cache (warm), and with ``--no-model``. Everything the
command prints or writes (cards with real names, Markdown, HTML, JSON) goes to
RAW_DIR, which should be outside this repository. ``--out`` gets counts and
timings only: no name, no commit message, no quote.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ofrenda import __version__, model  # noqa: E402
from ofrenda.cards import material_for, prompt_for  # noqa: E402
from ofrenda.gitread import Git  # noqa: E402
from ofrenda.ledger import read_ledger  # noqa: E402

QUOTED = re.compile(r'"[^"]*"')


def code_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src" / "ofrenda").glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:16]


def run(clone: Path, args: list[str], stdout_file: Path) -> tuple[float, int]:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src"), "NO_COLOR": "1",
           "HOME": os.environ.get("HOME", "")}
    started = time.perf_counter()
    result = subprocess.run([sys.executable, "-m", "ofrenda", str(clone), *args], capture_output=True, env=env,
                            check=False)
    seconds = time.perf_counter() - started
    stdout_file.write_bytes(result.stdout)
    stdout_file.with_suffix(".stderr.txt").write_bytes(result.stderr)
    return seconds, result.returncode


def category(reason: str) -> str:
    """The reason without the text it quotes, so no name or message ends up in the counts."""
    return QUOTED.sub('"..."', reason)


def measure_repo(clone: Path, raw: Path, top: int, model_name: str) -> dict[str, Any]:
    name = clone.name.removesuffix(".git")
    cache = raw / "cache" / name
    shutil.rmtree(cache, ignore_errors=True)
    common = ["--top", str(top), "--model", model_name, "--cache", str(cache)]
    cold_s, cold_rc = run(clone, [*common, "--json", str(raw / f"{name}-cold.json"), "--md",
                                  str(raw / f"{name}-OFRENDA.md"), "--html", str(raw / f"{name}-ofrenda.html")],
                          raw / f"{name}-cold.txt")
    warm_s, warm_rc = run(clone, [*common, "--json", str(raw / f"{name}-warm.json")], raw / f"{name}-warm.txt")
    bare_s, bare_rc = run(clone, ["--top", str(top), "--no-model", "--no-cache", "--json",
                                  str(raw / f"{name}-no-model.json")], raw / f"{name}-no-model.txt")
    cold = json.loads((raw / f"{name}-cold.json").read_text(encoding="utf-8"))
    warm = json.loads((raw / f"{name}-warm.json").read_text(encoding="utf-8"))
    stats, warm_stats = cold["card_stats"], warm["card_stats"]
    reasons = Counter(category(r) for card in cold["cards"] for r in card["reasons"])
    with Git(clone) as git:
        ledger = read_ledger(git, cache_dir=cache)
        prompts = [len(prompt_for(material_for(ledger, p))) for p in ledger.ghosts(730)[:top]]
        messages = [len(p.messages) for p in ledger.ghosts(730)[:top]]
    model_calls = stats["asked"]
    entry = {
        "repo": name, "commit": cold["commit"], "commit_date": cold["commit_date"],
        "exit_codes": [cold_rc, warm_rc, bare_rc],
        "files_read": cold["files_read"], "skipped": cold["skipped"], "lines_read": cold["lines_read"],
        "bot_lines": cold["bot_lines"], "people_with_lines": cold["people_with_lines"],
        "moved_on_730_days": cold["moved_on"], "ignored_commits": cold["ignored_commits"],
        "formatting_commits_noticed": len(cold["formatting_commits"]),
        "blame_options": cold["blame_options"], "blame_seconds": cold["blame_seconds"],
        "blame_jobs": cold["blame_jobs"],
        "cards": stats["cards"], "first_try": stats["first_try"], "after_retry": stats["after_retry"],
        "fallback": stats["fallback"], "quotes_verified": stats["quotes_verified"], "model_calls_cold": model_calls,
        "model_seconds_cold": round(stats["seconds"], 2),
        "model_seconds_per_call": round(stats["seconds"] / model_calls, 2) if model_calls else None,
        "prompt_chars_median": int(statistics.median(prompts)) if prompts else 0,
        "prompt_chars_max": max(prompts) if prompts else 0,
        "messages_per_prompt_median": statistics.median(messages) if messages else 0,
        "wall_seconds_cold": round(cold_s, 2), "wall_seconds_warm": round(warm_s, 2),
        "wall_seconds_no_model": round(bare_s, 2),
        "tone_calls_cold": stats["tone_calls"], "tone_refused_cold": stats["tone_refused"],
        "tone_seconds_cold": round(stats["tone_seconds"], 2),
        "tone_seconds_per_call": round(stats["tone_seconds"] / stats["tone_calls"], 3) if stats["tone_calls"] else None,
        "warm_model_calls": warm_stats["asked"], "warm_replies_from_cache": warm_stats["cached"],
        "warm_tone_calls": warm_stats["tone_calls"],
        "warm_facts_from_cache": warm["facts_from_cache"],
        "warm_output_identical": (raw / f"{name}-cold.txt").read_bytes() == (raw / f"{name}-warm.txt").read_bytes(),
        "rejection_reasons": dict(sorted(reasons.items())),
    }
    print(json.dumps(entry), file=sys.stderr)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clones", nargs="+", type=Path)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--model", default=model.DEFAULT_MODEL)
    args = parser.parse_args()
    if ROOT in args.raw.resolve().parents or args.raw.resolve() == ROOT:
        parser.error("--raw must be outside the repository: it holds real names")
    args.raw.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    repos = [measure_repo(c, args.raw, args.top, args.model) for c in args.clones]
    totals = {key: sum(r[key] for r in repos) for key in ("cards", "first_try", "after_retry", "fallback",
                                                         "quotes_verified", "model_calls_cold", "warm_model_calls",
                                                         "tone_calls_cold", "tone_refused_cold", "warm_tone_calls")}
    data = {"ofrenda": __version__, "code": code_hash(), "started": started, "model": args.model,
            "model_digest": model.digest(args.model), "top": args.top, "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(), "repos": repos, "totals": totals}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
