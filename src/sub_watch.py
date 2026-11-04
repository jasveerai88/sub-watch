#!/usr/bin/env python3
"""sub-watch — keep every subcontractor's compliance documents
current: a local registry of certificates of insurance (COIs),
WSIB clearance certificates (Ontario), WCB clearance letters
(other provinces) and licences, turned into a 90/60/30/7-day
chase report and ready-to-send renewal-request letters.

Pure Python standard library. Local only: no network, no
uploads, no accounts. The registry never leaves the machine.

A general contractor has to hold a current compliance document
for every subcontractor on every job. Collecting the documents
is easy; the failure mode is a certificate lapsing mid-project
and nobody noticing — the claim then lands on the GC's own
policy. The usual tool is a spreadsheet nobody remembers to
open: at 10 projects x 15 subs x several documents each, that
is hundreds of expiry dates. This tool is the watching half of
that spreadsheet: type each document once (sub, document
type, issuer, expiry), then ask for the chase report.

Commands:
  check REGISTRY.csv --as-of YYYY-MM-DD [--json]
  letters REGISTRY.csv --as-of YYYY-MM-DD --out DIR
        [--from NAME] [--within DAYS] [--json]
  rules [--json]

Input CSV columns (headers matched case-insensitively, spaces
and underscores ignored — "Doc Type", "doc_type" and "DocType"
are the same column; extra columns are tolerated and ignored):

  sub           required: the subcontractor's name
  doc_type      required: COI, WSIB clearance, WCB clearance,
                licence — free text, recorded as typed
  issuer        required: who issued the document (insurer,
                WSIB, WorkSafeBC, a municipality, ...)
  expiry        required: YYYY-MM-DD, the date the document
                stops being current
  doc_number    optional: policy / certificate number
  contact_email optional: where the renewal request goes
  notes         optional: free text, carried through untouched

The tool never reads the machine clock: every run is dated by
the explicit --as-of date, so a report is reproducible and a
test means the same thing tomorrow.

The chase bands (also printed by `rules`): expired (expiry
before the as-of date), due_7 (0-7 days), due_30 (8-30),
due_60 (31-60), due_90 (61-90), current (over 90 days).
Expiry on the as-of date itself is due_7 — "expires today" is
a chase item, not a current document.

The registry checks (every finding names the row, the rule,
the measured value and the limit): a blank sub, doc_type or
issuer is an error — the row cannot be chased; a blank expiry
is an error — the document cannot be watched at all; the same
document recorded twice (same sub, doc_type, issuer and
expiry) is a warning; the same sub and doc_type carrying two
different expiry dates is listed as information — it is
usually a renewal already filed, and the chase report uses
the earliest date.

HONESTY: every date, issuer and document type in a report or
letter comes from a registry row the user typed. The tool
never contacts an insurer, a board or a broker, never sees
the documents themselves, and cannot know about a document
that was never entered. A report with nothing expired means
no expiry date IN THE REGISTRY has passed — it does not mean
a sub's coverage is adequate, its limits meet a contract, or
its certificate is genuine. WSIB and WCB clearance documents
run on the boards' own validity cycles, which the tool does
not model — it uses only the expiry date typed in the
registry (checked 2026-11; verify current cycle and
verification requirements with the WSIB or your provincial
WCB). This tool is a watching aid: it is not legal or
insurance advice, and it sends nothing — the letters are
drafts the user sends themselves.

Exit codes: check — 0 = nothing expired and no registry
errors · 1 = at least one document expired, or at least one
registry error · 2 = an input error. letters / rules — 0 on
success · 2 = an input error. Errors print only the error —
"ERROR: ..." as text, or a single {"error": ...} object with
--json. Never a traceback.
"""
import argparse
import csv
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

__version__ = "0.1.0"
TOOL = "sub-watch"

RULES_CHECKED = "2026-11"
RULES_NOTE = ("Encoded chase bands and notes, checked "
              "2026-11 — clearance-certificate cycles and "
              "verification duties change; verify them with "
              "the WSIB or your provincial WCB.")
