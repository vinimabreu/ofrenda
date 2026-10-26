"""The seed measurement on invented data: every broken answer must be caught."""

from __future__ import annotations

from ofrenda.cards import Answer, Material, check_card
from ofrenda.ledger import CommitFact
from ofrenda.tamper import seeds_for, measure

MESSAGES = (
    CommitFact("a" * 40, "2012-03-04", "Teach the scheduler about time zones", 30,
               "Teach the scheduler about time zones\n\nJobs now keep the zone they were created in, so a job set\n"
               "for the morning still runs in the morning after a clock change."),
    CommitFact("b" * 40, "2012-05-06", "Retry failed jobs with backoff", 20,
               "Retry failed jobs with backoff\n\nA job that fails waits longer before each new attempt."),
)
OTHER = (CommitFact("c" * 40, "2013-01-01", "Render the dashboard in one pass", 5,
                    "Render the dashboard in one pass\n\nThe page used to query every widget on its own."),)
MATERIAL = Material("Ines Okonkwo", "almanac", MESSAGES, ("almanac/scheduler.py", "almanac/retry.py"),
                    "almanac/scheduler.py", ("def next_run(job):",))
OTHER_MATERIAL = Material("Tomas Varga", "almanac", OTHER, ("almanac/dashboard.py",), "almanac/dashboard.py", ())
ANSWER = Answer("Ines Okonkwo made scheduled jobs respect their own time zone and retry gently when they fail.",
                ("Jobs now keep the zone they were created in", "waits longer before each new attempt"))
OTHER_ANSWER = Answer("Tomas Varga made the dashboard draw at once.", ("Render the dashboard in one pass",))


def test_the_original_answers_pass() -> None:
    assert check_card(ANSWER, MATERIAL) is None
    assert check_card(OTHER_ANSWER, OTHER_MATERIAL) is None


def test_every_seed_kind_is_made() -> None:
    kinds = {s.kind for s in seeds_for(ANSWER, MATERIAL, [OTHER_MATERIAL])}
    assert {"quote-word-swapped", "quote-word-dropped", "quote-word-added", "quote-case-changed", "quote-homoglyph",
            "quote-joined-across-messages", "quote-from-someone-else", "quote-invented", "quotes-missing",
            "sentence-digit", "sentence-hash", "sentence-path", "sentence-death-passed-away", "sentence-death-rip",
            "sentence-pronoun", "sentence-invented-name", "sentence-embedded-quote", "sentence-number-word",
            "sentence-judgment", "sentence-gendered-noun", "sentence-single-quoted-invented",
            "sentence-guillemets-invented", "sentence-invented-name-first", "sentence-gendered-title",
            "quote-starts-inside-a-word", "quote-word-and-symbol"} <= kinds


def test_no_seed_gets_through() -> None:
    report = measure([(ANSWER, MATERIAL), (OTHER_ANSWER, OTHER_MATERIAL)])
    assert report.answers == 2 and report.seeds >= 40
    assert report.passed == 0, report.leaks


def test_the_held_out_measurement_counts_rejections_and_their_reason() -> None:
    from pathlib import Path

    from ofrenda.tamper import measure_heldout, read_heldout
    heldout = Path(__file__).resolve().parent / "heldout"
    death = read_heldout(heldout / "death.txt")
    report = measure_heldout(death, [(ANSWER, MATERIAL), (OTHER_ANSWER, OTHER_MATERIAL)], "as if the person died")
    assert report.sentences == 45 and report.trials == 90
    assert report.intended <= report.rejected <= report.trials
    assert report.always_rejected + report.never_rejected <= report.sentences
    plain = measure_heldout(["{name} made the dashboard draw at once."], [(OTHER_ANSWER, OTHER_MATERIAL)], "x")
    assert plain.rejected == 0 and plain.never_rejected == 1
