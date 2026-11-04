# Changelog

## v0.1.0 — 2026-11-04

First release. `sub-watch` turns a local subcontractor
compliance registry — one CSV row per certificate of
insurance (COI), WSIB clearance certificate (Ontario), WCB
clearance letter (other provinces) or licence — into a
90/60/30/7-day chase report and ready-to-send renewal-request
letters, for the small general contractors whose current
system is a spreadsheet nobody remembers to open.

- `check REGISTRY.csv --as-of YYYY-MM-DD [--json]` bands
  every document by days from the as-of date to the recorded
  expiry: `expired` (< 0), `due_7` (0–7 — an expiry on the
  as-of date itself counts), `due_30` (8–30), `due_60`
  (31–60), `due_90` (61–90), `current` (> 90), `unknown`
  (no expiry recorded). Registry checks: a blank sub,
  document type or issuer and a blank expiry are errors;
  the same document recorded twice (case-insensitive) is a
  warning; one sub and document type carrying two different
  expiry dates is listed as info, with the chase using the
  earliest. Exit 1 when anything is expired or any registry
  error exists; exit 0 otherwise. `--as-of` is required —
  the tool never reads the machine clock, so a report is
  reproducible.
- `letters REGISTRY.csv --as-of YYYY-MM-DD --out DIR
  [--from NAME] [--within DAYS] [--json]` writes one
  renewal-request letter per sub with documents expired or
  due within the window (default 90 days; expired always
  included). A letter names each document, its issuer, its
  document number when recorded, and its exact timing
  ("expired 2026-10-20 (26 days ago)"); a document recorded
  twice is chased once; undated documents are excluded and
  their subs surface in the manifest. The tool sends
  nothing — the letters are drafts.
- `rules [--json]` prints the encoded bands, registry
  checks and notes with the basis of each, stamped "Encoded
  chase bands and notes, checked 2026-11 — clearance-
  certificate cycles and verification duties change; verify
  them with the WSIB or your provincial WCB." The notes
  state plainly what the tool does not do: the bands are
  reporting buckets, not law; WSIB/WCB validity cycles are
  not modelled; the registry is the only source; a quiet
  report is not a compliance verdict.
- Every output carries the honesty line: sub-watch is a
  watching aid — it is not legal or insurance advice, and
  every date comes from the registry the user typed, never
  from an issuer or a board.
- Agent-ready from birth: `--json` on every command, one
  object per run, `{"error": ...}` with exit 2 for input
  and usage errors (argparse included), exit 0 / 1 for
  OK / ACTION on `check`; SKILL.md documents the band
  table, the JSON shapes and the exit codes.
- Bundled examples: an 11-row registry for the fictional
  Example Ridge Contracting Ltd. with the classic defects
  planted — an expired COI, a blank issuer, a clearance
  whose expiry was never typed in, a certificate entered
  twice, and a renewal filed beside its predecessor (bands
  1 expired / 1 due_7 / 3 due_30 / 2 due_60 / 1 due_90 /
  2 current / 1 unknown; 2 errors, 1 warning, 1 info; five
  letters) — plus a clean 4-row registry, all documents
  current, no findings. Every subcontractor, insurer and
  company in the examples is fictional.
- Pure Python 3.10+ standard library. No network code, no
  tracking; dates are handled as calendar dates, so every
  day count is exact.
