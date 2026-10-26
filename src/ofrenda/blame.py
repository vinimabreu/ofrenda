"""git blame for every kept file at one revision, in parallel.

Default options (the measurement behind them is in ``measurements/``):

- ``-w``: a line whose only change was whitespace keeps its author;
- ``-M``: a line moved inside its file keeps its author;
- ``-C``: a line moved or copied from another file changed in the same commit
  keeps its author (when a module is split in two, the split does not take the
  credit). It costs more blame time than the others (how much, on four public
  repositories, is in ``measurements/``); ``-C -C`` costs more again for few
  further lines and is not used;
- ``.git-blame-ignore-revs`` read from the tree at the revision (never from a
  working tree): commits listed there, such as a formatter run over the whole
  code base, give their lines back to the commit before them. Entries are
  resolved first; ones that are not a commit in this repository are dropped,
  because git stops on an abbreviated or unknown entry instead of skipping it.

Blame runs with ``--no-textconv`` so a textconv driver never runs. Output is read
in ``--porcelain`` form (the commit id and text of every line); who wrote each
commit and when comes from ``git log`` (see ``ledger``), so the per-line copy of
those headers in ``--line-porcelain`` is not needed.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .files import Kept
from .gitread import Git, GitError

IGNORE_REVS_PATH = ".git-blame-ignore-revs"
_HEADER = re.compile(rb"^([0-9a-f]{40}|[0-9a-f]{64}) (\d+) (\d+)(?: \d+)?$")


@dataclass(frozen=True)
class BlameOptions:
    whitespace: bool = True
    moves: bool = True
    copies: int = 1  # how many times -C is given (0 to 3)
    ignore_revs: bool = True
    extra_ignored: tuple[str, ...] = ()  # commits given with --ignore-rev, resolved to full ids

    def args(self) -> list[str]:
        args: list[str] = []
        if self.whitespace:
            args.append("-w")
        if self.moves:
            args.append("-M")
        args += ["-C"] * max(0, min(self.copies, 3))
        return args

    def label(self) -> str:
        words = self.args() or ["plain"]
        if self.ignore_revs:
            words.append("ignore-revs")
        words += [f"ignore-rev={oid}" for oid in sorted(self.extra_ignored)]
        return " ".join(words)


@dataclass(frozen=True)
class BlamedLine:
    number: int
    oid: str
    text: str


@dataclass
class BlameRun:
    files: dict[str, list[BlamedLine]] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    ignore_listed: int = 0
    ignore_used: list[str] = field(default_factory=list)
    seconds: float = 0.0
    jobs: int = 1

    @property
    def lines(self) -> int:
        return sum(len(v) for v in self.files.values())


def parse_porcelain(out: bytes) -> list[BlamedLine]:
    """Lines of ``git blame --porcelain`` or ``--line-porcelain`` output, in file order."""
    lines: list[BlamedLine] = []
    oid = ""
    number = 0
    for raw in out.split(b"\n"):
        if raw.startswith(b"\t"):
            text = raw[1:].decode("utf-8", errors="replace").rstrip("\r")
            lines.append(BlamedLine(number, oid, text))
            continue
        match = _HEADER.match(raw)
        if match:
            oid = match.group(1).decode()
            number = int(match.group(3))
    lines.sort(key=lambda line: line.number)
    return lines


def ignore_revs(git: Git, commit: str) -> tuple[int, list[str]]:
    """Entries in ``.git-blame-ignore-revs`` at ``commit``: how many are listed, and the full ids
    of the ones that are commits here."""
    data = git.read_path(commit, IGNORE_REVS_PATH)
    if data is None:
        return 0, []
    names = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            names.append(entry.split()[0])
    return len(names), git.commits_that_exist(names)


def blame_file(git: Git, commit: str, path: str, options: BlameOptions, revs_file: Path | None) -> list[BlamedLine]:
    args = ["blame", "--porcelain", "--no-textconv", *options.args()]
    if revs_file is not None:
        args += ["--ignore-revs-file", str(revs_file)]
    args += [commit, "--", path]
    return parse_porcelain(git.run(args))


def default_jobs() -> int:
    return max(1, min(8, os.cpu_count() or 1))


def blame_all(git: Git, commit: str, kept: Sequence[Kept], options: BlameOptions | None = None, *,
              jobs: int | None = None, progress: Callable[[int, int, str], None] | None = None) -> BlameRun:
    options = options or BlameOptions()
    run = BlameRun(jobs=jobs or default_jobs())
    revs_file: Path | None = None
    if options.ignore_revs:
        run.ignore_listed, run.ignore_used = ignore_revs(git, commit)
    for oid in options.extra_ignored:
        if oid not in run.ignore_used:
            run.ignore_used.append(oid)
    if run.ignore_used:
        revs_file = git.tmp / "ignore-revs"
        revs_file.write_text("".join(f"{oid}\n" for oid in run.ignore_used), encoding="ascii")
    started = time.perf_counter()

    def one(item: Kept) -> tuple[str, list[BlamedLine] | None, str]:
        try:
            return item.path, blame_file(git, commit, item.path, options, revs_file), ""
        except GitError as error:
            return item.path, None, str(error)

    with ThreadPoolExecutor(max_workers=run.jobs) as pool:
        for done, (path, lines, error) in enumerate(pool.map(one, kept), start=1):
            if lines is None:
                run.failed[path] = error
            else:
                run.files[path] = lines
            if progress:
                progress(done, len(kept), path)
    run.seconds = time.perf_counter() - started
    return run
