"""Cards on the terminal, in an OFRENDA.md, and on one self-contained HTML page.

Everything that comes from the repository (names, commit messages, code lines,
paths) is untrusted text. On the terminal, control characters and the Unicode
direction overrides are shown as escapes, so a commit message cannot move the
cursor, write to the clipboard or reorder what you read. In Markdown, names and
subjects are escaped and code goes in fences longer than any run of backticks in
it. In HTML, every value goes through ``html.escape`` and the page carries a
Content Security Policy that allows no script and no request at all.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import textwrap
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any, TextIO

from . import __version__
from .cards import Card, CardStats, Quote
from .ledger import Ledger, LineFact

UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]")


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def mask_emails(text: str) -> str:
    """Email addresses shown as <email>: a page about people should not republish their addresses."""
    return EMAIL.sub("<email>", text)


def safe(text: str) -> str:
    """One line of untrusted text with every control and direction character made visible, and
    email addresses masked."""
    text = mask_emails(text.replace("\t", "    ").replace("\n", " "))
    return UNSAFE.sub(lambda m: f"\\u{ord(m.group(0)):04x}" if ord(m.group(0)) > 0xff
                      else f"\\x{ord(m.group(0)):02x}", text)


def short(oid: str) -> str:
    return oid[:10]


def count(n: int) -> str:
    return f"{n:,}"


def percent(share: float) -> str:
    value = share * 100
    if 0 < value < 0.1:
        return "under 0.1%"
    return f"{value:.1f}%"


def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{count(n)} {word if n == 1 else (many or word + 's')}"


def source_note(card: Card, model: str) -> str:
    if card.source == "model":
        return f"words by {model}, every quote checked against git"
    if card.source == "model-retry":
        return f"words by {model} on the second try, every quote checked against git"
    if card.source == "fallback":
        return "from git alone: neither answer from the model passed the check"
    return "from git alone"


NOBODY_WITH_LINES = ("No one has lines here that ofrenda can credit to a person: what it read is binary, "
                     "generated, or written by bots.")
NOBODY_MOVED_ON = "Nobody here has moved on yet: everyone with lines at this revision committed recently."
LIMIT_NOTE = ("The sentences come from a model running on the machine that made this page. They are used only when "
              "every phrase they quote is in that person's commit messages and they pass a list of word rules; "
              "a sentence can still say something the messages do not support.")


def empty_note(ledger: Ledger) -> str:
    return NOBODY_WITH_LINES if not ledger.people else NOBODY_MOVED_ON


def intro(ledger: Ledger, quiet_days: int, moved_on: int) -> str:
    verb = "has" if len(ledger.people) == 1 else "have"
    return (f"{plural(len(ledger.people), 'person', 'people')} still {verb} lines in {ledger.repo} at "
            f"{short(ledger.commit)} ({ledger.commit_date}); {count(moved_on)} of them made no commit in the "
            f"{count(quiet_days)} days before it.")


def method_lines(ledger: Ledger, quiet_days: int, stats: CardStats | None, model: str) -> list[str]:
    skipped = ", ".join(f"{count(n)} {reason}" for reason, n in ledger.skipped.items()) or "none"
    lines = [
        f"Revision {ledger.commit} ({ledger.commit_date}). Blame options: {ledger.options}.",
        f"Files read: {count(ledger.files_kept)}; skipped: {skipped}. Lines read: {count(ledger.lines)}"
        + (f", of which {count(ledger.bot_lines)} by bots" if ledger.bot_lines else "") + ".",
        f"Moved on: lines still here, and no commit reachable from the revision in the {count(quiet_days)} days "
        "before its commit date.",
    ]
    if ledger.ignore_used:
        lines.append(f"Ignored for blame: {plural(ledger.ignore_used, 'commit')} "
                     f"(.git-blame-ignore-revs at the revision, and --ignore-rev).")
    if ledger.shallow:
        lines.append("This is a shallow clone: lines older than its history are credited to its oldest commit.")
    if stats is not None and stats.cards:
        lines.append(f"Cards: {stats.cards}; {stats.first_try} written by {model} on the first try, "
                     f"{stats.after_retry} on the second, {stats.fallback} from git alone after two rejected "
                     f"answers. Quotes checked against the commit messages: {stats.quotes_verified}.")
    for suspect in ledger.suspects:
        lines.append(f'Commit {short(suspect.oid)} "{safe(suspect.subject)}" still holds '
                     f"{plural(suspect.lines, 'line')}. If it only reformatted code, pass --ignore-rev "
                     f"{short(suspect.oid)} (or list it in .git-blame-ignore-revs) to give those lines back.")
    return lines


# -- terminal ------------------------------------------------------------------------------------

class Palette:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled and text else text

    def marigold(self, text: str) -> str:
        return self.paint("38;5;214", text)

    def flame(self, text: str) -> str:
        return self.paint("38;5;220", text)

    def name(self, text: str) -> str:
        return self.paint("1;38;5;223", text)

    def dim(self, text: str) -> str:
        return self.paint("2", text)

    def picado(self, width: int) -> str:
        colors = ("38;5;205", "38;5;214", "38;5;44", "38;5;141", "38;5;156")
        pieces = []
        for i in range(max(1, width // 4)):
            pieces.append(self.paint(colors[i % len(colors)], "/\\/\\"))
        return "".join(pieces)[: None if self.enabled else width]


def use_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def fit(text: str, width: int) -> str:
    """One line cut to ``width`` characters, marked with an ellipsis when cut."""
    return text if len(text) <= width else text[:max(0, width - 3)].rstrip() + "..."


def _quote_line(quote: Quote) -> str:
    return f'"{safe(quote.text)}" ({short(quote.oid)}, {quote.date})'


def terminal(ledger: Ledger, cards: Sequence[Card], *, quiet_days: int, moved_on: int, model: str,
             stats: CardStats | None, color: bool, width: int = 78) -> str:
    p = Palette(color)
    out = [p.picado(width), p.marigold(f"ofrenda for {safe(ledger.repo)}"),
           *textwrap.wrap(safe(intro(ledger, quiet_days, moved_on)), width=width), ""]
    indent = " " * 7
    wrap = textwrap.TextWrapper(width=width, initial_indent=indent, subsequent_indent=indent)
    if ledger.elder is not None:
        e = ledger.elder
        out += [p.marigold("  The elder: the oldest line still running"),
                f"{indent}{safe(e.path)}:{e.number}, by {p.name(safe(e.author))} on {e.date} ({short(e.oid)})",
                f"{indent}{p.dim('|')} {fit(safe(e.text), width - len(indent) - 2)}",
                f'{indent}from "{safe(e.subject)}"', ""]
    for card in cards:
        person = card.person
        out += [f"   {p.flame(')')}   {p.name(safe(person.name))}",
                f"  |{p.marigold(chr(39))}|  {person.first_date} to {person.last_date}, "
                f"{plural(person.commits, 'commit')}",
                f"  |_|  {plural(person.lines, 'line')} still here ({percent(person.share)} of the lines read), "
                f"in {plural(len(person.files), 'file')}", ""]
        if card.text:
            out += wrap.wrap(safe(card.text))
        for i, quote in enumerate(card.quotes):
            lead = "in their words: " if i == 0 and not card.text else ""
            out += textwrap.wrap(lead + _quote_line(quote), width=width, initial_indent=indent,
                                 subsequent_indent=indent + "  ")
        out += [f"{indent}{p.dim(line)}" for line in textwrap.wrap(f"({source_note(card, model)})",
                                                                    width=width - len(indent))]
        o = person.oldest
        out += ["", f"{indent}{p.dim('oldest line')}  {safe(o.path)}:{o.number} ({o.date}, {short(o.oid)})",
                f"{indent}{' ' * 13}{p.dim('|')} {fit(safe(o.text), width - len(indent) - 15)}"]
        top = textwrap.wrap(f'"{safe(person.top.subject)}" ({short(person.top.oid)}, {person.top.date}), '
                            f"{plural(person.top.lines, 'line')}", width=width - len(indent) - 13)
        out += [f"{indent}{p.dim('most lines') if i == 0 else ' ' * 10}   {line}" for i, line in enumerate(top)]
        out.append("")
    if not cards:
        out += [*textwrap.wrap(empty_note(ledger), width=width, initial_indent="  ", subsequent_indent="  "), ""]
    out.append(p.picado(width))
    for line in method_lines(ledger, quiet_days, stats, model):
        out += [p.dim(x) for x in textwrap.wrap(line, width=width)]
    return "\n".join(out) + "\n"


# -- Markdown ------------------------------------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|~])")


def md_text(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", safe(text))


def md_code(text: str) -> str:
    """Inline code that survives backticks inside it."""
    text = safe(text)
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def md_cell_code(text: str) -> str:
    """Inline code inside a table cell: a pipe would end the cell, even inside backticks."""
    return md_code(text).replace("|", "\\|")


def md_block(lines: Sequence[str], language: str = "") -> list[str]:
    body = [safe(line) for line in lines]
    longest = max((len(run) for line in body for run in re.findall(r"`+", line)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence + language, *body, fence]


LANGUAGE = {".py": "python", ".js": "javascript", ".ts": "typescript", ".rb": "ruby", ".go": "go", ".rs": "rust",
            ".c": "c", ".h": "c", ".java": "java", ".sh": "sh", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml",
            ".json": "json", ".html": "html", ".css": "css", ".rst": "rst", ".md": "markdown"}


def _language(path: str) -> str:
    return LANGUAGE.get(os.path.splitext(path)[1].casefold(), "text")


def _md_quote(quote: Quote) -> str:
    return f"\"{md_text(quote.text)}\" ({md_code(short(quote.oid))}, {quote.date})"


def markdown(ledger: Ledger, cards: Sequence[Card], *, quiet_days: int, moved_on: int, model: str,
             stats: CardStats | None) -> str:
    out = [f"# Ofrenda for {md_text(ledger.repo)}", "",
           "An ofrenda keeps people present. This one keeps present the people whose work still runs here: "
           "they have lines in the code at this revision and have moved on from this repository to other things. "
           "Their code did not.", "", md_text(intro(ledger, quiet_days, moved_on)), ""]
    if ledger.elder is not None:
        e = ledger.elder
        out += ["## The elder", "",
                f"The oldest line still running is {md_code(f'{e.path}:{e.number}')}, written by "
                f"{md_text(e.author)} on {e.date} in \"{md_text(e.subject)}\" ({md_code(short(e.oid))}).", "",
                *md_block([e.text], _language(e.path)), ""]
    for card in cards:
        person = card.person
        out += [f"## {md_text(person.name)}", ""]
        if card.text:
            out += [f"> {md_text(card.text)}", ">"]
        quotes = "; ".join(_md_quote(q) for q in card.quotes)
        if quotes:
            out += [f"> In their words: {quotes}", ""]
        out += [f"*{md_text(source_note(card, model))}*", "",
                "| | |", "|---|---|",
                f"| Commits | {count(person.commits)}, from {person.first_date} to {person.last_date} |",
                f"| Lines still here | {count(person.lines)} ({percent(person.share)} of the lines read), in "
                f"{plural(len(person.files), 'file')} |",
                f"| Most lines | \"{md_text(person.top.subject)}\" ({md_code(short(person.top.oid))}, "
                f"{person.top.date}): {plural(person.top.lines, 'line')} |",
                f"| Oldest line | {md_cell_code(f'{person.oldest.path}:{person.oldest.number}')} "
                f"({person.oldest.date}, {md_code(short(person.oldest.oid))}) |", "",
                *md_block([person.oldest.text], _language(person.oldest.path)), ""]
    if not cards:
        out += [empty_note(ledger), ""]
    out += ["---", "", "### How this page was made", ""]
    out += [f"- {md_text(line)}" for line in method_lines(ledger, quiet_days, stats, model)]
    out += [f"- Made with ofrenda {__version__}. Every number, date, path and line of code above comes from git. "
            + LIMIT_NOTE, ""]
    return "\n".join(out)


# -- HTML ----------------------------------------------------------------------------------------

FLAG_COLORS = ("#ff9f1c", "#e83f6f", "#2ec4b6", "#9b5de5", "#f15bb5", "#fee440", "#00bbf9")


def _flag(x: float, color: str, motif: int) -> str:
    """One paper flag, 60 wide, with a zigzag hem and cut-outs (even-odd fill makes the holes)."""
    w, h = 60.0, 64.0
    hem = " ".join(f"L{x + w - i * 7.5:.1f},{h + (6 if i % 2 else 0):.1f}" for i in range(9))
    outer = f"M{x:.1f},8 L{x + w:.1f},8 L{x + w:.1f},{h:.1f} {hem} L{x:.1f},{h:.1f} Z"
    cx, cy = x + w / 2, 36.0
    if motif == 0:  # flower: a centre and six petals
        cuts = [f"M{cx - 4:.1f},{cy:.1f} a4,4 0 1,0 8,0 a4,4 0 1,0 -8,0"]
        for dx, dy in ((0, -11), (9.5, -5.5), (9.5, 5.5), (0, 11), (-9.5, 5.5), (-9.5, -5.5)):
            px, py = cx + dx, cy + dy
            cuts.append(f"M{px - 3:.1f},{py:.1f} a3,3 0 1,0 6,0 a3,3 0 1,0 -6,0")
    elif motif == 1:  # diamond with four dots
        cuts = [f"M{cx:.1f},{cy - 13:.1f} L{cx + 10:.1f},{cy:.1f} L{cx:.1f},{cy + 13:.1f} L{cx - 10:.1f},{cy:.1f} Z"]
        for dx, dy in ((-18, -16), (18, -16), (-18, 16), (18, 16)):
            cuts.append(f"M{cx + dx - 2:.1f},{cy + dy:.1f} a2,2 0 1,0 4,0 a2,2 0 1,0 -4,0")
    else:  # star and a row of small triangles
        points = []
        for i in range(10):
            radius = 12 if i % 2 == 0 else 5
            angle = math.pi * (i / 5 - 0.5)
            points.append(f"{cx + radius * math.cos(angle):.1f},{cy + radius * math.sin(angle):.1f}")
        cuts = ["M" + " L".join(points) + " Z"]
        for i in range(5):
            tx = x + 8 + i * 11
            cuts.append(f"M{tx:.1f},14 L{tx + 6:.1f},14 L{tx + 3:.1f},19 Z")
    return f'<path fill="{color}" fill-rule="evenodd" d="{outer} {" ".join(cuts)}"/>'


def papel_picado(flags: int = 16) -> str:
    width = flags * 66
    body = [f'<path d="M0,8 Q{width / 2:.0f},14 {width},8" stroke="#d9c9a8" stroke-width="1.5" fill="none"/>']
    for i in range(flags):
        body.append(_flag(3 + i * 66, FLAG_COLORS[i % len(FLAG_COLORS)], i % 3))
    return (f'<svg class="picado" viewBox="0 0 {width} 74" preserveAspectRatio="none" role="presentation" '
            f'aria-hidden="true">{"".join(body)}</svg>')


CSS = """
:root{--bg:#120d18;--panel:#1c1524;--ink:#f3e9dc;--muted:#b7a8c2;--marigold:#ff9f1c;--rosa:#e83f6f;--line:#33283f}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
background:radial-gradient(circle at 12% 18%,rgba(255,159,28,.10) 0 2px,transparent 3px) 0 0/90px 90px,
radial-gradient(circle at 70% 60%,rgba(232,63,111,.10) 0 2px,transparent 3px) 0 0/130px 130px,var(--bg)}
.picado{display:block;width:100%;height:74px}
.picado.bottom{transform:scaleY(-1)}
main{max-width:1100px;margin:0 auto;padding:8px 24px 32px}
header{text-align:center;padding:18px 0 8px}
h1{font:600 2.6rem/1.1 Georgia,"Times New Roman",serif;margin:0;color:var(--marigold);letter-spacing:.02em}
.lede{max-width:720px;margin:14px auto 0;color:var(--muted)}
.count{margin:10px auto 0;color:var(--ink)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,440px),1fr));gap:22px;margin-top:28px}
.card{position:relative;background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--marigold);
border-radius:10px;padding:20px 22px 16px 70px;box-shadow:0 10px 30px rgba(0,0,0,.35);min-width:0}
.card.elder{grid-column:1/-1;border-top-color:var(--rosa);background:linear-gradient(180deg,#24182c,var(--panel))}
.candle{position:absolute;left:24px;top:28px;width:20px;height:46px;border-radius:3px;
background:linear-gradient(90deg,#efe2c8,#fff6e4 45%,#d9c6a4)}
.candle::before{content:"";position:absolute;left:5px;top:-24px;width:10px;height:20px;border-radius:50% 50% 45% 45%;
background:radial-gradient(circle at 50% 70%,#fff7c2 0 25%,#ffc93c 45%,#ff7b00 80%);
box-shadow:0 0 18px 6px rgba(255,159,28,.45);animation:flicker 2.8s ease-in-out infinite}
.candle::after{content:"";position:absolute;left:9px;top:-5px;width:2px;height:6px;background:#3b2a1e}
@keyframes flicker{0%,100%{transform:scale(1) rotate(-1deg)}50%{transform:scale(1.06,.94) rotate(2deg)}}
@media (prefers-reduced-motion:reduce){.candle::before{animation:none}}
.marigold{position:absolute;left:20px;top:30px;width:28px;height:28px;border-radius:50%;
background:radial-gradient(circle,#ffd166 0 22%,#ff9f1c 23% 55%,#e07a00 56% 70%,transparent 71%)}
.label{font-size:.72rem;text-transform:uppercase;letter-spacing:.14em;color:var(--rosa);margin:0 0 4px}
h2{font:600 1.45rem/1.2 Georgia,"Times New Roman",serif;margin:0 0 4px;color:#ffe7c4}
.when{color:var(--muted);font-size:.92rem;margin:0}
.words{margin:14px 0 6px;font:italic 1.05rem/1.5 Georgia,"Times New Roman",serif}
.quotes{margin:8px 0;padding:0;list-style:none}
.quotes li{margin:4px 0;color:var(--marigold)}
.quotes small,.facts small{color:var(--muted);font-style:normal}
.quotes small,.when small{white-space:nowrap}
.source{font-size:.78rem;color:var(--muted);margin:6px 0 10px}
.facts{width:100%;border-collapse:collapse;font-size:.9rem;margin-top:6px}
.facts th{text-align:left;font-weight:500;color:var(--muted);padding:4px 10px 4px 0;vertical-align:top;
white-space:nowrap}
.facts td{padding:4px 0;vertical-align:top;overflow-wrap:anywhere}
code,pre{font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre{background:#0d0912;border:1px solid var(--line);border-left:3px solid var(--marigold);border-radius:6px;
padding:10px 12px;margin:8px 0 0;overflow-x:auto;white-space:pre}
.card.elder pre{border-left-color:var(--rosa)}
footer{margin-top:34px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:16px}
footer ul{padding-left:18px}
"""


def _h(text: str) -> str:
    return html.escape(safe(text), quote=True)


def _html_quote(quote: Quote) -> str:
    return f"<li>&ldquo;{_h(quote.text)}&rdquo; <small>{_h(short(quote.oid))}, {_h(quote.date)}</small></li>"


def _elder_html(e: LineFact, moved_on: bool) -> str:
    """The candle is for people who moved on; an elder who still commits gets a marigold instead."""
    mark = ('<div class="candle" aria-hidden="true"></div>' if moved_on
            else '<div class="marigold" aria-hidden="true"></div>')
    still = "" if moved_on else " <small>(still committing here)</small>"
    return (f'<article class="card elder">{mark}'
            f'<p class="label">The elder: the oldest line still running</p><h2>{_h(e.author)}{still}</h2>'
            f'<p class="when">{_h(e.date)}, in &ldquo;{_h(e.subject)}&rdquo; <small>({_h(short(e.oid))})</small></p>'
            f'<pre><code>{_h(e.text)}</code></pre>'
            f'<p class="source"><code>{_h(e.path)}:{e.number}</code></p></article>')


def _card_html(card: Card, model: str) -> str:
    person = card.person
    parts = ['<article class="card"><div class="candle" aria-hidden="true"></div>',
             f"<h2>{_h(person.name)}</h2>",
             f'<p class="when">{_h(person.first_date)} to {_h(person.last_date)} &middot; '
             f"{_h(plural(person.commits, 'commit'))}</p>"]
    if card.text:
        parts.append(f'<p class="words">{_h(card.text)}</p>')
    if card.quotes:
        lead = "" if card.text else '<p class="label">In their words</p>'
        parts.append(lead + '<ul class="quotes">' + "".join(_html_quote(q) for q in card.quotes) + "</ul>")
    parts.append(f'<p class="source">{_h(source_note(card, model))}</p>')
    o = person.oldest
    parts.append('<table class="facts">'
                 f"<tr><th>Lines still here</th><td>{_h(count(person.lines))} "
                 f"<small>({_h(percent(person.share))} of the lines read, in "
                 f"{_h(plural(len(person.files), 'file'))})</small></td></tr>"
                 f"<tr><th>Most lines</th><td>&ldquo;{_h(person.top.subject)}&rdquo; "
                 f"<small>{_h(short(person.top.oid))}, {_h(person.top.date)}, "
                 f"{_h(plural(person.top.lines, 'line'))}</small></td></tr>"
                 f"<tr><th>Oldest line</th><td><code>{_h(o.path)}:{o.number}</code> "
                 f"<small>{_h(o.date)}, {_h(short(o.oid))}</small></td></tr></table>")
    parts.append(f"<pre><code>{_h(o.text)}</code></pre></article>")
    return "".join(parts)


def html_page(ledger: Ledger, cards: Sequence[Card], *, quiet_days: int, moved_on: int, model: str,
              stats: CardStats | None) -> str:
    cards_html = []
    if ledger.elder is not None:
        moved = {p.key for p in ledger.ghosts(quiet_days)}
        cards_html.append(_elder_html(ledger.elder, ledger.elder.author_key in moved))
    cards_html += [_card_html(card, model) for card in cards]
    if not cards:
        cards_html.append(f'<article class="card"><p class="words">{_h(empty_note(ledger))}</p></article>')
    method = "".join(f"<li>{_h(line)}</li>" for line in method_lines(ledger, quiet_days, stats, model))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="ofrenda {_h(__version__)}">
<title>Ofrenda for {_h(ledger.repo)}</title>
<style>{CSS}</style>
</head>
<body>
{papel_picado()}
<main>
<header>
<h1>Ofrenda for {_h(ledger.repo)}</h1>
<p class="lede">An ofrenda keeps people present. This one keeps present the people whose work still runs here: they
have moved on from this repository to other things, and their code is still in it.</p>
<p class="count">{_h(intro(ledger, quiet_days, moved_on))}</p>
</header>
<section class="cards">
{"".join(cards_html)}
</section>
<footer>
<ul>{method}
<li>Every number, date, path and line of code on this page comes from git. {_h(LIMIT_NOTE)} Made with ofrenda
{_h(__version__)}.</li></ul>
</footer>
</main>
{papel_picado().replace('class="picado"', 'class="picado bottom"')}
</body>
</html>
"""


# -- JSON ----------------------------------------------------------------------------------------

def as_json(ledger: Ledger, cards: Sequence[Card], *, quiet_days: int, moved_on: int, model: str,
            stats: CardStats | None) -> dict[str, Any]:
    def card_dict(card: Card) -> dict[str, Any]:
        person = asdict(card.person)
        person.pop("messages", None)
        person.pop("key", None)
        return {"person": person, "text": card.text, "quotes": [asdict(q) for q in card.quotes],
                "source": card.source, "reasons": list(card.reasons), "cached": card.cached}

    elder = asdict(ledger.elder) if ledger.elder else None
    if elder is not None:
        elder.pop("author_key", None)

    return {
        "ofrenda": __version__, "repo": ledger.repo, "commit": ledger.commit, "commit_date": ledger.commit_date,
        "quiet_days": quiet_days, "people_with_lines": len(ledger.people), "moved_on": moved_on,
        "files_read": ledger.files_kept, "skipped": ledger.skipped, "lines_read": ledger.lines,
        "bot_lines": ledger.bot_lines, "blame_options": ledger.options, "ignored_commits": ledger.ignore_used,
        "shallow": ledger.shallow, "blame_seconds": ledger.blame_seconds, "blame_jobs": ledger.jobs,
        "facts_from_cache": ledger.cached, "model": model or None,
        "elder": elder,
        "formatting_commits": [asdict(c) for c in ledger.suspects],
        "cards": [card_dict(c) for c in cards],
        "card_stats": ({k: v for k, v in asdict(stats).items() if k != "reasons"} if stats else None),
    }


def _masked(value: Any) -> Any:
    if isinstance(value, str):
        return mask_emails(value)
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, dict):
        return {k: _masked(v) for k, v in value.items()}
    return value


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(_masked(data), indent=2, ensure_ascii=False) + "\n"
