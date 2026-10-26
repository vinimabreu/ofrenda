from __future__ import annotations

import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import ANA, BRUNO, CELIA, DARIO, MakeRepo, Repo, git
from ofrenda.blame import BlameOptions
from ofrenda.gitread import Git
from ofrenda.ledger import (DAY, MESSAGE_CHARS, Ledger, clean_message, fold, is_bot, meaningful, name_can_merge,
                            read_ledger, subject_of)

T0 = 1_400_000_000  # 2014-05-13


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S+0000")


def ledger_of(path: Path, rev: str = "HEAD", **kwargs: object) -> Ledger:
    with Git(path) as g:
        return read_ledger(g, rev, **kwargs)  # type: ignore[arg-type]


def by_name(ledger: Ledger) -> dict[str, int]:
    return {p.name: p.lines for p in ledger.people}


def lines(prefix: str, n: int) -> str:
    return "".join(f"{prefix}_value_{i} = compute('{prefix}', {i})\n" for i in range(n))


# -- identity ----------------------------------------------------------------------------------

def _two_addresses(repo: Repo, *, mailmap: bool) -> None:
    repo.commit({"old.py": lines("old", 3)}, author=("A. Q.", "ana@old.example"), when=iso(T0),
                message="Write the old module")
    repo.commit({"new.py": lines("new", 2)}, author=ANA, when=iso(T0 + DAY), message="Write the new module")
    if mailmap:
        repo.commit({".mailmap": f"{ANA[0]} <{ANA[1]}> <ana@old.example>\n"}, author=BRUNO, when=iso(T0 + 2 * DAY),
                    message="Map the old address")


def test_the_mailmap_at_the_revision_makes_two_addresses_one_person(make_repo: MakeRepo) -> None:
    repo = make_repo()
    _two_addresses(repo, mailmap=True)
    ledger = ledger_of(repo.path)
    assert by_name(ledger)[ANA[0]] == 5
    assert "A. Q." not in by_name(ledger)
    before = ledger_of(repo.path, "HEAD~1")
    assert by_name(before) == {"A. Q.": 3, ANA[0]: 2}


