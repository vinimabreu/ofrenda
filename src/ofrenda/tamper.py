"""Seeds for measuring ``check_card``: take an answer that passed and break it on purpose.

Each seed changes one thing a model could get wrong (a word inside a quote, a quote
stitched from two messages, a quote from someone else, a number or a death word in
the sentence, ...). A seed is kept only when it really is wrong, so a seed that
passes the check is a hole in the check, never a lucky no-op. Used by
``scripts/measure_seeds.py`` and by the tests.
"""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from .cards import Answer, Material, check_card, squash

HOMOGLYPHS = {"a": "\u0430", "e": "\u0435", "o": "\u043e", "c": "\u0441", "p": "\u0440", "x": "\u0445",
              "i": "\u0456", "s": "\u0455"}
INVENTED_QUOTES = ("Improve overall stability across the board", "Refactor the core logic for clarity",
                   "Rewrite everything from scratch", "Make the codebase production ready")
SENTENCE_INSERTS = {
    "digit": " in 3 places",
    "year": " during the years they spent here",
    "hash": " in commit 4e1f9a2c7b",
    "path": " in core/handlers.py",
    "email": " (reach them at someone@mail.example)",
    "link": " as documented on https://docs.example/guide",
    "death-passed-away": " before they passed away",
    "death-rip": ", RIP",
    "death-in-memory": " and this card is in memory of them",
    "death-haunt": " and still haunt the code",
    "pronoun": " with his own tests",
    "invented-name": " for the Kubernetes operators",
}


@dataclass(frozen=True)
class Seed:
    kind: str
    answer: Answer


def _in_messages(quote: str, material: Material) -> bool:
    needle = squash(quote).strip(" \"'\u201c\u201d\u2018\u2019`")
    return bool(needle) and any(needle in squash(m.message) for m in material.messages)


def _sentence_seed(answer: Answer, kind: str, insert: str) -> Seed:
    text = answer.text.rstrip(".")
    return Seed(kind, Answer(text + insert + ".", answer.quotes))


def _quote_seed(answer: Answer, kind: str, index: int, quote: str) -> Seed:
    quotes = list(answer.quotes)
    quotes[index] = quote
    return Seed(kind, Answer(answer.text, tuple(quotes)))


def seeds_for(answer: Answer, material: Material, others: Sequence[Material] = (), *,
              rng: random.Random | None = None) -> list[Seed]:
    """Every seed that can be made from ``answer`` (which must pass ``check_card``)."""
    rng = rng or random.Random(0)
    made: list[Seed] = []
    vocabulary = sorted({w for m in material.messages for w in re.findall(r"[A-Za-z]{4,}", m.message)})
    for index, quote in enumerate(answer.quotes):
        words = squash(quote).split()
        if len(words) >= 2 and vocabulary:
            for _ in range(8):
                at = rng.randrange(len(words))
                swapped = [*words[:at], rng.choice(vocabulary), *words[at + 1:]]
                if not _in_messages(" ".join(swapped), material):
                    made.append(_quote_seed(answer, "quote-word-swapped", index, " ".join(swapped)))
                    break
        if len(words) >= 3:
            dropped = words[:1] + words[2:]
            if not _in_messages(" ".join(dropped), material):
                made.append(_quote_seed(answer, "quote-word-dropped", index, " ".join(dropped)))
        if vocabulary:
            added = [*words[:1], rng.choice(vocabulary), *words[1:]]
            if not _in_messages(" ".join(added), material):
                made.append(_quote_seed(answer, "quote-word-added", index, " ".join(added)))
        flipped = quote[:1].swapcase() + quote[1:]
        if flipped != quote and not _in_messages(flipped, material):
            made.append(_quote_seed(answer, "quote-case-changed", index, flipped))
        positions = [i for i, ch in enumerate(quote) if ch in HOMOGLYPHS]
        if positions:
            at = positions[len(positions) // 2]
            lookalike = quote[:at] + HOMOGLYPHS[quote[at]] + quote[at + 1:]
            if not _in_messages(lookalike, material):
                made.append(_quote_seed(answer, "quote-homoglyph", index, lookalike))
    if len(material.messages) >= 2:
        first, second = material.messages[0].message, material.messages[1].message
        tail = " ".join(squash(first).split()[-3:])
        head = " ".join(squash(second).split()[:3])
        joined = f"{tail} {head}"
        if not _in_messages(joined, material):
            made.append(_quote_seed(answer, "quote-joined-across-messages", 0, joined))
    borrowed = next((" ".join(squash(m.message).split()[:5]) for other in others for m in other.messages
                     if len(squash(m.message).split()) >= 3
                     and not _in_messages(" ".join(squash(m.message).split()[:5]), material)), None)
    if borrowed:
        made.append(_quote_seed(answer, "quote-from-someone-else", 0, borrowed))
    for phrase in INVENTED_QUOTES:
        if not _in_messages(phrase, material):
            made.append(_quote_seed(answer, "quote-invented", 0, phrase))
            break
    made.append(Seed("quotes-missing", Answer(answer.text, ())))
    for kind, insert in SENTENCE_INSERTS.items():
        if kind == "invented-name" and "kubernetes" in {w.casefold() for w in material.vocabulary()}:
            continue
        made.append(_sentence_seed(answer, f"sentence-{kind}", insert))
    fabricated = next((p for p in INVENTED_QUOTES if not _in_messages(p, material)), None)
    if fabricated:
        made.append(_sentence_seed(answer, "sentence-embedded-quote", f' and wrote "{fabricated}"'))
    return made


@dataclass
class SeedReport:
    answers: int = 0
    seeds: int = 0
    passed: int = 0  # seeds the check let through: holes in the check
    by_kind: dict[str, list[int]] = field(default_factory=dict)  # kind -> [seeds, passed]
    leaks: list[tuple[str, str]] = field(default_factory=list)  # (kind, the answer that got through)


def measure(pairs: Sequence[tuple[Answer, Material]], *, seed: int = 0) -> SeedReport:
    """Make every seed for each (answer, material) pair and count how many pass ``check_card``.
    Answers that do not pass the check themselves are skipped."""
    rng = random.Random(seed)
    report = SeedReport()
    materials = [m for _, m in pairs]
    for position, (answer, material) in enumerate(pairs):
        if check_card(answer, material) is not None:
            continue
        report.answers += 1
        others = materials[position + 1:] + materials[:position]
        for item in seeds_for(answer, material, others, rng=rng):
            counts = report.by_kind.setdefault(item.kind, [0, 0])
            counts[0] += 1
            report.seeds += 1
            if check_card(item.answer, material) is None:
                counts[1] += 1
                report.passed += 1
                report.leaks.append((item.kind, item.answer.text + " | " + " / ".join(item.answer.quotes)))
    return report
