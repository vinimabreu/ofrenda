"""One card per person: a local model writes the words, code decides whether they are used.

The model gets, for one person, the commit messages of their commits that still
have lines at the revision (subject and body, sign-off trailers removed, capped
in count and size), a few of those lines, and the paths that carry them. No count
or date from the facts goes into the prompt. It answers with JSON: ``text``, one
or two sentences on what the person left behind and why it exists, and
``quotes``, the phrases from the commit messages that back the sentence.

``check_card`` keeps the answer only when:

- every quote, whitespace aside, is copied from one of the messages the model was
  given (case and punctuation included; quote marks around it and a trailing
  full stop are trimmed), starts and ends on a word boundary of that message,
  has two words with letters and eight characters or more and at most
  ``MAX_QUOTE`` characters, and there are one to three of them;
- text inside any kind of quotation marks in the sentence (straight, curly,
  single, guillemets) is also copied from a message, and no quotation mark is
  left open;
- the sentence has no control characters or markup, no dates, amounts (in
  digits or in words), commit hashes, email addresses, links, file names or paths
  (cards print those from git, next to the sentence), and no number or amount
  word unless the messages have it too (``Python 3``, ``Jinja2``);
- every name in the sentence (a capitalised word, the first word of a sentence
  included unless it is a plain starter such as "They", or a code identifier)
  appears in the material the model was given, or is one of a few generic
  computing words (``GENERIC_TERMS``);
- the sentence uses none of the words in ``wording``: death and mourning words in
  English, Spanish and Portuguese, words that judge the person, and gendered
  pronouns, titles and nouns.

Those are lists. A paraphrase that is on none of them can still pass, and so can
a plain lowercase claim the messages do not support; ``tests/heldout`` and
``measurements/`` say how much gets through.

When the answer fails, the model is asked once more with the plain reason and
nothing else, never with a corrected version. When that fails too, the card is
built from git alone: the subject line of the person's top commit, quoted as it
is. No quote is invented on either path; the sentence on a card that passed can
still say things the messages do not support.

Replies are cached per model and prompt version, keyed by the revision, the
person and the exact prompt (which holds every fact the model saw). The check
runs again on every use, so a stricter check applies to old replies too.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import wording
from .ledger import CommitFact, Ledger, Person, fold, make_private_dir, write_private
from .model import Ask

PROMPT_ID = "cards-v1"
MAX_TEXT = 320
MAX_QUOTE = 200
MAX_QUOTES = 3
PROMPT_PATHS = 6

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "quotes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "quotes"],
}

# No name, phrase or sample answer appears in here on purpose: an example in a prompt is
# an answer the model reaches for when it is unsure.
SYSTEM = (
    "You write the words on one card of an ofrenda that a software team keeps for the people whose code is "
    "still in their repository. The person on the card has moved on from this repository to other things. "
    "They are alive: never suggest otherwise, and do not write about death, mourning, ghosts or an afterlife.\n"
    "You are given the commit messages this person wrote for code that still runs, a few of those lines of "
    "code, and the files that carry them. Use only what these messages say.\n"
    "text: one or two plain sentences on what this person left behind in this codebase and why it exists. "
    "Refer to the person by name or as they. Do not write numbers, dates, years, amounts, commit hashes, file "
    "names, paths, email addresses or links: the card prints those from git next to your words. Do not name a "
    "project, library, company or person that the messages do not name.\n"
    "quotes: one to three short phrases, each copied exactly, character for character, from one of the commit "
    "messages, that support your sentence. A quote is a few words from a single message, never joined across "
    "messages and never reworded."
)

QUOTE_DEATH_CASED = re.compile(r"\bRIP\b|\bR\.I\.P\b")
QUOTE_DEATH = re.compile(r"rest in peace|passed away|in memory of|in memoriam|\bobituar|\bdeceased\b|\bcondolence|"
                         r"\bfuneral", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"(https?://|ftp://|www\.)|\b[\w-]+\.(?:com|org|net|io|dev|edu|gov|co)\b", re.I)
PATH = re.compile(r"[\w.-]+/[\w.-]+|\\[\w.-]+|\b[\w-]+\.(?:py|pyi|js|mjs|ts|tsx|jsx|rb|go|rs|java|kt|c|h|cc|cpp|"
                  r"hpp|cs|php|sh|bash|zsh|md|rst|txt|toml|ini|cfg|json|ya?ml|xml|html?|css|scss|lock|sql|in|tpl|"
                  r"po|pot|swift|m|mm|pl|lua|r)\b", re.I)
HASH = re.compile(r"\b[0-9a-f]{7,64}\b", re.I)
DIGIT = re.compile(r"\d")
# Text in quotation marks: straight and curly double quotes, curly single quotes, straight single
# quotes that open after a non-letter and close before one (so "it's" is not a quote), guillemets
# and low quotes.
QUOTED_SPANS = (
    re.compile(r'"([^"]{2,}?)"'),
    re.compile("\u201c([^\u201c\u201d]{2,}?)\u201d"),
    re.compile("\u2018([^\u2018\u2019]{2,}?)\u2019(?!\\w)"),
    re.compile(r"(?<!\w)'([^']{2,}?)'(?!\w)"),
    re.compile("\u00ab\\s*([^\u00ab\u00bb]{2,}?)\\s*\u00bb"),
    re.compile("\u2039\\s*([^\u2039\u203a]{2,}?)\\s*\u203a"),
    re.compile("\u201e([^\u201e\u201c\u201d]{2,}?)[\u201c\u201d]"),
)
PAIRS = (("\u201c", "\u201d"), ("\u00ab", "\u00bb"), ("\u2039", "\u203a"))
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff<>]")
IDENTIFIER = re.compile(r"`([^`]+)`")
GENERIC_TERMS = frozenset({
    "i", "api", "apis", "http", "https", "url", "urls", "json", "xml", "html", "css", "cli", "sql", "ui", "os",
    "ok", "unicode", "ascii", "utf", "ssl", "tls", "ssh", "io", "ci", "id", "ids",
})
LANGUAGES = {".py": "python", ".js": "javascript", ".ts": "typescript", ".rb": "ruby", ".go": "go", ".rs": "rust",
             ".java": "java", ".c": "c", ".php": "php", ".sh": "shell", ".rst": "restructuredtext"}
TRIM = " \t\n\"'\u201c\u201d\u2018\u2019`"


# -- what the model is given ---------------------------------------------------------------------

@dataclass(frozen=True)
class Material:
    name: str
    repo: str
    messages: tuple[CommitFact, ...]
    paths: tuple[str, ...]
    snippet_path: str
    snippet: tuple[str, ...]

    def vocabulary(self) -> frozenset[str]:
        """Folded words the sentence may use as names."""
        words: set[str] = set()
        sources = [self.name, self.repo, self.snippet_path, *self.paths, *self.snippet,
                   *(m.message for m in self.messages)]
        for text in sources:
            for word in re.findall(r"[^\W_]+", text):
                words.add(fold(word))
            for word in re.findall(r"[\w.-]+", text):
                words.add(fold(word))
        for path in (self.snippet_path, *self.paths):
            language = LANGUAGES.get(PurePosixPath(path).suffix.casefold())
            if language:
                words.add(language)
        return frozenset(words)

    def file_names(self) -> frozenset[str]:
        names = set()
        for path in (self.snippet_path, *self.paths):
            pure = PurePosixPath(path)
            names.add(pure.name.casefold())
            if pure.suffix:
                names.add(pure.stem.casefold() + pure.suffix.casefold())
        return frozenset(n for n in names if "." in n)


def material_for(ledger: Ledger, person: Person) -> Material:
    return Material(person.name, ledger.repo, tuple(person.messages),
                    tuple(path for path, _ in person.files[:PROMPT_PATHS]), person.snippet_path,
                    tuple(text for _, text in person.snippet))


def prompt_for(material: Material) -> str:
    blocks = [f"Person: {material.name}", f"Repository: {material.repo}",
              "Files that still carry their lines: " + ", ".join(material.paths), "",
              "Their commit messages, one per block:"]
    for i, message in enumerate(material.messages, start=1):
        blocks += [f"[message {i}]", message.message, f"[end of message {i}]"]
    if material.snippet:
        blocks += ["", f"Some of their lines that still run, from {material.snippet_path}:", *material.snippet]
    return "\n".join(blocks)


def retry_prompt(prompt: str, reason: str) -> str:
    return f"{prompt}\n\nYour previous answer was not used: {reason}. Write the card again, following every rule."


# -- the answer and the check ---------------------------------------------------------------------

@dataclass(frozen=True)
class Answer:
    text: str
    quotes: tuple[str, ...]
    error: str = ""


def parse_answer(reply: str) -> Answer:
    try:
        data = json.loads(reply)
    except (json.JSONDecodeError, TypeError):
        return Answer("", (), error="the reply was not JSON")
    if not isinstance(data, dict):
        return Answer("", (), error="the reply was not a JSON object")
    text, quotes = data.get("text"), data.get("quotes")
    if not isinstance(text, str) or not isinstance(quotes, list) or not all(isinstance(q, str) for q in quotes):
        return Answer("", (), error="the reply is missing text or quotes")
    return Answer(text.strip(), tuple(quotes))


def squash(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class Quote:
    text: str
    oid: str
    date: str


def find_quote(quote: str, messages: Sequence[CommitFact]) -> Quote | None:
    """The quote as it appears in one message (whitespace aside), with that commit; trims quote
    marks around it and a trailing full stop or comma first when that is what makes it match."""
    raw = squash(quote)
    tries = [raw, raw.strip(TRIM)]
    tries.append(tries[-1].rstrip(".,;:!"))
    for candidate in dict.fromkeys(t for t in tries if t):
        pattern = re.compile(("(?<!\\w)" if _wordish(candidate[0]) else "") + re.escape(candidate)
                             + ("(?!\\w)" if _wordish(candidate[-1]) else ""))
        for message in messages:
            if pattern.search(squash(message.message)):
                return Quote(candidate, message.oid, message.date)
    return None


def _wordish(char: str) -> bool:
    return char.isalnum() or char == "_"


def word_count(text: str) -> int:
    """Words that have a letter in them: "&" and "--" are not words."""
    return sum(1 for token in text.split() if any(c.isalpha() for c in token))


def quoted_spans(text: str) -> list[str]:
    spans: list[str] = []
    for pattern in QUOTED_SPANS:
        spans += [m.group(1) for m in pattern.finditer(text)]
    return spans


def without_quotes(text: str) -> str:
    for pattern in QUOTED_SPANS:
        text = pattern.sub(" ", text)
    return text


def open_quote(text: str) -> bool:
    """True when a quotation mark in ``text`` is never closed."""
    if text.count('"') % 2:
        return True
    if any(text.count(left) != text.count(right) for left, right in PAIRS):
        return True
    opening = len(re.findall(r"(?<!\w)'(?=\w)", text)) + text.count("\u2018")
    closing = len(re.findall(r"(?<=[\w.,!?])'(?!\w)", text)) + len(re.findall("\u2019(?!\\w)", text))
    return opening > closing


ABBREVIATIONS = frozenset({"e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "jr", "sr", "st", "no", "cf"})
_END = re.compile(r"[.!?]+[\"\u201d\u2019')\]]*\s+")
_NUMBERED = re.compile(r"[\w.+-]*\d[\w.+-]*")


def _sentences(text: str) -> list[str]:
    """Sentences, without breaking after an initial ("Ines M. Okonkwo") or a short abbreviation."""
    parts: list[str] = []
    start = 0
    text = text.strip()
    for match in _END.finditer(text):
        words = text[start:match.start()].split()
        last = words[-1] if words else ""
        if text[match.start()] == "." and ((len(last) == 1 and last.isupper()) or last.casefold() in ABBREVIATIONS):
            continue
        parts.append(text[start:match.end()].strip())
        start = match.end()
    if text[start:].strip():
        parts.append(text[start:].strip())
    return parts


def _ungrounded_number(text: str, material: Material) -> str | None:
    """The first number in the sentence that is not copied from a commit message, or None. A word
    with a digit in it passes when a message has that word (``Jinja2``); a bare number passes
    only together with the word before it, when a message has the pair (``Python 3``)."""
    messages = [squash(m.message).casefold() for m in material.messages]
    words = {w for m in messages for w in re.findall(r"[\w.+-]+", m)}
    for match in _NUMBERED.finditer(text):
        token = match.group(0).strip(".+-")
        if not token:
            continue
        if any(c.isalpha() for c in token):
            if token.casefold() in words:
                continue
            return token
        before = text[:match.start()].split()
        pair = f"{before[-1]} {token}".casefold() if before else token
        if not any(re.search(rf"(?<![\w.]){re.escape(pair)}(?![\w])", m) for m in messages):
            return token
    return None


def _names_in(text: str) -> list[str]:
    """Words that name something: capitalised (the first word of a sentence too, unless it is a
    plain starter such as "They"), written in camelCase or snake_case, or code in backticks. Text
    in quotation marks is left out (it is checked as a quote)."""
    found = [m.group(1) for m in IDENTIFIER.finditer(text)]
    plain = IDENTIFIER.sub(" ", without_quotes(text))
    for sentence in _sentences(plain):
        for position, word in enumerate(re.findall(r"[^\W\d][\w'\u2019-]*", sentence)):
            word = re.sub(r"['\u2019]s$", "", word).strip("'\u2019-")
            if not word:
                continue
            if "_" in word.strip("_"):
                found.append(word)
                continue
            for index, part in enumerate(p for p in word.split("-") if p):
                camel = any(c.isupper() for c in part[1:]) and any(c.islower() for c in part)
                starter = position == 0 and index == 0 and part.casefold() in wording.STARTERS
                if camel or (part[0].isupper() and not starter):
                    found.append(part)
    return found


def _is_hash(token: str) -> bool:
    return any(c.isdigit() for c in token) and any(c.isalpha() for c in token)


def reads_as_death(quote: str) -> bool:
    """For quotes: only phrases that are about a death whatever the context ("rip out" is fine)."""
    return bool(QUOTE_DEATH_CASED.search(quote) or QUOTE_DEATH.search(quote))


def _has_number(text: str) -> bool:
    """A digit, or any other character with a numeric value (a superscript two, a Roman numeral)."""
    return any(unicodedata.numeric(c, None) is not None for c in text)


def check_card(answer: Answer, material: Material) -> str | None:
    """None when the answer can go on the card, else the plain reason it can't."""
    if answer.error:
        return answer.error
    text = answer.text
    if not text:
        return "the sentence is empty"
    if len(text) > MAX_TEXT:
        return f"the sentence is longer than {MAX_TEXT} characters"
    if CONTROL.search(text):
        return "the sentence carries control characters or markup"
    if len(_sentences(text)) > 2:
        return "the text is more than two sentences"
    death = wording.death_word(text, material.name)
    if death:
        return f'the sentence uses "{death}", which can read as if the person died'
    judged = wording.judgment_word(text, material.name)
    if judged:
        return f'the sentence uses "{judged}", which judges the person'
    gendered = wording.gendered_word(text, material.name)
    if gendered:
        return (f'the sentence uses "{gendered}"; the card does not guess anyone\'s gender, '
                "so it says their name or they")
    if EMAIL.search(text):
        return "the sentence carries an email address"
    if URL.search(text):
        return "the sentence carries a link"
    lowered = text.casefold()
    if PATH.search(text) or any(re.search(rf"(?<![\w.]){re.escape(n)}(?![\w])", lowered)
                                for n in material.file_names()):
        return "the sentence carries a file name or a path"
    if any(_is_hash(m.group(0)) for m in HASH.finditer(text)):
        return "the sentence carries a commit hash"
    if _has_number(text) and (any(c not in "0123456789" and unicodedata.numeric(c, None) is not None for c in text)
                              or _ungrounded_number(text, material)):
        return "the sentence carries a number"
    amount = wording.ungrounded_amount(text, [m.message for m in material.messages])
    if amount:
        return f'the sentence carries a date or an amount ("{amount}")'
    if open_quote(text):
        return "the sentence opens a quotation mark and never closes it"
    for inner in quoted_spans(text):
        if find_quote(inner, material.messages) is None:
            return f'the sentence quotes "{squash(inner)}", which is not in their commit messages'
    vocabulary = material.vocabulary()
    for name in _names_in(text):
        if any(variant in GENERIC_TERMS or variant in vocabulary for variant in wording.stems(fold(name))):
            continue
        parts = [p for p in re.split(r"[\W_]+", fold(name)) if p]
        if parts and all(p in vocabulary or p in GENERIC_TERMS for p in parts):
            continue
        return f'the sentence names "{name}", which is not in their commit messages or files'
    if not answer.quotes:
        return "the answer quotes nothing from the commit messages"
    if len(answer.quotes) > MAX_QUOTES:
        return f"the answer has more than {MAX_QUOTES} quotes"
    for quote in answer.quotes:
        shown = squash(quote).strip(TRIM)
        if not shown:
            return "one of the quotes is empty"
        if len(shown) > MAX_QUOTE:
            return f"a quote is longer than {MAX_QUOTE} characters"
        if word_count(shown) < 2 or len(shown) < 8:
            return f'the quote "{shown}" is too short to stand on its own'
        if find_quote(quote, material.messages) is None:
            return f'the quote "{shown}" is not in any of their commit messages'
        if reads_as_death(shown):
            return f'the quote "{shown}" can read as if the person died'
    return None


