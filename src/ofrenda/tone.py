"""A second reading of every card sentence, by the same local model.

The word lists in ``wording`` catch the words on them and little else: on sentences
written to get past them, most get past. So after a sentence passes ``check_card``,
the model is asked one narrow question in a separate call, at temperature 0, with a
JSON schema and no example in the prompt: does this sentence say or suggest that
the person died, does it insult or judge the person or their work, does it assume
their gender? Any yes and the card is refused with that plain reason, like any other
refusal: one more answer, then the card from git alone.

The reader is a model too. It lowers how much gets through; it does not make it
zero, and it can refuse a sentence that was fine. ``measurements/`` has both rates.

A reply that is not the JSON asked for gets one more try; a second bad reply counts
as a refusal, so a broken reading never lets a sentence through. Verdicts are
cached by model, prompt version, name and sentence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .model import Ask

TONE_PROMPT_ID = "tone-v1"

TONE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "death": {"type": "boolean"},
        "judgment": {"type": "boolean"},
        "gender": {"type": "boolean"},
    },
    "required": ["death", "judgment", "gender"],
}

# No sample sentence on purpose: an example in a prompt is an answer the model reaches for.
TONE_SYSTEM = (
    "You review one sentence written for a card about a software developer. The developer is alive: they "
    "stopped committing to one code repository and moved on to other things. Answer three questions about the "
    "sentence, each with true or false.\n"
    "death: does the sentence say or suggest, in any wording or language, that the person died, is dead, is "
    "mourned, rests in an afterlife, or is remembered as someone who is no longer alive? Words about software "
    "itself, such as a process, a program or a piece of code that stops or is removed, are not about the person.\n"
    "judgment: does the sentence insult the person, mock them, or judge the person or the quality of their work "
    "as bad?\n"
    "gender: does the sentence assume the person's gender, through a pronoun, a title, a family role or another "
    "gendered word about the person?\n"
    "Answer only about what the sentence says, not about whether it is true."
)

REASONS = {
    "death": "a second reading by the model says the sentence suggests the person died",
    "judgment": "a second reading by the model says the sentence judges the person or their work",
    "gender": "a second reading by the model says the sentence assumes the person's gender",
}
UNREADABLE = "the second reading by the model could not be read"


@dataclass(frozen=True)
class Verdict:
    death: bool = False
    judgment: bool = False
    gender: bool = False
    error: str = ""

    def reason(self) -> str | None:
        """The plain reason to refuse the sentence, or None when the reading found nothing."""
        if self.error:
            return UNREADABLE
        for field in ("death", "judgment", "gender"):
            if getattr(self, field):
                return REASONS[field]
        return None

    @property
    def flags(self) -> tuple[str, ...]:
        return tuple(f for f in ("death", "judgment", "gender") if getattr(self, f))


def tone_prompt(name: str, sentence: str) -> str:
    return f"The developer: {name}\nThe sentence: {sentence}"


def parse_verdict(reply: str) -> Verdict:
    try:
        data = json.loads(reply)
    except (json.JSONDecodeError, TypeError):
        return Verdict(error="not JSON")
    if not isinstance(data, dict) or not all(isinstance(data.get(k), bool) for k in ("death", "judgment", "gender")):
        return Verdict(error="missing fields")
    return Verdict(data["death"], data["judgment"], data["gender"])


def tone_key(model: str, name: str, sentence: str, attempt: int = 1) -> str:
    material = json.dumps([TONE_PROMPT_ID, TONE_SYSTEM, model, name, sentence, attempt])
    return "tone:" + hashlib.sha256(material.encode()).hexdigest()


def read_tone(ask: Ask, name: str, sentence: str) -> tuple[Verdict, int]:
    """One reading, and one more when the reply is not the JSON asked for. Returns the verdict and
    how many calls it took. Used without a cache by the measurement scripts."""
    verdict = parse_verdict(ask(TONE_SYSTEM, tone_prompt(name, sentence), TONE_SCHEMA))
    if not verdict.error:
        return verdict, 1
    return parse_verdict(ask(TONE_SYSTEM, tone_prompt(name, sentence), TONE_SCHEMA)), 2
