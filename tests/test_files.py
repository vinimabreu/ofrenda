from __future__ import annotations

import pytest

from conftest import MakeRepo
from ofrenda import files
from ofrenda.files import attribute_rule, content_rule, count_lines, path_rule, select
from ofrenda.gitread import Git


@pytest.mark.parametrize("path, reason", [
    ("node_modules/left-pad/index.js", "vendored"),
    ("web/vendor/lib.js", "vendored"),
    ("src/third_party/x.c", "vendored"),
    ("dist/app.js", "vendored"),
    ("package-lock.json", "generated"),
    ("sub/poetry.lock", "generated"),
    ("go.sum", "generated"),
    ("static/app.min.js", "generated"),
    ("static/app.css.map", "generated"),
    ("proto/thing_pb2.py", "generated"),
    ("docs/_locale/xx/LC_MESSAGES/api.po", "generated"),
    ("docs/messages.pot", "generated"),
    ("src/app.py", None),
    ("vendor.py", None),  # only directories named vendor count
    ("docs/distribution.md", None),
])
def test_path_rules(path: str, reason: str | None) -> None:
    assert path_rule(path) == reason


def test_attribute_rules() -> None:
    assert attribute_rule({"linguist-vendored": "set"}) == "vendored"
    assert attribute_rule({"linguist-generated": "true"}) == "generated"
    assert attribute_rule({"binary": "set"}) == "binary"
    assert attribute_rule({"diff": "unset"}) == "binary"
    assert attribute_rule({"diff": "unspecified", "linguist-generated": "unspecified"}) is None


def test_content_rules() -> None:
    assert content_rule(b"text\x00more\n") == "binary"
    assert content_rule(b"") == "empty"
    assert content_rule(b"x" * 900 + b"\n") == "long-lines"
    assert content_rule(b"short\nlines\n") is None
    assert content_rule(b"a" * 9000 + b"\x00") == "long-lines"  # a NUL after the probe window is not looked at


def test_count_lines_matches_blame() -> None:
    assert count_lines(b"") == 0
    assert count_lines(b"a") == 1
    assert count_lines(b"a\n") == 1
    assert count_lines(b"a\nb") == 2
    assert count_lines(b"\n\n") == 2


def test_select_keeps_text_and_counts_every_skip(make_repo: MakeRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(files, "MAX_BYTES", 2000)
    repo = make_repo()
    oid = repo.commit({
        "src/app.py": "print('hello')\n",
        "README.md": "# hello\n",
        "node_modules/x/index.js": "module.exports = 1\n",
        "yarn.lock": "lock\n",
        "static/site.min.js": "var a=1;\n",
        "assets/logo.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00",
        "data/big.txt": "line\n" * 500,
        "data/one-line.json": "[" + "1," * 400 + "1]\n",
        "empty.txt": "",
        "gen/out.txt": "generated\n",
        "blob.dat": "looks like text\n",
        ".gitattributes": "gen/** linguist-generated\n*.dat binary\n",
    })
    with Git(repo.path) as g:
        selection = select(g, oid)
    assert [k.path for k in selection.kept] == [".gitattributes", "README.md", "src/app.py"]
    assert dict(selection.skipped) == {"vendored": 1, "generated": 3, "binary": 2, "large": 1, "long-lines": 1,
                                       "empty": 1}
    assert selection.files_seen == 12
    assert {k.path: k.lines for k in selection.kept}["src/app.py"] == 1


def test_symlinks_are_not_files(make_repo: MakeRepo) -> None:
    import os
    repo = make_repo()
    repo.write({"a.txt": "one\n"})
    os.symlink("a.txt", repo.path / "link.txt")
    oid = repo.commit({})
    with Git(repo.path) as g:
        selection = select(g, oid)
    assert [k.path for k in selection.kept] == ["a.txt"]
    assert selection.skipped["not-a-file"] == 1


def test_a_submodule_is_not_a_file(make_repo: MakeRepo) -> None:
    repo = make_repo()
    first = repo.commit({"a.txt": "one\n"})
    repo.run("update-index", "--add", "--cacheinfo", f"160000,{first},sub")
    repo.run("commit", "-q", "-m", "Add a submodule", env={"GIT_AUTHOR_NAME": "Ana", "GIT_AUTHOR_EMAIL": "a@b.example",
                                                         "GIT_COMMITTER_NAME": "Ana",
                                                         "GIT_COMMITTER_EMAIL": "a@b.example"})
    with Git(repo.path) as g:
        selection = select(g, g.resolve("HEAD"))
    assert [k.path for k in selection.kept] == ["a.txt"]
    assert selection.skipped["not-a-file"] == 1
