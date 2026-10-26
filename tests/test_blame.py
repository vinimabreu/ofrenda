from __future__ import annotations

from pathlib import Path

from conftest import ANA, BRUNO, MakeRepo, Repo
from ofrenda.blame import BlameOptions, blame_all, ignore_revs, parse_porcelain
from ofrenda.files import select
from ofrenda.gitread import Git

CODE = "".join(f"def function_{i}(value):\n    return value + {i}\n\n" for i in range(6))


def authors(repo_path: Path, options: BlameOptions | None = None, path: str = "app.py") -> dict[int, str]:
    """Line number -> author email of the commit blame gives that line."""
    with Git(repo_path) as g:
        commit = g.resolve("HEAD")
        run = blame_all(g, commit, [k for k in select(g, commit).kept], options, jobs=2)
        emails = {}
        for line in run.files[path]:
            emails[line.number] = g.run(["log", "-1", "--format=%aE", line.oid]).decode().strip()
    return emails


def test_parse_porcelain_reads_both_forms() -> None:
    oid = "a" * 40
    porcelain = (f"{oid} 1 1 2\nauthor X\nauthor-mail <x@y.example>\nsummary s\nfilename f\n\tfirst\n"
                 f"{oid} 2 2\n\tsecond\r\n").encode()
    lines = parse_porcelain(porcelain)
    assert [(x.number, x.oid, x.text) for x in lines] == [(1, oid, "first"), (2, oid, "second")]
    line_porcelain = (f"{oid} 1 1 1\nauthor X\nfilename f\n\t\tindented\n").encode()
    assert parse_porcelain(line_porcelain)[0].text == "\tindented"


def test_options_build_the_git_flags() -> None:
    assert BlameOptions().args() == ["-w", "-M", "-C"]
    assert BlameOptions().label() == "-w -M -C ignore-revs"
    assert BlameOptions(whitespace=False, moves=False, copies=0, ignore_revs=False).label() == "plain"
    assert BlameOptions(copies=2).args() == ["-w", "-M", "-C", "-C"]
    assert BlameOptions(extra_ignored=("b" * 40,)).label().endswith("ignore-rev=" + "b" * 40)


def _reindented(repo: Repo) -> None:
    repo.commit({"app.py": CODE}, author=ANA, message="Write the functions")
    repo.commit({"app.py": CODE.replace("    return", "        return")}, author=BRUNO,
                when="2016-01-01T00:00:00+0000", message="Indent with eight spaces")


def test_whitespace_only_changes_keep_their_author(make_repo: MakeRepo) -> None:
    repo = make_repo()
    _reindented(repo)
    assert set(authors(repo.path).values()) == {ANA[1]}
    plain = authors(repo.path, BlameOptions(whitespace=False, copies=0))
    assert BRUNO[1] in plain.values()


def test_code_moved_inside_a_file_keeps_its_author(make_repo: MakeRepo) -> None:
    repo = make_repo()
    blocks = [f"def block_{i}(items):\n    total = sum(items) * {i}\n    return total - {i}\n\n" for i in range(4)]
    repo.commit({"app.py": "".join(blocks)}, author=ANA, message="Write four blocks")
    moved = blocks[1] + blocks[2] + blocks[3] + blocks[0]
    repo.commit({"app.py": moved}, author=BRUNO, when="2016-01-01T00:00:00+0000", message="Move the first block")
    assert set(authors(repo.path).values()) == {ANA[1]}
    plain = authors(repo.path, BlameOptions(moves=False, copies=0))
    assert BRUNO[1] in plain.values()


def test_copies_across_files_are_followed_unless_turned_off(make_repo: MakeRepo) -> None:
    repo = make_repo()
    helper = "".join(f"def helper_{i}(text):\n    cleaned = text.strip().lower()\n    return cleaned[{i}:]\n\n"
                     for i in range(5))
    repo.commit({"app.py": helper}, author=ANA, message="Write the helpers")
    repo.commit({"app.py": "from helpers import *\n", "helpers.py": helper}, author=BRUNO,
                when="2016-01-01T00:00:00+0000", message="Move the helpers to their own module")
    assert set(authors(repo.path, path="helpers.py").values()) == {ANA[1]}
    assert set(authors(repo.path, BlameOptions(copies=0), path="helpers.py").values()) == {BRUNO[1]}


def _formatter_repo(repo: Repo, *, listed: bool) -> str:
    repo.commit({"app.py": "def a(x):\n    return {'k':x}\n"}, author=ANA, message="Add a")
    fmt = repo.commit({"app.py": 'def a(x):\n    return {"k": x}\n'}, author=BRUNO,
                      when="2016-01-01T00:00:00+0000", message="Run the formatter")
    if listed:
        repo.commit({".git-blame-ignore-revs": f"# formatter\n{fmt}\n"}, author=BRUNO,
                    when="2016-01-02T00:00:00+0000", message="Ignore the formatter run in blame")
    return fmt


def test_ignore_revs_at_the_revision_give_lines_back(make_repo: MakeRepo) -> None:
    repo = make_repo("listed")
    _formatter_repo(repo, listed=True)
    assert authors(repo.path) == {1: ANA[1], 2: ANA[1]}
    assert authors(repo.path, BlameOptions(ignore_revs=False))[2] == BRUNO[1]


def test_without_a_list_the_formatter_keeps_the_lines(make_repo: MakeRepo) -> None:
    repo = make_repo("unlisted")
    fmt = _formatter_repo(repo, listed=False)
    assert authors(repo.path)[2] == BRUNO[1]
    assert authors(repo.path, BlameOptions(extra_ignored=(fmt,)))[2] == ANA[1]


def test_an_ignore_list_only_in_the_working_tree_is_not_read(make_repo: MakeRepo) -> None:
    repo = make_repo()
    fmt = _formatter_repo(repo, listed=False)
    repo.write({".git-blame-ignore-revs": f"{fmt}\n"})
    repo.run("config", "blame.ignoreRevsFile", ".git-blame-ignore-revs")
    assert authors(repo.path)[2] == BRUNO[1]


def test_ignore_list_entries_are_resolved_before_blame(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"app.py": "def a(x):\n    return {'k':x}\n"}, author=ANA, message="Add a")
    fmt = repo.commit({"app.py": 'def a(x):\n    return {"k": x}\n'}, author=BRUNO,
                      when="2016-01-01T00:00:00+0000", message="Run the formatter")
    repo.commit({".git-blame-ignore-revs": f"# comments and junk are fine\n{fmt[:10]}  # short id\n{'0' * 40}\n"
                                           "not-a-commit\n\n"},
                author=BRUNO, when="2016-01-02T00:00:00+0000", message="List the formatter run")
    with Git(repo.path) as g:
        listed, used = ignore_revs(g, g.resolve("HEAD"))
    assert listed == 3 and used == [fmt]
    assert authors(repo.path)[2] == ANA[1]


def test_blame_all_counts_and_keeps_going_when_a_file_fails(make_repo: MakeRepo, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = make_repo()
    oid = repo.commit({"a.py": "a = 1\nb = 2\n", "b.py": "c = 3\n"})
    from ofrenda import blame as module
    original = module.blame_file

    def flaky(git, commit, path, options, revs_file):  # type: ignore[no-untyped-def]
        if path == "b.py":
            raise module.GitError("git blame failed: simulated")
        return original(git, commit, path, options, revs_file)

    monkeypatch.setattr(module, "blame_file", flaky)
    with Git(repo.path) as g:
        run = blame_all(g, oid, select(g, oid).kept, jobs=1)
    assert run.lines == 2 and list(run.failed) == ["b.py"] and run.seconds >= 0
