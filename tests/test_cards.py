from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from conftest import FakeModel
from ofrenda import cards
from ofrenda.cards import (SYSTEM, Answer, Cardsmith, Material, ReplyCache, check_card, fallback_quotes, find_quote,
                           material_for, parse_answer, prompt_for)
from ofrenda.ledger import CommitFact, Ledger, LineFact, Person

M1 = CommitFact("1" * 40, "2013-04-02", "Add the session interface", 40,
                "Add the session interface\n\nSessions can now be stored outside cookies, so large apps keep\n"
                "state on the server.")
M2 = CommitFact("2" * 40, "2014-07-09", "Make blueprints nestable", 12,
                "Make blueprints nestable\n\nA blueprint can register another blueprint under its own prefix.\n"
                "We rip out the old prefix hack.")
M3 = CommitFact("3" * 40, "2015-01-01", "RIP the old loader", 3, "RIP the old loader")


def person(name: str = "Celia Mbeki", messages: tuple[CommitFact, ...] = (M1, M2), key: str = "email:c") -> Person:
    return Person(key=key, name=name, first_date="2013-04-02", last_date="2015-01-01", last_time=1_420_070_400,
                  commits=9, lines=55, share=0.25, files=[("src/sessions.py", 40), ("src/blueprints.py", 15)],
                  oldest=LineFact("src/sessions.py", 3, "class SessionInterface:", "1" * 40, "2013-04-02"),
                  top=CommitFact(M1.oid, M1.date, M1.subject, M1.lines), surviving_commits=3,
                  messages=list(messages), snippet_path="src/sessions.py",
                  snippet=[(3, "class SessionInterface:"), (4, "    def open_session(self, app, request):")])


def ledger(*people: Person) -> Ledger:
    return Ledger(repo="lantern", commit="c" * 40, commit_time=1_600_000_000, commit_date="2020-09-13",
                  options="-w -M ignore-revs", files_kept=2, skipped={}, failed=0, lines=220, bot_lines=0,
                  people=list(people), elder=None, ignore_listed=0, ignore_used=0, shallow=False, name_joins=0,
                  blame_seconds=0.1, jobs=1)


MATERIAL = Material("Celia Mbeki", "lantern", (M1, M2), ("src/sessions.py", "src/blueprints.py"), "src/sessions.py",
                    ("class SessionInterface:",))
GOOD = Answer("Celia Mbeki made sessions pluggable and let one blueprint live inside another.",
              ("Add the session interface", "register another blueprint under its own prefix"))


def answer(text: str = GOOD.text, quotes: tuple[str, ...] = GOOD.quotes) -> Answer:
    return Answer(text, quotes)


def test_a_grounded_answer_passes() -> None:
    assert check_card(GOOD, MATERIAL) is None


@pytest.mark.parametrize("quote", [
    "Add the  session\n interface",  # whitespace aside
    '"Add the session interface"',  # quote marks around it
    "state on the server.",  # spans a line break in the message
    "keep state on the server",
    "rip out the old prefix hack",  # not a death phrase
])
def test_quotes_that_are_really_in_a_message_pass(quote: str) -> None:
    assert check_card(answer(quotes=(quote,)), MATERIAL) is None


@pytest.mark.parametrize("quote, reason", [
    ("Rewrite the whole framework", "is not in any of their commit messages"),  # made up
    ("Add the cookie interface", "is not in any of their commit messages"),  # one word changed
    ("on the server. Make blueprints nestable", "is not in any of their commit messages"),  # joined across messages
    ("add the session interface", "is not in any of their commit messages"),  # case changed
    ("Add the sess\u0456on interface", "is not in any of their commit messages"),  # Cyrillic i
    ("Add", "too short"),
    ("the", "too short"),
    ("x" * 201 + " y", "longer than 200"),
    ("   ", "empty"),
])
def test_quotes_that_are_not_copied_are_rejected(quote: str, reason: str) -> None:
    result = check_card(answer(quotes=(quote,)), MATERIAL)
    assert result is not None and reason in result


