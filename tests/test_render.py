from __future__ import annotations

import io
import re

import pytest

from ofrenda.cards import Card, CardStats, Quote
from ofrenda.ledger import CommitFact, Ledger, LineFact, Person
from ofrenda.render import (as_json, dumps, html_page, markdown, md_block, md_code, md_text, papel_picado, percent,
                            safe, terminal, use_color)

EVIL_NAME = "Eve <script>alert(1)</script> \x1b]52;c;cHduZWQ=\x07 \u202egnp.exe"
EVIL_SUBJECT = "Fix `parser` | <img src=x onerror=alert(1)> \x1b[2J"


def person(name: str = "Celia Mbeki", subject: str = "Add the session interface") -> Person:
    return Person(key="email:c", name=name, first_date="2013-04-02", last_date="2015-01-01", last_time=1_420_070_400,
                  commits=1234, lines=5678, share=0.123, files=[("src/sessions.py", 5000), ("src/b.py", 678)],
                  oldest=LineFact("src/sessions.py", 3, "class SessionInterface: # `x` ```", "1" * 40, "2013-04-02"),
                  top=CommitFact("1" * 40, "2013-04-02", subject, 4000), surviving_commits=3, messages=[],
                  snippet_path="src/sessions.py", snippet=[])


def ledger(*people: Person, elder: LineFact | None = None) -> Ledger:
    return Ledger(repo="lantern", commit="c" * 40, commit_time=1_600_000_000, commit_date="2020-09-13",
                  options="-w -M ignore-revs", files_kept=2, skipped={"binary": 3, "generated": 1}, failed=0,
                  lines=46000, bot_lines=12, people=list(people), elder=elder, ignore_listed=1, ignore_used=1,
                  shallow=False, name_joins=0, blame_seconds=0.1, jobs=1,
                  suspects=[CommitFact("f" * 40, "2019-01-01", "Reformat with the formatter", 900)])


ELDER = LineFact("README", 1, "Lantern", "e" * 40, "2010-01-01", author="Ana Quintero", subject="Initial import")
MODEL_CARD = Card(person(), "Celia Mbeki made sessions pluggable.",
                  (Quote("Add the session interface", "1" * 40, "2013-04-02"),), "model")
GIT_CARD = Card(person("Bruno Takahashi"), "", (Quote("Add the session interface", "1" * 40, "2013-04-02"),),
                "fallback", ("a", "b"))
STATS = CardStats(cards=2, asked=3, first_try=1, after_retry=0, fallback=1, quotes_verified=1)
KW = {"quiet_days": 730, "moved_on": 2, "model": "gemma4:12b", "stats": STATS}


def test_safe_makes_controls_and_direction_marks_visible() -> None:
    assert safe("a\x1b[2Jb") == "a\\x1b[2Jb"
    assert safe("x\u202ey") == "x\\u202ey"
    assert safe("tab\there") == "tab    here"
    assert safe("caf\u00e9 \u00fcn\u00efcode") == "caf\u00e9 \u00fcn\u00efcode"


def test_percent() -> None:
    assert percent(0.123) == "12.3%" and percent(0.0004) == "under 0.1%" and percent(0) == "0.0%"


def test_terminal_plain_output_has_the_facts_and_no_escape_codes() -> None:
    text = terminal(ledger(person(), elder=ELDER), [MODEL_CARD, GIT_CARD], color=False, **KW)  # type: ignore[arg-type]
    assert "\x1b" not in text
    assert "5,678 lines still here (12.3% of the lines read), in 2 files" in text
    assert "2013-04-02 to 2015-01-01, 1,234 commits" in text
    assert '"Add the session interface" (1111111111, 2013-04-02)' in text
    assert "words by gemma4:12b, every quote checked against git" in text
    assert "from git alone: neither answer from the model passed the check" in text
    assert "in their words:" in text
    assert "The elder: the oldest line still running" in text and "README:1, by Ana Quintero on 2010-01-01" in text
    assert "--ignore-rev ffffffffff" in text
    flat = " ".join(text.split())
    assert "1 written by gemma4:12b on the first try, 0 on the second, 1 from git alone" in flat