# -- cards -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Card:
    person: Person
    text: str  # empty when the card is built from git alone
    quotes: tuple[Quote, ...]
    source: str  # "model", "model-retry", "fallback" (the check rejected both answers) or "git" (no model)
    reasons: tuple[str, ...] = ()
    cached: bool = False


def fallback_quotes(person: Person) -> tuple[Quote, ...]:
    """The subject of the person's top commit as it is, or of the next one when that one can read
    as if someone died; nothing when every subject is empty."""
    candidates = [CommitFact(person.top.oid, person.top.date, person.top.subject, person.top.lines),
                  *person.messages]
    for commit in candidates:
        subject = commit.subject.strip()
        if subject and not reads_as_death(subject):
            return (Quote(subject, commit.oid, commit.date),)
    return ()


def git_card(person: Person, source: str = "git", reasons: tuple[str, ...] = (), cached: bool = False) -> Card:
    return Card(person, "", fallback_quotes(person), source, reasons, cached)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "model"


class ReplyCache:
    """The model's raw replies on disk, one file per model and prompt version, readable only by you."""

    def __init__(self, directory: Path, model: str) -> None:
        self.directory = Path(directory)
        self.model = model
        self.path = self.directory / f"cards-{_slug(model)}-{PROMPT_ID}.json"
        self._entries: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._entries is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                entries = data.get("entries", {}) if isinstance(data, dict) else {}
                self._entries = {k: v for k, v in entries.items() if isinstance(v, str)}
            except (OSError, json.JSONDecodeError):
                self._entries = {}
        return self._entries

    def get(self, key: str) -> str | None:
        return self._load().get(key)

    def put(self, key: str, reply: str) -> None:
        self._load()[key] = reply
        make_private_dir(self.directory)
        write_private(self.path, {"model": self.model, "prompt": PROMPT_ID, "entries": self._load()})

    def __len__(self) -> int:
        return len(self._load())


