---
name: sub-watch
description: Watch a subcontractor compliance registry — certificates of insurance (COIs), WSIB clearance certificates (Ontario), WCB clearance letters (other provinces) and licences — as a 90/60/30/7-day chase report plus ready-to-send renewal-request letters, all from one local CSV of expiry dates the user typed. Use when a general contractor or property manager needs to know which subs' documents have lapsed or come due, or wants the renewal letters drafted. The tool reads dates only: it never contacts an insurer or a board, never verifies a certificate, and a report with nothing expired means no expiry date IN THE REGISTRY has passed — never that a sub is compliant. Not legal or insurance advice.
---

# sub-watch — agent skill

## Purpose

A general contractor must hold a current compliance document
for every subcontractor on every job. Collection is easy; the
failure mode is a certificate lapsing mid-project and nobody
noticing, because the registry is a spreadsheet nobody opens.
sub-watch is the watching half of that spreadsheet: one CSV
row per document (sub, document type, issuer, expiry), and
two outputs — a chase report banding every document expired /
due in 7 / 30 / 60 / 90 days with the registry's own mistakes
flagged, and one renewal-request letter per sub that needs
chasing. Pure Python standard library; local only; the only
files it writes are the letters, in the directory named.

**The honesty core of this tool:** every date, issuer and
document type in a report or letter comes from a registry row
the user typed. The tool never contacts an insurer, the WSIB,
a WCB or a broker; it never sees the documents themselves; it
cannot know about a document that was never entered, a
renewal that arrived but was not typed in, or a certificate
revoked early. A report with nothing expired means no expiry
date *in the registry* has passed — never present it as "the
sub is compliant", never as proof of adequate coverage, and
never as legal or insurance advice. WSIB/WCB clearance
documents run on the boards' own validity cycles, which the
tool does not model; the encoded notes are stamped "checked
2026-11" and carry a verify-with-the-board instruction.

## When to use / not use

Use when:
- A GC or property manager asks what has lapsed or comes due:
  run `check` with today's date (or the planning date) as
  `--as-of` and report the bands and findings.
- Renewal requests need drafting: run `letters` — one file
  per sub, expired documents always included, `--within` to
  narrow the due-soon window (default 90 days).
- An agent needs the band table or the honesty notes
  themselves: `rules` prints them, text or JSON.

Do NOT use when:
- The question is whether a certificate is genuine, current
  with the board, or sufficient for a contract — the tool
  reads typed dates, not documents, and contacts nobody.
  Verification happens with the issuer / the WSIB / the
  provincial WCB.
- The question is which documents a sub *must* hold — that
  is set by contracts, primes and insurers. The registry is
  the user's list; the tool watches it, it does not write it.
- Sending the letters — the tool drafts and stops. A human
  (or a separately authorized step) sends.
- Tax slips or construction holdbacks — different chores,
  different tools (`slip-watch`, `holdback-ledger`).

## Commands

```bash
# Chase report (exit 0 OK / 1 ACTION — expired or registry errors / 2 input)
python3 src/sub_watch.py check REGISTRY.csv --as-of 2026-11-15
python3 src/sub_watch.py check REGISTRY.csv --as-of 2026-11-15 --json

# Renewal-request letters (exit 0 / 2 input)
python3 src/sub_watch.py letters REGISTRY.csv --as-of 2026-11-15 --out letters-out
python3 src/sub_watch.py letters REGISTRY.csv --as-of 2026-11-15 --out letters-out --from "Your Company Ltd." --within 30
python3 src/sub_watch.py letters REGISTRY.csv --as-of 2026-11-15 --out letters-out --json

# Encoded bands, checks and notes with their bases (exit 0)
python3 src/sub_watch.py rules [--json]
```

Every command accepts `--json` and prints exactly one JSON
object. Input and usage errors — including argparse errors —
print `{"error": "..."}` and exit 2. The tool never reads
the machine clock: `--as-of` is required on `check` and
`letters`, so every date in the output traces to a date the
caller chose.

## Input format

One CSV, one row per document. Headers are matched after
stripping non-alphanumerics and lowercasing, so `Doc Type`,
`doc-type` and `doc_type` are the same column; `Subcontractor`,
`Issued By` and `Expiry Date` are accepted aliases. Extra
columns are ignored; blank lines are skipped; a row with
more values than the header is an input error (exit 2)
naming the row.

Required columns (an absent one is an exit-2 error naming
it): `sub`, `doc_type`, `issuer`, `expiry`. Optional:
`doc_number`, `contact_email`, `notes`.

Values: `expiry` is strict `YYYY-MM-DD` and must be a real
calendar date — a non-blank value in any other shape is an
exit-2 input error naming the row (the tool never guesses a
date). A *blank* expiry is not an input error: the row loads
and the `expiry_missing` check flags it, because a registry
with one undated document is exactly what the report must
surface. `doc_type` is free text, recorded as typed.

## The chase bands and the checks (state them when you report results)

Bands, by `days_until = (expiry − as_of).days`:

