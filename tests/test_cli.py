from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import ANA, BRUNO, CELIA, DARIO, FakeModel, MakeRepo, Repo
from ofrenda import __version__, model
from ofrenda.cli import main

DAY = 86400


def iso(ts: int) -> str:
    from datetime import UTC, datetime
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S+0000")


def history(repo: Repo) -> None:
    t = 1_300_000_000
    repo.commit({"README.md": "# Lantern\n\nA small web toolkit.\n"}, author=ANA, when=iso(t),
                message="Start the lantern toolkit")
    repo.commit({"lantern/routing.py": "".join(f"def route_{i}(path):\n    return path.split('/')[{i}]\n"
                                               for i in range(5))},
                author=CELIA, when=iso(t + 30 * DAY), message="Add the router\n\nPaths are split once and cached.")
    repo.commit({"lantern/sessions.py": "class Session:\n    def __init__(self):\n        self.data = {}\n"
                                        "        self.dirty = False\n"},
                author=DARIO, when=iso(t + 60 * DAY), message="Add server side sessions")
    repo.commit({"lantern/app.py": "from lantern import routing\n\nAPP_NAME = 'lantern'\n"}, author=BRUNO,
                when=iso(t + 2000 * DAY), message="Wire the app together")


@pytest.fixture
def lantern(make_repo: MakeRepo) -> Repo:
    repo = make_repo("lantern")
    history(repo)
    return repo


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    model_ = FakeModel()

    def asker(**kwargs: Any) -> FakeModel:
        if not kwargs.get("allow_remote") and not model.is_loopback(kwargs.get("host", model.DEFAULT_HOST)):
            raise model.RemoteHostRefused("not this machine")
        return model_

    monkeypatch.setattr(model, "asker", asker)
    return model_


def test_cards_on_the_terminal_and_in_three_files(lantern: Repo, fake: FakeModel, tmp_path: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    code = main([str(lantern.path), "--cache", str(tmp_path / "cache"), "--md", str(out / "OFRENDA.md"),
                 "--html", str(out / "ofrenda.html"), "--json", str(out / "ofrenda.json")])
    assert code == 0
    text = capsys.readouterr().out
    flat = " ".join(text.split())
    assert "4 people still have lines in lantern" in flat and "3 of them made no commit in the 730 days" in flat
    headers = [line.split(")   ", 1)[1] for line in text.splitlines() if line.startswith("   )   ")]
    assert headers == [CELIA[0], DARIO[0], ANA[0]]  # most lines first
    assert BRUNO[0] + "\n" not in text  # he committed at the revision
    assert fake.calls == 3
    data = json.loads((out / "ofrenda.json").read_text(encoding="utf-8"))
    assert [c["person"]["name"] for c in data["cards"]] == [CELIA[0], DARIO[0], ANA[0]]
    assert {c["source"] for c in data["cards"]} == {"model"} and data["card_stats"]["quotes_verified"] == 3
    assert data["elder"]["author"] == ANA[0] and data["elder"]["text"] == "# Lantern"
    assert (out / "OFRENDA.md").read_text(encoding="utf-8").startswith("# Ofrenda for lantern")
    assert "<!doctype html>" in (out / "ofrenda.html").read_text(encoding="utf-8")
    cache = tmp_path / "cache"
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in cache.iterdir())


def test_a_second_run_asks_the_model_nothing(lantern: Repo, fake: FakeModel, tmp_path: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    args = [str(lantern.path), "--cache", str(tmp_path / "cache")]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out
    assert fake.calls == 3 and first == second


def test_top_and_quiet_days(lantern: Repo, fake: FakeModel, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(lantern.path), "--no-cache", "--top", "1"]) == 0
    assert fake.calls == 1 and CELIA[0] in capsys.readouterr().out
    assert main([str(lantern.path), "--no-cache", "--quiet-days", "5000"]) == 0
    assert "Nobody here has moved on yet" in capsys.readouterr().out
    assert main([str(lantern.path), "--no-cache", "--top", "0", "--quiet-days", "0", "--no-model"]) == 0
    assert "3 of them" in " ".join(capsys.readouterr().out.split())  # the revision is Bruno's own commit


def test_no_model_never_builds_a_client(lantern: Repo, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    def refuse(**kwargs: Any) -> None:
        raise AssertionError("no model was asked for")

    monkeypatch.setattr(model, "asker", refuse)
    assert main([str(lantern.path), "--no-model", "--no-cache", "--host", "10.0.0.5"]) == 0
    out = capsys.readouterr().out
    assert "in their words:" in out and "(from git alone)" in out


def test_a_remote_host_is_refused_before_any_blame(lantern: Repo, fake: FakeModel,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(lantern.path), "--no-cache", "--host", "192.168.1.20:11434"]) == 2
    assert "--allow-remote-model" in capsys.readouterr().err and fake.calls == 0


def test_an_unreachable_model_says_what_to_do(lantern: Repo, monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    def down(system: str, user: str, schema: Any = None) -> str:
        raise model.ModelUnavailable("Ollama is not reachable at 127.0.0.1:11434; start it with: ollama serve")

    monkeypatch.setattr(model, "asker", lambda **kwargs: down)
    assert main([str(lantern.path), "--no-cache"]) == 2
    err = capsys.readouterr().err
    assert "ollama serve" in err and "--no-model" in err


@pytest.mark.parametrize("args, message", [
    (["--rev", "no-such-branch"], "is not a commit"),
    (["--ignore-rev", "nope"], "is not a commit"),
])
def test_bad_revisions_exit_two(lantern: Repo, args: list[str], message: str,
                                capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(lantern.path), "--no-model", "--no-cache", *args]) == 2
    assert message in capsys.readouterr().err


def test_a_folder_that_is_not_a_repository_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path), "--no-model", "--no-cache"]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_an_older_revision(lantern: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(lantern.path), "--no-model", "--no-cache", "--rev", "HEAD~1", "--quiet-days", "10"]) == 0
    out = capsys.readouterr().out
    assert "3 people still have lines in lantern" in " ".join(out.split()) and BRUNO[0] not in out


def test_the_default_is_the_repository_you_are_in(lantern: Repo, monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(lantern.path / "lantern")
    assert main(["--no-model", "--no-cache"]) == 0
    assert "ofrenda for lantern" in capsys.readouterr().out
    monkeypatch.chdir(lantern.path.parent)
    assert main(["lantern", "--no-model", "--no-cache", "--md", "out/OFRENDA.md"]) == 0
    assert (lantern.path.parent / "out" / "OFRENDA.md").is_file()


def test_version_and_module_entry_point(lantern: Repo) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    src = Path(__file__).resolve().parent.parent / "src"
    result = subprocess.run([sys.executable, "-m", "ofrenda", str(lantern.path), "--no-model", "--no-cache"],
                            capture_output=True, text=True, check=False,
                            env={"PYTHONPATH": str(src), "NO_COLOR": "1", "PATH": os.environ.get("PATH", "")})
    assert result.returncode == 0, result.stderr
    assert "ofrenda for lantern" in result.stdout and "\x1b" not in result.stdout
    assert __version__ == "0.1.0"
