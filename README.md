# sub-watch

**Watch every subcontractor's insurance certificates, WSIB/WCB clearances and licences from one local registry — and get the chase report and renewal letters before a lapse lands on your own policy.**

A general contractor has to hold a current compliance document for every subcontractor on every job: the certificate of insurance (COI), the WSIB clearance certificate in Ontario, the WCB clearance letter in other provinces, the trade and business licences. Collecting them is easy. The failure mode is a certificate lapsing mid-project and nobody noticing — an injury claim from a lapsed sub lands on the GC's own policy, and one GC's account of exactly that (a 28% premium hike and forty hours proving due diligence) is the loudest story in this trade. The usual tool is a spreadsheet nobody remembers to open: at 10 projects × 15 subs × several documents each, that is hundreds of expiry dates, and the lapse has already happened by the time anyone checks.

sub-watch is the watching half of that spreadsheet. Type each document once — sub, document type, issuer, expiry — into a plain CSV, then run the chase report whenever you like: every document banded expired / due in 7 / 30 / 60 / 90 days, registry mistakes flagged, and a ready-to-send renewal-request letter drafted per sub. Local-first on purpose: no cloud account, no per-seat pricing, and your sub list never leaves your machine. (The cloud incumbents — TrackMyVendor, COI File, Workhand — are good software; this is for the small GC who won't pay per-seat rent to watch dates.)

> **Encoded chase bands and notes, checked 2026-11 — clearance-certificate cycles and verification duties change; verify them with the WSIB or your provincial WCB.**
>
> sub-watch is a watching aid: it is not legal or insurance advice, and it sends nothing — the letters are drafts you send yourself. Every date in a report or letter comes from your registry — a report with nothing expired means no expiry date *in the registry* has passed, not that a sub's coverage is adequate or its certificate genuine.

## What it does

**The chase bands** (days from the `--as-of` date you give the run to the recorded expiry):

| Band | Window | Meaning |
|------|--------|---------|
| `expired` | before the as-of date | Already lapsed — chase today |
| `due_7` | 0–7 days (expires today counts) | Inside a week — the renewal should already be in motion |
| `due_30` | 8–30 days | Inside a month — send the renewal request |
| `due_60` | 31–60 days | Inside two months — goes out with the next chase round |
| `due_90` | 61–90 days | Inside a quarter — on the watch list |
| `current` | over 90 days | No action — reported as a count |

**The registry checks** (run `sub-watch rules` for the full table with the basis of each):

| Check | Severity | What it catches |
|-------|----------|-----------------|
| `missing_field` | error | A blank `sub`, `doc_type` or `issuer` — the row cannot be chased |
| `expiry_missing` | error | No expiry date recorded — the document cannot be watched at all |
| `duplicate_document` | warning | The same document (sub + doc type + issuer + expiry, case-insensitive) recorded twice |
| `same_type_multiple_expiry` | info | One sub and doc type carrying two different expiry dates — usually a renewal filed beside the old row; the chase uses the earliest |

**The letters**: one `.txt` per sub with anything expired or due inside the window (default 90 days, `--within` to change it; expired is always included). A letter names each document, its issuer, its document number if recorded, and its exact timing ("expired 2026-10-20 (26 days ago)"). The same document recorded twice is chased once. The tool writes drafts — it sends nothing.

## Input format

One CSV, one row per document. Headers are matched case-insensitively with spaces, dashes and underscores ignored (`Doc Type`, `doc-type` and `doc_type` all work; `Subcontractor`, `Issued By` and `Expiry Date` are accepted too). Extra columns are ignored. Blank lines are skipped.

| Column | Required | Notes |
|--------|----------|-------|
| `sub` | yes | The subcontractor's name, as you want it in letters |
| `doc_type` | yes | Free text as typed: `COI (CGL)`, `WSIB clearance`, `WCB clearance`, `Business licence`, … |
| `issuer` | yes | Who issued it: the insurer, `WSIB`, `WorkSafeBC`, a municipality, … |
| `expiry` | yes | `YYYY-MM-DD` — the date the document stops being current |
| `doc_number` | no | Policy / certificate number; printed in letters when present |
| `contact_email` | no | Carried into the letters manifest so you (or an agent) can send the draft |
| `notes` | no | Free text, carried through untouched |

Deliberately no PDF parsing: you type each date once, the tool does the watching. A non-blank expiry that isn't a real `YYYY-MM-DD` date is an input error (exit 2) naming the row — the tool never guesses a date.

## Usage

```bash
# The chase report (exit 0 nothing expired and no registry errors / 1 action needed / 2 input)
python3 src/sub_watch.py check registry.csv --as-of 2026-11-15
python3 src/sub_watch.py check registry.csv --as-of 2026-11-15 --json

# Renewal-request letters, one file per sub
python3 src/sub_watch.py letters registry.csv --as-of 2026-11-15 --out letters-out --from "Your Company Ltd."
python3 src/sub_watch.py letters registry.csv --as-of 2026-11-15 --out letters-out --within 30

# The encoded bands, checks and notes, with their bases
python3 src/sub_watch.py rules
```

`--as-of` is required on `check` and `letters`: the tool never reads the machine clock, so a report is reproducible and "today" is always a date you chose. Letters are written only when at least one is needed — a clean run creates no directory and says so.

### For agents and scripts

Every command accepts `--json` and prints exactly one JSON object. Input and usage errors — argparse included — print `{"error": "..."}` and exit 2. See `SKILL.md` for the JSON schemas, the band table and the honesty rules an agent must respect.

## Real runs (verbatim)

The bundled `examples/sample.csv` is the fictional Example Ridge Contracting Ltd.'s registry, with the classic defects planted — one expired COI, one blank issuer, one clearance whose expiry was never typed in, one certificate entered twice, and one renewal filed beside its predecessor. `examples/clean.csv` is a tidy registry. Every run below is dated `--as-of 2026-11-15`; the day counts were counted by hand from the rows.

```
$ python3 src/sub_watch.py check examples/sample.csv --as-of 2026-11-15
sub-watch v0.1.0 — chase report for sample.csv · as of 2026-11-15 (11 document(s) in the registry)
Encoded chase bands and notes, checked 2026-11 — clearance-certificate cycles and verification duties change; verify them with the WSIB or your provincial WCB.

EXPIRED — chase today (1):
  Brightline Electrical Ltd. — COI (CGL) · NorthPeak Insurance Co. · expired 2026-10-20 (26 days ago)

DUE IN 7 DAYS (1):
  Brightline Electrical Ltd. — WSIB clearance · WSIB · expires 2026-11-20 (in 5 days)

DUE IN 30 DAYS (3):
  Summit Roofing Group — COI (CGL) · Harbor Mutual Insurance · expires 2026-12-01 (in 16 days)
  Summit Roofing Group — COI (CGL) · Harbor Mutual Insurance · expires 2026-12-01 (in 16 days)
  Cascadia Drywall Inc. — COI (CGL) · Harbor Mutual Insurance · expires 2026-12-10 (in 25 days)

DUE IN 60 DAYS (2):
  Pinewood Plumbing & Heating Ltd. — COI (CGL) · no issuer recorded · expires 2026-12-20 (in 35 days)
  Cascadia Drywall Inc. — WCB clearance · WorkSafeBC · expires 2027-01-05 (in 51 days)

DUE IN 90 DAYS (1):
  True North Scaffolding Co. — COI (CGL) · NorthPeak Insurance Co. · expires 2027-02-10 (in 87 days)

CURRENT — beyond 90 days, no action (2):

NO EXPIRY DATE — cannot be watched (1): see the errors below.

ERRORS — registry rows that cannot be chased (2):
  row 8 — expiry_missing: no expiry date recorded — this document cannot be watched at all until the date is typed in
  row 7 — missing_field: issuer is blank — this row cannot be chased until the issuer is recorded

WARNINGS — registry hygiene (1):
  row 10 — duplicate_document: this is the same document as row 9 (Summit Roofing Group — COI (CGL), Harbor Mutual Insurance, expires 2026-12-01) — merge the rows so it is chased once

INFO — worth knowing (1):
  row 9 — same_type_multiple_expiry: Summit Roofing Group — COI (CGL) has 2 different expiry dates on file (2026-12-01, 2027-03-01) — usually a renewal filed beside the old row; the chase uses the earliest, 2026-12-01

Verdict: ACTION — 1 document(s) expired, 2 registry error(s). Chase the expired documents today and fix the registry errors so nothing is unwatched.
sub-watch is a watching aid: it is not legal or insurance advice, and it sends nothing — the letters are drafts you send yourself. Every date in a report or letter comes from the registry — the tool never contacts an issuer or a board, and a document with nothing expired against it is current only as far as the expiry date typed in the registry.
(exit code: 1)
```

```
$ python3 src/sub_watch.py check examples/clean.csv --as-of 2026-11-15
sub-watch v0.1.0 — chase report for clean.csv · as of 2026-11-15 (4 document(s) in the registry)
Encoded chase bands and notes, checked 2026-11 — clearance-certificate cycles and verification duties change; verify them with the WSIB or your provincial WCB.

EXPIRED — chase today (0):
  none

DUE IN 7 DAYS (0):
  none

DUE IN 30 DAYS (0):
  none

DUE IN 60 DAYS (0):
  none

DUE IN 90 DAYS (0):
  none

CURRENT — beyond 90 days, no action (4):

Verdict: OK — nothing expired and no registry errors; 0 document(s) come due within 90 days of 2026-11-15.
sub-watch is a watching aid: it is not legal or insurance advice, and it sends nothing — the letters are drafts you send yourself. Every date in a report or letter comes from the registry — the tool never contacts an issuer or a board, and a document with nothing expired against it is current only as far as the expiry date typed in the registry.
(exit code: 0)
```

```
$ python3 src/sub_watch.py letters examples/sample.csv --as-of 2026-11-15 --out letters-out --from "Example Ridge Contracting Ltd."
sub-watch v0.1.0 — renewal-request letters from sample.csv · as of 2026-11-15 · expired or due within 90 days
Encoded chase bands and notes, checked 2026-11 — clearance-certificate cycles and verification duties change; verify them with the WSIB or your provincial WCB.

  wrote letters-out/brightline-electrical-ltd-renewal-request.txt — Brightline Electrical Ltd. (2 document(s)) · contact: office@brightline-example.ca
  wrote letters-out/cascadia-drywall-inc-renewal-request.txt — Cascadia Drywall Inc. (2 document(s)) · contact: admin@cascadia-example.ca
  wrote letters-out/pinewood-plumbing-heating-ltd-renewal-request.txt — Pinewood Plumbing & Heating Ltd. (1 document(s)) · contact: info@pinewood-example.ca
  wrote letters-out/summit-roofing-group-renewal-request.txt — Summit Roofing Group (1 document(s)) · contact: hello@summit-example.ca
  wrote letters-out/true-north-scaffolding-co-renewal-request.txt — True North Scaffolding Co. (1 document(s))

5 letter(s) written. Review before sending — the tool sends nothing.
sub-watch is a watching aid: it is not legal or insurance advice, and it sends nothing — the letters are drafts you send yourself.
(exit code: 0)
```

The Brightline letter, in full:

```
November 15, 2026

To: Brightline Electrical Ltd.
Subject: Renewal request — compliance documents on file

Hello,

We keep a current compliance file for every subcontractor we work with. Our registry shows the following document(s) for Brightline Electrical Ltd. have expired or will expire soon:

- COI (CGL) — issued by NorthPeak Insurance Co., document no. CGL-8841 — expired 2026-10-20 (26 days ago)
- WSIB clearance — issued by WSIB — expires 2026-11-20 (in 5 days)

Please send us the renewed document(s) as soon as they are issued — for anything already expired, please send the renewal right away so your file stays current with us.

Thank you,
Example Ridge Contracting Ltd.

(Drafted by sub-watch from the sender's registry on 2026-11-15 — every date above is the expiry date recorded there.)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

42 tests. The expected numbers are worked by hand from the example rows and stated in the test file: the sample's band counts (expired 1 · due_7 1 · due_30 3 · due_60 2 · due_90 1 · current 2 · unknown 1), its per-row day counts, its findings (2 errors, 1 warning, 1 info) and its five letters; every band edge pinned at the boundary and one day past it (−1/0/7/8/30/31/60/61/90/91 days); duplicate detection in both directions (case-insensitive duplicate fires, different expiry doesn't); letters at `--within` 90/7/0; and the error discipline — missing columns, malformed dates, a missing `--as-of` — all exit 2 with no traceback, JSON errors included.

## Who it's for

Small general contractors and property managers holding compliance paper for a roster of subs — especially in Canada, where the WSIB/WCB clearance cycle means some documents come due far more often than the annual insurance renewal, and where the primes' own paperwork burden flows downhill. It's also the mirror image: a subcontractor can run its *own* documents as the registry and hand the chase report to its primes before they ask.

Not for: verifying a certificate with an insurer or a board (the tool never contacts anyone), judging whether coverage limits or endorsements meet a contract (it reads dates, not documents), or replacing a contract's document requirements (which documents a sub must hold is set by your contracts and your insurer — the registry is your list).

## Known limits

- **The registry is the whole world.** A document never entered is never watched; a renewal that arrived but wasn't typed in still chases. The `same_type_multiple_expiry` note exists because the second failure is so common.
- **No board cycles are modelled.** WSIB/WCB clearances are issued on the boards' own validity cycles; the tool uses only the expiry date you typed. The notes are stamped "checked 2026-11" — verify current requirements with the board.
- **Dates only.** Adequacy of coverage, additional-insured endorsements, waiver of subrogation, certificate authenticity: none of that is visible to a date check, and the tool never claims otherwise.
- **A sub with no rows is invisible.** The tool cannot flag a subcontractor who should be in the registry but isn't — keep the registry next to your sub list and reconcile them yourself.

## Privacy

Everything is local. The tool reads the CSV you point it at and writes only the letter files you ask for, in the directory you name. No network code, no telemetry, no uploads — your sub roster and their insurers stay on your machine.

## Support

sub-watch is free and MIT-licensed. If it saves you one lapsed-certificate scare, consider sponsoring its maintenance via the GitHub Sponsors link in `.github/FUNDING.yml` — and if it misses a case your registry hits, open an issue with the (fictionalized) rows.

## Licence

MIT — see `LICENSE`.
