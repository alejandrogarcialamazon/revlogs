"""Regresiones de contaminación por reportes y selección de entradas."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from revlogs.analyzer import LogAnalyzer
from revlogs.cli import main
from revlogs.models import Severity
from revlogs.reports import MarkdownRenderer, write_report


class FilterTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "app.log").write_text("ERROR ERROR WARN\n", encoding="utf-8")

    def test_custom_report_does_not_change_repeated_counts(self) -> None:
        analyzer = LogAnalyzer()
        first = analyzer.scan([self.root])
        write_report(self.root / "custom.md", first, MarkdownRenderer())
        second = analyzer.scan([self.root])
        self.assertEqual(second.total(Severity.ERROR), 2)
        self.assertEqual(second.total(Severity.WARNING), 1)
        self.assertEqual(len(second.files), 1)
        self.assertEqual(second.issues, [])

    def test_legacy_report_without_marker_is_skipped(self) -> None:
        report = self.root / "old.txt"
        report.write_text(
            "# Reporte de análisis de logs\n\nInicio: 2026\nERROR", encoding="utf-8"
        )
        self.assertEqual(LogAnalyzer().scan([self.root]).total(Severity.ERROR), 2)

    def test_markdown_log_is_preserved(self) -> None:
        (self.root / "events.md").write_text("ERROR", encoding="utf-8")
        self.assertEqual(LogAnalyzer().scan([self.root]).total(Severity.ERROR), 3)

    def test_report_can_be_included_explicitly(self) -> None:
        result = LogAnalyzer().scan([self.root])
        path = self.root / "custom.md"
        write_report(path, result, MarkdownRenderer())
        included = LogAnalyzer().scan([path], skip_reports=False)
        self.assertGreater(included.total(Severity.ERROR), 0)

    def test_include_patterns(self) -> None:
        (self.root / "other.txt").write_text("FATAL", encoding="utf-8")
        result = LogAnalyzer().scan([self.root], include_patterns=("*.log",))
        self.assertEqual(result.total(Severity.ERROR), 2)

    def test_exclude_wins_over_include(self) -> None:
        result = LogAnalyzer().scan(
            [self.root], include_patterns=("*.log",), exclude_patterns=("app.*",)
        )
        self.assertEqual(result.files, [])

    def test_directory_is_pruned(self) -> None:
        nested = self.root / "archive"
        nested.mkdir()
        (nested / "old.log").write_text("FATAL", encoding="utf-8")
        result = LogAnalyzer().scan(
            [self.root], recursive=True, exclude_patterns=("archive",)
        )
        self.assertEqual(result.total(Severity.ERROR), 2)

    def test_relative_path_pattern(self) -> None:
        nested = self.root / "service"
        nested.mkdir()
        (nested / "other.log").write_text("FATAL", encoding="utf-8")
        result = LogAnalyzer().scan(
            [self.root], recursive=True, include_patterns=("service/*.log",)
        )
        self.assertEqual(result.total(Severity.ERROR), 1)

    def test_exact_directory_exclusion(self) -> None:
        self.assertEqual(
            LogAnalyzer().scan([self.root], excluded=(self.root,)).files, []
        )

    def test_cli_repeated_reports_have_stable_totals(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            for name in ("first.md", "second.md"):
                self.assertEqual(
                    main(
                        [
                            str(self.root),
                            "--include",
                            "*.log",
                            "-o",
                            str(self.root / name),
                        ]
                    ),
                    0,
                )
        self.assertIn("## Errores (2)", (self.root / "second.md").read_text())

    def test_recursive_reports_are_skipped(self) -> None:
        nested = self.root / "output"
        nested.mkdir()
        result = LogAnalyzer().scan([self.root])
        write_report(nested / "any-name.md", result, MarkdownRenderer())
        self.assertEqual(
            LogAnalyzer().scan([self.root], recursive=True).total(Severity.ERROR), 2
        )

    def test_invalid_empty_glob(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main([str(self.root), "--exclude", ""])