def test_an_answer_without_quotes_is_rejected() -> None:
    assert check_card(answer(quotes=()), MATERIAL) == "the answer quotes nothing from the commit messages"


def test_more_than_three_quotes_are_rejected() -> None:
    quotes = ("Add the session interface", "Make blueprints nestable", "keep state on the server",
              "under its own prefix")
    assert "more than 3 quotes" in (check_card(answer(quotes=quotes), MATERIAL) or "")


@pytest.mark.parametrize("text, reason", [
    ("Celia Mbeki wrote 3 modules for sessions.", "carries a number"),
    ("Celia Mbeki shipped a1b2c3d4e5 for sessions.", "carries a commit hash"),
    ("Celia Mbeki wrote src/sessions.py for sessions.", "file name or a path"),
    ("Celia Mbeki wrote sessions.py for sessions.", "file name or a path"),
    ("Celia Mbeki wrote blueprints.py for nesting.", "file name or a path"),
    ("Write to celia@mbeki.example about sessions.", "email address"),
    ("Celia Mbeki documented sessions at www.lantern-docs.example.", "link"),
    ("Celia Mbeki documented sessions at https://lantern.example/docs for everyone.", "link"),
    ("Celia Mbeki wrote sessions over many years.", "date or an amount"),
    ("Celia Mbeki wrote two parts of the session code.", "date or an amount"),
    ("Celia Mbeki wrote the session code in March.", "date or an amount"),
    ("Celia Mbeki wrote hundreds of tests.", "date or an amount"),
    ("Celia Mbeki, who passed away, wrote sessions.", "as if the person died"),
    ("The late Celia Mbeki wrote sessions.", "as if the person died"),
    ("RIP Celia Mbeki, author of sessions.", "as if the person died"),
    ("In memory of Celia Mbeki, who wrote sessions.", "as if the person died"),
    ("May Celia Mbeki rest in peace with her sessions.", "as if the person died"),
    ("Celia Mbeki still haunts the session code.", "as if the person died"),
    ("The ghost of Celia Mbeki wrote sessions.", "as if the person died"),
    ("Celia Mbeki died after writing sessions.", "as if the person died"),
    ("Her session code lives on in this repository.", "as if the person died"),
    ("Celia Mbeki removed dead code from sessions.", "as if the person died"),
    ("Celia Mbeki wrote sessions and his blueprints.", "the card refers to the person by name or as they"),
    ("She made sessions pluggable.", "the card refers to the person by name or as they"),
    ("Celia Mbeki made sessions pluggable in Django style.", 'names "Django"'),
    ("Celia Mbeki added the SessionManager and nested blueprints.", 'names "SessionManager"'),
    ('Celia Mbeki wanted "a faster router" for blueprints.', 'quotes "a faster router"'),
    ("Celia Mbeki wrote sessions. Then blueprints. Then more.", "more than two sentences"),
    ("Celia Mbeki " + "wrote sessions and " * 20 + "more.", "longer than 320"),
    ("", "empty"),
])
def test_sentences_that_break_a_rule_are_rejected(text: str, reason: str) -> None:
    result = check_card(answer(text=text), MATERIAL)
    assert result is not None and reason in result, result


@pytest.mark.parametrize("text", [
    "Celia Mbeki made the session interface pluggable, so large apps keep state on the server.",
    'They wrote the "session interface" and made blueprints nestable.',
    "Their Python code lets the API keep sessions outside cookies.",  # generic terms and the language of .py files
    "Celia's SessionInterface still decides where sessions live.",  # an identifier from the code they wrote
    "Sessions outside cookies came from Celia Mbeki; blueprints nest because of them too.",
    "They left the session interface behind, and the ability for a blueprint to hold another.",
])
def test_sentences_within_the_rules_pass(text: str) -> None:
    assert check_card(answer(text=text), MATERIAL) is None


M4 = CommitFact("4" * 40, "2016-02-02", "add Python 3 compatibility", 5,
                "add Python 3 compatibility\n\nAlso add support for Jinja2 and the IPv6 resolver.")
