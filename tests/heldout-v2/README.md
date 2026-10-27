# Held-out set v2

Written by an independent writer who had not seen the word lists in `src/ofrenda/wording.py` or the
prompts in `src/ofrenda/cards.py` and `src/ofrenda/tone.py`. The second reading (`tone.py`) was frozen
and committed before these files were opened, and they were measured once, with no change to any
prompt or list afterwards. They were copied here after that measurement.

- `death.txt`, `judgment.txt`, `gendered.txt`: wording a card must not carry.
- `clean.txt`: respectful sentences, some with technical words that sound like the others (a process
  that is killed, dead code), to count false refusals.

`{name}` is replaced by the person on the card; lines without it are used as written. Results are in
`measurements/2026-10-27-gemma4-12b-tone.json`.
