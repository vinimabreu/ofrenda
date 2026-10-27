"""Synthetic repositories and a fake model. No test reaches a model or the network unless it is
marked ``real_model``. Every name and address here is invented."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

import ofrenda.model as _model

REAL_CHECK_LOCAL_MODEL = _model.check_local_model  # kept before the autouse fixture stubs it

# git used to build the fixtures ignores the machine's own config, so the tests behave the
# same on any laptop and in CI.
BASE_ENV = {
    "PATH": os.environ.get("PATH", os.defpath),
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "C.UTF-8",
}

ANA = ("Ana Quintero", "ana@quintero.example")
BRUNO = ("Bruno Takahashi", "bruno@takahashi.example")
CELIA = ("Celia Mbeki", "celia@mbeki.example")
DARIO = ("Dario Lindqvist", "dario@lindqvist.example")


def git(cwd: Path, *args: str, env: Mapping[str, str] | None = None, input: bytes | None = None) -> str:
    result = subprocess.run(["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false",
                             "-c", "core.hooksPath=" + os.devnull, *args], cwd=cwd, input=input,
                            capture_output=True, env={**BASE_ENV, "HOME": str(cwd), **(env or {})}, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout.decode(errors="replace")


class Repo:
    """A throwaway repository that commits with invented authors at fixed dates."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        git(path, "init", "-q")

    def write(self, files: Mapping[str, str | bytes | None]) -> None:
        for name, content in files.items():
            target = self.path / name
            if content is None:
                if target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")

    def commit(self, files: Mapping[str, str | bytes | None], *, author: tuple[str, str] = ANA,
               when: str = "2015-01-01T00:00:00+0000", message: str = "Change things",
               committer: tuple[str, str] | None = None, committed: str | None = None) -> str:
        self.write(files)
        who = committer or author
        env = {"GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1], "GIT_AUTHOR_DATE": when,
               "GIT_COMMITTER_NAME": who[0], "GIT_COMMITTER_EMAIL": who[1], "GIT_COMMITTER_DATE": committed or when}
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "--allow-empty", "-m", message, env=env)
        return self.head()

    def head(self) -> str:
        return git(self.path, "rev-parse", "HEAD").strip()

    def run(self, *args: str, env: Mapping[str, str] | None = None) -> str:
        return git(self.path, *args, env=env)

    def bare_clone(self, target: Path) -> Path:
        git(target.parent, "clone", "-q", "--bare", "--no-local", str(self.path), str(target))
        return target


MakeRepo = Callable[..., "Repo"]


@pytest.fixture
def make_repo(tmp_path: Path) -> MakeRepo:
    def make(name: str = "project") -> Repo:
        return Repo(tmp_path / name)
    return make


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_model: talks to a real Ollama on this machine")


@pytest.fixture(autouse=True)
def no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("real_model"):
        yield
        return
    import ofrenda.model as model

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a test tried to reach the network")

    monkeypatch.setattr(model, "_call", refuse)
    monkeypatch.setattr(model, "check_local_model", lambda *args, **kwargs: None)
    monkeypatch.delenv("NO_COLOR", raising=False)
    yield


PERSON = re.compile(r"^Person: (.+)$", re.M)
MESSAGE = re.compile(r"^\[message \d+\]\n(.*?)\n\[end of message \d+\]$", re.M | re.S)


def prompt_person(prompt: str) -> str:
    match = PERSON.search(prompt)
    return match.group(1) if match else ""


def prompt_messages(prompt: str) -> list[str]:
    return MESSAGE.findall(prompt)


class FakeModel:
    """Answers from a table keyed by person name: a dict, a reply string, or a callable
    (prompt -> reply). With no entry it writes a plain card quoting the first message's subject.
    Second readings (the tone check) are answered from ``verdicts``: the first entry whose key is
    in the sentence wins, and a sentence with no entry reads clean. Counts both kinds of call."""

    def __init__(self, answers: Mapping[str, Any] | None = None,
                 verdicts: Mapping[str, Any] | None = None) -> None:
        self.answers = dict(answers or {})
        self.verdicts = dict(verdicts or {})
        self.prompts: list[str] = []
        self.readings: list[str] = []

    @property
    def calls(self) -> int:
        return len(self.prompts)

    def __call__(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        from ofrenda.tone import TONE_SYSTEM
        if system == TONE_SYSTEM:
            self.readings.append(user)
            for needle, verdict in self.verdicts.items():
                if needle in user:
                    return verdict if isinstance(verdict, str) else json.dumps(verdict)
            return json.dumps({"death": False, "judgment": False, "gender": False})
        self.prompts.append(user)
        name = prompt_person(user)
        answer = self.answers.get(name)
        if callable(answer):
            return str(answer(user))
        if isinstance(answer, list):  # one answer per call, in order
            answer = answer.pop(0) if answer else None
        if answer is None:
            subject = prompt_messages(user)[0].split("\n", 1)[0]
            answer = {"text": f"{name} left work that still runs in this codebase.", "quotes": [subject]}
        return answer if isinstance(answer, str) else json.dumps(answer)


@pytest.fixture
def fake_model() -> FakeModel:
    return FakeModel()
