"""ofrenda: cards for the people whose code still runs in a git repository.

Reads git objects only: no checkout, nothing from the repository is ever run.
For a repository you did not write, run it on a bare clone:
git clone --bare <url> repo.git && ofrenda repo.git
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, model
from .blame import BlameOptions
from .cards import Cardsmith, ReplyCache, stderr_progress
from .gitread import Git, GitError
from .ledger import read_ledger
from .render import as_json, dumps, html_page, markdown, terminal, use_color


def default_cache_dir() -> Path:
    if os.environ.get("OFRENDA_CACHE"):
        return Path(os.environ["OFRENDA_CACHE"]).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base).expanduser() / "ofrenda"


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{text} is not a whole number") from error
    if value < 0:
        raise argparse.ArgumentTypeError("use a number of zero or more")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ofrenda", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", nargs="?", default=".", help="repository path, bare or not (default: here)")
    parser.add_argument("--rev", default="HEAD", help="revision to read (default HEAD)")
    parser.add_argument("--quiet-days", type=_positive, default=730,
                        help="moved on = no commit in this many days before the revision's date (default 730)")
    parser.add_argument("--top", type=_positive, default=10, help="cards for this many people, most lines first "
                        "(default 10; 0 for everyone)")
    parser.add_argument("--md", type=Path, metavar="FILE", help="also write the cards as Markdown")
    parser.add_argument("--html", type=Path, metavar="FILE", help="also write one self-contained HTML page")
    parser.add_argument("--json", type=Path, metavar="FILE", help="also write every fact and card as JSON")
    parser.add_argument("--ignore-rev", action="append", default=[], metavar="REV",
                        help="blame past this commit as well (a formatter run, say); can be repeated")
    parser.add_argument("--no-copies", action="store_true",
                        help="blame without -C (lines moved from another file go to whoever moved them; faster)")
    parser.add_argument("--no-model", action="store_true", help="no model: cards from git alone")
    parser.add_argument("--model", default=model.DEFAULT_MODEL, help=f"Ollama model (default {model.DEFAULT_MODEL})")
    parser.add_argument("--host", default=model.DEFAULT_HOST, help="Ollama address (default %(default)s)")
    parser.add_argument("--allow-remote-model", action="store_true",
                        help="let commit messages go to an Ollama host that is not this machine, or a cloud model")
    parser.add_argument("--cache", type=Path, default=None, help=f"cache folder (default {default_cache_dir()})")
    parser.add_argument("--no-cache", action="store_true", help="read and write no cache")
    parser.add_argument("--jobs", type=_positive, default=0, help="blame processes in parallel (default: up to 8)")
    parser.add_argument("--version", action="version", version=f"ofrenda {__version__}")
    return parser


def _blame_progress(done: int, total: int, path: str) -> None:
    if sys.stderr.isatty():
        sys.stderr.write(f"\r\033[Kblame {done}/{total}")
        if done == total:
            sys.stderr.write("\n")
        sys.stderr.flush()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cache_dir = None if args.no_cache else (args.cache or default_cache_dir())
    if not args.no_model:
        try:
            if not args.allow_remote_model and not model.is_loopback(args.host):
                raise model.RemoteHostRefused(f"{args.host} is not this machine; commit messages stay local unless "
                                              "you pass --allow-remote-model")
        except (model.RemoteHostRefused, model.ModelUnavailable) as error:
            print(f"ofrenda: {error}", file=sys.stderr)
            return 2
    try:
        with Git(args.repo) as git:
            extra = tuple(git.resolve(rev) for rev in args.ignore_rev)
            options = BlameOptions(copies=0 if args.no_copies else 1, extra_ignored=extra)
            ledger = read_ledger(git, args.rev, options=options, jobs=args.jobs or None, cache_dir=cache_dir,
                                 progress=_blame_progress)
    except GitError as error:
        print(f"ofrenda: {error}", file=sys.stderr)
        return 2
    unreadable = ledger.skipped.get("unreadable", 0) + ledger.failed
    if unreadable:
        print(f"ofrenda: {unreadable} file(s) could not be read at this revision and are left out (objects "
              "missing, as in a partial clone: ofrenda never fetches)", file=sys.stderr)
        if ledger.lines == 0:
            return 2
    moved_on = ledger.ghosts(args.quiet_days)
    chosen = moved_on if args.top == 0 else moved_on[:args.top]
    model_name = "" if args.no_model else args.model
    if args.no_model:
        smith = Cardsmith(None)
    else:
        try:
            ask = model.asker(model=args.model, host=args.host, allow_remote=args.allow_remote_model)
        except model.RemoteHostRefused as error:
            print(f"ofrenda: {error}", file=sys.stderr)
            return 2
        smith = Cardsmith(ask, model=args.model, cache=ReplyCache(cache_dir, args.model) if cache_dir else None,
                          progress=stderr_progress)
    try:
        made = smith.cards(ledger, chosen)
    except model.RemoteHostRefused as error:
        print(f"ofrenda: {error}", file=sys.stderr)
        return 2
    except model.ModelUnavailable as error:
        print(f"ofrenda: {error}. Cards written so far are cached. Run with --no-model for cards from git alone.",
              file=sys.stderr)
        return 2
    stats = None if args.no_model else smith.stats
    quiet, count = args.quiet_days, len(moved_on)
    sys.stdout.write(terminal(ledger, made, quiet_days=quiet, moved_on=count, model=model_name, stats=stats,
                              color=use_color(sys.stdout)))
    if args.md:
        _write(args.md, markdown(ledger, made, quiet_days=quiet, moved_on=count, model=model_name, stats=stats))
    if args.html:
        _write(args.html, html_page(ledger, made, quiet_days=quiet, moved_on=count, model=model_name, stats=stats))
    if args.json:
        _write(args.json, dumps(as_json(ledger, made, quiet_days=quiet, moved_on=count, model=model_name,
                                        stats=stats)))
    return 0