DISCLAIMER = ("sub-watch is a watching aid: it is not legal "
              "or insurance advice, and it sends nothing — "
              "the letters are drafts you send yourself.")
HONESTY = ("Every date in a report or letter comes from the "
           "registry — the tool never contacts an issuer or "
           "a board, and a document with nothing expired "
           "against it is current only as far as the expiry "
           "date typed in the registry.")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The chase bands, in urgency order. days_until is
# (expiry - as-of).days; a band's range is inclusive.
BANDS = [
    {"band": "expired", "window": "expiry before the as-of "
     "date (days_until < 0)",
     "meaning": "the document has already lapsed — chase "
     "today; until the renewal is on file, the sub's work is "
     "covered by your own policy, not theirs"},
    {"band": "due_7", "window": "0-7 days (expires today "
     "counts)",
     "meaning": "inside a week — the renewal should already "
     "be in motion; chase now"},
    {"band": "due_30", "window": "8-30 days",
     "meaning": "inside a month — send the renewal request"},
    {"band": "due_60", "window": "31-60 days",
     "meaning": "inside two months — the renewal request "
     "goes out with the next chase round"},
    {"band": "due_90", "window": "61-90 days",
     "meaning": "inside a quarter — on the watch list, no "
     "letter needed yet unless your contracts say sooner"},
    {"band": "current", "window": "more than 90 days",
     "meaning": "no action — listed only as a count"},
]

# Notes that travel with every report (printed by `rules`).
NOTES = [
    {"note": "bands_are_reporting_only",
     "basis": "The 90/60/30/7 bands are this tool's reporting "
     "buckets, matching the chase rhythm contractors "
     "describe. No statute, board or insurer sets them. If a "
     "contract or a prime requires a document sooner, it is "
     "sooner — the registry's expiry date is the only date "
     "the tool knows."},
    {"note": "clearance_cycles_not_modelled",
     "basis": "WSIB clearance certificates (Ontario) and WCB "
     "clearance letters (other provinces) are issued for "
     "short, fixed validity windows and are re-verified "
     "through a project; primes commonly must hold a current "
     "clearance before paying a sub. The tool models none of "
     "that — it uses only the expiry date typed in the "
     "registry. Checked 2026-11 — verify the current cycle "
     "and verification requirements with the WSIB or your "
     "provincial WCB."},
    {"note": "registry_is_the_only_source",
     "basis": "Every sub, document type, issuer and date in "
     "a report or letter comes from the registry rows the "
     "user typed. The tool never contacts an insurer, board "
     "or broker, and cannot know about a document that was "
     "never entered, a renewal that arrived but was not "
     "typed in, or a certificate that was revoked early."},
    {"note": "not_a_compliance_verdict",
     "basis": "A report with nothing expired means no expiry "
     "date in the registry has passed. It does not mean a "
     "sub's coverage is adequate, its limits meet your "
     "contract, its endorsements are right, or its "
     "certificate is genuine — the tool reads dates, not "
     "documents."},
]

# The registry checks (printed by `rules`). Severity "error"
# fails `check` (exit 1); "warning" and "info" are listed but
# never fail a run on their own.
CHECKS = [
    {"rule": "missing_field", "severity": "error",
     "basis": "A registry row with a blank sub, doc_type or "
     "issuer cannot be chased: there is nobody to write to, "
     "no document to name, or no issuer to ask about. The "
     "row is listed in the report with its band if it has an "
     "expiry, and flagged here."},
    {"rule": "expiry_missing", "severity": "error",
     "basis": "Watching is the whole job: a document with no "
     "expiry date in the registry cannot be watched at all. "
     "It is excluded from every band and from letters until "
     "the date is typed in."},
    {"rule": "duplicate_document", "severity": "warning",
     "basis": "The same document (same sub, doc_type, issuer "
     "and expiry, compared case-insensitively) recorded on "
     "two or more rows. Harmless on paper, but it doubles "
     "the row in counts and letters if left in — the second "
     "and later rows are flagged; merge them."},
    {"rule": "same_type_multiple_expiry", "severity": "info",
     "basis": "The same sub and doc_type carrying two "
     "different expiry dates. Usually the renewal has "
     "already been filed beside the old row — delete the "
     "old row. Until then the chase report and letters use "
     "the earliest date, so a renewal hiding in the registry "
     "never makes a live document look lapsed, and a lapsed "
     "one is never hidden by a future renewal for a "
     "different period."},
]


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# input loading + validation (every error names its row)
# --------------------------------------------------------------------------

