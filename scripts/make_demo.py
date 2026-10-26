"""Build the demo repository: fifteen years of an invented job scheduler, ``almanac``.

    python scripts/make_demo.py /tmp/almanac

Every person, address and line in it is made up. The history is fixed (authors,
dates, contents), so the commit ids come out the same on every machine and the
output in the README can be reproduced. It has what ofrenda has to handle: one
person under two addresses joined by a ``.mailmap``, code moved to another file,
a formatter commit, a bot, and a maintainer who is still active.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

INES = ("Ines Okonkwo", "ines@okonkwo.example")
INES_OLD = ("I. Okonkwo", "ines@old-lab.example")
TOMAS = ("Tomas Varga", "tomas@varga.example")
MEI = ("Mei Lindqvist", "mei@lindqvist.example")
RAFAEL = ("Rafael Oyelaran", "rafael@oyelaran.example")
SANNA = ("Sanna Petrova", "sanna@petrova.example")
NOOR = ("Noor Halvorsen", "noor@halvorsen.example")
BOT = ("dependabot[bot]", "dependabot[bot]@users.noreply.example")

SCHEDULER = '''"""The scheduler: a sorted list of jobs and a loop that runs the ones that are due."""

import bisect
import time


class Job:
    def __init__(self, name, func, every):
        self.name = name
        self.func = func
        self.every = every
        self.next_run = time.time() + every

    def __lt__(self, other):
        return self.next_run < other.next_run


class Scheduler:
    def __init__(self):
        self.jobs = []

    def add(self, name, func, every):
        job = Job(name, func, every)
        bisect.insort(self.jobs, job)
        return job

    def run_pending(self, now=None):
        now = now or time.time()
        while self.jobs and self.jobs[0].next_run <= now:
            job = self.jobs.pop(0)
            job.func()
            job.next_run = now + job.every
            bisect.insort(self.jobs, job)
'''

CRON = '''"""Five-field expressions, the way cron writes them: minute hour day month weekday."""

FIELDS = (("minute", 0, 59), ("hour", 0, 23), ("day", 1, 31), ("month", 1, 12), ("weekday", 0, 6))


def parse_field(text, low, high):
    if text == '*':
        return set(range(low, high + 1))
    values = set()
    for part in text.split(','):
        if '/' in part:
            base, step = part.split('/')
            start = low if base == '*' else int(base)
            values.update(range(start, high + 1, int(step)))
        elif '-' in part:
            first, last = part.split('-')
            values.update(range(int(first), int(last) + 1))
        else:
            values.add(int(part))
    return values


def parse(expression):
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError('a cron expression has five fields')
    return {name: parse_field(text, low, high) for text, (name, low, high) in zip(parts, FIELDS)}


def matches(fields, when):
    return (when.minute in fields['minute'] and when.hour in fields['hour'] and when.day in fields['day']
            and when.month in fields['month'] and when.weekday() in fields['weekday'])
'''

ZONES = '''"""Time zones for jobs: a job remembers the zone it was created in."""

from datetime import datetime, timedelta


def local_now(zone):
    return datetime.now(zone)


def next_local_time(zone, hour, minute, after):
    candidate = after.astimezone(zone).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate
'''

ZONES_FOLD = '''

def resolve_fold(zone, naive):
    """The first of the two moments a repeated wall-clock time names, when clocks go back."""
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    return min(first, second, key=lambda moment: moment.timestamp())
'''

RETRY = '''"""Retry a failed job, waiting longer before each new attempt."""

import random


def backoff(attempt, base=2.0, ceiling=300.0):
    delay = min(ceiling, base ** attempt)
    return delay / 2 + random.uniform(0, delay / 2)


def run_with_retries(func, attempts=5, sleep=None):
    import time
    sleep = sleep or time.sleep
    for attempt in range(attempts):
        try:
            return func()
        except Exception:
            if attempt == attempts - 1:
                raise
            sleep(backoff(attempt))
'''

CLI = '''"""almanac list / almanac run: a small command line around the scheduler."""

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog='almanac')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='show every job and its next run')
    run = commands.add_parser('run', help='run the jobs that are due')
    run.add_argument('--once', action='store_true', help='run once and exit')
    args = parser.parse_args(argv)
    if args.command == 'list':
        print('no jobs yet')
    return 0


if __name__ == '__main__':
    sys.exit(main())
'''

STORE = '''"""Jobs kept in SQLite, so a restart does not forget them."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    name TEXT PRIMARY KEY,
    every REAL NOT NULL,
    last_run REAL
)
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(SCHEMA)

    def save(self, name, every, last_run=None):
        self.db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?, ?)", (name, every, last_run))
        self.db.commit()

    def load(self):
        return list(self.db.execute("SELECT name, every, last_run FROM jobs ORDER BY name"))
'''

STORE_LOCK = '''

    def claim(self, name, now):
        """Mark a job as running unless another worker already did."""
        with self.db:
            cursor = self.db.execute(
                "UPDATE jobs SET last_run = ? WHERE name = ? AND (last_run IS NULL OR last_run < ?)",
                (now, name, now),
            )
        return cursor.rowcount == 1
'''

TUTORIAL = '''# Tutorial

Almanac runs your functions on a schedule, inside your own process.

## Your first job

Create a scheduler, add a job, and call `run_pending` from your main loop:

    from almanac import Scheduler

    scheduler = Scheduler()
    scheduler.add("report", send_report, every=3600)

## Cron expressions

When "every hour" is not enough, write the schedule the way cron does.
Five fields: minute, hour, day of the month, month, day of the week.

## Time zones