| Band | days_until | Meaning |
|------|-----------|---------|
| `expired` | < 0 | Already lapsed — chase today |
| `due_7` | 0–7 | Inside a week; expiry on the as-of date itself lands here ("expires today") |
| `due_30` | 8–30 | Inside a month |
| `due_60` | 31–60 | Inside two months |
| `due_90` | 61–90 | Inside a quarter |
| `current` | > 90 | No action; counted, not listed in the text bands |
| `unknown` | no expiry recorded | Cannot be watched; surfaces as an `expiry_missing` error |

| Rule | Severity | Basis |
|------|----------|-------|
| `missing_field` | error | A blank `sub`, `doc_type` or `issuer` — nobody to write to, no document to name, or no issuer to ask about. The row still appears in its band when it has an expiry. |
| `expiry_missing` | error | No expiry date — excluded from every band and from letters until the date is typed in. |
| `duplicate_document` | warning | Same sub + doc_type + issuer + expiry (case-insensitive) on 2+ rows; the second and later rows are flagged. Letters chase the document once regardless. |
| `same_type_multiple_expiry` | info | Same sub + doc_type with 2+ distinct expiry dates — usually a renewal filed beside the old row. The chase and the letters use the earliest date. |

Boundaries (pinned by tests): −1 day is `expired`; 0 and 7
are `due_7`; 8 and 30 are `due_30`; 31 and 60 are `due_60`;
61 and 90 are `due_90`; 91 is `current`. `check` exits 1
when any document is expired OR any error finding exists —
due-soon bands and warnings alone exit 0.

## Output JSON schema (`--json`)

`check`:
```json
{
  "tool": "sub-watch", "version": "0.1.0", "command": "check",
  "file": "registry.csv", "rows": 11, "as_of": "2026-11-15",
  "documents": [
    {"row": 1, "sub": "Brightline Electrical Ltd.",
     "doc_type": "COI (CGL)", "issuer": "NorthPeak Insurance Co.",
     "doc_number": "CGL-8841", "expiry": "2026-10-20",
     "days_until": -26, "band": "expired"}
  ],
  "bands": {"expired": 1, "due_7": 1, "due_30": 3, "due_60": 2,
            "due_90": 1, "current": 2, "unknown": 1},
  "findings": [
    {"row": 7, "sub": "Pinewood Plumbing & Heating Ltd.",
     "doc_type": "COI (CGL)", "field": "issuer",
     "rule": "missing_field", "severity": "error",
     "measured": "blank", "limit": "the issuer recorded in the registry",
     "message": "issuer is blank — this row cannot be chased until the issuer is recorded"}
  ],
  "summary": {"errors": 2, "warnings": 1, "info": 1,
              "by_rule": {"missing_field": 1}},
  "verdict": "ACTION",
  "note": null,
  "rules_note": "Encoded chase bands and notes, checked 2026-11 — ...",
  "honesty": "Every date in a report or letter comes from the registry — ...",
  "disclaimer": "sub-watch is a watching aid: it is not legal or insurance advice, ..."
}
```
`bands` counts every registry row exactly once and sums to
`rows`. `verdict` is `"ACTION"` exactly when the exit code
is 1. Findings are sorted by rule, then row.

`letters`: `letters` (one per sub: `sub`, `file`,
`contact_email` — the first one recorded on a chased row,
else null — and `documents`, the same document objects as
`check`, duplicates already collapsed), `subs_without_letters`
(subs whose rows exist but none could be chased — all
current, or undated), `within_days`, `from`, `out_dir`,
`note`. The letter files themselves are the deliverable; the
JSON is the manifest. No letters needed → `letters` is
empty, nothing is written, and the output directory is not
created.

`rules`: `bands` (each with `band`, `window`, `meaning`),
`checks` (each with `rule`, `severity`, `basis`), `notes`
(each with `note`, `basis`), `rules_checked` and the same
`rules_note` / `honesty` / `disclaimer`.

Errors (any command): `{"error": "..."}` with exit 2.

## Exit codes

- `check`: 0 = nothing expired and no registry errors
  (due-soon documents, warnings and info may be present),
  1 = at least one document expired or at least one error
  finding, 2 = the input could not be read or the command
  line was invalid.
- `letters`, `rules`: 0 = success, 2 = input/usage error.

## Limits & honesty rules the agent must respect

- **Never present an OK report as compliance.** "Nothing
  expired" is a statement about typed dates in one file.
  Coverage adequacy, endorsements, authenticity and board
  standing are all outside the tool — say so when reporting.
- **Never soften an expired document.** `expired` means the
  recorded expiry is before the as-of date. Report the sub,
  the document and the day count exactly as printed.
- **The bands are reporting buckets, not law.** No statute
  or insurer sets 90/60/30/7; contracts may demand sooner.
  State the bands as the tool's, with the rules stamp.
- **Clearance cycles are not modelled.** WSIB/WCB validity
  windows and verification duties are the boards' current
  rules — the notes were checked 2026-11 and direct the
  reader to the board. Do not state a cycle length as fact
  from this tool's output.
- **Letters are drafts.** The tool sends nothing; do not
  describe a written letter as sent, and note the sender
  placeholder when `--from` was not given.
- **No clock, no network.** `--as-of` is always explicit;
  do not pipe the registry to an external service to
  "verify" a date — the registry stays local.
