"""Límites de recursos con resultados parciales explícitos."""

import contextlib
import io
import tempfile
import tracemalloc
import unittest
from pathlib import Path

from revlogs.analyzer import LogAnalyzer
from revlogs.cli import main
from revlogs.limits import ScanLimits
from revlogs.models import Severity


class LimitTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def log(self, data: bytes, name: str = "app.log") -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_long_line_is_not_counted_as_complete(self) -> None:
        result = LogAnalyzer(limits=ScanLimits(max_line_bytes=8)).scan(
            [self.log(b"ERROR\nERROR too long\n")]
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertFalse(result.files[0].complete)
        self.assertEqual(result.issues[0].code, "resource_limit")

    def test_exact_line_limit_is_allowed(self) -> None:
        result = LogAnalyzer(limits=ScanLimits(max_line_bytes=6)).scan(
            [self.log(b"ERROR\n")]
        )
        self.assertTrue(result.files[0].complete)

    def test_file_budget_preserves_previous_lines(self) -> None:
        result = LogAnalyzer(limits=ScanLimits(max_file_bytes=6)).scan(
            [self.log(b"ERROR\nWARN\n")]
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.total(Severity.WARNING), 0)
        self.assertTrue(result.operational_failed)

    def test_exact_file_budget_is_complete(self) -> None:
        result = LogAnalyzer(limits=ScanLimits(max_file_bytes=6)).scan(
            [self.log(b"ERROR\n")]
        )
        self.assertFalse(result.operational_failed)

    def test_total_budget_spans_files(self) -> None:
        paths = [self.log(b"ERROR\n", name) for name in ("a", "b", "c")]
        result = LogAnalyzer(limits=ScanLimits(max_total_bytes=6)).scan(paths)
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(len(result.files), 2)
        self.assertLessEqual(result.bytes_read, 7)

    def test_file_count_is_bounded(self) -> None:
        paths = [self.log(b"ERROR\n", name) for name in ("a", "b", "c")]
        result = LogAnalyzer(limits=ScanLimits(max_files=2)).scan(paths)
        self.assertEqual(len(result.files), 2)
        self.assertTrue(result.operational_failed)

    def test_depth_limit_keeps_root_files(self) -> None:
        self.log(b"ERROR\n")
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "deep.log").write_text("FATAL", encoding="utf-8")
        result = LogAnalyzer(limits=ScanLimits(max_depth=0)).scan(
            [self.root], recursive=True
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertTrue(result.operational_failed)

    def test_entry_budget_counts_directories(self) -> None:
        for index in range(5):
            (self.root / str(index)).mkdir()
        result = LogAnalyzer(limits=ScanLimits(max_entries=2)).scan([self.root])
        self.assertTrue(any(issue.code == "resource_limit" for issue in result.issues))

    def test_global_evidence_cap_keeps_counts(self) -> None:
        paths = [self.log(b"ERROR WARN\n", name) for name in ("a", "b")]
        result = LogAnalyzer(limits=ScanLimits(max_total_details=1)).scan(paths)
        self.assertEqual(result.total(Severity.ERROR), 2)
        self.assertEqual(
            sum(len(c.evidence) for f in result.files for c in f.categories.values()), 1
        )
        self.assertTrue(result.details_limited)
        self.assertFalse(result.operational_failed)

    def test_issues_are_bounded_without_hiding_failure(self) -> None:
        paths = [self.root / str(index) for index in range(10)]
        result = LogAnalyzer(limits=ScanLimits(max_issues=2)).scan(paths)
        self.assertEqual(len(result.issues), 2)
        self.assertGreater(result.issues_omitted, 0)
        self.assertTrue(result.operational_failed)

    def test_huge_single_line_uses_bounded_memory(self) -> None:
        path = self.log(b"x" * 2_000_000)
        tracemalloc.start()
        try:
            result = LogAnalyzer(limits=ScanLimits(max_line_bytes=1024)).scan([path])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertTrue(result.operational_failed)
        self.assertLess(peak, 1_000_000)

    def test_cli_limit_validation(self) -> None:
        for arguments in (["--max-line-bytes", "0"], ["--max-depth", "129"]):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                main(arguments)