def _fail_row(row_no, msg):
    raise ToolError(f"row {row_no}: {msg}")


def _norm_header(name):
    """'Doc Type', 'doc_type' and 'DocType' are one column."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


_HEADER_ALIASES = {
    "sub": "sub", "subcontractor": "sub",
    "subcontractorname": "sub", "company": "sub",
    "companyname": "sub", "trade": "sub", "vendor": "sub",
    "doctype": "doc_type", "documenttype": "doc_type",
    "document": "doc_type", "type": "doc_type",
    "certificatetype": "doc_type",
    "issuer": "issuer", "issuedby": "issuer",
    "insurancecompany": "issuer", "insurer": "issuer",
    "broker": "issuer",
    "expiry": "expiry", "expirydate": "expiry",
    "expiration": "expiry", "expirationdate": "expiry",
    "expires": "expiry", "validuntil": "expiry",
    "docnumber": "doc_number", "policynumber": "doc_number",
    "certificatenumber": "doc_number", "number": "doc_number",
    "contactemail": "contact_email", "email": "contact_email",
    "notes": "notes", "note": "notes",
}

# Columns the file itself must carry (a missing column is an
# input error, exit 2). The contact and notes columns may be
# absent entirely.
REQUIRED_COLUMNS = ("sub", "doc_type", "issuer", "expiry")


def _parse_date(raw, field, row_no):
    """YYYY-MM-DD text -> a date (None when blank). Any other
    non-blank shape is a clean input error naming the row —
    a mistyped date is not a finding, it is a file the tool
    cannot read honestly."""
    text = (raw or "").strip()
    if not text:
        return None
    if not DATE_RE.match(text):
        _fail_row(row_no, f"'{field}' must be a date "
                          f"YYYY-MM-DD (got {raw!r})")
    try:
        return date.fromisoformat(text)
    except ValueError:
        _fail_row(row_no, f"'{field}' is not a real calendar "
                          f"date (got {raw!r})")


def normalize_row(row, row_no):
    """Validate one raw row dict -> a clean document dict.
    Blank cells stay blank (the checks judge absence); a
    non-blank expiry that cannot be parsed is an input
    error."""
    def cell(name):
        return (row.get(name) or "").strip()

    return {
        "row": row_no,
        "sub": cell("sub"),
        "doc_type": cell("doc_type"),
        "issuer": cell("issuer"),
        "expiry": _parse_date(row.get("expiry"), "expiry",
                              row_no),
        "doc_number": cell("doc_number"),
        "contact_email": cell("contact_email"),
        "notes": cell("notes"),
    }


def load_registry(path):
    """Read a .csv registry file -> list of document dicts."""
    if not path.is_file():
        raise ToolError(f"file not found: {path}")
    if path.suffix.lower() != ".csv":
        raise ToolError(f"expected a .csv file (got {path.name})")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"could not read {path.name} "
                        f"({exc.__class__.__name__})")
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:  # pragma: no cover - 32-bit builds
        csv.field_size_limit(2 ** 31 - 1)
    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        if reader.fieldnames is None:
            raise ToolError(f"{path.name}: empty CSV — no header "
                            f"row")
        header_map = {}
        for raw_name in reader.fieldnames:
            canonical = _HEADER_ALIASES.get(_norm_header(raw_name))
            if canonical is not None:
                header_map[canonical] = True
        missing = [c for c in REQUIRED_COLUMNS
                   if c not in header_map]
        if missing:
            raise ToolError(
                f"{path.name}: CSV must have "
                f"{', '.join(repr(c) for c in missing)} "
                f"column(s) (headers found: "
                f"{', '.join(reader.fieldnames)})")
        entries = []
        for row in reader:
            row_no = len(entries) + 1
            if row.get(None):
                _fail_row(row_no, "more values than the header "
                                  "has columns")
            if all(v is None or (isinstance(v, str)
                                 and not v.strip())
                   for v in row.values()):
                continue  # a blank line is not a bad row
            mapped = {}
            for raw_name, value in row.items():
                canonical = _HEADER_ALIASES.get(
                    _norm_header(raw_name))
                if canonical is not None:
                    mapped[canonical] = value
            entries.append(normalize_row(mapped, row_no))
    except csv.Error as exc:
        raise ToolError(f"{path.name}: malformed CSV ({exc})")
    return entries


# --------------------------------------------------------------------------
# bands + the checks
# --------------------------------------------------------------------------

def band_for(days_until):
    """The chase band for a signed day count (None when the
    document has no expiry and cannot be watched)."""
    if days_until is None:
        return "unknown"
    if days_until < 0:
        return "expired"
    if days_until <= 7:
        return "due_7"
    if days_until <= 30:
        return "due_30"
    if days_until <= 60:
        return "due_60"
    if days_until <= 90:
        return "due_90"
    return "current"


ACTION_BANDS = ("expired", "due_7", "due_30", "due_60", "due_90")


def annotate(entries, as_of):
    """Attach days_until + band to every document."""
    for e in entries:
        e["days_until"] = (e["expiry"] - as_of).days \
            if e["expiry"] is not None else None
        e["band"] = band_for(e["days_until"])
    return entries


def _finding(entry, field, rule, severity, measured, limit,
             message):
    return {"row": entry["row"] if entry else None,
            "sub": entry["sub"] if entry else None,
            "doc_type": entry["doc_type"] if entry else None,
            "field": field, "rule": rule, "severity": severity,
            "measured": measured, "limit": limit,
            "message": message}


def run_checks(entries):
    """Every registry finding, in rule order then row order."""
    out = []

    def key_of(e):
        return (e["sub"].lower(), e["doc_type"].lower(),
                e["issuer"].lower(),
                e["expiry"].isoformat() if e["expiry"] else "")

    for e in entries:
        for field in ("sub", "doc_type", "issuer"):
            if not e[field]:
                out.append(_finding(
                    e, field, "missing_field", "error", "blank",
                    f"the {field} recorded in the registry",
                    f"{field} is blank — this row cannot be "
                    f"chased until the {field} is recorded"))
        if e["expiry"] is None:
            out.append(_finding(
                e, "expiry", "expiry_missing", "error",
                "blank", "an expiry date (YYYY-MM-DD) in the "
                "registry",
                "no expiry date recorded — this document "
                "cannot be watched at all until the date is "
                "typed in"))

    seen = {}
    for e in entries:
        if e["expiry"] is None or not e["sub"] \
                or not e["doc_type"]:
            continue
        key = key_of(e)
        if key in seen:
            first = seen[key]
            out.append(_finding(
                e, "expiry", "duplicate_document", "warning",
                f"same sub, doc_type, issuer and expiry as "
                f"row {first}",
                "each document recorded once",
                f"this is the same document as row {first} "
                f"({e['sub']} — {e['doc_type']}, "
                f"{e['issuer'] or 'no issuer'}, expires "
                f"{e['expiry'].isoformat()}) — merge the rows "
                f"so it is chased once"))
        else:
            seen[key] = e["row"]

    by_type = {}
    for e in entries:
        if e["expiry"] is None or not e["sub"] \
                or not e["doc_type"]:
            continue
        by_type.setdefault((e["sub"].lower(),
                            e["doc_type"].lower()),
                           []).append(e)
    for group in by_type.values():
        expiries = sorted({e["expiry"] for e in group})
        if len(expiries) > 1:
            first = group[0]
            dates = ", ".join(d.isoformat() for d in expiries)
            out.append(_finding(
                first, "expiry", "same_type_multiple_expiry",
                "info",
                f"expiry dates on file: {dates}",
                "one live expiry per sub and document type",
                f"{first['sub']} — {first['doc_type']} has "
                f"{len(expiries)} different expiry dates on "
                f"file ({dates}) — usually a renewal filed "
                f"beside the old row; the chase uses the "
                f"earliest, {expiries[0].isoformat()}"))
    out.sort(key=lambda f: (f["rule"], f["row"] or 0))
    return out


# --------------------------------------------------------------------------
# summaries
# --------------------------------------------------------------------------

def _check_summary(findings):
    by_rule = {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    return {
        "errors": sum(1 for f in findings
                      if f["severity"] == "error"),
        "warnings": sum(1 for f in findings
                        if f["severity"] == "warning"),
        "info": sum(1 for f in findings
                    if f["severity"] == "info"),
        "by_rule": dict(sorted(by_rule.items())),
    }


def _band_counts(entries):
    counts = {b["band"]: 0 for b in BANDS}
    counts["unknown"] = 0
    for e in entries:
        counts[e["band"]] += 1
    return counts


def _verdict(entries, findings):
    expired = any(e["band"] == "expired" for e in entries)
    errors = any(f["severity"] == "error" for f in findings)
    return "ACTION" if (expired or errors) else "OK"


# --------------------------------------------------------------------------
# check report
# --------------------------------------------------------------------------

def _doc_json(e):
    return {
        "row": e["row"], "sub": e["sub"] or None,
        "doc_type": e["doc_type"] or None,
        "issuer": e["issuer"] or None,
        "doc_number": e["doc_number"] or None,
        "expiry": e["expiry"].isoformat()
        if e["expiry"] else None,
        "days_until": e["days_until"], "band": e["band"],
    }


def check_as_json(source_name, entries, findings, as_of, note):
    return {
        "tool": TOOL, "version": __version__, "command": "check",
        "file": source_name, "rows": len(entries),
        "as_of": as_of.isoformat(),
        "documents": [_doc_json(e) for e in entries],
        "bands": _band_counts(entries),
        "findings": findings,
        "summary": _check_summary(findings),
        "verdict": _verdict(entries, findings),
        "note": note,
        "rules_note": RULES_NOTE,
        "honesty": HONESTY,
        "disclaimer": DISCLAIMER,
    }


def _when(e):
    """The human phrase for a document's timing."""
    d = e["days_until"]
    if d is None:
        return "no expiry date recorded"
    if d < 0:
        return (f"expired {e['expiry'].isoformat()} "
                f"({-d} day{'s' if -d != 1 else ''} ago)")
    if d == 0:
        return f"expires today, {e['expiry'].isoformat()}"
    return (f"expires {e['expiry'].isoformat()} "
            f"(in {d} day{'s' if d != 1 else ''})")