NUMBERED = Material("Ines M. Okonkwo", "lantern", (M4,), ("lantern/compat.py",), "lantern/compat.py", ())


@pytest.mark.parametrize("text", [
    "Ines M. Okonkwo made the code run on Python 3.",
    "They added support for Jinja2 templates and the IPv6 resolver.",
    "Ines M. Okonkwo kept the code portable. They also added Jinja2 support.",
])
def test_numbers_copied_with_their_word_from_a_message_pass(text: str) -> None:
    assert check_card(Answer(text, ("add Python 3 compatibility",)), NUMBERED) is None


@pytest.mark.parametrize("text", [
    "Ines M. Okonkwo made the code run on Python 4.",
    "They added support for Jinja3 templates.",
    "They wrote 3 compatibility shims.",
    "They added compatibility in 2016.",
    "Ines M. Okonkwo kept the code portable. They added Jinja2. They wrote docs.",
])
def test_numbers_not_in_a_message_are_rejected(text: str) -> None:
    result = check_card(Answer(text, ("add Python 3 compatibility",)), NUMBERED)
    assert result in ("the sentence carries a number", "the text is more than two sentences")


def test_death_phrases_in_a_quote_are_rejected_but_ordinary_words_are_not() -> None:
    material = Material("Dario", "lantern", (M3,), (), "", ())
    assert "can read as if the person died" in (check_card(Answer("They cleaned up loading.",
                                                                  ("RIP the old loader",)), material) or "")


def test_replies_that_are_not_the_json_asked_for() -> None:
    assert parse_answer("not json").error == "the reply was not JSON"
    assert parse_answer("[1]").error == "the reply was not a JSON object"
    assert parse_answer('{"text": "x"}').error == "the reply is missing text or quotes"
    assert parse_answer('{"text": "x", "quotes": [1]}').error == "the reply is missing text or quotes"
    assert check_card(parse_answer("nope"), MATERIAL) == "the reply was not JSON"
    good = parse_answer(json.dumps({"text": " A ", "quotes": ["b c"]}))
    assert good == Answer("A", ("b c",))


def test_find_quote_names_the_commit() -> None:
    found = find_quote("register another blueprint under its own prefix.", (M1, M2))
    assert found is not None and found.oid == M2.oid
    assert found.text == "register another blueprint under its own prefix."  # the full stop is in the message
    trimmed = find_quote("\u201cMake blueprints nestable.\u201d", (M1, M2))
    assert trimmed is not None and trimmed.text == "Make blueprints nestable"  # this one is not
    assert find_quote("not there", (M1, M2)) is None


# -- the prompt --------------------------------------------------------------------------------

def test_the_prompt_holds_messages_but_no_number_from_the_facts() -> None:
    p = person()
    prompt = prompt_for(material_for(ledger(p), p))
    assert "Person: Celia Mbeki" in prompt and M1.message in prompt and M2.message in prompt
    for fact in ("55", "2013-04-02", "2015-01-01", "25", "40", M1.oid[:10], "9 commits"):
        assert fact not in prompt
    assert "class SessionInterface:" in prompt


def test_the_system_prompt_carries_no_example_answer() -> None:
    for word in ("Celia", "session", "blueprint", "lantern", "e.g.", "for example", "Example"):
        assert word not in SYSTEM


# -- writing cards -------------------------------------------------------------------------------

def test_a_good_first_answer_makes_a_model_card() -> None:
    p = person()
    fake = FakeModel({p.name: {"text": GOOD.text, "quotes": list(GOOD.quotes)}})
    smith = Cardsmith(fake, model="fake")
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "model" and card.text == GOOD.text and fake.calls == 1
    assert [q.oid for q in card.quotes] == [M1.oid, M2.oid]
    assert smith.stats.first_try == 1 and smith.stats.quotes_verified == 2 and smith.stats.asked == 1


