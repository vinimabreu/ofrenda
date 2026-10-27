"""From blame and log to the facts on every card. Pure code: no model is involved here.

Identity. git maps every author through the ``.mailmap`` at the revision (see
``gitread``). After that, one person is one canonical email address. Two
addresses that carry the same full name are merged too, because the other way
round is worse: without the merge, someone who changed jobs and kept committing
under a new address would show up as a person who moved on. Generic names
(``GENERIC_NAMES``) and one-word names shorter than four letters are never merged
by name. Bot accounts are counted in the totals and never get a card.

A person who moved on ("a ghost" in the code) still has lines at the revision,
and their last commit reachable from it is more than ``quiet_days`` older than
the revision's commit date. The clock is the revision, not today, so the same
revision gives the same answer on any day.

Dates on cards are the author's own local date, as ``git log --date=short``
prints them.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .blame import BlameOptions, BlameRun, BlamedLine, blame_all
from .files import RULES_VERSION, Selection, select
from .gitread import Git

LEDGER_VERSION = "ledger-v2"
DAY = 86400
MESSAGE_CHARS = 1200  # per commit message given to the model
MESSAGES_TOTAL = 7000  # all of one person's messages together
MAX_MESSAGES = 12
SNIPPET_LINES = 8
LINE_CHARS = 160
GENERIC_NAMES = frozenset({
    "root", "admin", "administrator", "user", "unknown", "none", "nobody", "anonymous", "your name", "you",
    "github", "gitlab", "git", "local", "ubuntu", "developer", "dev", "test", "me", "noreply", "system",
})
BOT_NAMES = frozenset({"dependabot", "renovate", "github-actions", "pre-commit-ci", "greenkeeper", "pyup-bot",
                       "snyk-bot", "mergify", "allcontributors", "imgbot", "web-flow"})
# Build and CI services commit under names like these; their commits are not a person's work.
# Build, CI and bot services, by the addresses they commit from. A bare name is not enough: a person
# can be called Travis or Jenkins.
CI_ADDRESSES = frozenset({"noreply@github.com", "actions@github.com", "action@github.com",
                          "azuredevops@microsoft.com", "bot@renovateapp.com", "support@dependabot.com",
                          "noreply@weblate.org", "hosted@weblate.org"})
CI_DOMAINS = ("travis-ci.org", "travis-ci.com", "circleci.com", "appveyor.com", "dependabot.com", "renovateapp.com",
              "greenkeeper.io", "pre-commit.ci", "pyup.io", "snyk.io", "mergify.io", "mergify.com", "codecov.io",
              "coveralls.io", "transifex.com", "crowdin.com", "allcontributors.org", "imgbot.net")
FORMATTING = re.compile(r"\b(re-?format\w*|black|autopep8|yapf|isort|prettier|clang-format|gofmt|rustfmt|"
                        r"ruff format|code style|formatting|whitespace|indentation|pep ?8|tabs to spaces|"
                        r"trailing spaces|line endings|crlf)\b", re.I)
SUSPECT_SHARE = 0.005  # a formatting commit that still holds this share of the lines gets a notice
TRAILER = re.compile(r"^(signed-off-by|co-authored-by|reviewed-by|acked-by|tested-by|reported-by|suggested-by|"
                     r"helped-by|cc|change-id):.*$", re.I | re.M)


@dataclass(frozen=True)
class Commit:
    oid: str
    name: str
    email: str
    author_time: int
    author_date: str  # YYYY-MM-DD in the author's own offset
    commit_time: int
    commit_date: str
    message: str

    @property
    def subject(self) -> str:
        return subject_of(self.message)


def subject_of(message: str) -> str:
    """The first paragraph folded into one line, as git's ``%s`` does it."""
    paragraph = message.strip().split("\n\n", 1)[0]
    return " ".join(paragraph.split())