def reply_key(model: str, commit: str, person: str, prompt: str) -> str:
    return hashlib.sha256(json.dumps([PROMPT_ID, model, commit, person, SYSTEM, prompt]).encode()).hexdigest()


@dataclass
class CardStats:
    cards: int = 0
    asked: int = 0  # model calls made in this run
    cached: int = 0  # replies read from the cache
    first_try: int = 0
    after_retry: int = 0
    fallback: int = 0
    quotes_verified: int = 0
    seconds: float = 0.0
    reasons: list[str] = field(default_factory=list)


class Cardsmith:
    """Writes cards. ``ask`` is the model; None builds every card from git alone."""

    def __init__(self, ask: Ask | None, *, model: str = "", cache: ReplyCache | None = None,
                 progress: Callable[[int, int, str], None] | None = None) -> None:
        self.ask = ask
        self.model = model
        self.cache = cache
        self.progress = progress
        self.stats = CardStats()

    def _reply(self, key: str, prompt: str) -> tuple[str, bool]:
        assert self.ask is not None
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                self.stats.cached += 1
                return cached, True
        reply = self.ask(SYSTEM, prompt, SCHEMA)
        self.stats.asked += 1
        if self.cache is not None:
            self.cache.put(key, reply)
        return reply, False

    def card(self, ledger: Ledger, person: Person) -> Card:
        if self.ask is None:
            return git_card(person)
        material = material_for(ledger, person)
        prompt = prompt_for(material)
        reply, hit = self._reply(reply_key(self.model, ledger.commit, person.key, prompt), prompt)
        answer = parse_answer(reply)
        first = check_card(answer, material)
        if first is None:
            return self._accept(person, answer, material, "model", (), hit)
        second_prompt = retry_prompt(prompt, first)
        reply, hit2 = self._reply(reply_key(self.model, ledger.commit, person.key, second_prompt), second_prompt)
        answer = parse_answer(reply)
        second = check_card(answer, material)
        if second is None:
            return self._accept(person, answer, material, "model-retry", (first,), hit and hit2)
        self.stats.reasons += [first, second]
        return git_card(person, "fallback", (first, second), hit and hit2)

    def _accept(self, person: Person, answer: Answer, material: Material, source: str, reasons: tuple[str, ...],
                cached: bool) -> Card:
        quotes = tuple(q for q in (find_quote(raw, material.messages) for raw in answer.quotes) if q is not None)
        self.stats.reasons += list(reasons)
        return Card(person, " ".join(answer.text.split()), quotes, source, reasons, cached)

    def cards(self, ledger: Ledger, people: Sequence[Person]) -> list[Card]:
        started = time.perf_counter()
        made: list[Card] = []
        for done, person in enumerate(people, start=1):
            if self.progress:
                self.progress(done, len(people), person.name)
            card = self.card(ledger, person)
            made.append(card)
            self.stats.cards += 1
            if card.source == "model":
                self.stats.first_try += 1
            elif card.source == "model-retry":
                self.stats.after_retry += 1
            elif card.source == "fallback":
                self.stats.fallback += 1
            if card.source.startswith("model"):
                self.stats.quotes_verified += len(card.quotes)
        self.stats.seconds = time.perf_counter() - started
        return made


def stderr_progress(done: int, total: int, label: str) -> None:
    """One line on a terminal, nothing when piped."""
    if sys.stderr.isatty():
        sys.stderr.write(f"\r\033[Kwriting card {done}/{total}")
        if done == total:
            sys.stderr.write("\n")
        sys.stderr.flush()
