"""What each blame option costs and what it changes, on bare clones of real repositories.

    python scripts/measure_blame.py CLONE.git [CLONE.git ...] --out measurements/blame.json [--repeats 3]

For every clone and every option set it times blame over all kept files at HEAD
(median of ``--repeats`` runs, with the default number of parallel jobs, plus one
run with a single job), and counts against plain ``git blame``: lines credited to
another commit, lines credited to another person, and how the set of people who
moved on (730 days) changes. Only counts are written; no name leaves the clone.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ofrenda.blame import BlameOptions, BlameRun, blame_all, default_jobs  # noqa: E402
from ofrenda.files import select  # noqa: E402
from ofrenda.gitread import Git  # noqa: E402
from ofrenda.ledger import build, identities, read_log, repo_label  # noqa: E402

VARIANTS: dict[str, BlameOptions] = {
    "plain": BlameOptions(whitespace=False, moves=False, copies=0, ignore_revs=False),
    "-w": BlameOptions(whitespace=True, moves=False, copies=0, ignore_revs=False),
    "-w -M": BlameOptions(whitespace=True, moves=True, copies=0, ignore_revs=False),
    "-w -M ignore-revs": BlameOptions(copies=0),
    "-w -M -C ignore-revs (default)": BlameOptions(),
    "-w -M -C -C ignore-revs": BlameOptions(copies=2),
}


def owners(run: BlameRun, keys: dict[str, str]) -> dict[tuple[str, int], tuple[str, str]]:
    return {(path, line.number): (line.oid, keys.get(line.oid, "?")) for path, lines in run.files.items()
            for line in lines}


def measure(clone: Path, repeats: int) -> dict[str, object]:
    with Git(clone) as git:
        commit = git.resolve("HEAD")
        selection = select(git, commit)
        commits = read_log(git, commit)
        keys, _ = identities(commits.values())
        result: dict[str, object] = {"repo": repo_label(git), "commit": commit, "commits_reachable": len(commits),
                                     "files_kept": len(selection.kept), "variants": {}}
        baseline: dict[tuple[str, int], tuple[str, str]] | None = None
        base_ghosts: set[str] = set()
        variants: dict[str, object] = {}
        for label, options in VARIANTS.items():
            times = []
            run = None
            for _ in range(repeats):
                started = time.perf_counter()
                run = blame_all(git, commit, selection.kept, options)
                times.append(time.perf_counter() - started)
            assert run is not None
            started = time.perf_counter()
            blame_all(git, commit, selection.kept, options, jobs=1)
            serial = time.perf_counter() - started
            ledger = build(repo_label(git), commit, selection, run, commits, options)
            ghosts = {p.key for p in ledger.ghosts(730)}
            mapping = owners(run, keys)
            entry: dict[str, object] = {
                "seconds_median": round(statistics.median(times), 3), "seconds_all": [round(t, 3) for t in times],
                "seconds_one_job": round(serial, 3), "jobs": run.jobs, "lines": run.lines,
                "failed_files": len(run.failed), "ignored_commits": len(run.ignore_used),
                "people_with_lines": len(ledger.people), "moved_on_730": len(ghosts),
                "top10_moved_on_lines": [p.lines for p in ledger.ghosts(730)[:10]],
            }
            if baseline is None:
                baseline, base_ghosts = mapping, ghosts
            else:
                entry["lines_to_another_commit_vs_plain"] = sum(1 for k, v in mapping.items()
                                                                if baseline.get(k, v)[0] != v[0])
                entry["lines_to_another_person_vs_plain"] = sum(1 for k, v in mapping.items()
                                                                if baseline.get(k, v)[1] != v[1])
                entry["moved_on_gained_vs_plain"] = len(ghosts - base_ghosts)
                entry["moved_on_lost_vs_plain"] = len(base_ghosts - ghosts)
            variants[label] = entry
            print(f"{result['repo']:>10} {label:<32} {entry['seconds_median']:>7}s  one job {serial:>7.2f}s  "
                  f"lines {run.lines}  other person {entry.get('lines_to_another_person_vs_plain', 0)}",
                  file=sys.stderr)
        result["variants"] = variants
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clones", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    data = {"cpu_count": os.cpu_count(), "default_jobs": default_jobs(), "repeats": args.repeats,
            "repos": [measure(c, args.repeats) for c in args.clones]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