def clean_message(message: str) -> str:
    """The message without sign-off style trailers (they carry emails), trimmed, at most
    ``MESSAGE_CHARS`` characters cut at a line end."""
    text = TRAILER.sub("", message.replace("\r\n", "\n"))
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.split("\n"))).strip()
    if len(text) > MESSAGE_CHARS:
        cut = text.rfind("\n", 0, MESSAGE_CHARS)
        text = text[:cut if cut > MESSAGE_CHARS // 2 else MESSAGE_CHARS].rstrip()
    return text


def read_log(git: Git, commit: str) -> dict[str, Commit]:
    fields = "%H%x1f%aN%x1f%aE%x1f%at%x1f%ai%x1f%ct%x1f%ci%x1f%B"
    out = git.run([*git.mailmap_args(commit), "log", "-z", "--no-show-signature", "--no-ext-diff", "--no-color",
                   f"--format={fields}", commit, "--"])
    commits: dict[str, Commit] = {}
    for record in out.split(b"\0"):
        if not record.strip():
            continue
        parts = record.decode("utf-8", errors="replace").lstrip("\n").split("\x1f", 7)
        if len(parts) < 8:
            continue
        oid, name, email, author_time, author_iso, commit_time, commit_iso, message = parts
        commits[oid] = Commit(oid, name.strip(), email.strip(), int(author_time or 0), author_iso[:10],
                              int(commit_time or 0), commit_iso[:10], message)
    return commits


def fold(text: str) -> str:
    """Case, accents and runs of spaces aside."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.casefold().split())


def is_bot(name: str, email: str) -> bool:
    """Bots and CI services: a ``[bot]`` marker, a name in ``BOT_NAMES`` or ending in "bot", or an
    address in ``CI_ADDRESSES`` or at one of ``CI_DOMAINS``. A person's name alone never makes them
    a bot."""
    low_name, low_email = " ".join(name.casefold().split()), email.casefold().strip("<>")
    if ("[bot]" in low_name or "[bot]" in low_email or low_name in BOT_NAMES or low_name.endswith("-bot")
            or low_name.endswith(" bot")):
        return True
    domain = low_email.rsplit("@", 1)[-1]
    return low_email in CI_ADDRESSES or any(domain == d or domain.endswith("." + d) for d in CI_DOMAINS)


def name_can_merge(name: str) -> bool:
    folded = fold(name)
    if not folded or folded in GENERIC_NAMES:
        return False
    return " " in folded or len(folded) >= 4


class _Union:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def identities(commits: Iterable[Commit], *, name_merge: bool = True) -> tuple[dict[str, str], int]:
    """Commit id -> person key, and how many address groups were joined by name."""
    union = _Union()
    by_commit: dict[str, str] = {}
    first_for_name: dict[str, str] = {}
    joined = 0
    for commit in commits:
        email_key = "email:" + commit.email.casefold() if commit.email else "name:" + fold(commit.name)
        union.find(email_key)
        by_commit[commit.oid] = email_key
        if name_merge and name_can_merge(commit.name):
            folded = fold(commit.name)
            other = first_for_name.setdefault(folded, email_key)
            if union.find(other) != union.find(email_key):
                union.join(other, email_key)
                joined += 1
    return {oid: union.find(key) for oid, key in by_commit.items()}, joined


@dataclass
class LineFact:
    path: str
    number: int
    text: str
    oid: str
    date: str
    author: str = ""
    subject: str = ""
    author_key: str = ""


@dataclass
class CommitFact:
    oid: str
    date: str
    subject: str
    lines: int
    message: str = ""


@dataclass
class Person:
    key: str
    name: str
    first_date: str
    last_date: str
    last_time: int
    commits: int
    lines: int
    share: float  # of all blamed lines, 0..1
    files: list[tuple[str, int]]
    oldest: LineFact
    top: CommitFact
    surviving_commits: int
    messages: list[CommitFact]  # the commits with the most surviving lines, with their messages
    snippet_path: str
    snippet: list[tuple[int, str]]

    def quiet_days(self, at: int) -> int:
        return max(0, (at - self.last_time) // DAY)


@dataclass
class Ledger:
    repo: str
    commit: str
    commit_time: int
    commit_date: str
    options: str
    files_kept: int
    skipped: dict[str, int]
    failed: int
    lines: int
    bot_lines: int
    people: list[Person]
    elder: LineFact | None
    ignore_listed: int
    ignore_used: int
    shallow: bool
    name_joins: int
    blame_seconds: float
    jobs: int
    suspects: list[CommitFact] = field(default_factory=list)  # formatting commits that hold many lines
    version: str = LEDGER_VERSION
    cached: bool = field(default=False, compare=False)

    def ghosts(self, quiet_days: int) -> list[Person]:
        """People with surviving lines whose last commit is more than ``quiet_days`` before the
        revision, most surviving lines first."""
        limit = self.commit_time - quiet_days * DAY
        found = [p for p in self.people if p.lines > 0 and p.last_time < limit]
        return sorted(found, key=lambda p: (-p.lines, fold(p.name), p.key))


def meaningful(text: str) -> bool:
    """Worth showing as someone's oldest line: eight or more visible characters, three letters."""
    visible = text.strip()
    return len(visible) >= 8 and sum(c.isalpha() for c in visible) >= 3


def _clip(text: str, limit: int = LINE_CHARS) -> str:
    text = text.expandtabs(4).rstrip()
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _best_run(lines: list[BlamedLine], oid: str) -> list[BlamedLine]:
    """The longest run of consecutive lines from ``oid`` (the first one on a tie), without its
    leading and trailing blank lines, at most ``SNIPPET_LINES`` long."""
    best: list[BlamedLine] = []
    run: list[BlamedLine] = []
    for line in lines:
        if line.oid == oid and (not run or line.number == run[-1].number + 1):
            run.append(line)
        else:
            if len(run) > len(best):
                best = run
            run = [line] if line.oid == oid else []
    if len(run) > len(best):
        best = run
    while best and not best[0].text.strip():
        best = best[1:]
    best = best[:SNIPPET_LINES]
    while best and not best[-1].text.strip():
        best = best[:-1]
    return best


def build(repo_label: str, commit: str, selection: Selection, blame: BlameRun, commits: dict[str, Commit],
          options: BlameOptions, *, shallow: bool = False, name_merge: bool = True) -> Ledger:
    keys, joined = identities(commits.values(), name_merge=name_merge)
    head = commits[commit]
    authored: dict[str, list[Commit]] = defaultdict(list)
    for each in commits.values():
        authored[keys[each.oid]].append(each)

    lines_by_person: Counter[str] = Counter()
    files_by_person: dict[str, Counter[str]] = defaultdict(Counter)
    commit_lines: dict[str, Counter[str]] = defaultdict(Counter)  # person -> oid -> lines
    commit_file_lines: dict[str, Counter[str]] = defaultdict(Counter)  # oid -> path -> lines
    oldest: dict[str, tuple[tuple[int, str, int], LineFact]] = {}
    oldest_any: dict[str, tuple[tuple[int, str, int], LineFact]] = {}
    elder: tuple[tuple[int, str, int], LineFact] | None = None
    total = bots = 0
    for path in sorted(blame.files):
        for line in blame.files[path]:
            total += 1
            c = commits.get(line.oid)
            if c is None:
                continue
            if is_bot(c.name, c.email):
                bots += 1
                continue
            key = keys[c.oid]
            lines_by_person[key] += 1
            files_by_person[key][path] += 1
            commit_lines[key][c.oid] += 1
            commit_file_lines[c.oid][path] += 1
            rank = (c.author_time, path, line.number)
            fact = LineFact(path, line.number, _clip(line.text), c.oid, c.author_date)
            if key not in oldest_any or rank < oldest_any[key][0]:
                oldest_any[key] = (rank, fact)
            if meaningful(line.text):
                if key not in oldest or rank < oldest[key][0]:
                    oldest[key] = (rank, fact)
                if elder is None or rank < elder[0]:
                    elder = (rank, LineFact(path, line.number, _clip(line.text), c.oid, c.author_date,
                                            author=c.name, subject=c.subject, author_key=key))

    people: list[Person] = []
    for key, count in lines_by_person.items():
        mine = authored[key]
        names = Counter(c.name for c in mine)
        latest_name = max(mine, key=lambda c: c.author_time).name
        name = max(names, key=lambda n: (names[n], n == latest_name, n))
        first = min(mine, key=lambda c: (c.author_time, c.oid))
        last = max(mine, key=lambda c: (c.author_time, c.oid))
        ranked = sorted(commit_lines[key].items(), key=lambda kv: (-kv[1], commits[kv[0]].author_time, kv[0]))
        top_oid, top_lines = ranked[0]
        top = commits[top_oid]
        messages: list[CommitFact] = []
        seen: set[str] = set()
        budget = MESSAGES_TOTAL
        for oid, n in ranked:
            if len(messages) >= MAX_MESSAGES:
                break
            text = clean_message(commits[oid].message)
            if not text or text in seen or len(text) > budget:
                continue
            seen.add(text)
            budget -= len(text)
            messages.append(CommitFact(oid, commits[oid].author_date, commits[oid].subject, n, text))
        snippet_path = sorted(commit_file_lines[top_oid].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        run = _best_run(blame.files[snippet_path], top_oid)
        files = sorted(files_by_person[key].items(), key=lambda kv: (-kv[1], kv[0]))
        people.append(Person(
            key=key, name=name, first_date=first.author_date, last_date=last.author_date,
            last_time=last.author_time, commits=len(mine), lines=count, share=count / total if total else 0.0,
            files=files, oldest=(oldest.get(key) or oldest_any[key])[1],
            top=CommitFact(top_oid, top.author_date, top.subject, top_lines),
            surviving_commits=len(commit_lines[key]), messages=messages, snippet_path=snippet_path,
            snippet=[(line.number, _clip(line.text)) for line in run]))
    people.sort(key=lambda p: (-p.lines, fold(p.name), p.key))
    held = {oid: sum(paths.values()) for oid, paths in commit_file_lines.items()}
    suspects = [CommitFact(oid, commits[oid].author_date, commits[oid].subject, n)
                for oid, n in sorted(held.items(), key=lambda kv: (-kv[1], kv[0]))
                if n >= SUSPECT_SHARE * total and FORMATTING.search(commits[oid].subject)
                and oid not in blame.ignore_used]
    if elder is not None:
        display = {p.key: p.name for p in people}
        elder[1].author = display.get(keys[elder[1].oid], elder[1].author)
    return Ledger(
        repo=repo_label, commit=commit, commit_time=head.commit_time, commit_date=head.commit_date,
        options=options.label(), files_kept=len(blame.files), skipped=dict(sorted(selection.skipped.items())),
        failed=len(blame.failed), lines=total, bot_lines=bots, people=people, elder=elder[1] if elder else None,
        ignore_listed=blame.ignore_listed, ignore_used=len(blame.ignore_used), shallow=shallow, name_joins=joined,
        blame_seconds=round(blame.seconds, 3), jobs=blame.jobs, suspects=suspects)


def repo_label(git: Git) -> str:
    path = git.git_dir
    if path.name == ".git":
        path = path.parent
    name = path.name
    return name[:-4] if name.endswith(".git") and len(name) > 4 else name


# -- cache --------------------------------------------------------------------------------------

def ledger_key(commit: str, options: BlameOptions, shallow_marker: str, name_merge: bool) -> str:
    material = json.dumps([LEDGER_VERSION, RULES_VERSION, commit, options.label(), shallow_marker, name_merge])
    return hashlib.sha256(material.encode()).hexdigest()


def make_private_dir(directory: Path) -> None:
    """Create ``directory`` readable only by you; an existing folder keeps its permissions."""
    if directory.is_dir():
        return
    missing = [directory]
    while not missing[-1].parent.exists() and missing[-1].parent != missing[-1]:
        missing.append(missing[-1].parent)
    directory.mkdir(parents=True, exist_ok=True)
    for created in missing:
        with contextlib.suppress(OSError):
            os.chmod(created, 0o700)


def write_private(path: Path, payload: Any) -> None:
    make_private_dir(path.parent)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ofrenda-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=1, sort_keys=True)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def ledger_from_dict(data: dict[str, Any]) -> Ledger:
    people = []
    for p in data["people"]:
        people.append(Person(
            key=p["key"], name=p["name"], first_date=p["first_date"], last_date=p["last_date"],
            last_time=p["last_time"], commits=p["commits"], lines=p["lines"], share=p["share"],
            files=[(f, n) for f, n in p["files"]], oldest=LineFact(**p["oldest"]), top=CommitFact(**p["top"]),
            surviving_commits=p["surviving_commits"], messages=[CommitFact(**m) for m in p["messages"]],
            snippet_path=p["snippet_path"], snippet=[(n, t) for n, t in p["snippet"]]))
    values = {k: v for k, v in data.items() if k not in ("people", "elder", "cached", "suspects")}
    return Ledger(**values, people=people, elder=LineFact(**data["elder"]) if data.get("elder") else None,
                  suspects=[CommitFact(**c) for c in data.get("suspects", [])])


def load_cached(directory: Path, key: str) -> Ledger | None:
    try:
        data = json.loads((directory / f"ledger-{key[:32]}.json").read_text(encoding="utf-8"))
        if data.get("version") != LEDGER_VERSION:
            return None
        ledger = ledger_from_dict(data)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    ledger.cached = True
    return ledger


def save_cached(directory: Path, key: str, ledger: Ledger) -> None:
    payload = asdict(ledger)
    payload.pop("cached", None)
    write_private(directory / f"ledger-{key[:32]}.json", payload)


def read_ledger(git: Git, rev: str = "HEAD", *, options: BlameOptions | None = None, jobs: int | None = None,
                cache_dir: Path | None = None, name_merge: bool = True,
                progress: Callable[[int, int, str], None] | None = None) -> Ledger:
    """Blame the revision and build the facts, or load them from the cache when this exact
    commit was read before with the same options."""
    options = options or BlameOptions()
    commit = git.resolve(rev)
    shallow = git.is_shallow()
    key = ledger_key(commit, options, git.shallow_marker(), name_merge)
    if cache_dir is not None:
        cached = load_cached(cache_dir, key)
        if cached is not None:
            cached.repo = repo_label(git)  # the same commit can live in a clone with another name
            return cached
    selection = select(git, commit)
    blame = blame_all(git, commit, selection.kept, options, jobs=jobs, progress=progress)
    commits = read_log(git, commit)
    ledger = build(repo_label(git), commit, selection, blame, commits, options, shallow=shallow,
                   name_merge=name_merge)
    # Facts read with objects missing (a partial clone) or a file git could not blame are not
    # the facts of this commit, so they are never cached: a complete clone must not inherit them.
    if cache_dir is not None and not selection.skipped.get("unreadable") and not blame.failed:
        save_cached(cache_dir, key, ledger)
    return ledger