A job keeps the zone it was created in. A job set for nine in the morning
runs at nine in the morning, in summer and in winter.
'''

README = '''# almanac

A small job scheduler for Python programs that already have a main loop.

Run a function every few minutes, at a time of day, or on a cron expression,
without a separate daemon.
'''

LICENSE = '''MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software, to deal in the software without restriction.
'''

ENV_BASE = {"PATH": os.environ.get("PATH", os.defpath), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0", "LANG": "C.UTF-8"}


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false",
                    "-c", f"core.hooksPath={os.devnull}", *args], cwd=repo, check=True, capture_output=True,
                   env={**ENV_BASE, "HOME": str(repo), **(env or {})})


def commit(repo: Path, who: tuple[str, str], when: str, message: str, files: dict[str, str | None]) -> None:
    for name, content in files.items():
        path = repo / name
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    stamp = f"{when}T10:00:00+0000"
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message, env={
        "GIT_AUTHOR_NAME": who[0], "GIT_AUTHOR_EMAIL": who[1], "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_NAME": who[0], "GIT_COMMITTER_EMAIL": who[1], "GIT_COMMITTER_DATE": stamp})


def build(repo: Path) -> None:
    if repo.exists() and any(repo.iterdir()):
        raise SystemExit(f"{repo} is not empty")
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    commit(repo, INES, "2011-03-14", "Start almanac, a small job scheduler\n\nOne sorted list of jobs and a loop "
           "that runs the ones that are due. No daemon, no threads.",
           {"README.md": README, "LICENSE": LICENSE, "almanac/__init__.py": "from .scheduler import Scheduler\n",
            "almanac/scheduler.py": SCHEDULER})
    commit(repo, INES, "2011-04-02", "Add cron-like expressions\n\nA schedule can now be written as five fields, "
           "the same way cron reads them, for jobs that run at a time of day rather than every few seconds.",
           {"almanac/cron.py": CRON})
    commit(repo, INES_OLD, "2011-09-20", "Keep the job list sorted by next run",
           {"almanac/scheduler.py": SCHEDULER.replace(
               "            job.next_run = now + job.every\n",
               "            job.next_run = max(now, job.next_run) + job.every\n")})
    commit(repo, TOMAS, "2012-02-11", "Teach the scheduler about time zones\n\nJobs now keep the zone they were "
           "created in, so a job set for the morning still runs in the morning after a clock change.",
           {"almanac/zones.py": ZONES})
    commit(repo, TOMAS, "2012-06-30", "Retry failed jobs with backoff\n\nA job that fails waits longer before each "
           "new attempt, up to a ceiling, with some jitter so that many workers do not retry in step.",
           {"almanac/retry.py": RETRY})
    commit(repo, MEI, "2013-01-15", "Add a command line to list and run jobs\n\nOperators asked for a way to see "
           "what is scheduled without opening a Python shell.", {"almanac/cli.py": CLI})
    commit(repo, MEI, "2013-05-04", "Write the tutorial\n\nFrom a first job to cron expressions and time zones, in "
           "the order people usually need them.", {"docs/tutorial.md": TUTORIAL})
    commit(repo, RAFAEL, "2014-08-19", "Store jobs in SQLite so they survive a restart\n\nThe store keeps one row "
           "per job and the time of its last run.", {"almanac/store.py": STORE})
    commit(repo, TOMAS, "2015-03-03", "Handle the hour that repeats when clocks go back\n\nWhen a wall-clock time "
           "happens twice, a job runs at the first one and not again an hour later.",
           {"almanac/zones.py": ZONES + ZONES_FOLD})
    commit(repo, RAFAEL, "2016-11-11", "Lock the store while a job runs\n\nTwo workers on the same database no "
           "longer pick the same job: the first one to claim it wins.", {"almanac/store.py": STORE + STORE_LOCK})
    commit(repo, SANNA, "2017-06-02", "Explain retries in the tutorial\n\nPeople kept asking why a failing job did "
           "not run again at once.",
           {"docs/tutorial.md": TUTORIAL + "\n## Retries\n\nA job that fails is tried again later, and each wait is "
            "longer than the one before.\nAfter the last attempt the error is raised, so it shows up in your "
            "logs.\n"})
    commit(repo, INES, "2018-01-09", "Map my old address", {".mailmap": f"{INES[0]} <{INES[1]}> <{INES_OLD[1]}>\n"})
    commit(repo, NOOR, "2019-04-20", "Reformat with the code formatter",
           {"almanac/cli.py": CLI.replace("'", '"'), "almanac/cron.py": CRON.replace("'", '"')})
    commit(repo, NOOR, "2021-10-05", "Drop support for old Python versions",
           {"setup.cfg": "[metadata]\nname = almanac\n\n[options]\npackages = almanac\npython_requires = >=3.9\n"})
    formatted = CRON.replace("'", '"')
    start, end = formatted.index("def parse_field"), formatted.index("def parse(")
    commit(repo, NOOR, "2022-02-14", "Move field parsing into its own module",
           {"almanac/fields.py": ('"""Parse one field of a cron expression."""\n\n\n'
                                  + formatted[start:end].rstrip() + "\n"),
            "almanac/cron.py": formatted[:start] + "from .fields import parse_field\n\n\n" + formatted[end:]})
    commit(repo, BOT, "2025-03-17", "Bump the development requirements",
           {"requirements-dev.txt": "pytest==9.0.2\ncoverage==7.10.1\n"})
    commit(repo, NOOR, "2026-09-28", "Prepare the next release",
           {"almanac/__init__.py": "from .scheduler import Scheduler\n\n__version__ = '3.0'\n"})


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/make_demo.py <empty folder>")
    build(Path(sys.argv[1]))
