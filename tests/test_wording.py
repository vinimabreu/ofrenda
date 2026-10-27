"""The card check against the wording an audit got through it, kept as regression tests.

Each sentence comes with a quote that is really in the person's messages, so the only reason to
reject it is the wording under test."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ofrenda import wording
from ofrenda.cards import Answer, Material, check_card, find_quote, word_count
from ofrenda.ledger import CommitFact

M1 = CommitFact("a" * 40, "2012-06-30", "Retry failed jobs with backoff", 20,
                "Retry failed jobs with backoff\n\nA job that fails waits longer before each new attempt, up to a "
                "ceiling, with some jitter so that many workers do not retry in step.")
M2 = CommitFact("b" * 40, "2015-03-03", "Handle the hour that repeats when clocks go back", 9,
                "Handle the hour that repeats when clocks go back\n\nWhen a wall-clock time happens twice, a job runs "
                "at the first one and not again an hour later.")
M3 = CommitFact("c" * 40, "2016-01-01", "Unbreak the build on Windows", 3,
                "Unbreak the build on Windows & add a test")
TOMAS = Material("Tomas Varga", "almanac", (M1, M2, M3), ("almanac/retry.py", "almanac/zones.py"),
                 "almanac/retry.py", ("def backoff(attempt, base=2.0, ceiling=300.0):",))
Q = ("Retry failed jobs with backoff",)


def reason(text: str, quotes: tuple[str, ...] = Q) -> str | None:
    return check_card(Answer(text, quotes), TOMAS)


def test_the_plain_sentence_passes() -> None:
    assert reason("Tomas Varga made failed jobs retry with backoff, so that workers do not retry in step.") is None


@pytest.mark.parametrize("text", [
    "Tomas Varga is no longer with us, but their retry logic still runs.",
    "Tomas Varga is gone but not forgotten; they made failed jobs retry with backoff.",
    "Tomas Varga will be missed by everyone who relies on retries with backoff.",
    "Tomas Varga was laid to rest, and their retry logic outlived them.",
    "The retry logic Tomas Varga wrote has outlived them.",
    "We sadly lost Tomas Varga, whose code still retries failed jobs.",
    "Beloved Tomas Varga rests now; their retries are eternal.",
    "Tomas Varga is buried here beside the retry logic they wrote.",
    "Until their last breath Tomas Varga kept failed jobs retrying.",
    "Honoring the memory of Tomas Varga, who taught the scheduler to retry.",
    "Tomas Varga, who left us too soon, made failed jobs retry with backoff.",
    "Tomas Varga has passed, but failed jobs still retry with backoff.",
    "Tomas Varga is no more, yet failed jobs still retry with backoff.",
    "In loving remembrance of Tomas Varga, failed jobs retry with backoff.",
    "Tomas Varga sleeps while failed jobs retry with backoff.",
    "The skeleton of Tomas Varga still rattles in the retry code.",
    "Tomas Varga now smiles from a sugar skull beside the retry logic.",
    "Tomas Varga made failed jobs retry with backoff, r.i.p.",
    "Tomas Varga falleci\u00f3, pero su l\u00f3gica de reintentos sigue viva.",
    "Tomas Varga fallecio, pero su logica de reintentos sigue viva.",
    "Tomas Varga, que en paz descanse, hizo que los trabajos fallidos se reintenten.",
    "El difunto Tomas Varga escribi\u00f3 los reintentos con espera.",
    "Tomas Varga faleceu; os jobs com falha tentam de novo.",
])
def test_death_and_mourning_wording_is_refused(text: str) -> None:
    assert "as if the person died" in (reason(text) or "")


@pytest.mark.parametrize("text", [
    "Tomas Varga made failed jobs retry after a lost connection.",
    "Tomas Varga made sure no job is gone for good when a worker fails.",
    "Tomas Varga made failed jobs retry with backoff, and the hour that repeats runs only once.",
])
def test_technical_uses_of_lost_and_gone_still_pass(text: str) -> None:
    assert reason(text) is None


@pytest.mark.parametrize("text, word", [
    ("Tomas Varga wrote sloppy, careless retry code that nobody wanted to maintain.", "sloppy"),
    ("Tomas Varga was a lazy and incompetent developer who only added retries.", "lazy"),
    ("Tomas Varga era descuidado con los reintentos.", "descuidado"),
])
def test_judging_the_person_is_refused(text: str, word: str) -> None:
    assert reason(text) == f'the sentence uses "{word}", which judges the person'


@pytest.mark.parametrize("text", [
    "Mr. Varga made failed jobs retry with backoff, a true gentleman.",
    "This man, Tomas Varga, made failed jobs retry with backoff.",
    "Tomas Varga was the kind of guy who made failed jobs retry.",
    "Tomas Varga made failed jobs retry; she also handled clocks.",
    "Tomas Varga hizo los reintentos y \u00e9l escribi\u00f3 la espera.",
])
def test_gendered_wording_is_refused(text: str) -> None:
    assert "does not guess anyone's gender" in (reason(text) or "")


def test_a_man_page_is_not_a_man() -> None:
    assert wording.gendered_word("They wrote the man page for retries.", "Tomas Varga") is None


@pytest.mark.parametrize("text, word", [
    ("Tomas Varga wrote fifteen retry paths so that failed jobs come back with backoff.", "fifteen"),
    ("Tomas Varga wrote one retry path so that failed jobs come back with backoff.", "one"),
    ("Tomas Varga wrote half of the scheduler, including retries with backoff.", "half"),
    ("Tomas Varga wrote most of the scheduler, nearly ninety percent of it.", "ninety"),
    ("Tomas Varga spent eighteen months making failed jobs retry with backoff.", "eighteen"),
    ("Tomas Varga wrote a third of the scheduler, and its retries with backoff.", "a third"),
    ("Tomas Varga spent many days making failed jobs retry with backoff.", "days"),
    ("For a decade Tomas Varga kept failed jobs retrying.", "decade"),
    ("Tomas Varga wrote thirteen, fourteen, sixteen, seventeen and nineteen fixes.", "thirteen"),
    ("Tomas Varga escribi\u00f3 quince reintentos durante diez a\u00f1os.", "quince"),
])
def test_amounts_in_words_are_refused(text: str, word: str) -> None:
    assert reason(text) == f'the sentence carries a date or an amount ("{word}")'


def test_an_amount_copied_with_its_neighbour_passes() -> None:
    assert reason("Tomas Varga handled the hour that repeats when clocks go back.") is None
    assert reason("Tomas Varga wrote eighteen hours of retries.") is not None


def test_percent_sign_and_unusual_numerals_are_refused() -> None:
    assert reason("Tomas Varga made failed jobs retry with backoff in most cases, about 90%.") is not None
    assert reason("Tomas Varga made failed jobs retry with backoff\u00b2.") == "the sentence carries a number"


@pytest.mark.parametrize("text, name", [
    ("Google adopted the retry logic Tomas Varga wrote for failed jobs.", "Google"),
    ("Tomas Varga made failed jobs retry with backoff. Microsoft copied it.", "Microsoft"),
])
def test_an_unknown_name_at_the_start_of_a_sentence_is_refused(text: str, name: str) -> None:
    assert reason(text) == f'the sentence names "{name}", which is not in their commit messages or files'


@pytest.mark.parametrize("text", [
    "They made failed jobs retry with backoff.",
    "Retries with backoff came from Tomas Varga.",
    "Workers do not retry in step because of Tomas Varga.",
])
def test_plain_starters_and_words_from_the_messages_pass(text: str) -> None:
    assert reason(text) is None


@pytest.mark.parametrize("text", [
    "Tomas Varga summed it up as 'never trust the clock, always retry'.",
    "Tomas Varga wrote \u00abnever trust the clock\u00bb about retries.",
    "Tomas Varga wrote \u2018never trust the clock\u2019 about retries.",
    "Tomas Varga wrote \u201cnever trust the clock\u201d about retries.",
])
def test_invented_quotes_in_any_quotation_marks_are_refused(text: str) -> None:
    assert "which is not in their commit messages" in (reason(text) or "")


@pytest.mark.parametrize("text", [
    'Tomas Varga wrote "never trust the clock about retries.',
    "Tomas Varga wrote \u201cnever trust the clock about retries.",
    "Tomas Varga wrote \u00abnever trust the clock about retries.",
])
def test_a_quotation_mark_left_open_is_refused(text: str) -> None:
    assert reason(text) == "the sentence opens a quotation mark and never closes it"


def test_quoting_the_messages_in_any_marks_passes() -> None:
    assert reason("Tomas Varga wrote 'Retry failed jobs with backoff' and it still runs.") is None
    assert reason("Tomas Varga's retries wait longer before each new attempt.") is None


def test_control_characters_and_markup_are_refused() -> None:
    assert reason("Tomas Varga made failed jobs retry with backoff.\x1b]52;c;cGF3bmVk\x07") == \
        "the sentence carries control characters or markup"
    assert reason("Tomas Varga made failed jobs retry <img src=x onerror=alert(1)> with backoff.") == \
        "the sentence carries control characters or markup"


# -- quotes on word boundaries ---------------------------------------------------------------------

@pytest.mark.parametrize("quote", ["break the build on Windows", "ailed jobs with backoff", "Retry failed jobs wit",
                                   "nbreak the build"])
def test_a_quote_that_starts_or_ends_inside_a_word_is_refused(quote: str) -> None:
    assert find_quote(quote, TOMAS.messages) is None
    assert "is not in any of their commit messages" in (reason("Tomas Varga fixed the build.", (quote,)) or "")


def test_a_quote_on_word_boundaries_passes() -> None:
    assert find_quote("Unbreak the build on Windows", TOMAS.messages) is not None
    assert find_quote("the build on Windows", TOMAS.messages) is not None


def test_symbols_are_not_words() -> None:
    assert word_count("& add") == 1 and word_count("-- &") == 0 and word_count("add a test") == 3
    assert "too short" in (reason("Tomas Varga fixed the build.", ("Windows &",)) or "")


# -- the documented limits: these still pass, and the README says so --------------------------------

@pytest.mark.parametrize("text", [
    "Tomas Varga added redis and kubernetes support to make failed jobs retry.",
    "Tomas Varga built the cron-like expressions and the sorted job list.",
])
def test_lowercase_claims_the_messages_do_not_make_still_pass(text: str) -> None:
    assert reason(text) is None


# -- the held-out sets are never part of the lists ---------------------------------------------------

HELDOUT = Path(__file__).resolve().parent / "heldout"


def test_the_held_out_sets_are_where_the_measurement_expects_them() -> None:
    sizes = {name: len([line for line in (HELDOUT / f"{name}.txt").read_text(encoding="utf-8").splitlines()
                        if line and not line.startswith("#")]) for name in ("death", "judgment", "gendered")}
    assert sizes == {"death": 45, "judgment": 26, "gendered": 20}


@pytest.mark.parametrize("term", ["churchyard", "daisies", "bucket", "mortal coil", "maker", "saints", "flatlined",
                                  "succumbed", "expired", "ancestors", "cielo", "botas", "estrela", "outlasted",
                                  "crossed over", "better place", "taken from", "spaghetti", "mediocre", "clueless",
                                  "garbage", "mister", "madame", "fellow", "chap", "uncle", "queen", "godfather"])
def test_no_term_that_only_the_held_out_sets_use_is_on_a_list(term: str) -> None:
    for pattern in (wording.DEATH, wording.JUDGMENT, wording.GENDERED, wording.TITLES):
        assert not re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", pattern.pattern)


def test_the_independent_held_out_set_is_complete() -> None:
    folder = HELDOUT.parent / "heldout-v2"
    sizes = {name: len([line for line in (folder / f"{name}.txt").read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.startswith("#")])
             for name in ("death", "judgment", "gendered", "clean")}
    assert sizes == {"death": 50, "judgment": 35, "gendered": 30, "clean": 80}


# -- technical prose that shares words with the lists (fixed after a second audit) ----------------

TECH = Material("Tomas Varga", "almanac", (M1, M2, M3, CommitFact(
    "d" * 40, "2017-01-01", "Add two-factor login", 4,
    "Add two-factor login\n\nVendor a third-party parser and keep the new one behind a flag.")),
    ("almanac/retry.py",), "almanac/retry.py", ())


@pytest.mark.parametrize("text", [
    "Tomas Varga added lazy loading so failed jobs retry with backoff.",
    "Tomas Varga lazily loads the retry policy for failed jobs.",
    "Tomas Varga made failed jobs retry with backoff to resist a man-in-the-middle.",
    "Tomas Varga made failed jobs retry with backoff after a late reply from a worker.",
    "Tomas Varga made sure failed jobs retry with backoff when the parent dies.",
    "Tomas Varga removed dead code and made failed jobs retry with backoff.",
    "Tomas Varga sent failed jobs to a dead letter queue after the backoff.",
    "Tomas Varga kept tombstones for jobs that retry with backoff.",
    "Tomas Varga made sure the retry state lives on disk.",
    "Tomas Varga added late binding to the retry policy for failed jobs.",
    "Tomas Varga fixed the grave accent in job names that retry with backoff.",
    "Tomas Varga removed ghost text from failed jobs that retry with backoff.",
    "Tomas Varga kept remembered hosts out of the retry loop for failed jobs.",
    "Tomas Varga made failed jobs retry with backoff in the parent process and the child process.",
    "Tomas Varga added two-factor login, and failed jobs retry with backoff.",
    "Tomas Varga vendored a third-party parser, and failed jobs retry with backoff.",
    "Tomas Varga kept the new one behind a flag, and failed jobs retry with backoff.",
])
def test_technical_phrases_pass(text: str) -> None:
    assert check_card(Answer(text, Q), TECH) is None


@pytest.mark.parametrize("text", [
    "Tomas Varga was lazy about failed jobs.",
    "Tomas Varga is dead, and failed jobs still retry with backoff.",
    "Tomas Varga added two-step login.",
])
def test_the_same_words_about_the_person_or_uncopied_still_fail(text: str) -> None:
    assert check_card(Answer(text, Q), TECH) is not None


@pytest.mark.parametrize("text", [
    "Tomas Varga, the father of the retry logic, made failed jobs back off.",
    "Tomas Varga, the godfather of retries, taught failed jobs to back off.",
    "Tomas Varga, a true craftsman, made failed jobs retry with backoff.",
    "Tomas Varga looked after failed jobs like a big brother.",
    "Tomas Varga, a husband who loved retries, made failed jobs back off.",
    "Tomas Varga fue el padrino de los reintentos.",
])
def test_kinship_and_role_nouns_are_gendered(text: str) -> None:
    assert "gender" in (check_card(Answer(text, Q), TECH) or "")
