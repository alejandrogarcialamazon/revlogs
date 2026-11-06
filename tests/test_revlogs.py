"""Pruebas de conteo, tolerancia a fallos e integración de la CLI."""

import contextlib
import io
import re
import tempfile
import unittest
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from revlogs.analyzer import LogAnalyzer
from revlogs.cli import main
from revlogs.models import Issue, ScanResult, Severity
from revlogs.reader import discover_files
from revlogs.reports import MarkdownRenderer, write_report


class RevlogsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def log(self, text: str, name: str = "sample.log") -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_occurrences_boundaries_case_and_mixed_severities(self) -> None:
        path = self.log(
            "ERROR error CRITICAL FATAL warning WARN\n"
            "error_code terror warned\n"
            "[error] [warn]\n"
            "INFO todo bien\n"
        )
        result = LogAnalyzer().scan([path])
        self.assertEqual(result.total(Severity.ERROR), 5)
        self.assertEqual(result.total(Severity.WARNING), 3)
        self.assertEqual(result.files[0].lines_read, 4)
        category = result.files[0].categories[Severity.ERROR]
        self.assertEqual(category.matching_lines, 2)
        self.assertEqual(category.evidence[0].occurrences, 4)
        self.assertEqual(category.evidence[1].line_number, 3)

    def test_details_are_bounded_but_counts_are_complete(self) -> None:
        path = self.log("ERROR " + "x" * 100 + "\nERROR\nERROR\n")
        result = LogAnalyzer(max_details=1, max_excerpt_chars=10).scan([path])
        category = result.files[0].categories[Severity.ERROR]
        self.assertEqual(category.occurrences, 3)
        self.assertEqual(len(category.evidence), 1)
        self.assertTrue(category.evidence[0].text.endswith("[truncado]"))
        report = "".join(MarkdownRenderer().render(result))
        self.assertIn("Otras 2 líneas", report)

    def test_zero_details(self) -> None:
        result = LogAnalyzer(max_details=0).scan([self.log("ERROR")])
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.files[0].categories[Severity.ERROR].evidence, [])

    def test_utf8_latin1_and_bom(self) -> None:
        path = self.root / "mixed.log"
        path.write_bytes(
            b"\xef\xbb\xbfERROR UTF-8: \xc3\xb1\nWARNING latin-1: \xf1\nERROR final"
        )
        result = LogAnalyzer().scan([path])
        self.assertEqual(result.total(Severity.ERROR), 2)
        self.assertEqual(result.total(Severity.WARNING), 1)
        self.assertEqual(result.files[0].fallback_lines, 1)
        self.assertTrue(result.files[0].complete)

    def test_recursive_and_duplicate_paths(self) -> None:
        direct = self.log("ERROR")
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "other.log").write_text("WARN", encoding="utf-8")
        first = LogAnalyzer().scan([self.root, direct])
        self.assertEqual(len(first.files), 1)
        recursive = LogAnalyzer().scan([self.root, direct], recursive=True)
        self.assertEqual(len(recursive.files), 2)
        self.assertEqual(recursive.total(Severity.WARNING), 1)

    def test_missing_path_does_not_stop_other_files(self) -> None:
        result = LogAnalyzer().scan([self.root / "missing", self.log("ERROR")])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.total(Severity.ERROR), 1)

    def test_permission_error_during_discovery(self) -> None:
        path = self.log("ERROR")
        issues: list[Issue] = []
        with patch("revlogs.reader.os.access", return_value=False):
            files = list(
                discover_files([path], recursive=False, on_issue=issues.append)
            )
        self.assertEqual(files, [])
        self.assertIn("permiso", issues[0].message)

    def test_failure_mid_read_keeps_partial_counts(self) -> None:
        def failing_lines(path: Path) -> Iterator[tuple[int, str, bool]]:
            yield 1, "ERROR", False
            raise PermissionError("Acceso revocado")

        path = self.log("")
        with patch("revlogs.analyzer.read_lines", side_effect=failing_lines):
            result = LogAnalyzer().scan([path])
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertFalse(result.files[0].complete)
        self.assertEqual(len(result.issues), 1)

    def test_symbolic_links_and_special_files_are_skipped(self) -> None:
        import os

        path = self.log("ERROR")
        (self.root / "alias.log").symlink_to(path)
        os.mkfifo(self.root / "pipe")
        result = LogAnalyzer().scan([self.root], recursive=True)
        self.assertEqual(len(result.files), 1)
        self.assertEqual(len(result.issues), 2)

    def test_custom_patterns_and_invalid_regex(self) -> None:
        result = LogAnalyzer(error_patterns=[r"\bfailed\b"]).scan(
            [self.log("FAILED ERROR")]
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        with self.assertRaises(re.error):
            LogAnalyzer(error_patterns=["["])
        with self.assertRaises(ValueError):
            LogAnalyzer(error_patterns=[".*"])

    def test_markdown_escapes_untrusted_log_content(self) -> None:
        result = LogAnalyzer().scan([self.log("ERROR <script>x</script> | **x**\x1b")])
        report = "".join(MarkdownRenderer().render(result))
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)
        self.assertIn(r"\|", report)
        self.assertNotIn("\x1b", report)

    def test_atomic_writer_preserves_existing_file_and_cleans_up(self) -> None:
        output = self.root / "report.md"
        output.write_text("original", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            write_report(output, ScanResult(datetime.now()), MarkdownRenderer())
        self.assertEqual(output.read_text(), "original")
        self.assertEqual(list(self.root.iterdir()), [output])

    def test_writer_failure_does_not_publish_partial_report(self) -> None:
        class BrokenRenderer:
            def render(self, result: ScanResult) -> Iterator[str]:
                yield "partial"
                raise OSError("Disco lleno")

        with self.assertRaises(OSError):
            write_report(
                self.root / "report.md", ScanResult(datetime.now()), BrokenRenderer()
            )
        self.assertEqual(list(self.root.iterdir()), [])

    def run_cli(self, *args: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return main(args)

    def test_cli_report_and_fail_on(self) -> None:
        path = self.log("ERROR\nWARN")
        output = self.root / "report.md"
        self.assertEqual(self.run_cli(str(path), "-o", str(output)), 0)
        self.assertIn("## Errores (1)", output.read_text(encoding="utf-8"))
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            self.run_cli(
                str(path), "-o", str(self.root / "ci.md"), "--fail-on", "error"
            ),
            1,
        )

    def test_cli_defaults_and_operational_failure(self) -> None:
        path = self.log("INFO")
        with patch("revlogs.cli.DEFAULT_PATHS", (path,)):
            self.assertEqual(self.run_cli("-o", str(self.root / "default.md")), 0)
        output = self.root / "missing.md"
        self.assertEqual(self.run_cli(str(self.root / "absent"), "-o", str(output)), 2)
        self.assertTrue(output.exists())

    def test_cli_warning_threshold_and_empty_directory(self) -> None:
        path = self.log("WARN")
        self.assertEqual(
            self.run_cli(
                str(path), "-o", str(self.root / "warning.md"), "--fail-on", "warning"
            ),
            1,
        )
        empty = self.root / "empty"
        empty.mkdir()
        self.assertEqual(self.run_cli(str(empty), "-o", str(self.root / "empty.md")), 2)

    def test_cli_rejects_existing_output_and_invalid_pattern(self) -> None:
        path = self.log("ERROR", "input.md")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main([str(path), "-o", str(path)])
            self.assertEqual(raised.exception.code, 2)
            with self.assertRaises(SystemExit):
                main([str(path), "--error-pattern", "["])
        self.assertEqual(path.read_text(), "ERROR")


if __name__ == "__main__":
    unittest.main()