def test_a_bare_clone_gives_the_same_ledger(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    _two_addresses(repo, mailmap=True)
    bare = repo.bare_clone(tmp_path / "copy.git")
    normal, cloned = ledger_of(repo.path), ledger_of(bare)
    assert by_name(normal) == by_name(cloned)
    assert normal.commit == cloned.commit and normal.elder == cloned.elder
    assert [p.name for p in normal.ghosts(0)] == [p.name for p in cloned.ghosts(0)]
    assert cloned.repo == "copy" and normal.repo == "project"


def test_a_bare_clone_maps_with_the_revision_not_with_head(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    _two_addresses(repo, mailmap=True)
    bare = repo.bare_clone(tmp_path / "copy.git")
    # git's own default in a bare clone is HEAD:.mailmap, which would merge them at HEAD~1 too
    assert by_name(ledger_of(bare, "HEAD~1")) == {"A. Q.": 3, ANA[0]: 2}


def test_a_mailmap_only_in_the_working_tree_is_ignored(make_repo: MakeRepo) -> None:
    repo = make_repo()
    _two_addresses(repo, mailmap=False)
    repo.write({".mailmap": f"{ANA[0]} <{ANA[1]}> <ana@old.example>\n"})
    assert by_name(ledger_of(repo.path)) == {"A. Q.": 3, ANA[0]: 2}


def test_a_mailmap_file_in_the_repository_config_is_ignored(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    _two_addresses(repo, mailmap=False)
    outside = tmp_path / "elsewhere.mailmap"
    outside.write_text(f"{ANA[0]} <{ANA[1]}> <ana@old.example>\n", encoding="utf-8")
    repo.run("config", "mailmap.file", str(outside))
    assert by_name(ledger_of(repo.path)) == {"A. Q.": 3, ANA[0]: 2}


def test_the_same_full_name_under_two_addresses_is_one_person(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": lines("a", 3)}, author=(BRUNO[0], "bruno@first-job.example"), when=iso(T0))
    repo.commit({"b.py": lines("b", 2)}, author=(BRUNO[0].upper(), "bruno@second-job.example"),
                when=iso(T0 + 900 * DAY))
    merged = ledger_of(repo.path)
    assert [(p.lines, p.commits) for p in merged.people] == [(5, 2)] and merged.name_joins == 1
    # the merge is what keeps an active person from being shown as someone who moved on
    assert merged.ghosts(730) == []
    split = ledger_of(repo.path, name_merge=False)
    assert sorted(p.lines for p in split.people) == [2, 3]
    assert [p.lines for p in split.ghosts(730)] == [3]


def test_generic_names_are_never_merged(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": lines("a", 3)}, author=("root", "root@build-1.example"), when=iso(T0))
    repo.commit({"b.py": lines("b", 2)}, author=("root", "root@build-2.example"), when=iso(T0 + DAY))
    assert sorted(p.lines for p in ledger_of(repo.path).people) == [2, 3]
    assert not name_can_merge("root") and not name_can_merge("Bo") and name_can_merge("Bo Li")
    assert name_can_merge("quintero")


def test_bots_count_in_the_totals_and_get_no_card(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": lines("a", 3)}, author=ANA, when=iso(T0))
    repo.commit({"deps.txt": lines("dep", 4)}, author=("dependabot[bot]", "49699333+dependabot[bot]@users.example"),
                when=iso(T0 + DAY))
    ledger = ledger_of(repo.path)
    assert by_name(ledger) == {ANA[0]: 3} and ledger.bot_lines == 4 and ledger.lines == 7
    assert ledger.people[0].share == pytest.approx(3 / 7)
    assert is_bot("renovate-bot", "x@y.example") and is_bot("Some Name", "x[bot]@y.example")
    assert not is_bot("Abbot Smith", "abbot@smith.example")


# -- moved on ----------------------------------------------------------------------------------

def _threshold_repo(repo: Repo) -> int:
    head_time = T0 + 2000 * DAY
    repo.commit({"celia.py": lines("celia", 2)}, author=CELIA, when=iso(head_time - 730 * DAY))
    repo.commit({"dario.py": lines("dario", 3)}, author=DARIO, when=iso(head_time - 730 * DAY - 1))
    repo.commit({"ana.py": lines("ana", 1)}, author=ANA, when=iso(head_time))
    return head_time


def test_moved_on_is_strictly_older_than_the_quiet_days(make_repo: MakeRepo) -> None:
    repo = make_repo()
    head_time = _threshold_repo(repo)
    ledger = ledger_of(repo.path)
    assert ledger.commit_time == head_time
    assert [p.name for p in ledger.ghosts(730)] == [DARIO[0]]
    assert [p.name for p in ledger.ghosts(729)] == [DARIO[0], CELIA[0]]
    assert ledger.ghosts(731) == []
    assert [p.name for p in ledger.ghosts(0)] == [DARIO[0], CELIA[0]]  # Ana committed at the revision itself


def test_the_clock_is_the_revision_not_today(make_repo: MakeRepo) -> None:
    repo = make_repo()
    _threshold_repo(repo)
    earlier = ledger_of(repo.path, "HEAD~1")  # Dario's commit is the revision itself
    assert earlier.ghosts(730) == []
    assert earlier.commit_date == iso(T0 + 2000 * DAY - 730 * DAY - 1)[:10]


def test_the_committer_date_of_the_revision_is_the_clock(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"dario.py": lines("dario", 3)}, author=DARIO, when=iso(T0))
    repo.commit({"ana.py": lines("ana", 1)}, author=ANA, when=iso(T0 + 10 * DAY), committed=iso(T0 + 1000 * DAY))
    ledger = ledger_of(repo.path)
    # the revision was committed on day 1000; on day 10, its author date, nobody would have moved on
    assert ledger.commit_time == T0 + 1000 * DAY
    # and a person's activity is their author date: Ana wrote this on day 10, it was applied later
    assert [p.name for p in ledger.ghosts(730)] == [DARIO[0], ANA[0]]
    assert [p.name for p in ledger.ghosts(995)] == [DARIO[0]]


def test_someone_with_no_line_left_is_not_on_the_ofrenda(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": lines("old", 3)}, author=DARIO, when=iso(T0))
    repo.commit({"a.py": lines("new", 3)}, author=ANA, when=iso(T0 + 1000 * DAY))
    ledger = ledger_of(repo.path)
    assert by_name(ledger) == {ANA[0]: 3} and ledger.ghosts(0) == []


def test_a_second_commit_resets_the_quiet_days(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"d.py": lines("d", 3)}, author=DARIO, when=iso(T0))
    repo.commit({"notes.md": "a note from later\n"}, author=DARIO, when=iso(T0 + 900 * DAY))
    repo.commit({"notes.md": "rewritten by someone else\n"}, author=ANA, when=iso(T0 + 1000 * DAY))
    person = {p.name: p for p in ledger_of(repo.path).people}[DARIO[0]]
    assert person.last_date == iso(T0 + 900 * DAY)[:10] and person.lines == 3 and person.commits == 2
    assert ledger_of(repo.path).ghosts(730) == []


# -- card facts ----------------------------------------------------------------------------------

def test_the_elder_and_each_oldest_line_skip_blank_and_tiny_lines(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": "\n)\nimport os\n"}, author=DARIO, when=iso(T0), message="Start the module")
    repo.commit({"b.py": "def helper_function():\n    return None\n"}, author=CELIA, when=iso(T0 + DAY))
    ledger = ledger_of(repo.path)
    assert ledger.elder is not None
    assert (ledger.elder.path, ledger.elder.number, ledger.elder.text) == ("a.py", 3, "import os")
    assert ledger.elder.author == DARIO[0] and ledger.elder.subject == "Start the module"
    assert meaningful("import os") and not meaningful(")") and not meaningful("   ") and not meaningful("x = 1")


def test_the_oldest_line_falls_back_to_any_line(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": "x = 1\n"}, author=DARIO, when=iso(T0))
    person = ledger_of(repo.path).people[0]
    assert person.oldest.text == "x = 1"


def test_top_commit_files_and_snippet(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": lines("a", 2)}, author=DARIO, when=iso(T0), message="Add the small part")
    body = "".join(f"step_{i} = run_step({i})\n" for i in range(12))
    repo.commit({"b.py": "header = 1\n" + body, "c.py": "single = 'line here'\n"}, author=DARIO,
                when=iso(T0 + DAY), message="Add the pipeline\n\nIt runs every step in order.")
    person = ledger_of(repo.path).people[0]
    assert person.top.subject == "Add the pipeline" and person.top.lines == 14
    assert person.files == [("b.py", 13), ("a.py", 2), ("c.py", 1)]
    assert person.snippet_path == "b.py" and len(person.snippet) == 8 and person.snippet[0] == (1, "header = 1")
    assert person.surviving_commits == 2
    assert [m.subject for m in person.messages] == ["Add the pipeline", "Add the small part"]
    assert person.messages[0].message == "Add the pipeline\n\nIt runs every step in order."


def test_messages_drop_trailers_duplicates_and_get_capped(make_repo: MakeRepo) -> None:
    repo = make_repo()
    long_body = "\n".join(f"Detail line number {i} about the change." for i in range(80))
    repo.commit({"a.py": lines("a", 3)}, author=DARIO, when=iso(T0),
                message=f"Rework the parser\n\n{long_body}\n\nSigned-off-by: Dario <dario@lindqvist.example>")
    repo.commit({"b.py": lines("b", 2)}, author=DARIO, when=iso(T0 + DAY), message="Fix typo in docs")
    repo.commit({"c.py": lines("c", 1)}, author=DARIO, when=iso(T0 + 2 * DAY), message="Fix typo in docs")
    person = ledger_of(repo.path).people[0]
    assert [m.subject for m in person.messages] == ["Rework the parser", "Fix typo in docs"]
    first = person.messages[0].message
    assert len(first) <= MESSAGE_CHARS and "Signed-off-by" not in first and "@" not in first
    assert clean_message("Title\r\n\r\n\r\n\r\nBody  \nCo-authored-by: X <x@y.example>\n") == "Title\n\nBody"
    assert subject_of("First line\nstill subject\n\nbody") == "First line still subject"


def test_names_fold_case_accents_and_spaces() -> None:
    assert fold("  José   ÁLVAREZ ") == "jose alvarez"


def test_shallow_clones_are_flagged(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    repo.commit({"a.py": lines("a", 2)}, author=DARIO, when=iso(T0))
    repo.commit({"b.py": lines("b", 2)}, author=ANA, when=iso(T0 + DAY))
    shallow = tmp_path / "shallow.git"
    git(tmp_path, "clone", "-q", "--bare", "--depth", "1", f"file://{repo.path}", str(shallow))
    ledger = ledger_of(shallow)
    assert ledger.shallow and by_name(ledger) == {ANA[0]: 4}
    assert not ledger_of(repo.path).shallow


def test_a_formatting_commit_that_holds_lines_gets_a_notice(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.py": "def a(x):\n    return {'k':x}\n"}, author=DARIO, when=iso(T0), message="Add a")
    fmt = repo.commit({"a.py": 'def a(x):\n    return {"k": x}\n'}, author=ANA, when=iso(T0 + DAY),
                      message="Reformat with the code formatter")
    ledger = ledger_of(repo.path)
    assert [(c.oid, c.lines) for c in ledger.suspects] == [(fmt, 1)]
    with Git(repo.path) as g:
        fixed = read_ledger(g, options=BlameOptions(extra_ignored=(g.resolve(fmt),)))
    assert fixed.suspects == [] and by_name(fixed) == {DARIO[0]: 2} and fixed.ignore_used == 1


# -- cache -------------------------------------------------------------------------------------

def test_the_ledger_is_cached_per_commit_and_options(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    _threshold_repo(repo)
    cache = tmp_path / "cache" / "ofrenda"
    first = ledger_of(repo.path, cache_dir=cache)
    second = ledger_of(repo.path, cache_dir=cache)
    assert not first.cached and second.cached
    assert second == first  # every fact survives the round trip
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700
    files = list(cache.iterdir())
    assert len(files) == 1 and stat.S_IMODE(files[0].stat().st_mode) == 0o600
    other = ledger_of(repo.path, cache_dir=cache, options=BlameOptions(copies=0))
    assert not other.cached and len(list(cache.iterdir())) == 2
    moved = ledger_of(repo.path, "HEAD~1", cache_dir=cache)
    assert not moved.cached


def test_a_broken_cache_file_is_read_again_from_git(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    _threshold_repo(repo)
    cache = tmp_path / "cache"
    ledger_of(repo.path, cache_dir=cache)
    for file in cache.iterdir():
        file.write_text("{not json", encoding="utf-8")
    again = ledger_of(repo.path, cache_dir=cache)
    assert not again.cached and again.people


def test_no_wall_clock_anywhere(make_repo: MakeRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo()
    _threshold_repo(repo)
    import time as time_module
    monkeypatch.setattr(time_module, "time", lambda: 4_000_000_000.0)
    assert [p.name for p in ledger_of(repo.path).ghosts(730)] == [DARIO[0]]