def test_long_code_lines_are_cut_to_the_terminal_width() -> None:
    wide = person()
    wide.oldest = LineFact("src/a.py", 1, "x = '" + "y" * 200 + "'", "1" * 40, "2013-04-02")
    text = terminal(ledger(wide), [Card(wide, "", (), "git")], color=False, **KW)  # type: ignore[arg-type]
    code = [line for line in text.splitlines() if "x = 'yyy" in line]
    assert code and all(len(line) <= 78 for line in code) and code[0].endswith("...")


def test_terminal_color_is_marigold_when_asked() -> None:
    text = terminal(ledger(person()), [MODEL_CARD], color=True, **KW)  # type: ignore[arg-type]
    assert "\x1b[38;5;214m" in text and "\x1b[0m" in text


def test_untrusted_text_cannot_drive_the_terminal() -> None:
    card = Card(person(EVIL_NAME, EVIL_SUBJECT), "", (Quote(EVIL_SUBJECT, "1" * 40, "2013-04-02"),), "git")
    text = terminal(ledger(card.person), [card], color=True, **KW)  # type: ignore[arg-type]
    assert "\x1b]52" not in text and "\x1b[2J" not in text and "\u202e" not in text and "\x07" not in text
    assert "\\x1b]52" in text and "\\u202e" in text


def test_use_color_respects_no_color_and_pipes(monkeypatch: pytest.MonkeyPatch) -> None:
    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    assert use_color(Tty()) and not use_color(io.StringIO())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not use_color(Tty())


def test_markdown_escapes_names_and_fences_code() -> None:
    card = Card(person(EVIL_NAME, EVIL_SUBJECT), "", (Quote(EVIL_SUBJECT, "1" * 40, "2013-04-02"),), "git")
    text = markdown(ledger(card.person, elder=ELDER), [card], **KW)  # type: ignore[arg-type]
    assert not re.search(r"(?<!\\)<", text) and "\x1b" not in text  # every < is escaped
    assert "\\<script\\>" in text and "\\|" in text
    assert "````python\nclass SessionInterface: # `x` ```\n````" in text  # fence longer than any run inside
    assert text.startswith("# Ofrenda for lantern\n")
    assert "## The elder" in text and "Every number, date, path and line of code above comes from git" in text


def test_markdown_helpers() -> None:
    assert md_text("a_b*c") == "a\\_b\\*c"
    assert md_code("plain") == "`plain`"
    assert md_code("has `tick`") == "`` has `tick` ``"
    assert md_block(["```"], "") == ["````", "```", "````"]


def test_html_is_self_contained_escaped_and_scriptless() -> None:
    card = Card(person(EVIL_NAME, EVIL_SUBJECT), EVIL_SUBJECT, (Quote(EVIL_SUBJECT, "1" * 40, "2013-04-02"),),
                "model")
    page = html_page(ledger(card.person, elder=ELDER), [card, GIT_CARD], **KW)  # type: ignore[arg-type]
    assert page.startswith("<!doctype html>")
    assert "<script" not in page and "<img" not in page
    assert "&lt;script&gt;" in page and "&lt;img src=x" in page
    assert "default-src 'none'" in page
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", page)
    assert "http://" not in page and "https://" not in page and "@import" not in page
    # the elder (Ana) never moved on in this ledger: a marigold, not a candle
    assert page.count('class="picado') == 2 and page.count('class="candle"') == 2
    assert page.count('class="marigold"') == 1 and "(still committing here)" in page
    assert "The elder: the oldest line still running" in page and "5,678" in page


def test_papel_picado_has_flags_with_cut_outs() -> None:
    svg = papel_picado(6)
    assert svg.count("<path fill=") == 6 and 'fill-rule="evenodd"' in svg


