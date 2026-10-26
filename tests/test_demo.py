"""The demo repository behind the README: same commits on every machine, same facts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from ofrenda.blame import BlameOptions
from ofrenda.gitread import Git
from ofrenda.ledger import read_ledger

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make_demo.py"


@pytest.fixture(scope="module")
def almanac(tmp_path_factory: pytest.TempPathFactory) -> Path:
    spec = importlib.util.spec_from_file_location("make_demo", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path_factory.mktemp("demo") / "almanac"
    module.build(path)
    return path


def test_the_demo_history_is_the_same_everywhere(almanac: Path) -> None:
    with Git(almanac) as g:
        assert g.resolve("HEAD") == "3aff65026debda92e05289fc36c2b42249356c52"


def test_the_demo_facts(almanac: Path) -> None:
    with Git(almanac) as g:
        ledger = read_ledger(g)
    moved_on = ledger.ghosts(730)
    assert [p.name for p in moved_on] == ["Ines Okonkwo", "Tomas Varga", "Mei Lindqvist", "Rafael Oyelaran",
                                          "Sanna Petrova"]
    assert {p.name for p in ledger.people} - {p.name for p in moved_on} == {"Noor Halvorsen"}
    assert ledger.lines == 213 and ledger.bot_lines == 2
    ines = moved_on[0]
    assert ines.commits == 4  # three under her own address and one under the old one, joined by the .mailmap
    assert ines.top.subject == "Start almanac, a small job scheduler"
    assert ledger.elder is not None and (ledger.elder.path, ledger.elder.number) == ("LICENSE", 1)
    assert [c.subject for c in ledger.suspects] == ["Reformat with the code formatter"]
    with Git(almanac) as g:
        no_copies = read_ledger(g, options=BlameOptions(copies=0))
    # without -C the module move takes the credit for the lines it moved
    before = {p.name: p.lines for p in no_copies.people}
    assert before["Noor Halvorsen"] > {p.name: p.lines for p in ledger.people}["Noor Halvorsen"]
