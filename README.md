# ofrenda

[![test](https://github.com/vinimabreu/ofrenda/actions/workflows/test.yml/badge.svg)](https://github.com/vinimabreu/ofrenda/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An ofrenda for the people whose code still runs. Gemma 4 writes each card on your machine, and every word it quotes is checked against git.

Every long-lived repository carries lines written by people who stopped committing to it years ago. Their names are in `git blame`, one line at a time, and nowhere else. An ofrenda keeps people present. This one keeps present the people whose work still runs: it finds everyone who still has lines in the code and has moved on from the repository to other things, and gives each of them a card with what is still theirs, the oldest of their lines that still runs, and a sentence about what they left behind, in the words of their own commit messages.

![ofrenda: git finds who still has lines in the code, Gemma 4 writes each card on your machine, and code checks every quote](assets/ofrenda.gif)

The animation runs on the invented demo repository below. Every line and number in it comes from that run's output and from the files in [`measurements/`](measurements/); a 1280x720 video of it is in [`assets/ofrenda.mp4`](assets/ofrenda.mp4).

Here is the output for `almanac`, an invented job scheduler with fifteen years of history that [`scripts/make_demo.py`](scripts/make_demo.py) builds (every name in it is made up, and the commit ids come out the same on any machine), cut where it says `...`. The whole output is in [`examples/almanac.txt`](examples/almanac.txt).

```text
$ ofrenda almanac
/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\
ofrenda for almanac
6 people still have lines in almanac at 3aff65026d (2026-09-28); 5 of them
made no commit in the 730 days before it.

  The elder: the oldest line still running
       LICENSE:1, by Ines Okonkwo on 2011-03-14 (5ea5ca50f1)
       | MIT License
       from "Start almanac, a small job scheduler"

   )   Ines Okonkwo
  |'|  2011-03-14 to 2018-01-09, 4 commits
  |_|  69 lines still here (32.4% of the lines read), in 7 files

       Ines Okonkwo established the foundation for a small job scheduler. They
       implemented a system where schedules can be written as fields similar
       to how cron reads them.
       "Start almanac, a small job scheduler" (5ea5ca50f1, 2011-03-14)
       "Add cron-like expressions" (3bd5728192, 2011-04-02)
       "Keep the job list sorted by next run" (2370c0831d, 2011-09-20)
       (words by gemma4:12b on the second try, every quote checked against
       git)

       oldest line  LICENSE:1 (2011-03-14, 5ea5ca50f1)
                    | MIT License
       most lines   "Start almanac, a small job scheduler" (5ea5ca50f1,
                    2011-03-14), 43 lines

   )   Tomas Varga
  |'|  2012-02-11 to 2015-03-03, 3 commits
  |_|  41 lines still here (19.2% of the lines read), in 2 files

       Tomas Varga implemented logic to handle job retries with backoff and
       ensured the scheduler respects time zones during clock changes.
       "Retry failed jobs with backoff" (9c747ce829, 2012-06-30)
       "Teach the scheduler about time zones" (99340cb984, 2012-02-11)
       (words by gemma4:12b on the second try, every quote checked against
       git)

       oldest line  almanac/zones.py:1 (2012-02-11, 99340cb984)
                    | """Time zones for jobs: a job remembers the zone it w...
       most lines   "Retry failed jobs with backoff" (9c747ce829, 2012-06-30),
                    20 lines

   ... three more cards ...

/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\
Revision 3aff65026debda92e05289fc36c2b42249356c52 (2026-09-28). Blame options:
-w -M -C ignore-revs.
Files read: 14; skipped: none. Lines read: 213, of which 2 by bots.
Moved on: lines still here, and no commit reachable from the revision in the
730 days before its commit date.
Cards: 5; 3 written by gemma4:12b on the first try, 2 on the second, 0 from
git alone after two rejected answers. Quotes checked against the commit
messages: 12.
Second reading of each sentence for death, judgment or gender wording, by
gemma4:12b: 5 sentences read, 0 refused. It is a model too: it lowers what
gets through, not to zero.
Commit 8019e4f9ac "Reformat with the code formatter" still holds 18 lines. If
it only reformatted code, pass --ignore-rev 8019e4f9ac (or list it in .git-
blame-ignore-revs) to give those lines back.
```

Both cards came on the second try. In the first card's first answer Gemma quoted "a sorted list of jobs and a loop that runs the ones that are due", but the commit message says "One sorted list of jobs and a loop that runs the ones that are due"; the check refused the changed word. The second card's first answer said the scheduler "correctly manages time zones and repeating hours", and the check refused "hours", an amount word the messages do not have next to the same word. That sentence was faithful, so this refusal only cost a retry. Each time the model was asked again with the plain reason, and the second answer passed.

The same cards as a page: [`examples/ofrenda.html`](examples/ofrenda.html) (one self-contained file, no script, no request), and as Markdown a team could commit: [`examples/OFRENDA.md`](examples/OFRENDA.md).

"Moved on" means one thing here: the person made no commit reachable from the revision in the 730 days before the revision's date. In the code, such a person is a ghost of this repository and nothing more. Two things stand between a card and wording that suggests anyone died, judges them or guesses their gender: word lists in code, and a second reading of the sentence by the same local model. Neither is perfect, and both rates are measured below, on sentences written by someone who had not seen either. That is also why every card names the model that wrote its words and every quote names its commit.

## What the model does, and what code does

Every number, date, path and line of code on a card comes from git through plain code. Gemma 4 (12B, through [Ollama](https://ollama.com) on this machine) writes one thing: a sentence or two on what the person left behind and why it exists, with the phrases from their commit messages that back it up. Code checks every quoted phrase against the commit messages and runs the sentence through a list of rules; then the model reads the sentence once more, in a separate call, and answers three yes or no questions about it. Only then does the card use it.

```mermaid
flowchart LR
    rev[revision] --> files[files at the revision<br/>skip binary, vendored, generated]
    files --> blame[git blame -w -M -C<br/>+ .git-blame-ignore-revs]
    rev --> log[git log<br/>.mailmap at the revision]
    blame --> facts[people, lines, oldest line,<br/>top commit, who moved on]
    log --> facts
    facts --> cached{reply cached?}
    cached -- no --> gemma[Gemma 4 on Ollama<br/>127.0.0.1, temperature 0]
    gemma --> store[(reply cache)]
    store --> check
    cached -- yes --> check[check_card<br/>every quote against the messages]
    check -- holds --> tone{second reading:<br/>death, judgment,<br/>gender?}
    tone -- no --> card[card]
    tone -- yes --> retry
    check -- fails once --> retry[ask again with<br/>the plain reason] --> check2[check_card<br/>+ second reading]
    check2 -- holds --> card
    check2 -- fails --> fallback[card from git alone:<br/>top commit subject, as is] --> card
    card --> out[terminal, OFRENDA.md, HTML, JSON]
```

### The facts on a card

For each person, from `git blame` at the revision and `git log` up to it:

- name, first and last commit dates (their own author dates), number of commits;
- lines still in the code, their share of all the lines read, and the files that carry them;
- the oldest of their lines that still runs: path and line number, the code, the commit and its date. Lines shorter than eight characters or with fewer than three letters (a lone bracket, a blank line) are passed over when the person has any other line;
- the commit of theirs that still holds the most lines, with its subject.

And for the whole repository, the elder: the oldest line still running, whoever wrote it. On the HTML page the elder gets a candle only when they moved on, and a marigold when they still commit.

Bots and CI accounts (a `[bot]` marker, names such as dependabot, renovate, jenkins, travis, circleci, buildbot, GitHub Actions, GitLab CI, Azure Pipelines or AppVeyor, as the name or the address) are counted in the totals and get no card and no elder line.

People are listed by surviving lines, most first; `--top` keeps the first ten by default. Who moved on is measured from the revision's commit date, not from today, so the same revision gives the same cards on any day.

### The check on every card

The model receives, for one person, the full commit messages (subject and body, sign-off trailers removed, at most 12 messages and 7,000 characters) of the commits that still have lines at the revision, a few of those lines, and the paths that carry them. No count and no date go into the prompt, and the prompt has no example answer (an example in a prompt is an answer the model reaches for when it is unsure). It answers with JSON: `text` and `quotes`. [`check_card`](src/ofrenda/cards.py) uses the answer only when:

- there are one to three quotes, each with two words that have letters, eight characters or more and at most 200 characters, and each one is copied from a single message and starts and ends on a word boundary of it: whitespace aside, case, punctuation and every letter must match (quote marks around a quote and a full stop at its end are trimmed). A quote stitched from two messages, a word changed, a letter swapped for a lookalike from another alphabet, a quote that starts inside a word ("break the build" out of "Unbreak the build"): all refused;
- text inside any quotation marks in the sentence (straight or curly, double or single, guillemets) is also copied from a message, and no quotation mark is left open;
- the sentence has no control characters or markup, no date, commit hash, email address, link, file name or path (the card prints those from git next to it), and no amount in digits or in words (`fifteen`, `half`, `a third`, `percent`, `days`) unless a message has it next to the same word (`Python 3`, `Jinja2`, "the hour that repeats");
- every capitalized word, the first word of a sentence included unless it is a plain starter such as "They" or "The", and every `camelCase` or `snake_case` identifier or code in backticks, appears in what the model was given, or is one of a few generic computing words such as API or JSON;
- the sentence uses none of the words on three lists in [`wording.py`](src/ofrenda/wording.py): death, mourning and the afterlife in English, Spanish and Portuguese (`lost`, `gone`, `sleeps` and `no more` only with the person as subject or object, so "a lost connection" still passes); words that judge the person (`sloppy`, `lazy`); and gendered pronouns, titles and nouns (`his`, `Mr.`, `gentleman`, `man`, but not "man page"), since the card does not guess anyone's gender. In a quote, only phrases that are about a death in any context are refused (`rest in peace`, `passed away`, `RIP` in capitals), so a commit that says "rip out the old loader" can still be quoted.

### A second reading of the sentence

The lists catch the words on them. So a sentence that passes them goes back to the same model in a separate call, at temperature 0, with a JSON schema and no example in the prompt ([`tone.py`](src/ofrenda/tone.py)): does it say or suggest that the person died, does it insult or judge the person or their work, does it assume their gender? A yes refuses the sentence like any other rule, with the plain reason ("a second reading by the model says the sentence suggests the person died"). A reply that is not the JSON asked for gets one more try and then counts as a refusal, so a broken reading never lets a sentence through. Verdicts are cached with the card. It costs one call of about 0.71 seconds per sentence read, and `--no-tone-check` turns it off.

The reader is a model too. It lowered what gets through a lot, as the measurement below shows; it did not make it zero, and on other sentences it can refuse something that was fine.

When an answer fails, the model is asked once more with the plain reason (for example `the quote "..." is not in any of their commit messages`) and nothing else: no corrected version, not even its own previous answer. When the second answer fails too, the card is built from git alone: the subject line of the person's top commit, quoted as it is, marked "from git alone". No quote is invented on either path. The sentence on a card that passed can still say things the messages do not support: the rules above are lists and patterns, and a plain lowercase claim ("added redis support") or a paraphrase that is on no list gets through. Each card says which model wrote its words, and every quote on it names the commit it came from, so you can read the whole message.

### Slow the first time, instant after

Facts are cached per commit id and blame options; replies are cached per model and prompt version, keyed by the revision, the person and the exact prompt, so new facts are a new question. Both live in `~/.cache/ofrenda/` (or `$XDG_CACHE_HOME`, `$OFRENDA_CACHE`, `--cache`), readable only by you. The check runs again on every use, so a cached reply gets no free pass.

## Safe to run on a repository you did not write

ofrenda reads git objects. It never checks out, never touches a working tree or an index, and never runs anything from the repository. A repository can ask git to run programs during ordinary reads; ofrenda is built so that git never acts on those requests:

- the real repository answers a few plumbing questions (where its objects are, their hash format, whether it is shallow, which commit a revision names). Every other read (tree, blobs, blame, log, attributes) runs against a shadow repository in a private temporary folder whose `objects/info/alternates` points at the real objects. git never reads the repository's own `config` there, so a `core.fsmonitor` command, a textconv driver, `gpg.program` with `log.showSignature`, a pager, a filter, an external diff or a promisor remote in it has nothing to act on;
- the calls to the real repository are `rev-parse` only, which runs no diff, filter or textconv. They carry `-c` overrides for `core.fsmonitor`, `core.hooksPath`, `core.pager`, `log.showSignature`, the `gpg` programs, `protocol.allow` and `mailmap.file`; the system and global config are ignored, the work tree is an empty folder, and lazy fetching, every transport and replace refs are turned off;
- blame runs with `--no-textconv`, log with `--no-show-signature` and `--no-ext-diff`;
- `.mailmap`, `.gitattributes` and `.git-blame-ignore-revs` are read from the tree at the revision, never from disk.

[`tests/test_safety.py`](tests/test_safety.py) plants these in a repository (a textconv driver, an fsmonitor hook, a signature program on a signed commit, an external diff, a pager, smudge and clean filters, hooks, an `sshCommand`), shows for five of them (textconv, fsmonitor, the signature program, the external diff, the smudge filter) that plain git does run the planted program, then runs ofrenda and checks that nothing ran. A partial clone is read without fetching: the missing files are reported and left out, and the object store is unchanged afterwards.

Text from the repository (names, commit messages, code) is untrusted too. On the terminal and in the HTML, control characters and Unicode direction overrides are printed as escapes, so a commit message or an author name can't move the cursor, write to your clipboard or reorder what you read. In Markdown, names and messages are escaped, code goes in fences longer than any run of backticks inside it, and a pipe in a path can't break a table. In HTML, every value is escaped and the page carries a Content Security Policy that allows no script and no request. Email addresses in anything shown (subjects, quotes, lines of code, the JSON) are printed as `<email>`; the quote check still runs on the messages as they are.

For a repository you did not write, the recommended setup is still a bare clone, which has no working tree and a config git wrote itself:

```sh
git clone --bare https://github.com/OWNER/REPO.git
ofrenda REPO.git
```

The model client talks only to an Ollama on this machine. It ignores proxy settings, follows no redirects, and refuses a cloud model served through the local Ollama unless you pass `--allow-remote-model`.

## Blame options, measured

Plain `git blame` gives each line to the last commit that touched it, so whoever reindented a file, moved a function or ran a formatter takes the credit for lines someone else wrote. Each option gives some of those lines back. Measured on bare clones of four public repositories (pallets/flask, psf/requests, bottlepy/bottle and paramiko/paramiko) at their HEAD on 26 October 2026, blaming every file ofrenda keeps: median of 3 runs with 8 parallel jobs, and one run with a single job, on a machine with 18 cores.

| repository | history | lines | option | 8 jobs | 1 job | lines given to someone other than plain blame |
|---|---:|---:|---|---:|---:|---:|
| flask | 5,562 commits | 34,635 | plain | 1.38 s | 5.59 s |  |
| | | | -w -M | 1.43 s | 6.13 s | 2,435 |
| | | | -w -M + ignore list | 1.45 s | 6.03 s | 2,435 |
| | | | **-w -M -C + ignore list** | 1.96 s | 8.73 s | 4,212 (12.2%) |
| | | | -w -M -C -C + ignore list | 2.20 s | 11.02 s | 4,232 |
| requests | 6,496 commits | 19,461 | plain | 0.69 s | 2.72 s |  |
| | | | -w -M | 0.82 s | 2.98 s | 1,103 |
| | | | -w -M + ignore list | 0.85 s | 3.07 s | 3,041 |
| | | | **-w -M -C + ignore list** | 0.96 s | 3.64 s | 3,128 (16.1%) |
| | | | -w -M -C -C + ignore list | 1.16 s | 5.48 s | 3,280 |
| bottle | 1,999 commits | 13,894 | plain | 0.31 s | 1.43 s |  |
| | | | -w -M | 0.55 s | 1.86 s | 256 |
| | | | -w -M + ignore list | 0.57 s | 1.90 s | 256 |
| | | | **-w -M -C + ignore list** | 0.58 s | 2.38 s | 422 (3.0%) |
| | | | -w -M -C -C + ignore list | 0.60 s | 2.94 s | 434 |
| paramiko | 4,086 commits | 31,810 | plain | 0.82 s | 3.60 s |  |
| | | | -w -M | 0.87 s | 4.07 s | 1,789 |
| | | | -w -M + ignore list | 0.92 s | 4.35 s | 3,794 |
| | | | **-w -M -C + ignore list** | 1.30 s | 6.24 s | 4,234 (13.3%) |
| | | | -w -M -C -C + ignore list | 1.53 s | 7.74 s | 4,368 |

- `-w` (whitespace) and `-M` (lines moved inside a file) cost little: at most 0.24 s more with 8 jobs (0.546 s against 0.307 s, on bottle, whose code is one large file).
- The ignore list costs nothing and matters where it exists. requests and paramiko each list one formatter run in `.git-blame-ignore-revs`; honoring it gives 1,938 and 2,005 lines back to the people who wrote them.
- `-C` (lines moved or copied from another file changed in the same commit) costs 2% to 43% more time with 8 jobs, under half a second here (18% to 45% with one job), and gives back 1,777 more lines in flask, where modules were split, and 87 to 440 in the others.
- `-C -C` (also copies from other files in the commit that created the file) costs another 4% to 21% for 12 to 152 more lines.

So ofrenda blames with `-w -M -C` and the ignore list, and `--no-copies` drops `-C`. With `-C`, 27 more people still have lines in flask (437 instead of 410). The full table, with the number of people who moved on under each option, is in [`measurements/2026-10-26-summary.md`](measurements/2026-10-26-summary.md).

flask has no ignore list, and its "Reformat with black" commit still holds 2,167 lines after all four options; ofrenda prints that commit under the cards with the `--ignore-rev` that would give them back.

## Measured on four public repositories

The same four bare clones, a card for each of the 10 people with the most surviving lines among those who moved on (no commit in the 730 days before HEAD), with `gemma4:12b` (Q4_K_M, digest `6114515d63c1`) through Ollama on the same machine. Counts only: the raw output, with real names, stays outside this repository. Everything is in [`measurements/`](measurements/), produced by [`scripts/measure.py`](scripts/measure.py), [`scripts/measure_seeds.py`](scripts/measure_seeds.py) and [`scripts/measure_blame.py`](scripts/measure_blame.py) from the code in this commit.

| repository | people with lines | moved on | cards | first try | after retry | from git alone | quotes checked | first run | second run |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flask | 437 | 415 | 10 | 8 | 1 | 1 | 24 | 30.26 s | 0.23 s |
| requests | 500 | 469 | 10 | 9 | 0 | 1 | 25 | 29.11 s | 0.33 s |
| bottle | 159 | 147 | 10 | 10 | 0 | 0 | 26 | 25.07 s | 0.25 s |
| paramiko | 136 | 134 | 10 | 10 | 0 | 0 | 30 | 33.48 s | 0.30 s |
| total | | | 40 | 37 | 1 | 2 | 105 | | |

The first run blames, asks the model for words 10 to 12 times (2.28 to 3.09 seconds per call, median prompts of 1,074 to 1,662 characters), reads each sentence that passed the lists a second time (38 readings, 0.53 to 0.65 seconds each, 0 refused) and writes the cards. The second run reads the facts, the replies and the readings from the cache and prints the same output, byte for byte, in 0.23 to 0.33 seconds. With `--no-model` the first run takes 1.36 to 3.07 seconds.

Five answers were refused, and every refusal held up when read by hand. Three quoted a single word: for one person the model quoted their one-word top commit message twice, so that card fell back to git alone and shows the word as the subject it is, and another person's card passed on the retry. The other two (one answer and its retry) quoted `Add async support` where the message says ``Add `async` support``, with backticks; that card fell back to git alone too.

A second cold run, right after the first, wrote the same 40 cards, word for word. The time per call did not repeat: it went from 2.28 to 3.09 seconds to 2.76 to 4.37 seconds. Other programs were open on the machine during both runs, and the cause was not isolated.

Neither the stricter lists that came out of an audit nor the second reading refused any of these answers: the counts above are the same as before both.

### Breaking good answers on purpose

To see whether the check lets anything through, [`ofrenda.tamper`](src/ofrenda/tamper.py) takes the 38 answers that passed and breaks each one in every way it knows: a word swapped, dropped or added inside a quote, the case of a letter changed, a letter replaced by a lookalike from another alphabet, a quote that starts inside a word, a quote joined across two messages, a quote from someone else's messages, an invented quote, no quote at all, and a number, an amount in words, a year, a hash, a path, an email address, a link, four kinds of death wording, an insult, a gendered pronoun, title or noun, an invented name (at the start of the sentence too), or an invented quote in double, single or angle quotes added to the sentence. A broken answer is kept only when it really is wrong.

**1,637 broken answers, 0 passed the check.** Per kind of break, in [`measurements/2026-10-26-gemma4-12b-seeds.json`](measurements/2026-10-26-gemma4-12b-seeds.json). The same measurement runs in the test suite on invented data. These breaks are made of the very words the rules look for, so this number says the rules are wired in, not that the lists are complete.

### Wording that is on no list

Two held-out sets test the parts that are only screened. [`tests/heldout`](tests/heldout) (45 death and mourning paraphrases in English, Spanish and Portuguese, 26 put-downs, 20 gendered phrases without a pronoun) was written by me before the word lists, and never added to them. [`tests/heldout-v2`](tests/heldout-v2) (50 death, 35 judgment, 30 gendered, and 80 respectful sentences with technical traps such as a killed worker or dead code) was written by an independent writer who had seen neither the lists nor the prompts. The second reading was frozen and committed before that folder was opened, and both sets were measured once, with no change to any list or prompt afterwards.

Each sentence was put on real people from the four repositories with their real quotes, so a refusal can only come from the sentence. The lists ran on all 38 people whose answers passed; the second reading, and both together, on 8 of them, two per repository (2,326 readings). Refused, in percent of trials:

| set | lists | second reading | both |
|---|---:|---:|---:|
| death and mourning, my set | 24.4% | 96.4% | 96.4% |
| death and mourning, independent set | 73.8% | 94.2% | 99.8% |
| judging the person, my set | 3.8% | 96.2% | 96.2% |
| judging the person, independent set | 56.6% | 100.0% | 100.0% |
| gendered wording, my set | 25.0% | 90.0% | 90.0% |
| gendered wording, independent set | 86.7% | 79.2% | 95.0% |
| **false refusals**: respectful sentences, independent set | 21.2% | 0.0% | 21.2% |
| **false refusals**: the 38 real sentences that passed the lists | 0.0% | 0.0% | 0.0% |

On the independent set, lists and second reading together refused 99.8% of the death wording, 100.0% of the put-downs and 95.0% of the gendered wording. So some still gets through. The second reading refused none of the respectful sentences and none of the real ones. The 21.2% of respectful sentences the lists refused is mostly the check doing its other job: those sentences were not written from these people's commit messages, so they name things the messages do not (an acronym, an operating system) or carry an amount; only 3.75% of those trials (24 of 640 on the sample) were refused for death, judgment or gender words ("dead" in dead code, "outlived", and the Portuguese "eles"). The full numbers are in [`measurements/2026-10-27-gemma4-12b-tone.json`](measurements/2026-10-27-gemma4-12b-tone.json).

I read the 40 real cards above by hand, and none of them carries death, put-down or gendered wording.

## Install

You need Python 3.11 or newer, git, and for the sentences, Ollama with the model:

```sh
ollama pull gemma4:12b
pipx install git+https://github.com/vinimabreu/ofrenda
```

There are no Python dependencies. Without Ollama, `--no-model` builds every card from git alone.

## Use

```sh
ofrenda                                  # the repository you are in, at HEAD
ofrenda path/to/repo.git                 # a bare clone
ofrenda --rev v1.0 --quiet-days 365      # another revision, another threshold
ofrenda --top 0                          # a card for everyone who moved on
ofrenda --md OFRENDA.md --html ofrenda.html --json ofrenda.json
ofrenda --ignore-rev 8019e4f9ac          # blame past a formatter commit
ofrenda --no-copies                      # blame without -C (faster on very large repositories)
ofrenda --no-model                       # cards from git alone
ofrenda --no-tone-check                  # skip the second reading of each sentence
ofrenda --model qwen3:8b                 # another local model
```

`python -m ofrenda` works the same way. Colors follow the terminal: none when the output is piped or `NO_COLOR` is set.

## Tests

```sh
pip install pytest
pytest -q
```

On the machine that made the measurements, with Ollama running (so the one test that talks to the real model ran too):

```text
353 passed in 32.63s
```

The suite builds its repositories in temporary folders with invented authors and dates, uses a fake model, and needs no network. One test talks to a real Ollama and is skipped when there is none.

## Where it is weak

- The sentence. Quotes are verified; the sentence around them is only screened. A plain lowercase claim the messages do not make ("added redis and kubernetes support", "built the sorted job list" when someone else did) passes the rules, and the second reading does not look for it. On the independent held-out set, 0.2% of the death wording, 0.0% of the put-downs and 5.0% of the gendered wording still got through both layers.
- The second reading is the same model judging its own kind of text. It was measured on one set of respectful sentences and on 38 real ones, with no false refusal, but that is two sets; on other text it can refuse a good sentence (which costs a retry, or a card from git alone) or pass a bad one.
- The word lists hold what an audit of ofrenda named, with inflections and Spanish and Portuguese translations. My held-out set was written before the lists and never added to them, but by the same person; the second set was written by someone else, blind.
- Amount words are refused unless a message has them next to the same word, so a faithful sentence with "one" or "hours" in it costs a retry. Capitalized words, the first word of a sentence included, must come from what the model saw, so an ordinary word at the start of a sentence that the messages lack (say "Retries" when the messages never use it) also costs a retry.
- Activity is the author date: a change written long ago and applied recently counts on the day it was written. A wrong clock in an old commit puts that commit on the wrong day.
- One person is one canonical email address after the `.mailmap` at the revision, and two addresses that carry the same full name are joined (generic names such as `root` are not). Two different people with the same full name become one card, and so do two people who committed under one shared address (a `dev@localhost` or a team address); someone who changed both name and address without a `.mailmap` entry shows up twice. Joining errs in the safer direction: it can hide a card, never announce a departure that did not happen.
- Blame is git's line matching. `-C` follows code moved or copied from files changed in the same commit; copies from files that commit left alone are found only by `-C -C` and `-C -C -C`, which cost more (see above). A formatter commit that is not listed in `.git-blame-ignore-revs` keeps the lines it touched: ofrenda names such commits under the cards and tells you how to pass them with `--ignore-rev`, and never ignores one on its own.
- What counts as code is a rule list in [`files.py`](src/ofrenda/files.py): binary, vendored, generated (lockfiles, minified files, gettext catalogs) and very large files are skipped; documentation and tests count.
- The check was changed twice before the runs above. After a preliminary run on the same four repositories, it rejected faithful sentences that carried `Python 3` and `Jinja2` copied from the messages and split one person's name at a middle initial; both were fixed. Then an audit got 45 bad sentences through it (death paraphrases, amounts in words, invented quotes in single quotes, insults, gendered titles, quotes that start inside a word); the rules above came from that audit. The measured runs came after both, with the code frozen.
- The numbers are one model (`gemma4:12b`, Q4_K_M) on one machine (Apple silicon, 18 cores). Other models and machines will be slower or faster, and will write other sentences.
- On a shallow clone, lines older than its history are credited to its oldest commit; the output says when a clone is shallow.
- Tested on macOS (Python 3.14, git 2.54) and in Linux containers: the whole suite on Python 3.12 with git 2.54 (352 passed, the real-model test skipped), and on Python 3.11 and 3.13, whose images have no git, the six test files that need none (`test_cards`, `test_model`, `test_render`, `test_seeds`, `test_tone`, `test_wording`: 244 passed on each). The workflow in `.github/workflows` runs the whole suite on Python 3.11, 3.12 and 3.13. Windows is not tested.

## License

MIT