def test_the_json_names_every_fact_and_leaves_out_emails() -> None:
    data = as_json(ledger(person(), elder=ELDER), [MODEL_CARD], **KW)  # type: ignore[arg-type]
    assert data["moved_on"] == 2 and data["cards"][0]["source"] == "model"
    assert data["cards"][0]["person"]["lines"] == 5678 and "key" not in data["cards"][0]["person"]
    assert data["formatting_commits"][0]["lines"] == 900 and data["card_stats"]["fallback"] == 1
    assert "@" not in str(data)


@pytest.mark.parametrize("renderer", ["terminal", "markdown", "html"])
@pytest.mark.parametrize("with_people, message", [(True, "Nobody here has moved on yet"),
                                                  (False, "No one has lines here that ofrenda can credit")])
def test_an_empty_ofrenda_says_why(renderer: str, with_people: bool, message: str) -> None:
    kw = dict(KW, moved_on=0)
    led = ledger(person()) if with_people else ledger()
    if renderer == "terminal":
        text = " ".join(terminal(led, [], color=False, **kw).split())  # type: ignore[arg-type]
    elif renderer == "markdown":
        text = markdown(led, [], **kw)  # type: ignore[arg-type]
    else:
        text = html_page(led, [], **kw)  # type: ignore[arg-type]
    assert message in text


def test_one_person_has_lines() -> None:
    assert "1 person still has lines in lantern" in " ".join(
        terminal(ledger(person()), [], color=False, **KW).split())  # type: ignore[arg-type]
    assert "2 people still have lines" in " ".join(
        terminal(ledger(person(), person("Bruno Takahashi")), [], color=False, **KW).split())  # type: ignore[arg-type]


def test_email_addresses_are_masked_everywhere_they_are_shown() -> None:
    subject = "[project @ Arch-1:someone@old-host.example--2003] initial import"
    p = person(subject=subject)
    card = Card(p, "", (Quote("mail me at someone@old-host.example please", "1" * 40, "2013-04-02"),), "git")
    outputs = [terminal(ledger(p), [card], color=False, **KW),  # type: ignore[arg-type]
               markdown(ledger(p), [card], **KW),  # type: ignore[arg-type]
               html_page(ledger(p), [card], **KW),  # type: ignore[arg-type]
               dumps(as_json(ledger(p), [card], **KW))]  # type: ignore[arg-type]
    for text in outputs:
        assert "someone@old-host.example" not in text and "email" in text


def test_a_pipe_in_a_path_does_not_break_the_markdown_table() -> None:
    p = person()
    p.oldest = LineFact("odd`name|x.md", 2, "| pipe | table |", "1" * 40, "2013-04-02")
    text = markdown(ledger(p), [Card(p, "", (), "git")], **KW)  # type: ignore[arg-type]
    row = next(line for line in text.splitlines() if line.startswith("| Oldest line"))
    assert row.count("|") - row.count("\\|") == 3  # two cells: three unescaped pipes


def test_html_escapes_controls_in_names_too() -> None:
    p = person(EVIL_NAME)
    page = html_page(ledger(p, elder=LineFact("a.py", 1, "x = 1", "e" * 40, "2010-01-01", author=EVIL_NAME,
                                             subject=EVIL_SUBJECT, author_key="email:c")),
                     [Card(p, "", (), "git")], **KW)  # type: ignore[arg-type]
    assert "\x1b" not in page and "\x07" not in page and "\u202e" not in page
    assert "\\x1b]52" in page and "\\u202e" in page


def test_an_elder_who_moved_on_gets_a_candle() -> None:
    p = person()
    elder = LineFact("README", 1, "Lantern", "e" * 40, "2010-01-01", author=p.name, subject="Start", author_key=p.key)
    page = html_page(ledger(p, elder=elder), [], **KW)  # type: ignore[arg-type]
    assert page.count('class="candle"') == 1 and 'class="marigold"' not in page


def test_addresses_are_masked_inside_snippet_tuples_in_the_json() -> None:
    p = person()
    p.snippet = [(1, "# Maintainer: jane.roe@corp.example")]
    text = dumps(as_json(ledger(p), [Card(p, "", (), "git")], **KW))  # type: ignore[arg-type]
    assert "jane.roe@corp.example" not in text and "<email>" in text