def test_a_rejected_answer_gets_one_retry_with_the_plain_reason() -> None:
    p = person()
    bad = {"text": "Celia Mbeki wrote 3 modules.", "quotes": ["Add the session interface"]}
    fake = FakeModel({p.name: [bad, {"text": GOOD.text, "quotes": list(GOOD.quotes)}]})
    smith = Cardsmith(fake, model="fake")
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "model-retry" and card.reasons == ("the sentence carries a number",)
    assert fake.calls == 2
    retry = fake.prompts[1]
    assert retry.startswith(fake.prompts[0])
    assert retry.endswith("Your previous answer was not used: the sentence carries a number. Write the card again, "
                          "following every rule.")
    assert GOOD.text not in retry and "3 modules" not in retry  # no corrected version, not even the old answer
    assert smith.stats.after_retry == 1


def test_two_rejected_answers_fall_back_to_git_alone() -> None:
    p = person()
    made_up = {"text": "Celia Mbeki wrote sessions.", "quotes": ["Invent a quote here"]}
    fake = FakeModel({p.name: [made_up, made_up]})
    smith = Cardsmith(fake, model="fake")
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "fallback" and card.text == "" and fake.calls == 2
    assert [q.text for q in card.quotes] == [M1.subject] and card.quotes[0].oid == M1.oid
    assert all("is not in any of their commit messages" in r for r in card.reasons)
    assert smith.stats.fallback == 1 and smith.stats.quotes_verified == 0


def test_the_fallback_skips_a_subject_that_reads_as_a_death() -> None:
    p = person(messages=(M3, M2))
    p.top = CommitFact(M3.oid, M3.date, M3.subject, 3)
    assert [q.text for q in fallback_quotes(p)] == [M2.subject]


def test_without_a_model_every_card_comes_from_git() -> None:
    p = person()
    smith = Cardsmith(None)
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "git" and card.text == "" and card.quotes[0].text == M1.subject


def test_the_cache_answers_the_second_run(tmp_path: Path) -> None:
    p, q = person(), person("Bruno Takahashi", key="email:b")
    fake = FakeModel()
    cache = ReplyCache(tmp_path / "cache", "fake:1b")
    first = Cardsmith(fake, model="fake:1b", cache=cache).cards(ledger(p, q), [p, q])
    assert fake.calls == 2
    again = Cardsmith(fake, model="fake:1b", cache=ReplyCache(tmp_path / "cache", "fake:1b"))
    second = again.cards(ledger(p, q), [p, q])
    assert fake.calls == 2 and again.stats.cached == 2 and again.stats.asked == 0
    assert [c.text for c in first] == [c.text for c in second] and all(c.cached for c in second)
    assert stat.S_IMODE(cache.path.stat().st_mode) == 0o600
    other = Cardsmith(fake, model="fake:2b", cache=ReplyCache(tmp_path / "cache", "fake:2b"))
    other.cards(ledger(p), [p])
    assert fake.calls == 3  # another model is another cache


def test_a_cached_reply_is_checked_again_on_every_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = person()
    fake = FakeModel({p.name: [{"text": GOOD.text, "quotes": list(GOOD.quotes)},
                               {"text": "They made sessions pluggable.", "quotes": ["Add the session interface"]}]})
    Cardsmith(fake, model="fake", cache=ReplyCache(tmp_path, "fake")).cards(ledger(p), [p])
    assert fake.calls == 1
    monkeypatch.setattr(cards, "MAX_TEXT", 40)  # a stricter rule than when the reply was cached
    smith = Cardsmith(fake, model="fake", cache=ReplyCache(tmp_path, "fake"))
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "model-retry" and fake.calls == 2 and "longer than 40" in card.reasons[0]


def test_changed_facts_are_a_new_question(tmp_path: Path) -> None:
    p = person()
    fake = FakeModel()
    Cardsmith(fake, model="fake", cache=ReplyCache(tmp_path, "fake")).cards(ledger(p), [p])
    changed = person(messages=(M2, M1))
    Cardsmith(fake, model="fake", cache=ReplyCache(tmp_path, "fake")).cards(ledger(changed), [changed])
    assert fake.calls == 2
