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
from pathlib import Path

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
    "number-word": " in fifteen places",
    "judgment": ", sloppily",
    "gendered-noun": ", a true gentleman",
    "single-quoted-invented": " and wrote 'Rewrite everything from scratch'",
    "guillemets-invented": " and wrote \u00abRewrite everything from scratch\u00bb",
}
SENTENCE_PREFIXES = {
    "invented-name-first": "Google says ",
    "gendered-title": "Mr. ",
}
INTENDED = {"death": "as if the person died", "judgment": "judges the person", "gendered": "gender"}


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


def _prefix_seed(answer: Answer, kind: str, prefix: str) -> Seed:
    return Seed(kind, Answer(prefix + answer.text, answer.quotes))


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
        stripped = squash(quote).strip(" \"'\u201c\u201d\u2018\u2019`")
        if len(stripped) > 9 and stripped[0].isalpha() and stripped[1].isalpha():
            inside = stripped[1:]  # still in the message, but starting inside a word
            if _in_messages(inside, material):
                made.append(_quote_seed(answer, "quote-starts-inside-a-word", index, inside))
        made.append(_quote_seed(answer, "quote-word-and-symbol", index, f"{words[0]} &" if words else "& &"))
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
    for kind, prefix in SENTENCE_PREFIXES.items():
        if kind == "invented-name-first" and "google" in material.vocabulary():
            continue
        made.append(_prefix_seed(answer, f"sentence-{kind}", prefix))
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


@dataclass
class HeldOutReport:
    """How many held-out sentences the check rejects: at all, and for the reason the set is about."""
    sentences: int = 0
    trials: int = 0  # sentences times answers
    rejected: int = 0
    intended: int = 0
    always_rejected: int = 0  # sentences rejected for every answer
    never_rejected: int = 0


def read_heldout(path: str | Path) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.strip() and not line.startswith("#")]


def measure_heldout(templates: Sequence[str], pairs: Sequence[tuple[Answer, Material]], intended: str) -> HeldOutReport:
    """Each template with each passing answer's person and quotes; the quotes are real, so a
    rejection can only come from the sentence."""
    report = HeldOutReport(sentences=len(templates))
    usable = [(a, m) for a, m in pairs if check_card(a, m) is None]
    for template in templates:
        hits = 0
        for answer, material in usable:
            result = check_card(Answer(template.format(name=material.name), answer.quotes), material)
            report.trials += 1
            if result is not None:
                hits += 1
                report.rejected += 1
                report.intended += intended in result
        report.always_rejected += bool(usable) and hits == len(usable)
        report.never_rejected += hits == 0
    return report
