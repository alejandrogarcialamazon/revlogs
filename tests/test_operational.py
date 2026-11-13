"""Estados operativos de entradas explícitas, opcionales y vacías."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from revlogs.analyzer import LogAnalyzer
from revlogs.cli import main
from revlogs.reports import MarkdownRenderer


class OperationalTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.log = self.root / "app.log"
        self.log.write_text("INFO\n", encoding="utf-8")
        self.missing = self.root / "absent"

    def cli(self, *args: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return main([*args, "-o", str(self.root / "report.md")])

    def test_missing_defaults_are_nonblocking(self) -> None:
        with patch("revlogs.cli.DEFAULT_PATHS", (self.log, self.missing)):
            self.assertEqual(self.cli(), 0)

    def test_explicit_missing_path_is_blocking(self) -> None:
        self.assertEqual(self.cli(str(self.log), str(self.missing)), 2)

    def test_strict_defaults_are_blocking(self) -> None:
        with patch("revlogs.cli.DEFAULT_PATHS", (self.log, self.missing)):
            self.assertEqual(self.cli("--strict"), 2)

    def test_all_defaults_missing_still_fail(self) -> None:
        with patch("revlogs.cli.DEFAULT_PATHS", (self.missing,)):
            self.assertEqual(self.cli(), 2)

    def test_empty_directory_has_reason(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        result = LogAnalyzer().scan([empty])
        self.assertEqual(result.issues[-1].code, "empty_directory")
        self.assertTrue(result.operational_failed)

    def test_filtered_selection_has_reason(self) -> None:
        result = LogAnalyzer().scan([self.root], include_patterns=("*.other",))
        self.assertEqual(result.issues[-1].code, "empty_selection")

    def test_permission_errors_are_never_optional(self) -> None:
        with patch("revlogs.reader.os.access", return_value=False):
            result = LogAnalyzer().scan([self.log], optional_paths=True)
        self.assertTrue(result.issues[0].blocking)

    def test_report_distinguishes_optional_advice(self) -> None:
        result = LogAnalyzer().scan([self.log, self.missing], optional_paths=True)
        self.assertFalse(result.operational_failed)
        self.assertIn("Aviso", "".join(MarkdownRenderer().render(result)))
