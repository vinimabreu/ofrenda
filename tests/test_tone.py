"""The second reading: a narrow yes/no question to the same model after a sentence passes the check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FakeModel
from ofrenda import tone
from ofrenda.cards import Cardsmith, ReplyCache
from ofrenda.render import method_lines
from test_cards import GOOD, M1, ledger, person

CLEAN = {"death": False, "judgment": False, "gender": False}
GOOD_REPLY = {"text": GOOD.text, "quotes": list(GOOD.quotes)}
OTHER = {"text": "Celia Mbeki made the session interface pluggable, so large apps keep state on the server.",
         "quotes": ["Add the session interface"]}


def test_the_tone_prompt_has_no_example_and_names_the_three_questions() -> None:
    for word in ("Celia", "session", "e.g.", "for example", "Example", "passed away", "RIP"):
        assert word not in tone.TONE_SYSTEM
    for field in ("death:", "judgment:", "gender:"):
        assert field in tone.TONE_SYSTEM
    assert set(tone.TONE_SCHEMA["required"]) == {"death", "judgment", "gender"}


@pytest.mark.parametrize("reply, reason", [
    (json.dumps(CLEAN), None),
    (json.dumps({**CLEAN, "death": True}), tone.REASONS["death"]),
    (json.dumps({**CLEAN, "judgment": True}), tone.REASONS["judgment"]),
    (json.dumps({**CLEAN, "gender": True}), tone.REASONS["gender"]),
    ("not json", tone.UNREADABLE),
    (json.dumps({"death": "no", "judgment": False, "gender": False}), tone.UNREADABLE),
])
def test_verdicts_and_their_plain_reasons(reply: str, reason: str | None) -> None:
    assert tone.parse_verdict(reply).reason() == reason


def test_a_clean_reading_keeps_the_card_and_costs_one_call() -> None:
    p = person()
    fake = FakeModel({p.name: GOOD_REPLY})
    smith = Cardsmith(fake, model="fake")
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "model" and fake.calls == 1 and len(fake.readings) == 1
    assert fake.readings[0] == tone.tone_prompt(p.name, GOOD.text)
    assert smith.stats.tone_calls == 1 and smith.stats.tone_refused == 0 and smith.stats.tone_seconds >= 0


def test_a_refused_reading_gets_the_usual_retry_with_the_plain_reason() -> None:
    p = person()
    fake = FakeModel({p.name: [GOOD_REPLY, OTHER]}, verdicts={"let a blueprint live": {**CLEAN, "death": True}})
    smith = Cardsmith(fake, model="fake")
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "model-retry" and card.text == OTHER["text"]
    assert card.reasons == (tone.REASONS["death"],)
    assert fake.prompts[1].endswith(f"Your previous answer was not used: {tone.REASONS['death']}. Write the card "
                                    "again, following every rule.")
    assert GOOD.text not in fake.prompts[1]
    assert smith.stats.tone_calls == 2 and smith.stats.tone_refused == 1


def test_two_refused_readings_fall_back_to_git_alone() -> None:
    p = person()
    fake = FakeModel({p.name: [GOOD_REPLY, OTHER]}, verdicts={"Celia Mbeki made": {**CLEAN, "gender": True}})
    [card] = Cardsmith(fake, model="fake").cards(ledger(p), [p])
    assert card.source == "fallback" and card.text == "" and card.quotes[0].text == M1.subject
    assert card.reasons == (tone.REASONS["gender"], tone.REASONS["gender"])


def test_an_unreadable_reading_is_asked_again_and_then_counts_as_a_refusal() -> None:
    p = person()
    fake = FakeModel({p.name: [GOOD_REPLY, GOOD_REPLY]}, verdicts={"let a blueprint": "not json"})
    smith = Cardsmith(fake, model="fake")
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "fallback" and card.reasons == (tone.UNREADABLE, tone.UNREADABLE)
    assert len(fake.readings) == 4  # two tries for each answer, no cache here


def test_the_sentence_is_never_read_when_the_check_already_refused_it() -> None:
    p = person()
    bad = {"text": "Celia Mbeki wrote 3 modules.", "quotes": ["Add the session interface"]}
    fake = FakeModel({p.name: [bad, GOOD_REPLY]})
    smith = Cardsmith(fake, model="fake")
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "model-retry" and len(fake.readings) == 1


def test_readings_are_cached_with_the_card(tmp_path: Path) -> None:
    p = person()
    fake = FakeModel({p.name: GOOD_REPLY})
    Cardsmith(fake, model="fake", cache=ReplyCache(tmp_path, "fake")).cards(ledger(p), [p])
    again = Cardsmith(fake, model="fake", cache=ReplyCache(tmp_path, "fake"))
    again.cards(ledger(p), [p])
    assert len(fake.readings) == 1 and again.stats.tone_cached == 1 and again.stats.tone_calls == 0


def test_the_tone_check_can_be_turned_off() -> None:
    p = person()
    fake = FakeModel({p.name: GOOD_REPLY}, verdicts={"Celia": {**CLEAN, "death": True}})
    smith = Cardsmith(fake, model="fake", tone_check=False)
    [card] = smith.cards(ledger(p), [p])
    assert card.source == "model" and fake.readings == []
    assert any("--no-tone-check" in line for line in method_lines(ledger(p), 730, smith.stats, "fake"))


def test_the_footer_says_the_reader_is_a_model_too() -> None:
    p = person()
    smith = Cardsmith(FakeModel({p.name: GOOD_REPLY}), model="fake")
    smith.cards(ledger(p), [p])
    line = next(x for x in method_lines(ledger(p), 730, smith.stats, "fake") if x.startswith("Second reading"))
    assert "1 sentences read, 0 refused" in line and "not to zero" in line
