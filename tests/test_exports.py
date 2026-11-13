"""Exportación consistente, no destructiva y reconocible por el lector."""

import contextlib
import csv
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from revlogs.analyzer import LogAnalyzer
from revlogs.cli import main
from revlogs.exports import CsvRenderer, JsonRenderer
from revlogs.models import Evidence, FileResult, ScanResult, Severity
from revlogs.reports import write_report


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / "app.log"
        self.path.write_text('ERROR ERROR WARN "á", detalle\n', encoding="utf-8")
        self.result = LogAnalyzer().scan([self.path])

    def cli(self, *arguments: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return main([str(self.path), *arguments])

    def test_json_schema_and_totals(self) -> None:
        record = json.loads("".join(JsonRenderer().render(self.result)))
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["report_kind"], "revlogs")
        self.assertEqual(record["metadata"]["summary"]["errors"], 2)
        self.assertEqual(record["metadata"]["summary"]["warnings"], 1)

    def test_json_preserves_raw_evidence(self) -> None:
        record = json.loads("".join(JsonRenderer().render(self.result)))
        evidence = record["files"][0]["categories"]["ERROR"]["evidence"][0]
        self.assertEqual(evidence["text"], self.path.read_text().strip())

    def test_csv_totals_match_json(self) -> None:
        rows = list(
            csv.DictReader(io.StringIO("".join(CsvRenderer().render(self.result))))
        )
        values = {
            row["metric"]: row["value"]
            for row in rows
            if row["record_type"] == "summary"
        }
        self.assertEqual(int(values["errors"]), 2)
        self.assertEqual(int(values["warnings"]), 1)

    def test_csv_quotes_unicode_and_delimiters(self) -> None:
        rows = list(
            csv.DictReader(
                io.StringIO("".join(CsvRenderer().render(self.result)), newline="")
            )
        )
        text = next(row["text"] for row in rows if row["record_type"] == "evidence")
        self.assertEqual(text, self.path.read_text().strip())

    def test_formula_like_evidence_is_neutralized_in_csv(self) -> None:
        self.result.files[0].categories[Severity.ERROR].evidence = [
            Evidence(1, ' =HYPERLINK("x")', 1)
        ]
        rows = list(
            csv.DictReader(io.StringIO("".join(CsvRenderer().render(self.result))))
        )
        text = next(row["text"] for row in rows if row["record_type"] == "evidence")
        self.assertTrue(text.startswith("'"))

    def test_csv_internal_newlines_roundtrip(self) -> None:
        self.result.files[0].categories[Severity.ERROR].evidence = [
            Evidence(1, "a\rb\nc", 1)
        ]
        rows = list(
            csv.DictReader(
                io.StringIO("".join(CsvRenderer().render(self.result)), newline="")
            )
        )
        self.assertEqual(
            next(row["text"] for row in rows if row["record_type"] == "evidence"),
            "a\rb\nc",
        )

    def test_all_outputs_in_one_scan(self) -> None:
        self.assertEqual(
            self.cli(
                "-o",
                str(self.root / "out.md"),
                "--json-output",
                str(self.root / "out.json"),
                "--csv-output",
                str(self.root / "out.csv"),
            ),
            0,
        )
        self.assertTrue(
            all(
                (self.root / f"out.{suffix}").exists()
                for suffix in ("md", "json", "csv")
            )
        )

    def test_json_as_primary(self) -> None:
        path = self.root / "out.json"
        self.assertEqual(self.cli("--report-format", "json", "-o", str(path)), 0)
        self.assertEqual(json.loads(path.read_text())["schema_version"], 1)

    def test_csv_as_primary(self) -> None:
        self.assertEqual(
            self.cli("--report-format", "csv", "-o", str(self.root / "out.csv")), 0
        )

    def test_new_report_formats_do_not_contaminate_scan(self) -> None:
        write_report(self.root / "custom.json", self.result, JsonRenderer())
        write_report(self.root / "custom.csv", self.result, CsvRenderer())
        result = LogAnalyzer().scan([self.root])
        self.assertEqual(result.total(Severity.ERROR), 2)
        self.assertEqual(len(result.files), 1)

    def test_same_destination_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.cli(
                "--report-format",
                "json",
                "-o",
                str(self.root / "same.json"),
                "--json-output",
                str(self.root / "same.json"),
            )

    def test_existing_destination_is_preserved(self) -> None:
        path = self.root / "existing.json"
        path.write_text("original")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.cli("--report-format", "json", "-o", str(path))
        self.assertEqual(path.read_text(), "original")

    def test_partial_scan_and_omitted_evidence_are_visible(self) -> None:
        result = LogAnalyzer(max_details=0).scan([self.path, self.root / "missing"])
        record = json.loads("".join(JsonRenderer().render(result)))
        self.assertTrue(record["metadata"]["summary"]["operational_failed"])
        self.assertEqual(record["files"][0]["categories"]["ERROR"]["omitted_lines"], 1)
        self.assertTrue(record["issues"][0]["blocking"])

    def test_empty_and_surrogate_paths_remain_valid_json(self) -> None:
        result = ScanResult(datetime.now())
        result.files.append(FileResult(Path("bad-\udcff")))
        path = self.root / "out.json"
        write_report(path, result, JsonRenderer())
        self.assertEqual(json.loads(path.read_text())["files"][0]["path"], "bad-\udcff")

    def test_toml_export_options(self) -> None:
        config = self.root / "settings.toml"
        config.write_text(
            '[revlogs]\npaths=["app.log"]\nreport_format="json"\noutput="out.json"\ncsv_output="out.csv"'
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--config", str(config)]), 0)
        self.assertTrue((self.root / "out.csv").exists())
