"""Word lists the card check uses, and the small functions that apply them.

These are lists, not understanding. They hold the words and phrases a review of
ofrenda named, their inflections and their Spanish and Portuguese translations,
and a few plain death words of the same kind (coffin, cemetery, epitaph). A
paraphrase that is on none of them can still get through, which is why every
card names the model that wrote it and every quote names its commit. How much
gets through is measured on held-out sets that were written before these lists
and never added to them (``tests/heldout/``, and ``measurements/``).

All matching is done on the sentence with accents removed and case folded, after
the person's own name is taken out (so a person called Grace Graves or Alma can
still have a card).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache

# Death, mourning and the afterlife, in English, Spanish and Portuguese (accents removed).
# "lost", "gone", "sleeps", "no more", "has passed" and "skeleton" are common in technical
# prose ("lost connection", "the bug is gone"), so they count only with the person as the
# subject or object (see _person_patterns).
DEATH = re.compile(r"\b(?:" + "|".join([
    r"rip", r"r\.i\.p", r"rest(?:s|ed|ing)? in peace", r"laid to rest", r"lay to rest",
    r"pass(?:ed|es|ing)? (?:away|on)", r"the late", r"late",
    r"in (?:loving )?memory of", r"in loving memory", r"honou?r\w* (?:the )?memory", r"in memoriam",
    r"memorial\w*", r"remembrance", r"remembered",
    r"deceased", r"died", r"dies", r"die", r"dying", r"death\w*", r"dead",
    r"mourn\w*", r"griev\w*", r"grief", r"graves?", r"gravestone\w*", r"tomb\w*", r"buried", r"bury", r"burial",
    r"funeral\w*", r"obituar\w*", r"coffin\w*", r"casket\w*", r"cemeter\w*", r"epitaph\w*",
    r"afterlife", r"departed", r"beyond the grave", r"eternal\w*", r"beloved", r"condolence\w*", r"eulog\w*",
    r"perish\w*", r"demise", r"ghosts?", r"ghostly", r"haunt\w*", r"spirits?", r"souls?", r"heaven\w*",
    r"angels?", r"skulls?", r"sugar skull\w*", r"calaveras?", r"catrinas?", r"skeleton of",
    r"lives? on", r"lived on", r"farewell", r"goodbye", r"tribute\w*", r"(?:is|are|will be|sorely|deeply) missed",
    r"resting", r"no longer with us", r"gone but not forgotten", r"gone too soon", r"gone forever",
    r"left us", r"outliv\w*", r"last breath", r"saudades?", r"survived by", r"is survived",
    r"survives (?:them|him|her)",
    r"(?:their|his|her) passing", r"passing of",
    # Spanish
    r"fallec\w*", r"murio", r"murieron", r"muert[oa]s?", r"muerte", r"difunt[oa]s?", r"descanse", r"descansa en paz",
    r"en paz", r"q\.?e\.?p\.?d", r"luto", r"velorio", r"entierro", r"enterrad[oa]s?", r"tumbas?", r"sepultur\w*",
    r"cementerio\w*", r"mas alla", r"alma", r"almas", r"espiritu", r"en memoria", r"en recuerdo", r"nos dejo",
    # Portuguese
    r"falec\w*", r"morreu", r"morreram", r"mort[oa]s?", r"morte", r"descansa em paz", r"em paz", r"enterro",
    r"tumulo", r"cemiterio\w*", r"em memoria", r"nos deixou",
]) + r")\b")

# Judging the person or their work: the words the review named, inflected and translated.
JUDGMENT = re.compile(r"\b(?:" + "|".join([
    r"sloppy", r"sloppily", r"sloppiness", r"careless\w*", r"lazy", r"lazily", r"laziness",
    r"incompeten\w*", r"chapucer[oa]s?", r"descuidad[oa]s?", r"desleixad[oa]s?", r"perezos[oa]s?", r"flojo",
    r"preguicos[oa]s?",
]) + r")\b")

# Gendered titles and nouns (pronouns are in PRONOUNS). "man page" is not a man.
GENDERED = re.compile(r"\b(?:" + "|".join([
    r"sir", r"sirs", r"madam", r"ma'?am", r"gentlem[ae]n", r"lady", r"ladies", r"man(?!\s*-?pages?\b)", r"men",
    r"wom[ae]n", r"guys?", r"girls?", r"boys?",
    r"fathers?", r"mothers?", r"godfathers?", r"godmothers?", r"craftsm[ae]n", r"chairm[ae]n", r"brothers?",
    r"sisters?", r"sons?", r"daughters?", r"husbands?", r"wi(?:fe|ves)",
    r"padres?", r"madres?", r"padrinos?", r"madrinas?", r"herman[oa]s?", r"hij[oa]s?", r"espos[oa]s?", r"maridos?",
    r"pais?", r"maes?", r"padrinhos?", r"madrinhas?", r"irmaos?", r"irmas?", r"filh[oa]s?",
    r"senor", r"senora", r"senorita", r"senhor", r"senhora", r"caballeros?", r"damas?", r"hombres?", r"mujer(?:es)?",
    r"homem", r"homens", r"mulher(?:es)?", r"chic[oa]s?", r"menin[oa]s?",
]) + r")\b")
# Technical phrases that contain a word from the lists above and are about software, not people.
# They are taken out of the sentence before the lists run. Kept narrow on purpose: each one names
# the software thing ("dead code", "lazy loading"), so "Ana was lazy" still meets the list.
TECHNICAL = re.compile(r"\b(?:" + "|".join([
    r"lazy[ -]?(?:load\w*|import\w*|evaluat\w*|initiali[sz]\w*|propert\w*|iterat\w*|attribut\w*)",
    r"lazily (?:load\w*|import\w*|evaluat\w*|initiali[sz]\w*|comput\w*|creat\w*|open\w*)",
    r"man[ -]in[ -]the[ -]middle", r"man[ -]?pages?",
    r"late[ -]?(?:binding|bound|repl(?:y|ies)|respons\w*|arriv\w*|packets?|data|messages?|events?)",
    r"a late (?:reply|response|message|packet)",
    r"(?:process|processes|worker|workers|child|children|parent|thread|threads|connection|connections|server|"
    r"daemon|job|jobs|peer|node|session|socket) (?:dies|died|die|dying|death|is dead|are dead)",
    r"dead (?:code|letters?|letter queues?|links?|hosts?|connections?|workers?|process(?:es)?|threads?|sockets?|"
    r"branches|keys?|peers?|servers?|nodes?|jobs?|locks?|ends?|zones?|man'?s switch\w*)",
    r"tombstones?", r"grave accents?",
    r"lives? (?:on disk|on the (?:disk|stack|heap|server|client|filesystem|network|main thread))",
    r"ghost (?:text|cursors?|images?|process(?:es)?|entr(?:y|ies)|objects?|files?|refs?|references?|keys?)",
    r"remembered (?:hosts?|keys?|passwords?|credentials?|settings?|state|values?|choices?|sessions?|logins?|"
    r"positions?|options?)",
    r"(?:parent|child|sister|sibling) (?:process(?:es)?|projects?|repos?|repositor(?:y|ies)|librar(?:y|ies)|packages?|"
    r"modules?|sites?|nodes?|threads?|tasks?|elements?|directories|directory|folders?|commits?)",
    r"son (?:process(?:es)?|nodes?)", r"master (?:branch|node)",
]) + r")\b")
# Wording that speaks to a reader, a reviewer or a model, or carries instructions: a commit message
# can try to steer the card writer and the second reading. Plain technical uses ("returns true",
# "the answer cache", "ignore patterns", "the output", "a shell prompt") do not match.
READER = re.compile(r"\b(?:" + "|".join([
    r"answer(?:s|ed|ing)? (?:(?:with |is |are )?)(?:true|false|yes|no)\b",
    r"(?:true|false|yes|no) (?:to|for) (?:each|every|all|any|the|death|judgment|gender)",
    r"reviewers?", r"review notes?", r"questions?",
    r"ignor(?:e|es|ed|ing) (?:the |all |any |every |previous |prior |above |earlier |these |those )*"
    r"(?:instructions?|rules?|questions?|prompts?|guidelines?)",
    r"instructions? (?:for|to) (?:the |any |an |a )?(?:card|writer|reviewer|model|reader|assistant|ai)",
    r"(?:card|automated|ai) writers?", r"for the (?:card|writer|model|reader|assistant)",
    r"(?:write|say|print|output|return|use|end|start) (?:only |exactly |verbatim )?(?:exactly|verbatim|only) "
    r"(?:this|the following|these)",
    r"(?:write|say|output|print) exactly", r"exact (?:text|clause|sentence|wording|words)",
    r"respond(?:s|ed|ing)? (?:with|only|exactly)", r"output (?:only|exactly|the following)",
    r"system prompts?", r"(?:the|this|previous|above|your) prompt\b", r"language models?",
    r"as an (?:ai|assistant|language model)", r"you are (?:a|an|the) (?:ai|assistant|model|writer|reviewer)",
    r"this (?:sentence|card|text) is (?:about|not about|only about)",
]) + r")")


def technical(text: str) -> str:
    """``text`` folded, with the technical phrases in ``TECHNICAL`` taken out."""
    return TECHNICAL.sub(" ", plain(text))


def reader_words(text: str) -> str | None:
    """The first phrase in ``text`` that speaks to a reader or a model, or carries instructions."""
    found = READER.search(re.sub(r"\s+", " ", plain(text)))
    return found.group(0) if found else None


TITLES = re.compile(r"\b(?:Mr|Mrs|Ms|Miss)\b\.?\s+[A-Z]")
PRONOUNS = re.compile(r"\b(?:he|him|his|himself|she|her|hers|herself|ele|ela|eles|elas|dele|dela)\b")
ACCENTED_PRONOUNS = re.compile(r"\b(?:\u00e9l|ella|ellos|ellas)\b", re.I)

# Amounts and time spans the model can't know. A word that is also in the person's commit
# messages is allowed (it is copied, not counted).
AMOUNTS = re.compile(r"\b(?:" + "|".join([
    r"one", r"two", r"three", r"four", r"five", r"six", r"seven", r"eight", r"nine", r"ten", r"eleven", r"twelve",
    r"thirteen", r"fourteen", r"fifteen", r"sixteen", r"seventeen", r"eighteen", r"nineteen",
    r"twenty", r"thirty", r"forty", r"fifty", r"sixty", r"seventy", r"eighty", r"ninety",
    r"hundreds?", r"thousands?", r"millions?", r"billions?", r"dozens?", r"half", r"halves", r"a third", r"thirds",
    r"quarters?", r"percent\w*", r"per cent",
    r"years?", r"decades?", r"centur(?:y|ies)", r"months?", r"weeks?", r"days?", r"hours?", r"minutes?", r"ago",
    r"annual\w*",
    r"dos", r"tres", r"cuatro", r"cinco", r"seis", r"siete", r"ocho", r"nueve", r"diez", r"doce", r"quince",
    r"veinte", r"cien", r"mil", r"anos", r"meses", r"semanas", r"dias", r"decadas?",
    r"dois", r"quatro", r"sete", r"oito", r"nove", r"dez", r"onze", r"doze", r"vinte", r"cem",
]) + r")\b")
PERCENT = re.compile(r"%")
# "the new one", "each one": a pronoun, not a count
ONE_AS_PRONOUN = re.compile(r"\b(?:the|a|this|that|each|every|any|which|new|old|same|other|another|last|next|right|"
                            r"wrong|only|first|second|current|previous|default|original) one\b")
MONTHS = re.compile(r"\b(?:January|February|March|April|June|July|August|September|October|November|December)\b")

# Words a sentence may start with that are not a name. Any other capitalised first word has
# to be in what the model was given, like a name in the middle of a sentence.
STARTERS = frozenset({"a", "an", "the", "they", "their", "theirs", "them", "this", "these", "that", "those", "it",
    "its", "in", "on", "at", "with", "by", "for", "from", "to", "as", "after", "before", "when", "while", "through",
    "thanks", "because", "since", "most", "much", "every", "each", "all", "some", "without", "under", "over", "here",
    "there", "what", "where", "why", "how", "along", "across", "both", "even", "also", "later", "and", "but", "so",
    "yet", "or", "nor", "if", "then", "now", "once", "still", "only", "together", "among", "between", "during",
    "about", "around", "behind", "within", "against", "into", "onto", "upon", "via", "besides", "unlike", "like",
    "instead", "however", "thus", "whether", "which", "who", "whose", "whom"})


def plain(text: str) -> str:
    """Accents removed and case folded, spacing kept."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def stems(word: str) -> set[str]:
    """The word and a few plain English inflections of it, for matching against a vocabulary."""
    w = word.casefold()
    found = {w}
    for suffix, replace in (("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("d", ""), ("ing", ""),
                            ("ing", "e"), ("'s", ""), ("\u2019s", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            found.add(w[: len(w) - len(suffix)] + replace)
    return found


def without_name(text: str, name: str) -> str:
    """``text`` folded, with every word of the person's name and the technical phrases taken out."""
    folded = technical(text)
    for part in sorted({p for p in re.split(r"[\s.,]+", plain(name)) if len(p) > 1}, key=len, reverse=True):
        folded = re.sub(rf"(?<!\w){re.escape(part)}(?!\w)", " ", folded)
    return folded


@lru_cache(maxsize=256)
def _person_patterns(name: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in re.split(r"[\s.,]+", plain(name)) if len(p) > 1]
    subject = "|".join(["they", "them", "him", "her", "we", "us", *parts])
    return re.compile(
        rf"\b(?:{subject})\s+(?:is|was|are|were|has|have|had|has been|have been)\s+"
        r"(?:gone|no more|passed|buried|laid|lost|missed)\b"
        rf"|\b(?:{subject})\s+(?:sleeps|slept|rests|rested)\b"
        rf"|\b(?:lost|losing|loss of|miss|missing|bury|buried|remember|remembering)\s+(?:{subject})\b"
        rf"|\bskeleton of\s+(?:{subject})\b"
        rf"|\b(?:{subject})(?:'s|s'|\u2019s)? passing\b"
        r"|\bwe (?:sadly )?(?:lost|miss)\b")


def death_word(text: str, name: str) -> str | None:
    folded = technical(text)
    person = _person_patterns(name).search(re.sub(r"\s+", " ", folded))
    if person:
        return person.group(0)
    found = DEATH.search(without_name(text, name))
    return found.group(0) if found else None


def judgment_word(text: str, name: str) -> str | None:
    found = JUDGMENT.search(without_name(text, name))
    return found.group(0) if found else None


def gendered_word(text: str, name: str) -> str | None:
    title = TITLES.search(text)
    if title:
        return title.group(0).split()[0]
    accented = ACCENTED_PRONOUNS.search(text)
    if accented:
        return accented.group(0)
    rest = without_name(text, name)
    found = PRONOUNS.search(rest) or GENDERED.search(rest)
    return found.group(0) if found else None


def ungrounded_amount(text: str, messages: Iterable[str]) -> str | None:
    """The first amount or time word in ``text`` that is not copied from a message together with
    a word next to it ("the hour that repeats" lets "hour that" through, not "eighteen hours")."""
    folded_messages = [re.sub(r"\s+", " ", plain(m)) for m in messages]
    folded = re.sub(r"\s+", " ", ONE_AS_PRONOUN.sub(" ", plain(text)))
    if PERCENT.search(text):
        return "%"
    for match in AMOUNTS.finditer(folded):
        token = match.group(0)
        # a hyphenated word ("two-factor", "third-party") is copied as a whole or not at all
        left = re.search(r"[\w-]*$", folded[:match.start()])
        right = re.match(r"[\w-]*", folded[match.end():])
        compound = (left.group(0) if left else "") + token.split()[-1] + (right.group(0) if right else "")
        if "-" in compound:
            if any(re.search(rf"(?<![\w-]){re.escape(compound)}(?![\w-])", m) for m in folded_messages):
                continue
            return compound
        before = re.findall(r"[^\W_]+", folded[:match.start()])
        after = re.findall(r"[^\W_]+", folded[match.end():])
        phrases = []
        for variant in stems(token) | {token}:
            if before:
                phrases.append(f"{before[-1]} {variant}")
            if after:
                phrases.append(f"{variant} {after[0]}")
        if not any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", m) for phrase in phrases for m in folded_messages):
            return token
    month = MONTHS.search(text)
    if month and not any(month.group(0).casefold() in m for m in folded_messages):
        return month.group(0)
    return None
