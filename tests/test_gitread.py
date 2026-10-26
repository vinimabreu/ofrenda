from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import ANA, MakeRepo, Repo, git
from ofrenda.gitread import HARDENING, Git, GitError, _environment


def test_a_folder_that_is_not_a_repository_is_refused(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    with pytest.raises(GitError, match="not a git repository"):
        Git(tmp_path / "plain")


def test_a_missing_path_is_refused(tmp_path: Path) -> None:
    with pytest.raises(GitError, match="does not exist"):
        Git(tmp_path / "nowhere")


def test_resolve_names_a_commit_and_refuses_the_rest(make_repo: MakeRepo) -> None:
    repo = make_repo()
    oid = repo.commit({"a.txt": "one\n"})
    with Git(repo.path) as g:
        assert g.resolve("HEAD") == oid
        assert g.resolve(oid[:8]) == oid
        with pytest.raises(GitError, match="is not a commit"):
            g.resolve("no-such-branch")
        with pytest.raises(GitError, match="is not a commit"):
            g.resolve("--output=/tmp/x")  # never read as an option
        tree = g.run(["rev-parse", f"{oid}^{{tree}}"]).decode().strip()
        with pytest.raises(GitError):
            g.resolve(tree)


def test_bare_and_normal_repositories_are_told_apart(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    repo.commit({"a.txt": "one\n"})
    bare = repo.bare_clone(tmp_path / "bare.git")
    with Git(repo.path) as g:
        assert not g.bare and g.git_dir == (repo.path / ".git").resolve()
    with Git(bare) as g:
        assert g.bare and g.git_dir == bare.resolve()


def test_a_subfolder_opens_the_repository_around_it(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"src/a.txt": "one\n"})
    with Git(repo.path / "src") as g:
        assert g.git_dir == (repo.path / ".git").resolve()


def test_git_runs_with_an_empty_work_tree_and_no_user_config(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.commit({"a.txt": "one\n"})
    with Git(repo.path) as g:
        env = _environment(g.tmp, g.shadow, g.work)
        assert env["GIT_DIR"] == str(g.shadow) and env["GIT_WORK_TREE"] == str(g.work)
        assert env["GIT_INDEX_FILE"].startswith(str(g.work)) and not Path(env["GIT_INDEX_FILE"]).exists()
        assert env["GIT_CONFIG_GLOBAL"] == os.devnull and env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert env["GIT_NO_LAZY_FETCH"] == "1" and env["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert env["HOME"] == str(g.tmp)
        assert not any(key.startswith(("SSH_AUTH", "AWS", "GITHUB")) for key in env)
        g.run(["log", "-1", "--format=%H", g.resolve("HEAD")])
        assert list(g.work.iterdir()) == []
        scratch = g.scratch
        assert oct(scratch.stat().st_mode & 0o777) == "0o700"
    assert not scratch.exists()


def test_the_shadow_reads_objects_but_not_the_config(make_repo: MakeRepo) -> None:
    repo = make_repo()
    oid = repo.commit({"a.txt": "one\n"})
    repo.run("config", "ofrenda.marker", "from-the-repository")
    with Git(repo.path) as g:
        assert g.run(["cat-file", "-t", oid]).strip() == b"commit"
        assert g.run(["config", "--get", "ofrenda.marker"], check=False) == b""
        assert (g.shadow / "objects" / "info" / "alternates").read_text().strip() == str(
            (repo.path / ".git" / "objects").resolve())


def test_the_hardening_overrides_every_key_that_can_start_a_program() -> None:
    keys = {HARDENING[i + 1].split("=", 1)[0] for i in range(0, len(HARDENING), 2)}
    assert {"core.fsmonitor", "core.hooksPath", "core.pager", "log.showSignature", "gpg.program",
            "protocol.allow", "mailmap.file"} <= keys


def test_ls_tree_reports_mode_size_and_path(make_repo: MakeRepo) -> None:
    repo = make_repo()
    repo.write({"dir/b.txt": "two\n", "a b.txt": "spaces\n"})
    os.symlink("dir/b.txt", repo.path / "link")
    repo.commit({})
    with Git(repo.path) as g:
        entries = {e.path: e for e in g.ls_tree(g.resolve("HEAD"))}
    assert entries["dir/b.txt"].size == 4 and entries["dir/b.txt"].mode == "100644"
    assert entries["a b.txt"].kind == "blob"
    assert entries["link"].mode == "120000"


def test_read_blobs_and_read_path(make_repo: MakeRepo) -> None:
    repo = make_repo()
    oid = repo.commit({"a.txt": "alpha\n", "b.bin": b"\x00\x01\n\n"})
    with Git(repo.path) as g:
        entries = {e.path: e.oid for e in g.ls_tree(oid)}
        blobs = g.read_blobs([entries["a.txt"], entries["b.bin"], "f" * 40])
        assert blobs[entries["a.txt"]] == b"alpha\n" and blobs[entries["b.bin"]] == b"\x00\x01\n\n"
        assert "f" * 40 not in blobs
        assert g.read_path(oid, "a.txt") == b"alpha\n"
        assert g.read_path(oid, "missing.txt") is None


def test_commits_that_exist_resolves_short_ids_and_drops_the_rest(make_repo: MakeRepo) -> None:
    repo = make_repo()
    first = repo.commit({"a.txt": "one\n"})
    second = repo.commit({"a.txt": "two\n"}, when="2016-01-01T00:00:00+0000")
    with Git(repo.path) as g:
        blob = g.ls_tree(second)[0].oid
        found = g.commits_that_exist([first[:9], second, "0" * 40, "not a hash", "-x", blob, first])
    assert found == [first, second]


def test_check_attr_reads_the_attributes_of_the_revision(make_repo: MakeRepo) -> None:
    repo = make_repo()
    oid = repo.commit({".gitattributes": "gen/* linguist-generated\n*.dat -diff\n", "gen/x.txt": "x\n"})
    repo.write({".gitattributes": "*.txt linguist-vendored\n"})  # the working tree says something else
    with Git(repo.path) as g:
        attrs = g.check_attr(oid, ["gen/x.txt", "d.dat", "src/a.txt"], ("linguist-generated", "linguist-vendored",
                                                                        "diff"))
    assert attrs["gen/x.txt"]["linguist-generated"] == "set"
    assert attrs["d.dat"]["diff"] == "unset"
    assert attrs["src/a.txt"]["linguist-vendored"] == "unspecified"


def test_check_mailmap_uses_the_mailmap_of_the_revision_in_a_bare_clone(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    old = repo.commit({".mailmap": "Ana Q <ana@quintero.example> <ana@old.example>\n"})
    repo.commit({".mailmap": "Ana Quintero <ana@quintero.example> <ana@old.example>\n"},
                when="2016-01-01T00:00:00+0000")
    bare = repo.bare_clone(tmp_path / "bare.git")
    # plain git in a bare clone maps with HEAD:.mailmap, whatever revision you look at
    assert git(bare, "check-mailmap", "<ana@old.example>").strip() == "Ana Quintero <ana@quintero.example>"
    with Git(bare) as g:
        assert g.check_mailmap(old, ["<ana@old.example>"]) == ["Ana Q <ana@quintero.example>"]
        head = g.resolve("HEAD")
        assert g.check_mailmap(head, ["<ana@old.example>"]) == ["Ana Quintero <ana@quintero.example>"]


def test_check_mailmap_ignores_a_mailmap_in_the_working_tree(make_repo: MakeRepo) -> None:
    repo = make_repo()
    oid = repo.commit({"a.txt": "one\n"}, author=ANA)
    repo.write({".mailmap": "Someone Else <else@elsewhere.example> <ana@quintero.example>\n"})
    assert "Someone Else" in git(repo.path, "check-mailmap", f"<{ANA[1]}>")  # plain git reads it
    with Git(repo.path) as g:
        assert g.check_mailmap(oid, [f"<{ANA[1]}>"]) == [f"<{ANA[1]}>"]


def test_is_shallow(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    repo.commit({"a.txt": "one\n"})
    repo.commit({"a.txt": "one\ntwo\n"}, when="2016-01-01T00:00:00+0000")
    shallow = tmp_path / "shallow.git"
    git(tmp_path, "clone", "-q", "--bare", "--depth", "1", f"file://{repo.path}", str(shallow))
    with Git(shallow) as g:
        assert g.is_shallow() and g.shallow_marker().strip()
    with Git(repo.path) as g:
        assert not g.is_shallow() and g.shallow_marker() == ""


def test_repo_builder_sanity(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "r")
    oid = repo.commit({"x.txt": "x\n"}, author=ANA, when="2014-05-06T07:08:09+0200")
    line = repo.run("log", "-1", "--format=%an|%ae|%ai", oid).strip()
    assert line == "Ana Quintero|ana@quintero.example|2014-05-06 07:08:09 +0200"
