"""The one test that talks to a real model. Skipped when Ollama or the model is not on this machine."""

from __future__ import annotations

import pytest

from conftest import ANA, CELIA, MakeRepo
from ofrenda import model
from ofrenda.cards import Cardsmith
from ofrenda.gitread import Git
from ofrenda.ledger import read_ledger


def _ready() -> bool:
    try:
        return model.digest(model.DEFAULT_MODEL) is not None
    except (model.ModelUnavailable, model.RemoteHostRefused):
        return False


@pytest.mark.real_model
def test_the_local_model_writes_a_card_and_the_check_holds(make_repo: MakeRepo) -> None:
    if not _ready():
        pytest.skip(f"no Ollama with {model.DEFAULT_MODEL} on this machine")
    repo = make_repo("almanac")
    repo.commit({"almanac/scheduler.py": "".join(f"def step_{i}(job):\n    return job.next({i})\n" for i in range(6))},
                author=CELIA, when="2012-03-04T10:00:00+0000",
                message="Teach the scheduler about time zones\n\nJobs now keep the zone they were created in, so a "
                        "job set for the morning still runs in the morning after a clock change.")
    repo.commit({"README.md": "# almanac\n"}, author=ANA, when="2019-01-01T10:00:00+0000", message="Add a readme")
    with Git(repo.path) as g:
        ledger = read_ledger(g)
    smith = Cardsmith(model.asker(), model=model.DEFAULT_MODEL)
    [card] = smith.cards(ledger, ledger.ghosts(730))
    assert card.person.name == CELIA[0]
    assert card.source in ("model", "model-retry", "fallback")
    if card.source != "fallback":
        assert card.text and card.quotes
        assert all(q.oid == ledger.people[0].top.oid for q in card.quotes)
