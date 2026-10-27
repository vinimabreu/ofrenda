# Ofrenda for almanac

An ofrenda keeps people present. This one keeps present the people whose work still runs here: they have lines in the code at this revision and have moved on from this repository to other things. Their code did not.

6 people still have lines in almanac at 3aff65026d (2026-09-28); 5 of them made no commit in the 730 days before it.

## The elder

The oldest line still running is `LICENSE:1`, written by Ines Okonkwo on 2011-03-14 in "Start almanac, a small job scheduler" (`5ea5ca50f1`).

```text
MIT License
```

## Ines Okonkwo

> Ines Okonkwo established the foundation for a small job scheduler. They implemented a system where schedules can be written as fields similar to how cron reads them.
>
> In their words: "Start almanac, a small job scheduler" (`5ea5ca50f1`, 2011-03-14); "Add cron-like expressions" (`3bd5728192`, 2011-04-02); "Keep the job list sorted by next run" (`2370c0831d`, 2011-09-20)

*words by gemma4:12b on the second try, every quote checked against git*

| | |
|---|---|
| Commits | 4, from 2011-03-14 to 2018-01-09 |
| Lines still here | 69 (32.4% of the lines read), in 7 files |
| Most lines | "Start almanac, a small job scheduler" (`5ea5ca50f1`, 2011-03-14): 43 lines |
| Oldest line | `LICENSE:1` (2011-03-14, `5ea5ca50f1`) |

```text
MIT License
```

## Tomas Varga

> Tomas Varga implemented logic to handle job retries with backoff and ensured the scheduler respects time zones during clock changes.
>
> In their words: "Retry failed jobs with backoff" (`9c747ce829`, 2012-06-30); "Teach the scheduler about time zones" (`99340cb984`, 2012-02-11)

*words by gemma4:12b on the second try, every quote checked against git*

| | |
|---|---|
| Commits | 3, from 2012-02-11 to 2015-03-03 |
| Lines still here | 41 (19.2% of the lines read), in 2 files |
| Most lines | "Retry failed jobs with backoff" (`9c747ce829`, 2012-06-30): 20 lines |
| Oldest line | `almanac/zones.py:1` (2012-02-11, `99340cb984`) |

```python
"""Time zones for jobs: a job remembers the zone it was created in."""
```

## Mei Lindqvist

> Mei Lindqvist provided a tutorial for users to learn the system and added a command line interface for operators to manage scheduled jobs.
>
> In their words: "Write the tutorial" (`dd2b602a08`, 2013-05-04); "Add a command line to list and run jobs" (`3b05f08714`, 2013-01-15)

*words by gemma4:12b, every quote checked against git*

| | |
|---|---|
| Commits | 2, from 2013-01-15 to 2013-05-04 |
| Lines still here | 34 (16.0% of the lines read), in 2 files |
| Most lines | "Write the tutorial" (`dd2b602a08`, 2013-05-04): 22 lines |
| Oldest line | `almanac/cli.py:1` (2013-01-15, `3b05f08714`) |

```python
"""almanac list / almanac run: a small command line around the scheduler."""
```

## Rafael Oyelaran

> Rafael Oyelaran implemented a persistent storage system to ensure jobs survive a restart and added locking to prevent multiple workers from claiming the same task.
>
> In their words: "Store jobs in SQLite so they survive a restart" (`67252d2c51`, 2014-08-19); "Lock the store while a job runs" (`455f42b64d`, 2016-11-11); "the first one to claim it wins" (`455f42b64d`, 2016-11-11)

*words by gemma4:12b, every quote checked against git*

| | |
|---|---|
| Commits | 2, from 2014-08-19 to 2016-11-11 |
| Lines still here | 34 (16.0% of the lines read), in 1 file |
| Most lines | "Store jobs in SQLite so they survive a restart" (`67252d2c51`, 2014-08-19): 24 lines |
| Oldest line | `almanac/store.py:1` (2014-08-19, `67252d2c51`) |

```python
"""Jobs kept in SQLite, so a restart does not forget them."""
```

## Sanna Petrova

> Sanna Petrova added an explanation of how the system handles retries for failing jobs. This ensures users understand why a job does not run again immediately.
>
> In their words: "Explain retries in the tutorial" (`5d347a71e2`, 2017-06-02); "why a failing job did not run again at once" (`5d347a71e2`, 2017-06-02)

*words by gemma4:12b, every quote checked against git*

| | |
|---|---|
| Commits | 1, from 2017-06-02 to 2017-06-02 |
| Lines still here | 5 (2.3% of the lines read), in 1 file |
| Most lines | "Explain retries in the tutorial" (`5d347a71e2`, 2017-06-02): 5 lines |
| Oldest line | `docs/tutorial.md:24` (2017-06-02, `5d347a71e2`) |

```markdown
## Retries
```

---

### How this page was made

- Revision 3aff65026debda92e05289fc36c2b42249356c52 (2026-09-28). Blame options: -w -M -C ignore-revs.
- Files read: 14; skipped: none. Lines read: 213, of which 2 by bots.
- Moved on: lines still here, and no commit reachable from the revision in the 730 days before its commit date.
- Cards: 5; 3 written by gemma4:12b on the first try, 2 on the second, 0 from git alone after two rejected answers. Quotes checked against the commit messages: 12.
- Commit 8019e4f9ac "Reformat with the code formatter" still holds 18 lines. If it only reformatted code, pass --ignore-rev 8019e4f9ac (or list it in .git-blame-ignore-revs) to give those lines back.
- Made with ofrenda 0.1.0. Every number, date, path and line of code above comes from git. The sentences come from a model running on the machine that made this page. They are used only when every phrase they quote is in that person's commit messages and they pass a list of word rules; a sentence can still say something the messages do not support.