def _doc_line(e):
    who = e["sub"] or "(no sub recorded)"
    what = e["doc_type"] or "(no document type)"
    issuer = e["issuer"] or "no issuer recorded"
    return f"  {who} — {what} · {issuer} · {_when(e)}"


_BAND_TITLES = {
    "expired": "EXPIRED — chase today",
    "due_7": "DUE IN 7 DAYS",
    "due_30": "DUE IN 30 DAYS",
    "due_60": "DUE IN 60 DAYS",
    "due_90": "DUE IN 90 DAYS",
}


def render_check_text(source_name, entries, findings, as_of,
                      note):
    counts = _band_counts(entries)
    lines = [
        f"sub-watch v{__version__} — chase report for "
        f"{source_name} · as of {as_of.isoformat()} "
        f"({len(entries)} document(s) in the registry)",
        RULES_NOTE,
        "",
    ]
    if note:
        lines.append(note)
        lines.append("")
    for band in ACTION_BANDS:
        group = [e for e in entries if e["band"] == band]
        group.sort(key=lambda e: (e["days_until"],
                                  e["sub"].lower(),
                                  e["doc_type"].lower()))
        lines.append(f"{_BAND_TITLES[band]} ({len(group)}):")
        if group:
            for e in group:
                lines.append(_doc_line(e))
        else:
            lines.append("  none")
        lines.append("")
    lines.append(f"CURRENT — beyond 90 days, no action "
                 f"({counts['current']}):")
    lines.append("")
    if counts["unknown"]:
        lines.append(f"NO EXPIRY DATE — cannot be watched "
                     f"({counts['unknown']}): see the errors "
                     f"below.")
        lines.append("")
    for severity, title in (("error", "ERRORS — registry rows "
                             "that cannot be chased"),
                            ("warning", "WARNINGS — registry "
                             "hygiene"),
                            ("info", "INFO — worth knowing")):
        group = [f for f in findings
                 if f["severity"] == severity]
        if group:
            lines.append(f"{title} ({len(group)}):")
            for f in group:
                where = (f"row {f['row']}"
                         if f["row"] is not None else "file")
                lines.append(f"  {where} — {f['rule']}: "
                             f"{f['message']}")
            lines.append("")
    verdict = _verdict(entries, findings)
    summary = _check_summary(findings)
    if verdict == "ACTION":
        lines.append(
            f"Verdict: ACTION — {counts['expired']} document"
            f"(s) expired, {summary['errors']} registry "
            f"error(s). Chase the expired documents today and "
            f"fix the registry errors so nothing is unwatched.")
    else:
        due = sum(counts[b] for b in ACTION_BANDS[1:])
        lines.append(
            f"Verdict: OK — nothing expired and no registry "
            f"errors; {due} document(s) come due within 90 "
            f"days of {as_of.isoformat()}.")
    lines.append(DISCLAIMER + " " + HONESTY)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# letters
