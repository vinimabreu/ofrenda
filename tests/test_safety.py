"""A repository can ask git to run programs. ofrenda must never let it.

Each test plants one way in, shows that plain git really runs the planted program
(the control), then runs ofrenda on the same repository and checks that nothing ran.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from conftest import ANA, BRUNO, MakeRepo, Repo, git
from ofrenda.cli import main
from ofrenda.gitread import Git
from ofrenda.ledger import read_ledger

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the planted programs are shell scripts")


def plant(tmp_path: Path, name: str) -> tuple[Path, Path]:
    """A script that leaves a marker file when anything runs it."""
    marker = tmp_path / f"ran-{name}"
    script = tmp_path / f"{name}.sh"
    script.write_text(f'#!/bin/sh\ntouch "{marker}"\ncat "$1" 2>/dev/null\nexit 0\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script, marker


def run_ofrenda(path: Path, tmp_path: Path) -> None:
    with Git(path) as g:
        ledger = read_ledger(g)
    assert ledger.lines > 0
    out = tmp_path / "out"
    assert main([str(path), "--no-model", "--no-cache", "--quiet-days", "0", "--md", str(out / "o.md"),
                 "--html", str(out / "o.html"), "--json", str(out / "o.json")]) == 0


def base(repo: Repo) -> None:
    repo.commit({"app.py": "def main():\n    return 'hello'\n"}, author=ANA, when="2014-01-01T00:00:00+0000")
    repo.commit({"app.py": "def main():\n    return 'hello, world'\n"}, author=BRUNO,
                when="2015-01-01T00:00:00+0000")


def test_a_textconv_driver_never_runs(make_repo: MakeRepo, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo()
    base(repo)
    script, marker = plant(tmp_path, "textconv")
    repo.commit({".gitattributes": "* diff=evil\n"}, author=ANA, when="2015-02-01T00:00:00+0000")
    repo.run("config", "diff.evil.textconv", str(script))
    repo.run("blame", "HEAD", "--", "app.py")
    assert marker.exists(), "control: plain git blame runs the textconv driver"
    marker.unlink()
    run_ofrenda(repo.path, tmp_path)
    assert not marker.exists()


def test_fsmonitor_never_runs(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    base(repo)
    script, marker = plant(tmp_path, "fsmonitor")
    repo.run("config", "core.fsmonitor", str(script))
    repo.run("status")
    assert marker.exists(), "control: plain git status runs the fsmonitor hook"
    marker.unlink()
    run_ofrenda(repo.path, tmp_path)
    assert not marker.exists()


def test_a_signature_program_never_runs(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    base(repo)
    script, marker = plant(tmp_path, "gpg")
    tree = repo.run("rev-parse", "HEAD^{tree}").strip()
    parent = repo.head()
    signed = (f"tree {tree}\nparent {parent}\nauthor {ANA[0]} <{ANA[1]}> 1430000000 +0000\n"
              f"committer {ANA[0]} <{ANA[1]}> 1430000000 +0000\ngpgsig -----BEGIN PGP SIGNATURE-----\n \n"
              " iQEzBAABCAAdFiEE\n -----END PGP SIGNATURE-----\n\nA signed commit\n")
    oid = git(repo.path, "hash-object", "-t", "commit", "-w", "--stdin", input=signed.encode()).strip()
    repo.run("update-ref", "refs/heads/main", oid)
    repo.run("config", "log.showSignature", "true")
    repo.run("config", "gpg.program", str(script))
    repo.run("log", "-1", "--format=%H")
    assert marker.exists(), "control: plain git log runs gpg.program on a signed commit"
    marker.unlink()
    run_ofrenda(repo.path, tmp_path)
    assert not marker.exists()


def test_an_external_diff_pager_and_filters_never_run(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    base(repo)
    external, external_marker = plant(tmp_path, "external")
    pager, pager_marker = plant(tmp_path, "pager")
    smudge, smudge_marker = plant(tmp_path, "smudge")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for hook in ("post-checkout", "post-merge", "reference-transaction", "pre-auto-gc"):
        script, _ = plant(hooks, hook)
        script.rename(hooks / hook)
    repo.commit({".gitattributes": "*.py filter=evil\n"}, author=ANA, when="2015-02-01T00:00:00+0000")
    for key, value in (("diff.external", str(external)), ("core.pager", str(pager)), ("pager.log", str(pager)),
                       ("filter.evil.smudge", str(smudge)), ("filter.evil.clean", str(smudge)),
                       ("core.hooksPath", str(hooks)), ("core.sshCommand", str(external)),
                       ("blame.ignoreRevsFile", "does-not-exist"), ("core.alternateRefsCommand", str(external))):
        repo.run("config", key, value)
    repo.run("diff", "HEAD~2", "HEAD")
    assert external_marker.exists(), "control: plain git diff runs diff.external"
    assert smudge_marker.exists(), "control: and the smudge filter, to write the files it compares"
    for marker in tmp_path.glob("ran-*"):
        marker.unlink()
    run_ofrenda(repo.path, tmp_path)
    assert not external_marker.exists() and not pager_marker.exists() and not smudge_marker.exists()
    assert not list(hooks.glob("ran-*")) and not list(tmp_path.glob("ran-*"))


def test_a_partial_clone_is_never_fetched_from(make_repo: MakeRepo, tmp_path: Path,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo()
    base(repo)
    repo.run("config", "uploadpack.allowFilter", "true")
    partial = tmp_path / "partial.git"
    git(tmp_path, "clone", "-q", "--bare", "--filter=blob:none", f"file://{repo.path}", str(partial))
    objects_before = sorted(p.name for p in (partial / "objects" / "pack").iterdir())
    with Git(partial) as g:
        ledger = read_ledger(g)
    assert ledger.lines == 0 and ledger.skipped == {"unreadable": 1}
    assert sorted(p.name for p in (partial / "objects" / "pack").iterdir()) == objects_before
    assert main([str(partial), "--no-model", "--no-cache"]) == 2
    assert "could not be read" in capsys.readouterr().err
    # control: plain git fetches the missing blob on demand
    assert "hello, world" in git(partial, "cat-file", "-p", "HEAD:app.py")
    assert sorted(p.name for p in (partial / "objects" / "pack").iterdir()) != objects_before


def test_nothing_is_written_inside_the_repository(make_repo: MakeRepo, tmp_path: Path) -> None:
    repo = make_repo()
    base(repo)
    def snapshot() -> dict[str, float]:
        return {str(p.relative_to(repo.path)): p.stat().st_mtime for p in repo.path.rglob("*")}
    before = snapshot()
    run_ofrenda(repo.path, tmp_path)
    assert snapshot() == before
