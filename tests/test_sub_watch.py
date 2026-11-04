#!/usr/bin/env python3
"""Tests for sub-watch. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

The expected numbers are worked BY HAND from the registry
rows and the band table in src/sub_watch.py (and stated in
the README), not copied out of the tool's own output. All
runs are dated --as-of 2026-11-15; day counts below are
(expiry - 2026-11-15).days, counted on a calendar:

  Sample (examples/sample.csv, 11 rows):
    row 1  Brightline COI, expiry 2026-10-20 -> -26 expired
    row 2  Brightline WSIB, 2026-11-20 -> +5 due_7
    row 3  Cascadia COI, 2026-12-10 -> +25 due_30
    row 4  Cascadia WCB, 2027-01-05 -> +51 due_60
    row 5  True North COI, 2027-02-10 -> +87 due_90
    row 6  True North licence, 2027-06-30 -> +227 current
    row 7  Pinewood COI, 2026-12-20 -> +35 due_60, and the
           issuer cell is blank -> missing_field error
    row 8  Pinewood WSIB, expiry blank -> expiry_missing
           error, band unknown
    row 9  Summit COI, 2026-12-01 -> +16 due_30
    row 10 Summit COI, identical to row 9 -> duplicate
    row 11 Summit COI, 2027-03-01 -> +106 current; rows
           9-11 give Summit's COI two distinct expiries ->
           same_type_multiple_expiry info
    bands: expired 1, due_7 1, due_30 3, due_60 2, due_90 1,
           current 2, unknown 1 (sums to the 11 rows)
    findings: 2 errors, 1 warning, 1 info; verdict ACTION,
    check exit 1
    letters (default --within 90): 5 letters — Brightline
    (rows 1-2), Cascadia (3-4), True North (5 only; row 6 is
    current), Pinewood (7 only; row 8 has no date), Summit
    (row 9 once — row 10 is the same document, chased once;
    row 11 is current)

  Clean (examples/clean.csv, 4 rows): expiries 2027-05-01
  (+167), 2027-02-15 (+92), 2027-08-19, 2027-04-30 — all
  current (the +92 row sits just past the 90-day band edge),
  no findings, verdict OK, check exit 0, no letters.

Band edges are pinned exactly against as-of 2026-11-15:
2026-11-14 (-1) expired; 2026-11-15 (0) and 2026-11-22 (7)
due_7; 2026-11-23 (8) and 2026-12-15 (30) due_30;
2026-12-16 (31) and 2027-01-14 (60) due_60; 2027-01-15 (61)
and 2027-02-13 (90) due_90; 2027-02-14 (91) current.
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "sub_watch.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import sub_watch as sw  # noqa: E402

AS_OF = "2026-11-15"
HEADER = "sub,doc_type,issuer,expiry,doc_number," \
         "contact_email,notes\n"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SRC), *args],
        capture_output=True, text=True)


def run_json(*args):
    proc = run_cli(*args, "--json")
    return proc, json.loads(proc.stdout)


def write_registry(tmp, body, name="registry.csv"):
    path = Path(tmp) / name
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def one_row(expiry, sub="Solo Trade Ltd.", doc_type="COI",
            issuer="NorthPeak Insurance Co."):
    return f"{sub},{doc_type},{issuer},{expiry},,,\n"


class SampleCheckTests(unittest.TestCase):
    def setUp(self):
        self.proc, self.data = run_json(
            "check", str(EXAMPLES / "sample.csv"),
            "--as-of", AS_OF)

    def test_check_exits_1(self):
        self.assertEqual(self.proc.returncode, 1)

    def test_band_counts(self):
        self.assertEqual(self.data["bands"], {
            "expired": 1, "due_7": 1, "due_30": 3, "due_60": 2,
            "due_90": 1, "current": 2, "unknown": 1})

    def test_bands_sum_to_rows(self):
        self.assertEqual(sum(self.data["bands"].values()),
                         self.data["rows"])
        self.assertEqual(self.data["rows"], 11)

    def test_days_until_are_the_hand_counts(self):
        days = {d["row"]: d["days_until"]
                for d in self.data["documents"]}
        self.assertEqual(days, {1: -26, 2: 5, 3: 25, 4: 51,
                                5: 87, 6: 227, 7: 35, 8: None,
                                9: 16, 10: 16, 11: 106})

    def test_finding_counts_by_rule(self):
        self.assertEqual(self.data["summary"]["by_rule"], {
            "missing_field": 1, "expiry_missing": 1,
            "duplicate_document": 1,
            "same_type_multiple_expiry": 1})
        self.assertEqual(self.data["summary"]["errors"], 2)
        self.assertEqual(self.data["summary"]["warnings"], 1)
        self.assertEqual(self.data["summary"]["info"], 1)

    def test_summary_recounts_against_findings(self):
        findings = self.data["findings"]
        for severity in ("error", "warning", "info"):
            key = {"error": "errors", "warning": "warnings",
                   "info": "info"}[severity]
            self.assertEqual(
                self.data["summary"][key],
                sum(1 for f in findings
                    if f["severity"] == severity))

    def test_findings_are_where_expected(self):
        by_rule = {}
        for f in self.data["findings"]:
            by_rule.setdefault(f["rule"], []).append(f["row"])
        self.assertEqual(by_rule["missing_field"], [7])
        self.assertEqual(by_rule["expiry_missing"], [8])
        self.assertEqual(by_rule["duplicate_document"], [10])
        self.assertEqual(by_rule["same_type_multiple_expiry"],
                         [9])

    def test_verdict_action(self):
        self.assertEqual(self.data["verdict"], "ACTION")

    def test_text_run_names_the_expired_document(self):
        proc = run_cli("check", str(EXAMPLES / "sample.csv"),
                       "--as-of", AS_OF)
        self.assertIn("Brightline Electrical Ltd.", proc.stdout)
        self.assertIn("expired 2026-10-20 (26 days ago)",
                      proc.stdout)
        self.assertIn("Verdict: ACTION", proc.stdout)


class CleanCheckTests(unittest.TestCase):
    def setUp(self):
        self.proc, self.data = run_json(
            "check", str(EXAMPLES / "clean.csv"),
            "--as-of", AS_OF)

    def test_clean_passes(self):
        self.assertEqual(self.proc.returncode, 0)
        self.assertEqual(self.data["findings"], [])
        self.assertEqual(self.data["verdict"], "OK")
        self.assertEqual(self.data["bands"]["current"], 4)

    def test_clean_letters_write_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "letters"
            proc = run_cli("letters",
                           str(EXAMPLES / "clean.csv"),
                           "--as-of", AS_OF, "--out", str(out))
            self.assertEqual(proc.returncode, 0)
            self.assertIn("No letters written", proc.stdout)
            self.assertFalse(out.exists())


class BandBoundaryTests(unittest.TestCase):
    CASES = [
        ("2026-11-14", -1, "expired"), ("2026-11-15", 0, "due_7"),
        ("2026-11-22", 7, "due_7"), ("2026-11-23", 8, "due_30"),
        ("2026-12-15", 30, "due_30"), ("2026-12-16", 31, "due_60"),
        ("2027-01-14", 60, "due_60"), ("2027-01-15", 61, "due_90"),
        ("2027-02-13", 90, "due_90"), ("2027-02-14", 91, "current"),
    ]

    def test_every_band_edge(self):
        for expiry, days, band in self.CASES:
            with self.subTest(expiry=expiry):
                self.assertEqual(sw.band_for(days), band)
                with tempfile.TemporaryDirectory() as tmp:
                    path = write_registry(tmp, one_row(expiry))
                    _, data = run_json("check", str(path),
                                       "--as-of", AS_OF)
                    doc = data["documents"][0]
                    self.assertEqual(doc["days_until"], days)
                    self.assertEqual(doc["band"], band)

    def test_expired_alone_fails_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(tmp, one_row("2026-11-14"))
            proc = run_cli("check", str(path), "--as-of", AS_OF)
            self.assertEqual(proc.returncode, 1)

    def test_due_soon_alone_passes_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(tmp, one_row("2026-11-22"))
            proc = run_cli("check", str(path), "--as-of", AS_OF)
            self.assertEqual(proc.returncode, 0)

    def test_registry_error_alone_fails_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(tmp, one_row(""))
            proc, data = run_json("check", str(path),
                                  "--as-of", AS_OF)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(data["summary"]["errors"], 1)


class RegistryCheckTests(unittest.TestCase):
    def check(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(tmp, body)
            return run_json("check", str(path), "--as-of", AS_OF)

    def test_duplicate_is_case_insensitive(self):
        _, data = self.check(
            one_row("2027-01-31") +
            "solo trade ltd.,coi,NORTHPEAK INSURANCE CO.,"
            "2027-01-31,,,\n")
        self.assertEqual(data["summary"]["by_rule"],
                         {"duplicate_document": 1})

    def test_different_expiry_is_not_a_duplicate(self):
        _, data = self.check(one_row("2027-01-31")
                             + one_row("2027-07-31"))
        self.assertNotIn("duplicate_document",
                         data["summary"]["by_rule"])
        self.assertEqual(
            data["summary"]["by_rule"]
            ["same_type_multiple_expiry"], 1)

    def test_same_expiry_same_type_no_info(self):
        _, data = self.check(one_row("2027-01-31"))
        self.assertEqual(data["findings"], [])

    def test_blank_sub_doc_type_issuer_each_flagged(self):
        _, data = self.check(
            ",COI,NorthPeak Insurance Co.,2027-01-31,,,\n"
            "Solo Trade Ltd.,,NorthPeak Insurance Co.,"
            "2027-01-31,,,\n"
            "Solo Trade Ltd.,COI,,2027-01-31,,,\n")
        fields = sorted(f["field"] for f in data["findings"]
                        if f["rule"] == "missing_field")
        self.assertEqual(fields, ["doc_type", "issuer", "sub"])
        self.assertEqual(data["summary"]["errors"], 3)


class LetterTests(unittest.TestCase):
    def letters(self, tmp, *extra, source="sample.csv"):
        out = Path(tmp) / "out"
        proc, data = run_json(
            "letters", str(EXAMPLES / source), "--as-of", AS_OF,
            "--out", str(out), *extra)
        return proc, data, out

    def test_sample_writes_five_letters(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, data, out = self.letters(
                tmp, "--from", "Example Ridge Contracting Ltd.")
            self.assertEqual(proc.returncode, 0)
            files = sorted(p.name for p in out.iterdir())
            self.assertEqual(files, [
                "brightline-electrical-ltd-renewal-request.txt",
                "cascadia-drywall-inc-renewal-request.txt",
                "pinewood-plumbing-heating-ltd-renewal-request"
                ".txt",
                "summit-roofing-group-renewal-request.txt",
                "true-north-scaffolding-co-renewal-request.txt",
            ])
            self.assertEqual(len(data["letters"]), 5)
            self.assertEqual(data["subs_without_letters"], [])

    def test_letter_document_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, data, _ = self.letters(tmp)
            counts = {letter["sub"]: len(letter["documents"])
                      for letter in data["letters"]}
            self.assertEqual(counts, {
                "Brightline Electrical Ltd.": 2,
                "Cascadia Drywall Inc.": 2,
                "True North Scaffolding Co.": 1,
                "Pinewood Plumbing & Heating Ltd.": 1,
                "Summit Roofing Group": 1})

    def test_brightline_letter_states_both_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, out = self.letters(
                tmp, "--from", "Example Ridge Contracting Ltd.")
            body = (out / "brightline-electrical-ltd-renewal-"
                    "request.txt").read_text(encoding="utf-8")
            self.assertIn("expired 2026-10-20 (26 days ago)",
                          body)
            self.assertIn("expires 2026-11-20 (in 5 days)", body)
            self.assertIn("Example Ridge Contracting Ltd.", body)
            self.assertIn("CGL-8841", body)

    def test_letter_without_from_uses_a_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, out = self.letters(tmp)
            body = (out / "summit-roofing-group-renewal-"
                    "request.txt").read_text(encoding="utf-8")
            self.assertIn("[Your name / company name]", body)

    def test_pinewood_letter_names_the_missing_issuer(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, out = self.letters(tmp)
            body = (out / "pinewood-plumbing-heating-ltd-"
                    "renewal-request.txt").read_text(
                        encoding="utf-8")
            self.assertIn("issuer not recorded", body)
            self.assertNotIn("WSIB", body)

    def test_summit_letter_chases_the_duplicate_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, out = self.letters(tmp)
            body = (out / "summit-roofing-group-renewal-"
                    "request.txt").read_text(encoding="utf-8")
            self.assertEqual(body.count("2026-12-01"), 1)
            self.assertNotIn("2027-03-01", body)

    def test_within_7_writes_only_brightline(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, data, out = self.letters(tmp, "--within", "7")
            self.assertEqual([letter["sub"]
                              for letter in data["letters"]],
                             ["Brightline Electrical Ltd."])
            self.assertEqual(len(list(out.iterdir())), 1)

    def test_within_0_chases_only_expired(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, data, _ = self.letters(tmp, "--within", "0")
            docs = data["letters"][0]["documents"]
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0]["band"], "expired")


class InputErrorTests(unittest.TestCase):
    def assert_clean_error(self, proc, code=2):
        self.assertEqual(proc.returncode, code)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_missing_file(self):
        proc, data = run_json("check", "no-such-file.csv",
                              "--as-of", AS_OF)
        self.assert_clean_error(proc)
        self.assertIn("error", data)

    def test_wrong_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.txt"
            path.write_text(HEADER, encoding="utf-8")
            proc = run_cli("check", str(path), "--as-of", AS_OF)
            self.assert_clean_error(proc)
            self.assertIn("ERROR:", proc.stdout)

    def test_missing_required_column_names_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.csv"
            path.write_text("sub,doc_type,issuer\n"
                            "Solo,COI,NorthPeak\n",
                            encoding="utf-8")
            proc = run_cli("check", str(path), "--as-of", AS_OF)
            self.assert_clean_error(proc)
            self.assertIn("'expiry'", proc.stdout)

    def test_malformed_expiry_names_the_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(
                tmp, one_row("2027-01-31") + one_row("15/03/2027"))
            proc = run_cli("check", str(path), "--as-of", AS_OF)
            self.assert_clean_error(proc)
            self.assertIn("row 2", proc.stdout)

    def test_impossible_date_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(tmp, one_row("2027-02-30"))
            proc = run_cli("check", str(path), "--as-of", AS_OF)
            self.assert_clean_error(proc)
            self.assertIn("not a real calendar date",
                          proc.stdout)

    def test_bad_as_of(self):
        proc, data = run_json("check",
                              str(EXAMPLES / "clean.csv"),
                              "--as-of", "Nov 15 2026")
        self.assert_clean_error(proc)
        self.assertIn("error", data)

    def test_missing_as_of_is_a_clean_usage_error(self):
        proc = run_cli("check", str(EXAMPLES / "clean.csv"),
                       "--json")
        self.assert_clean_error(proc)
        self.assertIn("error", json.loads(proc.stdout))

    def test_bad_within(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("letters", str(EXAMPLES / "clean.csv"),
                           "--as-of", AS_OF, "--out", tmp,
                           "--within", "-3", "--json")
            self.assert_clean_error(proc)
            self.assertIn("error", json.loads(proc.stdout))

    def test_extra_values_in_a_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.csv"
            path.write_text("sub,doc_type,issuer,expiry\n"
                            "Solo,COI,NorthPeak,2027-01-31,EXTRA\n",
                            encoding="utf-8")
            proc = run_cli("check", str(path), "--as-of", AS_OF)
            self.assert_clean_error(proc)
            self.assertIn("row 1", proc.stdout)

    def test_header_aliases_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.csv"
            path.write_text(
                "Subcontractor,Document Type,Issued By,"
                "Expiry Date\nSolo Trade Ltd.,COI,"
                "NorthPeak Insurance Co.,2027-01-31\n",
                encoding="utf-8")
            proc, data = run_json("check", str(path),
                                  "--as-of", AS_OF)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(data["rows"], 1)

    def test_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(
                tmp, "\n" + one_row("2027-01-31") + "\n")
            _, data = run_json("check", str(path),
                               "--as-of", AS_OF)
            self.assertEqual(data["rows"], 1)

    def test_header_only_file_is_a_vacuous_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(tmp, "")
            proc, data = run_json("check", str(path),
                                  "--as-of", AS_OF)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("vacuous", data["note"])


class RulesTests(unittest.TestCase):
    def test_rules_text_carries_bands_and_stamp(self):
        proc = run_cli("rules")
        self.assertEqual(proc.returncode, 0)
        for band in ("expired", "due_7", "due_30", "due_60",
                     "due_90", "current"):
            self.assertIn(band, proc.stdout)
        self.assertIn("checked 2026-11", proc.stdout)
        self.assertIn("clearance_cycles_not_modelled",
                      proc.stdout)

    def test_rules_json_shape(self):
        _, data = run_json("rules")
        self.assertEqual(len(data["bands"]), 6)
        self.assertEqual(len(data["checks"]), 4)
        self.assertEqual(len(data["notes"]), 4)


class NoNetworkTests(unittest.TestCase):
    def test_source_has_no_network_or_process_calls(self):
        source = SRC.read_text(encoding="utf-8")
        for banned in ("urllib", "socket", "requests",
                       "subprocess", "os.system"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