# --------------------------------------------------------------------------

def _slug(name):
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return slug.strip("-") or "subcontractor"


def chaseable(entries, within):
    """Documents a letter can chase: dated, named, and expired
    or due within `within` days. Exact duplicates (same sub,
    doc_type, issuer, expiry) are chased once."""
    out, seen = [], set()
    for e in entries:
        if e["expiry"] is None or not e["sub"] \
                or not e["doc_type"]:
            continue
        if e["days_until"] > within:
            continue
        key = (e["sub"].lower(), e["doc_type"].lower(),
               e["issuer"].lower(), e["expiry"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _letter_body(sub, docs, as_of, from_name):
    docs = sorted(docs, key=lambda e: (e["expiry"],
                                       e["doc_type"].lower()))
    expired = [e for e in docs if e["days_until"] < 0]
    lines = [
        f"{as_of.strftime('%B')} {as_of.day}, {as_of.year}",
        "",
        f"To: {sub}",
        f"Subject: Renewal request — compliance documents on "
        f"file",
        "",
        "Hello,",
        "",
        f"We keep a current compliance file for every "
        f"subcontractor we work with. Our registry shows the "
        f"following document(s) for {sub} "
        + ("have expired or will expire soon:"
           if expired else "will expire soon:"),
        "",
    ]
    for e in docs:
        issuer = e["issuer"] or "issuer not recorded"
        number = f", document no. {e['doc_number']}" \
            if e["doc_number"] else ""
        lines.append(f"- {e['doc_type']} — issued by "
                     f"{issuer}{number} — {_when(e)}")
    lines += [
        "",
        "Please send us the renewed document(s) as soon as "
        "they are issued — for anything already expired, "
        "please send the renewal right away so your file "
        "stays current with us.",
        "",
        "Thank you,",
        from_name or "[Your name / company name]",
        "",
        "(Drafted by sub-watch from the sender's registry on "
        f"{as_of.isoformat()} — every date above is the "
        "expiry date recorded there.)",
    ]
    return "\n".join(lines) + "\n"


def build_letters(entries, as_of, within, from_name):
    """(letters, skipped) — one letter per sub with at least
    one chaseable document; skipped counts the subs whose
    documents exist but none can be chased in this run."""
    docs = chaseable(entries, within)
    by_sub = {}
    for e in docs:
        by_sub.setdefault(e["sub"], []).append(e)
    letters = []
    used = set()
    for sub in sorted(by_sub, key=str.lower):
        slug = _slug(sub)
        name, n = slug, 2
        while name in used:
            name = f"{slug}-{n}"
            n += 1
        used.add(name)
        group = by_sub[sub]
        letters.append({
            "sub": sub,
            "file": f"{name}-renewal-request.txt",
            "contact_email": next(
                (e["contact_email"] for e in group
                 if e["contact_email"]), None),
            "documents": [_doc_json(e) for e in
                          sorted(group,
                                 key=lambda e: e["expiry"])],
            "body": _letter_body(sub, group, as_of, from_name),
        })
    all_subs = {e["sub"] for e in entries if e["sub"]}
    skipped = sorted(all_subs - set(by_sub), key=str.lower)
    return letters, skipped


def letters_as_json(source_name, letters, skipped, out_dir,
                    as_of, within, from_name):
    return {
        "tool": TOOL, "version": __version__,
        "command": "letters",
        "file": source_name, "as_of": as_of.isoformat(),
        "within_days": within, "from": from_name,
        "out_dir": str(out_dir),
        "letters": [{k: v for k, v in letter.items()
                     if k != "body"} for letter in letters],
        "subs_without_letters": skipped,
        "note": ("Letters state only what the registry "
                 "holds: sub, document type, issuer and the "
                 "recorded expiry. Review before sending — "
                 "the tool sends nothing."),
        "rules_note": RULES_NOTE,
        "disclaimer": DISCLAIMER,
    }


def render_letters_text(source_name, letters, skipped, out_dir,
                        as_of, within):
    lines = [
        f"sub-watch v{__version__} — renewal-request letters "
        f"from {source_name} · as of {as_of.isoformat()} · "
        f"expired or due within {within} days",
        RULES_NOTE,
        "",
    ]
    if letters:
        for letter in letters:
            email = (f" · contact: {letter['contact_email']}"
                     if letter["contact_email"] else "")
            lines.append(
                f"  wrote {out_dir / letter['file']} — "
                f"{letter['sub']} "
                f"({len(letter['documents'])} document(s))"
                f"{email}")
        lines.append("")
        lines.append(f"{len(letters)} letter(s) written. "
                     f"Review before sending — the tool sends "
                     f"nothing.")
    else:
        lines.append("No letters written — no document in the "
                     "registry is expired or due within "
                     f"{within} days of {as_of.isoformat()}.")
    if skipped:
        lines.append(f"Not written for "
                     f"{len(skipped)} sub(s) with nothing to "
                     f"chase in this run: "
                     f"{', '.join(skipped)}.")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# rules report
# --------------------------------------------------------------------------

def rules_as_json():
    return {
        "tool": TOOL, "version": __version__, "command": "rules",
        "rules_checked": RULES_CHECKED,
        "rules_note": RULES_NOTE,
        "bands": BANDS,
        "checks": CHECKS,
        "notes": NOTES,
        "honesty": HONESTY,
        "disclaimer": DISCLAIMER,
    }


def render_rules_text():
    lines = [
        f"sub-watch v{__version__} — the encoded chase bands, "
        f"registry checks and notes",
        RULES_NOTE,
        "",
        "THE CHASE BANDS (days from the --as-of date to the "
        "recorded expiry):",
    ]
    for b in BANDS:
        lines.append(f"  {b['band']} — {b['window']}: "
                     f"{b['meaning']}")
    lines.append("")
    lines.append("THE REGISTRY CHECKS:")
    for c in CHECKS:
        lines.append(f"  {c['rule']} ({c['severity']}) — "
                     f"{c['basis']}")
    lines.append("")
    lines.append("NOTES:")
    for n in NOTES:
        lines.append(f"  {n['note']} — {n['basis']}")
    lines.append("")
    lines.append(DISCLAIMER + " " + HONESTY)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in
    --json mode ({"error": ...} on stdout, same exit code 2)
    — an agent driving this tool with --json never gets plain
    text or a traceback. The flag lives on the class so
    subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _as_of_value(text):
    if not DATE_RE.match(text or ""):
        raise ToolError(f"--as-of must be a date YYYY-MM-DD "
                        f"(got {text!r})")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ToolError(f"--as-of is not a real calendar date "
                        f"(got {text!r})")


def _within_value(text):
    try:
        value = int(text)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"--within must be a whole number of days "
            f"(got {text!r})")
    if value < 0:
        raise argparse.ArgumentTypeError(
            f"--within must be 0 or more (got {text!r})")
    return value


def _scope_note(entries):
    if not entries:
        return ("Note: the file has a header row but no data "
                "rows — nothing was watched, so this OK is "
                "vacuous.")
    return None


def cmd_check(a):
    path = Path(a.csv)
    entries = annotate(load_registry(path), a.as_of)
    findings = run_checks(entries)
    note = _scope_note(entries)
    if a.json:
        print(json.dumps(check_as_json(path.name, entries,
                                       findings, a.as_of, note),
                         indent=2))
    else:
        print(render_check_text(path.name, entries, findings,
                                a.as_of, note))
    return 1 if _verdict(entries, findings) == "ACTION" else 0


def cmd_letters(a):
    path = Path(a.csv)
    entries = annotate(load_registry(path), a.as_of)
    letters, skipped = build_letters(entries, a.as_of,
                                     a.within, a.from_name)
    out_dir = Path(a.out)
    if letters:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            for letter in letters:
                (out_dir / letter["file"]).write_text(
                    letter["body"], encoding="utf-8")
        except OSError as exc:
            raise ToolError(f"could not write letters to "
                            f"{out_dir} ({exc.__class__.__name__})")
    if a.json:
        print(json.dumps(letters_as_json(
            path.name, letters, skipped, out_dir, a.as_of,
            a.within, a.from_name), indent=2))
    else:
        print(render_letters_text(path.name, letters, skipped,
                                  out_dir, a.as_of, a.within))
    return 0


def cmd_rules(a):
    if a.json:
        print(json.dumps(rules_as_json(), indent=2))
    else:
        print(render_rules_text())
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="Watch a subcontractor compliance "
                    "registry (COIs, WSIB/WCB clearances, "
                    "licences): a 90/60/30/7-day chase report "
                    "and renewal-request letters (stdlib only, "
                    "local only). A watching aid — not legal "
                    "or insurance advice.")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_check = sub.add_parser(
        "check", help="chase report: every registry document "
                      "banded by days to expiry")
    p_check.add_argument("csv", help="registry file (.csv)")
    p_check.add_argument("--as-of", type=_as_of_value,
                         required=True, metavar="YYYY-MM-DD",
                         help="date the report is dated "
                              "(required — the tool never reads "
                              "the clock itself)")
    p_check.add_argument("--json", action="store_true",
                         help="print one JSON object instead of "
                              "the text report")
    p_check.set_defaults(func=cmd_check)

    p_letters = sub.add_parser(
        "letters", help="write one renewal-request letter per "
                        "sub with documents expired or due "
                        "within the window")
    p_letters.add_argument("csv", help="registry file (.csv)")
    p_letters.add_argument("--as-of", type=_as_of_value,
                           required=True, metavar="YYYY-MM-DD",
                           help="date the letters are dated "
                                "(required — the tool never "
                                "reads the clock itself)")
    p_letters.add_argument("--out", required=True,
                           help="directory the letter files "
                                "are written to (created if "
                                "needed)")
    p_letters.add_argument("--from", dest="from_name",
                           default=None,
                           help="sender name signed on the "
                                "letters (default: a bracketed "
                                "placeholder to fill in)")
    p_letters.add_argument("--within", type=_within_value,
                           default=90,
                           help="chase documents due within "
                                "this many days (default 90; "
                                "expired documents are always "
                                "included)")
    p_letters.add_argument("--json", action="store_true",
                           help="print one JSON object instead "
                                "of the text report")
    p_letters.set_defaults(func=cmd_letters)

    p_rules = sub.add_parser(
        "rules", help="print the encoded chase bands, "
                      "registry checks and notes")
    p_rules.add_argument("--json", action="store_true",
                         help="print one JSON object instead of "
                              "text")
    p_rules.set_defaults(func=cmd_rules)

    def fail(msg, json_mode):
        if json_mode:
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    # parse_args sits inside the try: the --as-of type
    # callable raises ToolError for a bad date, and argparse
    # only converts its own error types — an unwrapped
    # ToolError here would escape as a traceback.
    try:
        a = ap.parse_args(argv)
    except ToolError as exc:
        return fail(str(exc), _JsonAwareParser.json_mode)
    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc), getattr(a, "json", False))


if __name__ == "__main__":
    sys.exit(main())
