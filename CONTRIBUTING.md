# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** sub-watch's promise is
  "clone and run". Pull requests that add a third-party dependency
  will not be merged.
- **Local only.** No network calls, no telemetry, no uploads of user
  files. A compliance registry is a contractor's whole sub roster;
  it never leaves the machine. The tool also sends nothing — letters
  are drafts, and any change that makes the tool transmit a letter
  or a registry row will not be merged.
- **The registry is the only source.** Every date, issuer and
  document type in a report or letter comes from a registry row.
  Features that look dates up, model a board's clearance cycle, or
  infer a document's status from anything but the typed expiry do
  not belong here — WSIB/WCB cycles change, and the tool's notes
  say so, stamped with their checked date.
- **An OK must never be worded as compliance.** The honesty lines
  in the reports are load-bearing. Wording changes that soften
  "no expiry date in the registry has passed" into "the sub is
  compliant" will not be merged. The tool is a watching aid, not
  legal or insurance advice — that sentence stays in every output.
- **Band edges are pinned by hand.** The bands live in the `BANDS`
  table in `src/sub_watch.py`, and the README, SKILL.md and
  CHANGELOG state the same bands. Any change to a band edge is a
  behaviour change: it needs all three documents, the changelog
  and the tests updated together, with tests at the edge (in the
  band) and one day past it (in the next). The bundled sample's
  band counts (1 expired / 1 due_7 / 3 due_30 / 2 due_60 / 1 due_90 /
  2 current / 1 unknown), findings (2 errors / 1 warning / 1 info)
  and five letters were counted by hand when the file was built;
  if a change moves them, the recount must be shown.
- **No clock reads.** `--as-of` is required precisely so runs are
  reproducible. A change that defaults a date from the machine
  clock will not be merged.

## Getting started

```bash
git clone https://github.com/jasveerai88/sub-watch
cd sub-watch
python3 -m unittest discover -s tests -v
python3 src/sub_watch.py check examples/sample.csv --as-of 2026-11-15
python3 src/sub_watch.py letters examples/sample.csv --as-of 2026-11-15 --out letters-out --from "Example Ridge Contracting Ltd."
python3 src/sub_watch.py rules
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if the
   CLI output changes.
