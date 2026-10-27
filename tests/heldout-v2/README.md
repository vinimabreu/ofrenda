# Held-out set v2

Written separately, in a process with no access to the word lists in `src/ofrenda/wording.py` or the
prompts in `src/ofrenda/cards.py` and `src/ofrenda/tone.py`. The second reading (`tone.py`) was
committed (12c224f) before these files were opened, and they were measured once, with the word lists
of that commit and no change to any prompt afterwards. They were copied here after that measurement.
The word lists changed later, after an audit, and after these files had been seen: results with the
later lists are reported apart and are not blind.

- `death.txt`, `judgment.txt`, `gendered.txt`: wording a card must not carry.
- `clean.txt`: respectful sentences, some with technical words that sound like the others (a process
  that is killed, dead code), to count false refusals.

`{name}` is replaced by the person on the card; lines without it are used as written. Results are in
`measurements/2026-10-27-gemma4-12b-tone-by-reason.json` (by the right reason) and
`measurements/2026-10-27-gemma4-12b-tone.json` (the blind run as it came out).
